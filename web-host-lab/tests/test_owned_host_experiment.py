from concurrent.futures import ThreadPoolExecutor
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import run_owned_host_experiment as experiment

spec = importlib.util.spec_from_file_location('motive_experiment_test_supervisor', ROOT / 'poc/browser-host/supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = supervisor
spec.loader.exec_module(supervisor)


class OwnedHostExperimentTests(unittest.TestCase):
    def test_only_fixed_host_counts_and_bounded_sampling_are_cli_inputs(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for tail in (['--hosts', '2'], ['--hosts', '3', '--sample-interval-ms', '1'],
                         ['--hosts', '1', '--command', '/bin/sh']):
                with self.assertRaises(SystemExit):
                    experiment.parser().parse_args(['--build-root', '/missing', '--expected-sha256', 'a' * 64] + tail)

    def test_combined_limit_is_not_multiplied_by_host_count(self):
        budget = experiment.AggregateBudget(3, 2048 * 1024)
        budget.observe(1, {'rss_kib': 800 * 1024})
        budget.observe(2, {'rss_kib': 800 * 1024})
        self.assertFalse(budget.cancel.is_set())
        budget.observe(3, {'rss_kib': 800 * 1024})
        self.assertTrue(budget.cancel.is_set())
        self.assertTrue(budget.triggered)
        self.assertIsNone(budget.peak_footprint_bytes)
        self.assertIsNone(budget.samples[-1]['latest_observed_tree_phys_footprint_bytes'])

    def test_footprint_sum_uses_latest_observations_not_independent_peaks(self):
        budget = experiment.AggregateBudget(3, 2048 * 1024)
        budget.observe(1, {'rss_kib': 1, 'resource_usage': {'phys_footprint_bytes': 100}})
        budget.observe(1, {'rss_kib': 1, 'resource_usage': {'phys_footprint_bytes': 10}})
        budget.observe(2, {'rss_kib': 1, 'resource_usage': {'phys_footprint_bytes': 100}})
        self.assertEqual(budget.peak_footprint_bytes, 110)
        budget.finished(1)
        self.assertNotIn(1, budget.latest)

    def test_missing_measurement_summary_remains_null(self):
        report = experiment.summarize_hosts([{'supervision': {}}], 1000000)
        self.assertIsNone(report['observed_cpu_delta_ns'])
        self.assertIsNone(report['observed_cpu_percent_over_launch_to_join_one_core'])
        self.assertIsNone(report['gpu_percent'])
        self.assertEqual(report['observed_process_roles'], {})

    def test_setup_failure_never_marks_native_execution(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as directory:
            root = Path(directory)
            output = root / 'output'; output.mkdir()
            private = root / 'private'; private.mkdir()
            (private / 'host-1').mkdir()
            budget = experiment.AggregateBudget(1, 2048 * 1024)
            report = experiment.run_host(1, None, root, private, output, None, budget, threading.Barrier(1))
            self.assertEqual(report['status'], 'FAIL')
            self.assertFalse(report['native_host_execution_attempted'])
            self.assertFalse(report['native_host_executed'])
            self.assertTrue(budget.cancel.is_set())

    def test_three_owned_python_trees_cancel_at_aggregate_limit_and_clean_up(self):
        # Real Python processes only. Each is below 128MiB; their sum exceeds it.
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as directory:
            root = Path(directory)
            budget = experiment.AggregateBudget(3, 128 * 1024)
            barrier = threading.Barrier(3)
            def launch(index):
                own = root / str(index); own.mkdir(mode=0o700)
                owner = supervisor.Supervisor(own, deadline_seconds=3, rss_limit_kib=128 * 1024, interval_seconds=.05)
                barrier.wait(timeout=2)
                try:
                    return owner.run([sys.executable, '-c', 'import time; memory=bytearray(64*1024*1024); time.sleep(2)'],
                                     cancelled=budget.cancel.is_set,
                                     on_sample=lambda sample: budget.observe(index, sample))
                finally:
                    budget.finished(index)
            with ThreadPoolExecutor(max_workers=3) as executor:
                reports = list(executor.map(launch, range(3)))
            self.assertTrue(budget.triggered, budget.samples)
            self.assertGreater(budget.peak_kib, 128 * 1024)
            self.assertTrue(all(report['final_cleanup_observed_tree'] for report in reports), reports)
            self.assertTrue(all(report['reason'] == 'cancelled' for report in reports), reports)


if __name__ == '__main__':
    unittest.main()
