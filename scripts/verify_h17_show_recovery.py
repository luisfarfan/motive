#!/usr/bin/env python3
"""Reproduce native Show Control reconciliation on an already-open portable owner.

Requires the canonical lock and a fresh default Production. Uses the exact CLI
socket protocol with LOCAL_PEERPID validation before every command. Creates one
owned alert and tone through public APIs, not a pack or GPUI gesture. No process,
device, output or external connection is started. The caller shuts the owner down.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import time
import traceback

from h14_show_helpers import counter_value, native_animation_id
from verification_paths import verification_paths
from verify_h14_collection import Client, ROOT, default_owner, digest, lock, process_identity

TERMINAL = {'completed', 'cancelled', 'failed', 'rejected', 'timed_out', 'needs_reconciliation'}
STORE_NAMES = ('project.json', 'audio-mixer.json', 'output-profiles.json',
               'show-control/configuration.json', 'streaming/destinations.json')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def hash_bytes(payload):
    return hashlib.sha256(payload).hexdigest() if payload is not None else None


def read_private(path):
    if not path.exists():
        require(not path.is_symlink(), 'Dangling store link')
        return None
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 16 * 1024 * 1024,
            'Expected bounded private regular store: ' + str(path))
    return path.read_bytes()


def restore_owned_store(path, original, owned, nonce):
    """Restore only the exact bytes last acknowledged as this run's own write."""
    require(read_private(path) == owned, 'Do not overwrite an unrelated configuration change')
    if original is None:
        path.unlink()
    else:
        temporary = path.with_name('.' + nonce + '.restore')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    require(read_private(path) == original, 'Restored configuration bytes differ')


def configuration(scene, source, layer):
    config = {'schema_version': 1, 'rules': [{
        'id': 'h17-recovery', 'enabled': True, 'event_kind': 'manual.button_pressed',
        'priority': 5, 'conditions': [], 'actions': [
            {'type': 'trigger_animated_widget', 'source_id': source, 'scene_id': scene,
             'layer_id': layer, 'animation': {'kind': 'scale_in', 'easing': 'ease_out',
                 'duration_ms': 450, 'distance': 0, 'scale_from': .8}},
            {'type': 'increment_counter', 'name': 'goals', 'amount': 1}],
        'cooldown_ms': 1200, 'debounce_ms': 0, 'timeout_ms': 5000,
        'busy_policy': 'reject', 'failure_policy': 'stop'}],
        'variables': {'goals': {'type': 'int', 'value': 0}},
        'queue_capacity': 8, 'rate_limit': 20, 'rate_window_ms': 1000,
        'max_actions_per_event': 32}
    deck = {'schema_version': 1, 'id': 'h17-recovery', 'name': 'H17 owned recovery fixture',
        'groups': [{'id': 'test', 'label': 'Controlled verification', 'order': 0}],
        'buttons': [{'id': 'test', 'group_id': 'test', 'label': 'Owned alert 450 ms',
            'icon': 'goal', 'order': 0, 'enabled': True, 'shortcut': None,
            'cooldown_ms': 1200, 'sensitive': False,
            'target': {'kind': 'rule', 'rule_id': 'h17-recovery'}}]}
    return config, deck


def job(state, identifier):
    return next(j for j in state['show_control']['jobs'] if j['id'] == identifier)


def native(state, identifier):
    return next((j for j in state['overlays']['runtime']['animations']['jobs']
                 if j['operation_id'] == identifier), None)


def running(value):
    return bool(value and value['phase'] == 'running' and value['started'] is True
                and value['widget_triggered'] is True and value['duration_ms'] == 450
                and value['elapsed_ms'] < 450)


def terminal(value):
    return bool(value and value['phase'] in {'completed', 'cancelled', 'failed'}
                and value['pending_ack'] is False)


def validate_reconciled(before, after, session, pid):
    require(before['state'] == 'needs_reconciliation', 'Uncertain job must be retained before reconcile')
    require(after['state'] == 'cancelled' and after['cursor'] == before['cursor'] == 0,
            'Reconcile cancels remainder without advancing cursor')
    require(after['expected'] == before['expected'], 'Reconcile must not adopt foreign revisions')
    require(len(after['records']) == 1, 'Counter must have no action record')
    record, prior = after['records'][0], before['records'][0]
    require(record['stage'] == 'completed' and record['operation_id'] == prior['operation_id'],
            'Same native action completed')
    native_animation_id(record['operation_id'], session)
    require(len(record['revision_receipts']) == 1
            and record['revision_receipts'] == prior['revision_receipts'], 'Dispatch receipt remains unchanged')
    receipt = record['terminal_receipt']
    require(receipt == {'action_key': record['revision_receipts'][0]['action_key'],
                       'operation_id': record['operation_id'], 'pid': pid},
            'Exact owner terminal receipt is required')
    return receipt


