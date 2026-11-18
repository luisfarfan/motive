#!/usr/bin/env python3
"""Real concurrent MKV/loopback RTMP acceptance for the H13 output contract.

The caller must already own the shared device/bundle lock and launch the signed
idle app from THIS checkout. This script never builds, launches, signs, opens a
capture device, changes privacy settings, or sends a public stream. It requires
an empty mixer and disposable pattern/legacy-overlay production. No store is
saved. New scenes, sources, inputs and profiles are removed when safe; graph ID
counters and project migration are not rolled back. If no endpoint was selected
beforehand, the test's loopback endpoint remains selected (there is no unset API).

Start small: --lock-held --stage smoke (~30 seconds plus media analysis).
Then: --lock-held --stage production / receiver-loss / muxer-loss / all.
--soak-seconds 1800 extends the healthy dual-output interval. --hold-seconds
defaults to 3; its minimum is 2 so decoded audio has an interior analysis window.
Each invocation creates a unique evidence directory and retains failures. There
are no relaxed success thresholds for a quick run. The script consumes the
proposed docs/h13-output-contract.md and fails if its typed API is unavailable.
"""

import argparse
import array
import bisect
import hashlib
import itertools
import json
import math
import os
import pathlib
import select
import signal
import socket
import statistics
import subprocess
import time
import traceback

# These modules have main guards; importing them does not operate the studio.
from h7_support import process_sample
from verify_h10_audio import tonal_amplitude
from verify_h11_visuals import png, shape_definition


ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
APP = VERIFY.app_executable
VIDEO = {'version': 1, 'resolution': 'full_hd1080', 'fps': 30,
         'coordinate_space': 'design960'}
DEFAULT_VIDEO = {**VIDEO, 'resolution': 'legacy540'}
TARGETS = ('recording', 'streaming')
SCENE_COLORS = {'A': (32, 224, 96), 'B': (224, 48, 64)}
MARKER_BOX = (910, 26, 16, 16)
STRIPE_BOX = (32, 24, 16, 16)
PALETTE = list(itertools.product((32, 96, 160, 224), repeat=3))
REQUIRED_TOOLS = {'outputs', 'start_output', 'stop_output_target',
                  'cancel_output_target', 'recover_output_target',
                  'cancel_all_outputs', 'preflight_output', 'configure_video'}


def check(condition, label, **details):
    if not condition:
        raise AssertionError({'check': label, **details})


def sha(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def run(*args, timeout=120):
    return subprocess.check_output(args, stderr=subprocess.PIPE, timeout=timeout)


def rgb(color):
    return color[0] << 16 | color[1] << 8 | color[2]


def near(actual, expected, tolerance=24):
    return max(abs(a-b) for a, b in zip(actual, expected)) <= tolerance


def db(value):
    return 20 * math.log10(max(value, 1e-12))


def profile(identifier, encoder, bitrate):
    return {'id': identifier, 'encoder': encoder, 'bitrate_kbps': bitrate,
            'rate_control': 'cbr', 'keyframe_seconds': 1, 'frame_reordering': False}


def widget(kind, title, width, height, duration=0):
    return {'kind': 'widget', 'widget': {'kind': kind, 'title': title,
            'subtitle': 'H13 controlled production', 'width': width, 'height': height,
            'background': 0x203050, 'accent': 0x20e060, 'color': 0xffffff,
            'opacity': 1., 'duration_ms': duration}}


def layer(state, scene_id, source_id):
    scene = next(s for s in state['project']['graph']['scenes'] if s['id'] == scene_id)
    return next(item for item in scene['layers'] if item['source_id'] == source_id)


def slots(state):
    check(state.get('output_contract_version') == 1, 'H13 output contract version',
          actual=state.get('output_contract_version'))
    value = state['outputs']
    check(set(value) == set(TARGETS), 'exact output registry keys', actual=list(value))
    return value


class Client:
    """One real stdio MCP client plus CLI calls; full bounded-on-disk transcript."""
    def __init__(self, directory):
        self.log = (directory / 'operations.jsonl').open('w')
        self.stderr = (directory / 'mcp-stderr.log').open('w')
        self.process = subprocess.Popen([str(APP), 'mcp'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, bufsize=1)
        self.next_id = 0
        self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                 'clientInfo': {'name': 'h13-real-outputs', 'version': '1'}})

    def log_entry(self, value):
        self.log.write(json.dumps(value, separators=(',', ':')) + '\n')
        self.log.flush()

    def rpc(self, method, params=None):
        self.next_id += 1
        request = {'jsonrpc': '2.0', 'id': self.next_id, 'method': method,
                   'params': params or {}}
        before = time.monotonic()
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 15)
        check(bool(ready), 'MCP response timeout', request=request)
        line = self.process.stdout.readline()
        check(bool(line), 'MCP closed its stdout', request=request)
        response = json.loads(line)
        self.log_entry({'transport': 'mcp', 'request_monotonic': before,
                        'response_monotonic': time.monotonic(),
                        'request': request, 'response': response})
        check(response.get('id') == self.next_id and 'error' not in response,
              'JSON-RPC response', response=response)
        return response['result']

    def call(self, op, expect=True, transport='mcp', **arguments):
        if transport == 'cli':
            request = {'op': op, **arguments}
            before = time.monotonic()
            process = subprocess.run([str(APP), 'ctl', json.dumps(request)],
                                     capture_output=True, text=True, timeout=15)
            value = json.loads(process.stdout)
            self.log_entry({'transport': 'cli', 'request_monotonic': before,
                            'response_monotonic': time.monotonic(), 'request': request,
                            'response': value, 'returncode': process.returncode,
                            'stderr': process.stderr})
        else:
            result = self.rpc('tools/call', {'name': op, 'arguments': arguments})
            value = json.loads(result['content'][0]['text'])
            check(result['isError'] == (not expect), 'MCP isError agreement', result=result)
        check(value.get('ok') is expect, 'command result', op=op, response=value)
        return value

    def state(self):
        return self.call('status')['state']

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        finally:
            self.log.close()
            self.stderr.close()


