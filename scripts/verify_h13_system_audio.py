#!/usr/bin/env python3
"""Real H13 system-audio trials against the already running signed studio.

Caller owns the canonical shared physical-test lock; this script never takes
over a lock, builds/signs, changes permissions/routing, or launches Motive.
Build the separate owned fixture beforehand with fixtures/build_h13_audio_app.py.
Default: a small MKV pilot with application + 440 Hz tone and live gain/mute.
Repeat --stage to add independent trials; --microphone-id is required only for
the microphone stage. Failed evidence is retained in a unique directory.

The fixture produces actual OS output. Its loudness follows the user's existing
output device/volume. No claim of Motive self-audio exclusion is made: there is
no owned emitter inside the Motive process in this verifier.
"""
import argparse
import array
import hashlib
import json
import math
import pathlib
import socket
import statistics
import subprocess
import time

from h7_support import Client, EVIDENCE, EXE, ROOT, process_sample
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
from verify_h10_audio import power, tonal_amplitude

BUNDLE = 'local.motive.audiofixture'
FIXTURE = ROOT / 'target/H13AudioFixture.app/Contents/MacOS/MotiveAudioFixture'
STAGES = ('pilot', 'rtmp', 'recovery', 'silence', 'transitions', 'persistence', 'microphone', 'av')


def db(value):
    return 20 * math.log10(max(value, 1e-15))


def input_state(state, ident):
    return next(i for i in state['audio_mixer']['runtime']['inputs'] if i['id'] == ident)


def output_active(state, kind):
    # Single-output compatibility commands deliberately remain under test.
    return state['output'] == kind


