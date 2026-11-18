#!/usr/bin/env python3
"""Observe one genuine GPUI goal→gain edit; never synthesize UI actions.

The root owns launches, focus and fresh AX observations. This runner requires a
fresh disposable owner and exact reviewed store/binary hashes. It only prepares
controlled runtime resources, then queries state. No store save, pack install,
GUI automation, physical capture, external stream, replay or media analysis.
"""
import argparse
import json
import pathlib
import re
import socket
import subprocess
import time
import traceback

from h14_collection_helpers import owned_stop_command, require, unique_owned_tone
from h14_show_helpers import counter_value, native_animation_id
from h14_ui_concurrency_helpers import (classify_result, native_job, pending_evidence, temporary_configuration,
    tone_gain, ui_gain_edit, validate_manifest, validate_saved_project)
from verify_h14_collection import Client, Receiver, default_owner, digest, executable, load, lock, process_identity, save

ROOT = pathlib.Path(__file__).resolve().parents[1]
STORES = ('project.json', 'audio-mixer.json', 'output-profiles.json',
          'show-control/configuration.json', 'streaming/destinations.json')
TERMINAL = {'completed', 'rejected', 'failed', 'cancelled', 'timed_out', 'needs_reconciliation'}


def store_hashes(directory):
    result = {}
    for name in STORES:
        path = directory/name
        require(not path.is_symlink(), 'Store may not be a symlink')
        require(not path.exists() or (path.is_file() and path.stat().st_size <= 1024*1024), 'Bounded regular store required')
        result[name] = digest(path) if path.exists() else None
    return result


def snapshot(state):
    result = {key: state[key] for key in ('pid', 'revision', 'last_action', 'show_control', 'overlays',
        'audio_mixer', 'outputs', 'issues', 'transition', 'output_lifecycle', 'stats')}
    result['active_scene'] = state['project']['graph']['active_scene']
    return result


