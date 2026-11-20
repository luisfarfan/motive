#!/usr/bin/env python3
"""Owned native AppKit fullscreen entry/exit through real SCK and dual outputs.

Run through h15_run_owned. Never selects Display, a personal app, camera or mic.
Minimization is observed separately; decoded progress is required after restore.
"""
import argparse
import json
from pathlib import Path
import socket
import shutil
import subprocess
import time

from h7_support import Client
from verify_h14_collection import ROOT, Receiver, default_owner, digest, lines, lock, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('window',), required=True)
    args = parser.parse_args(); owner_lock = lock()
    app=args.app.resolve(strict=True); out=args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    binary=ROOT/'target/H21CaptureFixtureV5.app/Contents/MacOS/MotiveH21CaptureFixture'
    report={'status':'FAIL', 'mode':args.mode, 'lock':owner_lock, 'owner_sha256':digest(app/'Contents/MacOS/motive'),
            'native_fullscreen':True, 'fixture_sha256':digest(binary), 'samples':[], 'phases':[], 'snapshots':[], 'media':[], 'cleanup_errors':[],
            'limits':['Owned 10 Hz content, not a game or a 60 Hz capture freshness claim.',
                      'No Display, manual Space switch, Stage Manager, permission revocation, physical devices or long soak.',
                      'Internal tone checks continuity, not audiovisual alignment.']}
    client=fixture=receiver=None; attempts={}; capture_scene=safe=None
    def checkpoint(): save(out/'report.json',report)
    def sample(label):
        before=time.monotonic(); state=client.state(); after=time.monotonic()
        report['samples'].append({'phase':label,'host_bracket_s':[before,after], 'state':state})
        return state
    def wait(predicate,label,timeout=15):
        deadline=time.monotonic()+timeout
        while True:
            state=sample(label)
            if predicate(state): return state
            require(time.monotonic()<deadline,label+' timeout'); time.sleep(.2)
    def phase(label,seconds,command=None,allow_fallback=False):
        start=time.monotonic()
        if command:
            fixture.stdin.write(command+'\n'); fixture.stdin.flush()
        while time.monotonic()-start<seconds:
            state=sample(label)
            require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a
                        for t,a in attempts.items()), 'Output continuity lost: '+label)
            require(state['project']['graph']['active_scene'] in
                    ([capture_scene,safe] if allow_fallback else [capture_scene]), 'Unexpected safe fallback: '+label)
            time.sleep(.25)
        for index in range(2):
            before=time.monotonic(); client.call('snapshot'); after=time.monotonic()
            path=out/(label+'-'+str(index)+'.png')
            shutil.copy2(Path.home()/'Library/Logs/Motive/preview.png',path)
            report['snapshots'].append({'phase':label,'path':str(path),'host_bracket_s':[before,after],
                                        'sha256':digest(path)})
            if index==0: time.sleep(1.2)
        report['phases'].append({'name':label,'start':start,'end':time.monotonic(),'command':command}); checkpoint()
    with (out/'fixture.jsonl').open('x') as log, (out/'fixture.stderr').open('x') as errors:
        try:
            client=Client(); default_owner(client.state()); report['owner_pid']=client.state()['pid']
            fixture=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=log,stderr=errors,text=True)
            report['fixture_pid']=fixture.pid; deadline=time.monotonic()+10
            while True:
                rows=lines(out/'fixture.jsonl')
                ready=next((r for r in rows if len(r.get('windows',[]))==2 and
                    all(isinstance(w.get('bounds'),dict) and w['bounds']['Width']>0
                        and w['bounds']['Height']>0 for w in r['windows'])),None)
                if ready: break
                require(fixture.poll() is None and time.monotonic()<deadline,'Fixture startup failed'); time.sleep(.1)
            require(ready['pid']==fixture.pid and len(ready['windows'])==2,'Wrong owned fixture')
            devices=client.call('devices')['devices']
            windows=ready['windows']; b=windows[0]['bounds']; x=b['X']+b['Width']/2; y=b['Y']+b['Height']/2
            displays=[d for d in devices['displays'] if d['bounds']['x']<=x<d['bounds']['x']+d['bounds']['width']
                      and d['bounds']['y']<=y<d['bounds']['y']+d['bounds']['height']]
            require(len(displays)==1,'Own display identity ambiguous')
            d=displays[0]['bounds']
            require(all(w['bounds'] and d['x']<=w['bounds']['X'] and d['y']<=w['bounds']['Y']
                        and w['bounds']['X']+w['bounds']['Width']<=d['x']+d['width']
                        and w['bounds']['Y']+w['bounds']['Height']<=d['y']+d['height'] for w in windows),
                    'Both owned windows must be wholly on the selected display')
            if args.mode=='application':
                source={'kind':'application','bundle_id':'local.motive.h21capturefixture','display_uuid':displays[0]['display_uuid']}
            else: source={'kind':'window','window_id':windows[0]['window_id']}
            report['source']=source; report['ready']=ready
            fps=60 if args.mode=='application' else 30
            client.call('configure_video',video={'version':1,'resolution':'full_hd1080','fps':fps,'coordinate_space':'design960'})
            client.call('set_overlay',visible=False); safe=client.state()['project']['graph']['active_scene']
            client.call('configure_capture_fallback',scene_id=safe)
            state=client.call('create_scene',name='H21 owned capture')['state']; capture_scene=state['project']['graph']['active_scene']
            state=client.call('add_source',scene_id=capture_scene,name='H21 two-window fixture',source=source)['state']
            source_id=next(s['id'] for s in state['project']['graph']['sources'] if s['name']=='H21 two-window fixture')
            report.update(source_id=source_id,capture_scene=capture_scene,safe_scene=safe,fps=fps)
            state=client.call('add_audio_input',name='H21 tone',source={'kind':'tone'})['state']
            tone=next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']=='H21 tone')
            client.call('set_audio_gain',input_id=tone,gain_db=-12)
            profile={'id':'h21-lifecycle','encoder':'videotoolbox','bitrate_kbps':6000,'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':False}
            client.call('upsert_output_profile',profile=profile)
            for target in ('recording','streaming'): client.call('select_output_profile',target=target,profile_id=profile['id'])
            with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
            client.call('configure_stream',endpoint={'transport':'rtmp','port':port})
            # Fixed bounded readiness polling; no reconnect or retry of a failed source.
            deadline=time.monotonic()+15
            while True:
                raw=subprocess.run([str(app/'Contents/MacOS/motive'),'ctl',json.dumps({'op':'preflight_output','target':'recording'})],capture_output=True,text=True,timeout=10)
                preflight=json.loads(raw.stdout)
                if preflight.get('ok'): break
                require(time.monotonic()<deadline,'Preflight failed: '+str(preflight.get('error'))); time.sleep(.25)
            receiver=Receiver(str(app/'Contents/MacOS/ffmpeg'),out,port)
            for target in ('recording','streaming'):
                report[target+'_start_bracket']=[time.monotonic()]
                state=client.call('start_output',target=target)['state']; slot=state['outputs'][target]
                report[target+'_start_bracket'].append(time.monotonic()); attempts[target]=slot['attempt_id']
                report['media'].append({'target':target,'path':str(receiver.path) if target=='streaming' else slot['path']})
            wait(lambda s:all(s['outputs'][t]['phase']=='active' for t in attempts),'outputs_active')
            report['resources_before']=client.state()['transition']['source_instances_created']
            report['source_instances_before']={s['id']:s['instance_id'] for s in client.state()['sources']}
            report['mixer_before']=client.state()['audio_mixer']
            phase('both_visible',6,'focus 0'); phase('focus_second',4,'focus 1')
            phase('resized',5,'resize 0')
            report['fullscreen_observations']=[]
            for enabled,label in [(True,'fullscreen'),(False,'restored')]:
                requested=time.monotonic();fixture.stdin.write('fullscreen 0\n');fixture.stdin.flush()
                deadline=time.monotonic()+20
                while True:
                    metadata=lines(out/'fixture.jsonl')
                    observed=metadata[-1] if metadata else {}
                    if observed.get('windows') and observed['windows'][0].get('native_fullscreen') in (0,1) and observed['windows'][0]['native_fullscreen']==enabled:break
                    require(fixture.poll() is None and time.monotonic()<deadline,'Native fullscreen transition not observed')
                    time.sleep(.2)
                report['fullscreen_observations'].append({'requested_host_s':requested,'enabled':enabled,'fixture':observed})
                wait(lambda s:any(x['id']==source_id and x.get('capture_diagnostics',{}).get('sample_status')=='complete'
                                  and x['capture_diagnostics'].get('surface_age_ms',1e9)<500 for x in s['sources']),
                     label+'_surface',20)
                if client.state()['project']['graph']['active_scene']==safe:
                    recovered=sample(label+'_healthy_off_program')
                    recovery=recovered['capture_recovery']
                    require(recovery.get('fallback_attempted') and not recovery.get('fallback_armed'),
                            'Health polling alone rearmed the fallback')
                    client.call('select_scene',scene_id=capture_scene)
                    returned=wait(lambda s:s['project']['graph']['active_scene']==capture_scene and s['transition']['phase']=='completed','explicit_return')
                    require(returned['capture_recovery'].get('fallback_armed') and
                            returned['capture_recovery'].get('attempt_count')==recovery.get('attempt_count'),
                            'Explicit healthy return did not renew exactly one opportunity')
                phase(label,8)
            state=sample('repeated_fallback_verified')
            require(state['capture_recovery'].get('attempt_count',0)>=2,
                    'Two confirmed failures and fallback attempts were not observed')
            report['fallback_attempt_count']=state['capture_recovery']['attempt_count']
            require({s['id']:s['instance_id'] for s in state['sources']}==report['source_instances_before'],
                    'Native source identities changed')
            require(state['audio_mixer']['store']==report['mixer_before']['store'],'Audio mixer changed')
            before_mixer=report['mixer_before']['runtime']; after_mixer=state['audio_mixer']['runtime']
            require(before_mixer['instances_created']==after_mixer['instances_created'] and
                    {i['id']:i['instance_id'] for i in before_mixer['inputs']}==
                    {i['id']:i['instance_id'] for i in after_mixer['inputs']},'Audio input recreated')
            client.call('select_scene',scene_id=safe)
            state=wait(lambda s:s['project']['graph']['active_scene']==safe and s['transition']['phase']=='completed','safe_scene')
            require(state['transition']['source_instances_created']==report['resources_before'],'Unexpected source reconstruction')
            report['safe_observed']=time.monotonic()
            end=time.monotonic()+4
            while time.monotonic()<end:
                state=sample('safe_continuity')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()),'Fallback interrupted output')
                time.sleep(.25)
            client.call('stop_output_target',target='streaming'); wait(lambda s:not s['outputs']['streaming']['native_busy'],'stream_stop')
            require(client.state()['outputs']['recording']['phase']=='active','Independent stop failed')
            client.call('stop_output_target',target='recording'); wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'quiescent')
            report['runtime_status']='PASS'; report['status']='PARTIAL'
        except Exception as error: report['error']=repr(error)
        finally:
            if client:
                try:
                    state=client.state()
                    for target,attempt in attempts.items():
                        require(state['outputs'][target]['attempt_id']==attempt,'Output ownership changed')
                        if state['outputs'][target]['native_busy']: client.call('stop_output_target',target=target)
                    wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'cleanup_quiescent',25)
                except Exception as error: report['cleanup_errors'].append(repr(error))
                client.close()
            if fixture and fixture.poll() is None:
                fixture.stdin.write('quit\n'); fixture.stdin.flush(); fixture.wait(timeout=8)
            if receiver: report['receiver_exit']=receiver.close()
            report['fixture_exit']=fixture.poll() if fixture else None
            checkpoint()
    # Media analysis is separate, after the wrapper has shut the native owner down.
    print(json.dumps({'output':str(out),'status':report['status'],'error':report.get('error')}))
    return int(report.get('runtime_status')!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__': raise SystemExit(main())
