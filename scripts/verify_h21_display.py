#!/usr/bin/env python3
"""Explicitly authorized Display capture, covered by an owned native surface.

Run through h15_run_owned under the canonical lock. The cover stays until outputs
are quiescent and the display source is removed. No display mode or global
preference is changed. A flag records consent; it cannot grant user consent.
"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time

from h7_support import Client
from verify_h14_collection import ROOT, Receiver, default_owner, digest, lines, lock, require, save


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--display-uuid',required=True)
    parser.add_argument('--authorized-controlled-display',action='store_true',required=True)
    args=parser.parse_args(); owner_lock=lock()
    app=args.app.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    fixture_binary=ROOT/'target/H21CaptureFixtureV2.app/Contents/MacOS/MotiveH21CaptureFixture'
    report={'status':'FAIL','mode':'display','fps':60,'lock':owner_lock,
            'owner_sha256':digest(app/'Contents/MacOS/motive'),'fixture_sha256':digest(fixture_binary),
            'samples':[],'memory':[],'snapshots':[],'phases':[],'media':[],'cleanup_errors':[],
            'authorization':'User authorized the controlled Display trial (60 seconds, local MKV and loopback RTMP) and granted freedom to choose available test content/devices. Exact target is recorded below.',
            'limits':['Controlled 10 Hz native surface; not a game or a one-hour session.',
                      'Internal tone does not measure physical audiovisual sync.']}
    client=fixture=receiver=None;source_id=scene=safe=None;attempts={}
    shutil.copy2(Path(__file__),out/'runner-source.py')
    shutil.copy2(ROOT/'scripts/fixtures/h21_capture_app.m',out/'fixture-source.m')
    def checkpoint():save(out/'report.json',report)
    def sample(label):
        before=time.monotonic();s=client.state()
        report['samples'].append({'phase':label,'host_bracket_s':[before,time.monotonic()],'state':s})
        return s
    def wait(predicate,label,seconds=15):
        deadline=time.monotonic()+seconds
        while True:
            state=sample(label)
            if predicate(state):return state
            require(time.monotonic()<deadline,label+' timeout');time.sleep(.2)
    def snapshot(label):
        before=time.monotonic();client.call('snapshot');after=time.monotonic()
        path=out/(label+'.png');shutil.copy2(Path.home()/'Library/Logs/Motive/preview.png',path)
        report['snapshots'].append({'phase':'controlled_display','path':str(path),
            'host_bracket_s':[before,after],'sha256':digest(path)})
    with (out/'fixture.jsonl').open('x') as log,(out/'fixture.stderr').open('x') as err:
        try:
            client=Client();default_owner(client.state());report['owner_pid']=client.state()['pid']
            devices=client.call('devices')['devices'];save(out/'devices-private.json',devices)
            display=[d for d in devices['displays'] if d['display_uuid']==args.display_uuid]
            require(len(display)==1,'Exact authorized display unavailable');report['display']=display[0]
            fixture=subprocess.Popen([str(fixture_binary)],stdin=subprocess.PIPE,stdout=log,stderr=err,text=True)
            report['fixture_pid']=fixture.pid
            deadline=time.monotonic()+10
            while not any(r.get('reason')=='ready' for r in lines(out/'fixture.jsonl')):
                require(fixture.poll() is None and time.monotonic()<deadline,'Fixture startup failed');time.sleep(.1)
            fixture.stdin.write('cover 0\n');fixture.stdin.flush()
            while True:
                rows=lines(out/'fixture.jsonl'); latest=rows[-1] if rows else {}
                bounds=latest.get('windows',[{}])[0].get('bounds');d=display[0]['bounds']
                if bounds and all(abs(bounds[a]-d[b])<1 for a,b in [('X','x'),('Y','y'),('Width','width'),('Height','height')]):break
                require(fixture.poll() is None and time.monotonic()<deadline,'Own surface does not cover authorized display');time.sleep(.1)
            report['cover_observed']=latest
            client.call('configure_video',video={'version':1,'resolution':'full_hd1080','fps':60,'coordinate_space':'design960'})
            client.call('set_overlay',visible=False);safe=client.state()['project']['graph']['active_scene']
            client.call('configure_capture_fallback',scene_id=safe)
            scene=client.call('create_scene',name='H21 authorized controlled Display')['state']['project']['graph']['active_scene']
            source={'kind':'display','display_uuid':args.display_uuid};report['source']=source
            state=client.call('add_source',scene_id=scene,name='H21 controlled Display',source=source)['state']
            source_id=next(s['id'] for s in state['project']['graph']['sources'] if s['name']=='H21 controlled Display')
            state=client.call('add_audio_input',name='H21 Display tone',source={'kind':'tone'})['state']
            tone=next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']=='H21 Display tone')
            client.call('set_audio_gain',input_id=tone,gain_db=-12)
            profile={'id':'h21-display','encoder':'videotoolbox','bitrate_kbps':6000,'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':False}
            client.call('upsert_output_profile',profile=profile)
            for target in ('recording','streaming'):client.call('select_output_profile',target=target,profile_id=profile['id'])
            with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            client.call('configure_stream',endpoint={'transport':'rtmp','port':port})
            wait(lambda s:any(x['id']==source_id and x.get('capture_delivery')=='receiving' for x in s['sources']),'display_receiving')
            client.call('preflight_output',target='recording');receiver=Receiver(str(app/'Contents/MacOS/ffmpeg'),out,port)
            for target in ('recording','streaming'):
                slot=client.call('start_output',target=target)['state']['outputs'][target];attempts[target]=slot['attempt_id']
                report['media'].append({'target':target,'path':str(receiver.path) if target=='streaming' else slot['path']})
            wait(lambda s:all(s['outputs'][t]['phase']=='active' for t in attempts),'active')
            report['initial_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
            start=time.monotonic();snapshot('display-start')
            while time.monotonic()-start<60:
                state=sample('controlled_display')
                require(fixture.poll() is None,'Cover process exited during capture')
                require(state['project']['graph']['active_scene']==scene,'Unexpected fallback')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()),'Output interrupted')
                before=time.monotonic();memory=client.call('memory_diagnostics')
                report['memory'].append({'host_bracket_s':[before,time.monotonic()],'response':memory})
                checkpoint();time.sleep(1)
            snapshot('display-end');report['phases'].append({'name':'controlled_display','start':start,'end':time.monotonic()})
            client.call('select_scene',scene_id=safe)
            wait(lambda s:s['project']['graph']['active_scene']==safe and s['transition']['phase']=='completed','safe_cut')
            end=time.monotonic()+3
            while time.monotonic()<end:
                state=sample('safe_continuity');require(all(state['outputs'][t]['phase']=='active' for t in attempts),'Safe Cut interrupted outputs');time.sleep(.25)
            client.call('stop_output_target',target='streaming');wait(lambda s:not s['outputs']['streaming']['native_busy'],'stream_stop')
            require(client.state()['outputs']['recording']['phase']=='active','Independent stop failed')
            client.call('stop_output_target',target='recording');wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'quiescent')
            report['final_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
            report['runtime_status']='PASS';report['status']='PARTIAL'
        except Exception as error:report['error']=repr(error)
        finally:
            safe_to_close=False
            if client:
                try:
                    state=client.state()
                    for t,a in attempts.items():
                        require(state['outputs'][t]['attempt_id']==a,'Output identity changed')
                        if state['outputs'][t]['native_busy']:client.call('stop_output_target',target=t)
                    wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'cleanup_quiescent',25)
                    if source_id:
                        state=client.state()
                        if state['project']['graph']['active_scene']!=safe:
                            client.call('select_scene',scene_id=safe)
                            wait(lambda s:s['transition']['phase']=='completed','cleanup_safe')
                        client.call('remove_scene',scene_id=scene);client.call('remove_source',source_id=source_id)
                    safe_to_close=True
                except Exception as error:report['cleanup_errors'].append(repr(error))
                client.close()
            if fixture and fixture.poll() is None and safe_to_close:
                fixture.stdin.write('quit\n');fixture.stdin.flush();fixture.wait(timeout=8)
            if receiver:report['receiver_exit']=receiver.close()
            report['fixture_exit']=fixture.poll() if fixture else None;checkpoint()
    print(json.dumps({'status':report['status'],'error':report.get('error'),'cleanup_errors':report['cleanup_errors']}))
    return int(report.get('runtime_status')!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
