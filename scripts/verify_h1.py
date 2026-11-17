#!/usr/bin/env python3
"""Real H1 integration. Requires Motive, FFmpeg and normal screen permission.
Optional --camera-id and --microphone-id explicitly opt into a local physical
capture test. Artifacts remain in ignored var/. No simulated device removal.
"""
import argparse, hashlib, json, math, os, pathlib, signal, struct, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EXE = VERIFY.client_executable
OUT = ROOT / 'var/evidence'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--camera-id')
parser.add_argument('--microphone-id')
args = parser.parse_args()
report = {'ok': False, 'checks': [], 'physical_hot_unplug': 'not tested; requires removable hardware'}
fixture_pid = None

def ctl(op, expect=True, **fields):
    proc = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **fields})], capture_output=True, text=True, timeout=12)
    value = json.loads(proc.stdout)
    assert value['ok'] == expect, value
    return value

def state():
    return ctl('status')['state']

def wait_for(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = state()
        if predicate(s): return s
        time.sleep(.2)
    raise AssertionError({'timeout_state': s})

def ready():
    return wait_for(lambda s: not s['issues'])

def idle():
    return wait_for(lambda s: s['output'] == 'idle')

def media(path, minimum=2):
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', path]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac', probe
    assert float(probe['format']['duration']) >= minimum, probe
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-f', 'null', '-'], capture_output=True, check=True)
    pcm = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'])
    samples = struct.unpack('<%df' % (len(pcm)//4), pcm)
    rms = math.sqrt(sum(x*x for x in samples)/len(samples))
    assert rms > 1e-6, ('Silent audio', rms)
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-ss', '1', '-i', path, '-frames:v', '1', '-vf', 'crop=960:400:0:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    nonblack = sum(max(raw[i:i+3]) > 40 for i in range(0, len(raw), 3))
    assert nonblack > 10000, ('No source content outside overlay', nonblack)
    return {'path':path, 'duration':probe['format']['duration'], 'video_frames':video['nb_read_frames'],
            'audio_rms':rms, 'nonblack_source_pixels':nonblack}

def launch_fixture():
    existing = {w['pid'] for w in ctl('devices')['devices']['windows'] if w['bundle_id'] == 'local.motive.fixture'}
    subprocess.run(['open', '-n', str(ROOT/'target/MotiveFixture.app')], check=True)
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        windows = ctl('devices')['devices']['windows']
        for w in windows:
            if w['bundle_id'] == 'local.motive.fixture' and w['pid'] not in existing:
                return w
        time.sleep(.2)
    raise AssertionError('Owned external fixture did not appear')

try:
    assert state()['output'] == 'idle', 'Stop the current output before testing.'
    devices = ctl('devices')['devices']
    assert devices['screen_permission'], 'Grant Motive screen permission in macOS first.'
    subprocess.run(['python3', str(ROOT/'scripts/window_fixture.py')], check=True, capture_output=True)
    ctl('select_source', window_id=None)
    ctl('select_audio', id='tone')
    ctl('set_variant', variant='horizontal')
    ctl('set_overlay', visible=True)
    fixture = launch_fixture(); fixture_pid = fixture['pid']
    selected = ctl('select_source', window_id=fixture['id'])['state']
    assert selected['window_id'] == fixture['id'] and fixture_pid != selected['pid']
    ready(); ctl('save_project')
    ctl('select_source', window_id=None)
    restored = ctl('load_project')['state']
    assert restored['window_id'] == fixture['id']
    ready()
    recording = ctl('start_recording')['state']
    assert ctl('select_source', expect=False, window_id=None)['error']['code'] == 'OUTPUT_BUSY'
    assert ctl('reconnect_sources', expect=False)['error']['code'] == 'OUTPUT_BUSY'
    time.sleep(3)
    # Kill only the controlled process this script just launched.
    os.kill(fixture_pid, signal.SIGTERM); fixture_pid = None
    lost = wait_for(lambda s: 'SOURCE_UNAVAILABLE' in s['issues'] and s['output'] == 'idle')
    assert lost['recovery_required'] and 'SOURCE_UNAVAILABLE' in lost['last_fault']
    assert lost['output_code'] == 0
    # Regression: audio acknowledgement must not clear an unrelated video fault.
    after_audio = ctl('select_audio', id='none')['state']
    assert after_audio['recovery_required'] and 'main' in after_audio['recovery_sources']
    ctl('select_audio', id='tone')
    report['audio_change_preserves_video_recovery'] = True
    assert ctl('start_recording', expect=False)['error']['code'] == 'SOURCE_UNAVAILABLE'
    assert ctl('reconnect_sources', expect=False)['error']['code'] == 'SOURCE_UNAVAILABLE'
    report['source_loss'] = {'state':lost, 'media':media(recording['output_path'])}
    replacement = launch_fixture(); fixture_pid = replacement['pid']
    assert replacement['id'] != fixture['id']
    assert state()['recovery_required'], 'A returned source must not silently resume output.'
    ctl('select_source', window_id=replacement['id']); ready()
    ctl('reconnect_sources'); ready()
    path = ctl('start_recording')['state']['output_path']; time.sleep(3)
    ctl('stop_output'); idle()
    report['recovered_window'] = media(path)
    report['checks'].extend(['external process window selection', 'v2 project resolves selected identity',
                            'source loss gracefully finalizes real MKV', 'missing source cannot record',
                            'explicit reselection and reconnect permit a new recording'])
    ctl('select_source', window_id=None); ctl('select_audio', id='none')
    if args.camera_id or args.microphone_id:
        assert args.camera_id and args.microphone_id, 'Provide both physical IDs.'
        ctl('select_camera', id=args.camera_id); ctl('select_audio', id=args.microphone_id)
        first = ready(); ctl('save_project')
        ctl('select_source', window_id=None); ctl('select_audio', id='none')
        ctl('load_project'); ready()
        ctl('reconnect_sources'); first = ready()
        path = ctl('start_recording')['state']['output_path']
        samples = []
        for i in range(8):
            if i in (2,4):
                subprocess.Popen(['afplay', '-v', '0.5', str(ROOT/'var/tone.wav')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1); samples.append(state())
        ctl('stop_output'); idle()
        assert all(not s['issues'] and s['output']=='recording' for s in samples)
        assert samples[-1]['stats']['audio_frames'] > samples[0]['stats']['audio_frames']
        report['physical'] = {'media':media(path, 7), 'before':first, 'samples':samples}
        report['checks'].extend(['physical camera and mic', 'physical project restore', 'explicit physical source reconnect'])
    report['ok'] = True
except BaseException as failure:
    report['error'] = repr(failure)
    raise
finally:
    try:
        ctl('stop_output'); idle(); ctl('select_source', window_id=None); ctl('select_audio', id='none')
    except Exception as cleanup_error:
        report['cleanup_error'] = repr(cleanup_error)
    if fixture_pid:
        try: os.kill(fixture_pid, signal.SIGTERM)
        except ProcessLookupError: pass
    app = VERIFY.app_executable
    report['app_sha256'] = hashlib.sha256(app.read_bytes()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'h1-acceptance.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('source_loss','physical')}, indent=2))
