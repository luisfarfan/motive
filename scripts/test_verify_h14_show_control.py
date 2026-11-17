"""Offline harness helper regressions; no app, socket, device or media acceptance."""
import copy
import hashlib
import pathlib
import tempfile
import unittest
from unittest import mock

import verify_h14_show_control as harness
from h14_show_helpers import (composite_receipt, counter_value, native_animation_id,
                             native_cancel_outcome)


class HarnessHelpers(unittest.TestCase):
    def test_wait_reaches_a_later_observation_without_argument_collision(self):
        suite = harness.Suite.__new__(harness.Suite)
        suite.snapshot = mock.Mock(side_effect=[{'ready': False}, {'ready': True}])
        with mock.patch.object(harness.time, 'monotonic', side_effect=[100., 100.1]), \
                mock.patch.object(harness.time, 'sleep') as sleep:
            result = suite.wait(lambda state: state['ready'], 'native finalization')
        self.assertTrue(result['ready'])
        self.assertEqual(suite.snapshot.call_count, 2)
        sleep.assert_called_once_with(.08)

    def test_wait_timeout_retains_the_specific_wait_context(self):
        suite = harness.Suite.__new__(harness.Suite)
        suite.snapshot = mock.Mock(return_value={'ready': False})
        with mock.patch.object(harness.time, 'monotonic', side_effect=[100., 113.]):
            with self.assertRaises(AssertionError) as raised:
                suite.wait(lambda state: state['ready'], 'animation completion')
        self.assertEqual(raised.exception.args[0]['wait_label'], 'animation completion')

    def test_unanalyzed_artifact_paths_and_hashes_survive_failure_reporting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'evidence.bin'
            payload = b'controlled helper-test bytes, not media'
            path.write_bytes(payload)
            absent = pathlib.Path(directory) / 'missing.bin'
            evidence = harness.media_evidence([('present', path), ('absent', absent)])
            self.assertEqual(evidence[0]['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertTrue(evidence[0]['hash_stable_observation'])
            self.assertEqual(evidence[0]['decode_status'], 'NOT_EVALUATED')
            self.assertEqual(evidence[1]['path'], str(absent))
            self.assertFalse(evidence[1]['exists'])


class ShowControlEvidenceHelpers(unittest.TestCase):
    SESSION = 'owner:session'
    TOKEN = SESSION + ':animation:17:2'

    def completed_job(self):
        receipts = [
            {'action_key': 'manual-1:4:0', 'operation_id': self.TOKEN,
             'before': {'pid': 71, 'revision': 10}, 'after': {'pid': 71, 'revision': 12}},
            {'action_key': 'manual-1:4:0', 'operation_id': self.TOKEN,
             'before': {'pid': 71, 'revision': 12}, 'after': {'pid': 71, 'revision': 15}},
        ]
        return {'id': 4, 'state': 'completed', 'cursor': 2, 'records': [
            {'index': 1, 'stage': 'completed', 'operation_id': None, 'revision_receipts': []},
            {'index': 0, 'stage': 'completed', 'operation_id': self.TOKEN,
             'revision_receipts': receipts},
        ]}

    def test_token_parser_uses_exact_session_and_two_positive_integers(self):
        self.assertEqual(native_animation_id(self.TOKEN, self.SESSION), 17)
        for token in [None, 17, 'other:animation:17:2', self.SESSION + ':transition:17:2',
                      self.SESSION + ':animation:0:2', self.SESSION + ':animation:17:0',
                      self.SESSION + ':animation:-17:2', self.SESSION + ':animation:+17:2',
                      self.SESSION + ':animation:017:2', self.SESSION + ':animation:17:02',
                      self.SESSION + ':animation:17:2:3', self.SESSION + ':animation:17',
                      self.SESSION + ':animation:17:2\n', self.SESSION + ':animation:١٧:2']:
            with self.subTest(token=token), self.assertRaises(AssertionError):
                native_animation_id(token, self.SESSION)

    def test_composite_accepts_reversed_projection_without_mutating_it(self):
        job = self.completed_job()
        before = copy.deepcopy(job)
        proof = composite_receipt(job, self.SESSION, 71)
        self.assertEqual(proof['operation_id'], 17)
        self.assertEqual(proof['operation_token'], self.TOKEN)
        self.assertEqual(proof['action_key'], 'manual-1:4:0')
        self.assertEqual(len(proof['receipts']), 2)
        self.assertEqual(job, before)
        job['records'].reverse()
        self.assertEqual(composite_receipt(job, self.SESSION, 71), proof)

    def test_composite_rejects_legacy_or_ambiguous_action_records(self):
        for change in ['legacy_cursor', 'duplicate_index', 'missing_counter', 'counter_native',
                       'composite_pending', 'counter_pending', 'job_uncertain', 'missing_receipt']:
            job = self.completed_job()
            if change == 'legacy_cursor':
                job['cursor'] = 3
            elif change == 'duplicate_index':
                job['records'][0]['index'] = 0
            elif change == 'missing_counter':
                job['records'].pop(0)
            elif change == 'counter_native':
                job['records'][0]['operation_id'] = self.TOKEN
            elif change == 'composite_pending':
                job['records'][1]['stage'] = 'accepted'
            elif change == 'counter_pending':
                job['records'][0]['stage'] = 'prepared'
            elif change == 'job_uncertain':
                job['state'] = 'needs_reconciliation'
            else:
                job['records'][1]['revision_receipts'].pop()
            with self.subTest(change=change), self.assertRaises(AssertionError) as raised:
                composite_receipt(job, self.SESSION, 71)
            self.assertEqual(raised.exception.args[0]['job_id'], 4)

    def test_composite_rejects_broken_chain_identity_and_revision_types(self):
        for change in ['gap', 'regression', 'pid', 'token', 'action_key', 'bool_revision',
                       'bool_pid', 'negative_revision']:
            job = self.completed_job()
            receipts = job['records'][1]['revision_receipts']
            if change == 'gap':
                receipts[1]['before']['revision'] = 13
            elif change == 'regression':
                receipts[1]['after']['revision'] = 11
            elif change == 'pid':
                receipts[1]['after']['pid'] = 72
            elif change == 'token':
                receipts[1]['operation_id'] = self.SESSION + ':animation:18:2'
            elif change == 'action_key':
                receipts[1]['action_key'] = 'manual-1:9:0'
            elif change == 'bool_revision':
                receipts[0]['before']['revision'] = True
            elif change == 'bool_pid':
                receipts[0]['before']['pid'] = True
            else:
                receipts[0]['before']['revision'] = -1
            with self.subTest(change=change), self.assertRaises(AssertionError):
                composite_receipt(job, self.SESSION, 71)
        with self.assertRaises(AssertionError):
            composite_receipt(self.completed_job(), 'other-owner', 71)
        with self.assertRaises(AssertionError):
            composite_receipt(self.completed_job(), self.SESSION, 72)

    def test_composite_permits_unchanged_certified_revisions(self):
        job = self.completed_job()
        for receipt in job['records'][1]['revision_receipts']:
            receipt['before']['revision'] = 10
            receipt['after']['revision'] = 10
        self.assertEqual(composite_receipt(job, self.SESSION, 71)['operation_id'], 17)

    def test_native_cancellation_requires_matching_observed_terminal_barrier(self):
        for after_started in (False, True):
            terminal = {'phase': 'cancelled', 'pending_ack': False,
                        'widget_triggered': after_started, 'started': after_started}
            self.assertEqual(native_cancel_outcome(terminal, after_started), 'PASS')
            for changed in [dict(terminal, pending_ack=True), dict(terminal, phase='completed'),
                            dict(terminal, phase='cancel_pending'),
                            dict(terminal, started=not after_started),
                            dict(terminal, started=int(after_started)),
                            dict(terminal, widget_triggered=not after_started),
                            dict(terminal, widget_triggered=int(after_started))]:
                self.assertEqual(native_cancel_outcome(changed, after_started), 'NOT_OBSERVED')
            for field in terminal:
                incomplete = dict(terminal)
                del incomplete[field]
                self.assertEqual(native_cancel_outcome(incomplete, after_started), 'NOT_OBSERVED')
            self.assertEqual(native_cancel_outcome(dict(terminal, phase='failed'), after_started),
                             'FAIL')
        self.assertEqual(native_cancel_outcome(None, False), 'NOT_OBSERVED')
        self.assertEqual(native_cancel_outcome({'state': 'cancelled'}, False), 'NOT_OBSERVED')

    def test_counter_reads_only_tagged_integer_and_defaults_only_missing_goal(self):
        self.assertEqual(counter_value({'show_control': {'counters': {}}}), 0)
        for number in [0, 1, -1, 1000]:
            self.assertEqual(counter_value({'show_control': {'counters': {
                'goals': {'type': 'int', 'value': number}}}}), number)
        for value in [None, 1, True, {'type': 'bool', 'value': True},
                      {'type': 'string', 'value': '1'}, {'type': 'int', 'value': True},
                      {'type': 'int', 'value': 1.0}, {'type': 'int'}]:
            with self.subTest(value=value), self.assertRaises(AssertionError):
                counter_value({'show_control': {'counters': {'goals': value}}})
        for state in [None, {}, {'show_control': {}}, {'show_control': {'counters': []}}]:
            with self.subTest(state=state), self.assertRaises(AssertionError):
                counter_value(state)


if __name__ == '__main__':
    unittest.main()
