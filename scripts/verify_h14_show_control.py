#!/usr/bin/env python3
"""Observe real MATCHDAY Show Control over MCP/CLI and two local outputs.

The owner must already hold the canonical lock, open the signed app, and install
MATCHDAY through its native reviewed UI. This harness never installs a pack,
launches/signs an app, opens a physical capture, writes a store, or starts an
external stream. --plan is offline. Execution retains media and honest PARTIAL
visual/UI gates; control acknowledgments are not proof of visible animation.
"""
import argparse
import array
import json
import math
import pathlib
import shutil
import socket
import subprocess
import time
import traceback

import verify_h13_outputs as support
from verify_h13_outputs import Client, Receiver, check, profile, run, sha, slots, write_json
from verify_h14_memory import canonical_lock
from h14_show_helpers import composite_receipt, counter_value, native_animation_id, native_cancel_outcome

ROOT = pathlib.Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'rejected', 'failed', 'cancelled', 'timed_out', 'needs_reconciliation'}


def plan():
    return {'version': 2, 'requires': ['canonical H14 physical lock', 'already-open signed B3 app',
            'MATCHDAY installed through GPUI', 'idle healthy outputs', 'empty or controlled tone mixer'],
            'cases': ['MCP goal with own revision receipts', 'immediate cooldown rejection',
                      'same event ID rejected after cooldown', 'MCP/CLI concurrent edit fencing',
                      'CLI countdown start/reset', 'MCP disconnect during native animation',
                      'owner continues and CLI observes completion', 'simultaneous MKV and loopback RTMP',
                      'single composite action and exact two-step cursor/receipts',
                      'native cancellation before/after first tick, races remain NOT_OBSERVED',
                      'early packet traces after three frames and final traces before cleanup'],
            'never': ['pack installation bypass', 'external RTMPS start', 'store save', 'device capture',
                      'automatic replay', 'fake UI origin'],
            'separate_gates': ['GPUI click/confirmation evidence', 'real UI concurrent edit',
                               'decoded animation visibility', 'frame/packet tail delivery', 'A/V synchronization'],
            'status': 'NOT_EXECUTED'}


def stores(directory):
    return {name: sha(directory / name) if (directory / name).is_file() else None
            for name in ('project.json', 'audio-mixer.json', 'output-profiles.json',
                         'show-control/configuration.json', 'streaming/destinations.json')}


def media_evidence(paths):
    """Retain known artifacts even when analysis/cleanup failed; never imply decode."""
    evidence = []
    for label, value in paths:
        if value is None:
            continue
        path = pathlib.Path(value)
        item = {'label': label, 'path': str(path), 'exists': False,
                'sha256': None, 'decode_status': 'NOT_EVALUATED',
                'hash_stable_observation': False}
        try:
            item['exists'] = path.is_file()
            if item['exists']:
                before = path.stat()
                item['sha256'] = sha(path)
                after = path.stat()
                item.update(bytes=after.st_size, bytes_before_hash=before.st_size,
                            mtime_ns=after.st_mtime_ns,
                            hash_stable_observation=(before.st_size, before.st_mtime_ns,
                                                     before.st_dev, before.st_ino) ==
                                                    (after.st_size, after.st_mtime_ns,
                                                     after.st_dev, after.st_ino))
        except Exception as exc:
            item['evidence_error'] = str(exc)
        evidence.append(item)
    return evidence


def analyze(path, directory, label):
    """Decode actual media, retain every timestamp, and make review contact sheets."""
    path = pathlib.Path(path)
    check(path.is_file() and path.stat().st_size > 0, 'actual output file exists', path=str(path))
    result = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
              'visible_animation': 'NOT_EVALUATED', 'av_sync': 'NOT_EVALUATED',
              'packet_tail_delivery': 'NOT_EVALUATED'}
    probe = json.loads(run('ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                          '-show_format', '-of', 'json', str(path), timeout=180))
    result['probe'] = probe
    check(any(s['codec_type'] == 'video' for s in probe['streams']), 'decoded video stream')
    check(any(s['codec_type'] == 'audio' for s in probe['streams']), 'decoded audio stream')
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                              '-f', 'null', '-'], capture_output=True, timeout=180)
    result['decode'] = {'returncode': decoded.returncode, 'stderr': decoded.stderr.decode()}
    check(decoded.returncode == 0 and not decoded.stderr, 'full media decode', details=result['decode'])
    frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path), timeout=180))['frames']
    pts = [float(frame['best_effort_timestamp_time']) for frame in frames]
    check(len(pts) > 60 and all(b > a for a, b in zip(pts, pts[1:])), 'monotonic decoded video timeline')
    write_json(directory / (label + '-video-pts.json'), pts)
    result['video'] = {'frames': len(pts), 'first_pts': pts[0], 'last_pts': pts[-1],
                       'max_gap_seconds': max(b-a for a, b in zip(pts, pts[1:]))}
    pcm = array.array('f')
    pcm.frombytes(run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn',
                      '-ac', '1', '-ar', '48000', '-f', 'f32le', '-', timeout=180))
    check(pcm and all(math.isfinite(value) for value in pcm), 'finite decoded audio')
    peak = max(abs(value) for value in pcm)
    rms = math.sqrt(sum(value*value for value in pcm) / len(pcm))
    result['audio'] = {'samples': len(pcm), 'sample_rate': 48000, 'peak': peak, 'rms': rms,
                       'peak_dbfs': 20*math.log10(max(peak, 1e-12)),
                       'clipped_samples': sum(abs(value) >= .99999 for value in pcm)}
    check(peak > .0001 and peak < .99999, 'audible controlled tone without sample clipping', audio=result['audio'])
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vf',
                    'fps=2,scale=480:-1,tile=6x4', '-frames:v', '5',
                    str(directory / (label + '-review-%02d.png'))], check=True, timeout=180)
    result['review_sheets'] = [str(p) for p in sorted(directory.glob(label + '-review-*.png'))]
    result['decode_status'] = 'PASS'
    return result


