#!/usr/bin/env python3
"""Real H11 runtime acceptance, split into repeatable independent stages.

Parent must own the physical-test lock and start the signed, idle app. This
script never starts/rebuilds/signs Motive, opens devices or streams externally.
Examples: --stage animations --transport recording; --stage widgets --transport
rtmp; --stage presets --preset starting_soon --variant vertical. With no stage,
all three run; transport defaults to recording. --transport both repeats runtime
stages over recording and loopback RTMP. Presets always use local recordings.

Every stage keeps its report, source definitions, decoded frames and recordings
on failure. Only IDs created by that stage are removed. save_project is tested
by presets; its original disk bytes/mode are restored after the test. No app
shutdown/restart, asset recovery or global environment changes are performed.
Install the test-only dependency in a local venv from requirements-h11.txt.
"""
import argparse
import bisect
import copy
import functools
import hashlib
import json
import math
import os
import pathlib
import socket
import statistics
import struct
import subprocess
import time

from PIL import Image, ImageChops
from h7_support import Client, EVIDENCE, ROOT, EXE, process_sample
from verify_h10_audio import tonal_amplitude
from verify_h11_visuals import png, shape_definition, sources

BG = (16, 32, 64)
BG_B = (96, 24, 32)
GREEN = (32, 224, 96)
SYNC_BEFORE = (224, 32, 224)
SYNC_AFTER = (32, 224, 224)
TERMINAL = ('completed', 'cancelled', 'failed')


def rgb(color):
    return (color[0] << 16) | (color[1] << 8) | color[2]


def graph(state):
    return state['project']['graph']


def scene(state, identifier):
    return next(s for s in graph(state)['scenes'] if s['id'] == identifier)


def layer_for(state, scene_id, source_id):
    return next(l for l in scene(state, scene_id)['layers'] if l['source_id'] == source_id)


def job(state, identifier):
    return next(j for j in state['overlays']['runtime']['animations']['jobs'] if j['operation_id'] == identifier)


def cli(op, expect=True, **fields):
    result = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **fields})],
                            capture_output=True, text=True, timeout=12)
    value = json.loads(result.stdout)
    assert value['ok'] == expect, value
    return value


@functools.lru_cache(maxsize=16)
def video_pts(path):
    frames = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v',
                        '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))['frames']
    return tuple(float(frame['best_effort_timestamp_time']) for frame in frames)


def decode_frame(path, second, dimensions, out=None):
    # second is an absolute presentation timestamp, never FFmpeg's normalized
    # seek offset (FLV can have different positive audio/video start times).
    points = video_pts(path)
    index = bisect.bisect_left(points, second)
    assert index < len(points), ('Frame PTS outside media', second, points[-1])
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                                   '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', '-fps_mode', 'passthrough',
                                   '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    width, height = dimensions
    assert len(raw) == width * height * 3, (path, second, len(raw))
    if out:
        png(out, width, height, raw, channels=3)
    return Image.frombytes('RGB', dimensions, raw)


def mean(image, box):
    values = list(image.crop(box).getdata())
    return [statistics.mean(v[c] for v in values) for c in range(3)]


def near(value, target, tolerance=20):
    return max(abs(v-t) for v, t in zip(value, target)) <= tolerance


def calibrate_timeline(path, dimensions, marks, report):
    """One independent marker establishes the origin; its inverse checks drift.

    A command's actual mutation is bounded by request/response monotonic times.
    Its presentation is bounded by the last old and first new decoded frame.
    These intervals bound the origin without fitting any tested animation.
    """
    points = video_pts(path)
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                '-vf', f'crop=16:16:{dimensions[0]-40}:20,scale=1:1', '-fps_mode', 'passthrough',
                '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    assert len(raw) == len(points)*3
    colors = [list(raw[i:i+3]) for i in range(0, len(raw), 3)]
    runs = []
    for index, color in enumerate(colors):
        label = 'before' if near(color, SYNC_BEFORE, 18) else 'after' if near(color, SYNC_AFTER, 18) else 'invalid'
        if not runs or label != runs[-1]['label']:
            runs.append({'label': label, 'first_frame': index, 'frames': 0, 'first_pts': points[index]})
        runs[-1]['frames'] += 1
    report.update({'method': 'independent native color marker; first edge fixes one origin; inverse only checks drift',
                   'commands': marks, 'runs': runs, 'marker_rgb_by_frame': colors,
                   'video_pts': points, 'source_id': marks['start']['source_id']})
    assert [run['label'] for run in runs] == ['before', 'after', 'before'], runs
    assert min(run['frames'] for run in runs) >= 3, runs
    bounds = []
    for name, run in zip(('start', 'end'), runs[1:]):
        index = run['first_frame']
        command = marks[name]
        low = points[index-1]-command['response_seconds']
        high = points[index]-command['request_seconds']
        assert low <= high
        bounds.append({'name': name, 'low': low, 'high': high,
                       'midpoint': (low+high)/2, 'uncertainty_ms': (high-low)*500,
                       'last_old_pts': points[index-1], 'first_new_pts': points[index]})
    report['origin_bounds'] = bounds
    # An overly slow control call cannot calibrate a 300 ms widget fade well.
    assert all(bound['uncertainty_ms'] <= 75 for bound in bounds), bounds
    origin = bounds[0]['midpoint']
    report['offset_seconds'] = origin
    report['inverse_midpoint_drift_ms'] = (bounds[1]['midpoint']-origin)*1000
    # Allow only 1 ms timestamp quantization. The end marker never changes the
    # origin chosen from the start marker, even when the intervals overlap.
    assert max(bound['low'] for bound in bounds) <= min(bound['high'] for bound in bounds)+.001, ('Timeline origin drifted', bounds)
    return origin