class Run:
    def __init__(self, args):
        self.args = args
        self.path = EVIDENCE / f'h13-system-audio-{time.time_ns()}'
        self.path.mkdir(parents=True)
        self.report = dict(ok=False, run=str(self.path), requested_stages=args.stage,
            trials=[], fixture_runs=[], own_process_exclusion='not tested: no Motive-process OS emitter',
            physical_unplug='not tested: application quit/relaunch and explicit input recovery only')
        self.client = None
        self.fixture = None
        self.receiver = None
        self.created_audio = []
        self.created_scenes = []
        self.created_sources = []
        self.initial = None
        self.audio_saved_before = None
        self.audio_save_changed = False

    def save(self):
        if self.client:
            self.report['mcp'] = self.client.ops
        (self.path / 'report.json').write_text(json.dumps(self.report, indent=2))

    def cli(self, op, expect=True, **fields):
        request = dict(op=op, **fields)
        proc = subprocess.run([str(EXE), 'ctl', json.dumps(request)], capture_output=True, text=True, timeout=20)
        response = json.loads(proc.stdout)
        self.report.setdefault('cli', []).append(dict(request=request, response=response))
        assert response['ok'] == expect, response
        return response

    def wait(self, predicate, timeout=15):
        return self.client.wait(predicate, timeout)

    def launch_fixture(self, sequence=False):
        assert self.fixture is None or self.fixture.poll() is not None
        assert FIXTURE.is_file(), f'Build the owned fixture first: {FIXTURE}'
        number = len(self.report['fixture_runs'])
        stdout = self.path / f'fixture-{number}.jsonl'
        stderr = self.path / f'fixture-{number}.stderr.log'
        arguments = [str(FIXTURE)] + (['--sequence'] if sequence else [])
        snapshot_dir = None
        if self.args.fixture_snapshots:
            snapshot_dir = self.path / f'fixture-{number}-local-view'
            snapshot_dir.mkdir()
            arguments += ['--snapshot-dir', str(snapshot_dir)]
        with stdout.open('xb') as out, stderr.open('xb') as err:
            self.fixture = subprocess.Popen(arguments, stdout=out, stderr=err)
        entry = dict(pid=self.fixture.pid, sequence=sequence, stdout=str(stdout), stderr=str(stderr), launched=time.monotonic())
        if snapshot_dir:
            entry['local_view_snapshots'] = dict(path=str(snapshot_dir), redraws_view=True,
                proves_windowserver_publication=False)
        self.report['fixture_runs'].append(entry)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            assert self.fixture.poll() is None, entry
            lines = stdout.read_text().splitlines()
            events = [json.loads(line) for line in lines if line.endswith('}')]
            if any(e['event'] == 'ready' for e in events) and (not sequence or any(e['event'] == 'sequence' for e in events)):
                entry['events'] = events
                if sequence:
                    entry['sequence_start'] = next(e['uptime_seconds'] for e in events if e['event'] == 'sequence')
                    assert abs(time.monotonic() - entry['sequence_start']) < 5, 'Fixture/script monotonic clocks differ'
                return entry
            time.sleep(.1)
        raise AssertionError(dict(fixture_start_timeout=entry))

    def stop_fixture(self):
        if self.fixture and self.fixture.poll() is None:
            self.fixture.terminate()
            self.fixture.wait(timeout=8)

    def inventory(self):
        result = self.client.call('system_audio_sources')
        assert result['pid'] == self.initial['pid']
        return result['system_audio_sources']

    def wait_fixture_selectable(self):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            inventory = self.inventory()
            assert inventory['available'] and inventory['permission'] == 'authorized', inventory
            found = [a for a in inventory['applications'] if a['bundle_id'] == BUNDLE]
            if len(found) == 1 and found[0]['selectable']:
                return inventory
            time.sleep(.2)
        raise AssertionError(dict(fixture_not_selectable=inventory))

    def add_audio(self, name, source):
        before = {i['id'] for i in self.client.state()['audio_mixer']['store']['inputs']}
        state = self.client.call('add_audio_input', name=name, source=source)['state']
        ident = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['id'] not in before)
        self.created_audio.append(ident)
        return ident

    def new_scene(self, name, source):
        scene = self.client.call('create_scene', name=name)['state']['project']['graph']['active_scene']
        self.created_scenes.append(scene)
        before = {s['id'] for s in self.client.state()['project']['graph']['sources']}
        graph = self.client.call('add_source', scene_id=scene, name=name, source=source)['state']['project']['graph']
        ident = next(s['id'] for s in graph['sources'] if s['id'] not in before)
        self.created_sources.append(ident)
        layer = next(l['id'] for s in graph['scenes'] if s['id'] == scene for l in s['layers'] if l['source_id'] == ident)
        for variant, dimensions in [('horizontal', (960, 540)), ('vertical', (540, 960))]:
            self.client.call('set_transform', scene_id=scene, layer_id=layer, variant=variant,
                transform=dict(x=0, y=0, width=dimensions[0], height=dimensions[1], order=0, visible=True))
        return scene

    def setup(self):
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        if not common.is_absolute():
            common = ROOT / common
        lock = self.args.lock_dir or common.resolve().parent / 'var/run/physical-test.lock'
        owner = (lock / 'OWNER').read_text()
        self.report['shared_lock'] = dict(path=str(lock.resolve()), owner=owner)
        assert VERIFY.lock_matches(owner), 'Caller must hold the canonical physical lock for this worktree'
        self.client = Client()
        self.initial = self.client.state()
        self.report['initial'] = self.initial
        assert self.initial['output'] == 'idle' and not self.initial['audio_mixer']['store']['inputs'], 'An idle studio with an empty mixer is required'
        self.report['binary_sha256'] = hashlib.sha256((VERIFY.app_executable).read_bytes()).hexdigest()
        self.report['fixture_sha256'] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.report['script_sha256'] = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        self.report['ffmpeg'] = subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]
        tools = {t['name']: t for t in self.client.rpc('tools/list')['tools']}
        assert tools['system_audio_sources']['annotations']['readOnlyHint']
        self.launch_fixture()
        inventory = self.wait_fixture_selectable()
        self.report['inventory'] = inventory
        self.tone = self.add_audio('H13 controlled 440 Hz', dict(kind='tone'))
        self.system = self.add_audio('H13 owned application', dict(kind='system_application', bundle_id=BUNDLE))
        self.wait(lambda s: all(input_state(s, i)['phase'] == 'ready' for i in (self.system, self.tone)))
        before = self.client.state()
        self.client.call('add_audio_input', name='Reuse owned application', source=dict(kind='system_application', bundle_id=BUNDLE))
        after = self.client.state()
        assert after['audio_mixer']['store'] == before['audio_mixer']['store']
        assert after['audio_mixer']['runtime']['instances_created'] == before['audio_mixer']['runtime']['instances_created']
        shared = self.cli('audio_mixer')
        assert shared['pid'] == before['pid'] and shared['audio_mixer']['store'] == before['audio_mixer']['store']
        desktops = [d for d in inventory['displays'] if d['selectable']]
        assert len(desktops) == 1, inventory
        rejected = self.cli('add_audio_input', expect=False, name='Forbidden overlap',
            source=dict(kind='system_desktop', display_uuid=desktops[0]['display_uuid']))
        assert rejected['error']['code'] == 'AUDIO_CAPTURE_OVERLAP', rejected
        assert self.client.state()['audio_mixer']['store'] == before['audio_mixer']['store']
        assert self.cli('set_audio_gain', expect=False, input_id=self.tone, gain_db=25)['error']['code'] == 'INVALID_AUDIO_GAIN'
        self.scene = self.new_scene('H13 owned audio verification', dict(kind='pattern'))
        self.client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
        self.client.call('select_scene', scene_id=self.scene)
        self.save()

    def controls(self):
        for ident in (self.system, self.tone):
            self.client.call('set_audio_gain', input_id=ident, gain_db=-6)
            self.client.call('set_audio_mute', input_id=ident, muted=False)

    def listen(self, trial):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        path = self.path / f'{trial["name"]}.flv'
        log = self.path / f'{trial["name"]}-receiver.log'
        with log.open('xb') as stderr:
            self.receiver = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'info', '-listen', '1', '-i',
                f'rtmp://127.0.0.1:{port}/live/motive', '-c', 'copy', str(path)], stdout=subprocess.DEVNULL, stderr=stderr)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert self.receiver.poll() is None, str(log)
            if subprocess.run(['lsof', '-a', '-p', str(self.receiver.pid), '-iTCP:' + str(port), '-sTCP:LISTEN'], capture_output=True).returncode == 0:
                self.client.call('configure_stream', endpoint=dict(transport='rtmp', port=port))
                return path
            time.sleep(.1)
        raise AssertionError('Owned local RTMP receiver did not listen')

    def start_trial(self, name, stream=False):
        self.controls()
        trial = dict(name=name, stages=[], events=[], before=self.client.state())
        self.report['trials'].append(trial)
        path = self.listen(trial) if stream else None
        started = self.client.call('start_stream' if stream else 'start_recording')['state']
        self.kind = 'streaming' if stream else 'recording'
        started = self.wait(lambda s: output_active(s, self.kind))
        trial.update(started=started, origin=time.monotonic(), path=str(path or started['output_path']))
        self.current = trial
        self.tone_instance = input_state(started, self.tone)['instance_id']
        self.last_encoded_frames = started['stats']['encoded_frames']
        self.previous_cpu, _ = process_sample(started['pid'])
        self.previous_time = time.monotonic()
        self.save()
        return trial

    def sample(self):
        state = self.client.state()
        now = time.monotonic()
        cpu, rss = process_sample(state['pid'])
        assert state['pid'] == self.initial['pid'] and output_active(state, self.kind), state
        assert input_state(state, self.tone)['instance_id'] == self.tone_instance
        assert state['transition']['source_instances_created'] == self.current['started']['transition']['source_instances_created']
        assert state['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0
        assert state['output_path'] == self.current['started']['output_path']
        assert state['stats']['encoded_frames'] >= self.last_encoded_frames
        self.last_encoded_frames = state['stats']['encoded_frames']
        observation = dict(seconds=now-self.current['origin'], state=state,
            cpu_percent=100*(cpu-self.previous_cpu)/(now-self.previous_time), rss_mib=rss)
        self.previous_cpu, self.previous_time = cpu, now
        return observation

    def hold(self, name, seconds=3.3):
        stage = dict(name=name, start=time.monotonic()-self.current['origin'], samples=[])
        self.current['stages'].append(stage)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(.18)
            stage['samples'].append(self.sample())
        stage['end'] = time.monotonic()-self.current['origin']
        self.save()
        return stage

    def finish_trial(self):
        trial = self.current
        trial['stop'] = self.client.stop()
        assert trial['stop']['end']['output'] == 'idle' and trial['stop']['end']['output_code'] == 0
        if self.receiver:
            assert self.receiver.wait(timeout=15) == 0
            self.receiver = None
        observations = [v for stage in trial['stages'] for v in stage['samples']]
        trial['performance'] = dict(cpu_median=statistics.median(v['cpu_percent'] for v in observations),
            rss_peak_mib=max(v['rss_mib'] for v in observations))
        trial['counter_delta'] = {key: trial['stop']['end']['stats'][key]-trial['before']['stats'][key]
            for key in ('lagged_frames', 'video_skipped_frames', 'rendered_frames')}
        trial['max_output_dropped_frames'] = max(v['state']['stats']['output_dropped_frames'] for v in observations)
        media, samples = analyse_media(pathlib.Path(trial['path']), self.path / trial['name'])
        trial['media'] = media
        for stage in trial['stages']:
            if stage['end']-stage['start'] >= 2.3:
                segment = samples[round((stage['start']+1)*48000):round((stage['start']+2)*48000)]
                assert len(segment) == 48000, stage['name']
                stage['decoded'] = dict(rms_dbfs=db(math.sqrt(sum(x*x for x in segment)/len(segment))),
                    peak_dbfs=db(max(abs(x) for x in segment)), a440=tonal_amplitude(segment, 440), a997=tonal_amplitude(segment, 997))
        self.save()
        assert trial['counter_delta']['lagged_frames'] == 0 and trial['counter_delta']['video_skipped_frames'] == 0 and trial['max_output_dropped_frames'] == 0, trial['counter_delta']
        return trial, samples

    def pilot(self, stream=False):
        self.start_trial('rtmp' if stream else 'pilot', stream)
        self.hold('both')
        self.cli('set_audio_gain', input_id=self.tone, gain_db=-18)
        self.hold('tone_lower')
        self.client.call('set_audio_mute', input_id=self.system, muted=True)
        self.hold('system_muted')
        self.cli('set_audio_mute', input_id=self.system, muted=False)
        self.hold('system_unmuted')
        self.client.call('set_audio_gain', input_id=self.system, gain_db=-18)
        self.hold('system_lower')
        self.cli('set_audio_gain', input_id=self.system, gain_db=-6)
        self.client.call('set_audio_mute', input_id=self.tone, muted=True)
        self.hold('tone_muted')
        self.cli('set_audio_mute', input_id=self.system, muted=True)
        self.hold('both_muted')
        trial, samples = self.finish_trial()
        stages = {s['name']: s for s in trial['stages']}
        r = {k: s['decoded'] for k, s in stages.items()}
        assert min(r['both']['a440'], r['both']['a997']) > .005, r['both']
        trial['gain_delta_db'] = dict(tone=db(r['tone_lower']['a440']/r['both']['a440']),
            system=db(r['system_lower']['a997']/r['system_unmuted']['a997']))
        assert all(-13 < delta < -11 for delta in trial['gain_delta_db'].values()), trial['gain_delta_db']
        assert r['system_muted']['a997'] < r['tone_lower']['a997']*.02
        assert r['system_unmuted']['a997'] > r['both']['a997']*.8
        assert abs(db(r['system_muted']['a440']/r['tone_lower']['a440'])) < .6
        assert r['tone_muted']['a440'] < r['tone_lower']['a440']*.03
        assert r['both_muted']['rms_dbfs'] < -95
        trial['isolated_meters'] = {name: meter_compare(samples, stages[name], ident)
            for name, ident in [('system_muted', self.tone), ('tone_muted', self.system)]}
        for value in trial['isolated_meters'].values():
            assert abs(value['rms_error_db']) < 2 and abs(value['peak_error_db']) < 2, value
        trial['ok'] = True
        self.save()

    def recovery(self):
        trial = self.start_trial('recovery')
        self.hold('both')
        old_pid = self.fixture.pid
        previous_instance = input_state(self.client.state(), self.system)['instance_id']
        self.stop_fixture()
        self.wait(lambda s: input_state(s, self.system)['phase'] == 'failed')
        self.hold('application_absent')
        self.launch_fixture()
        assert self.fixture.pid != old_pid
        self.wait_fixture_selectable()
        still_failed = self.client.state()
        assert input_state(still_failed, self.system)['phase'] == 'failed'
        assert input_state(still_failed, self.system)['instance_id'] == previous_instance
        self.hold('relaunch_not_automatically_recovered')
        self.cli('reconnect_audio_input', input_id=self.system)
        self.wait(lambda s: input_state(s, self.system)['phase'] == 'ready')
        assert input_state(self.client.state(), self.system)['instance_id'] != previous_instance
        self.hold('recovered')
        trial, samples = self.finish_trial()
        r = {s['name']: s['decoded'] for s in trial['stages']}
        for name in ('application_absent', 'relaunch_not_automatically_recovered'):
            assert r[name]['a997'] < r['both']['a997']*.02
        assert r['recovered']['a997'] > r['both']['a997']*.8
        trial['tone_continuity'] = tone_continuity(samples, trial['stages'], r['both']['a440'])
        trial['old_pid'], trial['new_pid'], trial['ok'] = old_pid, self.fixture.pid, True
        self.save()

    def restart_sequence(self):
        self.stop_fixture()
        self.wait(lambda s: input_state(s, self.system)['phase'] == 'failed')
        fixture = self.launch_fixture(sequence=True)
        self.wait_fixture_selectable()
        self.client.call('reconnect_audio_input', input_id=self.system)
        self.wait(lambda s: input_state(s, self.system)['phase'] == 'ready')
        return fixture

    def silence(self, av=False):
        fixture = self.restart_sequence()
        owned_window = None
        if av:
            windows = self.client.call('devices')['devices']['windows']
            owned = [w for w in windows if w['pid'] == self.fixture.pid and w['bundle_id'] == BUNDLE and w['name'] == 'Motive controlled audio fixture']
            assert len(owned) == 1, dict(owned_fixture_windows=owned)
            owned_window = self.new_scene('H13 owned A/V fixture', dict(kind='window', window_id=owned[0]['id']))
            self.client.call('select_scene', scene_id=owned_window)
        trial = self.start_trial('av' if av else 'silence')
        trial['fixture_sequence_start'] = fixture['sequence_start']
        # Preserve all runtime samples by fixture phase, including zero/paused
        # buffers. Do not assume SCK necessarily emits or suppresses silence.
        for name, end in [('tone', 8), ('zero_buffers', 12), ('engine_paused', 16), ('tone_resumed', 24), ('pulses', 32), ('tail', 36)]:
            remaining = fixture['sequence_start'] + end - time.monotonic()
            assert remaining > .2, dict(sequence_setup_too_slow=name, remaining=remaining)
            self.hold(name, remaining)
        trial, samples = self.finish_trial()
        stages = {s['name']: s for s in trial['stages']}
        reference = stages['tone_resumed']['decoded']['a997']
        assert reference > .005
        for name in ('zero_buffers', 'engine_paused'):
            assert stages[name]['decoded']['a997'] < reference*.03, stages[name]['decoded']
        observations = [input_state(v['state'], self.system) for name in ('zero_buffers', 'engine_paused') for v in stages[name]['samples'][5:]]
        awaiting = [v for v in observations if v['phase'] == 'awaiting_audio']
        assert all(v['levels']['stale'] and v['issue'] == 'SYSTEM_AUDIO_NO_SAMPLES' for v in awaiting)
        ready_zeros = [v for v in observations if v['phase'] == 'ready' and not v['levels']['stale'] and all(x is None or x < -85 for x in v['levels']['rms_dbfs'])]
        trial['silence_observations'] = dict(awaiting_audio_observed=bool(awaiting), measured_zero_buffers_observed=bool(ready_zeros),
            awaiting_count=len(awaiting), measured_zero_count=len(ready_zeros),
            explanation='Engine paused does not promise missing SCK packets. Coverage follows actual callbacks; absent coverage remains pending.')
        if not awaiting:
            self.report.setdefault('pending_coverage', []).append('SCK did not exhibit awaiting_audio during the owned zero/pause intervals')
        if not ready_zeros:
            self.report.setdefault('pending_coverage', []).append('SCK did not deliver measured zero buffers during the owned zero/pause intervals')
        trial['tone_continuity'] = tone_continuity(samples, trial['stages'], .0316227766)
        if av:
            trial['av_pulses'] = analyse_pulses(pathlib.Path(trial['path']), samples, stages['pulses'], trial['media'])
            self.client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
            self.client.call('select_scene', scene_id=self.scene)
        trial['ok'] = True
        self.save()

    def transitions(self):
        a = self.new_scene('H13 mint audio continuity', dict(kind='overlay', color=0x33e8b5))
        b = self.new_scene('H13 red audio continuity', dict(kind='overlay', color=0xe83e4b))
        self.client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
        self.client.call('select_scene', scene_id=a)
        trial = self.start_trial('transitions')
        self.hold('both')
        for number, (kind, scene) in enumerate([('cut', b), ('cut', a), ('fade', b), ('fade', a)]):
            self.client.call('configure_transition', transition=dict(kind=kind, duration_ms=1000 if kind == 'fade' else 0))
            response = self.client.call('select_scene', scene_id=scene)
            trial['events'].append(dict(kind=kind, scene=scene, seconds=time.monotonic()-trial['origin'], response=response))
            self.hold(f'{kind}_{number}', 2.4)
        trial, samples = self.finish_trial()
        trial['tone_continuity'] = tone_continuity(samples, trial['stages'], trial['stages'][0]['decoded']['a440'])
        trial['video_colors'] = analyse_transition_colors(trial['path'], trial['media'])
        assert all(s['decoded']['a997'] > .02 for s in trial['stages'])
        trial['ok'] = True
        self.client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
        self.client.call('select_scene', scene_id=self.scene)
        self.save()

    def persistence(self):
        project = self.client.state()['project']
        profiles = self.client.call('output_profiles')['store']
        immutable = {name: (VERIFY.data_root/name).read_bytes() if (VERIFY.data_root/name).exists() else None for name in ('project.json', 'output-profiles.json')}
        path = VERIFY.data_root / 'audio-mixer.json'
        self.audio_saved_before = path.read_bytes() if path.exists() else None
        saved = self.client.call('save_audio_mixer')['state']['audio_mixer']['store']
        self.audio_save_changed = True
        assert saved['version'] == 2
        instances = self.client.state()['audio_mixer']['runtime']['instances_created']
        self.client.call('set_audio_gain', input_id=self.tone, gain_db=-30)
        restored = self.cli('load_audio_mixer')['state']
        assert restored['audio_mixer']['store'] == saved and restored['audio_mixer']['runtime']['instances_created'] == instances
        # Reordered newly assigned IDs must reuse the two captures on restore.
        for item in saved['inputs']:
            self.client.call('remove_audio_input', input_id=item['id'])
        self.created_audio.clear()
        for item in reversed(saved['inputs']):
            self.add_audio(item['name'], item['source'])
        instances = self.client.state()['audio_mixer']['runtime']['instances_created']
        restored = self.client.call('load_audio_mixer')['state']
        self.created_audio = [i['id'] for i in saved['inputs']]
        assert restored['audio_mixer']['store'] == saved and restored['audio_mixer']['runtime']['instances_created'] == instances
        assert restored['project'] == project and self.client.call('output_profiles')['store'] == profiles
        for name, data in immutable.items():
            candidate = VERIFY.data_root/name
            assert (candidate.read_bytes() if candidate.exists() else None) == data
        self.wait(lambda s: all(input_state(s, i)['phase'] == 'ready' for i in (self.system, self.tone)))
        trial = self.start_trial('persistence')
        self.hold('restored_audio')
        trial, _ = self.finish_trial()
        decoded = trial['stages'][0]['decoded']
        assert min(decoded['a440'], decoded['a997']) > .005
        trial.update(saved=saved, restored=restored, project_and_profiles_unchanged=True, ok=True)
        self.save()

    def microphone(self):
        mic = self.add_audio('H13 explicit physical microphone', dict(kind='microphone', device_id=self.args.microphone_id))
        self.client.call('set_audio_gain', input_id=mic, gain_db=self.args.microphone_gain)
        self.wait(lambda s: input_state(s, mic)['phase'] == 'ready')
        self.start_trial('microphone')
        self.hold('mixed')
        self.client.call('set_audio_mute', input_id=self.system, muted=True)
        self.hold('microphone_isolated')
        self.cli('set_audio_mute', input_id=mic, muted=True)
        self.hold('both_capture_paths_muted')
        self.client.call('set_audio_mute', input_id=self.system, muted=False)
        self.hold('system_isolated')
        self.cli('set_audio_mute', input_id=mic, muted=False)
        self.hold('mixed_again')
        trial, samples = self.finish_trial()
        r = {s['name']: s['decoded'] for s in trial['stages']}
        floor = max(r['both_capture_paths_muted']['a997'], 1e-7)
        assert r['microphone_isolated']['a997'] > max(1e-5, floor*10), 'Known fixture is not audible in the selected physical microphone'
        assert r['system_isolated']['a997'] > .005 and r['mixed_again']['a997'] > floor*10
        trial['tone_continuity'] = tone_continuity(samples, trial['stages'], r['mixed']['a440'])
        trial.update(microphone_uid=self.args.microphone_id, acoustic_recapture='intentional owned fixture for this physical test only', ok=True)
        self.client.call('remove_audio_input', input_id=mic)
        self.created_audio.remove(mic)
        self.save()

    def cleanup(self):
        # Preserve the failure before any potentially failing cleanup action.
        self.save()
        if self.client:
            try:
                state = self.client.state()
                if state['output'] not in ('idle', 'error'):
                    self.client.stop()
                if self.client.state()['output'] == 'idle':
                    self.client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
                    if self.initial:
                        self.client.call('select_scene', scene_id=self.initial['project']['graph']['active_scene'])
                    for scene in reversed(self.created_scenes):
                        self.client.call('remove_scene', scene_id=scene)
                    for source in reversed(self.created_sources):
                        self.client.call('remove_source', source_id=source)
                    live = {i['id'] for i in self.client.state()['audio_mixer']['store']['inputs']}
                    for ident in self.created_audio:
                        if ident in live:
                            self.client.call('remove_audio_input', input_id=ident)
                    if self.initial:
                        self.client.call('configure_transition', transition=self.initial['transition_configuration'])
                if self.audio_save_changed:
                    path = VERIFY.data_root / 'audio-mixer.json'
                    if self.audio_saved_before is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(self.audio_saved_before)
            except BaseException as error:
                self.report['cleanup_error'] = repr(error)
                self.report['ok'] = False
        try:
            self.stop_fixture()
        except BaseException as error:
            self.report['fixture_cleanup_error'] = repr(error)
            self.report['ok'] = False
        try:
            if self.receiver and self.receiver.poll() is None:
                self.receiver.terminate()
                self.receiver.wait(timeout=8)
        except BaseException as error:
            self.report['receiver_cleanup_error'] = repr(error)
            self.report['ok'] = False
        self.save()
        if self.client:
            try:
                self.client.close()
            except BaseException as error:
                self.report['mcp_cleanup_error'] = repr(error)
                self.report['ok'] = False
                self.save()


def analyse_media(path, output):
    output.mkdir()
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert audio['codec_name'] == 'aac' and audio['sample_rate'] == '48000' and audio['channels'] == 2
    numerator, denominator = map(int, video['avg_frame_rate'].split('/'))
    fps = numerator/denominator
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, timeout=180)
    (output/'decode.stderr').write_bytes(decoded.stderr)
    assert decoded.returncode == 0 and not decoded.stderr, decoded.stderr
    frame_data = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)])
    packet_data = subprocess.check_output(['ffprobe', '-v', 'error', '-show_packets', '-show_entries', 'packet=codec_type,pts_time,dts_time', '-of', 'json', str(path)])
    (output/'video-pts.json').write_bytes(frame_data)
    (output/'packet-pts.json').write_bytes(packet_data)
    vpts = [float(f['best_effort_timestamp_time']) for f in json.loads(frame_data)['frames']]
    packets = json.loads(packet_data)['packets']
    apts = [float(p['pts_time']) for p in packets if p['codec_type'] == 'audio']
    for kind in ('audio', 'video'):
        dts = [float(p['dts_time']) for p in packets if p['codec_type'] == kind and 'dts_time' in p]
        assert len(dts) > 1 and all(b > a for a, b in zip(dts, dts[1:])), kind
    vgaps = [b-a for a, b in zip(vpts, vpts[1:])]
    agaps = [b-a for a, b in zip(apts, apts[1:])]
    assert min(agaps) > 0 and max(agaps) <= .023, max(agaps)
    assert min(vgaps) > 0 and max(vgaps[:-4]) < 1.5/fps and max(vgaps) < .15, max(vgaps)
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'])
    samples = array.array('f')
    samples.frombytes(raw)
    peak = max(abs(x) for x in samples)
    assert peak < .98, dict(unexpected_clipping_peak=peak)
    media = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), probe=probe, fps=fps,
        duration=len(samples)/48000, peak_dbfs=db(peak), frames=len(vpts), audio_packets=len(apts),
        video_first_pts=vpts[0], video_last_pts=vpts[-1], audio_first_pts=apts[0], audio_last_pts=apts[-1],
        max_video_gap=max(vgaps), max_interior_video_gap=max(vgaps[:-4]), tail_video_gaps=vgaps[-4:],
        max_audio_gap=max(agaps), av_start_pts_delta=apts[0]-vpts[0], av_end_pts_delta=apts[-1]-vpts[-1],
        decoded_video_pts=vpts)
    return media, samples


