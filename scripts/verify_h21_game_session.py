#!/usr/bin/env python3
"""Owned Arkanoid + explicitly selected Display, application audio and dual outputs.

Use h21_run_owned_session with an external deadline and the canonical lock.
The 60-second mode is a pilot, never a one-hour acceptance result. Physical mic
selection additionally requires confirmation that its environment is controlled.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from h21_trace_origin import collect_origin

from h7_support import Client
from h21_gpu_sample import sample_gpu
from verify_h14_collection import ROOT, Receiver, default_owner, digest, lines, lock, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--display-uuid', required=True)
    parser.add_argument('--seconds', type=int, choices=(60,3600), required=True)
    parser.add_argument('--authorized-controlled-display', action='store_true', required=True)
    parser.add_argument('--microphone-id')
    parser.add_argument('--controlled-microphone-prepared', action='store_true')
    args = parser.parse_args()
    if args.microphone_id and not args.controlled_microphone_prepared:
        parser.error('Physical microphone requires controlled environment confirmation')
    held = lock(); app = args.app.resolve(strict=True)
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    cover_binary = ROOT/'target/H21CaptureFixtureV4.app/Contents/MacOS/MotiveH21CaptureFixture'
    game_binary = ROOT/'target/H21Arkanoid.app/Contents/MacOS/MotiveH21Arkanoid'
    other_binary = ROOT/'target/H13AudioFixture.app/Contents/MacOS/MotiveAudioFixture'
    report = {'status':'FAIL','scenario':'gaming','requested_seconds':args.seconds,'fps':60,
        'owner_sha256':digest(app/'Contents/MacOS/motive'),'lock':held,'events':[],
        'memory':[],'gpu':[],'media':[],'cleanup_errors':[], 'snapshots':[],
        'microphone_requested':bool(args.microphone_id),
        'limits':['Modified open-source Arkanoid with automated input; light 2D workload only.',
                  'A/V marker follows game audio sample clock; camera sync not measured.',
                  'One-hour acceptance additionally requires decoded media and resource analysis.']}
    report['fixture_hashes'] = {str(p):digest(p) for p in (cover_binary,game_binary,other_binary)}
    for p in (Path(__file__),ROOT/'scripts/fixtures/h21_game.c',ROOT/'scripts/fixtures/h21_game_window.m',
              ROOT/'target/H21CaptureFixtureV4-source.m',ROOT/'target/H21CaptureFixtureV4-build.json'):
        shutil.copy2(p,out/p.name)
    abort_file = Path(os.environ['MOTIVE_TEST_ABORT_FILE'])
    client = cover = game = other = receiver = None
    safe = capture_scene = source_id = None
    attempts = {}; audio_ids = []; handles = []; start = None
    def checkpoint(): save(out/'report.json',report)
    def event(name, **data):
        report['events'].append({'name':name,'host_monotonic':time.monotonic(),**data});checkpoint()
    def launch(binary, arguments, stem, stdin=False):
        log = (out/(stem+'.jsonl')).open('x'); err = (out/(stem+'.stderr')).open('x')
        handles.extend((log,err))
        return subprocess.Popen([str(binary),*arguments],stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                stdout=log,stderr=err,text=True)
    def bounded(predicate, label, seconds=15):
        end = time.monotonic()+seconds
        while True:
            state=client.state()
            if predicate(state): return state
            require(time.monotonic()<end,label+' timeout')
            time.sleep(.2)
    def snapshot(label):
        before=time.monotonic();client.call('snapshot');after=time.monotonic()
        path=out/(label+'.png');shutil.copy2(Path.home()/'Library/Logs/Motive/preview.png',path)
        report['snapshots'].append({'label':label,'path':str(path),'sha256':digest(path),'host_bracket_s':[before,after]})
    def add_audio(name, spec, gain):
        state=client.call('add_audio_input',name=name,source=spec)['state']
        ident=next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']==name)
        audio_ids.append(ident);client.call('set_audio_gain',input_id=ident,gain_db=gain)
        return ident
    try:
        client=Client();initial=client.state();default_owner(initial);report['owner_pid']=initial['pid']
        devices=client.call('devices')['devices'];save(out/'devices-private.json',devices)
        targets=[d for d in devices['displays'] if d['display_uuid']==args.display_uuid]
        require(len(targets)==1,'Explicit authorized display unavailable');report['display']=targets[0]
        if args.microphone_id:
            require(any(i['id']==args.microphone_id for i in devices['audio']),'Explicit microphone unavailable')
        cover=launch(cover_binary,['--seconds',str(args.seconds+240)],'cover',True)
        report['cover_pid']=cover.pid
        end=time.monotonic()+12
        while not any(e.get('reason')=='ready' for e in lines(out/'cover.jsonl')):
            require(cover.poll() is None and time.monotonic()<end,'Cover startup failed');time.sleep(.1)
        cover.stdin.write('cover 0\n');cover.stdin.flush()
        while True:
            rows=lines(out/'cover.jsonl'); row=rows[-1] if rows else {}
            bounds=row.get('windows',[{}])[0].get('bounds'); d=targets[0]['bounds']
            if bounds and all(abs(bounds[a]-d[b])<1 for a,b in [('X','x'),('Y','y'),('Width','width'),('Height','height')]):break
            require(cover.poll() is None and time.monotonic()<end,'Cover does not match selected display');time.sleep(.1)
        report['cover_observed']=row
        game=launch(game_binary,['--display-uuid',args.display_uuid,'--seconds',str(args.seconds+120)],'game')
        other=launch(other_binary,['--frequency','733','--peak-dbfs','-36'],'other-audio')
        report.update(game_pid=game.pid,other_audio_pid=other.pid)
        end=time.monotonic()+15
        while True:
            rows=lines(out/'game.jsonl')
            if any(r.get('event')=='game' and r.get('audio_frames',0)>48000 for r in rows):break
            require(game.poll() is None and time.monotonic()<end,'Game startup/audio failed');time.sleep(.2)
        report['game_ready']=next(r for r in rows if r.get('event')=='ready')
        client.call('configure_video',video={'version':1,'resolution':'full_hd1080','fps':60,'coordinate_space':'design960'})
        client.call('set_overlay',visible=False);safe=client.state()['project']['graph']['active_scene']
        client.call('configure_capture_fallback',scene_id=safe)
        capture_scene=client.call('create_scene',name='H21 Gaming controlled')['state']['project']['graph']['active_scene']
        state=client.call('add_source',scene_id=capture_scene,name='H21 game Display',
                          source={'kind':'display','display_uuid':args.display_uuid})['state']
        source_id=next(s['id'] for s in state['project']['graph']['sources'] if s['name']=='H21 game Display')
        definition={'kind':'text','text':'MOTIVE H21 · ARKANOID · LOCAL TEST','font':'Helvetica','size':20,
            'color':0xffffff,'opacity':1.0,'align':'left','width':620,'height':40,'background':0x122030,
            'background_opacity':0.85,'outline':False}
        overlay=client.call('create_overlay',scene_id=capture_scene,name='H21 owned game label',definition=definition)
        overlay_id=overlay['result']['source_id']
        graph=overlay['state']['project']['graph']
        layer=next(l for scene in graph['scenes'] if scene['id']==capture_scene for l in scene['layers'] if l['source_id']==overlay_id)
        client.call('set_transform',scene_id=capture_scene,layer_id=layer['id'],variant='horizontal',
                    transform={'x':40,'y':490,'width':620,'height':30,'order':2,'visible':True})
        game_audio=add_audio('H21 actual game audio',{'kind':'system_application','bundle_id':'local.motive.h21arkanoid'},-6)
        other_audio=add_audio('H21 second application 733 Hz',{'kind':'system_application','bundle_id':'local.motive.audiofixture'},-6)
        add_audio('H21 continuity 440 Hz',{'kind':'tone'},-18)
        if args.microphone_id:
            add_audio('H21 explicit physical microphone',{'kind':'microphone','device_id':args.microphone_id},-12)
        bounded(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']),'mixer ready')
        bounded(lambda s:any(i['id']==source_id and i.get('capture_delivery')=='receiving' for i in s['sources']),'Display receiving')
        profile={'id':'h21-game','encoder':'videotoolbox','bitrate_kbps':6000,'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':False}
        client.call('upsert_output_profile',profile=profile)
        for target in ('recording','streaming'):client.call('select_output_profile',target=target,profile_id=profile['id'])
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        client.call('configure_stream',endpoint={'transport':'rtmp','port':port})
        receiver=Receiver(str(app/'Contents/MacOS/ffmpeg'),out,port)
        client.call('preflight_output',target='recording')
        report['initial_traces']={}
        for target in ('recording','streaming'):
            slot=client.call('start_output',target=target)['state']['outputs'][target];attempts[target]=slot['attempt_id']
            report['media'].append({'target':target,'path':str(receiver.path) if target=='streaming' else slot['path']})
            bounded(lambda s:s['outputs'][target]['phase']=='active',target+' active')
            report['initial_traces'][target]=collect_origin(client,target,attempts[target])
        state=bounded(lambda s:all(s['outputs'][t]['phase']=='active' for t in attempts),'outputs active')
        require(all(state['outputs'][t]['encoding']['selected_hardware'] for t in attempts),'Hardware encoder required')
        report['initial_state']=state
        start=time.monotonic();report['started_monotonic']=start;event('session_started');snapshot('start')
        next_memory=next_checkpoint=0; next_switch=20 if args.seconds==60 else 300; return_at=None; switch_index=0
        with (out/'samples.jsonl').open('x') as samples:
            while time.monotonic()-start < args.seconds:
                before=time.monotonic();state=client.state();now=time.monotonic();elapsed=now-start
                samples.write(json.dumps({'host_bracket_s':[before,now],'elapsed_s':elapsed,'state':state})+'\n');samples.flush()
                report['last_elapsed_s']=elapsed;report['last_state']=state
                require(not abort_file.exists(),'External supervisor requested stop')
                require(all(p.poll() is None for p in (cover,game,other)),'Owned producer exited')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()),'Output interrupted')
                require(not state['audio_mixer']['issues'],'Audio input issue')
                require(state['audio_mixer']['runtime']['mix']['clipped_blocks']==0,'Mixer clipping')
                require(not state['capture_recovery']['fallback_attempted'],'Unexpected capture fallback')
                if elapsed>=next_memory:
                    report['memory'].append({'elapsed_s':elapsed,'response':client.call('memory_diagnostics')});next_memory+=5
                if return_at is not None and elapsed>=return_at:
                    client.call('select_scene',scene_id=capture_scene);event('return_game');return_at=None
                elif elapsed>=next_switch and elapsed<args.seconds-10:
                    kind='fade' if switch_index%2 else 'cut'
                    client.call('configure_transition',transition={'kind':kind,'duration_ms':300 if kind=='fade' else 0})
                    client.call('select_scene',scene_id=safe);event('planned_safe_scene',transition=kind)
                    return_at=elapsed+3;next_switch+=20 if args.seconds==60 else 300;switch_index+=1
                if elapsed>=next_checkpoint:
                    report['gpu'].append({'elapsed_s':elapsed,'response':sample_gpu()})
                    checkpoint();next_checkpoint+=15
                time.sleep(1)
        report['observed_seconds']=time.monotonic()-start;snapshot('end');event('session_completed')
        client.call('configure_transition',transition={'kind':'cut','duration_ms':0})
        client.call('select_scene',scene_id=safe)
        bounded(lambda s:s['project']['graph']['active_scene']==safe and s['transition']['phase']=='completed','final safe Cut')
        end=time.monotonic()+3
        while time.monotonic()<end:
            state=client.state();require(all(state['outputs'][t]['phase']=='active' for t in attempts),'Final safe continuity failed');time.sleep(.2)
        client.call('stop_output_target',target='streaming');bounded(lambda s:not s['outputs']['streaming']['native_busy'],'stream stop')
        require(client.state()['outputs']['recording']['phase']=='active','Independent stop failed')
        client.call('stop_output_target',target='recording');bounded(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'record stop')
        report['final_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
        report['runtime_status']='PASS';report['status']='PARTIAL'
    except Exception as error:
        report['error']=repr(error)
    finally:
        safe_to_close=False
        if client:
            try:
                state=client.state()
                for target,attempt in attempts.items():
                    require(state['outputs'][target]['attempt_id']==attempt,'Output identity changed during cleanup')
                    if state['outputs'][target]['native_busy']:client.call('stop_output_target',target=target)
                bounded(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'cleanup quiescence',30)
                if source_id:
                    client.call('configure_transition',transition={'kind':'cut','duration_ms':0})
                    if client.state()['project']['graph']['active_scene']!=safe:client.call('select_scene',scene_id=safe)
                    bounded(lambda s:s['transition']['phase'] in ('idle','completed'),'cleanup scene')
                    client.call('remove_scene',scene_id=capture_scene);client.call('remove_source',source_id=source_id)
                for ident in audio_ids:client.call('remove_audio_input',input_id=ident)
                safe_to_close=True
            except Exception as error:report['cleanup_errors'].append(repr(error))
            client.close()
        if safe_to_close:
            for name,proc in [('game',game),('other_audio',other)]:
                if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=10)
                report[name+'_exit']=proc.poll() if proc else None
            if cover and cover.poll() is None:cover.stdin.write('quit\n');cover.stdin.flush();cover.wait(timeout=8)
        report['cover_exit']=cover.poll() if cover else None
        if receiver:report['receiver_exit']=receiver.close()
        if not safe_to_close:report['cleanup_errors'].append('Cover retained: capture cleanup not proven')
        checkpoint()
        for handle in handles:handle.close()
    print(json.dumps({'status':report['status'],'runtime_status':report.get('runtime_status'),
                      'error':report.get('error'),'cleanup_errors':report['cleanup_errors']}))
    return int(report.get('runtime_status')!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