def green_box(image):
    # Downsampling is only analysis of a decoded real frame, not a render path.
    small = image.resize((image.width // 2, image.height // 2), Image.Resampling.NEAREST)
    positions = [(i % small.width, i // small.width) for i, p in enumerate(small.getdata())
                 if p[1] > 140 and p[1] > p[0] + 70 and p[1] > p[2] + 65]
    if not positions:
        return None
    xs, ys = zip(*positions)
    return [min(xs)*2, min(ys)*2, (max(xs)-min(xs)+1)*2, (max(ys)-min(ys)+1)*2]


def white_mask(image, box, tight=True):
    crop = image.crop(box)
    mask = Image.new('L', crop.size)
    mask.putdata([255 if min(p) > 185 and max(p)-min(p) < 55 else 0 for p in crop.getdata()])
    bounds = mask.getbbox()
    assert bounds, ('No white glyph pixels', box)
    return mask.crop(bounds) if tight else mask


def mask_error(left, right, same_glyphs=True):
    # Normalize only the tightly cropped raster glyph bounds; compare actual
    # libobs-rendered 00:03/00:00 against independently controlled native text.
    if same_glyphs:
        assert abs(left.width-right.width) <= 4 and abs(left.height-right.height) <= 4, (left.size, right.size)
    right = right.resize(left.size, Image.Resampling.NEAREST)
    union = sum(v != 0 for v in ImageChops.lighter(left, right).getdata())
    difference = sum(v != 0 for v in ImageChops.difference(left, right).getdata())
    return difference / union


def media(path, elapsed, dimensions):
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) == ('h264', *dimensions, '30/1'), video
    assert (audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2), audio
    assert int(video['nb_read_frames']) >= (elapsed-.3)*28, video
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    assert not decoded.stderr, decoded.stderr
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'])
    samples = struct.unpack('<%df' % (len(raw)//4), raw)
    levels = [math.sqrt(sum(v*v for v in samples[i:i+4800])/4800)
              for i in range(0, len(samples)-4799, 4800)][1:-1]
    assert levels and min(levels) > .01 and max(levels) < .35, levels
    peak = max(abs(v) for v in samples)
    assert peak < .5, peak
    amplitude = tonal_amplitude(samples[4800:-4800], 440)
    assert amplitude > .01, amplitude
    packets = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_packets', '-show_entries', 'packet=codec_type,pts_time,dts_time', '-of', 'json', str(path)]))['packets']
    frames = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))['frames']
    timestamps = {}
    for kind in ('audio', 'video'):
        typed = [p for p in packets if p['codec_type'] == kind]
        dts = [float(p['dts_time']) for p in typed if 'dts_time' in p]
        assert all(b > a for a, b in zip(dts, dts[1:])), kind
        pts = ([float(p['pts_time']) for p in typed] if kind == 'audio'
               else [float(f['best_effort_timestamp_time']) for f in frames])
        gaps = [b-a for a, b in zip(pts, pts[1:])]
        assert min(gaps) > 0
        checked = gaps if kind == 'audio' else gaps[:-4]
        assert max(checked) <= (.023 if kind == 'audio' else .035), (kind, max(checked))
        timestamps[kind] = {'points': len(pts), 'packets_without_dts': len(typed)-len(dts),
                            'max_gap_ms': max(gaps)*1000, 'max_checked_gap_ms': max(checked)*1000}
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'probe': probe,
            'timestamps': timestamps, 'audio': {'window_ms': 100, 'rms_by_window': levels,
            'rms_min': min(levels), 'rms_max': max(levels), 'peak': peak, 'tone_440_amplitude': amplitude}}


class Harness:
    def __init__(self, directory, report):
        self.directory, self.report = directory, report
        self.c, self.initial = None, None
        self.scenes, self.sources, self.tone = [], [], None
        self.sessions, self.receivers = [], []
        self.output_owned, self.changed = False, False
        self.disk_snapshot = None
        self.disk_touched = False
        self.sync_marker = None

    def open(self):
        self.c = Client()
        self.initial = self.c.state()
        self.report['initial'] = self.initial
        assert self.initial['output'] == 'idle'
        assert not self.initial['audio_mixer']['store']['inputs'], 'Requires an empty controlled audio mixer'
        assert all(s['spec']['kind'] in ('pattern', 'overlay') for s in graph(self.initial)['sources'])
        assert not self.initial['overlays']['runtime']['animations']['busy']
        self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.changed = True
        self.c.call('set_variant', variant='horizontal')
        state = self.c.call('add_audio_input', name='H11 runtime controlled tone', source={'kind': 'tone'})['state']
        self.tone = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=-6)
        self.c.wait(lambda s: any(i['id'] == self.tone and i['phase'] == 'ready' for i in s['audio_mixer']['runtime']['inputs']))

    def detach(self):
        assert self.c
        self.sessions.append(self.c.ops)
        self.c.close()
        self.c = None

    def reconnect(self):
        assert self.c is None
        self.c = Client()

    def new_scene(self, name):
        identifier = self.c.call('create_scene', name=name)['state']['project']['graph']['active_scene']
        self.scenes.append(identifier)
        if self.sync_marker is None:
            self.sync_marker, marker_layer = self.add(identifier, 'Native timeline calibration',
                    shape_definition('rectangle', 32, 32, rgb(SYNC_BEFORE)), (912, 12, 32, 32), 31)
        else:
            response = self.c.call('add_layer', scene_id=identifier, source_id=self.sync_marker)
            marker_layer = layer_for(response['state'], identifier, self.sync_marker)['id']
            self.transform(identifier, marker_layer, (912, 12, 32, 32), 31)
        self.transform(identifier, marker_layer, (492, 12, 32, 32), 31, variant='vertical')
        return identifier

    def transform(self, scene_id, layer_id, rect, order, variant='horizontal'):
        x, y, width, height = rect
        return self.c.call('set_transform', scene_id=scene_id, layer_id=layer_id, variant=variant,
                           transform=dict(x=x, y=y, width=width, height=height, visible=True, order=order))

    def add(self, scene_id, name, definition, rect, order=1):
        response = self.c.call('create_overlay', scene_id=scene_id, name=name, definition=definition)
        source_id = response['result']['source_id']
        self.sources.append(source_id)
        layer = layer_for(response['state'], scene_id, source_id)
        self.transform(scene_id, layer['id'], rect, order)
        return source_id, layer['id']

    def background(self, scene_id, color=BG):
        source, layer = self.add(scene_id, 'Controlled background', shape_definition('rectangle', 960, 540, rgb(color)), (0, 0, 960, 540), 0)
        self.transform(scene_id, layer, (0, 0, 540, 960), 0, variant='vertical')
        return source, layer

    def preset(self, scene_id, preset, parameters):
        response = self.c.call('instantiate_overlay_preset', scene_id=scene_id, preset=preset, parameters=parameters)
        ids = response['result']['source_ids']
        self.sources.extend(ids)
        assert response['result']['preset_version'] == 1 and len(ids) == len(set(ids))
        return ids

    def select(self, identifier):
        self.c.call('select_scene', scene_id=identifier)
        return self.c.wait(lambda s: graph(s)['active_scene'] == identifier and s['transition']['phase'] not in ('preparing', 'running'))

    def ready(self):
        return self.c.wait(lambda s: not s['issues'] and not s['recovery_required']
                           and all(identifier in sources(s) and not sources(s)[identifier]['health'] for identifier in self.sources))

    def listen(self, label):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        path = self.directory / (label + '.flv')
        with (self.directory / (label + '-receiver.log')).open('w') as log:
            process = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'info', '-listen', '1', '-i',
                                        f'rtmp://127.0.0.1:{port}/live/motive', '-c', 'copy', str(path)],
                                       stdout=subprocess.DEVNULL, stderr=log)
        self.receivers.append(process)
        for _ in range(80):
            assert process.poll() is None, 'Local receiver exited before listening'
            if subprocess.run(['lsof', '-a', '-p', str(process.pid), '-iTCP:'+str(port), '-sTCP:LISTEN'], capture_output=True).returncode == 0:
                return process, path, port
            time.sleep(.1)
        raise AssertionError('Loopback receiver did not listen')

    def snapshot_disk(self):
        path = ROOT / 'var/project.json'
        assert not path.is_symlink()
        self.disk_snapshot = (path, path.read_bytes() if path.exists() else None,
                              path.stat().st_mode & 0o777 if path.exists() else 0o600)
        if self.disk_snapshot[1] is not None:
            (self.directory / 'project-before.json').write_bytes(self.disk_snapshot[1])

    def close(self):
        errors = []
        def attempt(action):
            try:
                return action()
            except Exception as failure:
                errors.append(repr(failure))
        if self.changed and self.c is None:
            attempt(self.reconnect)
        if self.c:
            if self.changed:
                def cancel():
                    state = self.c.state()
                    for active in state['overlays']['runtime']['animations']['jobs']:
                        if active['phase'] in ('running', 'cancel_pending'):
                            self.c.call('cancel_overlay_animation', operation_id=active['operation_id'])
                    self.c.wait(lambda s: not s['overlays']['runtime']['animations']['busy'])
                    state = self.c.state()
                    if state['transition']['phase'] in ('preparing', 'running'):
                        self.c.call('cancel_transition', operation_id=state['transition']['operation_id'])
                attempt(cancel)
                if self.output_owned:
                    attempt(self.c.stop)
                attempt(lambda: self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0}))
                attempt(lambda: self.select(graph(self.initial)['active_scene']))
                for identifier in reversed(self.scenes):
                    attempt(lambda: self.c.call('remove_scene', scene_id=identifier))
                for identifier in reversed(self.sources):
                    attempt(lambda: self.c.call('remove_source', source_id=identifier))
                if self.tone:
                    attempt(lambda: self.c.call('remove_audio_input', input_id=self.tone))
                attempt(lambda: self.c.call('set_variant', variant=self.initial['project']['variant']))
                attempt(lambda: self.c.call('configure_transition', transition=self.initial['transition_configuration']))
                endpoint = self.initial['output_configuration']['endpoint']
                if endpoint is not None:
                    attempt(lambda: self.c.call('configure_stream', endpoint=endpoint))
                elif any(output['transport'] == 'rtmp' for output in self.report.get('outputs', [])):
                    # H8 has no clear-endpoint command. The owned loopback
                    # selection remains until the parent's next fresh launch.
                    self.report['cleanup_note'] = 'Owned loopback endpoint retained until app restart; no stream remains active.'
                self.report['after_cleanup'] = attempt(self.c.state)
            self.sessions.append(self.c.ops)
            attempt(self.c.close)
            self.c = None
        for process in self.receivers:
            if process.poll() is None:
                attempt(process.terminate)
                attempt(lambda: process.wait(timeout=10))
        if self.disk_touched and self.disk_snapshot:
            def restore_file():
                path, contents, mode = self.disk_snapshot
                if contents is None:
                    path.unlink(missing_ok=True)
                else:
                    temporary = self.directory / 'project-restoration.tmp'
                    temporary.write_bytes(contents)
                    temporary.chmod(mode)
                    os.replace(temporary, path)
                self.report['project_disk_restored'] = True
            attempt(restore_file)
        self.report['mcp_sessions'] = self.sessions
        if errors:
            self.report['cleanup_errors'] = errors
            self.report['ok'] = False