def analyse_transition_colors(path, media):
    # The legacy overlay is a 320x72 dark plate with a SIX-pixel accent stripe.
    # Averaging the whole frame cannot recover that stripe's configured color.
    # Probe its interior after the same contain transform used by the scene.
    video = next(s for s in media['probe']['streams'] if s['codec_type'] == 'video')
    width, height = video['width'], video['height']
    scale = min(width/320, height/72)
    x = round((width-320*scale)/2+2*scale)
    y = round((height-72*scale)/2+8*scale)
    box = (max(1, round(2*scale)), max(1, round(56*scale)), x, y)
    crop = ':'.join(map(str, box))
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
        '-vf', f'format=rgb24,crop={crop},scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    colors = [list(raw[i:i+3]) for i in range(0, len(raw), 3)]
    def near(color, target): return max(abs(x-y) for x, y in zip(color, target)) < 35
    mint = sum(near(c, (51, 232, 181)) for c in colors)
    red = sum(near(c, (232, 62, 75)) for c in colors)
    blends = {tuple(c) for c in colors if not near(c, (51, 232, 181)) and not near(c, (232, 62, 75))}
    assert mint >= 20 and red >= 20 and len(blends) >= 10, (mint, red, len(blends))
    return dict(probe_box=box, mint_frames=mint, red_frames=red, distinct_blends=len(blends), colors=colors)


