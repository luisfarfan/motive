import unittest
from h15_focus import corroborate, fixture_at_probe_end


class FocusEvidenceTests(unittest.TestCase):
    def probe(self):
        return dict(version=1, clock='NSProcessInfo.systemUptime', observer_pid=30,
                    expected_pid=10, window_id=40, window={'owner_pid': 10},
                    before_s=100.1, after_s=100.2, frontmost_pid=10,
                    frontmost_terminated=False)

    def fixture(self, timestamp=100., **changes):
        return dict(event='window_state', pid=10, window_id=40, uptime_seconds=timestamp,
                    app_active=True, key_window=True) | changes

    def assess(self, events, probe=None):
        probe = self.probe() if probe is None else probe
        return corroborate(probe, fixture_at_probe_end(probe, events),
                           fixture_pid=10, window_id=40, expected_pid=10)

    def test_log_growth_after_probe_keeps_the_same_observation(self):
        before = [dict(event='ready'), self.fixture(99.8), self.fixture(100.15)]
        after = before + [self.fixture(100.21), self.fixture(101.)]
        self.assertEqual(fixture_at_probe_end(self.probe(), before), before[-1])
        self.assertEqual(fixture_at_probe_end(self.probe(), after), before[-1])
        self.assertEqual(self.assess(after)['status'], 'PASS')
        # The former latest-log-row path rejects the newly published future state.
        self.assertEqual(corroborate(self.probe(), after[-1], fixture_pid=10,
                                    window_id=40, expected_pid=10)['status'], 'BLOCKED')

    def test_missing_stale_future_or_malformed_samples_still_block(self):
        for events in ([], [dict(event='ready')], [self.fixture(100.21)],
                       [self.fixture(98.599)], [self.fixture(float('nan'))],
                       [self.fixture(), self.fixture(float('inf'))],
                       [self.fixture(None)], [self.fixture(True)]):
            with self.subTest(events=events):
                self.assertEqual(self.assess(events)['status'], 'BLOCKED')
        self.assertEqual(self.assess([self.fixture(98.6)])['status'], 'PASS')
        self.assertEqual(self.assess([self.fixture(100.2)])['status'], 'PASS')
        for after in (None, True, float('inf'), float('nan')):
            self.assertEqual(self.assess([self.fixture()], {**self.probe(), 'after_s': after})['status'], 'BLOCKED')

    def test_latest_timestamp_does_not_search_for_favorable_focus_or_identity(self):
        for changes in ({'app_active': False}, {'key_window': False}, {'pid': 99}, {'window_id': 41}):
            newest = self.fixture(100.1, **changes)
            events = [newest, self.fixture(100.)]
            self.assertEqual(fixture_at_probe_end(self.probe(), events), newest)
            self.assertEqual(self.assess(events)['status'], 'BLOCKED')
        conflicting_same_time = self.fixture(100., app_active=False)
        self.assertEqual(self.assess([self.fixture(), conflicting_same_time])['status'], 'BLOCKED')

    def test_requires_independent_agreement_in_both_directions(self):
        for front in (10, 20):
            probe = dict(version=1, clock='NSProcessInfo.systemUptime', observer_pid=30,
                         expected_pid=front, window_id=40, window={'owner_pid': 10},
                         before_s=100.1, after_s=100.2, frontmost_pid=front,
                         frontmost_terminated=False)
            fixture = dict(pid=10, window_id=40, uptime_seconds=100.,
                           app_active=front == 10, key_window=front == 10)
            def check(p=probe, f=fixture):
                return corroborate(p, f, fixture_pid=10, window_id=40, expected_pid=front)
            self.assertEqual(check()['status'], 'PASS')
            for wrong in ({'frontmost_pid': 99}, {'window': None}, {'observer_pid': 10},
                          {'after_s': 101.}, {'before_s': float('nan')},
                          {'clock': 'unknown'}, {'frontmost_terminated': True}):
                self.assertEqual(check({**probe, **wrong})['status'], 'BLOCKED')
            for wrong in ({'app_active': front != 10}, {'key_window': front != 10},
                          {'uptime_seconds': 98.}, {'uptime_seconds': 101.}, {'pid': 99}):
                self.assertEqual(check(f={**fixture, **wrong})['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