class Receiver:
    def __init__(self, directory, label, port):
        self.path = directory / (label + '.mkv')
        self.log_path = directory / (label + '-receiver.log')
        with self.log_path.open('w') as log:
            self.process = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'warning',
                '-listen', '1', '-i', f'rtmp://127.0.0.1:{port}/live/motive',
                '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', str(self.path)],
                stdout=subprocess.DEVNULL, stderr=log)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            check(self.process.poll() is None, 'receiver exited before listening',
                  path=str(self.log_path), returncode=self.process.returncode)
            listener = subprocess.run(['lsof', '-a', '-p', str(self.process.pid),
                '-iTCP:' + str(port), '-sTCP:LISTEN'], capture_output=True)
            if listener.returncode == 0:
                return
            time.sleep(.1)
        self.terminate()
        raise AssertionError('Owned receiver did not listen within eight seconds')

    def wait(self):
        # Listener EOF can return nonzero after normal remote close; decoded
        # media and native output state determine success, never this code alone.
        return self.process.wait(timeout=12)

    def terminate(self):
        if self.process.poll() is None:
            self.process.terminate()
        return self.process.wait(timeout=12)


class Suite:
    def __init__(self, args, directory, report):
        self.args, self.directory, self.report = args, directory, report
        self.c = None
        self.initial = None
        self.created_scenes, self.created_sources, self.created_profiles = [], [], []
        self.tone = None
        self.receivers, self.media = [], []
        self.active, self.allowed_faults = set(), set()
        self.case = None
        self.last_counters = {}
        self.marker_number = 0
        self.scene_name, self.gain, self.muted = 'A', -6., False
        self.changed = False
        self.observations = (directory / 'observations.jsonl').open('w')

    def save(self):
        write_json(self.directory / 'report.json', self.report)

    def open(self):
        check(APP.is_file(), 'signed bundle executable must already exist', app=str(APP))
        self.report.update(app_sha256=sha(APP), app=str(APP), script_sha256=sha(__file__),
            commit=run('git', '-C', str(ROOT), 'rev-parse', 'HEAD').decode().strip(),
            git_status=run('git', '-C', str(ROOT), 'status', '--short').decode(),
            ffmpeg=run('ffmpeg', '-version').decode().splitlines()[0])
        self.c = Client(self.directory)
        self.initial = self.c.state()
        self.report['initial'] = self.initial
        check(all(not item['native_busy'] and not item['recovery_required']
                  for item in slots(self.initial).values()), 'requires idle healthy outputs')
        tools = {item['name']: item for item in self.c.rpc('tools/list')['tools']}
        check(REQUIRED_TOOLS <= tools.keys(), 'required H13 tools',
              missing=sorted(REQUIRED_TOOLS - tools.keys()))
        for name in REQUIRED_TOOLS:
            check(tools[name]['inputSchema']['additionalProperties'] is False,
                  'closed command schema', tool=name)
            check(tools[name]['annotations']['openWorldHint'] is False,
                  'local MCP tool annotation', tool=name)
        for name in ('outputs', 'preflight_output'):
            check(tools[name]['annotations']['readOnlyHint'] is True,
                  'read-only query annotation', tool=name)
        for name in ('stop_output_target', 'cancel_output_target', 'cancel_all_outputs'):
            check(tools[name]['annotations']['destructiveHint'] is True,
                  'stop mutation annotation', tool=name)
        check(not self.initial['audio_mixer']['store']['inputs'], 'empty controlled mixer required')
        graph = self.initial['project']['graph']
        check(all(s['spec']['kind'] in ('pattern', 'overlay') and s.get('overlay') is None
                  for s in graph['sources']), 'only disposable pattern/legacy sources allowed')
        check(not self.initial['issues'] and not self.initial['overlays']['runtime']['animations']['busy'],
              'production ready before fixture')
        check(self.initial['output_configuration']['credential_ref'] is None,
              'credential-free loopback fixture required')
        actual_app = pathlib.Path(run('ps', '-p', str(self.initial['pid']), '-o', 'comm=').decode().strip())
        check(actual_app.resolve() == APP.resolve(), 'studio belongs to this bundle', actual=str(actual_app))
        self.report['libobs'] = self.initial['libobs']
        self.original_profiles = self.c.call('output_profiles')['store']
        check(len(self.original_profiles['profiles']) <= 14, 'space for two temporary profiles')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.changed = True
        self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.c.call('set_variant', variant='horizontal')
        self.c.call('configure_video', video=VIDEO)
        self.c.call('configure_stream', endpoint={'transport': 'rtmp', 'port': self.port})
        stamp = str(time.time_ns())
        self.profiles = {
            'recording': profile('h13-record-' + stamp, self.args.recording_encoder, 6000),
            'streaming': profile('h13-stream-' + stamp, self.args.streaming_encoder, 4000)}
        for target, value in self.profiles.items():
            self.c.call('upsert_output_profile', profile=value)
            self.created_profiles.append(value['id'])
            self.c.call('select_output_profile', target=target, profile_id=value['id'])
        state = self.c.call('add_audio_input', name='H13 controlled 440 Hz', source={'kind': 'tone'})['state']
        self.tone = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=-6)
        pattern = next(s['id'] for s in graph['sources'] if s['spec']['kind'] == 'pattern')
        self.scenes = {}
        for name in ('A', 'B'):
            state = self.c.call('create_scene', name='H13 output scene ' + name)['state']
            scene_id = state['project']['graph']['active_scene']
            self.created_scenes.append(scene_id)
            self.scenes[name] = scene_id
            state = self.c.call('add_layer', scene_id=scene_id, source_id=pattern)['state']
            self.transform(scene_id, layer(state, scene_id, pattern)['id'], (0, 0, 960, 540), 0)
            self.add(scene_id, 'H13 scene stripe ' + name,
                     shape_definition('rectangle', 800, 80, rgb(SCENE_COLORS[name])),
                     (0, 0, 800, 80), 1)
        first = self.scenes['A']
        self.marker = self.add(first, 'H13 native stage marker',
            shape_definition('rectangle', 40, 40, rgb(PALETTE[0])), (900, 16, 40, 40), 31)
        self.lower = self.add(first, 'H13 lower third', widget('lower_third', 'AAAA', 640, 105),
                              (32, 410, 640, 105), 5)
        self.countdown = self.add(first, 'H13 countdown', widget('countdown', 'Countdown', 280, 130, 5000),
                                  (650, 330, 280, 130), 6)
        self.alert = self.add(first, 'H13 alert', widget('alert', 'ALERTA H13', 280, 110, 6000),
                              (650, 90, 280, 110), 7)
        for source, rect, order in ((self.marker, (900, 16, 40, 40), 31),
                (self.lower, (32, 410, 640, 105), 5),
                (self.countdown, (650, 330, 280, 130), 6),
                (self.alert, (650, 90, 280, 110), 7)):
            state = self.c.call('add_layer', scene_id=self.scenes['B'], source_id=source)['state']
            self.transform(self.scenes['B'], layer(state, self.scenes['B'], source)['id'], rect, order)
        self.c.call('overlay_event', source_id=self.lower, event='hide')
        self.c.call('overlay_event', source_id=self.alert, event='hide')
        self.c.call('select_scene', scene_id=first)
        deadline = time.monotonic() + 10
        while True:
            state = self.c.state()
            if not state['issues'] and all(i['phase'] == 'ready' for i in state['audio_mixer']['runtime']['inputs']):
                break
            check(time.monotonic() < deadline, 'owned fixture readiness', state=state)
            time.sleep(.1)
        check((state['width'], state['height'], state['fps']) == (1920, 1080, 30),
              'actual configured video', dimensions=[state['width'], state['height'], state['fps']])
        self.fixture_ids = self.identities(state)
        self.report['fixture'] = {'state': state, 'identities': self.fixture_ids, 'profiles': self.profiles}
        self.save()

    def transform(self, scene_id, layer_id, rect, order):
        x, y, width, height = rect
        self.c.call('set_transform', scene_id=scene_id, layer_id=layer_id, variant='horizontal',
                    transform={'x': x, 'y': y, 'width': width, 'height': height,
                               'visible': True, 'order': order})

    def add(self, scene_id, name, definition, rect, order):
        response = self.c.call('create_overlay', scene_id=scene_id, name=name, definition=definition)
        identifier = response['result']['source_id']
        self.created_sources.append(identifier)
        self.transform(scene_id, layer(response['state'], scene_id, identifier)['id'], rect, order)
        return identifier

    @staticmethod
    def identities(state):
        return {'sources': {s['id']: s['instance_id'] for s in state['sources']},
                'audio': {s['id']: s['instance_id'] for s in state['audio_mixer']['runtime']['inputs']},
                'overlay_children': {s['id']: s['child_instances_created'] for s in state['overlays']['runtime']['sources']},
                'source_instances_created': state['transition']['source_instances_created'],
                'scenes_built': state['transition']['scenes_built']}

    def sample(self):
        state = self.c.state()
        now = time.monotonic()
        cpu, rss = process_sample(state['pid'])
        row = {'monotonic': now, 'case': self.case['name'], 'state': state,
               'cpu_percent': 100*(cpu-self.last_cpu)/(now-self.last_time), 'rss_mib': rss}
        self.last_cpu, self.last_time = cpu, now
        self.observations.write(json.dumps(row, separators=(',', ':')) + '\n')
        self.observations.flush()
        self.case['samples'].append({'monotonic': now, 'cpu_percent': row['cpu_percent'],
             'rss_mib': rss, 'outputs': state['outputs'], 'stats': state['stats'],
             'tone_levels': next(i['levels'] for i in state['audio_mixer']['runtime']['inputs'] if i['id'] == self.tone)})
        check(state['pid'] == self.initial['pid'], 'one studio PID throughout')
        check(self.identities(state) == self.fixture_ids, 'native source identities remain stable',
              expected=self.fixture_ids, actual=self.identities(state))
        check(not state['issues'], 'shared source health', issues=state['issues'])
        check(state['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0, 'no native clipping')
        for target, item in slots(state).items():
            if target in self.active:
                check(item['phase'] == 'active' and item['native_busy'], 'surviving output stays active',
                      target=target, output=item)
            if target not in self.allowed_faults:
                check(not item['failure'] and not item['recovery_required'], 'unexpected output failure',
                      target=target, output=item)
            if item['phase'] == 'active':
                check(item['profile'] == self.profiles[target], 'independent effective profile', target=target)
                key = (target, item['attempt_id'])
                counts = tuple(item['stats'][k] for k in ('output_frames', 'output_bytes', 'encoded_frames'))
                previous = self.last_counters.get(key, (0, 0, 0))
                check(all(b >= a for a, b in zip(previous, counts)), 'monotonic attempt counters',
                      target=target, previous=previous, current=counts)
                self.last_counters[key] = counts
        return state

    def wait(self, predicate, timeout=40):
        deadline = time.monotonic() + timeout
        while True:
            state = self.sample()
            if predicate(state):
                return state
            check(time.monotonic() < deadline, 'native state timeout', state=state['outputs'])
            time.sleep(.15)

    def hold(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(min(.25, max(.001, deadline-time.monotonic())))
            self.sample()

    def mark(self, name, transition=None):
        color = PALETTE[self.marker_number % len(PALETTE)]
        self.marker_number += 1
        check(self.marker_number <= len(PALETTE), 'unique marker colors exhausted')
        entry = {'name': name, 'color': color, 'scene': self.scene_name,
                 'gain_db': self.gain, 'muted': self.muted, 'transition': transition,
                 'request_monotonic': time.monotonic(),
                 'outputs': {t: slots(self.c.state())[t]['attempt_id'] for t in self.active}}
        self.c.call('update_overlay', source_id=self.marker,
                    definition=shape_definition('rectangle', 40, 40, rgb(color)))
        entry['response_monotonic'] = time.monotonic()
        self.case['stages'].append(entry)
        self.save()
        return entry

    def stage(self, name, seconds=None):
        entry = self.mark(name)
        self.hold(self.args.hold_seconds if seconds is None else seconds)
        entry['hold_end_monotonic'] = time.monotonic()
        return entry

    def start(self, target, label, transport='mcp'):
        receiver = None
        if target == 'streaming':
            receiver = Receiver(self.directory, label, self.port)
            self.receivers.append(receiver)
        preflight = self.c.call('preflight_output', target=target, transport=transport)['preflight']
        check(preflight['ready'] and not preflight['network_tested'] and not preflight['encoder_initialized'],
              'honest preflight', preflight=preflight)
        response = self.c.call('start_output', target=target, transport=transport)
        item = slots(response['state'])[target]
        path = receiver.path if receiver else pathlib.Path(item['path'])
        owned_root = (self.directory if receiver else VERIFY.recordings_root) if VERIFY.portable else ROOT / 'var'
        check(path.is_absolute() and path.resolve().is_relative_to(owned_root.resolve()),
              'owned output path', path=str(path))
        record = {'label': label, 'case': self.case['name'], 'target': target,
                  'attempt_id': item['attempt_id'], 'path': str(path),
                  'started': item, 'request': response,
                  'expected_partial': False}
        self.media.append(record)
        self.case['media'].append(label)
        self.report['media'] = self.media
        self.save()
        state = self.wait(lambda s: slots(s)[target]['phase'] == 'active')
        self.active.add(target)
        record.update(started=slots(state)[target], active_observed=time.monotonic())
        self.save()
        return record, receiver

    def stop(self, target, record, receiver=None, transport='mcp'):
        self.active.discard(target)
        self.c.call('stop_output_target', target=target, transport=transport)
        state = self.wait(lambda s: not slots(s)[target]['native_busy'])
        item = slots(state)[target]
        check(item['phase'] == 'idle' and item['failure'] is None, 'normal stop completed', output=item)
        record.update(ended=item, terminal_observed=time.monotonic())
        if receiver:
            record['receiver_exit'] = receiver.wait()
        self.save()

    def begin_case(self, name):
        check(not self.active, 'previous case still active')
        self.allowed_faults.clear()
        self.scene_name, self.gain, self.muted = 'A', -6., False
        self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.c.call('select_scene', scene_id=self.scenes['A'])
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=self.gain)
        self.c.call('set_audio_mute', input_id=self.tone, muted=False)
        self.c.call('overlay_event', source_id=self.lower, event='hide')
        self.c.call('overlay_event', source_id=self.alert, event='hide')
        self.c.call('overlay_event', source_id=self.countdown, event='timer_reset')
        state = self.c.state()
        self.case = {'name': name, 'ok': False, 'before': state, 'stages': [], 'samples': [], 'media': []}
        self.report['cases'].append(self.case)
        self.last_time = time.monotonic()
        self.last_cpu, _ = process_sample(state['pid'])
        self.save()

    def finish_case(self):
        end = self.sample()
        check(all(not x['native_busy'] and not x['recovery_required'] for x in slots(end).values()),
              'case ends quiescent and recovered')
        rows = self.case['samples']
        self.case['metrics'] = {'cpu_median_percent': statistics.median(r['cpu_percent'] for r in rows),
            'rss_min_mib': min(r['rss_mib'] for r in rows), 'rss_max_mib': max(r['rss_mib'] for r in rows),
            'rss_median_mib': statistics.median(r['rss_mib'] for r in rows),
            'lagged_frames_delta': end['stats']['lagged_frames'] - self.case['before']['stats']['lagged_frames'],
            'video_skipped_frames_delta': end['stats']['video_skipped_frames'] - self.case['before']['stats']['video_skipped_frames']}
        self.case['after'] = end
        self.save()
        for field in ('lagged_frames_delta', 'video_skipped_frames_delta'):
            check(self.case['metrics'][field] == 0, 'zero unexpected shared frame loss',
                  field=field, value=self.case['metrics'][field])
        for row in rows:
            for target, output in row['outputs'].items():
                if output['phase'] == 'active' and target not in self.case.get('intentionally_failed_targets', []):
                    check(output['stats']['output_dropped_frames'] == 0, 'zero healthy output drops', target=target)
        self.case['ok'] = True
        self.save()

    def contract_checks(self):
        for transport in ('cli', 'mcp'):
            state = self.c.call('status', transport=transport)['state']
            check(state['pid'] == self.initial['pid'], 'CLI/MCP share PID')
            query = self.c.call('outputs', transport=transport)
            check(query['pid'] == state['pid'] and set(query['outputs']) == set(TARGETS), 'output query contract')
            for op in ('start_recording', 'start_stream'):
                denied = self.c.call(op, expect=False, transport=transport)
                check(denied['error']['code'] == 'OUTPUT_BUSY', 'legacy start stays exclusive', response=denied)
            for op in ('stop_output', 'cancel_output'):
                denied = self.c.call(op, expect=False, transport=transport)
                check(denied['error']['code'] == 'OUTPUT_TARGET_REQUIRED', 'legacy stop rejects ambiguity', response=denied)
            for fields in ({'target': 'public'}, {'target': 'recording', 'path': '/not-accepted'},
                           {'target': 'streaming', 'url': 'rtmp://example.invalid/live'}):
                denied = self.c.call('start_output', expect=False, transport=transport, **fields)
                check(denied['error']['code'] == 'INVALID_ARGUMENT', 'strict invalid command rejection', response=denied)
            self.sample()

    def production_events(self):
        for name, kind, destination in (('cut_b', 'cut', 'B'), ('cut_a', 'cut', 'A'),
                                        ('fade_b', 'fade', 'B'), ('fade_a', 'fade', 'A')):
            self.c.call('configure_transition', transition={'kind': kind, 'duration_ms': 1000 if kind == 'fade' else 0})
            self.scene_name = destination
            event = self.mark(name, transition=kind)
            self.c.call('select_scene', scene_id=self.scenes[destination])
            self.wait(lambda s: s['transition']['phase'] == 'completed' and
                      s['project']['graph']['active_scene'] == self.scenes[destination], 10)
            self.hold(self.args.hold_seconds)
            event['hold_end_monotonic'] = time.monotonic()
        self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.c.call('overlay_event', source_id=self.lower, event='show')
        self.stage('lower_before')
        self.c.call('update_overlay', source_id=self.lower,
                    definition=widget('lower_third', 'MMMMMMMM H13 EDITADO', 640, 105))
        self.stage('lower_after')
        self.c.call('overlay_event', source_id=self.countdown, event='timer_start')
        self.stage('countdown_running', 2.)
        self.stage('countdown_later', 3.5)
        self.c.call('overlay_event', source_id=self.alert, event='trigger')
        self.stage('alert_visible')
        self.gain = -18.
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=self.gain, transport='cli')
        self.stage('gain_lower')
        self.muted = True
        self.c.call('set_audio_mute', input_id=self.tone, muted=True, transport='mcp')
        self.stage('tone_muted')
        self.muted, self.gain = False, -6.
        self.c.call('set_audio_mute', input_id=self.tone, muted=False, transport='cli')
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=self.gain)
        self.stage('tone_restored')

    def healthy(self, production=False):
        self.begin_case('production' if production else 'smoke')
        name = self.case['name']
        recording, _ = self.start('recording', name + '-recording', transport='cli')
        self.stage('recording_only')
        streaming, receiver = self.start('streaming', name + '-stream-1')
        self.stage('both', self.args.steady_seconds)
        self.contract_checks()
        if production:
            self.production_events()
        if self.args.soak_seconds:
            self.stage('dual_soak', self.args.soak_seconds)
        self.stop('streaming', streaming, receiver, transport='cli')
        self.stage('recording_survives_rtmp_stop')
        streaming2, receiver2 = self.start('streaming', name + '-stream-2', transport='cli')
        check(streaming2['attempt_id'] > streaming['attempt_id'], 'RTMP restart has new attempt ID')
        self.stage('both_restarted')
        self.stop('recording', recording, transport='mcp')
        self.stage('streaming_survives_mkv_stop')
        self.stop('streaming', streaming2, receiver2)
        self.finish_case()

    def identify_muxer(self, record):
        def candidates():
            lines = run('ps', '-axo', 'pid=,ppid=,comm=').decode().splitlines()
            return [(int(p[0]), pathlib.Path(p[2])) for line in lines
                    if len(p := line.strip().split(maxsplit=2)) == 3 and
                    int(p[1]) == self.initial['pid'] and pathlib.Path(p[2]).name == 'obs-ffmpeg-mux']
        found = candidates()
        check(len(found) == 1, 'unique owned muxer', candidates=[(p, str(x)) for p, x in found])
        pid, executable = found[0]
        check(executable.resolve() == (APP.parent / 'obs-ffmpeg-mux').resolve(), 'muxer executable belongs to signed bundle')
        names = run('lsof', '-a', '-p', str(pid), '-Fn').decode().splitlines()
        check('n' + record['path'] in names, 'muxer owns the current recording file', pid=pid)
        check(candidates() == found, 'muxer identity immediately before signal')
        return pid

    def failure(self, target):
        name = 'receiver-loss' if target == 'streaming' else 'muxer-loss'
        self.begin_case(name)
        # Reverse startup order also exercises MKV joining an active RTMP.
        stream, receiver = self.start('streaming', name + '-stream-1')
        recording, _ = self.start('recording', name + '-recording-1', transport='cli')
        self.stage('before_fault', self.args.steady_seconds)
        self.active.remove(target)
        self.allowed_faults.add(target)
        self.case['intentionally_failed_targets'] = [target]
        failed_record = stream if target == 'streaming' else recording
        failed_record['expected_partial'] = True
        if target == 'streaming':
            self.case['fault'] = {'kind': 'owned_receiver_SIGTERM', 'pid': receiver.process.pid,
                                  'monotonic': time.monotonic(), 'returncode': receiver.terminate()}
        else:
            helper = self.identify_muxer(recording)
            self.case['fault'] = {'kind': 'owned_muxer_SIGTERM', 'pid': helper,
                                  'monotonic': time.monotonic()}
            os.kill(helper, signal.SIGTERM)
        self.save()
        end = self.wait(lambda s: slots(s)[target]['phase'] == 'error' and not slots(s)[target]['native_busy'])
        failed = slots(end)[target]
        expected = 'OUTPUT_DISCONNECTED' if target == 'streaming' else 'OUTPUT_ENCODE_ERROR'
        check(failed['recovery_required'] and failed['failure']['code'] == expected,
              'real output fault classification', output=failed)
        failed_record.update(ended=failed, terminal_observed=time.monotonic())
        self.stage('other_output_survives_fault')
        denied = self.c.call('start_output', target=target, expect=False)
        check(denied['error']['code'] == 'RECOVERY_REQUIRED', 'explicit recovery is mandatory')
        self.c.call('recover_output_target', target=target, transport='cli')
        self.allowed_faults.remove(target)
        replacement, new_receiver = self.start(target, name + '-recovered', transport='mcp')
        check(replacement['attempt_id'] > failed_record['attempt_id'], 'recovery starts new attempt')
        self.stage('both_after_recovery')
        self.stop(target, replacement, new_receiver, transport='cli')
        self.stage('survivor_after_recovered_stop')
        if target == 'streaming':
            self.stop('recording', recording)
        else:
            self.stop('streaming', stream, receiver)
        self.finish_case()

    def cleanup(self):
        errors = []
        if self.c and self.changed:
            try:
                self.c.call('cancel_all_outputs')
                deadline = time.monotonic() + 50
                while True:
                    state = self.c.state()
                    if all(not item['native_busy'] for item in slots(state).values()):
                        break
                    check(time.monotonic() < deadline, 'cleanup cannot free live workers', outputs=state['outputs'])
                    time.sleep(.2)
                for target in TARGETS:
                    if slots(state)[target]['recovery_required']:
                        self.c.call('recover_output_target', target=target)
                self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
                self.c.call('select_scene', scene_id=self.initial['project']['graph']['active_scene'])
                for scene_id in reversed(self.created_scenes):
                    self.c.call('remove_scene', scene_id=scene_id)
                for source_id in reversed(self.created_sources):
                    self.c.call('remove_source', source_id=source_id)
                if self.tone:
                    self.c.call('remove_audio_input', input_id=self.tone)
                for target in TARGETS:
                    self.c.call('select_output_profile', target=target,
                                profile_id=self.initial['output_configuration'][target + '_profile'])
                for identifier in self.created_profiles:
                    self.c.call('remove_output_profile', id=identifier)
                self.c.call('configure_video', video=self.initial['project'].get('video') or DEFAULT_VIDEO)
                self.c.call('set_variant', variant=self.initial['project']['variant'])
                endpoint = self.initial['output_configuration']['endpoint']
                if endpoint is not None:
                    self.c.call('configure_stream', endpoint=endpoint)
                else:
                    self.report['retained_loopback_endpoint'] = {'transport': 'rtmp', 'port': self.port}
                self.c.call('configure_transition', transition=self.initial['transition_configuration'])
                self.report['cleanup_state'] = self.c.state()
            except BaseException as error:
                errors.append(repr(error))
        for receiver in self.receivers:
            try:
                if receiver.process.poll() is None:
                    receiver.terminate()
            except BaseException as error:
                errors.append(repr(error))
        if self.c:
            try:
                self.c.close()
            except BaseException as error:
                errors.append(repr(error))
        self.observations.close()
        self.report['cleanup_errors'] = errors
        if APP.exists():
            self.report['final_app_sha256'] = sha(APP)
        self.save()