def meter_compare(samples, stage, ident):
    observations = stage['samples'][5:]
    native = [input_state(v['state'], ident)['levels'] for v in observations]
    assert all(not level['stale'] and level['rms_dbfs'][0] is not None for level in native)
    lo, hi = observations[0]['seconds'], observations[-1]['seconds']
    blocks = [samples[i:i+960] for i in range(round(lo*48000), round(hi*48000)-959, 960)]
    rms = [db(math.sqrt(sum(x*x for x in b)/len(b))) for b in blocks]
    peaks = [db(max(abs(x) for x in b)) for b in blocks]
    native_rms = statistics.median(v['rms_dbfs'][0] for v in native)
    native_peak = statistics.median(v['peak_dbfs'][0] for v in native)
    return dict(native_rms_dbfs=native_rms, decoded_rms_dbfs=statistics.median(rms),
        rms_error_db=statistics.median(rms)-native_rms, peak_error_db=statistics.median(peaks)-native_peak,
        native_levels=native, decoded_block_rms=rms, decoded_block_peak=peaks, block_ms=20)


def tone_continuity(samples, stages, reference):
    result = {}
    for stage in stages:
        lo, hi = round((stage['start']+.2)*48000), round((stage['end']-.2)*48000)
        amplitudes = [power(samples[i:i+4800], 440) for i in range(lo, hi-4799, 4800)]
        assert amplitudes and min(amplitudes) > reference*.65, dict(stage=stage['name'], minimum=min(amplitudes, default=0), reference=reference)
        result[stage['name']] = dict(minimum=min(amplitudes), maximum=max(amplitudes), windows=len(amplitudes))
    return result