class Trial:
    def __init__(self, args):
        self.args = args; self.manifest = validate_manifest(load(args.manifest, 65536))
        self.lock_owner = lock()
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        if not common.is_absolute(): common = ROOT/common
        self.lock_path = common.resolve().parent/'var/run/physical-test.lock/OWNER'
        self.lock_bytes = self.lock_path.read_bytes()
        self.out = pathlib.Path(args.output).resolve()
        require(self.out.is_relative_to((ROOT/'var/evidence').resolve()), 'Use a new worktree evidence directory')
        self.out.mkdir(parents=True, exist_ok=False)
        self.report = {'version': 1, 'status': 'FAIL', 'manifest': self.manifest, 'lock': self.lock_owner,
            'case': 'stockMATCHDAY450ms' if args.animation_ms == 450 else 'custom3000ms rule',
            'animation_ms': args.animation_ms, 'gate': {'status': 'NOT_OBSERVED'}, 'media': [],
            'limits': ['A UI-prefixed event and last_action corroborate root CUA evidence; the harness never sends origin UI.',
                       'The 3000 ms option is a separate custom rule, never evidence of the stock 450 ms race.',
                       'Runtime gain/state and native completion do not certify decoded media or output tail delivery.',
                       'Project/configuration stores remain unchanged; normal native Show Control journals may be appended.']}
        self.client = self.initial = self.receiver = self.identity = self.session = self.tone = None
        self.attempted = {}; self.owned = {}; self.profile_created = False; self.operation = self.job_id = None
        self.profile_id = 'h14-ui-race-'+self.manifest['trial_id']
        self.tone_name = 'H14 GPUI concurrency '+self.manifest['trial_id']
        self.tone_attempted = self.profile_attempted = False; self.profile = None
        self.prior_audio_ids = set()
        self.configured = False; self.samples = 0; self.stores_before = None; self.original = None

    def flush(self): save(self.out/'report.json', self.report)

    def call(self, op, **args):
        require(self.lock_path.read_bytes() == self.lock_bytes, 'Canonical physical lock changed')
        return self.client.call(op, **args)

    def sample(self, label, check_outputs=False):
        require(self.samples < 2600, 'Bounded observation sample limit reached')
        state = self.call('status')['state']; self.samples += 1
        row = {'label': label, 'host_clock': 'python.time.monotonic', 'host_bracket_s': self.client.last_bracket,
               'wall_unix': time.time(), 'state': snapshot(state)}
        with (self.out/'snapshots.jsonl').open('a') as output: output.write(json.dumps(row, separators=(',', ':'))+'\n')
        if self.session: require(state['show_control']['session'] == self.session, 'Show Control session changed')
        require(not state['destinations']['credential_busy'] and state['destinations']['selected'] is None
                and state['output_configuration']['credential_ref'] is None, 'External destination/credential state changed')
        if check_outputs:
            require(all(state['outputs'][target]['attempt_id'] == attempt and state['outputs'][target]['phase'] == 'active'
                        for target, attempt in self.owned.items()), 'Same two owned output attempts must remain active')
        return state

    def wait(self, predicate, label, seconds=12, check_outputs=False):
        deadline = time.monotonic()+seconds
        while True:
            state = self.sample(label, check_outputs)
            if predicate(state): return state
            require(time.monotonic() < deadline, 'Bounded wait expired: '+label)
            time.sleep(.08)

    def trace(self, target, label, early=False):
        deadline = time.monotonic()+3
        while True:
            value = self.call('output_diagnostics', target=target); trace = value['packet_trace']
            require(value['output']['attempt_id'] == self.owned[target], 'Packet trace attempt changed')
            if not trace['snapshot_busy'] and (not early or
                (sum(p['media_type'] == 'video' for p in trace['packets']) >= 3
                 and any(p['media_type'] == 'audio' for p in trace['packets']))): break
            require(time.monotonic() < deadline, 'Bounded packet trace wait expired'); time.sleep(.025)
        save(self.out/(label+'-packets-'+target+'.json'), value)

    def prepare(self):
        manifest = self.manifest; bundle = pathlib.Path(manifest['owner']['bundle']).resolve(strict=True)
        binary = executable(bundle, 'local.motive.studio')
        require(digest(binary) == manifest['owner']['sha256'], 'Owner executable does not match supplied reviewed hash')
        self.identity = process_identity(manifest['owner']['pid'], binary); self.report['identity'] = self.identity
        self.data = pathlib.Path(manifest['data_dir']).resolve(strict=True)
        expected_data = pathlib.Path.home()/'Library/Application Support/local.motive.studio' \
            if (bundle/'Contents/Resources/MotivePortable.json').exists() else ROOT/'var'
        require(self.data == expected_data.resolve(), 'Data directory must be the specified bundle’s actual runtime directory')
        self.stores_before = store_hashes(self.data); self.report['stores_before'] = self.stores_before
        require(self.stores_before['project.json'] == manifest['project_sha256']
                and self.stores_before['show-control/configuration.json'] == manifest['show_control_sha256'],
                'Saved project/configuration differs from root-reviewed hashes')
        project = load(self.data/'project.json', 262144)
        saved = load(self.data/'show-control/configuration.json', 1024*1024)
        pack_path = ROOT/'show-control/examples/packs/matchday.json'
        deck_path = ROOT/'show-control/examples/decks/matchday.json'
        pack, deck = load(pack_path), load(deck_path)
        self.report['hashes'] = {'owner': manifest['owner']['sha256'], 'pack': digest(pack_path),
            'deck_template': digest(deck_path), 'harness': digest(__file__),
            'helpers': digest(ROOT/'scripts/h14_ui_concurrency_helpers.py'),
            'receiver': digest(manifest['receiver_ffmpeg'])}
        self.client = Client(str(bundle), manifest['owner']['pid'], self.out)
        self.initial = self.sample('fresh disposable owner'); default_owner(self.initial)
        require(not self.initial['destinations']['credential_busy'], 'No credential enrollment in flight')
        self.report['initial'] = snapshot(self.initial)
        self.original = {key: self.initial['output_configuration'][key] for key in ('recording_profile', 'streaming_profile', 'endpoint')}
        self.bindings = validate_saved_project(project, pack, self.initial['project']['graph'])
        config, deck = temporary_configuration(saved, pack, deck, self.bindings, self.args.animation_ms)
        self.report['bindings'] = self.bindings
        profiles = self.call('output_profiles')['store']['profiles']
        require(not any(p['id'] == self.profile_id for p in profiles), 'Trial profile already exists')
        require(store_hashes(self.data) == self.stores_before, 'Stores changed before restore')
        self.call('load_project')
        state = self.sample('reviewed controlled project restored')
        require(state['project']['graph'] == project['graph'], 'Restored graph differs from reviewed store')
        self.call('load_show_control')
        state = self.sample('original B3 configuration restored disarmed')
        require(state['show_control']['configured'] and state['show_control']['armed'] is False
                and state['show_control']['bindings_current'] and not state['show_control']['jobs']
                and state['show_control']['project_fingerprint'] == saved['project_fingerprint'],
                'Original stored configuration must bind to the real restored project')
        self.report['restored_session'] = state['show_control']['session']
        if self.args.animation_ms == 3000:
            self.call('configure_show_control', config=config, deck=deck)
            self.report['temporary_change'] = {'path': 'config.rules[id=deck-goal].actions[0].animation.duration_ms',
                                               'before': 450, 'after': 3000, 'saved': False}
        else:
            self.report['temporary_change'] = None
        self.configured = True
        self.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.call('select_scene', scene_id=self.bindings['scenes']['match-live'])
        self.wait(lambda s: s['transition']['phase'] not in ('preparing', 'running'), 'controlled Match Live active')
        self.prior_audio_ids = {item['id'] for item in self.sample('before own tone admission')['audio_mixer']['store']['inputs']}
        require(not self.prior_audio_ids, 'Mixer changed before own tone admission')
        self.tone_attempted = True
        state = self.call('add_audio_input', name=self.tone_name, source={'kind': 'tone'})['state']
        inputs = state['audio_mixer']['store']['inputs']
        self.tone = unique_owned_tone(inputs, self.tone_name, self.prior_audio_ids)
        require(len(inputs) == 1, 'Concurrent unrelated mixer input; do not start outputs')
        self.call('set_audio_gain', input_id=self.tone, gain_db=-12)
        self.report['tone_id'] = self.tone
        profile = {'id': self.profile_id, 'encoder': 'videotoolbox', 'bitrate_kbps': 6000,
                   'rate_control': 'cbr', 'keyframe_seconds': 1, 'frame_reordering': False}
        self.profile = profile; self.profile_attempted = True
        self.call('upsert_output_profile', profile=profile); self.profile_created = True
        for target in ('recording', 'streaming'): self.call('select_output_profile', target=target, profile_id=self.profile_id)
        with socket.socket() as listener: listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        self.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
        self.receiver = Receiver(manifest['receiver_ffmpeg'], self.out, port)
        for target in ('recording', 'streaming'):
            require(self.call('preflight_output', target=target)['preflight']['ready'], 'Output preflight must be ready')
            state = self.sample('before '+target+' start'); self.attempted[target] = state['outputs'][target]['attempt_id']
            value = self.call('start_output', target=target)['state']['outputs'][target]
            self.owned[target] = value['attempt_id']
            self.report['media'].append({'target': target, 'attempt_id': value['attempt_id'],
                'path': str(self.receiver.path) if target == 'streaming' else value['path'], 'decode_status': 'NOT_EVALUATED'})
            self.wait(lambda s: s['outputs'][target]['phase'] == 'active', target+' active')
            self.trace(target, 'initial', True)
        state = self.sample('ready to arm exact live revision', True)
        self.call('arm_show_control', pid=state['pid'], revision=state['revision'])
        state = self.sample('armed ready for real UI', True)
        self.session = state['show_control']['session']; self.report['session'] = self.session
        require(state['show_control']['armed'] and state['show_control']['bindings_current'] and tone_gain(state, self.tone) == -12,
                'Current bindings armed with −12 dB owned tone')
        goals = [source for source in state['overlays']['runtime']['sources']
                 if source['id'] == self.bindings['sources']['goal-celebration']]
        require(len(goals) == 1 and goals[0]['phase'] in ('idle', 'hidden'), 'Owned goal alert must begin idle/hidden')
        require(store_hashes(self.data) == self.stores_before, 'Preparation must not save stores')
        self.report['before_ui'] = snapshot(state); self.report['attempts'] = self.owned.copy()
        return state

    def observe(self, initial):
        prior = {job['id'] for job in initial['show_control']['jobs']}; baseline = counter_value(initial)
        deadline = time.monotonic()+90; before = edit = job = None
        self.report['ready_host_monotonic'] = time.monotonic(); self.report['observation_deadline'] = deadline
        self.flush()
        print('READY_FOR_GPUI_CONCURRENCY', flush=True)
        print(json.dumps({'case': self.report['case'], 'tone_id': self.tone,
            'instructions': 'Root: actual goal click → fresh AX read → actual 0 dB click. Keep separate CUA evidence. No automatic retries.'}), flush=True)
        while time.monotonic() < deadline:
            state = self.sample('real GPUI concurrency observation', True)
            candidates = [j for j in state['show_control']['jobs'] if j['id'] not in prior]
            require(len(candidates) <= 1, 'Only one new real UI job is permitted in this trial')
            if candidates:
                job = candidates[0]
                require(job['rule_id'] == 'deck-goal' and re.fullmatch(r'ui-'+str(state['pid'])+r'-[1-9][0-9]*', job['event_id']),
                        'New goal must carry the actual owner UI event namespace')
                self.job_id = job['id']
                pending = pending_evidence(state, job, self.session, self.tone, self.args.animation_ms)
                if pending:
                    require(pending['native']['trigger_source_id'] == self.bindings['sources']['goal-celebration'],
                            'Native operation must trigger the exact controlled goal source')
                    self.operation = pending['operation_id']
                    if not before and pending['job_state'] == 'awaiting_completion' and pending['gain_db'] == -12:
                        before = pending; self.report['pending_before_ui_gain'] = {'host_monotonic': time.monotonic(), **pending}
                    if before and not edit and ui_gain_edit(pending):
                        edit = pending; self.report['ui_gain_while_native_running'] = {'host_monotonic': time.monotonic(), **pending}
                        self.report['audio_at_edit'] = state['audio_mixer']; self.flush()
                if job['state'] in TERMINAL:
                    require(job['state'] in ('completed', 'needs_reconciliation'), 'Unexpected goal terminal failure')
                    observed_gain = tone_gain(state, self.tone) == 0 and re.fullmatch(
                        r'UI · set_audio_gain · revisión [0-9]+', state['last_action'])
                    # If the stock operation finished before the second click,
                    # keep its real control available while root finishes the
                    # CUA batch. A late edit remains NOT_OBSERVED for concurrency.
                    if not observed_gain:
                        time.sleep(.05); continue
                    if not edit: self.report['ui_gain_observed_without_pending_proof'] = snapshot(state)
                    self.report['gate'] = classify_result(before, edit, job, state, baseline)
                    break
            time.sleep(.05)
        else:
            self.report['gate'] = {'status': 'NOT_OBSERVED', 'reason': 'No conclusive real UI race within 90 seconds'}
        self.report['last_observation'] = snapshot(state)
        if job:
            records = [r for r in job['records'] if r.get('operation_id')]
            if records:
                self.operation = native_animation_id(records[0]['operation_id'], self.session)
                state = self.wait(lambda s: (native := native_job(s, self.operation)) is not None
                    and native['phase'] in ('completed', 'cancelled', 'failed') and native['pending_ack'] is False,
                    'actual native terminal after UI observation', check_outputs=True)
                self.report['native_terminal'] = native_job(state, self.operation)
                require(self.report['native_terminal']['phase'] == 'completed', 'Native goal must finish normally')
            state = self.wait(lambda s: any(source['id'] == self.bindings['sources']['goal-celebration']
                and source['phase'] == 'hidden' and source['visible'] is False for source in s['overlays']['runtime']['sources']),
                'goal alert native hold and exit complete', check_outputs=True)
            self.report['after_alert_hidden'] = snapshot(state)
            # One second of read-only observation preserves evidence against a
            # delayed following counter or a second dispatch; never reconcile/replay.
            stop = time.monotonic()+1
            while time.monotonic() < stop:
                state = self.sample('post-quiescence no replay observation', True)
                if self.report['gate']['status'] == 'PASS':
                    current = next(j for j in state['show_control']['jobs'] if j['id'] == self.job_id)
                    require(counter_value(state) == baseline and current['state'] == 'needs_reconciliation'
                            and current['cursor'] == 0, 'Uncertain job must retain counter and cursor after native quiescence')
                time.sleep(.08)
        self.report['status'] = 'FAIL' if self.report['gate']['status'] == 'FAIL' else 'PARTIAL'
        self.report['runtime_gate'] = self.report['gate']['status']
        self.report['media_gate'] = 'NOT_EVALUATED_SEPARATE_OFFLINE_ANALYSIS_REQUIRED'
        self.flush()

    def cleanup(self):
        if self.client and self.initial:
            try:
                require(process_identity(self.identity['pid'], pathlib.Path(self.identity['binary'])) == self.identity,
                        'Owner identity changed; cleanup withheld')
                state = self.call('status')['state']
                for target, old in self.attempted.items():
                    slot = state['outputs'][target]
                    if target not in self.owned and slot['attempt_id'] != old and (slot.get('profile') or {}).get('id') == self.profile_id:
                        self.owned[target] = slot['attempt_id']
                    if target in self.owned and not any(m['target'] == target for m in self.report['media']):
                        self.report['media'].append({'target': target, 'attempt_id': self.owned[target],
                            'path': str(self.receiver.path) if target == 'streaming' else slot['path'],
                            'decode_status': 'NOT_EVALUATED', 'start_reply': 'not retained; reconciled by unique profile/attempt'})
                for target, attempt in self.owned.items():
                    command = owned_stop_command(state['outputs'][target], attempt)
                    if command: self.call(command, target=target)
                self.wait(lambda s: all(not s['outputs'][target]['native_busy'] for target in self.owned), 'owned output quiescence', 20)
                for target in self.owned: self.trace(target, 'final')
                self.report['before_resource_cleanup'] = snapshot(self.call('status')['state'])
                state = self.call('status')['state']
                require(all(not slot['native_busy'] for slot in state['outputs'].values()), 'Unrelated busy output; leave resources')
                if self.tone_attempted:
                    inputs = state['audio_mixer']['store']['inputs']
                    if self.tone is None:
                        if any(i.get('name') == self.tone_name for i in inputs):
                            self.tone = unique_owned_tone(inputs, self.tone_name, self.prior_audio_ids)
                    matches = [i for i in inputs if i['id'] == self.tone]
                    if matches:
                        require(matches[0]['name'] == self.tone_name and matches[0]['source'] == {'kind': 'tone'},
                                'Tone identity changed; cleanup withheld')
                        self.call('remove_audio_input', input_id=self.tone)
                if self.original:
                    for target in ('recording', 'streaming'):
                        current = self.call('status')['state']['output_configuration'][target+'_profile']
                        original = self.original[target+'_profile']
                        require(current in (self.profile_id, original), 'Profile selection changed; cleanup withheld')
                        if current == self.profile_id: self.call('select_output_profile', target=target, profile_id=original)
                if self.profile_attempted:
                    matches = [p for p in self.call('output_profiles')['store']['profiles'] if p['id'] == self.profile_id]
                    require(len(matches) <= 1 and (not matches or matches[0] == self.profile), 'Profile changed; cleanup withheld')
                    if matches: self.call('remove_output_profile', id=self.profile_id)
                if self.original and self.receiver:
                    if self.original['endpoint']: self.call('configure_stream', endpoint=self.original['endpoint'])
                    else: self.report['cleanup_residue'] = 'Own loopback endpoint remains selected: no unset API; no stores saved.'
                self.report['final'] = snapshot(self.call('status')['state'])
                self.report['retained_runtime'] = 'Controlled MATCHDAY project and current Show Control session/history retained; no reload, reconciliation or replay.'
            except BaseException as error:
                self.report['cleanup_error'] = repr(error); self.report['status'] = 'FAIL'
        if self.receiver:
            try:
                try: self.report['receiver_exit'] = self.receiver.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.report['receiver_exit'] = self.receiver.close(); self.report['receiver_forced_after_wait'] = True
                    self.report['limits'].append('Owned receiver required termination after output stop; inspect this boundary separately during offline tail analysis.')
            except BaseException as error:
                self.report['receiver_cleanup_error'] = repr(error); self.report['status'] = 'FAIL'
        if self.stores_before:
            try:
                self.report['stores_after'] = store_hashes(self.data)
                self.report['stores_unchanged'] = self.report['stores_after'] == self.stores_before
                require(self.report['stores_unchanged'], 'A persistent store changed')
            except BaseException as error:
                self.report['store_verification_error'] = repr(error); self.report['status'] = 'FAIL'
        for medium in self.report['media']:
            if not medium['path']:
                medium['exists'] = False; medium['evidence_error'] = 'No path was reported for the attempted output'; continue
            path = pathlib.Path(medium['path'])
            medium['exists'] = path.is_file(); medium['bytes'] = path.stat().st_size if path.is_file() else None
            medium['sha256'] = None; medium['hash_status'] = 'DEFERRED_TO_SEPARATE_OFFLINE_ANALYSIS'
        self.report['snapshot_count'] = self.samples; self.flush()


