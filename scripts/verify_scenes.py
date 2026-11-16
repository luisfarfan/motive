#!/usr/bin/env python3
"""Real scene acceptance through stdio MCP, with an owned AppKit window.

Requires the signed running app, FFmpeg, screen permission and --camera-id.
Physical camera use is explicit. No public transmission or project-file edits.
Artifacts (including physical media/device identifiers) stay in ignored var/.
Use --leave-open for read-only UI inspection; close the fixture afterwards.
"""
import argparse
import json
import os
import pathlib
import signal
import statistics
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = ROOT / 'target/debug/motive'
EVIDENCE = ROOT / 'var/evidence'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--camera-id', required=True)
parser.add_argument('--leave-open', action='store_true')
parser.add_argument('--seconds', type=int, default=15, choices=range(7, 301), metavar='7..300')
args = parser.parse_args()
report = {'ok': False, 'operations': [], 'checks': []}
fixture_pid = None
p = subprocess.Popen([str(EXE), 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def rpc(method, params=None):
    request = {'jsonrpc': '2.0', 'id': len(report['operations'])+1, 'method': method, 'params': params or {}}
    p.stdin.write(json.dumps(request)+'\n'); p.stdin.flush()
    result = json.loads(p.stdout.readline())
    report['operations'].append({'request': request, 'response': result})
    assert 'error' not in result, result
    return result['result']


def command(op, expect=True, **fields):
    result = rpc('tools/call', {'name': op, 'arguments': fields})
    value = json.loads(result['content'][0]['text'])
    assert value['ok'] == expect, value
    assert result['isError'] == (not expect), result
    return value


def state():
    return command('status')['state']


def wait_for(predicate, timeout=15):
    deadline = time.monotonic()+timeout
    last = None
    while time.monotonic() < deadline:
        last = state()
        if predicate(last): return last
        time.sleep(.25)
    raise AssertionError({'timeout_state': last})


def ready():
    return wait_for(lambda s: not s['issues'] and not s['recovery_required'])


def graph():
    return state()['project']['graph']


def transform(scene, layer, x, y, w, h, order, visible=True, variant='horizontal'):
    return command('set_transform', scene_id=scene, layer_id=layer, variant=variant,
                   transform={'x': x, 'y': y, 'width': w, 'height': h, 'order': order, 'visible': visible})['state']


def add_source(scene, name, spec):
    before = {s['id'] for s in graph()['sources']}
    g = command('add_source', scene_id=scene, name=name, source=spec)['state']['project']['graph']
    source = next(s['id'] for s in g['sources'] if s['id'] not in before)
    layer = next(l['id'] for s in g['scenes'] if s['id'] == scene for l in s['layers'] if l['source_id'] == source)
    return source, layer


def rgb(path, second, crop):
    return subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(second), '-i', str(path),
                                   '-frames:v', '1', '-vf', 'crop='+crop, '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])


def color_count(raw, color):
    return sum(all(abs(raw[i+c]-color[c]) < 32 for c in range(3)) for i in range(0, len(raw), 3))


def media(path, minimum):
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', path]))
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    a = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    assert (v['codec_name'], a['codec_name'], v['width'], v['height']) == ('h264', 'aac', 960, 540), info
    duration = float(info['format']['duration'])
    assert duration >= minimum and int(v['nb_read_frames']) >= minimum*29, info
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-f', 'null', '-'], capture_output=True, check=True)
    return {'path': path, 'duration': duration, 'frames': int(v['nb_read_frames'])}


def stop():
    command('stop_output')
    return wait_for(lambda s: s['output'] == 'idle')


try:
    deadline = time.monotonic()+10
    while not (ROOT/'var/run/motive.sock').exists():
        assert time.monotonic() < deadline, 'Open the signed Motive app before testing'
        time.sleep(.25)
    rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'scene-acceptance', 'version': '1'}})
    assert state()['output'] == 'idle'
    command('set_variant', variant='horizontal')
    command('select_source', window_id=None)
    command('select_audio', id='tone')
    command('set_overlay', visible=True)
    command('set_overlay_color', source_id='overlay', color=0x33e8b5)
    transform(graph()['active_scene'], 'overlay-layer', 32, 436, 320, 72, 1)
    subprocess.run(['python3', str(ROOT/'scripts/window_fixture.py')], check=True, capture_output=True)
    existing = {w['pid'] for w in command('devices')['devices']['windows'] if w['bundle_id'] == 'local.motive.fixture'}
    subprocess.run(['open', '-n', str(ROOT/'target/MotiveFixture.app')], check=True)
    deadline = time.monotonic()+10
    while True:
        fixtures = [w for w in command('devices')['devices']['windows'] if w['bundle_id'] == 'local.motive.fixture' and w['pid'] not in existing]
        if fixtures: break
        assert time.monotonic() < deadline, 'Owned fixture did not appear'
        time.sleep(.25)
    fixture = fixtures[0]; fixture_pid = fixture['pid']
    report['fixture_pid'] = fixture_pid
    command('select_source', window_id=fixture['id'])
    scene = graph()['active_scene']
    command('rename_scene', scene_id=scene, name='Window + camera · MCP')
    camera, camera_layer = add_source(scene, 'Webcam · secondary', {'kind': 'camera', 'device_id': args.camera_id})
    transform(scene, camera_layer, 640, 32, 288, 162, 2)
    first = ready()
    duplicate = command('add_source', expect=False, scene_id=scene, name='Duplicate camera',
                        source={'kind':'camera', 'device_id':args.camera_id})
    assert duplicate['error']['code']=='DEVICE_IN_USE'
    assert next(s for s in first['sources'] if s['id'] == camera)['frames'] > 0
    assert next(s for s in first['sources'] if s['id'] == 'main')['width'] > 0
    # Scene CRUD and reusing a source do not duplicate the hardware capture.
    other = command('create_scene', name='Alternate composition')['state']['project']['graph']['active_scene']
    command('add_layer', scene_id=other, source_id='main')
    command('select_scene', scene_id=scene)
    command('remove_scene', scene_id=other)
    assert command('remove_source', expect=False, source_id=camera)['error']['code'] == 'SOURCE_IN_USE'
    rev = state()['revision']
    bad = command('set_transform', expect=False, scene_id=scene, layer_id=camera_layer, variant='horizontal',
                  transform={'x': 0, 'y': 0, 'width': 0, 'height': 162, 'visible': True, 'order': 2})
    assert bad['error']['code'] == 'INVALID_TRANSFORM' and state()['revision'] == rev
    # Portrait edits must not move the landscape composition.
    horizontal = next(l for s in graph()['scenes'] if s['id']==scene for l in s['layers'] if l['id']==camera_layer)['layouts']['horizontal']
    transform(scene, camera_layer, 24, 200, 480, 270, 4, variant='vertical')
    assert next(l for s in graph()['scenes'] if s['id']==scene for l in s['layers'] if l['id']==camera_layer)['layouts']['horizontal'] == horizontal
    ready()
    path = command('start_recording')['state']['output_path']
    time.sleep(3)
    before = state()
    edited = transform(scene, camera_layer, 600, 48, 320, 180, 2)
    transform(scene, 'overlay-layer', 60, 420, 400, 90, 3)
    command('set_overlay_color', source_id='overlay', color=0xff6b5e)
    samples = []
    started = time.monotonic()
    while time.monotonic()-started < args.seconds-3:
        current = state()
        assert current['output']=='recording' and not current['issues'], current
        cpu, rss = subprocess.check_output(['ps','-p',str(current['pid']),'-o','%cpu=,rss='],text=True).split()
        samples.append({'elapsed':time.monotonic()-started, 'cpu_percent':float(cpu), 'rss_mib':int(rss)/1024,
                        'stats':current['stats']})
        time.sleep(1)
    after = state()
    assert after['output'] == 'recording' and not after['issues'], after
    a = next(s for s in before['sources'] if s['id']==camera)
    b = next(s for s in after['sources'] if s['id']==camera)
    assert b['frames'] > a['frames'] and b['frame_age_ms'] < 1000, (a, b)
    cli = json.loads(subprocess.check_output([str(EXE), 'ctl', '{"op":"status"}']))['state']
    assert cli['pid'] == after['pid'] and cli['revision'] == after['revision']
    stop()
    report['composition'] = media(path, args.seconds-1)
    report['samples'] = samples
    report['metrics'] = {'cpu_percent_median':statistics.median(s['cpu_percent'] for s in samples),
                         'cpu_percent_max':max(s['cpu_percent'] for s in samples),
                         'rss_mib_min':min(s['rss_mib'] for s in samples), 'rss_mib_max':max(s['rss_mib'] for s in samples),
                         'note':'Debug app process only; includes UI, capture and software encoding, excludes mux helper. Not a comparative benchmark.'}
    report['camera_clock'] = {'before': a, 'after': b}
    mint = color_count(rgb(path, 1, '8:72:32:436'), (51,232,181))
    coral = color_count(rgb(path, 5, '10:90:60:420'), (255,107,94))
    assert mint > 200 and coral > 350, (mint, coral)
    camera_pixels = rgb(path, 5, '300:160:610:58')
    varied = len(set(camera_pixels))
    assert varied > 40, ('Camera rectangle is empty', varied)
    report['recorded_pixels'] = {'mint_before': mint, 'coral_after': coral, 'camera_channel_values': varied}
    report['checks'].extend(['real external window + physical webcam simultaneously', 'MCP move/resize while recording; same camera counter',
                             'editable overlay color, size and position decoded from MKV', 'CLI/MCP shared PID and revision',
                             'scene CRUD, shared source, invalid transform rollback, independent portrait layout'])
    # Controlled overlapping overlays prove geometry, visibility and order in pixels.
    cover, cover_layer = add_source(scene, 'Controlled order probe', {'kind':'overlay', 'color':0x3388ff})
    transform(scene, cover_layer, 60, 420, 400, 90, 4)
    path2 = command('start_recording')['state']['output_path']; time.sleep(2)
    transform(scene, cover_layer, 60, 420, 400, 90, 0); time.sleep(2)
    stop(); media(path2, 3)
    blue = color_count(rgb(path2, 1, '10:90:60:420'), (51,136,255))
    red = color_count(rgb(path2, 3, '10:90:60:420'), (255,107,94))
    assert blue > 350 and red > 350, (blue, red)
    transform(scene, cover_layer, 60, 420, 400, 90, 4, visible=False)
    path3 = command('start_recording')['state']['output_path']; time.sleep(2)
    stop(); media(path3, 1)
    assert color_count(rgb(path3, 1, '10:90:60:420'), (255,107,94)) > 350
    command('remove_layer', scene_id=scene, layer_id=cover_layer)
    command('remove_source', source_id=cover)
    report['order_visibility'] = {'path':path2, 'hidden_path':path3, 'blue_top':blue, 'coral_top':red}
    report['checks'].append('recorded pixels prove layer order and hidden-layer exclusion')
    saved = command('save_project')['state']['project']
    old_pid = state()['pid']
    command('shutdown')
    deadline = time.monotonic()+15
    while (ROOT/'var/run/motive.sock').exists():
        assert time.monotonic() < deadline, 'Core did not close its socket'
        time.sleep(.25)
    while True:
        try: os.kill(old_pid, 0)
        except ProcessLookupError: break
        assert time.monotonic() < deadline, 'Native resources did not finish shutting down'
        time.sleep(.25)
    subprocess.run(['open', str(ROOT/'target/Motive.app')], check=True)
    deadline = time.monotonic()+15
    while not (ROOT/'var/run/motive.sock').exists():
        assert time.monotonic() < deadline, 'Studio did not restart'
        time.sleep(.25)
    restored = command('load_project')['state']
    assert restored['pid'] != old_pid and restored['project'] == saved
    # Stage Manager may hide the fixture when Motive is reopened. An explicit
    # normal activation of this owned test app lets ScreenCaptureKit deliver it.
    subprocess.run(['open', '-a', str(ROOT/'target/MotiveFixture.app')], check=True)
    ready()
    path4 = command('start_recording')['state']['output_path']; time.sleep(3)
    end = stop()
    report['restored'] = media(path4, 2)
    assert color_count(rgb(path4, 1, '10:90:60:420'), (255,107,94)) > 350
    report['checks'].append('save, graceful shutdown, new PID, load, identical stable IDs/layouts, valid new recording')
    report['final_state'] = end
    command('snapshot')
    (EVIDENCE/'scene-composition.png').write_bytes((EVIDENCE/'preview.png').read_bytes())
    report['ok'] = True
except BaseException as exc:
    report['error'] = repr(exc)
    raise
finally:
    if not args.leave_open or not report['ok']:
        try:
            stop()
            # Remove all physical/window layers through the core; retain owned overlays.
            g = graph()
            captured = {s['id'] for s in g['sources'] if s['spec']['kind'] in ('camera','window')}
            for s in g['scenes']:
                for l in s['layers']:
                    if l['source_id'] in captured: command('remove_layer', scene_id=s['id'], layer_id=l['id'])
            for source in captured: command('remove_source', source_id=source)
            command('select_source', window_id=None); command('select_audio', id='none')
        except Exception as cleanup_error: report['cleanup_error'] = repr(cleanup_error)
        if fixture_pid:
            try: os.kill(fixture_pid, signal.SIGTERM)
            except ProcessLookupError: pass
    p.stdin.close(); p.wait(timeout=8)
    (EVIDENCE/'scene-acceptance.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('operations','final_state','samples')}, indent=2))
