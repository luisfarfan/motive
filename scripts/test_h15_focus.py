import unittest
from h15_focus import corroborate


class FocusEvidenceTests(unittest.TestCase):
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
