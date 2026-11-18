"""Offline verifier checks; no owner, socket, native app, device or media access."""
import copy
import tempfile
from pathlib import Path
import unittest

from verify_h17_show_recovery import (configuration, read_private, restore_owned_store,
                                     running, validate_reconciled)


class RecoveryChecks(unittest.TestCase):
    def proof(self):
        session = 'a' * 32
        token = session + ':animation:7:1'
        receipt = {'action_key': 'event:5:0', 'operation_id': token,
                   'before': {'pid': 71, 'revision': 163}, 'after': {'pid': 71, 'revision': 165}}
        before = {'state': 'needs_reconciliation', 'cursor': 0,
                  'expected': {'pid': 71, 'revision': 165},
                  'records': [{'stage': 'uncertain', 'operation_id': token,
                               'revision_receipts': [receipt], 'terminal_receipt': None}]}
        after = copy.deepcopy(before)
        after['state'] = 'cancelled'
        after['records'][0]['stage'] = 'completed'
        after['records'][0]['terminal_receipt'] = {'action_key': 'event:5:0', 'operation_id': token, 'pid': 71}
        return before, after, session

    def test_terminal_gate_rejects_rebase_replay_and_wrong_owner(self):
        before, after, session = self.proof()
        validate_reconciled(before, after, session, 71)
        for key in ('revision', 'cursor', 'counter', 'token', 'receipt', 'pid', 'action'):
            invalid = copy.deepcopy(after)
            if key == 'revision': invalid['expected']['revision'] += 1
            if key == 'cursor': invalid['cursor'] = 1
            if key == 'counter': invalid['records'].append({'index': 1})
            if key == 'token': invalid['records'][0]['operation_id'] = 'other:animation:7:1'
            if key == 'receipt': invalid['records'][0]['revision_receipts'] = []
            if key == 'pid': invalid['records'][0]['terminal_receipt']['pid'] = 72
            if key == 'action': invalid['records'][0]['terminal_receipt']['action_key'] = 'other:5:0'
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_reconciled(before, invalid, session, 71)

    def test_running_requires_observed_first_tick_and_stock_duration(self):
        value = {'phase': 'running', 'started': True, 'widget_triggered': True,
                 'duration_ms': 450, 'elapsed_ms': 100}
        self.assertTrue(running(value))
        for key, changed in [('phase', 'completed'), ('started', False), ('widget_triggered', False),
                             ('duration_ms', 3000), ('elapsed_ms', 450)]:
            self.assertFalse(running({**value, key: changed}))

    def test_configuration_uses_two_steps_and_fixed_stock450(self):
        config, deck = configuration('scene-1', 'source-3', 'layer-4')
        actions = config['rules'][0]['actions']
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['animation']['duration_ms'], 450)
        self.assertEqual(actions[1]['type'], 'increment_counter')
        self.assertEqual(deck['buttons'][0]['target']['rule_id'], config['rules'][0]['id'])

    def test_store_restore_is_exact_and_refuses_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'configuration.json'
            path.write_bytes(b'owned')
            path.chmod(0o600)
            with self.assertRaises(AssertionError):
                restore_owned_store(path, b'original', b'other', 'test')
            self.assertEqual(path.read_bytes(), b'owned')
            restore_owned_store(path, b'original', b'owned', 'test')
            self.assertEqual(read_private(path), b'original')
            restore_owned_store(path, None, b'original', 'test-remove')
            self.assertFalse(path.exists())

    def test_store_symlinks_are_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'original'
            original.write_bytes(b'original')
            original.chmod(0o600)
            link = Path(directory) / 'configuration.json'
            link.symlink_to(original)
            with self.assertRaises(AssertionError):
                restore_owned_store(link, b'backup', b'original', 'test')
            self.assertEqual(original.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
