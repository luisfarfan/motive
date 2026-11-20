"""Instrument tests only; no claim of decoded delivery or physical capture."""
import copy
import unittest
from h21_trace_origin import collect_origin


def observation(kinds=(), busy=False, missed=0, overwritten=0, attempt=7):
    return {'output': {'attempt_id': attempt}, 'packet_trace': {
        'snapshot_busy': busy, 'summary': {'trace_missed_records': missed,
                                           'trace_overwritten_records': overwritten},
        'packets': [{'sequence': i+1, 'media_type': kind}
                    for i, kind in enumerate(kinds)]}}


class Client:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = 0

    def call(self, op, target):
        assert op == 'output_diagnostics' and target == 'streaming'
        self.calls += 1
        return next(self.rows)


class OriginTests(unittest.TestCase):
    def collect(self, rows, **kwargs):
        client = Client(rows)
        result = collect_origin(client, 'streaming', 7, poll=lambda _: None,
                                **kwargs)
        return result, client.calls

    def test_active_empty_then_audio_only_does_not_establish_av_origin(self):
        complete = observation(['audio', 'video'])
        before = copy.deepcopy(complete)
        result, count = self.collect([observation(), observation(['audio']), complete])
        self.assertEqual(count, 3)
        self.assertEqual(result, before)

    def test_busy_snapshot_is_not_used(self):
        result, count = self.collect([observation(['audio', 'video'], busy=True),
                                      observation(['audio', 'video'])])
        self.assertEqual(count, 2)
        self.assertFalse(result['packet_trace']['snapshot_busy'])

    def test_lost_metadata_cannot_be_recovered_by_polling_later(self):
        for options in [{'missed': 1}, {'overwritten': 1}, {'attempt': 8}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.collect([observation(['audio', 'video'], **options)])

    def test_missing_first_sequence_is_rejected(self):
        row = observation(['audio', 'video'])
        row['packet_trace']['packets'][0]['sequence'] = 2
        with self.assertRaises(ValueError):
            self.collect([row])

    def test_deadline_does_not_claim_an_empty_origin(self):
        ticks = iter([0, 5])
        with self.assertRaises(TimeoutError):
            self.collect([observation()], clock=lambda: next(ticks))


if __name__ == '__main__':
    unittest.main()
