#!/usr/bin/env python3
"""Fixed serial cold suspension/reload/viewport replacement, not hot resize."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from run_owned_fixture import LAB, canonical_directory, match_build_report, read_json, regular_bytes, require, save_json, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root',type=Path,required=True);p.add_argument('--expected-sha256',required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--first-generation',type=int,default=30)
    args=p.parse_args();require(1<=args.first_generation<=9007199254740989,'GENERATION')
    root,build_path,build=match_build_report(args.build_root,args.expected_sha256)
    output=Path(os.path.abspath(args.output_dir));canonical_directory(output.parent);output.mkdir(mode=0o700)
    report={'status':'FAIL','started_utc':datetime.now(timezone.utc).isoformat(),'artifact_sha256':args.expected_sha256,
            'build_report':str(build_path.relative_to(LAB)),'profile':'owned-smoke','native_executed':False,
            'steps':[],'transitions':[],'runtime_contract':'Lifecycle.close(false) -> closed -> Suspended -> restart_after_reap -> new generation',
            'lifecycle_contract_sha256':sha(regular_bytes(LAB/'poc/browser-host/src/lifecycle.rs',65536)),
            'source_inventory':build.get('fixture_inventory'),'source_inventory_unchanged_between_steps':True,
            'limitations':['Cold restart does not preserve the JavaScript heap.','Viewport changes replace the process, not WasResized in place.',
                           'Origins below are constructed by the frozen native generation contract, not independent network observations.',
                           'Cleanup concerns observed owned identities, not an OS sandbox or hostile process escape.']}
    private_roots=[];origins=[]
    try:
        for offset,(name,width,height) in enumerate([('initial',640,360),('cold-reload',640,360),('resize-replacement',540,960)]):
            generation=args.first_generation+offset
            if offset:
                prior=report['steps'][-1]
                require(prior['status']=='PASS' and prior['observed_tree_reaped'] is True,'REAP_BEFORE_REPLACEMENT')
                report['transitions'].append({'from_generation':generation-1,'to_generation':generation,'action':name,
                    'prior_state':'Suspended after native close and observed reap','fresh_generation_before_launch':True,
                    'reuse_old_origin_cache_or_frame_lease':False})
            command=[sys.executable,str(LAB/'tools/run_owned_fixture.py'),'--build-root',str(root),'--expected-sha256',args.expected_sha256,
                     '--generation',str(generation),'--width',str(width),'--height',str(height),'--fps','30','--duration-ms','5000',
                     '--deadline-seconds','10','--rss-limit-mib','2048','--output-dir',str(output/name),'--png']
            result=subprocess.run(command,capture_output=True,text=True)
            child=read_json(output/name/'report.json',4*1024**2)
            report['native_executed']=report['native_executed'] or child.get('native_host_executed') is True
            clean=child.get('supervision',{}).get('final_cleanup_observed_tree') is True and child.get('supervision',{}).get('final_remaining_observed_pids')==[]
            require(result.returncode==0 and child.get('status')=='PASS' and clean,'NATIVE_REPLACEMENT_STEP_FAILED')
            require(child.get('native_generation')==generation,'HOST_GENERATION')
            for sample in ('first','latest'):
                metadata=child['samples'][sample]['metadata']
                require((metadata['generation'],metadata['width'],metadata['height'],metadata['epoch'])==(generation,width,height,1),'CURRENT_GENERATION_LAYOUT')
            private_roots.append(child['raw_evidence_root']);origins.append(f'motive://i1-g{generation}/')
            require(len(set(private_roots))==len(private_roots) and len(set(origins))==len(origins),'FRESH_ROOT_AND_ORIGIN')
            report['steps'].append({'name':name,'status':'PASS','generation':generation,'width':width,'height':height,
                'observed_tree_reaped':clean,'report':name+'/report.json','report_sha256':sha(regular_bytes(output/name/'report.json',4*1024**2)),
                'private_root':private_roots[-1],'constructed_origin':origins[-1],'epoch':1})
            save_json(output/f'checkpoint-{offset}.json',report)
        report.update(status='PASS',gates={'cold_suspend_and_resume':'PASS','reload_by_process_replacement':'PASS','resize_by_process_replacement':'PASS','hot_reload_or_resize':'NOT_EVALUATED','preserved_js_heap':'NOT_EVALUATED'})
    except BaseException as error:
        report['error_type']=type(error).__name__;raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save_json(output/'summary.json',report)
        print(json.dumps({'status':report['status'],'steps':len(report['steps']),'summary':str(output/'summary.json')}))
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
