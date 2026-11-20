import unittest

from h21_audio_observation import classify_issues


class AudioObservationTests(unittest.TestCase):
    def setUp(self):
        self.warning = dict(input_id='mic', code='AUDIO_INPUT_CLIPPING',
                            severity='warning', recovery='reduce_device_gain')

    def test_strict_default_preserves_rejection(self):
        self.assertEqual(classify_issues([self.warning], 'mic'), ([], [self.warning]))

    def test_explicit_collection_retains_original_warning(self):
        self.assertEqual(classify_issues([self.warning], 'mic', True), ([self.warning], []))

    def test_other_input_and_mix_clipping_still_block(self):
        for change in (dict(input_id='guest'), dict(input_id=None, code='AUDIO_MIX_CLIPPING')):
            issue = self.warning | change
            self.assertEqual(classify_issues([issue], 'mic', True), ([], [issue]))

    def test_failure_information_and_unknown_severity_still_block(self):
        for change in (dict(code='AUDIO_DEVICE_UNAVAILABLE'), dict(severity='error'),
                       dict(severity='info'), dict(recovery='reconnect_audio_input')):
            issue = self.warning | change
            self.assertEqual(classify_issues([issue], 'mic', True), ([], [issue]))

    def test_mixed_warnings_do_not_hide_a_failure(self):
        failure = dict(input_id='guest', code='AUDIO_APPLICATION_UNAVAILABLE', severity='error')
        self.assertEqual(classify_issues([self.warning, failure], 'mic', True),
                         ([self.warning], [failure]))


if __name__ == '__main__':
    unittest.main()
