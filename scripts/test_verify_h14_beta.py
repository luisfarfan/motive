"""Coordinator safety only: fake subprocesses, temporary files, no apps or media."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import verify_h14_beta as beta


def idle_state():
    return {'pid': 700, 'outputs': {'recording': {'native_busy': False},
                                    'streaming': {'native_busy': False}},
            'destinations': {'selected': None, 'credential_busy': False, 'reconciliation_pending': []},
            'overlays': {'runtime': {'animations': {'busy': False}}},
            'transition': {'phase': 'idle'}, 'show_control': {'configured': False}}


class FakeProcess:
    pid = 800

    def __init__(self, result=0, first_poll=None):
        self.result, self.first_poll = result, first_poll

    def poll(self):
        callback, self.first_poll = self.first_poll, None
        if callback:
            callback()
        return self.result


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='motive-coordinator-unit-')
        self.base = Path(self.temp.name).resolve()
        self.root, self.common = self.base / 'worktree', self.base / 'main/.git'
        (self.root / 'scripts').mkdir(parents=True)
        (self.root / 'var/evidence').mkdir(parents=True)
        self.lock = self.common.parent / 'var/run/physical-test.lock/OWNER'
        self.lock.parent.mkdir(parents=True)
        self.lock_text = json.dumps({'owner': 'Codex H14 test', 'worktree': str(self.root)})
        self.lock.write_text(self.lock_text)
        self.lease = self.common.parent / 'var/run/h14-acceptance-stage.lock'
        self.app = self.base / 'Motive.app/Contents/MacOS/motive'
        self.app.parent.mkdir(parents=True)
        self.app.write_bytes(b'unit fixture, never executed')
        self.context = self.base / 'context.json'
        self.context.write_text(json.dumps({'app': str(self.app), 'binary_sha256': beta.digest(self.app),
                                           'compiled_source_commit': 'test-commit'}))
        self.args = SimpleNamespace(lock_held=True, build_context=self.context, app=self.app, stage='capture',
                                    data_root=self.base / 'data', recordings_root=self.base / 'recordings')
        self.directory = self.root / 'var/evidence/stage'
        self.binding = {'compiled_commit': 'test-commit', 'tracked_match': True, 'untracked_inputs': {}}
        self.patches = contextlib.ExitStack()
        self.addCleanup(self.patches.close)
        self.addCleanup(self.temp.cleanup)
        self.patches.enter_context(patch.object(beta, 'ROOT', self.root))
        paths = SimpleNamespace(app_executable=self.app, lock_matches=lambda value: value == self.lock_text,
                                manifest=lambda: {'portable': True})
        self.patches.enter_context(patch.object(beta, 'verification_paths', return_value=paths))
        self.source = self.patches.enter_context(patch.object(beta, 'source_binding', return_value=self.binding))
        self.owner = self.patches.enter_context(patch.object(beta, 'owner_observation', return_value=idle_state()))
        self.groups = self.patches.enter_context(patch.object(beta, 'group_members', return_value=[]))
        self.inventory = self.patches.enter_context(patch.object(beta, 'process_inventory', return_value=[
            {'pid': 1, 'group': 1, 'executable': '/sbin/launchd'}]))
        self.spawn = self.patches.enter_context(patch.object(beta.subprocess, 'Popen', return_value=FakeProcess()))
        self.patches.enter_context(patch.object(beta.subprocess, 'check_output', side_effect=self.git))
        self.patches.enter_context(patch.object(beta.subprocess, 'run', side_effect=AssertionError('No real subprocess')))
        self.patches.enter_context(patch.object(beta.time, 'sleep', return_value=None))

    def git(self, args, **kwargs):
        allowed = {('git', 'rev-parse', '--git-common-dir'): str(self.common) + '\n',
                   ('git', 'rev-parse', 'HEAD'): 'test-head\n', ('git', 'status', '--short'): ''}
        if tuple(args) not in allowed:
            raise AssertionError(('Unexpected subprocess', args))
        return allowed[tuple(args)]

    def execute(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = beta.execute(self.args, self.directory, [['fake-child']])
        return code, json.loads((self.directory / 'manifest.json').read_text())

    def test_completion_is_not_beta_acceptance_and_uses_own_session(self):
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'PROCESS_COMPLETED')
        self.assertEqual(report['beta_acceptance'], 'NOT_EVALUATED')
        self.assertTrue(self.spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(report['stage_lease'], str(self.lease))
        self.assertFalse(self.lease.exists())

    def test_canonical_existing_lease_rejects_before_owner_probe(self):
        self.lease.mkdir()
        owner_file = self.lease / 'owner.json'
        owner_file.write_text('prior owner')
        with self.assertRaises(FileExistsError):
            self.execute()
        self.owner.assert_not_called()
        self.spawn.assert_not_called()
        self.assertEqual(owner_file.read_text(), 'prior owner')

    def test_missing_required_python_rejects_before_owner_probe_or_child(self):
        self.args.stage = 'regressions'
        self.args.suite = ['verify_h11_runtime.py']
        self.args.verification_python = None
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.owner.assert_not_called()
        self.spawn.assert_not_called()
        self.assertFalse(self.lease.exists())
        self.assertIn('Verification Python', report['error'])

    def test_legacy_regression_subset_does_not_require_a_venv(self):
        self.args.stage = 'regressions'
        self.args.suite = ['verify_control.py', 'verify_control_delivery.py']
        self.args.verification_python = None
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report['verification_python']['status'], 'NOT_REQUIRED')

    def test_lease_exists_at_admission_and_rejected_admission_releases_own_lease(self):
        def reject(_app):
            self.assertTrue((self.lease / 'owner.json').exists())
            raise ValueError('Different active owner')
        self.owner.side_effect = reject
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.spawn.assert_not_called()
        self.assertFalse(self.lease.exists())
        self.assertEqual(report['native_barrier'], 'NOT_REQUIRED_NO_CHILD_STARTED')
        self.assertEqual(report['evidence'], [])

    def test_live_child_and_changed_binary_never_release_lease(self):
        def interrupt():
            self.app.write_bytes(b'changed')
            raise KeyboardInterrupt('synthetic interrupt')
        self.spawn.return_value = FakeProcess(None, interrupt)
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'CHILD_STILL_RUNNING')
        self.assertEqual(report['active_child_pid'], FakeProcess.pid)
        self.assertTrue(report['lease_retained'])
        self.assertTrue(self.lease.exists())
        self.assertTrue(any(e['section'] == 'executable_identity' for e in report['diagnostic_errors']))

    def test_missing_final_binary_preserves_manifest_and_lease(self):
        self.spawn.return_value = FakeProcess(0, self.app.unlink)
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(report['lease_retained'])
        self.assertTrue(self.lease.exists())
        self.assertEqual(report['commands'][0]['returncode'], 0)
        self.assertTrue(report['diagnostic_errors'])

    def test_changed_canonical_owner_is_observed_during_child(self):
        self.spawn.return_value = FakeProcess(None, lambda: self.lock.write_text('different owner'))
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertIn('Canonical lock changed while child was active', report['error'])
        self.assertTrue(self.lease.exists())
        self.assertEqual(self.owner.call_count, 1)

    def test_remaining_group_member_blocks_release_even_after_exit_zero(self):
        self.groups.return_value = [{'pid': 801, 'group': 800, 'executable': '/test/receiver'}]
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(self.lease.exists())
        self.assertEqual(report['remaining_group_members'][0]['pid'], 801)
        self.assertEqual(self.owner.call_count, 1)

    def test_busy_native_final_barrier_retains_lease(self):
        busy = idle_state()
        busy['outputs']['streaming']['native_busy'] = True
        self.owner.side_effect = [idle_state(), busy]
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(self.lease.exists())
        self.assertEqual(report['native_barrier'], 'UNKNOWN_OR_BUSY')

    def test_pending_credential_or_receipt_fails_admission_without_mutation(self):
        state = idle_state()
        state['destinations']['credential_busy'] = True
        self.owner.return_value = state
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.spawn.assert_not_called()
        self.assertFalse(self.lease.exists())
        state['destinations']['credential_busy'] = False
        state['destinations']['reconciliation_pending'] = [{'id': 'opaque-receipt'}]
        with self.assertRaises(ValueError):
            beta.require_quiescent(state)

    def test_untracked_product_input_rejects_before_owner_or_child(self):
        self.source.return_value = dict(self.binding, untracked_inputs={'src/new.rs': 'hash'})
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.owner.assert_not_called()
        self.spawn.assert_not_called()
        self.assertFalse(self.lease.exists())

    def test_changed_source_binding_is_failure_but_quiescent_child_can_release(self):
        self.source.side_effect = [self.binding, dict(self.binding, tracked_match=False)]
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'PROCESS_FAILED')
        self.assertFalse(self.lease.exists())
        self.assertTrue(any(e['section'] == 'source_binding' for e in report['diagnostic_errors']))

    def test_stage_never_removes_replaced_lease_owner(self):
        self.spawn.return_value = FakeProcess(0, lambda: (self.lease / 'owner.json').write_text('other owner'))
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(report['lease_retained'])
        self.assertEqual((self.lease / 'owner.json').read_text(), 'other owner')

    def test_static_checks_detect_owner_appearing_while_child_runs(self):
        self.args.stage = 'static'
        self.owner.return_value = None
        self.inventory.return_value = [{'pid': 700, 'group': 700, 'executable': str(self.app)}]
        self.spawn.return_value = FakeProcess(None)
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertIn('Owner appeared while a static command was active', report['error'])
        self.assertTrue(self.lease.exists())

    def test_report_write_failure_retains_lease(self):
        original = beta.write_json
        calls = 0
        def writer(path, value):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError('synthetic final write failure')
            return original(path, value)
        with patch.object(beta, 'write_json', side_effect=writer):
            code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(report['lease_retained'])
        self.assertTrue(self.lease.exists())
        self.assertIn('synthetic final write failure', report['finalization_error'])


class ObservationTests(unittest.TestCase):
    def test_unavailable_socket_does_not_prove_owner_absent(self):
        app = Path('/fixture/Motive.app/Contents/MacOS/motive')
        reply = SimpleNamespace(stdout=json.dumps({'ok': False, 'error': {'code': 'STUDIO_UNAVAILABLE'}}), returncode=1)
        with patch.object(beta.subprocess, 'run', return_value=reply), patch.object(beta, 'process_inventory', return_value=[
                {'pid': 10, 'group': 10, 'executable': str(app)}]):
            with self.assertRaisesRegex(ValueError, 'Live owner without a responding socket'):
                beta.owner_observation(app)

    def test_binding_covers_build_scripts_and_embedded_matchday_and_untracked_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extra = root / 'src/new.rs'
            extra.parent.mkdir()
            extra.write_text('untracked source')
            with patch.object(beta, 'ROOT', root), patch.object(beta.subprocess, 'check_output', side_effect=[
                    'resolved-commit\n', b'', b'src/new.rs\0']) as command:
                result = beta.source_binding({'compiled_source_commit': 'd0deeb5'})
            self.assertTrue(result['tracked_match'])
            self.assertEqual(result['untracked_inputs'], {'src/new.rs': beta.digest(extra)})
            for name in ('show-control/examples/packs/matchday.json', 'show-control/examples/decks/matchday.json',
                         'scripts/build_obs_outputs.py', 'scripts/build_obs_capture.py', '.cargo/config.toml'):
                self.assertIn(name, command.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