def plan():
    return {'version': 1, 'status': 'NOT_RUN', 'animation_ms_choices': [450, 3000], 'default_animation_ms': 450,
        'command': 'run --lock-held --manifest TRIAL.json --output NEW_EVIDENCE_DIRECTORY --animation-ms 450',
        'manifest': {'version': 1, 'trial_id': 'stock-01', 'owner': {'bundle': '/absolute/Motive.app', 'pid': 111,
            'sha256': '797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc'},
            'data_dir': str(pathlib.Path.home()/'Library/Application Support/local.motive.studio'),
            'project_sha256': '38cf418434deb1f055b4adec1797918f6ef7f121b002fbed949a61d17549b74f',
            'show_control_sha256': '6f54a1d66cbfdef8327f27b4d8d06ea8c5d6d38d2db90bb5851b2a89f95a4e17',
            'receiver_ffmpeg': '/opt/homebrew/bin/ffmpeg'},
        'workflow': ['Root supplies exact fresh default owner and reviewed hashes; no app launch or GUI by harness.',
            'Validate controlled saved definitions, load project and original disarmed configuration.',
            '450 ms: preserve loaded stock configuration. 3000 ms: public configure_show_control changes only goal duration in memory.',
            'Prepare −12 dB controlled tone, MKV plus loopback, exact current arm and initial packet traces.',
            'READY_FOR_GPUI_CONCURRENCY: root clicks goal, obtains fresh AX, then clicks the real tone 0 dB control.',
            'Read-only 50 ms observations for at most 90 s; no harness press, gain mutation, cancellation or replay.',
            'Require real pending native operation, UI gain edit, missing mutation receipt, intact counter and continuous output attempts.',
            'Wait native terminal and hidden alert, stop only own attempts, retain uncertain session/history and unchanged stores.'],
        'retry_policy': 'No automatic retry. Root may run at most two separate stock trials; custom3000ms is an independent fallback case.',
        'remaining_gates': ['Root CUA provenance', 'separate offline decode/PCM/PTS/tail inspection'], 'physical_run': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('plan')
    run = sub.add_parser('run'); run.add_argument('--lock-held', action='store_true', required=True)
    run.add_argument('--manifest', required=True); run.add_argument('--output', required=True)
    run.add_argument('--animation-ms', type=int, choices=(450, 3000), default=450)
    args = parser.parse_args()
    if args.mode == 'plan': print(json.dumps(plan(), indent=2)); return 0
    trial = Trial(args)
    try: trial.observe(trial.prepare())
    except BaseException as error:
        trial.report.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally: trial.cleanup()
    print(json.dumps({'output': str(trial.out), 'status': trial.report['status'], 'runtime_gate': trial.report.get('runtime_gate')}))
    return int(trial.report['status'] == 'FAIL')


if __name__ == '__main__': raise SystemExit(main())
