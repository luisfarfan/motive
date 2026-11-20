#!/usr/bin/env python3
"""Read-only cadence/visibility audit for intermittent owned widget events.

All active and interrupted intervals remain in the report. Capacity uses complete
events beginning after the declared 10 s warmup. Idle/hidden periods have no
invented 30 FPS expectation. No interval or limit is selected after seeing data.
"""
import argparse
import hashlib
import json
from pathlib import Path
from h19_lifecycle_check import Inputs,require,phase,NS_MS
from h19_performance_audit import native_interval


def active_windows(trace):
    result=[];start=None
    for row in trace:
        name=row['phase'];at=row['observed_ns']
        if name=='visual_active':
            require(start is None,'OVERLAPPING_ACTIVE_EVENTS');start=at
        elif start is not None and name in ('visual_complete','hidden_cancel_dispatched','close_requested','renderer_exit_requested'):
            require(at>start,'ACTIVE_ORDER')
            result.append((start,at,name=='visual_complete',name));start=None
    require(start is None,'UNTERMINATED_VISUAL_ACTIVITY')
    return result


def active_gap(times,start,end):
    values=[start,*[t for t in times if start<t<end],end]
    # There is no animation expectation before/after a typed active interval.
    # The entire interval is retained, including dispatch-to-first-paint latency.
    return max(b-a for a,b in zip(values,values[1:]))/NS_MS


def event_accounting(trace,goal,static):
    """Every actual native dispatch needs a finite observed disposition.

    This reports dispatch-to-active latency, not semantic pixels or end-to-end
    controller latency. No new cadence threshold and no invented ACK for idle.
    """
    pending=None;bootstrap=0;events=[];closing=False
    for row in trace:
        name=row['phase'];at=row['observed_ns']
        if name in ('fixture_goal_dispatched','fixture_event_dispatched'):
            require(pending is None,'EVENT_DISPATCH_UNANSWERED');pending=at
        elif name=='visual_active':
            require(not static,'STATIC_BECAME_ACTIVE')
            if pending is None:
                bootstrap+=1;require(goal and bootstrap<=1,'UNSOLICITED_VISUAL_ACTIVITY')
            else:
                require(at>=pending,'EVENT_RESPONSE_ORDER')
                events.append({'dispatched_ns':pending,'observed_ns':at,'outcome':'active','latency_ms':(at-pending)/NS_MS});pending=None
        elif name=='fixture_event_rejected':
            require(static and pending is not None,'UNEXPECTED_EVENT_REJECTION')
            events.append({'dispatched_ns':pending,'observed_ns':at,'outcome':'static_rejected','latency_ms':(at-pending)/NS_MS});pending=None
        elif name in ('remove_requested','restart_requested','cold_replacement_requested','renderer_exit_requested','suspend_requested'):
            closing=True
        elif pending is not None and name in ('close_requested','hidden_cancel_dispatched'):
            require(closing or name=='hidden_cancel_dispatched','FINAL_UNANSWERED_EVENT')
            events.append({'dispatched_ns':pending,'observed_ns':at,'outcome':'explicitly_interrupted_before_active','latency_ms':(at-pending)/NS_MS});pending=None
    require(pending is None,'UNANSWERED_EVENT_AT_END')
    return {'bootstrap_activities':bootstrap,'events':events,
        'maximum_dispatch_to_active_ms':max((e['latency_ms'] for e in events if e['outcome']=='active'),default=None)}