def probe_medium(record, directory, case):
    """Analyze real media; failed files remain distinct from healthy acceptance."""
    path = pathlib.Path(record['path'])
    result = {'ok': False, 'path': str(path), 'expected_partial': record['expected_partial']}
    record['analysis'] = result
    check(path.is_file() and path.stat().st_size > 0, 'media file exists', path=str(path))
    result.update(sha256=sha(path), bytes=path.stat().st_size)
    probe = json.loads(run('ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                           '-show_format', '-of', 'json', str(path), timeout=600))
    result['probe'] = probe
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    check((video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) ==
          ('h264', 1920, 1080, '30/1'), 'decoded H264 1080p30', stream=video)
    check((audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2),
          'decoded AAC stereo 48k', stream=audio)
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'],
                             capture_output=True, timeout=900)
    result['decode'] = {'returncode': decoded.returncode, 'stderr': decoded.stderr.decode()}
    if not record['expected_partial']:
        check(decoded.returncode == 0 and not decoded.stderr, 'full healthy media decode', decode=result['decode'])
    frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames',
             '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path), timeout=600))['frames']
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    check(len(pts) >= 60, 'at least two seconds of decoded video', frames=len(pts))
    gaps = [b-a for a, b in zip(pts, pts[1:])]
    result['video_timeline'] = {'frames': len(pts), 'first_pts': pts[0], 'last_pts': pts[-1],
         'max_interior_gap_s': max(gaps[:-4]), 'max_gap_s': max(gaps),
         'gaps_over_35ms': [{'frame': i+1, 'seconds': gap} for i, gap in enumerate(gaps) if gap > .035]}
    check(min(gaps) > 0 and max(gaps[:-4]) <= .035, '30 FPS interior cadence', timeline=result['video_timeline'])
    # Existing H12 tail limit, explicitly retained and reported; never silently
    # remove those last four intervals from the evidence or call them zero loss.
    check(max(gaps) < .15, 'H12 maximum final video gap', timeline=result['video_timeline'])
    packets = json.loads(run('ffprobe', '-v', 'error', '-show_packets', '-show_entries',
                  'packet=codec_type,pts_time,dts_time', '-of', 'json', str(path), timeout=600))['packets']
    result['packet_timelines'] = {}
    for kind in ('audio', 'video'):
        values = [p for p in packets if p['codec_type'] == kind]
        check(values and all('dts_time' in p for p in values), 'packet DTS present', kind=kind)
        dts = [float(p['dts_time']) for p in values]
        check(all(b > a for a, b in zip(dts, dts[1:])), 'monotonic DTS', kind=kind)
        result['packet_timelines'][kind] = {'packets': len(values), 'first_dts': dts[0], 'last_dts': dts[-1]}
        if kind == 'audio':
            points = [float(p['pts_time']) for p in values]
            agaps = [b-a for a, b in zip(points, points[1:])]
            result['packet_timelines'][kind].update(first_pts=points[0], last_pts=points[-1], max_gap_s=max(agaps))
            check(min(agaps) > 0 and max(agaps) <= .023, 'continuous AAC packet timeline', max_gap=max(agaps))

    def colors(box):
        x, y, width, height = box
        raw = run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vf',
                  f'crop={width*2}:{height*2}:{x*2}:{y*2},scale=1:1',
                  '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-', timeout=600)
        check(len(raw) == len(pts)*3, 'one ROI sample per decoded frame', bytes=len(raw), frames=len(pts))
        return [tuple(raw[i:i+3]) for i in range(0, len(raw), 3)]

    marker, stripe = colors(MARKER_BOX), colors(STRIPE_BOX)
    stages = case['stages']
    frame_stages = [next((s for s in stages if near(color, s['color'])), None) for color in marker]
    # Check the whole decoded audio, including output stop/restart boundaries.
    # Only deliberate gain/mute changes get a 200 ms meter/control transition
    # guard. An output lifecycle event never creates an excluded audio interval.
    audio_frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'a',
        '-read_intervals', '%+0.2', '-show_frames', '-show_entries',
        'frame=best_effort_timestamp_time', '-of', 'json', str(path)))['frames']
    first_audio = float(audio_frames[0]['best_effort_timestamp_time'])
    changes = []
    for i in range(1, len(frame_stages)):
        previous, current = frame_stages[i-1], frame_stages[i]
        if previous and current and (previous['gain_db'], previous['muted']) != (current['gain_db'], current['muted']):
            changes.append(pts[i])
    windows, peak, sample_count = [], 0., 0
    stderr_path = directory / (record['label'] + '-pcm-decode.log')
    with stderr_path.open('wb') as log:
        process = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
            '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'],
            stdout=subprocess.PIPE, stderr=log)
        try:
            while data := process.stdout.read(4800*4):
                samples = array.array('f', data)
                peak = max(peak, max(map(abs, samples)))
                midpoint = first_audio + (sample_count+len(samples)/2)/48000
                sample_count += len(samples)
                index = max(0, min(len(pts)-1, bisect.bisect_right(pts, midpoint)-1))
                stage = frame_stages[index]
                rms = math.sqrt(sum(x*x for x in samples)/len(samples))
                guard = (len(samples) != 4800 or midpoint < pts[0]+.2 or midpoint > pts[-1]-.2
                         or any(abs(midpoint-edge) < .2 for edge in changes) or stage is None)
                windows.append({'pts': midpoint, 'rms_dbfs': db(rms), 'guarded': guard,
                                'stage': stage['name'] if stage else None})
                if not guard:
                    expected = db(.0630957344/math.sqrt(2)) + stage['gain_db']
                    valid = db(rms) < -90 if stage['muted'] else abs(db(rms)-expected) < 1
                    check(valid, 'continuous whole-file audio level', window=windows[-1], expected_dbfs=expected)
            check(process.wait(timeout=30) == 0 or record['expected_partial'], 'whole audio decode exit')
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            result['whole_audio'] = {'samples': sample_count, 'peak_dbfs': db(peak),
                'windows_100ms': windows, 'gain_mute_guard_seconds': .2,
                'decode_log': str(stderr_path)}
    check(db(peak) < -.5, 'whole-file peak has no unexpected clipping', peak_dbfs=db(peak))
    result['stages'] = []
    usable = {}
    for stage in stages:
        if stage['outputs'].get(record['target']) != record['attempt_id']:
            continue
        indices = [i for i, color in enumerate(marker) if near(color, stage['color'])]
        check(len(indices) >= 30, 'native marker stage present in media', stage=stage['name'], frames=len(indices))
        check(indices[-1]-indices[0]+1 == len(indices), 'single contiguous marker stage', stage=stage['name'])
        start, end = pts[indices[0]], pts[indices[-1]]
        check(end-start >= 1.5, 'stable interior audio window', stage=stage['name'], span=end-start)
        middle = (start+end)/2
        # Original PTS are retained with -copyts. The filter's interval therefore
        # refers to this output's decoded marker, not wall-clock polling or the
        # other output's unrelated zero point. Rebase only this trimmed PCM
        # sink before its one-second output limit; otherwise -t 1 would discard
        # every selected interval whose original PTS starts after one second.
        pcm = run('ffmpeg', '-nostdin', '-v', 'error', '-copyts', '-i', str(path), '-vn',
             '-af', f'atrim=start={middle-.5}:end={middle+.5},asetpts=PTS-STARTPTS,pan=mono|c0=c0',
             '-t', '1', '-ar', '48000', '-f', 'f32le', '-', timeout=600)
        samples = array.array('f', pcm)
        check(47900 <= len(samples) <= 48100, 'one second decoded stage audio', samples=len(samples), stage=stage['name'])
        rms = math.sqrt(sum(x*x for x in samples)/len(samples))
        amplitude = tonal_amplitude(samples, 440)
        expected_peak = .0630957344 * 10 ** (stage['gain_db']/20)
        expected_rms_db = db(expected_peak/math.sqrt(2))
        value = {'name': stage['name'], 'first_pts': start, 'last_pts': end, 'frames': len(indices),
                 'gain_db': stage['gain_db'], 'muted': stage['muted'],
                 'rms_dbfs': db(rms), 'tone_peak_dbfs': db(amplitude),
                 'expected_unmuted_rms_dbfs': expected_rms_db,
                 'peak_dbfs': db(max(map(abs, samples))), 'scene': stage['scene']}
        result['stages'].append(value)
        observed = [r['tone_levels']['rms_dbfs'][0] for r in case['samples']
            if stage['response_monotonic']+.4 <= r['monotonic'] <= stage.get('hold_end_monotonic', 0)-.1
            and r['tone_levels']['rms_dbfs'][0] is not None]
        check(observed, 'native meter observations for decoded stage', stage=stage['name'])
        value['native_rms_median_dbfs'] = statistics.median(observed)
        check(abs(value['native_rms_median_dbfs']-expected_rms_db) < 1,
              'post-fader pre-mute native RMS matches tone', stage=value)
        if stage['muted']:
            check(db(rms) < -90, 'mute removes tone in decoded audio', stage=value)
        else:
            check(abs(db(rms)-expected_rms_db) < 1, 'decoded gain matches configured gain', stage=value)
            check(abs(db(amplitude)-db(expected_peak)) < 1, '440 Hz tone amplitude', stage=value)
        check(value['peak_dbfs'] < -.5, 'no unexpected decoded clipping', stage=value)
        block_rms = [math.sqrt(sum(x*x for x in samples[i:i+4800])/4800)
                     for i in range(0, len(samples)-4799, 4800)]
        if not stage['muted']:
            check(all(abs(db(level)-expected_rms_db) < 1 for level in block_rms),
                  'no unmuted 100ms dropout', stage=stage['name'], rms_dbfs=list(map(db, block_rms)))
        tail = indices[-30:]
        check(all(near(stripe[i], SCENE_COLORS[stage['scene']]) for i in tail),
              'decoded final scene color', stage=stage['name'])
        blends = [i for i in indices if not any(near(stripe[i], c) for c in SCENE_COLORS.values())]
        if stage['transition'] == 'cut':
            check(not blends, 'Cut has no blended frames', stage=stage['name'], mixed_frames=len(blends))
        elif stage['transition'] == 'fade':
            distinct = {stripe[i] for i in blends}
            check(len(blends) >= 10 and len(distinct) >= 10, 'Fade has real intermediate colors',
                  stage=stage['name'], mixed_frames=len(blends), distinct=len(distinct))
        value['mixed_frames'] = len(blends)
        usable[stage['name']] = indices

    def crop_frame(stage_name, box, suffix, fraction=.5):
        indices = usable[stage_name]
        index = indices[round((len(indices)-1)*fraction)]
        x, y, width, height = box
        raw = run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vf',
                  f'select=eq(n\\,{index}),crop={width*2}:{height*2}:{x*2}:{y*2},scale={width}:{height}',
                  '-frames:v', '1', '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-', timeout=600)
        check(len(raw) == width*height*3, 'decoded widget frame size')
        filename = directory / (record['label'] + '-' + suffix + '.png')
        png(filename, width, height, raw, channels=3)
        return raw

    def white_difference(left, right):
        def mask(raw):
            return [min(raw[i:i+3]) > 185 and max(raw[i:i+3])-min(raw[i:i+3]) < 55
                    for i in range(0, len(raw), 3)]
        a, b = mask(left), mask(right)
        return {'before_white': sum(a), 'after_white': sum(b), 'changed_mask_pixels': sum(x != y for x, y in zip(a, b))}

    if 'lower_before' in usable:
        left = crop_frame('lower_before', (32, 410, 620, 105), 'lower-before')
        right = crop_frame('lower_after', (32, 410, 620, 105), 'lower-after')
        result['lower_third'] = white_difference(left, right)
        check(min(result['lower_third']['before_white'], result['lower_third']['after_white']) > 100 and
              result['lower_third']['changed_mask_pixels'] > 100, 'lower third text changed in decoded frames',
              measured=result['lower_third'])
        left = crop_frame('countdown_running', (650, 330, 280, 130), 'countdown-running')
        right = crop_frame('countdown_later', (650, 330, 280, 130), 'countdown-later', .8)
        result['countdown'] = white_difference(left, right)
        check(result['countdown']['changed_mask_pixels'] > 50, 'countdown advances in real media', measured=result['countdown'])
        alert = crop_frame('alert_visible', (650, 90, 280, 110), 'alert')
        white = sum(min(alert[i:i+3]) > 185 for i in range(0, len(alert), 3))
        check(white > 100, 'alert glyphs visible', white_pixels=white)
        result['alert_white_pixels'] = white
    if usable:
        first = next(iter(usable))
        left = crop_frame(first, (0, 220, 960, 100), 'motion-before', .2)
        right = crop_frame(first, (0, 220, 960, 100), 'motion-after', .8)
        changed = sum(abs(a-b) > 30 for a, b in zip(left, right))
        check(changed > 1000, 'real moving pattern, not a static image', changed_channels=changed)
        result['motion_changed_channels'] = changed
    result['integrity'] = ('expected_partial_file' if record['expected_partial'] else 'complete_healthy_file')
    result['ok'] = True
    return result