class Output:
    def __init__(self, harness, label, transport):
        self.h, self.transport = harness, transport
        self.report = {'label': label, 'transport': transport, 'events': [], 'samples': []}
        harness.report.setdefault('outputs', []).append(self.report)
        self.receiver, self.path = None, None
        if transport == 'rtmp':
            self.receiver, self.path, port = harness.listen(label)
            harness.c.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
        harness.c.call('update_overlay', source_id=harness.sync_marker,
                       definition=shape_definition('rectangle', 32, 32, rgb(SYNC_BEFORE)))
        harness.ready()
        self.before_start = time.monotonic()
        harness.c.call('start_recording' if transport == 'recording' else 'start_stream')
        harness.output_owned = True
        expected = 'recording' if transport == 'recording' else 'streaming'
        self.started = harness.c.wait(lambda s: s['output'] == expected)
        self.start = time.monotonic()
        self.path = self.path or pathlib.Path(self.started['output_path'])
        self.dimensions = (self.started['width'], self.started['height'])
        self.last_time, self.last_frames = self.start, self.started['stats']['encoded_frames']
        self.last_cpu, _ = process_sample(self.started['pid'])
        self.report.update({'started': self.started, 'path': str(self.path), 'start_ack_seconds': self.start-self.before_start,
                            'timeline_note': 'Control offsets are mapped once to absolute video PTS by an independent marker; inverse marker verifies drift.'})
        self.calibration_marks = {}
        self.hold(.35)
        self.calibration_mark('start', SYNC_AFTER)
        self.hold(.35)

    def calibration_mark(self, name, color):
        marker = {'source_id': self.h.sync_marker, 'color': color,
                  'request_seconds': time.monotonic()-self.start}
        self.calibration_marks[name] = marker
        self.h.c.call('update_overlay', source_id=self.h.sync_marker,
                      definition=shape_definition('rectangle', 32, 32, rgb(color)))
        marker['response_seconds'] = time.monotonic()-self.start
        self.report['calibration_commands'] = self.calibration_marks

    def mark(self, label, **fields):
        event = {'label': label, 'seconds': time.monotonic()-self.start, **fields}
        self.report['events'].append(event)
        return event

    def sample(self):
        state = self.h.c.state()
        now = time.monotonic()
        cpu, rss = process_sample(state['pid'])
        base = self.started
        assert state['pid'] == base['pid'] and state['output'] == base['output'] and state['output_path'] == base['output_path']
        assert state['output_configuration'] == base['output_configuration']
        assert state['encoding'] == base['encoding']
        assert not state['issues'] and not state['recovery_required'], state['issues']
        assert state['stats']['encoded_frames'] >= self.last_frames
        assert state['transition']['source_instances_created'] == base['transition']['source_instances_created']
        assert state['transition']['scenes_built'] == base['transition']['scenes_built']
        assert state['audio_mixer']['store'] == base['audio_mixer']['store']
        assert state['audio_mixer']['runtime']['instances_created'] == base['audio_mixer']['runtime']['instances_created']
        assert state['audio_mixer']['runtime']['mix']['clipped_blocks'] == base['audio_mixer']['runtime']['mix']['clipped_blocks']
        before, current = sources(base), sources(state)
        for identifier in self.h.sources:
            assert current[identifier]['instance_id'] == before[identifier]['instance_id']
            assert current[identifier]['child_instances_created'] == before[identifier]['child_instances_created']
            assert not current[identifier]['health'], current[identifier]
        self.report['samples'].append({'seconds': now-self.start, 'cpu_percent': 100*(cpu-self.last_cpu)/(now-self.last_time),
                                        'rss_mib': rss, 'state': state})
        self.last_time, self.last_cpu, self.last_frames = now, cpu, state['stats']['encoded_frames']
        return state

    def hold(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            time.sleep(min(.12, max(.001, end-time.monotonic())))
            self.sample()

    def until(self, predicate, timeout=8):
        end = time.monotonic()+timeout
        while True:
            state = self.sample()
            if predicate(state):
                return state
            assert time.monotonic() < end, state
            time.sleep(.08)

    def stop(self):
        self.calibration_mark('end', SYNC_BEFORE)
        self.hold(.35)
        self.report['last'] = self.sample()
        self.report['elapsed'] = time.monotonic()-self.start
        self.report['stop'] = self.h.c.stop()
        assert self.report['stop']['end']['output'] == 'idle' and self.report['stop']['end']['output_code'] == 0
        self.h.output_owned = False
        if self.receiver:
            self.report['receiver_exit'] = self.receiver.wait(timeout=12)
            # FFmpeg's RTMP listener can report EOF/EIO after a successful remote
            # close. Full decode/timestamps below decide delivery, not exit code.
        self.report['media'] = media(self.path, self.report['elapsed'], self.dimensions)
        self.report['timeline_calibration'] = {}
        self.origin = calibrate_timeline(self.path, self.dimensions, self.calibration_marks,
                                         self.report['timeline_calibration'])
        samples = self.report['samples']
        self.report['performance'] = {'cpu_median': statistics.median(s['cpu_percent'] for s in samples),
                                      'rss_min_mib': min(s['rss_mib'] for s in samples),
                                      'rss_max_mib': max(s['rss_mib'] for s in samples),
                                      'lagged_delta': self.report['last']['stats']['lagged_frames']-self.started['stats']['lagged_frames'],
                                      'note': 'Debug process; observer cost included; native counters retained, no benchmark claim.'}
        assert self.report['last']['stats']['output_dropped_frames'] == 0

    def frame(self, name, second):
        target = second+self.origin
        points = video_pts(self.path)
        index = bisect.bisect_left(points, target)
        self.report.setdefault('frame_probes', []).append({'name': name, 'control_seconds': second,
                         'target_pts': target, 'index': index, 'actual_pts': points[index] if index < len(points) else None})
        return decode_frame(self.path, target, self.dimensions, self.h.directory/(self.report['label']+'-'+name+'.png'))


def animation_definition(kind, duration=1500, distance=160, scale=.35, easing='linear'):
    return {'kind': kind, 'duration_ms': duration, 'easing': easing, 'distance': distance, 'scale_from': scale}


def animations(h, transports, _args):
    first = h.new_scene('H11 animations A')
    h.background(first)
    marker, layer = h.add(first, 'Animated green rectangle', shape_definition('rectangle', 160, 100, rgb(GREEN)), (400, 220, 160, 100))
    second = h.new_scene('H11 shared source B')
    h.background(second, BG_B)
    response = h.c.call('add_layer', scene_id=second, source_id=marker)
    second_layer = layer_for(response['state'], second, marker)['id']
    h.transform(second, second_layer, (400, 220, 160, 100), 1)
    h.select(first)
    h.ready()
    denied = h.c.call('animate_overlay', expect=False, scene_id=first, layer_id=layer,
                      animation=animation_definition('fade_in', easing='ease_in'))
    assert denied['error']['code'] == 'UNSUPPORTED_FADE_EASING', denied
    h.report['invalid_easing'] = denied
    shared = cli('overlay_state')
    assert shared['pid'] == h.initial['pid']
    assert sum(s['id'] == marker for s in shared['result']['definitions']) == 1
    h.report['shared_source'] = {'source_id': marker, 'layers': [layer, second_layer], 'cli': shared}
    for transport in transports:
        h.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        h.select(first)
        output = Output(h, 'animations-'+transport, transport)
        output.hold(.8)
        measured = []
        for index, kind in enumerate(('fade_out', 'fade_in', 'slide_out', 'slide_in', 'scale_out', 'scale_in')):
            definition = animation_definition(kind, distance=-160 if kind == 'slide_in' else 160)
            event = output.mark(kind, animation=definition)
            response = h.c.call('animate_overlay', scene_id=first, layer_id=layer, animation=definition)
            identifier = response['result']['operation_id']
            assert isinstance(identifier, int) and identifier > 0
            event.update({'operation_id': identifier, 'response': response})
            if index == 0:
                busy = h.c.call('animate_overlay', expect=False, scene_id=first, layer_id=layer, animation=definition)
                assert busy['error']['code'] == 'ANIMATION_BUSY_OR_INVALID', busy
                blocked = h.c.call('select_scene', expect=False, scene_id=second)
                assert blocked['error']['code'] == 'ANIMATION_BUSY', blocked
                event['busy'] = busy
                event['scene_switch_blocked'] = blocked
            ended = output.until(lambda s: job(s, identifier)['phase'] in TERMINAL and not s['overlays']['runtime']['animations']['busy'])
            assert job(ended, identifier)['phase'] == 'completed', job(ended, identifier)
            assert layer_for(ended, first, marker)['layouts']['horizontal']['visible'] == kind.endswith('_in')
            event['terminal'] = job(ended, identifier)
            output.hold(.35)
            event['post_seconds'] = time.monotonic()-output.start-.15
            measured.append(event)
        cancellation = output.mark('cancel_slide')
        response = h.c.call('animate_overlay', scene_id=first, layer_id=layer,
                            animation=animation_definition('slide_out', duration=3000, easing='ease_in_out'))
        identifier = response['result']['operation_id']
        output.hold(.6)
        cancelled = h.c.call('cancel_overlay_animation', operation_id=identifier)
        ended = output.until(lambda s: job(s, identifier)['phase'] == 'cancelled' and not s['overlays']['runtime']['animations']['busy'])
        assert layer_for(ended, first, marker)['layouts']['horizontal']['visible']
        repeated = h.c.call('cancel_overlay_animation', operation_id=identifier)
        invalid = h.c.call('cancel_overlay_animation', expect=False, operation_id=identifier+1000000)
        assert invalid['error']['code'] == 'ANIMATION_OPERATION_UNAVAILABLE', invalid
        cancellation.update({'operation_id': identifier, 'cancel_response': cancelled, 'terminal': job(ended, identifier), 'repeat': repeated, 'invalid': invalid})
        output.hold(.4)
        cancellation['restored_seconds'] = time.monotonic()-output.start-.15
        cuts = []
        for target in (second, first):
            event = output.mark('cut', target=target)
            h.c.call('select_scene', scene_id=target)
            output.until(lambda s: graph(s)['active_scene'] == target and s['transition']['phase'] not in ('preparing', 'running'))
            output.hold(.5)
            event['post_seconds'] = time.monotonic()-output.start-.2
            cuts.append(event)
        h.c.call('configure_transition', transition={'kind': 'fade', 'duration_ms': 1500})
        fade = output.mark('scene_fade', target=second)
        h.c.call('select_scene', scene_id=second)
        blocked = h.c.call('animate_overlay', expect=False, scene_id=first, layer_id=layer,
                          animation=animation_definition('slide_in'))
        assert blocked['error']['code'] == 'TRANSITION_BUSY', blocked
        fade['animation_blocked'] = blocked
        output.until(lambda s: graph(s)['active_scene'] == second and s['transition']['phase'] == 'completed')
        output.hold(.5)
        output.stop()
        pixels = []
        for event in measured:
            kind = event['label']
            images = [output.frame(kind+'-'+str(i), event['seconds']+offset) for i, offset in enumerate((.3, .75, 1.2))]
            observation = {'kind': kind}
            if kind.startswith('fade'):
                colors = [mean(image, (440, 250, 520, 280)) for image in images]
                greens = [c[1] for c in colors]
                if kind == 'fade_in':
                    assert greens[0]+20 < greens[1] and greens[1]+20 < greens[2], colors
                else:
                    assert greens[0] > greens[1]+20 and greens[1] > greens[2]+20, colors
                assert all(BG[1]+10 < v < GREEN[1]-5 for v in greens), colors
                observation['rgb'] = colors
            else:
                boxes = [green_box(image) for image in images]
                assert all(boxes), boxes
                if kind.startswith('slide'):
                    expected = ([400-160*p for p in (.2, .5, .8)] if kind.endswith('_out')
                                else [400+160*(1-p) for p in (.2, .5, .8)])
                    assert all(abs(box[0]-x) < 16 and abs(box[2]-160) <= 6 for box, x in zip(boxes, expected)), (boxes, expected)
                    if kind == 'slide_in':
                        assert boxes[0][0] > 480, 'Negative distance must enter from the right'
                else:
                    expected = [160*(1+(.35-1)*p) for p in (.2, .5, .8)] if kind.endswith('_out') else [160*(.35+(1-.35)*p) for p in (.2, .5, .8)]
                    assert all(abs(box[2]-size) < 14 for box, size in zip(boxes, expected)), (boxes, expected)
                    assert abs(boxes[0][2]-boxes[2][2]) > 45, boxes
                observation['boxes'] = boxes
                observation['expected'] = expected
            post = green_box(output.frame(kind+'-post', event['post_seconds']))
            assert bool(post) == kind.endswith('_in'), (kind, post)
            observation['post_box'] = post
            pixels.append(observation)
        restored = green_box(output.frame('cancel-restored', cancellation['restored_seconds']))
        assert restored and abs(restored[0]-400) <= 4 and abs(restored[2]-160) <= 6, restored
        cut_colors = [mean(output.frame('cut-'+str(i), event['post_seconds']), (40, 40, 80, 80)) for i, event in enumerate(cuts)]
        assert near(cut_colors[0], BG_B) and near(cut_colors[1], BG), cut_colors
        stripe = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(output.path),
                                          '-vf', 'crop=8:8:40:40,scale=1:1', '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
        stripe_colors = [list(stripe[i:i+3]) for i in range(0, len(stripe), 3)]
        cut_windows = []
        points = video_pts(output.path)
        assert len(stripe_colors) == len(points)
        for event in cuts:
            first_frame = bisect.bisect_left(points, event['seconds']+output.origin-.2)
            last_frame = bisect.bisect_left(points, event['seconds']+output.origin+.4)
            window = stripe_colors[first_frame:last_frame]
            assert window and all(near(color, BG, 12) or near(color, BG_B, 12) for color in window), window
            cut_windows.append(window)
        fade_colors = [mean(output.frame('scene-fade-'+str(i), fade['seconds']+offset), (40, 40, 80, 80)) for i, offset in enumerate((.3, .75, 1.2))]
        assert fade_colors[0][0]+10 < fade_colors[1][0] and fade_colors[1][0]+10 < fade_colors[2][0], fade_colors
        for offset in (.3, .75, 1.2):
            box = green_box(output.frame('shared-during-fade-'+str(offset), fade['seconds']+offset))
            assert box and abs(box[0]-400) <= 4 and abs(box[2]-160) <= 6, ('Shared source disappeared during H9 Fade', box)
        output.report['pixel_proofs'] = {'animations': pixels, 'cancel_restored_box': restored,
                                       'cut_backgrounds': cut_colors, 'cut_frames_no_blend': cut_windows,
                                       'scene_fade_backgrounds': fade_colors}


def widget_definition(kind, title, width, height, color, duration, subtitle='Native state'):
    return {'kind': 'widget', 'widget': {'kind': kind, 'title': title, 'subtitle': subtitle, 'width': width, 'height': height,
            'background': color, 'accent': rgb(GREEN), 'color': 0xffffff, 'opacity': 1.0, 'duration_ms': duration}}


def reference_definition(value):
    return {'kind': 'text', 'text': value, 'font': 'Helvetica', 'size': 126, 'color': 0xffffff, 'opacity': 1.0,
            'align': 'center', 'width': 372, 'height': 141, 'background': None, 'background_opacity': 0.0, 'outline': False}


def widgets(h, transports, _args):
    selected = h.new_scene('H11 native widgets')
    h.background(selected)
    parameters = {'title': 'H11 Áé ñ', 'subtitle': 'Lower third native fade', 'background': 0x285ac8,
                  'accent': rgb(GREEN), 'color': 0xffffff, 'duration_ms': 0}
    lower_ids = h.preset(selected, 'professional_lower_third', parameters)
    lower = next(s['id'] for s in graph(h.c.state())['sources'] if s['id'] in lower_ids and s['overlay']['kind'] == 'widget')
    countdown, _ = h.add(selected, 'Three-second native timer', widget_definition('countdown', 'Countdown', 420, 300, 0x203050, 3000), (40, 30, 420, 300), 2)
    alert, _ = h.add(selected, 'Expiring native alert', widget_definition('alert', 'ALERTA Áé', 340, 160, 0xd05030, 1800), (560, 40, 340, 160), 3)
    reference, _ = h.add(selected, 'Controlled native glyph reference', reference_definition('00:03'), (520, 220, 372, 141), 4)
    h.ready()
    for identifier, event in ((lower, 'timer_start'), (countdown, 'trigger'), (alert, 'pause')):
        denied = h.c.call('overlay_event', expect=False, source_id=identifier, event=event)
        assert denied['error']['code'] == 'INVALID_OVERLAY_ACTION', denied
        h.report.setdefault('invalid_events', []).append(denied)
    for transport in transports:
        h.c.call('overlay_event', source_id=lower, event='hide')
        h.c.call('overlay_event', source_id=alert, event='hide')
        h.c.call('overlay_event', source_id=countdown, event='timer_reset')
        h.c.call('update_overlay', source_id=reference, definition=reference_definition('00:03'))
        output = Output(h, 'widgets-'+transport, transport)
        output.hold(.8)
        baseline = .4
        show = output.mark('lower_show')
        h.c.call('overlay_event', source_id=lower, event='show')
        output.hold(.7)
        hide = output.mark('lower_hide')
        h.c.call('overlay_event', source_id=lower, event='hide')
        output.hold(.6)
        h.c.call('overlay_event', source_id=countdown, event='timer_start')
        output.hold(.4)
        paused = h.c.call('overlay_event', source_id=countdown, event='timer_stop')['state']
        assert sources(paused)[countdown]['phase'] == 'paused'
        remaining = sources(paused)[countdown]['remaining_ms']
        output.hold(.4)
        assert abs(sources(output.sample())[countdown]['remaining_ms']-remaining) <= 1
        h.c.call('overlay_event', source_id=countdown, event='timer_reset')
        timer = output.mark('timer_start_no_client')
        h.c.call('overlay_event', source_id=countdown, event='timer_start')
        alert_event = output.mark('alert_trigger_no_client')
        h.c.call('overlay_event', source_id=alert, event='trigger')
        h.c.call('overlay_event', source_id=lower, event='show')
        before = output.sample()
        assert sources(before)[countdown]['phase'] == 'running'
        disconnected = output.mark('client_closed', state=before)
        h.detach()
        quiet_started = time.monotonic()
        time.sleep(4.2)  # deliberately no MCP client, status loop, or control calls
        quiet_seconds = time.monotonic()-quiet_started
        h.reconnect()
        after = output.sample()
        resumed = output.mark('client_reconnected', quiet_seconds=quiet_seconds, state=after)
        assert after['pid'] == before['pid'] and quiet_seconds >= 4.2
        assert sources(after)[countdown]['phase'] == 'completed' and sources(after)[countdown]['remaining_ms'] == 0
        assert sources(after)[alert]['phase'] == 'hidden' and not sources(after)[alert]['visible']
        assert sources(after)[lower]['phase'] == 'visible'
        # Same control via CLI; native reference verifies the final glyphs.
        changed = cli('update_overlay', source_id=reference, definition=reference_definition('00:00'))
        assert changed['pid'] == after['pid']
        output.report['cli_update'] = changed
        output.hold(.7)
        final_reference = time.monotonic()-output.start-.25
        output.stop()
        before_image = output.frame('idle-00-03', baseline)
        finished_image = output.frame('completed-00-00', final_reference)
        timer_box = (64, 129, 436, 270)
        reference_box = (520, 220, 892, 361)
        three = white_mask(before_image, timer_box)
        ref_three = white_mask(before_image, reference_box)
        zero = white_mask(finished_image, timer_box)
        ref_zero = white_mask(finished_image, reference_box)
        matches = {'00:03': mask_error(three, ref_three), '00:00': mask_error(zero, ref_zero),
                   'wrong_03_vs_00': mask_error(three, ref_zero, False), 'wrong_00_vs_03': mask_error(zero, ref_three, False)}
        assert matches['00:03'] < .10 and matches['00:00'] < .10, matches
        assert matches['wrong_03_vs_00'] > matches['00:03']+.015 and matches['wrong_00_vs_03'] > matches['00:00']+.015, matches
        countdown_frames = [output.frame('no-client-second-'+str(i), timer['seconds']+offset) for i, offset in enumerate((.4, 1.4, 2.4, 3.4))]
        masks = [white_mask(image, timer_box) for image in countdown_frames]
        changes = [mask_error(a, b, False) for a, b in zip(masks, masks[1:])]
        assert all(change > .01 for change in changes), changes
        assert mask_error(masks[0], ref_three) < .10 and mask_error(masks[-1], ref_zero) < .10
        lower_box = (620, 490, 650, 500)
        lower_colors = [mean(output.frame('lower-'+name, second), lower_box) for name, second in
                        (('hidden', baseline), ('half', show['seconds']+.15), ('shown', show['seconds']+.5), ('hidden-again', hide['seconds']+.45))]
        assert near(lower_colors[0], BG) and near(lower_colors[2], (40, 90, 200)) and near(lower_colors[3], BG), lower_colors
        assert lower_colors[0][2]+15 < lower_colors[1][2] < lower_colors[2][2]-15, lower_colors
        alert_box = (860, 170, 885, 185)
        alert_colors = [mean(output.frame('alert-'+str(i), alert_event['seconds']+offset), alert_box) for i, offset in enumerate((.7, 3.4))]
        assert near(alert_colors[0], (208, 80, 48)) and near(alert_colors[1], BG), alert_colors
        assert disconnected['seconds'] < timer['seconds']+3.4 < resumed['seconds']
        output.report['pixel_proofs'] = {'glyph_match_errors': matches, 'consecutive_timer_glyph_changes': changes,
                                       'lower_third_rgbs': lower_colors, 'alert_rgbs': alert_colors,
                                       'no_mcp_interval': [disconnected['seconds'], resumed['seconds']]}


def presets(h, _transports, args):
    catalogue = h.c.call('overlay_presets')['result']
    assert catalogue['version'] == 1
    h.report['catalogue'] = catalogue
    definitions = {p['id']: p for p in catalogue['presets']}
    requested = args.preset or list(definitions)
    variants = args.variant or ['horizontal', 'vertical']
    selected = []
    for name in requested:
        current = h.new_scene('H11 preset '+name)
        if name == 'professional_lower_third':
            h.background(current)
        parameters = copy.deepcopy(definitions[name]['parameters'])
        parameters.update({'title': 'H11 Áé '+definitions[name]['name'], 'subtitle': 'Original editable preset', 'accent': rgb(GREEN), 'color': 0xffffff})
        if name == 'starting_soon':
            parameters['duration_ms'] = 3000
        ids = h.preset(current, name, parameters)
        state = h.c.state()
        widgets_ids = [s['id'] for s in graph(state)['sources'] if s['id'] in ids and s['overlay']['kind'] == 'widget']
        assert len(widgets_ids) == 1
        entry = {'preset': name, 'scene_id': current, 'ids': ids, 'widget': widgets_ids[0], 'parameters': parameters}
        recipe = definitions[name].get('decoration_animation')
        if recipe:
            assert recipe['version'] == 1
            targets = [s for s in graph(state)['sources'] if s['id'] in ids and s['name'] == recipe['source_name']]
            assert len(targets) == 1 and targets[0]['overlay']['kind'] == 'shape' and targets[0]['overlay']['shape'] == 'circle'
            entry['decoration'] = {'recipe': recipe, 'source_id': targets[0]['id']}
        if name == 'be_right_back':
            assert 'decoration' in entry, 'BRB must publish its explicit decoration recipe'
        selected.append(entry)
    for preset in selected:
        for variant in variants:
            h.c.call('set_variant', variant=variant)
            h.select(preset['scene_id'])
            state = h.c.call('overlay_event', source_id=preset['widget'], event='show')['state']
            width, height = (960, 540) if variant == 'horizontal' else (540, 960)
            for layer in scene(state, preset['scene_id'])['layers']:
                rect = layer['layouts'][variant]
                assert rect['visible'] and 0 <= rect['x'] < width and 0 <= rect['y'] < height
                assert rect['x']+rect['width'] <= width and rect['y']+rect['height'] <= height, rect
            output = Output(h, preset['preset']+'-'+variant, 'recording')
            decoration = preset.get('decoration')
            decoration_event = None
            if decoration:
                output.hold(.25)
                target = layer_for(state, preset['scene_id'], decoration['source_id'])
                decoration_event = output.mark('brb_decoration', recipe=decoration['recipe'],
                                               source_id=decoration['source_id'], layer_id=target['id'])
                response = h.c.call('animate_overlay', scene_id=preset['scene_id'], layer_id=target['id'],
                                    animation=decoration['recipe']['animation'])
                identifier = response['result']['operation_id']
                decoration_event['operation_id'] = identifier
                ended = output.until(lambda s: job(s, identifier)['phase'] in TERMINAL and not s['overlays']['runtime']['animations']['busy'])
                assert job(ended, identifier)['phase'] == 'completed', job(ended, identifier)
                original_widget = next(s for s in graph(state)['sources'] if s['id'] == preset['widget'])
                assert next(s for s in graph(ended)['sources'] if s['id'] == preset['widget']) == original_widget
                decoration_event['terminal'] = job(ended, identifier)
                output.hold(.4)
                decoration_event['final_seconds'] = time.monotonic()-output.start-.15
            else:
                output.hold(2.4)
            output.stop()
            image = output.frame('layout', 1.2)
            layer = layer_for(state, preset['scene_id'], preset['widget'])['layouts'][variant]
            box = (int(layer['x']), int(layer['y']), int(layer['x']+layer['width']), int(layer['y']+layer['height']))
            pixels = list(image.crop(box).getdata())
            whites = sum(min(p) > 185 and max(p)-min(p) < 55 for p in pixels)
            accents = sum(near(p, GREEN, 25) for p in pixels)
            assert whites > 200 and accents > 100, (preset['preset'], variant, whites, accents)
            output.report['layout_pixels'] = {'variant': variant, 'canvas': [width, height], 'widget_bounds': box,
                                               'white_glyph_pixels': whites, 'green_accent_pixels': accents}
            if decoration_event:
                target = layer_for(state, preset['scene_id'], decoration['source_id'])['layouts'][variant]
                target_box = (int(target['x']), int(target['y']), int(target['x']+target['width']), int(target['y']+target['height']))
                early = output.frame('decoration-early', decoration_event['seconds']+.2)
                final = output.frame('decoration-final', decoration_event['final_seconds'])
                early_box, final_box = green_box(early.crop(target_box)), green_box(final.crop(target_box))
                # This widget must remain at identical scene coordinates. Use
                # its fixed box: codec rounding can change a tight glyph bound
                # by one pixel, and normalizing that bound would rescale every
                # letter instead of measuring the actual decoded difference.
                text_error = mask_error(white_mask(early, box, tight=False),
                                        white_mask(final, box, tight=False))
                progress = .2/(decoration['recipe']['animation']['duration_ms']/1000)
                eased = 2*progress*progress  # ease_in_out, first half
                expected_early = target['width']*(.7+.3*eased)
                output.report['decoration_animation'] = {'event': decoration_event, 'target_bounds': target_box,
                    'early_green_bounds': early_box, 'final_green_bounds': final_box,
                    'expected_early_diameter': expected_early, 'text_mask_error': text_error,
                    'text_mask_space': 'fixed_widget_bounds'}
                assert early_box and final_box, (early_box, final_box)
                assert abs(early_box[2]-expected_early) <= 8 and abs(early_box[3]-expected_early) <= 8, early_box
                assert abs(final_box[2]-target['width']) <= 4 and abs(final_box[3]-target['height']) <= 4, final_box
                assert final_box[2]-early_box[2] >= 12 and final_box[3]-early_box[3] >= 12, (early_box, final_box)
                assert text_error < .05, ('BRB decoration changed widget glyphs', text_error)
    h.snapshot_disk()
    before_profiles = h.c.call('output_profiles')['store']
    h.disk_touched = True
    saved = h.c.call('save_project')['state']['project']
    persisted = json.loads((ROOT/'var/project.json').read_text())
    (h.directory/'saved-presets-v4.json').write_text(json.dumps(persisted, indent=2))
    h.report['persistence'] = {'saved': saved, 'persisted': persisted, 'output_profiles_before': before_profiles, 'presets': selected}
    assert saved == persisted and persisted['version'] == 4
    assert h.c.call('output_profiles')['store'] == before_profiles
    by_id = {s['id']: s for s in persisted['graph']['sources']}
    for preset in selected:
        widget = by_id[preset['widget']]['overlay']['widget']
        for key, value in preset['parameters'].items():
            assert widget[key] == value, (key, widget, preset)
        for layer in next(s for s in persisted['graph']['scenes'] if s['id'] == preset['scene_id'])['layers']:
            assert set(layer['layouts']) == {'horizontal', 'vertical'}
    h.report['persistence']['output_profiles_unchanged'] = before_profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='append', choices=('animations', 'widgets', 'presets'))
    parser.add_argument('--transport', choices=('recording', 'rtmp', 'both'), default='recording')
    parser.add_argument('--preset', action='append', choices=('professional_lower_third', 'starting_soon', 'be_right_back'))
    parser.add_argument('--variant', action='append', choices=('horizontal', 'vertical'))
    args = parser.parse_args()
    transports = ['recording', 'rtmp'] if args.transport == 'both' else [args.transport]
    run = EVIDENCE/('h11-runtime-'+str(time.time_ns()))
    run.mkdir(parents=True)
    summary = {'ok': False, 'run': str(run), 'arguments': vars(args), 'stages': []}
    try:
        summary['app_sha256'] = hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
        for name in dict.fromkeys(args.stage or ('animations', 'widgets', 'presets')):
            directory = run/name
            directory.mkdir()
            report = {'stage': name, 'ok': False, 'directory': str(directory)}
            summary['stages'].append({'stage': name, 'report': str(directory/'report.json'), 'ok': False})
            harness = Harness(directory, report)
            try:
                harness.open()
                {'animations': animations, 'widgets': widgets, 'presets': presets}[name](harness, transports, args)
                report['ok'] = True
            except BaseException as failure:
                report['error'] = repr(failure)
                raise
            finally:
                harness.close()
                (directory/'report.json').write_text(json.dumps(report, indent=2))
                summary['stages'][-1]['ok'] = report['ok']
            assert report['ok'], report.get('cleanup_errors')
        summary['ok'] = True
    except BaseException as failure:
        summary['error'] = repr(failure)
        raise
    finally:
        contents = json.dumps(summary, indent=2)
        (run/'report.json').write_text(contents)
        (EVIDENCE/'h11-runtime.json').write_text(contents)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