def analyse_pulses(path, samples, stage, media):
    # Sample a left-side fixture background patch, clear of controlled text.
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
        '-vf', 'crop=8:8:iw*0.02:ih*0.5,scale=1:1', '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    colors = [tuple(raw[i:i+3]) for i in range(0, len(raw), 3)]
    pts = media['decoded_video_pts']
    assert len(colors) == len(pts)
    video_edges = []
    previous = False
    for pts_value, color in zip(pts, colors):
        on = color[1] > 70 and color[1] > color[0]*1.5
        seconds = pts_value-media['video_first_pts']
        if on and not previous and stage['start']+.4 < seconds < stage['end']-.4:
            video_edges.append(seconds)
        previous = on
    audio_edges = []
    previous = False
    # 20 ms narrow-band projection keeps continuous 440 Hz from looking like a
    # fixture pulse. This analyses recorded PCM; it never mixes product audio.
    for offset in range(round((stage['start']+.3)*48000), round((stage['end']-.3)*48000)-959, 960):
        block = samples[offset:offset+960]
        re = sum(x*math.cos(2*math.pi*997*i/48000) for i, x in enumerate(block))
        im = sum(x*math.sin(2*math.pi*997*i/48000) for i, x in enumerate(block))
        on = 2*math.hypot(re, im)/len(block) > .015
        if on and not previous:
            audio_edges.append(offset/48000)
        previous = on
    assert len(audio_edges) >= 5 and len(video_edges) >= 5, (audio_edges, video_edges)
    pairs = [(edge, min(audio_edges, key=lambda candidate: abs(candidate-edge))) for edge in video_edges]
    deltas = [audio-video for video, audio in pairs]
    assert max(abs(x) for x in deltas) < .25, deltas
    assert max(deltas)-min(deltas) < .10, deltas
    return dict(audio_onsets=audio_edges, video_onsets=video_edges, paired_audio_minus_video_seconds=deltas,
        median_offset_seconds=statistics.median(deltas), observed_drift_range_seconds=max(deltas)-min(deltas),
        limit='Includes fixture redraw and hardware-output latency; this is measured end-to-end alignment, not a zero-latency reference.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='append', choices=STAGES)
    parser.add_argument('--microphone-id')
    parser.add_argument('--microphone-gain', type=float, default=6)
    parser.add_argument('--fixture-snapshots', action='store_true',
        help='Opt-in local NSView PNG diagnostics; redraw may influence publication, not a baseline performance run.')
    parser.add_argument('--lock-dir', type=pathlib.Path, help='Explicit canonical shared lock directory, if git-common-dir discovery is unsuitable.')
    args = parser.parse_args()
    args.stage = list(dict.fromkeys(args.stage or ['pilot']))
    if 'microphone' in args.stage and not args.microphone_id:
        parser.error('--stage microphone requires --microphone-id from devices')
    if not math.isfinite(args.microphone_gain) or not -60 <= args.microphone_gain <= 24:
        parser.error('--microphone-gain must be finite -60..24 dB')
    run = Run(args)
    try:
        run.setup()
        for stage in args.stage:
            if stage == 'rtmp': run.pilot(stream=True)
            elif stage == 'av': run.silence(av=True)
            else: getattr(run, stage)()
        run.report['ok'] = True
    except BaseException as error:
        run.report['error'] = repr(error)
        raise
    finally:
        run.cleanup()
        print(run.path/'report.json', flush=True)


if __name__ == '__main__':
    main()