class Suite:
    def __init__(self, args, directory, report):
        self.args, self.directory, self.report = args, directory, report
        self.client = self.initial = self.receiver = None
        self.mcp_connected = True
        self.created_tone = None
        self.profiles = []
        self.started = set()
        self.attempts = {}
        self.harness_events = set()
        self.native_operations = set()
        self.owner_text = None
        self.lock = canonical_lock()
        self.tone = None
        self.changed = False
        self.snapshots = (directory / 'snapshots.jsonl').open('w')

    def check_owner(self):
        check(self.lock.read_text() == self.owner_text, 'canonical physical lock unchanged')

    def call(self, op, transport=None, **args):
        self.check_owner()
        return self.client.call(op, transport=transport or ('mcp' if self.mcp_connected else 'cli'), **args)

    def snapshot(self, label):
        state = self.call('status')['state']
        if self.initial:
            check(state['pid'] == self.initial['pid'], 'same real Production process')
        value = {'label': label, 'monotonic': time.monotonic(), 'state': state}
        self.snapshots.write(json.dumps(value, separators=(',', ':')) + '\n')
        self.snapshots.flush()
        return state

    def wait(self, predicate, label, seconds=12):
        deadline = time.monotonic() + seconds
        while True:
            state = self.snapshot(label)
            if predicate(state):
                return state
            check(time.monotonic() < deadline, 'bounded real owner wait', wait_label=label)
            time.sleep(.08)

    def job(self, identifier, label, terminal=True):
        state = self.wait(lambda s: any(j['id'] == identifier and
            (j['state'] in TERMINAL if terminal else j['state'] == 'awaiting_completion')
            for j in s['show_control']['jobs']), label)
        return next(j for j in state['show_control']['jobs'] if j['id'] == identifier)

    def press(self, button, event, transport=None, expect=True):
        self.harness_events.add(event)
        return self.call('press_show_control', transport=transport, expect=expect,
                         session=self.session, button_id=button, event_id=event)

    def native_job(self, state, operation):
        return next((job for job in state['overlays']['runtime']['animations']['jobs']
                     if job['operation_id'] == operation), None)

    def goal_source(self, state):
        return next(s for s in state['overlays']['runtime']['sources']
                    if s['id'] == self.bindings['sources']['goal-celebration'])

    def assert_outputs(self, state):
        check(all(slots(state)[target]['phase'] == 'active'
                  and slots(state)[target]['attempt_id'] == self.attempts[target]
                  for target in self.attempts), 'same two output attempts continue')

    def capture_trace(self, target, label, early=False):
        deadline = time.monotonic() + 5
        while True:
            value = self.call('output_diagnostics', target=target)
            trace = value['packet_trace']
            check(value['output']['attempt_id'] == self.attempts[target], 'trace belongs to owned attempt')
            check(trace['version'] == 1 and trace['scope'] == 'before_output_plugin', 'packet trace schema')
            packets = trace['packets']
            enough = (not early or (sum(p['media_type'] == 'video' for p in packets) >= 3
                                    and any(p['media_type'] == 'audio' for p in packets)))
            if not trace['snapshot_busy'] and enough:
                break
            check(time.monotonic() < deadline, 'bounded trace collection', trace_label=label, target=target)
            time.sleep(.025)
        path = self.directory / (label + '-' + target + '-packet-trace.json')
        write_json(path, {'monotonic': time.monotonic(), 'label': label, **value})
        sequences = [packet['sequence'] for packet in packets]
        complete_prefix = (bool(sequences) and sequences[0] == 1
                           and all(b == a + 1 for a, b in zip(sequences, sequences[1:]))
                           and trace['summary']['trace_missed_records'] == 0
                           and trace['summary']['trace_overwritten_records'] == 0)
        self.report.setdefault('packet_traces', {}).setdefault(label, {})[target] = {
            'path': str(path), 'sha256': sha(path), 'attempt_id': self.attempts[target],
            'first_retained_sequence': packets[0]['sequence'] if packets else None,
            'retained_packets': len(packets), 'summary': trace['summary'],
            'prefix_status': ('COMPLETE_PREFIX_OBSERVED' if complete_prefix else 'INCONCLUSIVE') if early else 'NOT_APPLICABLE',
            'delivery_status': 'NOT_EVALUATED'}
        return value

    def wait_alert_hidden(self, label):
        def hidden(state):
            self.assert_outputs(state)
            source = self.goal_source(state)
            return source['phase'] == 'hidden' and source['visible'] is False
        return self.wait(hidden, label, seconds=8)

    def complete_goal(self, identifier, label):
        goal = self.job(identifier, label)
        proof = composite_receipt(goal, self.session, self.initial['pid'])
        operation = proof['operation_id']
        self.native_operations.add(operation)
        state = self.wait(lambda s: (job := self.native_job(s, operation)) is not None
                          and job['phase'] == 'completed' and not job['pending_ack'],
                          label + ' native terminal')
        native = self.native_job(state, operation)
        check(native['widget_triggered'] is True
              and native['trigger_source_id'] == self.bindings['sources']['goal-celebration']
              and native['progress'] == 1 and native['elapsed_ms'] >= native['duration_ms'],
              'complete native composite duration observed', native=native)
        self.assert_outputs(state)
        # Preserve the complete source hold and exit in both files, without
        # claiming that control state proves rendered pixels.
        hidden = self.wait_alert_hidden(label + ' full widget lifecycle retained')
        return {'job': goal, 'proof': proof, 'native_terminal': native,
                'hidden_monotonic': time.monotonic(), 'counter': counter_value(hidden),
                'visual_status': 'NOT_EVALUATED'}

    def pending_job(self, identifier, label):
        """A short animation may finish before observation; that is not a fake race PASS."""
        state = self.wait(lambda s: any(j['id'] == identifier and
            (j['state'] == 'awaiting_completion' or j['state'] in TERMINAL)
            for j in s['show_control']['jobs']), label)
        return next(j for j in state['show_control']['jobs'] if j['id'] == identifier)

    def open(self):
        self.owner_text = self.lock.read_text()
        check(str(ROOT) in self.owner_text and 'H14' in self.owner_text, 'canonical H14 lock for this checkout')
        self.report['lock'] = {'path': str(self.lock), 'owner_sha256': __import__('hashlib').sha256(self.owner_text.encode()).hexdigest()}
        self.client = Client(self.directory)
        self.initial = self.snapshot('initial')
        actual = pathlib.Path(run('ps', '-p', str(self.initial['pid']), '-o', 'comm=').decode().strip())
        check(actual.resolve() == support.APP.resolve(), 'already-open owner belongs to specified bundle')
        check(all(not s['native_busy'] and not s['recovery_required'] for s in slots(self.initial).values()), 'idle healthy outputs')
        check(not self.initial['destinations']['credential_busy'], 'no local credential operation in flight')
        pack = self.call('creator_packs')['creator_packs']
        check(pack['phase'] == 'completed' and pack['pack_id'] == 'matchday', 'GPUI-installed complete MATCHDAY required')
        self.report['pack'] = pack
        self.bindings = pack['bindings']
        clock = next(source for source in self.initial['overlays']['runtime']['sources']
                     if source['id'] == self.bindings['sources']['match-clock'])
        check(clock['phase'] == 'idle', 'fresh idle MATCHDAY countdown required; do not reset an existing live timer')
        sc = self.call('show_control_status')['show_control']
        check(sc['configured'] and sc['armed'] and sc['bindings_current'], 'armed matching live owner deck')
        check(all(j['state'] in TERMINAL and j['state'] != 'needs_reconciliation' for j in sc['jobs']), 'no unresolved prior show jobs')
        self.session = sc['session']
        check(all(next(r for r in sc['rules'] if r['id'] == rule)['actions'] == 2
                  for rule in ('deck-goal', 'deck-celebrate')), 'new B3 MATCHDAY two-step bindings required')
        inputs = self.initial['audio_mixer']['store']['inputs']
        check(len(inputs) <= 1 and all(i['source']['kind'] == 'tone' for i in inputs), 'only controlled tone or empty mixer')
        self.report['stores_before'] = stores(self.args.data_dir)
        self.report['initial'] = self.initial
        self.changed = True
        if self.initial['destinations']['selected'] is not None:
            self.call('select_approved_destination', id=None)
        self.call('select_stream_credential', credential_ref=None)
        self.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.call('select_scene', scene_id=self.bindings['scenes']['match-live'])
        self.wait(lambda s: not s['transition']['phase'] in ('preparing', 'running'), 'match-live selected')
        if not inputs:
            state = self.call('add_audio_input', name='H14 Show Control controlled tone', source={'kind': 'tone'})['state']
            self.created_tone = state['audio_mixer']['store']['inputs'][0]['id']
        self.tone = self.created_tone or inputs[0]['id']
        self.call('set_audio_gain', input_id=self.tone, gain_db=-12)
        self.call('set_audio_mute', input_id=self.tone, muted=False)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
        stamp = str(time.time_ns())
        for target in ('recording', 'streaming'):
            value = profile('h14-show-' + target + '-' + stamp, self.args.encoder, 6000)
            self.call('upsert_output_profile', profile=value)
            self.profiles.append(value['id'])
            self.call('select_output_profile', target=target, profile_id=value['id'])
        self.report['loopback_path'] = str(self.directory / 'loopback.mkv')
        self.receiver = Receiver(self.directory, 'loopback', port)
        for target in ('recording', 'streaming'):
            self.call('preflight_output', target=target)
            baseline = slots(self.snapshot('before ' + target + ' start'))[target]['attempt_id']
            try:
                self.call('start_output', target=target)
            finally:
                # A rejected/uncertain start can still own native resources.
                # Preserve its actual attempt before entering any later wait.
                observed = slots(self.snapshot('after ' + target + ' start'))[target]
                if observed['attempt_id'] != baseline:
                    self.started.add(target)
                    self.attempts[target] = observed['attempt_id']
                    if target == 'recording' and observed.get('path'):
                        self.report['recording_path'] = observed['path']
            self.wait(lambda s: slots(s)[target]['phase'] == 'active', target + ' active')
            self.capture_trace(target, 'initial', early=True)
        state = self.snapshot('both outputs active')
        self.report['recording_path'] = slots(state)['recording']['path']
        check(set(self.attempts) == {'recording', 'streaming'}, 'two observed owned output attempts')
        self.report['attempts'] = self.attempts
        self.report['start_monotonic'] = time.monotonic()

    def await_ui_goal(self):
        """Observe an external owner event; CUA evidence establishes the click."""
        initial = self.snapshot('before awaiting real GPUI goal')
        previous = {job['id'] for job in initial['show_control']['jobs']}
        ready = time.monotonic()
        self.report['ui_goal'] = {'status': 'AWAITING_EXTERNAL_EVENT',
            'ready_monotonic': ready, 'timeout_seconds': 90,
            'click_provenance': 'NOT_VERIFIED_BY_HARNESS; retain separate root CUA evidence'}
        write_json(self.directory / 'report.json', self.report)
        print('READY_FOR_GPUI_GOAL', flush=True)
        deadline = ready + 90
        while True:
            state = self.snapshot('awaiting new GPUI goal job')
            check(state['show_control']['session'] == self.session, 'same owner show session while awaiting UI')
            check(all(slots(state)[target]['phase'] == 'active'
                      and slots(state)[target]['attempt_id'] == self.attempts[target]
                      for target in self.attempts), 'both owned outputs remain active during UI wait')
            candidate = next((job for job in state['show_control']['jobs']
                              if job['id'] not in previous and job['rule_id'] == 'deck-goal'
                              and job['event_id'] not in self.harness_events), None)
            if candidate:
                break
            check(time.monotonic() < deadline, 'new external deck-goal job within 90 seconds')
            time.sleep(.2)
        self.report['ui_goal'].update(status='OBSERVED', detected_monotonic=time.monotonic(),
                                      accepted=candidate)
        complete = self.complete_goal(candidate['id'], 'external GPUI goal completed')
        self.report['ui_goal'].update(completed=complete['job'], complete=complete,
                                      completed_monotonic=time.monotonic())
        check(complete['counter'] == counter_value(initial) + 1, 'UI goal increments counter once')
        state = self.wait(lambda s: any(button['id'] == 'goal'
                    and (button.get('state') or {}).get('state') == 'ready'
                    for button in s['show_control']['buttons']),
                    'real GPUI goal cooldown expires before automated exercise', seconds=15)
        check(state['show_control']['session'] == self.session, 'same session after UI cooldown')
        check(all(slots(state)[target]['phase'] == 'active'
                  and slots(state)[target]['attempt_id'] == self.attempts[target]
                  for target in self.attempts), 'both owned outputs continue after UI goal')
        self.report['ui_goal'].update(status='COMPLETED_OBSERVED', cooldown_ready_monotonic=time.monotonic(),
                                      button_state='ready')
        write_json(self.directory / 'report.json', self.report)

    def button_ready(self, identifier):
        return self.wait(lambda s: any(button['id'] == identifier
                         and (button.get('state') or {}).get('state') == 'ready'
                         for button in s['show_control']['buttons']),
                         identifier + ' real cooldown ready', seconds=15)

    def cancel_native(self, after_started):
        """Exercise the public composite operation, never a forged scheduler clock."""
        trials = []
        for index in range(1 if after_started else 2):
            self.wait_alert_hidden('clean widget baseline before native cancellation')
            state = self.wait(lambda s: not s['overlays']['runtime']['animations']['busy'],
                              'native animation barrier before cancellation')
            response = self.call('trigger_animated_widget', transport='cli' if after_started else 'mcp',
                source_id=self.bindings['sources']['goal-celebration'],
                scene_id=self.bindings['scenes']['match-live'], layer_id=self.bindings['layers']['live-goal'],
                animation={'kind': 'scale_in', 'easing': 'ease_out', 'duration_ms': 1200,
                           'distance': 120, 'scale_from': .8})
            operation = response['result']['operation_id']
            self.native_operations.add(operation)
            before = self.native_job(response['state'], operation)
            trial = {'operation_id': operation, 'admitted': before, 'requested_after_started': after_started,
                     'source_before': self.goal_source(state), 'counter_before': counter_value(state),
                     'boundary': 'direct owner API; not a Show Control dispatch/journal intent'}
            trials.append(trial)
            if after_started:
                state = self.wait(lambda s: (j := self.native_job(s, operation)) is not None
                    and ((j['phase'] == 'running' and j['widget_triggered'])
                         or j['phase'] in ('completed', 'cancelled', 'failed')),
                    'native first tick before cancellation')
                before = self.native_job(state, operation)
                trial['before_cancel'] = before
                if before['phase'] != 'running' or not before['widget_triggered']:
                    trial['status'] = 'NOT_OBSERVED'
                    final = self.wait_alert_hidden('late cancellation observation widget lifecycle')
                    trial.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
                    break
            trial['cancel_reply'] = self.call('cancel_overlay_animation', operation_id=operation)
            state = self.wait(lambda s: (j := self.native_job(s, operation)) is not None
                and j['phase'] in ('completed', 'cancelled', 'failed') and not j['pending_ack'],
                'native cancellation terminal barrier')
            terminal = self.native_job(state, operation)
            trial.update(terminal=terminal, status=native_cancel_outcome(terminal, after_started),
                         source_after_terminal=self.goal_source(state))
            check(trial['status'] != 'FAIL', 'native cancellation did not fail', trial=trial)
            self.assert_outputs(state)
            final = self.wait_alert_hidden('widget lifecycle after native cancellation')
            trial.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
            check(trial['counter_after'] == trial['counter_before'], 'direct cancellation never changes show counter')
            if trial['status'] == 'PASS':
                break
        return {'status': 'PASS' if any(t['status'] == 'PASS' for t in trials) else 'NOT_OBSERVED',
                'trials': trials, 'pixel_restoration': 'NOT_EVALUATED'}

    def cancel_show_job(self, event):
        before = self.button_ready('celebrate')
        response = self.press('celebrate', event)
        identifier = response['result']['job_ids'][0]
        observed = self.pending_job(identifier, 'show cancellation operation admission')
        record = next((r for r in observed['records'] if r.get('operation_id')), None)
        result = {'event_id': event, 'before': observed, 'status': 'NOT_OBSERVED',
                  'source_before': self.goal_source(before), 'counter_before': counter_value(before)}
        if observed['state'] != 'awaiting_completion' or not record:
            final = self.wait_alert_hidden('show cancellation race already terminal')
            result.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
            return result
        operation = native_animation_id(record['operation_id'], self.session)
        self.native_operations.add(operation)
        state = self.snapshot('before show cancellation')
        native = self.native_job(state, operation)
        result['native_before'] = native
        if not native or native['phase'] != 'running' or not native['widget_triggered']:
            self.job(identifier, 'show cancellation missed running observation')
            final = self.wait_alert_hidden('missed show cancellation full lifecycle')
            result.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
            return result
        result['cancel_reply'] = self.call('cancel_show_control', session=self.session, job_id=identifier)
        replied = next(j for j in result['cancel_reply']['show_control']['jobs'] if j['id'] == identifier)
        if replied['state'] == 'completed':
            result.update(job=replied, reason='Owner completion won before cancellation request')
            final = self.wait_alert_hidden('show cancellation arrived after job completion')
            result.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
            return result
        state = self.wait(lambda s: (j := self.native_job(s, operation)) is not None
            and j['phase'] in ('completed', 'cancelled', 'failed') and not j['pending_ack'],
            'show cancellation actual native terminal')
        terminal = self.native_job(state, operation)
        result['native_terminal'] = terminal
        result['source_after_terminal'] = self.goal_source(state)
        result['reconcile'] = self.call('reconcile_show_control', session=self.session, job_id=identifier)
        result['job'] = self.job(identifier, 'show cancellation reconciled')
        result['status'] = native_cancel_outcome(terminal, True)
        check(result['status'] != 'FAIL', 'show cancellation native result', result=result)
        check(counter_value(self.snapshot('counter after show cancel')) == counter_value(before),
              'cancelled/reconciled show job never runs following counter')
        if result['status'] == 'PASS':
            check(result['job']['state'] == 'cancelled', 'native cancelled reconciles to cancelled')
        final = self.wait_alert_hidden('source lifecycle after show cancel')
        result.update(source_after_lifecycle=self.goal_source(final), counter_after=counter_value(final))
        return result

    def exercise(self):
        event = 'h14-goal-' + str(time.time_ns())
        baseline = self.snapshot('counter before MCP goal')
        response = self.press('goal', event)
        goal_id = response['result']['job_ids'][0]
        blocked = self.press('goal', event + '-cooldown', expect=False)
        check(blocked['error']['code'] in ('DECK_COOLDOWN', 'DECK_PENDING'), 'real cooldown/pending rejection')
        complete = self.complete_goal(goal_id, 'first B3 goal completed')
        self.report['goal'] = complete
        check(complete['counter'] == counter_value(baseline) + 1, 'MCP goal increments counter exactly once')
        self.report['cooldown'] = blocked
        self.report['cancel_before_tick'] = self.cancel_native(False)
        self.report['cancel_after_tick'] = self.cancel_native(True)
        self.report['cancel_show_control'] = self.cancel_show_job(event + '-cancel')
        self.button_ready('goal')
        duplicate = self.press('goal', event, transport='cli', expect=False)
        check(duplicate['error']['code'] == 'DUPLICATE', 'same event cannot replay after cooldown', response=duplicate)
        self.report['duplicate'] = duplicate
        response = self.press('countdown', event + '-timer', transport='cli')
        timer = self.job(response['result']['job_ids'][0], 'countdown control completed')
        check(timer['state'] == 'completed', 'countdown start acknowledged')
        self.call('overlay_event', transport='cli', source_id=self.bindings['sources']['match-clock'], event='timer_reset')
        self.report['countdown'] = timer
        # A real accepted composite is followed by a CLI mutation. A scheduling
        # race that finishes first remains NOT_OBSERVED, never a forced PASS.
        baseline = self.button_ready('goal')
        response = self.press('goal', event + '-race')
        identifier = response['result']['job_ids'][0]
        observed = self.pending_job(identifier, 'composite admission before real CLI edit')
        race = {'before': observed, 'status': 'NOT_OBSERVED'}
        self.report['concurrent_mcp_cli'] = race
        if observed['state'] == 'awaiting_completion':
            race['edit'] = self.call('set_audio_gain', transport='cli', input_id=self.tone, gain_db=-11)
            job = self.job(identifier, 'composite concurrent edit terminal')
            race['job'] = job
            codes = {record.get('code') for record in job['records']}
            if job['state'] == 'needs_reconciliation' and 'MISSING_MUTATION_RECEIPT' in codes:
                race['status'] = 'PASS'
                state = self.snapshot('counter fenced after external edit')
                check(counter_value(state) == counter_value(baseline), 'concurrent edit prevents following counter')
                record = next(r for r in job['records'] if r.get('operation_id'))
                operation = native_animation_id(record['operation_id'], self.session)
                self.native_operations.add(operation)
                self.wait(lambda s: (j := self.native_job(s, operation)) is not None
                          and j['phase'] in ('completed', 'cancelled', 'failed') and not j['pending_ack'],
                          'concurrent composite actual native terminal')
                race['reconcile'] = self.call('reconcile_show_control', session=self.session, job_id=identifier)
                check(race['reconcile']['result']['state'] == 'needs_reconciliation',
                      'reconcile never invents missing receipt')
                self.report['retained_changes'].append('Observed concurrent goal remains needs_reconciliation; no replay or invented receipt.')
            else:
                check(job['state'] == 'completed', 'unexpected composite concurrency failure', job=job)
            self.call('set_audio_gain', transport='cli', input_id=self.tone, gain_db=-12)
        else:
            check(observed['state'] == 'completed', 'unexpected admission failure before race', job=observed)
        self.wait_alert_hidden('concurrent goal source lifecycle complete')
        self.report['concurrent_ui'] = {'status': 'NOT_EVALUATED', 'reason': 'requires actual native UI action; origin is never forged'}
        self.button_ready('celebrate')
        baseline = self.snapshot('before disconnect celebration')
        response = self.press('celebrate', event + '-disconnect')
        disconnect_id = response['result']['job_ids'][0]
        accepted = self.pending_job(disconnect_id, 'native animation before MCP disconnect')
        record = next((r for r in accepted['records'] if r.get('operation_id')), None)
        state = self.snapshot('actual native phase at MCP disconnect')
        native = self.native_job(state, native_animation_id(record['operation_id'], self.session)) if record else None
        in_flight = bool(accepted['state'] == 'awaiting_completion' and native
                         and native['phase'] == 'running' and native['widget_triggered'])
        self.client.process.stdin.close()
        exit_code = self.client.process.wait(timeout=8)
        self.mcp_connected = False
        closed_at = time.monotonic()
        disconnected = self.snapshot('CLI observes owner after MCP process exited')
        native_after_exit = self.native_job(disconnected, native['operation_id']) if native else None
        still_running = bool(native_after_exit and native_after_exit['phase'] == 'running'
                             and native_after_exit['widget_triggered'])
        complete = self.complete_goal(disconnect_id, 'owner completes after MCP disconnect')
        check(complete['counter'] == counter_value(baseline) + 1, 'disconnect celebration increments once')
        state = self.snapshot('both outputs survive client disconnect')
        self.assert_outputs(state)
        self.report['disconnect'] = {'accepted': accepted, 'native_at_disconnect': native,
            'native_after_client_exit': native_after_exit, 'client_exit_code': exit_code,
            'client_closed_monotonic': closed_at, 'complete': complete, 'owner_pid': state['pid'],
            'status': 'PASS' if in_flight and still_running else 'NOT_OBSERVED'}
        for target in self.attempts:
            self.capture_trace(target, 'after-events')
        gates = ('concurrent_mcp_cli', 'cancel_before_tick', 'cancel_after_tick', 'cancel_show_control', 'disconnect')
        self.report['control_status'] = 'PASS' if all(self.report[key]['status'] == 'PASS' for key in gates) else 'PARTIAL'

    def stop(self):
        if not self.client or not self.started:
            return
        try:
            self.wait(lambda s: not s['overlays']['runtime']['animations']['busy'],
                      'native animation barrier before output stop')
        except Exception as exc:
            self.report['pre_stop_animation_barrier_error'] = str(exc)
        state = self.snapshot('before controlled output stop')
        for target in sorted(self.started):
            slot = slots(state)[target]
            check(slot['attempt_id'] == self.attempts[target], 'never stop another output attempt')
            try:
                self.capture_trace(target, 'pre-stop')
            except Exception as exc:
                self.report.setdefault('trace_errors', []).append({'target': target, 'phase': 'pre-stop', 'error': str(exc)})
            if slot['native_busy']:
                self.call('stop_output_target', target=target)
        final = self.wait(lambda s: all(not slots(s)[t]['native_busy'] for t in self.started), 'native output finalization', seconds=40)
        self.report['final_outputs'] = slots(final)
        for target in sorted(self.started):
            try:
                self.capture_trace(target, 'final')
            except Exception as exc:
                self.report.setdefault('trace_errors', []).append({'target': target, 'phase': 'final', 'error': str(exc)})
        self.started.clear()
        if self.receiver:
            self.report['receiver_returncode'] = self.receiver.wait()

    def cleanup(self):
        errors = self.report.setdefault('cleanup_errors', [])
        if not self.changed or not self.client:
            return
        try:
            self.stop()
            self.wait(lambda s: not s['overlays']['runtime']['animations']['busy'] and
                      s['transition']['phase'] not in ('preparing', 'running'), 'quiescence before restoration')
            old = self.initial['output_configuration']
            for target in ('recording', 'streaming'):
                self.call('select_output_profile', target=target, profile_id=old[target + '_profile'])
            for identifier in self.profiles:
                self.call('remove_output_profile', id=identifier)
            if old['endpoint'] is not None:
                self.call('configure_stream', endpoint=old['endpoint'])
            else:
                self.report.setdefault('retained_changes', []).append('Ephemeral loopback endpoint remains configured: core has no unset endpoint operation.')
            self.call('select_stream_credential', credential_ref=old['credential_ref'])
            self.call('select_approved_destination', id=self.initial['destinations']['selected'])
            touched = {self.bindings['sources'][name] for name in ('goal-celebration', 'match-lower-third', 'match-clock')}
            for source in self.initial['overlays']['runtime']['sources']:
                if source['id'] in touched:
                    if source['id'] == self.bindings['sources']['match-clock']:
                        self.call('overlay_event', source_id=source['id'], event='timer_reset')
                    self.call('overlay_event', source_id=source['id'], event='show' if source['visible'] else 'hide')
            for scene in self.initial['project']['graph']['scenes']:
                for layer in scene['layers']:
                    if layer['source_id'] in touched:
                        for variant in ('horizontal', 'vertical'):
                            self.call('set_transform', scene_id=scene['id'], layer_id=layer['id'],
                                      variant=variant, transform=layer['layouts'][variant])
            if self.created_tone:
                self.call('remove_audio_input', input_id=self.created_tone)
            elif self.tone:
                original = self.initial['audio_mixer']['store']['inputs'][0]
                self.call('set_audio_gain', input_id=self.tone, gain_db=original['gain_db'])
                self.call('set_audio_mute', input_id=self.tone, muted=original['muted'])
            self.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
            self.call('select_scene', scene_id=self.initial['project']['graph']['active_scene'])
            self.call('configure_transition', transition=self.initial['transition_configuration'])
            self.report['restored'] = self.snapshot('restored original output configuration and selection')
            self.report['stores_after'] = stores(self.args.data_dir)
            check(self.report['stores_after'] == self.report['stores_before'], 'no store was written')
        except Exception as exc:
            errors.append(str(exc))

    def journal(self, require_cases=True):
        source = self.args.data_dir / 'show-control' / ('session-' + self.session + '.jsonl')
        check(source.is_file() and not source.is_symlink() and source.stat().st_size <= 16*1024*1024, 'bounded current owner journal')
        target = self.directory / 'owner-journal.jsonl'
        shutil.copyfile(source, target)
        entries = [json.loads(line) for line in target.read_text().splitlines()]
        intents = {}
        for index, entry in enumerate(entries):
            if entry['entry'] == 'intent':
                intents[entry['intent']['action_key']] = index
            if entry['entry'] == 'dispatch':
                check(entry['action_key'] in intents and intents[entry['action_key']] < index, 'durable intent precedes dispatch result')
        self.report['journal'] = {'path': str(target), 'sha256': sha(target), 'entries': len(entries),
                                  'owner_session': self.session, 'intent_order_verified': True}
        proofs = []
        for complete in (self.report.get('goal'), self.report.get('disconnect', {}).get('complete')):
            if complete and complete.get('proof'):
                proofs.append(complete['proof'])
        if require_cases:
            check(len(proofs) == 2, 'successful main and disconnect composite proofs retained')
        if self.report.get('ui_goal', {}).get('complete'):
            proofs.append(self.report['ui_goal']['complete']['proof'])
        for proof in proofs:
            intent = entries[intents[proof['action_key']]]['intent']
            prepared = intent['prepared']
            check(prepared['action']['type'] == 'trigger_animated_widget'
                  and len(prepared['commands']) == 1
                  and prepared['commands'][0]['op'] == 'trigger_animated_widget',
                  'durable journal proves one composite dispatch', action_key=proof['action_key'])
        self.report['journal']['composite_intents_verified'] = len(proofs)
        cancellation = self.report.get('cancel_show_control', {})
        if cancellation.get('status') == 'PASS':
            record = next(r for r in cancellation['before']['records'] if r.get('operation_id'))
            token = record['operation_id']
            dispatches = [i for i, entry in enumerate(entries) if entry['entry'] == 'dispatch'
                          and entry['report']['outcome'].get('operation_id') == token]
            cancels = [i for i, entry in enumerate(entries) if entry['entry'] == 'cancel_intent'
                       and entry['operation_id'] == token]
            completions = [i for i, entry in enumerate(entries) if entry['entry'] == 'completion'
                           and entry['operation_id'] == token]
            check(len(dispatches) == len(cancels) == len(completions) == 1
                  and dispatches[0] < cancels[0] < completions[0],
                  'one durable cancel intent follows acceptance and precedes native completion', token=token)
            self.report['journal']['cancel_intent_verified'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--await-ui-goal', action='store_true',
                        help='With both outputs active, wait up to 90s for an external GPUI goal before automation')
    parser.add_argument('--app', type=pathlib.Path, default=support.APP)
    parser.add_argument('--data-dir', type=pathlib.Path, default=ROOT / 'var')
    parser.add_argument('--output', type=pathlib.Path)
    parser.add_argument('--encoder', choices=('auto', 'videotoolbox', 'x264'), default='auto')
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(), indent=2)); return
    if not args.lock_held or not args.output:
        parser.error('--lock-held and a fresh --output are required')
    support.APP = args.app.resolve()
    args.data_dir = args.data_dir.resolve()
    directory = args.output.resolve()
    check(not directory.exists(), 'fresh evidence directory')
    directory.mkdir(parents=True, mode=0o700)
    report = {'version': 2, 'status': 'FAIL', 'control_status': 'NOT_EVALUATED',
              'plan': plan(), 'app': str(support.APP), 'app_sha256': sha(support.APP),
              'script_sha256': sha(__file__), 'helper_sha256': sha(pathlib.Path(__file__).with_name('h14_show_helpers.py')),
              'media': [], 'cleanup_errors': [],
              'retained_changes': ['Show Control history, consumed event IDs and legitimate goal counters are retained; no reset/replay.'],
              'visual_review_required': ['Review goal entry in both decoded contact sheets and full-resolution MKVs.',
                  'Correlate event/operation timeline against actual media; wall clock alone is not a video timestamp.',
                  'Exercise real GPUI controls and a concurrent UI edit separately.',
                  'Use retained initial/final packet traces with actual container PTS for tail accounting; trace alone proves dispatch only.']}
    suite = Suite(args, directory, report)
    print(directory, flush=True)
    try:
        suite.open()
        if args.await_ui_goal:
            suite.await_ui_goal()
        suite.exercise(); suite.stop(); suite.journal()
        report['media'].append(analyze(report['recording_path'], directory, 'recording'))
        report['media'].append(analyze(suite.receiver.path, directory, 'loopback'))
        report['status'] = 'PARTIAL'  # Media decoding is not visual/UI acceptance.
    except Exception as exc:
        report['failure'] = str(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        suite.cleanup()
        if hasattr(suite, 'session') and 'journal' not in report:
            try:
                suite.journal(require_cases=False)
            except Exception as exc:
                report['journal_preservation_error'] = str(exc)
        if suite.receiver and suite.receiver.process.poll() is None:
            try: suite.receiver.terminate()
            except Exception as exc: report['cleanup_errors'].append(str(exc))
        if suite.client:
            try: suite.client.close()
            except Exception as exc: report['cleanup_errors'].append(str(exc))
        suite.snapshots.close()
        report['media_evidence'] = media_evidence([
            ('recording', report.get('recording_path')),
            ('loopback', report.get('loopback_path'))])
        report['media_hash_scope'] = ('Observed files after cleanup attempt; hash stability is '
                                     'not proof of native finalization, decode or visible animation.')
        write_json(directory / 'report.json', report)
    print(json.dumps({'status': report['status'], 'control_status': report['control_status'],
                      'report': str(directory / 'report.json'), 'cleanup_errors': report['cleanup_errors']}))
    if report['status'] == 'FAIL' or report['cleanup_errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
