"""Pure streaming math checks; synthetic bytes do not certify Motive media."""
from array import array
import copy
import math
import sys
import unittest

from analyze_h14_soak import validate_streams
from h14_soak_helpers import (HashRuns, PCMStats, QuadrantFreshness, Timeline,
                              packet_origin_proof, tail_candidates, tail_status_with_ambiguity)


class SoakAnalysisTests(unittest.TestCase):
    @staticmethod
    def streams(width=1920, height=1080):
        return {'streams': [
            {'codec_type': 'video', 'codec_name': 'h264', 'width': width,
             'height': height, 'avg_frame_rate': '60/1'},
            {'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '48000',
             'channels': 2}]}

    def test_video_dimensions_match_explicit_plan_at_both_resolutions(self):
        for width, height in ((1920, 1080), (1280, 720)):
            for fps in (30, 60):
                with self.subTest(width=width, height=height, fps=fps):
                    probe = self.streams(width, height)
                    probe['streams'][0]['avg_frame_rate'] = f'{fps}/1'
                    result = validate_streams(probe,
                        {'resolution': f'{width}x{height}', 'fps': fps})
                    self.assertEqual((result['width'], result['height']), (width, height))

    def test_other_supported_resolution_is_still_a_mismatch(self):
        for actual, expected in (((1920, 1080), '1280x720'), ((1280, 720), '1920x1080')):
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaisesRegex(ValueError, 'Video format differs'):
                    validate_streams(self.streams(*actual), {'resolution': expected, 'fps': 60})

    def test_unknown_or_missing_plan_resolution_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown controlled-soak'):
            validate_streams(self.streams(), {'fps': 60})
        for resolution in (None, 'full_hd1080', '640x360'):
            with self.subTest(resolution=resolution):
                with self.assertRaisesRegex(ValueError, 'Unknown controlled-soak'):
                    validate_streams(self.streams(), {'resolution': resolution, 'fps': 60})

    def test_format_guards_still_reject_codec_cadence_audio_and_extra_streams(self):
        baseline = self.streams()
        for index, field, value in ((0, 'codec_name', 'hevc'), (0, 'avg_frame_rate', '30/1'),
                                   (1, 'sample_rate', '44100'), (1, 'channels', 1)):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(baseline)
                changed['streams'][index][field] = value
                with self.assertRaises(ValueError):
                    validate_streams(changed, {'resolution': '1920x1080', 'fps': 60})
        baseline['streams'].append(copy.deepcopy(baseline['streams'][1]))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            validate_streams(baseline, {'resolution': '1920x1080', 'fps': 60})

    def test_legitimate_30_to_60_duplicates_keep_duration_and_frame_count(self):
        runs = HashRuns()
        for index in range(120):
            runs.add(str(index // 2), index / 60, 1 / 60)
        result = runs.finish()
        self.assertEqual(result['frames'], 120)
        self.assertEqual(result['changing_pairs'], 59)
        self.assertAlmostEqual(result['longest_constant_run']['seconds'], 2 / 60)

    def test_static_quadrant_is_not_hidden_by_motion_in_another(self):
        stats = QuadrantFreshness()
        for index in range(65):
            frame = bytearray([64] * (128 * 72))
            for row in range(36):
                frame[row * 128:row * 128 + 64] = bytes([64 + 16 * (index % 3)]) * 64
            stats.add(bytes(frame), index / 60, 1 / 60)
        quadrants = stats.finish()['quadrants']
        self.assertGreater(quadrants[0]['meaningful']['changing_pairs'], 0)
        self.assertEqual(quadrants[3]['meaningful']['changing_pairs'], 0)
        self.assertGreater(quadrants[3]['exact']['longest_constant_run']['seconds'], 1.)

    def test_small_quantization_changes_do_not_prove_meaningful_motion(self):
        stats = QuadrantFreshness()
        for index in range(4):
            stats.add(bytes([64 + index % 2]) * (128 * 72), index / 60, 1 / 60)
        result = stats.finish()['quadrants'][0]
        self.assertEqual(result['exact']['changing_pairs'], 3)
        self.assertEqual(result['meaningful']['changing_pairs'], 0)

    def test_pcm_handles_arbitrary_chunk_boundaries_and_independent_channels(self):
        windows, tones = [], []
        stats = PCMStats(windows.append, tones.append, tone_seconds={0}, sample_rate=4800)
        samples = array('f')
        for frame in range(4800):
            value = .2 * math.sin(2 * math.pi * 440 * frame / 4800)
            samples.extend((value, value / 2))
        if sys.byteorder != 'little':
            samples.byteswap()
        raw = samples.tobytes()
        for start in range(0, len(raw), 137):
            stats.feed(raw[start:start + 137])
        result = stats.finish()
        self.assertEqual(result['frames_per_channel'], 4800)
        self.assertEqual(len(windows), 10)
        self.assertAlmostEqual(result['channel_statistics'][0]['rms'], .2 / math.sqrt(2), places=6)
        self.assertAlmostEqual(tones[0]['channels'][0]['440'], .2, places=6)
        self.assertAlmostEqual(tones[0]['channels'][1]['440'], .1, places=6)

    def test_pcm_counts_silence_clipping_and_rejects_truncated_stereo(self):
        stats = PCMStats(lambda _: None, lambda _: None, sample_rate=4800)
        stats.feed(array('f', [0., 1.] * 480).tobytes())
        result = stats.finish()['channel_statistics']
        self.assertEqual(result[0]['full_windows_below_minus80_dbfs'], 1)
        self.assertEqual(result[1]['samples_abs_ge_0_999'], 480)
        truncated = PCMStats(lambda _: None, lambda _: None)
        truncated.feed(b'abc')
        with self.assertRaises(ValueError):
            truncated.finish()

    def test_nonfinite_and_partial_pcm_do_not_become_valid_full_windows(self):
        rows = []
        stats = PCMStats(rows.append, lambda _: None, sample_rate=4800)
        stats.feed(array('f', [math.nan, math.inf, .25, -.25]).tobytes())
        result = stats.finish()
        self.assertEqual(result['partial_windows'], 1)
        self.assertEqual(result['windows_100ms'], 0)
        self.assertFalse(rows[0]['full_100ms_window'])
        self.assertEqual([value['nonfinite_samples'] for value in result['channel_statistics']], [1, 1])

    def test_timeline_does_not_hide_missing_timestamps_or_regressions(self):
        value = Timeline(.025)
        for pts in ('0', '.016', None, '.016', '.080'):
            value.add(pts)
        result = value.result()
        self.assertEqual((result['count'], result['missing'], result['non_increasing'], result['gaps_over_limit']), (5, 1, 1, 1))

    def test_origin_prefix_and_ambiguous_tail_candidates(self):
        records, actual = [], {'video': [], 'audio': []}
        for index in range(3):
            for kind in ('video', 'audio'):
                records.append({'sequence': len(records) + 1, 'media_type': kind,
                                'pts': index * 20, 'timebase_num': 1, 'timebase_den': 1000,
                                'size': 128 + index, 'keyframe': True})
                actual[kind].append({'codec_type': kind, 'pts_time': str(index * .02 + 1),
                                     'size': str(128 + index), 'flags': 'K_'})
        trace = {'snapshot_busy': False, 'summary': {'trace_missed_records': 0,
                  'trace_overwritten_records': 0}, 'packets': records}
        self.assertEqual(packet_origin_proof(trace, actual)['status'], 'MATCHED_METADATA_PREFIX')
        _, counts = tail_candidates(trace, trace, actual, {'video': [1., 1.02, 1.02, 1.04], 'audio': [1., 1.02, 1.04]})
        self.assertEqual(next(row['candidates_within_tolerance'] for row in counts if row['kind'] == 'video' and row['native_sequence'] == 3), 2)
        trace['summary']['trace_missed_records'] = 1
        self.assertEqual(packet_origin_proof(trace, actual)['status'], 'INCONCLUSIVE')
        trace['summary']['trace_missed_records'] = 0
        actual['audio'][1]['size'] = '9999'
        self.assertEqual(packet_origin_proof(trace, actual)['status'], 'INCONCLUSIVE')

    def test_ambiguous_match_never_hides_independent_tail_failure(self):
        counts = [{'candidates_within_tolerance': 0}, {'candidates_within_tolerance': 2}]
        failed = tail_status_with_ambiguity('FAIL', counts)
        self.assertEqual(failed['status'], 'FAIL')
        self.assertEqual(failed['ambiguity_reason'], 'ambiguous_timestamp_matches')
        self.assertEqual(tail_status_with_ambiguity('TRACED_TAIL_PRESENT', counts)['status'], 'INCONCLUSIVE')
        self.assertEqual(tail_status_with_ambiguity('FAIL', [{'candidates_within_tolerance': 0}]), {'status': 'FAIL'})


if __name__ == '__main__':
    unittest.main()
