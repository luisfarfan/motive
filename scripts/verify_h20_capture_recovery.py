#!/usr/bin/env python3
"""Real Production recovery of an owned Window/Application to a safe scene.

No full-display capture, external endpoint, physical camera/mic or user stores.
This is a bounded smoke test, not a 60-minute personal-stream acceptance.
"""
import argparse
import array
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import time

from verify_h14_collection import Client, Receiver, ROOT, default_owner, digest, executable, lines, lock, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['window', 'application'], required=True)
    args = parser.parse_args()
    owner_lock = lock()
    out = args.output.absolute()
    require(out.is_relative_to(ROOT / 'var/evidence'), 'Private evidence path required')
    out.mkdir(parents=True, exist_ok=False)
    app = args.app.resolve(strict=True)
    binary = executable(app, 'local.motive.studio')
    fixture_app = ROOT / 'target/H14CollectionFixture.app'
    fixture_binary = executable(fixture_app, 'local.motive.collectionfixture')
    report = {'version': 1, 'status': 'BLOCKED', 'mode': args.mode, 'lock': owner_lock,
              'owner_sha256': digest(binary), 'fixture_sha256': digest(fixture_binary),
              'samples': [], 'media': [], 'cleanup_errors': [],
              'limits': ['No Display capture, multi-window app acceptance, focus comparison or long soak.',
                         'Internal tone is not a measured human audiovisual sync stimulus.',
                         'Decoded safe pattern and continuous AAC do not prove full terminal packet delivery.']}
    owner = fixture = receiver = client = None
    handles = []
    attempts = {}
    env = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
    env['PATH'] = '/usr/bin:/bin'

    def checkpoint(): save(out / 'report.json', report)

    def launch(path, arguments, stem):
        stdout, stderr = (out / (stem + '.jsonl')).open('x'), (out / (stem + '.stderr')).open('x')
        handles.extend([stdout, stderr])
        return subprocess.Popen([str(path), *arguments], cwd='/', env=env, stdout=stdout, stderr=stderr)

    def sample(label):
        state = client.state()
        report['samples'].append({'label': label, 'host_bracket': client.last_bracket,
                                  'state': state})
        checkpoint()
        return state

    def wait(predicate, label, seconds=12):
        deadline = time.monotonic() + seconds
        while True:
            state = sample(label)
            if predicate(state): return state
            require(time.monotonic() < deadline, label + ' timeout')
            time.sleep(.25)

    try:
        control_socket = Path.home() / 'Library/Application Support/local.motive.studio/run/motive.sock'
        require(not control_socket.exists(), 'Existing Production must be closed normally first')
        owner = launch(binary, [], 'owner')
        report['owner_pid'] = owner.pid
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                client = Client(app, owner.pid, out)
                default_owner(client.state())
                break
            except (OSError, ValueError):
                require(owner.poll() is None, 'Owner exited at startup')
                time.sleep(.1)
        else: raise ValueError('Owner startup timeout')
        fixture = launch(fixture_binary, ['--collection-arm', 'default'], 'fixture')
        report['fixture_pid'] = fixture.pid
        deadline = time.monotonic() + 10
        while True:
            own = [x for x in lines(out / 'fixture.jsonl') if x['event'] == 'window_state']
            if own and isinstance(own[-1].get('cg_own_window_metadata'), dict): break
            require(time.monotonic() < deadline and fixture.poll() is None, 'Fixture unavailable')
            time.sleep(.1)
        fixture_state = own[-1]
        require(fixture_state['pid'] == fixture.pid, 'Fixture identity mismatch')
        report['fixture_state'] = fixture_state
        # Scope is always this owned app/window. For Application choose the exact
        # display containing the observed own-window center, never a default.
        devices = client.call('devices')['devices']
        if args.mode == 'application':
            b = fixture_state['cg_own_window_metadata']['bounds']
            x, y = b['X'] + b['Width']/2, b['Y'] + b['Height']/2
            displays = [d for d in devices['displays'] if d['bounds']['x'] <= x < d['bounds']['x']+d['bounds']['width']
                        and d['bounds']['y'] <= y < d['bounds']['y']+d['bounds']['height']]
            require(len(displays) == 1, 'Owned window display must resolve uniquely')
            source = {'kind': 'application', 'bundle_id': 'local.motive.collectionfixture',
                      'display_uuid': displays[0]['display_uuid']}
            require(any(d['bundle_id'] == source['bundle_id'] and d['display_uuid'] == source['display_uuid']
                        for d in devices['applications']), 'Owned application absent from exact inventory')
            report['display'] = displays[0]
        else:
            source = {'kind': 'window', 'window_id': fixture_state['window_id']}
        report['source'] = source
        client.call('configure_video', video={'version': 1, 'resolution': 'full_hd1080', 'fps': 30, 'coordinate_space': 'design960'})
        client.call('set_overlay', visible=False)
        safe = client.state()['project']['graph']['active_scene']
        client.call('configure_capture_fallback', scene_id=safe)
        state = client.call('create_scene', name='H20 owned capture')['state']
        capture_scene = state['project']['graph']['active_scene']
        state = client.call('add_source', scene_id=capture_scene, name='H20 owned source', source=source)['state']
        source_id = next(s['id'] for s in state['project']['graph']['sources'] if s['name'] == 'H20 owned source')
        report.update(safe_scene=safe, capture_scene=capture_scene, source_id=source_id)
        state = client.call('add_audio_input', name='H20 owned tone', source={'kind': 'tone'})['state']
        tone = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name'] == 'H20 owned tone')
        client.call('set_audio_gain', input_id=tone, gain_db=-12)
        profile = {'id': 'h20-capture-safe', 'encoder': 'videotoolbox', 'bitrate_kbps': 4000,
                   'rate_control': 'cbr', 'keyframe_seconds': 1, 'frame_reordering': False}
        client.call('upsert_output_profile', profile=profile)
        for target in ('recording', 'streaming'): client.call('select_output_profile', target=target, profile_id=profile['id'])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        client.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
        wait(lambda s: all(x.get('ok') for x in [client.call('preflight_output', target='recording', allow_error=True)]), 'preflight')
        receiver = Receiver(str(app / 'Contents/MacOS/ffmpeg'), out, port)
        for target in ('recording', 'streaming'):
            state = client.call('start_output', target=target)['state']
            slot = state['outputs'][target]; attempts[target] = slot['attempt_id']
            report['media'].append({'target': target, 'path': str(receiver.path) if target == 'streaming' else slot['path']})
        wait(lambda s: all(s['outputs'][t]['phase'] == 'active' for t in attempts), 'outputs_active')
        baseline = sample('before_source_loss')
        report['instances_before'] = baseline['transition']['source_instances_created']
        for _ in range(16): sample('capture'); time.sleep(.25)
        require(client.state()['project']['graph']['active_scene'] == capture_scene,
                'Spontaneous fallback occurred before controlled source loss; preserve and investigate')
        report['loss_requested_host_s'] = time.monotonic()
        fixture.terminate(); report['fixture_exit'] = fixture.wait(timeout=8)
        settled = wait(lambda s: s['project']['graph']['active_scene'] == safe and s['transition']['phase'] == 'completed', 'safe_scene')
        report['safe_observed_host_s'] = time.monotonic()
        require(settled['capture_recovery']['fallback_attempted'], 'Automatic safe cut not observed')
        require(settled['transition']['source_instances_created'] == report['instances_before'], 'Fallback recreated a native source')
        for _ in range(20):
            state = sample('safe_continuity')
            require(all(state['outputs'][t]['phase'] == 'active' and state['outputs'][t]['attempt_id'] == attempts[t]
                        for t in attempts), 'Output restarted or stopped during safe fallback')
            require(state['audio_mixer']['store']['inputs'] == baseline['audio_mixer']['store']['inputs'], 'Audio configuration changed')
            time.sleep(.25)
        client.call('stop_output_target', target='streaming')
        wait(lambda s: not s['outputs']['streaming']['native_busy'], 'independent_stream_stop')
        require(client.state()['outputs']['recording']['phase'] == 'active', 'Stream stop disturbed recording')
        for _ in range(8): sample('recording_only'); time.sleep(.25)
        client.call('stop_output_target', target='recording')
        wait(lambda s: all(not s['outputs'][t]['native_busy'] for t in attempts), 'outputs_quiescent')
        report['runtime_status'] = 'PASS'
        report['status'] = 'PARTIAL'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        report['status'] = 'FAIL' if attempts else 'BLOCKED'
    finally:
        if client and owner and owner.poll() is None:
            try:
                state = client.state()
                for target, attempt in attempts.items():
                    slot = state['outputs'][target]
                    require(slot['attempt_id'] == attempt, 'Output ownership changed; cleanup withheld')
                    if slot['native_busy']: client.call('stop_output_target', target=target)
                wait(lambda s: all(not o['native_busy'] for o in s['outputs'].values()), 'cleanup_quiescent', 25)
                client.call('request_shutdown'); owner.wait(timeout=25)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                report['cleanup_errors'].append(str(error))
        if fixture and fixture.poll() is None and owner and owner.poll() is not None:
            fixture.terminate(); fixture.wait(timeout=8)
        if receiver:
            try:
                report['receiver_exit'] = receiver.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                report['receiver_exit'] = receiver.close(); report['receiver_forced'] = True
        report['owner_exit'] = owner.poll() if owner else None
        report['fixture_exit'] = fixture.poll() if fixture else None
        checkpoint()
        for handle in handles: handle.close()
    # Analysis is performed only after all owned native capture processes exit.
    if report.get('runtime_status') == 'PASS' and not report['cleanup_errors'] and report['owner_exit'] == 0:
        for medium in report['media']:
            try:
                def ff(arguments):
                    result = subprocess.run([str(app / 'Contents/MacOS/ffmpeg'), '-nostdin', '-v', 'error', '-threads', '2', *arguments], capture_output=True, timeout=90)
                    require(result.returncode == 0 and not result.stderr, 'Decode failed: ' + result.stderr.decode()[:300])
                    return result.stdout
                path = medium['path']
                ff(['-i', path, '-f', 'null', '-'])
                early = ff(['-ss', '2', '-i', path, '-an', '-frames:v', '1', '-vf', 'scale=192:108,format=rgb24', '-f', 'rawvideo', '-'])
                blue = sum(max(abs(a-b) for a,b in zip(early[i:i+3], (18,41,61))) <= 8 for i in range(0,len(early)-2,3))
                require(len(early) == 192*108*3 and blue > 30, 'Owned fixture pixels absent before source loss')
                raw = ff(['-sseof', '-2', '-i', path, '-an', '-frames:v', '1', '-vf', 'scale=96:54,format=rgb24', '-f', 'rawvideo', '-'])
                require(len(raw) == 96*54*3, 'Final decoded frame absent')
                samples = [list(raw[(5*96+x)*3:(5*96+x)*3+3]) for x in (15, 48, 80)]
                expected = ((33, 156, 135), (59, 92, 181), (199, 87, 61))
                require(all(max(abs(a-b) for a,b in zip(actual, target)) <= 25 for actual,target in zip(samples,expected)), 'Decoded safe pattern differs')
                pcm = array.array('f', ff(['-i', path, '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-']))
                levels = [math.sqrt(sum(v*v for v in pcm[i:i+4800])/4800) for i in range(4800, len(pcm)-9600, 4800)]
                require(levels and min(levels) > .0001 and max(abs(v) for v in pcm) < .999, 'Tone missing or clipped')
                packets = subprocess.run([str(app / 'Contents/MacOS/ffprobe'), '-v', 'error', '-show_packets',
                    '-show_entries', 'packet=codec_type,pts_time', '-of', 'json', path], capture_output=True, timeout=90)
                require(packets.returncode == 0 and not packets.stderr, 'Packet probe failed')
                timestamps = json.loads(packets.stdout)['packets']
                gaps = {}
                for kind, bound in (('video', .05), ('audio', .023)):
                    pts = [float(p['pts_time']) for p in timestamps if p['codec_type'] == kind]
                    delta = [b-a for a,b in zip(pts,pts[1:])]
                    require(delta and min(delta)>0 and max(delta)<=bound, kind+' timeline discontinuity')
                    gaps[kind] = max(delta)
                medium.update(status='PASS', sha256=digest(Path(path)), safe_pattern_rgb=samples,
                              owned_fixture_blue_pixels=blue, max_pts_gap_s=gaps,
                              audio_rms_min=min(levels), audio_rms_max=max(levels), decoded_pcm_samples=len(pcm))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                medium.update(status='FAIL', error=str(error))
        report['status'] = 'PASS' if all(m.get('status') == 'PASS' for m in report['media']) and len(report['media']) == 2 else 'FAIL'
        checkpoint()
    print(json.dumps({'output': str(out), 'status': report['status'], 'error': report.get('error'), 'cleanup_errors': report['cleanup_errors']}))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
