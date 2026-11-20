#!/usr/bin/env python3
"""Bounded real camera/presentation sessions, owned content and local dual outputs.

A generated guest marker measures the application path. It does not establish
physical camera/microphone synchronization. Run via h21_run_owned_session.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from h7_support import Client
from h21_gpu_sample import sample_gpu
from h21_audio_observation import classify_issues
from verify_h14_collection import ROOT, Receiver, default_owner, digest, lines, lock, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', choices=('podcast', 'charlas'), required=True)
    parser.add_argument('--seconds', type=int, choices=(60, 3600), required=True)
    parser.add_argument('--camera-id')
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--controlled-devices-prepared', action='store_true', required=True)
    parser.add_argument('--display-uuid')
    parser.add_argument('--presentation-display-uuid')
    parser.add_argument('--authorized-controlled-display', action='store_true')
    parser.add_argument('--collect-microphone-clipping', action='store_true',
                        help='Continue diagnostic collection on mic clipping; keep audio quality FAIL')
    args = parser.parse_args()
    if args.scenario == 'podcast' and not args.camera_id:
        parser.error('Podcast requires an explicitly prepared physical camera')
    if args.scenario == 'charlas' and not (args.display_uuid and args.presentation_display_uuid and args.authorized_controlled_display):
        parser.error('Charlas requires explicit controlled Display authorization')
    held = lock(); app = args.app.resolve(strict=True)
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    fixture_name = 'H21CaptureFixtureV6' if args.scenario=='charlas' else 'H21CaptureFixtureV4'
    fixture_binary = ROOT/('target/'+fixture_name+'.app/Contents/MacOS/MotiveH21CaptureFixture')
    report = {'status': 'FAIL', 'scenario': args.scenario, 'requested_seconds': args.seconds,
              'fps': 30, 'owner_sha256': digest(app/'Contents/MacOS/motive'), 'lock': held,
              'events': [], 'memory': [], 'gpu': [], 'media': [], 'snapshots': [], 'cleanup_errors': [],
              'fixture_sha256': digest(fixture_binary), 'physical_camera_av': 'NOT_MEASURED',
              'audio_quality_status': 'NOT_COMPLETED', 'audio_quality_warnings': [],
              'collect_microphone_clipping': args.collect_microphone_clipping,
              'browser_capture': 'BLOCKED_OWNED_VISIBLE_BROWSER_UNAVAILABLE' if args.scenario=='charlas' else 'NOT_REQUIRED',
              'limits': ['Controlled generated guest audio/video, not a remote guest call.',
                         'Application marker does not calibrate physical camera/microphone latency.',
                         'No personal browser, Spaces settings or display mode changes.']}
    for p in (Path(__file__), ROOT/'scripts/h21_audio_observation.py', ROOT/('target/'+fixture_name+'-source.m'),
              ROOT/('target/'+fixture_name+'-build.json')):
        shutil.copy2(p, out/p.name)
    abort = Path(os.environ['MOTIVE_TEST_ABORT_FILE'])
    client = fixture = receiver = None; attempts = {}; audio_ids = []; scenes = []; sources = []
    handles = []; safe = main_scene = None
    def checkpoint(): save(out/'report.json', report)
    def event(name, **data):
        report['events'].append({'name': name, 'host_monotonic': time.monotonic(), **data}); checkpoint()
    def wait(predicate, label, seconds=15):
        end = time.monotonic()+seconds
        while True:
            state = client.state()
            if predicate(state): return state
            require(not abort.exists(), 'External supervisor requested stop')
            require(time.monotonic()<end, label+' timeout'); time.sleep(.2)
    def fixture_command(command):
        require(fixture.poll() is None, 'Owned producer exited')
        fixture.stdin.write(command+'\n'); fixture.stdin.flush(); event('fixture_command', command=command)
    def snapshot(label):
        before = time.monotonic(); client.call('snapshot'); after = time.monotonic()
        path = out/(label+'.png'); shutil.copy2(Path.home()/'Library/Logs/Motive/preview.png', path)
        report['snapshots'].append({'label': label, 'path': str(path), 'sha256': digest(path), 'host_bracket_s': [before, after]})
    def add_scene(name):
        ident = client.call('create_scene', name=name)['state']['project']['graph']['active_scene']
        scenes.append(ident); return ident
    def add_source(scene, name, spec, rect=None, order=0):
        state = client.call('add_source', scene_id=scene, name=name, source=spec)['state']
        graph = state['project']['graph']; ident = next(s['id'] for s in graph['sources'] if s['name']==name)
        sources.append(ident)
        if rect:
            layer = next(l for s in graph['scenes'] if s['id']==scene for l in s['layers'] if l['source_id']==ident)
            client.call('set_transform', scene_id=scene, layer_id=layer['id'], variant='horizontal',
                        transform=dict(zip(('x', 'y', 'width', 'height'), rect), order=order, visible=True))
        return ident
    def add_audio(name, source, gain):
        state = client.call('add_audio_input', name=name, source=source)['state']
        ident = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']==name)
        audio_ids.append(ident); client.call('set_audio_gain', input_id=ident, gain_db=gain); return ident
    try:
        client = Client(); state = client.state(); default_owner(state); report['owner_pid'] = state['pid']
        devices = client.call('devices')['devices']; save(out/'devices-private.json', devices)
        require(devices['microphone_permission'] and devices['screen_permission'], 'Normal audio/screen permission required')
        require(any(d['id']==args.microphone_id for d in devices['audio']), 'Prepared microphone absent')
        if args.camera_id:
            require(devices['camera_permission'] and any(d['id']==args.camera_id for d in devices['cameras']), 'Prepared camera unavailable')
        log = (out/'fixture.jsonl').open('x'); err = (out/'fixture.stderr').open('x'); handles.extend((log, err))
        fixture_args = ['--seconds', str(args.seconds+180), '--audio']
        if args.scenario=='charlas':
            require(any(d['display_uuid']==args.presentation_display_uuid for d in devices['displays']), 'Explicit presentation display absent')
            require(args.presentation_display_uuid!=args.display_uuid, 'Presentation and covered displays must differ')
            fixture_args += ['--presentation-display-uuid',args.presentation_display_uuid]
        fixture = subprocess.Popen([str(fixture_binary), *fixture_args],
                                   stdin=subprocess.PIPE, stdout=log, stderr=err, text=True)
        report['fixture_pid'] = fixture.pid; end = time.monotonic()+12
        while True:
            ready = next((r for r in reversed(lines(out/'fixture.jsonl')) if r.get('audio_frames', 0)>48000
                          and len(r.get('windows', []))==2 and all(isinstance(w['bounds'], dict) for w in r['windows'])), None)
            if ready: break
            require(fixture.poll() is None and time.monotonic()<end, 'Fixture startup failed'); time.sleep(.2)
        report['ready'] = ready
        selected_window = ready['windows'][0]
        if args.scenario == 'charlas':
            displays = [d for d in devices['displays'] if d['display_uuid']==args.display_uuid]
            require(len(displays)==1, 'Explicit Display absent'); report['display'] = displays[0]
            fixture_command('cover 0'); fixture_command('present 1')
            end = time.monotonic()+8
            while True:
                row = lines(out/'fixture.jsonl')[-1]; b = row['windows'][0]['bounds']; d = displays[0]['bounds']
                pb=row['windows'][1]['bounds'];pd=next(x['bounds'] for x in devices['displays'] if x['display_uuid']==args.presentation_display_uuid)
                on_presentation=pb and pd['x']<=pb['X'] and pd['y']<=pb['Y'] and pb['X']+pb['Width']<=pd['x']+pd['width'] and pb['Y']+pb['Height']<=pd['y']+pd['height']
                if b and on_presentation and all(abs(b[a]-d[v])<1 for a,v in [('X','x'),('Y','y'),('Width','width'),('Height','height')]): break
                require(time.monotonic()<end, 'Owned cover does not match authorized Display'); time.sleep(.2)
            report['cover_observed'] = row; selected_window = row['windows'][1]
        client.call('configure_video', video={'version':1, 'resolution':'full_hd1080', 'fps':30, 'coordinate_space':'design960'})
        client.call('set_overlay', visible=False); safe = client.state()['project']['graph']['active_scene']
        client.call('configure_capture_fallback', scene_id=safe)
        main_scene = add_scene('H21 '+args.scenario)
        camera = None
        if args.scenario == 'podcast':
            camera = add_source(main_scene, 'H21 prepared camera', {'kind':'camera', 'device_id':args.camera_id}, [0,0,960,540])
            # Leave the lower camera area unobstructed for the visible physical
            # sync gesture. The analyzer derives its crop from this stored rect.
            window_rect = [20,20,340,150]
        else: window_rect = [0,0,960,540]
        window_source = add_source(main_scene, 'H21 owned guest/presentation',
                                   {'kind':'window', 'window_id':selected_window['window_id']}, window_rect, 1)
        report.update(window_rect=window_rect, window_bounds=selected_window['bounds'], window_source_id=window_source,
                      main_scene=main_scene, safe_scene=safe, camera_source_id=camera)
        alternate = safe
        if args.scenario == 'charlas':
            app_scene = add_scene('H21 application presentation')
            add_source(app_scene, 'H21 owned application', {'kind':'application', 'bundle_id':'local.motive.h21capturefixture',
                                                          'display_uuid':args.presentation_display_uuid})
            display_scene = add_scene('H21 controlled shared Display')
            add_source(display_scene, 'H21 explicitly shared Display', {'kind':'display', 'display_uuid':args.display_uuid})
            alternate = app_scene; report['application_scene'] = app_scene; report['display_scene'] = display_scene
        client.call('select_scene', scene_id=main_scene)
        guest = add_audio('H21 generated guest', {'kind':'system_application', 'bundle_id':'local.motive.h21capturefixture'}, -6)
        mic = add_audio('H21 prepared microphone', {'kind':'microphone', 'device_id':args.microphone_id}, -12)
        add_audio('H21 continuity reference', {'kind':'tone'}, -18)
        wait(lambda s: not s['audio_mixer']['issues'] and all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']), 'mixer ready')
        wait(lambda s:any(i['id']==window_source and i.get('capture_delivery')=='receiving' for i in s['sources']), 'Window receiving')
        if camera: wait(lambda s:any(i['id']==camera and i['frames']>10 for i in s['sources']), 'camera frames')
        profile = {'id':'h21-studio', 'encoder':'videotoolbox', 'bitrate_kbps':6000, 'rate_control':'cbr',
                   'keyframe_seconds':1, 'frame_reordering':False}
        client.call('upsert_output_profile', profile=profile)
        for target in ('recording','streaming'): client.call('select_output_profile', target=target, profile_id=profile['id'])
        with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
        client.call('configure_stream', endpoint={'transport':'rtmp','port':port})
        receiver = Receiver(str(app/'Contents/MacOS/ffmpeg'), out, port)
        client.call('preflight_output', target='recording')
        for target in ('recording','streaming'):
            slot = client.call('start_output', target=target)['state']['outputs'][target]; attempts[target] = slot['attempt_id']
            report['media'].append({'target':target, 'path':str(receiver.path) if target=='streaming' else slot['path']})
        state = wait(lambda s:all(s['outputs'][t]['phase']=='active' for t in attempts), 'outputs active')
        require(all(state['outputs'][t]['encoding']['selected_hardware'] for t in attempts), 'Hardware encoder required')
        report['initial_state'] = state
        # Bind the beginning of each real output to its final trace. Packet
        # counters alone do not certify delivery at the stop boundary.
        report['initial_traces'] = {t:client.call('output_diagnostics', target=t) for t in attempts}
        start = time.monotonic(); report['started_monotonic'] = start; event('session_started'); snapshot('start')
        interval = 20 if args.seconds==60 else 300
        next_switch = interval; return_at = None; index = 0; next_memory = next_checkpoint = 0
        with (out/'samples.jsonl').open('x') as samples:
            while time.monotonic()-start<args.seconds:
                before = time.monotonic(); state = client.state(); now = time.monotonic(); elapsed = now-start
                # Retain the exact observation that rejects a session, including
                # audio issue codes and identity metadata, before any assertion.
                samples.write(json.dumps({'host_bracket_s':[before,now], 'elapsed_s':elapsed, 'state':state})+'\n'); samples.flush()
                report['last_state'] = state; report['last_elapsed_s'] = elapsed
                require(not abort.exists(), 'External supervisor requested stop')
                require(fixture.poll() is None, 'Owned fixture exited')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()), 'Output interrupted')
                collected, blockers = classify_issues(state['audio_mixer']['issues'], mic,
                                                       args.collect_microphone_clipping)
                if collected:
                    report['audio_quality_status'] = 'FAIL'
                    if not report['audio_quality_warnings']:
                        report['audio_quality_warnings'].append({'elapsed_s':elapsed, 'issues':collected,
                                                                'state':state})
                        checkpoint()
                    report['last_audio_quality_warning_elapsed_s'] = elapsed
                require(not blockers, 'Audio input issue')
                require(state['audio_mixer']['runtime']['mix']['clipped_blocks']==0, 'Mixer clipping')
                require(not state['capture_recovery']['fallback_attempted'], 'Unplanned capture fallback')
                if elapsed>=next_memory:
                    report['memory'].append({'elapsed_s':elapsed, 'response':client.call('memory_diagnostics')}); next_memory += 5
                if return_at is not None and elapsed>=return_at:
                    client.call('set_audio_mute', input_id=mic, muted=False)
                    client.call('set_audio_gain', input_id=guest, gain_db=-6)
                    client.call('select_scene', scene_id=main_scene); event('return_main'); return_at = None
                elif elapsed>=next_switch and elapsed<args.seconds-10:
                    kind = 'fade' if index%2 else 'cut'
                    client.call('configure_transition', transition={'kind':kind, 'duration_ms':300 if kind=='fade' else 0})
                    destination = alternate
                    if args.scenario=='charlas': destination = display_scene if index%2 else app_scene
                    client.call('select_scene', scene_id=destination)
                    client.call('set_audio_mute', input_id=mic, muted=True)
                    client.call('set_audio_gain', input_id=guest, gain_db=-18)
                    fixture_command('focus '+str(index%2))
                    event('planned_transition_and_mix', transition=kind, scene_id=destination, mic_muted=True, guest_gain_db=-18)
                    return_at = elapsed+3; next_switch += interval; index += 1
                if elapsed>=next_checkpoint:
                    report['gpu'].append({'elapsed_s':elapsed,'response':sample_gpu()})
                    checkpoint(); next_checkpoint += 15
                time.sleep(1)
        report['observed_seconds'] = time.monotonic()-start; snapshot('end'); event('session_completed')
        # Close the captured presentation window once, exercising safe fallback with
        # unchanged outputs. The separate cover stays until Display is removed.
        if args.scenario=='charlas':
            client.call('configure_transition', transition={'kind':'cut','duration_ms':0})
            fixture_command('close 1')
            wait(lambda s:s['project']['graph']['active_scene']==safe and s['capture_recovery']['fallback_attempted'], 'safe fallback after close')
            event('closed_window_safe_fallback')
        else:
            client.call('configure_transition', transition={'kind':'cut','duration_ms':0}); client.call('select_scene', scene_id=safe)
        wait(lambda s:s['project']['graph']['active_scene']==safe and s['transition']['phase']=='completed', 'final safe scene')
        end = time.monotonic()+3
        while time.monotonic()<end:
            state=client.state(); require(all(state['outputs'][t]['phase']=='active' for t in attempts), 'Safe-scene output interrupted'); time.sleep(.2)
        client.call('stop_output_target', target='streaming'); wait(lambda s:not s['outputs']['streaming']['native_busy'], 'stream stop')
        require(client.state()['outputs']['recording']['phase']=='active', 'Independent stop failed')
        client.call('stop_output_target', target='recording'); wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()), 'record stop')
        report['final_traces'] = {t:client.call('output_diagnostics', target=t) for t in attempts}
        report['runtime_status'] = 'PASS'; report['status'] = 'PARTIAL'
        if report['audio_quality_status'] != 'FAIL': report['audio_quality_status'] = 'PASS'
    except Exception as error: report['error'] = repr(error)
    finally:
        safe_to_close = fixture is None
        if client:
            try:
                state=client.state()
                for target,attempt in attempts.items():
                    require(state['outputs'][target]['attempt_id']==attempt, 'Output identity changed during cleanup')
                    if state['outputs'][target]['native_busy']: client.call('stop_output_target',target=target)
                wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()), 'cleanup quiescence', 30)
                client.call('configure_transition', transition={'kind':'cut','duration_ms':0})
                if safe and client.state()['project']['graph']['active_scene']!=safe: client.call('select_scene',scene_id=safe)
                wait(lambda s:s['transition']['phase'] in ('idle','completed'), 'cleanup scene')
                for scene in scenes: client.call('remove_scene', scene_id=scene)
                for source in sources: client.call('remove_source', source_id=source)
                for ident in audio_ids: client.call('remove_audio_input', input_id=ident)
                safe_to_close = True
            except Exception as error: report['cleanup_errors'].append(repr(error))
            client.close()
        if fixture and fixture.poll() is None and safe_to_close:
            fixture.stdin.write('quit\n'); fixture.stdin.flush(); fixture.wait(timeout=8)
        report['fixture_exit'] = fixture.poll() if fixture else None
        if receiver: report['receiver_exit'] = receiver.close()
        if not safe_to_close: report['cleanup_errors'].append('Owned cover retained: capture cleanup not proven')
        checkpoint()
        for handle in handles: handle.close()
    print(json.dumps({'status':report['status'],'runtime_status':report.get('runtime_status'), 'error':report.get('error'), 'cleanup_errors':report['cleanup_errors']}))
    return int(report.get('runtime_status')!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__': raise SystemExit(main())
