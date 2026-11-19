import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from h19_metrics import resource_window, frame_window, distribution


class H19Metrics(unittest.TestCase):
    def test_no_sample_means_missing_not_zero(self):
        metrics = resource_window([], 10000, 70000)
        self.assertIsNone(metrics['observed_cpu_percent_one_core'])
        self.assertIsNone(metrics['physical_footprint_mib']['max'])
        self.assertIsNone(metrics['gpu_percent'])

    def test_crossing_warmup_cpu_interval_is_excluded(self):
        def sample(at, cpu):
            return {'elapsed_ms': at, 'rss_kib': 1024, 'processes': 1, 'resource_usage': {
                'wall_delta_ns': 1_000_000_000, 'cpu_delta_ns': cpu,
                'cpu_observed_identity_coverage_complete': True,
                'phys_footprint_bytes': 1024**2, 'processes': []}}
        result = resource_window([sample(10100, 9_000_000_000), sample(11100, 100_000_000)], 10000, 70000)
        self.assertEqual(result['observed_cpu_percent_one_core'], 10)
        self.assertEqual(result['cpu_intervals'], 1)

    def test_native_frames_use_full_declared_window(self):
        result = frame_window({'samples': [[1, 99, 100, 5], [2, 199, 200, 4]], 'samples_truncated': False}, 100, 300)
        self.assertEqual(result['retained_acquisitions'], 2)
        self.assertEqual(result['frame_age_ms']['max'], 1e-6)
        self.assertEqual(distribution([1, 2, 3])['p95'], 3)
        with self.assertRaisesRegex(ValueError, 'CLOCK_ORDER'):
            frame_window({'samples': [[1, 101, 100, 5]]}, 100, 300)


if __name__ == '__main__':
    unittest.main()
