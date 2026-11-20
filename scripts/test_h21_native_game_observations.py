"""Metadata checks only; synthetic rows do not establish physical capture."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from analyze_h21_native_game import capture_observations


def state(frames, instance=3, clipped=0, mode='window'):
    diagnostics = {k: frames for k in ('callbacks', 'surface_samples', 'consumed_surface_samples')}
    diagnostics.update({k: 0 for k in ('errors', 'invalid_samples', 'pts_regressions', 'status_changes')})
    diagnostics.update(sample_status='complete', status_counts={'complete': frames, 'suspended': 0})
    return {'sources': [{'id': 'game', 'kind': mode, 'instance_id': instance,
                         'frames': frames, 'width': 1920, 'height': 1050,
                         'capture_diagnostics': diagnostics, 'capture_delivery': 'receiving',
                         'window_identity': {'found': True, 'observed_pid': 123} if mode == 'window' else None,
                         'application_identity': {'expected_pid':123, 'health':'matches', 'process_probe':'observed',
                             'process_generation_matches':True, 'process_executable_matches':True,
                             'catalog_absence_observations':0} if mode == 'application' else None}],
            'audio_mixer': {'issues': [], 'runtime': {'inputs': [
                {'id': 'audio-1', 'levels': {'clipped_blocks': clipped}}]}},
            'capture_recovery': {'attempt_count': 0}}


class CaptureObservationTests(unittest.TestCase):
    def analyze(self, states, times=None, mode='window'):
        run = {'initial_state': state(10, mode=mode), 'last_state': state(130, mode=mode),
               'game_pid': 123, 'capture_mode':mode}
        times = times or list(range(len(states)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'samples.jsonl'
            path.write_text(''.join(json.dumps({'state': s, 'elapsed_s': t,
                                               'host_bracket_s': [t, t+.01]})+'\n'
                                    for s, t in zip(states, times)))
            return capture_observations(run, path)

    def test_transient_clipping_and_status_are_retained(self):
        middle = state(70, clipped=1)
        middle['sources'][0]['capture_diagnostics']['sample_status'] = 'suspended'
        result = self.analyze([state(10), middle, state(130)])
        self.assertEqual(result['input_clipped_blocks_max'], {'audio-1': 1})
        self.assertEqual(result['sampled_status_counts'], {'complete': 2, 'suspended': 1})
        self.assertEqual(result['native_frame_arrival_delta'], 120)

    def test_replacement_between_identical_endpoints_is_rejected(self):
        for middle in (state(70, instance=4), copy.deepcopy(state(70))):
            if middle['sources'][0]['instance_id'] == 3:
                middle['sources'][0]['window_identity']['observed_pid'] = 456
            with self.assertRaises(ValueError):
                self.analyze([state(10), middle, state(130)])

    def test_application_video_retains_verified_catalog_absence(self):
        middle = state(70, mode='application')
        middle['sources'][0]['application_identity']['catalog_absence_observations'] = 7
        result = self.analyze([state(10, mode='application'), middle, state(130, mode='application')],
                              mode='application')['application_video_identity']
        self.assertEqual(result['sampled_health'], {'matches': 3})
        self.assertEqual(result['catalog_absence_observations_max'], 7)

    def test_application_video_rejects_unverified_or_replaced_identity(self):
        for key,value in [('expected_pid',456), ('health','unobserved'), ('process_executable_matches',False)]:
            middle = state(70, mode='application')
            middle['sources'][0]['application_identity'][key] = value
            with self.assertRaises(ValueError):
                self.analyze([state(10, mode='application'), middle, state(130, mode='application')],
                             mode='application')

    def test_repeated_sample_time_cannot_establish_coverage(self):
        with self.assertRaises(ValueError):
            self.analyze([state(10), state(130)], [1, 1])

    def test_catalog_absence_is_distinct_from_unverified_os_identity(self):
        middle = state(70)
        middle['audio_mixer']['runtime']['inputs'][0]['application_identity'] = {
            'reason': 'pinned_process_verified_catalog_absent', 'process_probe': 'observed',
            'process_generation_matches': True, 'process_executable_matches': True,
            'catalog_absence_observations': 4}
        result = self.analyze([state(10), middle, state(130)])['application_identity']
        self.assertEqual(result['catalog_absence_observations_max'], {'audio-1': 4})
        self.assertEqual(result['sampled_unverified_process_identities'], 0)
        middle['audio_mixer']['runtime']['inputs'][0]['application_identity']['process_probe'] = 'unobserved'
        result = self.analyze([state(10), middle, state(130)])['application_identity']
        self.assertEqual(result['sampled_unverified_process_identities'], 1)

    def test_legacy_identity_never_claims_os_identity_verified(self):
        middle = state(70)
        middle['audio_mixer']['runtime']['inputs'][0]['application_identity'] = {'reason': 'matching'}
        result = self.analyze([state(10), middle, state(130)])['application_identity']
        self.assertEqual(result['sampled_process_probes'], {'not_in_this_binary': 1})


if __name__ == '__main__':
    unittest.main()