class Suite:
    def __init__(self, args, paths, out):
        self.args, self.paths, self.out = args, paths, out
        self.report = {'status': 'FAIL', 'scope': 'native owner recovery via CLI, no media or GPUI claim',
            'gates': {'reconcile_same_process': 'NOT_EVALUATED', 'cancel_after_tick': 'NOT_EVALUATED',
                      'cancel_before_tick': 'NOT_EVALUATED', 'gpui_stock450': 'BLOCKED',
                      'outputs_and_pixels': 'NOT_EVALUATED'}, 'trials': [], 'cleanup_errors': []}
        self.client = self.initial = None
        self.source = self.layer = self.tone = self.session = None
        self.store = paths.data_root / 'show-control/configuration.json'
        self.before_stores = self.original = self.owned_store = None
        self.old_journals = {}
        self.own_journals = {}
        self.nonce = 'h17-recovery-' + str(time.time_ns())
        self.lock_owner = None

    def flush(self):
        (self.out / 'report.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def check_lock(self):
        require(lock() == self.lock_owner, 'Canonical lock changed')

    def call(self, op, **arguments):
        self.check_lock()
        value = self.client.call(op, **arguments)
        with (self.out / 'responses.jsonl').open('a') as output:
            output.write(json.dumps({'op': op, 'bracket': self.client.last_bracket,
                                     'response': value}, separators=(',', ':')) + '\n')
        return value

    def state(self):
        state = self.call('status')['state']
        require(state['pid'] == self.report['identity']['pid'], 'Same Production PID required')
        require(all(not value['native_busy'] for value in state['outputs'].values()),
                'Unrelated output appeared; never stop it from this runner')
        return state

    def wait(self, predicate, label, seconds=6):
        deadline = time.monotonic() + seconds
        while True:
            value = self.state()
            if predicate(value):
                return value
            require(time.monotonic() < deadline, 'Bounded wait expired: ' + label)
            time.sleep(.01)

    def journal(self, session):
        require(len(session) == 32 and all(c in '0123456789abcdef' for c in session), 'Native session ID expected')
        path = self.paths.data_root / 'show-control' / ('session-' + session + '.jsonl')
        payload = read_private(path)
        require(payload is not None and payload.endswith(b'\n'), 'Complete durable journal expected')
        require(payload.startswith(self.own_journals.get(session, b'')), 'Own journal was truncated or rewritten')
        self.own_journals[session] = payload
        (self.out / ('session-' + session + '.jsonl')).write_bytes(payload)
        return [json.loads(row) for row in payload.splitlines()]

    def save(self):
        require(read_private(self.store) == (self.owned_store if self.owned_store is not None else self.original),
                'Configuration changed outside this runner before save')
        state = self.state()
        value = self.call('save_show_control', expected={'pid': state['pid'], 'revision': state['revision'],
                                                      'session': state['show_control']['session']})
        receipt = value['result']['saved_configuration']
        payload = read_private(self.store)
        require(receipt['write']['durable'] is True and receipt['write']['bytes'] == len(payload)
                and receipt['write']['document_sha256'] == hash_bytes(payload), 'Durable receipt matches actual bytes')
        self.owned_store = payload
        self.report.setdefault('save_receipts', []).append(receipt)
        return receipt

    def open(self):
        self.lock_owner = lock()
        self.report['lock'] = self.lock_owner
        pid = self.args.owner_pid
        if pid is None:
            with socket.socket(socket.AF_UNIX) as channel:
                channel.connect(str(self.paths.socket))
                pid = channel.getsockopt(0, 2)
        self.report['identity'] = process_identity(pid, self.paths.app_executable)
        self.report['binary_sha256'] = digest(self.paths.app_executable)
        self.report['harness_sha256'] = digest(__file__)
        self.client = Client(self.paths.app_bundle, pid, self.out)
        self.initial = self.state()
        default_owner(self.initial)
        self.before_stores = {name: hash_bytes(read_private(self.paths.data_root / name)) for name in STORE_NAMES}
        self.original = read_private(self.store)
        if self.original is not None:
            backup = self.out / 'configuration.original.json'
            backup.write_bytes(self.original)
            backup.chmod(0o600)
        self.old_journals = {str(path): digest(path) for path in self.store.parent.glob('session-*.jsonl')}
        self.report['stores_before'] = self.before_stores
        self.scene = self.initial['project']['graph']['active_scene']
        definition = {'kind': 'widget', 'widget': {'kind': 'alert', 'title': 'H17 OWNED FIXTURE',
            'subtitle': 'CLI native reconciliation', 'width': 600, 'height': 150,
            'background': 0x203050, 'accent': 0x20e060, 'color': 0xffffff,
            'opacity': 1., 'duration_ms': 1000}}
        value = self.call('create_overlay', scene_id=self.scene, name=self.nonce, definition=definition)
        self.source = value['result']['source_id']
        scene = next(s for s in value['state']['project']['graph']['scenes'] if s['id'] == self.scene)
        self.layer = next(layer['id'] for layer in scene['layers'] if layer['source_id'] == self.source)
        value = self.call('add_audio_input', name=self.nonce, source={'kind': 'tone'})
        self.tone = next(i['id'] for i in value['state']['audio_mixer']['store']['inputs']
                         if i['name'] == self.nonce and i['source']['kind'] == 'tone')
        self.call('set_audio_gain', input_id=self.tone, gain_db=-18)
        config, deck = configuration(self.scene, self.source, self.layer)
        self.session = self.call('configure_show_control', config=config, deck=deck)['show_control']['session']
        self.journal(self.session)
        self.save()
        self.report['fixture'] = {'scene': self.scene, 'source': self.source, 'layer': self.layer,
                                  'tone': self.tone, 'session': self.session, 'duration_ms': 450}

    def ready(self):
        return self.wait(lambda s: not s['overlays']['runtime']['animations']['busy']
            and any(b['id'] == 'test' and b['state']['state'] == 'ready'
                    for b in s['show_control']['buttons']), 'owned button cooldown and animation barrier')

    def press(self, event):
        value = self.call('press_show_control', session=self.session, button_id='test', event_id=event)
        ids = value['result']['job_ids']
        require(len(ids) == 1, 'Exactly one job admitted')
        return ids[0]

    def observed_operation(self, identifier):
        state = self.wait(lambda s: job(s, identifier)['state'] == 'awaiting_completion'
                          or job(s, identifier)['state'] in TERMINAL, 'native operation admission')
        record = next((r for r in job(state, identifier)['records'] if r.get('operation_id')), None)
        operation = native_animation_id(record['operation_id'], self.session) if record else None
        if operation is not None and job(state, identifier)['state'] == 'awaiting_completion':
            state = self.wait(lambda s: running(native(s, operation)) or terminal(native(s, operation))
                              or job(s, identifier)['state'] in TERMINAL,
                              'actual first native tick or terminal')
        return state, operation

    def finish_uncertain(self, identifier, operation):
        state = self.wait(lambda s: terminal(native(s, operation)) and job(s, identifier)['state'] in TERMINAL,
                          'native terminal and owner receipt')
        before = job(state, identifier)
        if before['state'] == 'needs_reconciliation':
            value = self.call('reconcile_show_control', session=self.session, job_id=identifier)
            after = next(j for j in value['show_control']['jobs'] if j['id'] == identifier)
        else:
            after = before
        self.journal(self.session)
        return state, before, after

    def race(self):
        for attempt in range(2):
            baseline = self.ready()
            event = self.nonce + '-race-' + str(attempt)
            identifier = self.press(event)
            observed, operation = self.observed_operation(identifier)
            trial = {'attempt': attempt + 1, 'event': event, 'job_id': identifier,
                     'status': 'BLOCKED', 'before_edit': job(observed, identifier),
                     'native_before_edit': native(observed, operation) if operation else None,
                     'counter_before': counter_value(baseline)}
            self.report['trials'].append(trial)
            if operation is None:
                raise AssertionError('Accepted trigger has no native token')
            if job(observed, identifier)['state'] != 'awaiting_completion' or not running(native(observed, operation)):
                self.finish_uncertain(identifier, operation)
                trial['reason'] = 'First running tick was not observed before completion'
                continue
            edit = self.call('set_audio_gain', input_id=self.tone, gain_db=-20 - attempt)
            trial['edit_response'] = edit
            trial['native_after_edit'] = native(edit['state'], operation)
            in_window = running(trial['native_after_edit'])
            terminal_state = self.wait(lambda s: terminal(native(s, operation)) and job(s, identifier)['state'] in TERMINAL,
                                       'foreign-revision terminal')
            before = job(terminal_state, identifier)
            trial['before_reconcile'] = before
            trial['native_terminal'] = native(terminal_state, operation)
            if before['state'] != 'needs_reconciliation':
                require(not in_window, 'Edit inside running interval must fence following counter')
                trial['reason'] = 'Edit missed the native running interval'
                continue
            denied = self.call('load_show_control', allow_error=True)
            require(denied.get('error', {}).get('code') == 'SHOW_CONTROL_BUSY', 'Uncertain job must block load')
            trial['load_before_reconcile'] = denied
            self.journal(self.session)
            value = self.call('reconcile_show_control', session=self.session, job_id=identifier)
            after = next(j for j in value['show_control']['jobs'] if j['id'] == identifier)
            trial['after_reconcile'] = after
            trial['receipt'] = validate_reconciled(before, after, self.session, self.report['identity']['pid'])
            final = self.state()
            require(counter_value(final) == trial['counter_before'], 'Counter changed during reconciliation')
            require(len(final['show_control']['jobs']) == len(terminal_state['show_control']['jobs']), 'Reconcile must retain jobs')
            entries = self.journal(self.session)
            token = after['records'][0]['operation_id']
            action_key = trial['receipt']['action_key']
            dispatches = [row for row in entries if row.get('entry') == 'dispatch' and row.get('action_key') == action_key]
            completions = [row for row in entries if row.get('entry') == 'completion' and row.get('operation_id') == token]
            require(len(dispatches) == len(completions) == 1, 'Exactly one durable dispatch/completion; no replay')
            require(completions[0]['report']['terminal_receipt'] == trial['receipt'], 'Receipt comes from durable owner journal')
            require(completions[0]['report']['receipt'] is None, 'Race must exercise missing mutation receipt')
            trial['journal_evidence'] = {'dispatch': dispatches[0], 'completion': completions[0]}
            trial['status'] = 'PASS' if in_window else 'BLOCKED'
            if in_window:
                self.report['gates']['reconcile_same_process'] = 'PASS'
                # Wait for real cooldown before retrying the same event ID.
                self.ready()
                duplicate = self.call('press_show_control', session=self.session, button_id='test', event_id=event, allow_error=True)
                require(duplicate.get('error', {}).get('code') == 'DUPLICATE', 'Reconcile retains deduplication')
                trial['duplicate_after_reconcile'] = duplicate
                return
            trial['reason'] = 'Reconcile succeeded, but edit was not bracketed inside running'
        self.report['gates']['reconcile_same_process'] = 'BLOCKED'
        raise RuntimeError('Two attempts missed the stock450 concurrent window; preserve evidence without lengthening animation')

    def cancellation(self):
        baseline = self.ready()
        identifier = self.press(self.nonce + '-cancel')
        observed, operation = self.observed_operation(identifier)
        result = {'status': 'BLOCKED', 'job_id': identifier, 'before': job(observed, identifier),
                  'native_before': native(observed, operation) if operation else None}
        self.report['cancellation'] = result
        if operation is None:
            raise AssertionError('Cancel trial has no native operation')
        if not running(native(observed, operation)):
            self.finish_uncertain(identifier, operation)
            result['reason'] = 'Running phase not observed'
            self.report['gates']['cancel_after_tick'] = 'BLOCKED'
            return
        result['request'] = self.call('cancel_show_control', session=self.session, job_id=identifier)
        state, before, after = self.finish_uncertain(identifier, operation)
        result.update(native_terminal=native(state, operation), before_reconcile=before, after_reconcile=after)
        if native(state, operation)['phase'] == 'cancelled':
            require(after['state'] == 'cancelled' and after['cursor'] == 0, 'Cancelled native job never advances')
            require(counter_value(self.state()) == counter_value(baseline), 'Cancel never runs the counter')
            token = after['records'][0]['operation_id']
            entries = self.journal(self.session)
            cancels = [row for row in entries if row.get('entry') == 'cancel_intent'
                       and row.get('operation_id') == token]
            completions = [row for row in entries if row.get('entry') == 'completion'
                           and row.get('operation_id') == token]
            require(len(cancels) == len(completions) == 1, 'Exactly one durable cancel intention and native terminal')
            require(completions[0]['report']['completion']['status'] == 'cancelled', 'Journal confirms native cancellation')
            result['journal_evidence'] = {'cancel': cancels[0], 'completion': completions[0]}
            result['status'] = 'PASS'
        else:
            result['reason'] = 'Native completion won cancellation race'
        self.report['gates']['cancel_after_tick'] = result['status']

    def restore_and_arm(self):
        old_session = self.session
        original_journal = self.own_journals[old_session]
        value = self.call('load_show_control')['show_control']
        require(value['configured'] and value['armed'] is False and not value['jobs']
                and value['session'] != old_session and value['bindings_current'], 'Restore is new, disarmed and bound')
        self.session = value['session']
        self.report['restored'] = value
        require(self.journal(old_session) and self.own_journals[old_session] == original_journal,
                'Load preserves prior journal byte for byte')
        denied = self.call('press_show_control', session=self.session, button_id='test',
                           event_id=self.nonce + '-disarmed', allow_error=True)
        require(denied.get('error', {}).get('code') == 'SHOW_CONTROL_DISARMED', 'Restored rules cannot run before explicit arm')
        state = self.state()
        armed = self.call('arm_show_control', pid=state['pid'], revision=state['revision'])['show_control']
        require(armed['armed'] and not armed['jobs'], 'Explicit arm creates no job')
        self.report['explicit_arm'] = armed
        self.save()
        self.journal(self.session)
        self.report['gates']['restore_disarmed_explicit_arm_durable_save'] = 'PASS'

    def cleanup(self):
        if self.client is None or self.initial is None:
            return
        def attempt(label, operation):
            try:
                operation()
            except Exception as error:
                self.report['cleanup_errors'].append({'step': label, 'error': str(error)})
        if self.source:
            # Disarm through the public load API; do not clear jobs or journals.
            if self.owned_store is not None:
                attempt('restore own configuration disarmed', lambda: self.call('load_show_control'))
            attempt('wait native animation barrier', lambda: self.wait(
                lambda s: not s['overlays']['runtime']['animations']['busy'], 'cleanup native barrier'))
            if self.layer:
                attempt('remove owned layer', lambda: self.call('remove_layer', scene_id=self.scene, layer_id=self.layer))
            attempt('remove owned source', lambda: self.call('remove_source', source_id=self.source))
        if self.tone:
            attempt('remove owned tone', lambda: self.call('remove_audio_input', input_id=self.tone))
        if self.owned_store is not None:
            def restore_bytes():
                self.check_lock()
                restore_owned_store(self.store, self.original, self.owned_store, self.nonce)
            attempt('restore only configuration bytes written by this runner', restore_bytes)
        def verify_cleanup():
            current = {name: hash_bytes(read_private(self.paths.data_root / name)) for name in STORE_NAMES}
            self.report['stores_after'] = current
            require(current == self.before_stores, 'Persistent stores changed')
            require(all(Path(path).is_file() and digest(path) == value for path, value in self.old_journals.items()),
                    'Historical journals changed')
            for session in list(self.own_journals):
                self.journal(session)
            state = self.state()
            self.report['final'] = state
            require(not state['audio_mixer']['store']['inputs'], 'Owned tone was not released')
            require(state['project']['graph']['sources'] == self.initial['project']['graph']['sources'], 'Owned source was not released')
            require(state['project']['graph']['scenes'] == self.initial['project']['graph']['scenes'], 'Owned layer was not released')
            self.report['cleanup'] = 'PASS'
        if self.before_stores is not None:
            attempt('verify stores, retained journals and fixture release', verify_cleanup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--owner-pid', type=int, help='Expected PID; otherwise pin exact socket LOCAL_PEERPID before any mutation')
    args = parser.parse_args()
    paths = verification_paths(ROOT)
    require(paths.portable, 'Explicit portable MOTIVE_TEST_* paths required')
    out = args.output.resolve()
    require(out.is_relative_to((ROOT / 'var/evidence').resolve()), 'Use a new worktree evidence directory')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    suite = Suite(args, paths, out)
    try:
        suite.open()
        suite.race()
        suite.cancellation()
        suite.restore_and_arm()
        suite.report['status'] = 'PARTIAL'  # Physical presentation/UI/pre-first-tick remain separate.
    except Exception as error:
        suite.report['failure'] = str(error)
        suite.report['traceback'] = traceback.format_exc()
    finally:
        suite.cleanup()
        if suite.report['cleanup_errors']:
            suite.report['status'] = 'FAIL'
        suite.flush()
    print(json.dumps({'status': suite.report['status'], 'gates': suite.report['gates'],
                      'cleanup_errors': suite.report['cleanup_errors'], 'report': str(out / 'report.json')}))
    return int(suite.report['status'] == 'FAIL' or suite.report['gates']['reconcile_same_process'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
