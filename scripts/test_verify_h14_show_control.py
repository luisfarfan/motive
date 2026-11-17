"""Offline harness helper regressions; no app, socket, device or media acceptance."""
import hashlib
import pathlib
import tempfile
import unittest
from unittest import mock

import verify_h14_show_control as harness


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


if __name__ == '__main__':
    unittest.main()
