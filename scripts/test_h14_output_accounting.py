#!/usr/bin/env python3
"""Unit tests of trace classification only; these are not multimedia evidence."""
import copy
import unittest

from verify_h14_output_integrity import correlate_tail


def native(sequence, kind, pts):
    return {'sequence': sequence, 'media_type': kind, 'pts': pts,
            'timebase_num': 1, 'timebase_den': 1000,
            'sys_dts_usec': 1_000_000 + pts * 1000}


def fixture():
    summary = {'observed_video_packets': 2, 'observed_audio_packets': 2,
        'trace_missed_records': 0, 'trace_overwritten_records': 0,
        'stop_requested_ns': 1_031_000_000, 'stop_call_returned_ns': 1_032_000_000}
    trace = {'snapshot_busy': False, 'summary': summary,
        'packets': [native(1, 'video', 0), native(2, 'audio', 0),
                    native(3, 'audio', 21), native(4, 'video', 33)]}
    packets = [{'codec_type': 'video', 'pts_time': '0'},
               {'codec_type': 'audio', 'pts_time': '0'},
               {'codec_type': 'audio', 'pts_time': '.021'},
               {'codec_type': 'video', 'pts_time': '.033'}]
    return copy.deepcopy(trace), trace, packets


class Classification(unittest.TestCase):
    def test_complete_tail_requires_every_traced_packet(self):
        initial, final, packets = fixture()
        result = correlate_tail(initial, final, packets)
        self.assertEqual(result['status'], 'TRACED_TAIL_PRESENT')
        self.assertEqual(result['raw_dispatch_video_packets'], 2)

    def test_stop_boundary_absence_stays_visible(self):
        initial, final, packets = fixture()
        result = correlate_tail(initial, final, packets[:-1])
        self.assertEqual(result['status'], 'STOP_BOUNDARY_PACKETS_NOT_DELIVERED')
        self.assertEqual(len(result['kinds']['video']['absent']), 1)
        self.assertEqual(result['raw_dispatch_video_packets'], 2)
        self.assertEqual(len(packets), 4)

    def test_missing_packet_before_stop_is_failure(self):
        initial, final, packets = fixture()
        final['summary']['stop_requested_ns'] = 1_050_000_000
        final['summary']['stop_call_returned_ns'] = 1_051_000_000
        result = correlate_tail(initial, final, packets[:-1])
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['kinds']['video']['absent'][0]['stop_relation'], 'before_stop_bracket')

    def test_uncertain_stop_bracket_does_not_become_cutoff_success(self):
        initial, final, packets = fixture()
        final['summary']['stop_call_returned_ns'] = 1_035_000_000
        self.assertEqual(correlate_tail(initial, final, packets[:-1])['status'], 'INCONCLUSIVE')

    def test_metadata_loss_and_missing_origin_cannot_pass(self):
        for mutate in (
            lambda initial, final: initial['summary'].update(trace_overwritten_records=1),
            lambda initial, final: final['packets'].pop(2),
            lambda initial, final: final.update(snapshot_busy=True),
        ):
            initial, final, packets = fixture()
            mutate(initial, final)
            self.assertEqual(correlate_tail(initial, final, packets)['status'], 'INCONCLUSIVE')


if __name__ == '__main__':unittest.main()
