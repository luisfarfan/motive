#!/usr/bin/env python3
"""Independent retained-evidence audit. No native launches; no runner imports.

Shares H19's strict parser/accounting and independent Mach resource derivation,
not its runner. Keeps observed-paint, acquisition and completion gaps separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from h19_lifecycle_check import Inputs, conservation, phase, require, NS_MS
from h19_performance_audit import reconstruct_resources, resource_window, native_interval, fixed_file_counters
from h22_network_check import inspect_netlog

LAB = Path(__file__).resolve().parents[1]


def gaps(times, start, end):
    """Include straddling samples: clipping at an operation must not hide a gap."""
    require(end > start, 'GAP_WINDOW')
    before = [t for t in times if t <= start]
    inside = [t for t in times if start < t < end]
    after = [t for t in times if t >= end]
    require(before and after, 'PEER_WINDOW_COVERAGE')
    rows = [before[-1], *inside, after[0]]
    pairs = [(b-a, a, b) for a, b in zip(rows, rows[1:])]
    maximum, a, b = max(pairs)
    return {'max_gap_ms': maximum / NS_MS, 'gap_start_ns': a, 'gap_end_ns': b,
            'observations': len(rows), 'status': 'PASS' if maximum < 250 * NS_MS else 'FAIL'}


def analyze(root):
    root = Path(root)
    inputs = Inputs(root)
    result = {'status': 'FAIL', 'scope': 'owned CEF lab; no OBS or production credential acceptance',
              'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'input_sha256': inputs.hashes, 'gates': {}, 'operations': [], 'epochs': []}

    def gate(name, check):
        try:
            detail = check()
            result['gates'][name] = {'status': 'PASS', **(detail or {})}
        except (ValueError, KeyError, TypeError, OSError, StopIteration) as error:
            result['gates'][name] = {'status': 'FAIL', 'error': str(error)[:240]}

    try:
        report = inputs.json('report.json')
        manifest = inputs.json('instances.json')
        raw_bytes = inputs.read('supervision.json.gz', maximum=64*1024**2, compressed=True)
        raw = json.loads(raw_bytes)
        require(hashlib.sha256(raw_bytes).hexdigest() == report['supervision_sha256']
                and inputs.hashes['supervision.json.gz'] == report['supervision_gzip_sha256'], 'SUPERVISION_HASH')
        require(report['native_host_executed'] is True and manifest['native_executed'] is True
                and report['production_connected'] is False and manifest['third_party_execution'] is False, 'SCOPE')
        build_bytes = (LAB / report['build_report']).read_bytes()
        require(hashlib.sha256(build_bytes).hexdigest() == report['build_report_sha256'], 'BUILD_HASH')
        build = json.loads(build_bytes)
        require(build['binaries'][0]['sha256'] == report['expected_executable_sha256'], 'BINARY_IDENTITY')
        require(hashlib.sha256((LAB / build['binaries'][0]['path']).read_bytes()).hexdigest()
                == report['expected_executable_sha256'], 'RETAINED_EXECUTABLE_HASH')
        for relative, expected in report['collector_sha256'].items():
            require(hashlib.sha256(inputs.read('measurement-sources/' + relative)).hexdigest() == expected, 'MEASUREMENT_SOURCE')
        result.update(executable_sha256=report['expected_executable_sha256'], requested=report['requested'],
                      credential_backend=report['credential_backend'])
        host_trace = inputs.trace('lifecycle.jsonl')
        if build.get('network_lab'):
            def network_route():
                retained=inputs.json('network-analysis.json')
                netlog=inputs.read('netlog.json.gz', maximum=9*1024**2, compressed=True)
                require(retained==report['network_lab'], 'NETWORK_REPORT_BINDING')
                derived=inspect_netlog(netlog,retained['proxy_connections'],
                    retained['direct_target_connections'],retained['component_manifests'])
                require(derived['status']=='PASS' and all(derived[k]==retained[k] for k in
                    ('status','policy','netlog_sha256','events','owned_control_resolution_rejected',
                     'owned_control_errors','socket_attempts','proxy_connections','direct_target_connections',
                     'component_manifests')), 'NETWORK_ROUTE')
                require(report['owned_loopback_canary']['closed'] and
                    report['owned_loopback_canary']['accepted_connections']==retained['proxy_connections'], 'PROXY_CONTROL_COUNT')
                require(any(t['phase']=='network_probe_rejected' for t in host_trace), 'NATIVE_NETWORK_CONTROL')
                return derived
            gate('owned_network_lab_route',network_route)
        states, all_epochs, seen, browsers = manifest['instances'], [], set(), set()
        for state in states:
            identity = state['instance'], state['generation']
            require(identity not in seen and state['browser_id'] not in browsers, 'DUPLICATE_IDENTITY')
            seen.add(identity); browsers.add(state['browser_id'])
            require(state['origin'] == 'motive://i%d-g%d/' % identity, 'ORIGIN')
            state['_trace'] = []
            for epoch in state['epochs']:
                full_id = (*identity, epoch['epoch'])
                directory = 'instance-%d-g%d-e%d' % full_id
                trace = inputs.trace(directory + '/lifecycle.jsonl')
                require(all(tuple(t[k] for k in ('instance','generation','epoch')) == full_id for t in trace), 'TRACE_IDENTITY')
                state['_trace'] += trace
                frames = inputs.json(directory + '/frames.json')
                e = {'id': full_id, 'state': state, 'epoch': epoch, 'frames': frames, 'trace': trace}
                all_epochs.append(e)
                def check_epoch(e=e, directory=directory):
                    f, ep, identity = e['frames'], e['epoch'], e['id']
                    detail = conservation(f)
                    fixed_file_counters(f, ep['width'], ep['height'], required=True)
                    require(ep['accounting_observed'] and all(ep[k] == 0 for k in
                        ('pending_after_revoke','leased_after_join','retained_bytes_after_join')), 'RETIRED_BUFFERS')
                    require(e['state']['closed'] and e['state']['frames_written'], 'FINAL_CLOSE')
                    require(ep['started_ns'] <= ep['first_paint_ns'] < ep['ended_ns'], 'EPOCH_ORDER')
                    require(all(ep['started_ns'] <= r[1] <= ep['ended_ns'] for r in f['samples']), 'PAINT_OUTSIDE_EPOCH')
                    record = next(r for r in report['instances'] if tuple(r['identity']) == identity)
                    for label, retained in record['samples'].items():
                        meta = inputs.json(directory + '/' + label + '.json')
                        pixels = inputs.read(directory + '/' + label + '.bgra.gz', maximum=9*1024**2, compressed=True)
                        require(tuple(meta[k] for k in ('instance','generation','epoch')) == identity, 'PIXEL_IDENTITY')
                        require(meta['stride'] == ep['width']*4 and meta['width'] == ep['width'] and meta['height'] == ep['height']
                                and len(pixels) == meta['stride']*meta['height'], 'PIXEL_LAYOUT')
                        require(hashlib.sha256(pixels).hexdigest() == retained['raw_sha256']
                                and inputs.hashes[directory+'/'+label+'.bgra.gz'] == retained['gzip_sha256'], 'PIXEL_HASH')
                        require(any(a == 0 for a in pixels[3::4]), 'TRANSPARENCY')
                        require(all(max(pixels[i:i+3]) <= pixels[i+3]+1 for i in range(0,len(pixels),4)), 'PREMULTIPLIED_ALPHA')
                        if 'goal' not in build['profile'] and label == 'latest':
                            offset = (40*meta['width']+108)*4
                            require(tuple(pixels[offset:offset+4]) == (192,64,identity[0]*32,255), 'INSTANCE_PIXEL_MARKER')
                    return detail
                gate(directory, check_epoch)
                join_enter = [t['observed_ns'] for t in trace if t['phase']=='consumer_join_enter']
                metrics = {'identity': full_id, 'paints': frames['accounting_v2']['paints'],
                           'copied_bytes': frames['accounting_v2']['copied_bytes'],
                           'max_consumer_work_ms': max(r[3] for r in frames['samples'])/NS_MS}
                if join_enter:
                    metrics['join_ms'] = (phase(trace,'consumer_joined')-join_enter[0])/NS_MS
                    metrics['report_ms'] = (phase(trace,'frame_report_written')-phase(trace,'frame_report_enter'))/NS_MS
                result['epochs'].append(metrics)

        def native_close():
            require(raw['reason']=='exit' and raw['returncode']==0 and raw['final_cleanup_observed_tree']
                    and raw['final_remaining_observed_pids']==[], 'PROCESS_CLEANUP')
            require(raw['rss_budget']['limit_kib']==2048*1024 and raw['peak_tree_rss_kib']<=2048*1024, 'RSS_LIMIT')
            require(raw['sample_retention']['dropped_oldest']==0, 'RESOURCE_TRUNCATION')
            elapsed = (phase(host_trace,'shutdown_return')-phase(host_trace,'close_requested'))/NS_MS
            require(0 <= elapsed <= 5000 and raw['shutdown_ms'] <= 5000, 'CLOSE_DEADLINE')
            hosts={(p['pid'],tuple(p['birth']),p['proc_start_abstime']) for s in raw['samples']
                   for p in s['resource_usage']['processes'] if p['role']=='browser_host'}
            require(len(hosts)==1 and next(iter(hosts))[0]==manifest['host_pid'], 'SINGLE_HOST')
            for state in states:
                tr=state['_trace'];request=phase(tr,'close_requested');close=phase(tr,'before_close')
                require(request <= close <= state['closed_ns'] < phase(tr,'context_released'), 'NATIVE_CLOSE_ORDER')
                require(all(r[1] <= request for e in all_epochs if e['state'] is state for r in e['frames']['samples']), 'LATE_PAINT')
                expected_crash=any(t['phase']=='renderer_exit_requested' for t in tr)
                require(state['failed']==expected_crash, 'UNEXPECTED_FAILURE')
                if expected_crash:
                    require(state['renderer_decoded_exit_code']==86 and state['renderer_exit_code']==22016, 'CRASH_CODE')
            return {'close_to_shutdown_ms':elapsed,'supervisor_cleanup_ms':raw['shutdown_ms'],
                    'peak_rss_mib':raw['peak_tree_rss_kib']/1024,'host_identities':len(hosts)}
        gate('native_close_cleanup',native_close)

        def replacements():
            details=[]
            for old in states:
                if not any(t['phase']=='cold_replacement_requested' for t in old['_trace']):continue
                new=next(s for s in states if s['instance']==old['instance'] and s['generation']==old['generation']+1)
                a,b=old['_trace'],new['_trace']
                start=phase(a,'cold_replacement_requested');ready=new['epochs'][0]['first_paint_ns']
                require(start < phase(a,'before_close') < phase(a,'context_released') < phase(a,'cold_replacement_barrier_passed')
                        < phase(b,'create_requested') < phase(b,'after_created') <= ready, 'REPLACEMENT_BARRIERS')
                require(old['browser_id']!=new['browser_id'] and new['epochs'][0]['epoch']==1, 'COLD_IDENTITY')
                latency=(ready-start)/NS_MS
                details.append({'instance':old['instance'],'old_generation':old['generation'],
                                'new_generation':new['generation'],'first_paint_ms':latency,
                                'geometry':[old['width'],old['height'],new['width'],new['height']]})
                require(0<=latency<1000, 'REPLACEMENT_FIRST_PAINT_1000MS')
            require(details or not report['requested']['scenario'].startswith('cold-'),'NO_COLD_REPLACEMENTS')
            return {'replacements':details}
        gate('cold_replacement_barriers',replacements)

        # Stable peers must actually cover each operation, including both edges.
        for target in states:
            for event in target['_trace']:
                if event['phase'] not in ('cold_replacement_requested','restart_requested','remove_requested',
                                         'suspend_requested','renderer_exit_requested','hidden_begin','hidden_end','create_requested'):
                    continue
                if event['phase']=='create_requested' and event['observed_ns']-phase(host_trace,'initialize_enter')<1000*NS_MS:
                    continue
                start=event['observed_ns'];end=start+1000*NS_MS
                successor=next((s for s in states if s['instance']==target['instance'] and s['generation']==target['generation']+1),None)
                if successor and event['phase'] in ('cold_replacement_requested','restart_requested','suspend_requested','renderer_exit_requested'):
                    end=max(end,successor['epochs'][0]['first_paint_ns']+500*NS_MS)
                start-=100*NS_MS
                op={'instance':target['instance'],'generation':target['generation'],'phase':event['phase'],
                    'start_ns':start,'end_ns':end,'peers':[]}
                for peer in states:
                    if peer['instance']==target['instance']:continue
                    times=[r[1] for e in all_epochs if e['state'] is peer for r in e['frames']['samples']]
                    if not times or times[0]>start or times[-1]<end:continue
                    hidden=False;visible=True
                    for t in peer['_trace']:
                        if t['phase'] in ('hidden_begin','hidden_end'):
                            if start<=t['observed_ns']<=end:hidden=True
                            if t['observed_ns']<start:visible=t['phase']=='hidden_end'
                    if hidden or not visible:continue
                    f=[r for e in all_epochs if e['state'] is peer for r in e['frames']['samples']]
                    try:
                        op['peers'].append({'instance':peer['instance'],'generation':peer['generation'],
                            'paint':gaps([r[1] for r in f],start,end),'acquisition':gaps([r[2] for r in f],start,end),
                            'completion':gaps([r[2]+r[3] for r in f],start,end)})
                    except ValueError as exc:
                        op['peers'].append({'instance':peer['instance'],'error':str(exc),'status':'FAIL'})
                result['operations'].append(op)
        if report['requested']['scenario'].startswith('cold-'):
            def peers():
                require(result['operations'],'NO_OPERATIONS')
                require(all(o['peers'] for o in result['operations']),'NO_ACTIVE_PEER')
                require(all('error' not in p and all(p[k]['status']=='PASS' for k in ('paint','acquisition','completion'))
                    for o in result['operations'] for p in o['peers']),'PEER_GAP_250MS')
                return {'checked_operations':len(result['operations']),'limit_exclusive_ms':250}
            gate('peer_continuity',peers)
        beats=[r['observed_ns'] for r in host_trace if r['phase']=='ui_heartbeat']
        result['ui_heartbeat']={'samples':len(beats),'maximum_interval_ms':max((b-a for a,b in zip(beats,beats[1:])),default=0)/NS_MS}
        rows,summary=reconstruct_resources(raw)
        result['resources']={'totals':summary,'windows':[]}
        duration=report['requested']['duration_ms']
        for start,end in ([(10000,70000)] if duration<600000 else [(30000,90000),(120000,180000),(240000,300000),(360000,420000),(480000,540000),(540000,590000)]):
            if duration>=end:result['resources']['windows'].append(resource_window(rows,start,end))
        # Quantify all stable intervals; do not infer motion from cadence alone.
        result['steady_frames']=[]
        intermittent=build.get('controlled_widget_fixtures') or 'goal' in build['profile']
        for e in all_epochs:
            ep=e['epoch']
            continuously_animated=(not intermittent and report['requested']['scenario']!='static'
                and (report['requested']['scenario']!='mixed' or e['id'][0]==1))
            if continuously_animated and ep['ended_ns']-ep['started_ns']>=70000*NS_MS:
                for lo,hi in [(10,70),*([(540,590)] if ep['ended_ns']-ep['started_ns']>=590000*NS_MS else [])]:
                    start=ep['started_ns']+lo*10**9;end=ep['started_ns']+hi*10**9
                    if any(start<=t['observed_ns']<=end and t['phase'] in ('hidden_begin','hidden_end') for t in e['trace']):continue
                    interval=native_interval(e['frames']['samples'],ep['started_ns']+lo*10**9,ep['started_ns']+hi*10**9,report['requested']['fps'])
                    samples=e['frames']['samples']
                    interval['continuity']={'paint':gaps([r[1] for r in samples],start,end),
                        'acquisition':gaps([r[2] for r in samples],start,end),
                        'completion':gaps([r[2]+r[3] for r in samples],start,end)}
                    if any(x['status']=='FAIL' for x in interval['continuity'].values()):interval['status']='FAIL'
                    result['steady_frames'].append({'identity':e['id'],'interval':interval})
        result['steady_frame_performance']={'status':('PASS' if all(r['interval']['status']=='PASS' for r in result['steady_frames']) else 'FAIL') if result['steady_frames'] else 'NOT_EVALUATED',
            'scope':'continuous-motion native acquisition windows; intermittent animations evaluated separately'}
        result['status']='PASS' if all(g['status']=='PASS' for g in result['gates'].values()) else 'FAIL'
        result['functional_status']='PASS' if all(g['status']=='PASS' for name,g in result['gates'].items() if name!='peer_continuity') else 'FAIL'
        result['performance_status']=result['steady_frame_performance']['status']
        if result['gates'].get('peer_continuity',{}).get('status')=='FAIL':result['performance_status']='FAIL'
        if report.get('memory_profile_diagnostic'):
            result['performance_status']='NOT_EVALUATED'
            result['diagnostic_note']='vmmap/heap may suspend targets; cadence data retained but not performance acceptance'
        if result['performance_status']=='FAIL':result['status']='FAIL'
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:
        result['audit_error']=str(exc)[:512]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.root)
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'status':r['status'],'gates':r['gates'],'audit_error':r.get('audit_error')},indent=2))
    return r['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
