#!/usr/bin/env python3
"""Read-only Goal multi-instance regression. ACK, pixels and native close stay separate."""
import argparse
import hashlib
import json
from pathlib import Path

from h19_lifecycle_check import Inputs, require, conservation, phase, LAB_ROOT, EvidenceError


def phase_order(trace, names):
    times=[phase(trace,name) for name in names]
    require(all(a<b for a,b in zip(times,times[1:])), 'GOAL_PHASE_ORDER')
    return dict(zip(names,times))


def analyze(root):
    inputs=Inputs(root)
    report=inputs.json('report.json')
    manifest=inputs.json('instances.json')
    supervision=inputs.json('supervision.json.gz',compressed=True,maximum=64*1024**2)
    require(report['status']=='PASS' and report['native_host_executed'] is True, 'SCOPED_NATIVE_RUN')
    require(supervision['reason']=='exit' and supervision['returncode']==0 and supervision['final_cleanup_observed_tree'] is True and not supervision['final_remaining_observed_pids'], 'NATIVE_EXIT_AND_REAP')
    build_path=LAB_ROOT/report['build_report']
    build_raw=build_path.read_bytes()
    require(hashlib.sha256(build_raw).hexdigest()==report['build_report_sha256'], 'BUILD_PROVENANCE')
    build=json.loads(build_raw)
    require('goal' in build['profile'] and build['binaries'][0]['sha256']==report['expected_executable_sha256'], 'GOAL_BUILD')
    controls='controls' in build['profile']
    requested=report['requested']
    require(requested['instances']==3 and manifest['configured_widgets']==3, 'THREE_GOAL_INSTANCES')
    states=manifest['instances']
    require({s['instance'] for s in states}=={1,2,3}, 'GOAL_IDENTITIES')
    rows=[]
    for state in states:
        identity=(state['instance'],state['generation'],state['epoch'])
        directory='instance-%d-g%d-e%d'%identity
        trace=inputs.trace(directory+'/lifecycle.jsonl')
        names=[r['phase'] for r in trace]
        require(state['closed'] and state['closed_ns']>0,'BROWSER_FINAL_CLOSE')
        for name in ('bootstrap_loaded','renderer_ready','properties_dispatched','before_close','frame_report_written'):
            phase(trace,name)
        require('bridge_status_rejected' not in names and 'fixed_control_failed' not in names,'GOAL_NATIVE_ADMISSION')
        accounting=conservation(inputs.json(directory+'/frames.json'))
        samples={}
        for label in ('first','latest','visual'):
            path=Path(root)/directory/(label+'.bgra.gz')
            if not path.exists():continue
            pixels=inputs.read(directory+'/'+label+'.bgra.gz',compressed=True,maximum=1920*1080*4)
            meta=inputs.json(directory+'/'+label+'.json')
            require(tuple(meta[k] for k in ('instance','generation','epoch'))==identity,'GOAL_PIXEL_IDENTITY')
            require(meta['width']==requested['width'] and meta['height']==requested['height'] and meta['stride']==meta['width']*4 and len(pixels)==meta['stride']*meta['height'],'GOAL_PIXEL_LAYOUT')
            alphas=pixels[3::4]
            require(all(max(pixels[i:i+3])<=pixels[i+3]+1 for i in range(0,len(pixels),4)),'GOAL_PREMULTIPLIED_BOUND')
            samples[label]={'zero_alpha':alphas.count(0),'opaque':alphas.count(255),
                            'partial':len(alphas)-alphas.count(0)-alphas.count(255),'total':len(alphas),
                            'raw_sha256':hashlib.sha256(pixels).hexdigest()}
        if state['instance']==1:
            phase_order(trace,['bootstrap_loaded','renderer_ready','properties_dispatched','goal_dispatched','visual_active'])
            active=samples.get('visual')
            require(active and active['zero_alpha']>0 and active['partial']>0 and active['opaque']>0,'GOAL_ACTIVE_TRANSPARENT_PIXELS')
            if controls:
                phase_order(trace,['visual_active','repeated_event_rejected','cancel_dispatched','cancel_acknowledged',
                                   'resume_dispatched','resume_acknowledged','dispose_dispatched','dispose_acknowledged','before_close'])
            elif requested['scenario']=='hidden':
                phase_order(trace,['visual_active','hidden_cancel_dispatched','hidden_cancel_acknowledged','hidden_begin',
                                   'hidden_resume_dispatched','hidden_resume_acknowledged','hidden_end','before_close'])
            elif not state['failed']:
                phase_order(trace,['goal_dispatched','visual_active','visual_complete','before_close'])
            if not state['failed']:
                require(samples['latest']['zero_alpha']==samples['latest']['total'],'GOAL_FINAL_TRANSPARENCY')
        else:
            require('goal_dispatched' not in names and 'visual_active' not in names and 'visual' not in samples,'GOAL_EVENT_CONTAMINATION')
            require(samples['latest']['zero_alpha']==samples['latest']['total'],'PEER_UNEXPECTED_PIXELS')
        rows.append({'identity':identity,'browser_id':state['browser_id'],'renderer_pid':state['renderer_pid_reported'],
                     'targeted_goal_events':names.count('goal_dispatched'),'active_observations':names.count('visual_active'),
                     'accounting':accounting,'samples':samples,'closed':state['closed'],'failed':state['failed']})
    if requested['scenario']=='crash':
        target=[s for s in states if s['instance']==1]
        require(len(target)==2 and target[0]['failed'] and not target[1]['failed'],'GOAL_CRASH_RECOVERY')
        require(target[0]['renderer_exit_code']==22016 and target[1]['generation']==target[0]['generation']+1 and target[1]['browser_id']!=target[0]['browser_id'] and target[0]['closed_ns']<target[1]['created_ns'],'GOAL_CRASH_GENERATION_ORDER')
    return {'status':'PASS','scope':'owned original Goal multi-instance native regression',
            'scenario':requested['scenario'],'controls':controls,'viewport':[requested['width'],requested['height']],
            'instances':rows,'input_sha256':inputs.hashes,'semantic_visual_inspection':'NOT_EVALUATED',
            'production':'NOT_EVALUATED','third_party_execution':'BLOCKED',
            'limits':['Native status is not pixel evidence; raw BGRA is checked separately.',
                      'Pixel arithmetic does not itself read the rendered text; inspect derived PNG separately.',
                      'Restart is a new explicit fixture generation and new test event; no Production replay is wired.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:result=analyze(args.directory)
    except (OSError,ValueError,KeyError,TypeError) as error:
        result={'status':'FAIL','error':str(error),'scope':'owned Goal regression evidence'}
    output=args.output or args.directory/'analysis.json'
    with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':result['status'],'analysis':str(output),'error':result.get('error')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
