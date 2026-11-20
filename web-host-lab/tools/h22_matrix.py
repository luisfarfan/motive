#!/usr/bin/env python3
"""Read-only aggregation of immutable native matrices and independent audits."""
import argparse
import hashlib
import json
from pathlib import Path
from h19_lifecycle_check import Inputs,require

LAB=Path(__file__).resolve().parents[1]


def observed_case_result(native,analysis,workload=None,requires_workload=False):
    """Preserve the audited case scope; PASS does not invent a cadence window."""
    if native.get('status')!='PASS' or native.get('network_lab',{}).get('status')!='PASS' or analysis.get('status')!='PASS':
        return 'FAIL'
    if requires_workload:
        if workload is None:return 'NOT_EVALUATED'
        return 'PASS' if workload.get('status')=='PASS' else 'FAIL'
    return 'PASS'


def verify_audit_inputs(path,data):
    inputs=Inputs(path.parent)
    require('report.json' in data.get('input_sha256',{}),'AUDIT_REPORT_UNBOUND')
    for relative,expected in data['input_sha256'].items():
        actual=hashlib.sha256(inputs.read(relative,maximum=64*1024**2)).hexdigest()
        require(actual==expected,'AUDIT_INPUT_HASH')
    return inputs.hashes


def summarize(roots):
    hashes={};rows=[]
    def read(p):
        data=p.read_bytes();hashes[str(p.relative_to(LAB))]=hashlib.sha256(data).hexdigest();return json.loads(data)
    def audit(p):
        result=read(p)
        for relative,digest in verify_audit_inputs(p,result).items():hashes[str((p.parent/relative).relative_to(LAB))]=digest
        return result
    for root in roots:
        root=root.resolve();plan=read(root/'plan.json');suite=plan['suite']
        for name,build,scenario,count,seconds,width,height,intermittent in plan['cases']:
            path=LAB/'evidence'/(root.name+'-'+name)
            row={'suite':suite,'case':name,'path':str(path.relative_to(LAB)),
                'build':build,'scenario':scenario,'instances':count,'seconds':seconds,
                'width':width,'height':height,'fps':30,'functional':'NOT_EVALUATED','performance':'NOT_EVALUATED'}
            rows.append(row)
            if not (path/'report.json').exists():continue
            report=read(path/'report.json');req=report['requested']
            if any(req[k]!=v for k,v in [('scenario',scenario),('instances',count),('duration_ms',seconds*1000),('width',width),('height',height),('fps',30)]):raise ValueError('PLAN_RUN_MISMATCH')
            row['executable_sha256']=report['expected_executable_sha256']
            row['native_status']=report['status']
            row['network_lab']=report.get('network_lab',{}).get('status','NOT_OBSERVED')
            if not (path/'analysis.json').exists():
                row['functional']='FAIL' if report['status']=='FAIL' else 'NOT_EVALUATED';continue
            audit_path=path/('analysis-continuity.json' if (path/'analysis-continuity.json').exists() else 'analysis.json')
            analysis=audit(audit_path)
            row['audit']=str(audit_path.relative_to(LAB))
            row['case_result']=observed_case_result(report,analysis,requires_workload=intermittent)
            row['functional']=analysis.get('functional_status','FAIL') if report['status']=='PASS' else 'FAIL'
            row['performance']=analysis.get('performance_status','NOT_EVALUATED')
            close=analysis.get('gates',{}).get('native_close_cleanup',{})
            row['rss_peak_mib']=close.get('peak_rss_mib')
            row['close_ms']=close.get('close_to_shutdown_ms')
            row['cleanup_ms']=close.get('supervisor_cleanup_ms')
            windows=analysis.get('resources',{}).get('windows',[]);row['resources']=[{
                'start_ms':x['requested_start_ms'],'end_ms':x['requested_end_ms'],
                'footprint_median_mib':x['physical_footprint_mib']['median'],
                'cpu_window_mean_percent_one_core':x['observed_cpu_percent_one_core']} for x in windows]
            intervals=[x['interval'] for x in analysis.get('steady_frames',[])]
            gaps=[v['max_gap_ms'] for x in intervals for v in x.get('continuity',{}).values()]
            if intermittent:
                if not (path/'workload-analysis.json').exists():row['performance']='NOT_EVALUATED';continue
                workload=audit(path/'workload-analysis.json');row['workload_audit']=str((path/'workload-analysis.json').relative_to(LAB))
                row['case_result']=observed_case_result(report,analysis,workload,requires_workload=True)
                row['performance']=workload.get('performance_status','FAIL')
                if workload.get('functional_status')!='PASS':row['functional']='FAIL'
                intervals=[x for i in workload.get('instances',[]) for x in i['active_intervals'] if x['capacity_interval']]
                gaps=[x[k] for x in intervals for k in ('paint_max_active_gap_ms','acquisition_max_active_gap_ms','completion_max_active_gap_ms')]
                peer=workload.get('peer_continuity',{})
                if peer.get('status')=='FAIL':row['performance']='FAIL'
                gaps.extend(v for op in peer.get('operations',[]) for p in op['peers'] for v in p['maximum_gaps_ms'].values())
                row['complete_capacity_events']=workload.get('capacity_complete_events',0)
                accounts=[i['event_accounting'] for i in workload.get('instances',[]) if 'event_accounting' in i]
                row['maximum_dispatch_to_active_ms']=max((a['maximum_dispatch_to_active_ms'] for a in accounts
                    if a['maximum_dispatch_to_active_ms'] is not None),default=None)
                outcomes=[e['outcome'] for a in accounts for e in a['events']]
                row['event_dispositions']={key:outcomes.count(key) for key in sorted(set(outcomes))}
            else:
                gaps.extend(v['max_gap_ms'] for op in analysis.get('operations',[]) for p in op['peers'] for k,v in p.items() if k in ('paint','acquisition','completion'))
            row['minimum_interval_acquisition_fps']=min((x['acquisition_fps'] for x in intervals),default=None)
            row['worst_interval_p95_age_ms']=max((x['frame_age_ms']['p95'] for x in intervals if x['frame_age_ms']['p95'] is not None),default=None)
            row['maximum_active_gap_ms']=max(gaps,default=None)
            if row['maximum_active_gap_ms'] is None:row['performance']='NOT_EVALUATED'
    return {'status':'PASS' if rows and all(x['functional']==x['performance']=='PASS' for x in rows) else 'PARTIAL',
        'scope':'owned CEF host and lab consumer only; no OBS/capture/encoder/game/stream capacity',
        'rows':rows,'input_sha256':hashes,'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--roots',required=True,type=Path,nargs='+');a=p.parse_args();result=summarize(a.roots)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':result['status'],'cases':len(result['rows'])}))
