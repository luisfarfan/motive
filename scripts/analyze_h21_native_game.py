#!/usr/bin/env python3
"""Decode both actual game outputs; measure cadence, sustained freezes and audio.

A 0.5 s freeze candidate uses FFmpeg's 0.003 image-difference threshold on
160x90 luma. Candidates overlapping planned scene cuts are reported separately.
This is not calibrated game A/V, physical microphone acceptance or unique 60 FPS.
"""
import argparse,array,collections,json,math,re,shutil,subprocess
from pathlib import Path
from verify_h14_collection import digest,lock,require,save
from h21_session_metrics import summarize,distribution


def capture_observations(run, samples_path):
    """Summarize native arrival and sampled availability, not unique images."""
    capture_mode = run.get('capture_mode', 'window')
    require(capture_mode in ('window', 'application'), 'Unknown game capture mode')
    first = next(s for s in run['initial_state']['sources'] if s['kind'] == capture_mode)
    last = next(s for s in run['last_state']['sources'] if s['id'] == first['id'])
    require(first['instance_id'] == last['instance_id'], 'Capture instance changed')
    delivery = collections.Counter(); status = collections.Counter(); elapsed = []
    input_clipping = {}; issues = 0; max_query_seconds = 0
    identity_reasons = collections.Counter(); identity_probes = collections.Counter()
    catalog_absence = {}; identity_unverified = 0
    video_identity_health = collections.Counter(); video_catalog_absence = 0
    with samples_path.open() as samples:
        for line in samples:
            row = json.loads(line); state = row['state']; elapsed.append(row['elapsed_s'])
            source = next(s for s in state['sources'] if s['id'] == first['id'])
            require(source['instance_id'] == first['instance_id'], 'Capture instance changed between endpoints')
            if capture_mode == 'window':
                identity = source['window_identity']
                require(identity['found'] and identity['observed_pid'] == run['game_pid'], 'Game window identity lost')
            else:
                identity = source['application_identity']
                require(identity['expected_pid'] == run['game_pid'] and identity['health'] == 'matches'
                        and identity['process_probe'] == 'observed' and identity['process_generation_matches']
                        and identity['process_executable_matches'], 'Game application identity lost or unobserved')
                video_identity_health[identity['health']] += 1
                video_catalog_absence = max(video_catalog_absence, identity['catalog_absence_observations'])
            delivery[source['capture_delivery']] += 1
            status[source['capture_diagnostics']['sample_status']] += 1
            max_query_seconds = max(max_query_seconds, row['host_bracket_s'][1] - row['host_bracket_s'][0])
            issues += bool(state['audio_mixer']['issues'])
            for channel in state['audio_mixer']['runtime']['inputs']:
                input_clipping[channel['id']] = max(input_clipping.get(channel['id'], 0), channel['levels']['clipped_blocks'])
                identity = channel.get('application_identity')
                if identity:
                    identity_reasons[identity['reason']] += 1
                    identity_probes[identity.get('process_probe') or 'not_in_this_binary'] += 1
                    catalog_absence[channel['id']] = max(catalog_absence.get(channel['id'], 0),
                                                        identity.get('catalog_absence_observations', 0))
                    if identity.get('process_probe'):
                        identity_unverified += not (identity['process_probe'] == 'observed'
                            and identity['process_generation_matches'] and identity['process_executable_matches'])
    require(len(elapsed) >= 2, 'Insufficient capture observations')
    gaps = [b-a for a,b in zip(elapsed,elapsed[1:])]
    require(min(gaps) > 0, 'Sample clock did not advance')
    a = first['capture_diagnostics']; b = last['capture_diagnostics']
    return {'scope': 'Native frame arrivals and one-second control observations. Not unique pixels/FPS or continuous health between queries.',
            'samples_sha256': digest(samples_path), 'observations': len(elapsed), 'capture_mode':capture_mode,
            'application_video_identity': {'sampled_health':dict(video_identity_health),
                'catalog_absence_observations_max':video_catalog_absence} if capture_mode == 'application' else None,
            'sample_interval_seconds': distribution(gaps), 'max_control_query_seconds': max_query_seconds,
            'observed_span_seconds': elapsed[-1]-elapsed[0], 'effective_window_size': [last['width'], last['height']],
            'native_frame_arrival_delta': last['frames']-first['frames'],
            'sck_counters_delta': {k:b[k]-a[k] for k in ('callbacks','surface_samples','consumed_surface_samples','errors','invalid_samples','pts_regressions','status_changes')},
            'sck_status_counts_delta': {k:b['status_counts'][k]-a['status_counts'][k] for k in a['status_counts']},
            'sampled_delivery_counts': dict(delivery), 'sampled_status_counts': dict(status),
            'audio_issue_observations': issues, 'input_clipped_blocks_max': input_clipping,
            'application_identity': {'sampled_reasons':dict(identity_reasons),
                'sampled_process_probes':dict(identity_probes),
                'catalog_absence_observations_max':catalog_absence,
                'sampled_unverified_process_identities':identity_unverified,
                'scope':'Catalog counter includes native polls between samples. Legacy binaries lack OS identity observations.'},
            'fallback_attempts': run['last_state']['capture_recovery']['attempt_count']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inspect-failed-session',action='store_true',help='Decode retained failed-run media; overall result remains FAIL')
    a=p.parse_args();lock();source=a.report.resolve(strict=True);run=json.loads(source.read_text())
    out=a.output.absolute();out.mkdir(exist_ok=False);app=a.app.resolve(strict=True)
    shutil.copy2(__file__,out/Path(__file__).name)
    ff=str(app/'Contents/MacOS/ffmpeg');fp=str(app/'Contents/MacOS/ffprobe')
    result={'status':'FAIL','source_sha256':digest(source),'source_report':str(source),'analyzer_sha256':digest(Path(__file__)),
            'media':[],'resources':summarize(run),'physical_av':'NOT_MEASURED','game_av':'NOT_CALIBRATED','personal_ready':False,
            'runtime_status':run.get('runtime_status'),'runtime_error':run.get('error'),
            'scope':__doc__,'game_resources':{k:distribution([r[k] for r in run['game_resources']]) for k in ['cpu_percent','rss_kib']}}
    try:
        require((run.get('runtime_status')=='PASS' or a.inspect_failed_session) and not run['cleanup_errors'],'Runtime did not pass')
        coverage=run.get('observed_seconds',run.get('last_elapsed_s',0))
        require(coverage>20,'Insufficient observed duration')
        require(a.inspect_failed_session or coverage>=run['requested_seconds'],'Requested duration not observed')
        require(len(run['media'])==2 and {m['target'] for m in run['media']}=={'recording','streaming'},'Both distinct outputs required')
        result['coverage_seconds']=coverage
        require(digest(app/'Contents/MacOS/motive')==run['owner_sha256'],'Binary changed')
        result['capture_observations'] = capture_observations(run, source.parent/'samples.jsonl')
        require(not any(result['capture_observations']['input_clipped_blocks_max'].values()), 'Input clipping observed')
        for key in ['owner_pid','game_pid']:
            q=subprocess.run(['ps','-p',str(run[key]),'-o','pid='],capture_output=True,text=True)
            require(q.returncode==1 and not q.stdout.strip(),'Owned process remains')
        for medium in run['media']:
            path=Path(medium['path']);target=medium['target'];row={**medium,'sha256':digest(path),'failures':[]};result['media'].append(row)
            q=subprocess.run([fp,'-v','error','-show_streams','-show_packets','-show_entries',
                'stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:packet=codec_type,pts_time','-of','json',str(path)],capture_output=True,timeout=300)
            require(q.returncode==0 and not q.stderr,'Probe failed');probe=json.loads(q.stdout);save(out/(target+'-probe.json'),probe)
            v=next(s for s in probe['streams'] if s['codec_type']=='video');au=next(s for s in probe['streams'] if s['codec_type']=='audio')
            require((v['codec_name'],v['width'],v['height'],v['avg_frame_rate'])==('h264',1920,1080,'60/1'),'Video format')
            require((au['codec_name'],au['sample_rate'],au['channels'])==('aac','48000',2),'Audio format')
            row['cadence']={}
            for kind,bound in [('video',1/60+.0011),('audio',.023)]:
                pts=[float(x['pts_time']) for x in probe['packets'] if x['codec_type']==kind];gaps=[b-a for a,b in zip(pts,pts[1:])]
                row['cadence'][kind]={'first_pts_s':pts[0],'last_pts_s':pts[-1],'max_gap_s':max(gaps),'packets':len(pts)}
                if not (min(gaps)>0 and max(gaps)<=bound):row['failures'].append('Packet cadence failed: '+kind)
            log_path=out/(target+'-video.log')
            with log_path.open('x') as log:
                q=subprocess.run([ff,'-nostdin','-v','info','-xerror','-threads','2','-copyts','-i',str(path),'-an',
                    '-vf','scale=160:90,format=gray,freezedetect=n=0.003:d=0.5','-fps_mode','passthrough','-progress','pipe:1','-f','null','-'],stdout=subprocess.PIPE,stderr=log,timeout=1200)
            require(q.returncode==0,'Full video decode failed')
            row['decoded_frames']=int(re.findall(rb'frame=(\d+)',q.stdout)[-1])
            if row['decoded_frames']<coverage*59:row['failures'].append('Observed duration not covered')
            text=log_path.read_text();freezes=[];begin=None
            for line in text.splitlines():
                start=re.search(r'freeze_start: ([\d.e+-]+)',line);end=re.search(r'freeze_end: ([\d.e+-]+)',line)
                if start:begin=float(start[1])
                if end and begin is not None:freezes.append([begin,float(end[1])]);begin=None
            if begin is not None:freezes.append([begin,row['cadence']['video']['last_pts_s']])
            # Container origin bound from initial native video PTS and sys_dts.
            first=next(x for x in run['initial_traces'][target]['packet_trace']['packets'] if x['media_type']=='video')
            origin=row['cadence']['video']['first_pts_s']-first['sys_dts_usec']/1e6
            planned=[];begin=None
            for event in run['events']:
                if event['name']=='planned_safe_scene':begin=event['host_monotonic']+origin
                elif event['name']=='return_game' and begin is not None:planned.append([begin-.5,event['host_monotonic']+origin+.5]);begin=None
            if run.get('runtime_status')=='PASS':
                planned.append([run['started_monotonic']+coverage+origin-.5, row['cadence']['video']['last_pts_s']+1])
            row['freeze_candidates_s']=freezes;row['planned_safe_intervals_s']=planned
            row['unexplained_freezes_s']=[f for f in freezes if not any(lo<=f[0] and f[1]<=hi for lo,hi in planned)]
            audio_log=out/(target+'-audio.log');peak=0;count=0;rms=[]
            with audio_log.open('x') as log:
                process=subprocess.Popen([ff,'-nostdin','-v','error','-xerror','-threads','2','-i',str(path),'-vn','-ac','1','-ar','48000','-f','f32le','-'],stdout=subprocess.PIPE,stderr=log)
                try:
                    while True:
                        raw=process.stdout.read(48000*4)
                        if not raw:break
                        samples=array.array('f',raw);count+=len(samples);peak=max(peak,max(map(abs,samples)))
                        rms.append(math.sqrt(sum(v*v for v in samples)/len(samples)))
                    require(process.wait(timeout=30)==0,'Full audio decode failed')
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
            row.update(decoded_audio_samples=count,pcm_peak=peak,rms_per_second=rms)
            if not (count>=coverage*48000 and peak<.999 and max(rms)>.0001):
                row['failures'].append('Audio coverage/energy/clipping')
            row['silent_seconds_below_minus80dbfs']=[i for i,x in enumerate(rms) if x<.0001]
            row['audio_scope']='Game application only when no physical microphone requested. Silence is reported; not all sounds must be continuous.'
            row['status']='FAIL' if row['failures'] else 'PARTIAL' if row['unexplained_freezes_s'] else 'PASS'
            for index,t in enumerate([15,coverage/2,max(0,coverage-10)]):
                subprocess.run([ff,'-nostdin','-v','error','-threads','2','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=960:540',str(out/(target+'-sample-'+str(index)+'.png'))],check=True,timeout=60)
        result['media_analysis_status']=('FAIL' if any(m['status']=='FAIL' for m in result['media'])
                                         else 'PASS' if all(m['status']=='PASS' for m in result['media']) else 'PARTIAL')
        result['status']=result['media_analysis_status'] if run.get('runtime_status')=='PASS' else 'FAIL'
    except Exception as e:result['error']=repr(e)
    result['source_unchanged']=digest(source)==result['source_sha256']
    if not result['source_unchanged']:result['status']='FAIL'
    save(out/'analysis.json',result)
    print(json.dumps({'status':result['status'],'error':result.get('error')}));return int(result['status']=='FAIL')


if __name__=='__main__':raise SystemExit(main())
