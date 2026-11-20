#!/usr/bin/env python3
"""Two owned windows through real SCK, dual outputs and bounded safe fallback.

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
    parser.add_argument('--mode', choices=('window', 'application'), required=True)
    args = parser.parse_args(); owner_lock = lock()
    app=args.app.resolve(strict=True); out=args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    binary=ROOT/'target/H21CaptureFixture.app/Contents/MacOS/MotiveH21CaptureFixture'
    report={'status':'FAIL', 'mode':args.mode, 'lock':owner_lock, 'owner_sha256':digest(app/'Contents/MacOS/motive'),
            'fixture_sha256':digest(binary), 'samples':[], 'phases':[], 'snapshots':[], 'media':[], 'cleanup_errors':[],
            'limits':['Owned 10 Hz content, not a game or a 60 Hz capture freshness claim.',
                      'No Display, Spaces, Stage Manager, fullscreen, permission revocation, physical devices or long soak.',
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
            phase('both_visible',6,'focus 0'); phase('focus_second',4,'focus 1')
            phase('resized',5,'resize 0')
            phase('minimized',5,'minimize 0',allow_fallback=args.mode=='window')
            if args.mode=='window':
                state=client.state()
                require(state['project']['graph']['active_scene']==safe and state['capture_recovery']['fallback_attempted'],
                        'Configured safe fallback on suspension not observed')
                fixture.stdin.write('restore 0\n'); fixture.stdin.flush()
                wait(lambda s:any(x['id']==source_id and x.get('capture_diagnostics',{}).get('sample_status')=='complete'
                                  and x['capture_diagnostics'].get('surface_age_ms',1e9)<500 for x in s['sources']),
                     'restored_surface',15)
                # Explicit return to an existing healthy capture is not SCK reconstruction.
                client.call('select_scene',scene_id=capture_scene)
                wait(lambda s:s['project']['graph']['active_scene']==capture_scene and s['transition']['phase']=='completed','explicit_return')
                phase('restored',6)
                report['suspension_policy']='Configured safe scene, then explicit Cut after new SCK surfaces; no source recreation.'
            else: phase('restored',6,'restore 0')
            if args.mode=='application': phase('first_window_closed',6,'close 0')
            if args.mode=='application':
                report['loss_requested']=time.monotonic(); fixture.stdin.write('quit\n'); fixture.stdin.flush()
                fixture.wait(timeout=8)
            else:
                # This output session already spent its one automatic fallback.
                # Closing the window again would test budget exhaustion, not first-loss recovery.
                client.call('select_scene',scene_id=safe)
            state=wait(lambda s:s['project']['graph']['active_scene']==safe and s['transition']['phase']=='completed','safe_scene')
            require(state['capture_recovery']['fallback_attempted'],'Fallback not observed')
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
