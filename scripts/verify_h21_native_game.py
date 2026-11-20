#!/usr/bin/env python3
"""Isolated official SuperTuxKart with explicit owned Window, game audio and dual outputs.

Use h21_run_owned_session with an external deadline and the canonical lock.
The 60-second mode is a pilot, never a one-hour acceptance result. Physical mic
selection additionally requires confirmation that its environment is controlled.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from h21_trace_origin import collect_origin

from h7_support import Client
from h21_gpu_sample import sample_gpu
from verify_h14_collection import ROOT, Receiver, default_owner, digest, lines, lock, require, save


def display_observation():
    """Read display topology only; no settings, screenshots or window inventory."""
    cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    u=ctypes.c_uint32
    cg.CGGetActiveDisplayList.argtypes=[u,ctypes.POINTER(u),ctypes.POINTER(u)]
    cg.CGGetActiveDisplayList.restype=ctypes.c_int32
    cg.CGMainDisplayID.restype=u
    for name in ('CGDisplayPixelsWide','CGDisplayPixelsHigh'):
        getattr(cg,name).argtypes=[u];getattr(cg,name).restype=ctypes.c_size_t
    cg.CGDisplayIsBuiltin.argtypes=[u];cg.CGDisplayIsBuiltin.restype=u
    ids=(u*16)();count=u();before=time.monotonic()
    require(cg.CGGetActiveDisplayList(16,ids,ctypes.byref(count))==0,'Display observation failed')
    main=cg.CGMainDisplayID()
    displays=[{'id':int(ids[i]),'is_main':ids[i]==main,'built_in':bool(cg.CGDisplayIsBuiltin(ids[i])),
               'cg_width':cg.CGDisplayPixelsWide(ids[i]),'cg_height':cg.CGDisplayPixelsHigh(ids[i])}
              for i in range(count.value)]
    return {'host_bracket_s':[before,time.monotonic()],'displays':displays}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--game-app', type=Path, required=True)
    parser.add_argument('--seed-players', type=Path, required=True)
    parser.add_argument('--seconds', type=int, choices=(60,3600), required=True)
    parser.add_argument('--capture-mode', choices=('window','application'), default='window')
    parser.add_argument('--authorized-controlled-game', action='store_true', required=True)
    parser.add_argument('--microphone-id')
    parser.add_argument('--controlled-microphone-prepared', action='store_true')
    args = parser.parse_args()
    if args.microphone_id and not args.controlled_microphone_prepared:
        parser.error('Physical microphone requires controlled environment confirmation')
    held = lock(); app = args.app.resolve(strict=True)
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    game_binary = args.game_app.resolve(strict=True)/'Contents/MacOS/supertuxkart'
    import plistlib
    game_bundle = plistlib.loads((args.game_app/'Contents/Info.plist').read_bytes())['CFBundleIdentifier']
    require(game_bundle == 'net.sourceforge.supertuxkart', 'Expected official game identity')
    require(digest(game_binary) == '504a9b38a43236fd3c5e0a832bae99ea88ffc66290ec85ebba60f4c192f4c841', 'Pinned game binary changed')
    report = {'status':'FAIL','scenario':'gaming-native3d','requested_seconds':args.seconds,'fps':60,
        'owner_sha256':digest(app/'Contents/MacOS/motive'),'lock':held,'events':[],
        'memory':[],'gpu':[],'media':[],'cleanup_errors':[], 'snapshots':[], 'display_observations':[],
        'microphone_requested':bool(args.microphone_id), 'capture_mode':args.capture_mode,
        'limits':['Official native 3D automated race; measured workload, not all games.',
                  'Game audio is not a calibrated A/V reference; physical microphone is separate.',
                  'Duration and runtime counters alone do not establish decoded visual progress.']}
    report['game_sha256'] = digest(game_binary)
    report['seed_players_sha256'] = digest(args.seed_players)
    shutil.copy2(__file__,out/Path(__file__).name)
    profile=out/'game-profile';profile.mkdir();(profile/'tmp').mkdir();config=profile/'config-0.10';config.mkdir()
    players=args.seed_players.read_text()
    # This seed was created by the owned offline --race-now first-run smoke.
    # No personal game profile or authentication data is loaded.
    player_tree=ET.fromstring(players)
    player_nodes=player_tree.findall('player')
    require(player_nodes and all(p.get('saved-token')=='' and p.get('saved-session')=='false'
                                for p in player_nodes), 'Expected offline player seed')
    require(len(player_nodes)==1, 'Expected one owned offline player')
    player_nodes[0].set('name','C8 Offline')
    # MainMenuScreen::onUpdate asks about the tutorial when use-frequency is 0.
    # Mark this private automated profile as initialized, without gameplay claims.
    player_nodes[0].set('use-frequency','1')
    current=player_tree.find('current')
    require(current is not None, 'Offline player selection missing')
    current.set('player','C8 Offline')
    (config/'players.xml').write_text(ET.tostring(player_tree,encoding='unicode'))
    (config/'config.xml').write_text('<stkconfig version="8"><enable_internet value="2"/><Audio sfx_on="true" music_on="true" sfx_volume="0.1" music_volume="0.1"/><Video real_width="1920" real_height="1080" fullscreen="false" max_fps="120" show_fps="true"/></stkconfig>')
    sandbox=out/'game.sb'
    sandbox.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(profile))+'))\n(deny file-read* (subpath '+json.dumps(str(Path.home()/'Library/Application Support/SuperTuxKart'))+'))\n')
    game_command=['/usr/bin/sandbox-exec','-f',str(sandbox),str(game_binary),'--windowed','--screensize=1920x1080',
                  '--demo-mode=1','--demo-tracks=lighthouse','--demo-laps=999','--demo-karts=20',
                  '--disable-addon-karts','--disable-addon-tracks','--enable-dynamic-lights',
                  '--shadows=2048','--enable-ssao','--enable-bloom','--enable-hd-textures']
    game_env=os.environ.copy();game_env.update(SUPERTUXKART_SAVEDIR=str(profile),TMPDIR=str(profile/'tmp'))
    report['game_command']=game_command;report['game_resources']=[]
    abort_file = Path(os.environ['MOTIVE_TEST_ABORT_FILE'])
    client = game = receiver = None
    safe = capture_scene = source_id = None
    attempts = {}; audio_ids = []; handles = []; start = None
    def checkpoint(): save(out/'report.json',report)
    def event(name, **data):
        report['events'].append({'name':name,'host_monotonic':time.monotonic(),**data});checkpoint()
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
        report['display_observations'].append(display_observation())
        if args.microphone_id:
            require(any(i['id']==args.microphone_id for i in devices['audio']),'Explicit microphone unavailable')
        game_log=(out/'game.log').open('x');handles.append(game_log)
        game=subprocess.Popen(game_command,cwd=profile,env=game_env,stdout=game_log,stderr=game_log)
        report['game_pid']=game.pid;checkpoint()
        end=time.monotonic()+30
        while True:
            require(game.poll() is None, 'Owned game exited before capture')
            windows=[w for w in client.call('devices')['devices']['windows'] if w['pid']==game.pid and w['bundle_id']==game_bundle]
            if len(windows)==1:break
            require(time.monotonic()<end,'Exact owned game window unavailable');time.sleep(.2)
        report['selected_window']=windows[0]
        # CG window discovery can precede SCK/LaunchServices audio admission.
        # Observe that separate contract; never retry a failed audio source.
        end=time.monotonic()+45
        report['audio_admission_observations']=[]
        while True:
            require(game.poll() is None, 'Owned game exited during audio admission')
            inventory=client.call('system_audio_sources')['system_audio_sources']
            matches=[x for x in inventory['applications'] if x['bundle_id']==game_bundle]
            report['audio_admission_observations'].append({'host_monotonic':time.monotonic(),'matches':matches})
            checkpoint()
            if len(matches)==1 and matches[0]['selectable']:break
            require(time.monotonic()<end,'Explicit game audio target did not become selectable')
            time.sleep(.25)
        end=time.monotonic()+60
        while 'Track: Overall scene complexity' not in (out/'game.log').read_text():
            require(game.poll() is None and time.monotonic()<end, 'Game track did not load; menu is not a 3D workload')
            require(not abort_file.exists(), 'Supervisor abort during game loading')
            time.sleep(.25)
        report['track_load_observed_monotonic']=time.monotonic()
        client.call('configure_video',video={'version':1,'resolution':'full_hd1080','fps':60,'coordinate_space':'design960'})
        client.call('set_overlay',visible=False);safe=client.state()['project']['graph']['active_scene']
        client.call('configure_capture_fallback',scene_id=safe)
        capture_scene=client.call('create_scene',name='H21 Gaming controlled')['state']['project']['graph']['active_scene']
        capture_spec={'kind':'window','window_id':windows[0]['id']}
        if args.capture_mode=='application':
            # This variant is explicitly bounded to the single observed display.
            # Only the admitted owned application is included, never desktop pixels.
            require(len(report['display_observations'][0]['displays'])==1,
                    'Application variant requires one observed display')
            displays=[d for d in inventory['displays'] if d['is_main'] and d['selectable']]
            require(len(displays)==1,'Explicit main display identity unavailable')
            capture_spec={'kind':'application','bundle_id':game_bundle,'display_uuid':displays[0]['display_uuid']}
        report['capture_source']=capture_spec
        capture_name='H21 native game '+args.capture_mode.title()
        state=client.call('add_source',scene_id=capture_scene,name=capture_name,source=capture_spec)['state']
        source_id=next(s['id'] for s in state['project']['graph']['sources'] if s['name']==capture_name)
        definition={'kind':'text','text':'MOTIVE C8 · SUPERTUXKART · LOCAL TEST','font':'Helvetica','size':20,
            'color':0xffffff,'opacity':1.0,'align':'left','width':620,'height':40,'background':0x122030,
            'background_opacity':0.85,'outline':False}
        overlay=client.call('create_overlay',scene_id=capture_scene,name='H21 owned game label',definition=definition)
        overlay_id=overlay['result']['source_id']
        graph=overlay['state']['project']['graph']
        layer=next(l for scene in graph['scenes'] if scene['id']==capture_scene for l in scene['layers'] if l['source_id']==overlay_id)
        client.call('set_transform',scene_id=capture_scene,layer_id=layer['id'],variant='horizontal',
                    transform={'x':40,'y':490,'width':620,'height':30,'order':2,'visible':True})
        game_audio=add_audio('H21 actual game audio',{'kind':'system_application','bundle_id':game_bundle},-6)
        if args.microphone_id:
            add_audio('H21 explicit physical microphone',{'kind':'microphone','device_id':args.microphone_id},-12)
        bounded(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']),'mixer ready')
        bounded(lambda s:any(i['id']==source_id and i.get('capture_delivery')=='receiving' for i in s['sources']),'Owned game capture receiving')
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
                require(game.poll() is None,'Owned game exited')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()),'Output interrupted')
                require(not state['audio_mixer']['issues'],'Audio input issue')
                require(state['audio_mixer']['runtime']['mix']['clipped_blocks']==0,'Mixer clipping')
                require(not state['capture_recovery']['fallback_attempted'],'Unexpected capture fallback')
                if elapsed>=next_memory:
                    report['display_observations'].append(display_observation())
                    report['memory'].append({'elapsed_s':elapsed,'response':client.call('memory_diagnostics')})
                    metrics=subprocess.check_output(['ps','-p',str(game.pid),'-o','%cpu=,rss='],text=True).split()
                    require(len(metrics)==2,'Game process metrics unavailable')
                    report['game_resources'].append({'elapsed_s':elapsed,'cpu_percent':float(metrics[0]),'rss_kib':int(metrics[1])})
                    require(int(metrics[1])<4*1024*1024,'Game RSS bound exceeded')
                    next_memory+=5
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
        try:report['display_observations'].append(display_observation())
        except Exception as observation_error:report['display_observation_error']=repr(observation_error)
    finally:
        safe_to_close=False
        if client:
            try:
                state=client.state()
                for target,attempt in attempts.items():
                    require(state['outputs'][target]['attempt_id']==attempt,'Output identity changed during cleanup')
                    if state['outputs'][target]['native_busy']:client.call('stop_output_target',target=target)
                bounded(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'cleanup quiescence',30)
                if attempts and not report.get('final_traces'):
                    report['final_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
                    report['final_traces_collected_during_failed_cleanup']=True
                if source_id:
                    client.call('configure_transition',transition={'kind':'cut','duration_ms':0})
                    if client.state()['project']['graph']['active_scene']!=safe:client.call('select_scene',scene_id=safe)
                    bounded(lambda s:s['transition']['phase'] in ('idle','completed'),'cleanup scene')
                    client.call('remove_scene',scene_id=capture_scene);client.call('remove_source',source_id=source_id)
                for ident in audio_ids:client.call('remove_audio_input',input_id=ident)
                safe_to_close=True
            except Exception as error:report['cleanup_errors'].append(repr(error))
            client.close()
        if safe_to_close and game:
            if game.poll() is None:game.terminate()
            try:report['game_exit']=game.wait(timeout=10)
            except subprocess.TimeoutExpired:
                game.kill();report['game_exit']=game.wait(timeout=10);report['forced_game_kill']=True
        if receiver:report['receiver_exit']=receiver.close()
        if not safe_to_close:report['cleanup_errors'].append('Game retained: capture cleanup not proven')
        checkpoint()
        for handle in handles:handle.close()
    print(json.dumps({'status':report['status'],'runtime_status':report.get('runtime_status'),
                      'error':report.get('error'),'cleanup_errors':report['cleanup_errors']}))
    return int(report.get('runtime_status')!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
