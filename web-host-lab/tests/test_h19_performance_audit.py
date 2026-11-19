"""Closed synthetic arithmetic/negative fixtures; these never execute CEF."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/h19_performance_audit.py'
SPEC = importlib.util.spec_from_file_location('h19_performance_audit', SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def process(ticks, pid=1, birth=(10, 20), start=30):
    return {'pid': pid, 'birth': list(birth), 'proc_start_abstime': start,
            'role': 'renderer', 'user_time_mach_ticks': ticks, 'system_time_mach_ticks': 1,
            'user_time_ns': ticks * 125 // 3, 'system_time_ns': 41,
            'cpu_time_ns': (ticks + 1) * 125 // 3, 'resident_bytes': 1024 ** 2,
            'phys_footprint_bytes': 512 * 1024}


def resource_fixture(reused=False, start_changed=False):
    first = process(2)
    second = process(5, birth=(10, 21) if reused else (10, 20), start=31 if start_changed else 30)
    same = not reused and not start_changed
    first['cpu_delta_ns'] = None
    second['cpu_delta_ns'] = 125 if same else None
    rows = []
    for index, p in enumerate((first, second)):
        delta = p['cpu_delta_ns']
        usage = {'sample_monotonic_ns': 1_000_000_000 + index * 1_000_000_000,
                 'wall_delta_ns': 1_000_000_000 if index else None,
                 'attempted_processes': 1, 'sampled_processes': 1,
                 'cpu_delta_processes': int(delta is not None), 'cpu_delta_ns': delta,
                 'cpu_percent_one_core': 0.0000125 if delta is not None else None,
                 'cpu_observed_identity_coverage_complete': delta is not None,
                 'memory_observed_identity_coverage_complete': True,
                 'phys_footprint_bytes': 512 * 1024, 'observed_phys_footprint_bytes': 512 * 1024,
                 'processes': [p]}
        rows.append({'elapsed_ms': index * 1000, 'phase': 'running', 'rss_kib': 1024,
                     'processes': 1, 'resource_usage': usage})
    return {'samples': rows, 'peak_tree_rss_kib': 1024,
            'resource_measurements': {'mach_timebase': {'numer': 125, 'denom': 3},
                                      'total_samples': 2, 'partial_samples': 1 if same else 2,
                                      'valid_cpu_intervals': 1 if same else 0,
                                      'observed_cpu_delta_ns': 125 if same else 0,
                                      'measured_wall_delta_ns': 1_000_000_000 if same else 0,
                                      'observed_cpu_mean_percent_one_core': .0000125 if same else None,
                                      'peak_observed_tree_phys_footprint_bytes': 512 * 1024}}


def frames_fixture(count=1800):
    rows = [[i + 1, 11_000_000_000 + i * 33_333_333,
             11_005_000_000 + i * 33_333_333, 100_000] for i in range(count)]
    accounting = dict.fromkeys(audit.CLASSIFICATIONS, 0)
    accounting.update(paints=count, consumed=count, acquired=count, retained_leases=0,
                      retained_bytes=0, copied_bytes=count * 640 * 360 * 4, copy_ns=count * 10000)
    telemetry = {'native_executed': True, 'samples_truncated': False, 'sample_capacity_drops': 0,
                 'samples': rows, 'accounting_v2': accounting, 'successful_disk_writes': count,
                 'completion_rejected': 0}
    manifest = {'instance': 1, 'generation': 4, 'epoch': 1, 'created_ns': 1_000_000_000,
                'first_nontransparent_paint_ns': 1_100_000_000, 'closed_ns': 73_000_000_000}
    return telemetry, manifest


class ResourceAudit(unittest.TestCase):
    def test_tick_conversion_sums_before_floor_and_keeps_one_core_unit(self):
        rows, totals = audit.reconstruct_resources(resource_fixture())
        self.assertEqual(totals['observed_cpu_delta_ns'], 125)
        self.assertAlmostEqual(audit.resource_window(rows, 0, 2000)['observed_cpu_percent_one_core'], .0000125)

    def test_pid_reuse_is_not_zero_cpu(self):
        rows, totals = audit.reconstruct_resources(resource_fixture(reused=True))
        self.assertIsNone(rows[1]['resource_usage']['cpu_delta_ns'])
        self.assertIsNone(totals['observed_cpu_mean_percent_one_core'])

    def test_start_identity_change_is_not_zero_cpu(self):
        rows, _ = audit.reconstruct_resources(resource_fixture(start_changed=True))
        self.assertIsNone(rows[1]['resource_usage']['cpu_delta_ns'])

    def test_tampered_cpu_delta_rejected(self):
        raw = resource_fixture()
        raw['samples'][1]['resource_usage']['processes'][0]['cpu_delta_ns'] = 0
        with self.assertRaisesRegex(ValueError, 'process_cpu_delta_ns'):
            audit.reconstruct_resources(raw)

    def test_tampered_peak_rejected(self):
        raw = resource_fixture()
        raw['peak_tree_rss_kib'] = 1
        with self.assertRaisesRegex(ValueError, 'peak_tree_rss_kib'):
            audit.reconstruct_resources(raw)

    def test_boundary_crossing_interval_excluded(self):
        rows, _ = audit.reconstruct_resources(resource_fixture())
        window = audit.resource_window(rows, 500, 2000)
        self.assertEqual(window['sample_count'], 1)
        self.assertIsNone(window['observed_cpu_percent_one_core'])
        self.assertEqual(window['cpu_intervals'], 0)

    def test_empty_window_preserves_missing_values(self):
        window = audit.resource_window([], 10000, 70000)
        self.assertIsNone(window['physical_footprint_mib']['median'])
        self.assertIsNone(window['observed_cpu_percent_one_core'])
        self.assertIsNone(window['unique_physical_mib'])
        self.assertIsNone(window['gpu_percent'])

    def test_role_rss_and_footprint_are_separate(self):
        rows, _ = audit.reconstruct_resources(resource_fixture())
        role = audit.resource_window(rows, 0, 2000)['roles']['renderer']
        self.assertEqual(role['rss_mib']['median'], 1)
        self.assertEqual(role['footprint_mib']['median'], .5)


class FrameAudit(unittest.TestCase):
    def test_full_window_with_actual_paint_and_conservation_passes(self):
        telemetry, manifest = frames_fixture()
        result = audit.audit_frames(telemetry, manifest, 30, True)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['acquisition_fps_in_window'], 30)
        self.assertEqual(result['frame_age_ms']['p95'], 5)
        self.assertEqual(result['first_actual_paint_ms'], 100)

    def test_acquisition_age_does_not_hide_slow_completion(self):
        telemetry, manifest = frames_fixture()
        telemetry['samples'][0][3] = 500_000_000
        result = audit.audit_frames(telemetry, manifest, 30, True)
        self.assertEqual(result['frame_age_ms']['max'], 5)
        self.assertEqual(result['consumer_completion_age_ms']['max'], 505)
        self.assertEqual(result['consumer_work_over_100_ms'], 1)
        self.assertEqual(result['largest_consumer_work'][0]['epoch_relative_seconds'], 10.005)

    def test_exact_95_percent_rate_passes_but_one_fewer_fails(self):
        for count, expected in ((1710, 'PASS'), (1709, 'FAIL')):
            telemetry, manifest = frames_fixture(count)
            self.assertEqual(audit.audit_frames(telemetry, manifest, 30, True)['status'], expected)

    def test_truncated_trace_cannot_pass(self):
        telemetry, manifest = frames_fixture()
        telemetry['samples_truncated'] = True
        with self.assertRaisesRegex(ValueError, 'TRUNCATION'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_short_window_cannot_pass(self):
        telemetry, manifest = frames_fixture()
        manifest['closed_ns'] = 65_000_000_000
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_NATIVE_WINDOW'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_conservation_tamper_rejected(self):
        telemetry, manifest = frames_fixture()
        telemetry['accounting_v2']['paints'] += 1
        with self.assertRaisesRegex(ValueError, 'PAINT_CONSERVATION'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_missing_consumed_sample_rejected(self):
        telemetry, manifest = frames_fixture()
        telemetry['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'CONSUMED_SAMPLE_COUNT'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_negative_age_rejected(self):
        telemetry, manifest = frames_fixture()
        telemetry['samples'][0][1] = telemetry['samples'][0][2] + 1
        with self.assertRaisesRegex(ValueError, 'NATIVE_CLOCK_ORDER'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_old_actual_paint_rejected(self):
        telemetry, manifest = frames_fixture()
        manifest['first_nontransparent_paint_ns'] = 0
        with self.assertRaisesRegex(ValueError, 'FIRST_ACTUAL_PAINT_CLOCK'):
            audit.audit_frames(telemetry, manifest, 30, True)

    def test_static_empty_steady_window_has_no_invented_fps_gate(self):
        telemetry, manifest = frames_fixture(0)
        result = audit.audit_frames(telemetry, manifest, 30, False)
        self.assertEqual(result['status'], 'PASS')
        self.assertIsNone(result['frame_age_ms']['p95'])
        self.assertIsNone(result['gates']['animated_acquisition_fps_at_least_95_percent'])

    def test_native_arbitrary_window_uses_native_timestamps(self):
        telemetry, _ = frames_fixture()
        result = audit.native_interval(telemetry['samples'], 11_000_000_000, 71_000_000_000)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['acquisition_fps'], 30)
        self.assertEqual(result['completed_acquisitions'], 1800)

    def test_late_native_window_preserves_missing_frames_and_fails(self):
        telemetry, _ = frames_fixture()
        result = audit.native_interval(telemetry['samples'], 540_000_000_000, 590_000_000_000)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['completed_acquisitions'], 0)
        self.assertIsNone(result['frame_age_ms']['p95'])


class FixedFileCounters(unittest.TestCase):
    def counters(self):
        return {'latest_file_full_writes': 1800, 'latest_file_ftruncate_calls': 1,
                'latest_file_rejected_geometry_or_descriptor': 0,
                'latest_file_fixed_bytes': 640 * 360 * 4, 'successful_disk_writes': 1800}

    def test_legacy_missing_counters_remain_not_evaluated(self):
        self.assertEqual(audit.fixed_file_counters({}, 640, 360)['status'], 'NOT_PRESENT_LEGACY_BINARY')

    def test_required_candidate_counters_cannot_disappear(self):
        with self.assertRaisesRegex(ValueError, 'FIXED_FILE_COUNTERS_MISSING'):
            audit.fixed_file_counters({}, 640, 360, required=True)

    def test_full_write_every_frame_with_one_truncate(self):
        self.assertEqual(audit.fixed_file_counters(self.counters(), 640, 360, required=True)['status'], 'PASS')

    def test_skipped_full_write_is_rejected(self):
        counters = self.counters()
        counters['latest_file_full_writes'] -= 1
        with self.assertRaisesRegex(ValueError, 'LATEST_FULL_WRITES'):
            audit.fixed_file_counters(counters, 640, 360, required=True)

    def test_repeated_truncate_is_rejected(self):
        counters = self.counters()
        counters['latest_file_ftruncate_calls'] = 1800
        with self.assertRaisesRegex(ValueError, 'LATEST_FTRUNCATE_ONCE'):
            audit.fixed_file_counters(counters, 640, 360, required=True)


if __name__ == '__main__':
    unittest.main()