def analyze(root):
    inputs=Inputs(root);r=inputs.json('report.json');m=inputs.json('instances.json')
    build=json.loads((Path(__file__).resolve().parents[1]/r['build_report']).read_text())
    require('goal' in build['profile'] or build.get('controlled_widget_fixtures'),'INTERMITTENT_OWNED_WORKLOAD')
    goal='goal' in build['profile'];output={'status':'FAIL','functional_status':'PASS','performance_status':'NOT_EVALUATED',
        'scope':'owned original Goal or H22 web fixture; no stream/OBS acceptance','instances':[],
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':inputs.hashes}
    steady=[];activities={}
    for s in m['instances']:
        identity=(s['instance'],s['generation'],1);directory='instance-%d-g%d-e%d'%identity
        tr=inputs.trace(directory+'/lifecycle.jsonl');f=inputs.json(directory+'/frames.json');samples=f['samples']
        names=[row['phase'] for row in tr];windows=active_windows(tr)
        activities[(s['instance'],s['generation'])]=(windows,samples)
        require(not any(n in names for n in ('bridge_status_rejected','fixture_goal_failed','visibility_transition_rejected')),'WORKLOAD_PROTOCOL_REJECTED')
        static=not goal and r['requested']['scenario'] in ('widget-mix','widget-lifecycle','widget-soak') and s['instance']%3==0
        row={'identity':identity,'active_intervals':[],'hidden_intervals':[],'static':static,
            'idle_without_event':not static and not windows,'event_accounting':event_accounting(tr,goal,static)}
        for start,end,complete,reason in windows:
            perf=native_interval(samples,start,end,r['requested']['fps'])
            perf.update(completed_event=complete,terminal_reason=reason,
                paint_max_active_gap_ms=active_gap([x[1] for x in samples],start,end),
                acquisition_max_active_gap_ms=active_gap([x[2] for x in samples],start,end),
                completion_max_active_gap_ms=active_gap([x[2]+x[3] for x in samples],start,end))
            perf['after_warmup']=start>=s['created_ns']+10_000*NS_MS
            perf['capacity_interval']=complete and perf['after_warmup']
            if perf['capacity_interval']:
                if max(perf[k] for k in ('paint_max_active_gap_ms','acquisition_max_active_gap_ms','completion_max_active_gap_ms'))>=250:perf['status']='FAIL'
                steady.append(perf)
            row['active_intervals'].append(perf)
        hidden=None
        for t in tr:
            if t['phase']=='hidden_begin':
                require(hidden is None,'DUPLICATE_HIDE');hidden=t['observed_ns']
                cancel=[x['observed_ns'] for x in tr if x['phase']=='hidden_cancel_acknowledged' and x['observed_ns']<=hidden]
                require(cancel and hidden-cancel[-1]<1000*NS_MS,'CANCEL_BEFORE_HIDE')
            if t['phase']=='hidden_end':
                require(hidden is not None,'SHOW_WITHOUT_HIDE');end=t['observed_ns']
                require(not any(hidden+250*NS_MS<x[1]<end for x in samples),'PAINT_WHILE_SETTLED_HIDDEN')
                resume=[x['observed_ns'] for x in tr if x['phase']=='hidden_resume_acknowledged' and hidden<x['observed_ns']<=end]
                require(resume,'RESUME_ACK_BEFORE_SHOW')
                next_event=next((x['observed_ns'] for x in tr if x['phase'] in ('fixture_goal_dispatched','fixture_event_dispatched') and x['observed_ns']>end),s['closed_ns'])
                require(not any(end<x['observed_ns']<next_event and x['phase']=='visual_active' for x in tr),'SHOW_REPLAYED_EVENT')
                row['hidden_intervals'].append({'begin_ns':hidden,'end_ns':end,'settled_paints':0,'replay_on_show':False});hidden=None
        require(hidden is None or s['closed'],'UNCLOSED_HIDDEN')
        record=next(x for x in r['instances'] if tuple(x['identity'])==identity)
        if windows:
            visual=record['samples'].get('visual');require(visual,'ACTIVE_FRAME_NOT_RETAINED')
            alpha=visual['alpha'];require(alpha['zero_pixels']>0 and alpha['partial_pixels']>0 and alpha['opaque_pixels']>0,'VISUAL_ALPHA')
        # A deliberately closed/crashed active generation has no obligation to
        # produce a final transparent paint after it loses authority. The native
        # audit proves revocation/close/conservation; preserved old pixels remain
        # evidence, never a drawable replacement. Completed or idle Goal does
        # still require its observed transparent final frame.
        if goal and not s['failed'] and (not windows or windows[-1][2]):
            require(record['samples']['latest']['alpha']['zero_pixels']==s['width']*s['height'],'GOAL_FINAL_TRANSPARENCY')
        row['final_transparency_required']=goal and not s['failed'] and (not windows or windows[-1][2])
        output['instances'].append(row)
    output['peer_continuity']={'status':'NOT_APPLICABLE','operations':[]}
    if r['requested']['scenario'] in ('widget-lifecycle','goal-lifecycle','widget-soak'):
        # Reuse operation boundaries independently derived from native traces.
        # Every overlapping FULL active interval is kept; idle periods have no
        # invented animation requirement, and clipping cannot hide a stall.
        analysis=inputs.json('analysis.json')
        for operation in analysis['operations']:
            item={k:operation[k] for k in ('instance','generation','phase','start_ns','end_ns')}
            item['peers']=[];action=operation['start_ns']+100*NS_MS
            for identity,(windows,samples) in activities.items():
                if identity[0]==operation['instance']:continue
                for start,end,_,reason in windows:
                    if end<=operation['start_ns'] or start>=operation['end_ns']:continue
                    values=[active_gap([x[column]+(x[3] if column==2 and completion else 0) for x in samples],start,end)
                        for column,completion in ((1,False),(2,False),(2,True))]
                    item['peers'].append({'identity':identity,'active_start_ns':start,'active_end_ns':end,
                        'terminal_reason':reason,'active_during_operation':start<=action<end,
                        'maximum_gaps_ms':dict(zip(('paint','acquisition','completion'),values)),
                        'status':'PASS' if max(values)<250 else 'FAIL'})
            item['active_peer_observed']=any(x['active_during_operation'] for x in item['peers'])
            item['status']='PASS' if item['active_peer_observed'] and all(x['status']=='PASS' for x in item['peers']) else 'FAIL'
            output['peer_continuity']['operations'].append(item)
        ops=output['peer_continuity']['operations']
        output['peer_continuity']['status']='PASS' if ops and all(x['status']=='PASS' for x in ops) else 'FAIL'
    require(r['status']=='PASS','NATIVE_RUN_NOT_PASS')
    output['performance_status']='PASS' if steady and all(x['status']=='PASS' for x in steady) else 'FAIL' if steady else 'NOT_EVALUATED'
    if output['peer_continuity']['status']=='FAIL':output['performance_status']='FAIL'
    output['capacity_complete_events']=len(steady)
    output['status']='PASS' if output['performance_status']=='PASS' else output['performance_status']
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:result=analyze(a.root)
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as e:result={'status':'FAIL','error':str(e)}
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('instances','input_sha256','peer_continuity')},indent=2))
    raise SystemExit(result['status']=='FAIL')