def compare_shared_intervals(report):
    """Compare independently decoded production events, not binary encodings."""
    comparisons = []
    report['shared_interval_comparisons'] = comparisons
    for left, right in itertools.combinations(report['media'], 2):
        if left['case'] != right['case'] or left['target'] == right['target']:
            continue
        if not left.get('analysis', {}).get('ok') or not right.get('analysis', {}).get('ok'):
            continue
        a = {s['name']: s for s in left['analysis']['stages']}
        b = {s['name']: s for s in right['analysis']['stages']}
        shared = [name for name in a if name in b]
        if not shared:
            continue
        offsets = [b[name]['first_pts']-a[name]['first_pts'] for name in shared]
        entry = {'left': left['label'], 'right': right['label'], 'stages': shared,
                 'video_origin_offsets_s': offsets,
                 'origin_drift_s': max(offsets)-min(offsets),
                 'rms_differences_db': {name: b[name]['rms_dbfs']-a[name]['rms_dbfs']
                    for name in shared if not a[name]['muted']}}
        comparisons.append(entry)
        check(entry['origin_drift_s'] <= .035, 'shared visual event timeline stays aligned', comparison=entry)
        check(all(abs(delta) < .5 for delta in entry['rms_differences_db'].values()),
              'both outputs contain the same controlled audio stages', comparison=entry)
    check(comparisons, 'at least one decoded dual-output interval')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lock-held', action='store_true', help='Caller already owns the shared physical/bundle lock')
    parser.add_argument('--stage', choices=('smoke', 'production', 'receiver-loss', 'muxer-loss', 'all'), default='smoke')
    parser.add_argument('--hold-seconds', type=float, default=3.)
    parser.add_argument('--steady-seconds', type=float, default=8.)
    parser.add_argument('--soak-seconds', type=float, default=0.)
    parser.add_argument('--recording-encoder', choices=('auto', 'videotoolbox', 'x264'), default='auto')
    parser.add_argument('--streaming-encoder', choices=('auto', 'videotoolbox', 'x264'), default='auto')
    args = parser.parse_args()
    if not args.lock_held:
        parser.error('--lock-held is required; this script does not acquire another lock')
    if not math.isfinite(args.hold_seconds) or args.hold_seconds < 2:
        parser.error('--hold-seconds must be finite and >=2')
    if not math.isfinite(args.steady_seconds) or args.steady_seconds < 4:
        parser.error('--steady-seconds must be finite and >=4')
    if not math.isfinite(args.soak_seconds) or not 0 <= args.soak_seconds <= 7200:
        parser.error('--soak-seconds must be finite and 0..7200')
    directory = ROOT / 'var/evidence' / ('h13-outputs-' + str(time.time_ns()))
    directory.mkdir(parents=True)
    report = {'ok': False, 'run': str(directory), 'arguments': vars(args), 'cases': [], 'media': [],
              'limits': ['Pattern/tone fixture does not verify capture devices or system audio.',
                         'This script operates CLI/MCP; GPUI acceptance is a separate gate.',
                         'Expected partial files after injected faults do not prove clean finalization.',
                         'H12 final-tail video limit is retained; all gaps are reported.']}
    suite = Suite(args, directory, report)
    print(directory, flush=True)
    try:
        suite.open()
        if args.stage in ('smoke', 'all'):
            suite.healthy()
        if args.stage in ('production', 'all'):
            suite.healthy(production=True)
        if args.stage in ('receiver-loss', 'all'):
            suite.failure('streaming')
        if args.stage in ('muxer-loss', 'all'):
            suite.failure('recording')
    except BaseException as error:
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        suite.cleanup()
        analysis_errors = []
        for record in suite.media:
            try:
                case = next(c for c in report['cases'] if c['name'] == record['case'])
                probe_medium(record, directory, case)
            except BaseException as error:
                record.setdefault('analysis', {})['error'] = repr(error)
                analysis_errors.append({'label': record['label'], 'error': repr(error)})
            suite.save()
        report['analysis_errors'] = analysis_errors
        try:
            compare_shared_intervals(report)
        except BaseException as error:
            analysis_errors.append({'label': 'shared_intervals', 'error': repr(error)})
        report['ok'] = (not report.get('error') and not report['cleanup_errors'] and not analysis_errors
                        and bool(report['cases']) and all(case['ok'] for case in report['cases'])
                        and report.get('app_sha256') == report.get('final_app_sha256'))
        report['observations_sha256'] = sha(directory / 'observations.jsonl')
        suite.save()
    print(json.dumps({'ok': report['ok'], 'report': str(directory / 'report.json'),
                      'error': report.get('error'), 'analysis_errors': report['analysis_errors'],
                      'cleanup_errors': report['cleanup_errors']}, indent=2), flush=True)
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
