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

ROOT = pathlib.Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'rejected', 'failed', 'cancelled', 'timed_out', 'needs_reconciliation'}


def plan():
    return {'version': 1, 'requires': ['canonical H14 physical lock', 'already-open signed app',
            'MATCHDAY installed through GPUI', 'idle healthy outputs', 'empty or controlled tone mixer'],
            'cases': ['MCP goal with own revision receipts', 'immediate cooldown rejection',
                      'same event ID rejected after cooldown', 'MCP/CLI concurrent edit fencing',
                      'CLI countdown start/reset', 'MCP disconnect during native animation',
                      'owner continues and CLI observes completion', 'simultaneous MKV and loopback RTMP'],
            'never': ['pack installation bypass', 'external RTMPS start', 'store save', 'device capture',
                      'automatic replay', 'fake UI origin'],
            'separate_gates': ['GPUI click/confirmation evidence', 'real UI concurrent edit',
                               'decoded animation visibility', 'frame/packet tail delivery', 'A/V synchronization'],
            'status': 'NOT_EXECUTED'}


def stores(directory):
    return {name: sha(directory / name) if (directory / name).is_file() else None
            for name in ('project.json', 'audio-mixer.json', 'output-profiles.json',
                         'show-control/configuration.json', 'streaming/destinations.json')}


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
            check(time.monotonic() < deadline, 'bounded real owner wait', label=label)
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
            self.wait(lambda s: slots(s)[target]['phase'] == 'active', target + ' active')
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
        completed = self.job(candidate['id'], 'external GPUI goal completed')
        self.report['ui_goal'].update(completed=completed, completed_monotonic=time.monotonic())
        check(completed['state'] == 'completed', 'external goal sequence completes', job=completed)
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

    def exercise(self):
        event = 'h14-goal-' + str(time.time_ns())
        began = time.monotonic()
        response = self.press('goal', event)
        goal_id = response['result']['job_ids'][0]
        blocked = self.press('goal', event + '-cooldown', expect=False)
        check(blocked['error']['code'] in ('DECK_COOLDOWN', 'DECK_PENDING'), 'real cooldown/pending rejection')
        goal = self.job(goal_id, 'first goal completed')
        self.report['goal'] = goal
        check(goal['state'] == 'completed', 'real goal sequence completes', job=goal)
        receipts = [receipt for record in goal['records'] for receipt in record['revision_receipts']]
        check(len(receipts) >= 2 and any(r['after']['revision'] > r['before']['revision'] for r in receipts), 'own revision acknowledgments retained')
        self.report['cooldown'] = blocked
        # This is a real MCP submission followed by a real CLI edit. It is not
        # labelled a UI test, nor are races forced by changing the runtime clock.
        trials = []
        for index in range(3):
            self.wait(lambda s: not s['overlays']['runtime']['animations']['busy'], 'animation barrier before race')
            response = self.press('lower-entry', event + '-race-' + str(index))
            self.call('set_audio_gain', transport='cli', input_id=self.tone, gain_db=-11)
            job = self.job(response['result']['job_ids'][0], 'MCP CLI race terminal')
            self.call('set_audio_gain', transport='cli', input_id=self.tone, gain_db=-12)
            trials.append(job)
            if any(record.get('code') == 'STALE_REVISION' for record in job['records']):
                break
            time.sleep(.5)
        self.report['concurrent_mcp_cli'] = {'trials': trials, 'status': 'PASS' if any(
            record.get('code') == 'STALE_REVISION' for job in trials for record in job['records']) else 'NOT_OBSERVED'}
        self.report['concurrent_ui'] = {'status': 'NOT_EVALUATED', 'reason': 'requires actual native UI action; origin is never forged'}
        # Waiting for cooldown is wall time only; libobs still owns media timing.
        while time.monotonic() - began < 10.5:
            self.snapshot('waiting real goal cooldown')
            time.sleep(.2)
        duplicate = self.press('goal', event, transport='cli', expect=False)
        check(duplicate['error']['code'] == 'DUPLICATE', 'same event cannot replay after cooldown', response=duplicate)
        self.report['duplicate'] = duplicate
        response = self.press('countdown', event + '-timer', transport='cli')
        timer = self.job(response['result']['job_ids'][0], 'countdown control completed')
        check(timer['state'] == 'completed', 'countdown start acknowledged')
        self.call('overlay_event', transport='cli', source_id=self.bindings['sources']['match-clock'], event='timer_reset')
        self.report['countdown'] = timer
        response = self.press('celebrate', event + '-disconnect')
        disconnect_id = response['result']['job_ids'][0]
        accepted = self.job(disconnect_id, 'native animation before MCP disconnect', terminal=False)
        check(any(r.get('operation_id') for r in accepted['records']), 'real native operation token before disconnect')
        self.client.process.stdin.close()
        self.client.process.wait(timeout=8)
        self.mcp_connected = False
        completed = self.job(disconnect_id, 'owner completes after MCP disconnect')
        check(completed['state'] == 'completed', 'owner continues without MCP client', job=completed)
        state = self.snapshot('both outputs survive client disconnect')
        check(all(slots(state)[t]['phase'] == 'active' and slots(state)[t]['attempt_id'] == self.attempts[t]
                  for t in self.attempts), 'same outputs stay active after client disconnect')
        self.report['disconnect'] = {'accepted': accepted, 'completed': completed, 'owner_pid': state['pid']}
        for _ in range(10):
            self.snapshot('post-celebration steady output')
            time.sleep(.2)
        self.report['control_status'] = ('PASS' if self.report['concurrent_mcp_cli']['status'] == 'PASS' else 'PARTIAL')

    def stop(self):
        if not self.client or not self.started:
            return
        state = self.snapshot('before controlled output stop')
        for target in self.started:
            slot = slots(state)[target]
            check(slot['attempt_id'] == self.attempts[target], 'never stop another output attempt')
            if slot['native_busy']:
                self.call('stop_output_target', target=target)
        final = self.wait(lambda s: all(not slots(s)[t]['native_busy'] for t in self.started), 'native output finalization', seconds=40)
        self.report['final_outputs'] = slots(final)
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

    def journal(self):
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
    report = {'version': 1, 'status': 'FAIL', 'control_status': 'NOT_EVALUATED',
              'plan': plan(), 'app': str(support.APP), 'app_sha256': sha(support.APP),
              'script_sha256': sha(__file__), 'media': [], 'cleanup_errors': [],
              'retained_changes': ['Show Control history, consumed event IDs and legitimate goal counters are retained; no reset/replay.'],
              'visual_review_required': ['Review goal entry in both decoded contact sheets and full-resolution MKVs.',
                  'Correlate event/operation timeline against actual media; wall clock alone is not a video timestamp.',
                  'Exercise real GPUI controls and a concurrent UI edit separately.',
                  'Use H14 output-integrity harness for exact encoded/dispatched/container tail accounting.']}
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
        if suite.receiver and suite.receiver.process.poll() is None:
            try: suite.receiver.terminate()
            except Exception as exc: report['cleanup_errors'].append(str(exc))
        if suite.client:
            try: suite.client.close()
            except Exception as exc: report['cleanup_errors'].append(str(exc))
        suite.snapshots.close()
        write_json(directory / 'report.json', report)
    print(json.dumps({'status': report['status'], 'control_status': report['control_status'],
                      'report': str(directory / 'report.json'), 'cleanup_errors': report['cleanup_errors']}))
    if report['status'] == 'FAIL' or report['cleanup_errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
