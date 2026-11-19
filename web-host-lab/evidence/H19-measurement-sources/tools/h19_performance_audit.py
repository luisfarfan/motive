#!/usr/bin/env python3
"""Independent read-only H19 evidence audit. Never starts or imports the native runner.

Python monotonic resource windows and native steady-clock frame windows remain
separate. A PASS applies only to the selected owned fixture and retained samples.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

LAB = Path(__file__).resolve().parents[1]
MIB = 1024 ** 2
CLASSIFICATIONS = ('pending', 'leased', 'coalesced', 'consumed',
                   'released_unconsumed', 'invalidated_close', 'revoked_generation', 'stale')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def distribution(values):
    ordered = sorted(values)
    return {'n': len(ordered), 'median': statistics.median(ordered) if ordered else None,
            'p95': ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None,
            'max': ordered[-1] if ordered else None}


def require(condition, label):
    if not condition:
        raise ValueError(label)


def equal(actual, expected, path='value'):
    """Compare independently reconstructed metrics without rounding the stored values."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict), path + ':OBJECT')
        for key, value in expected.items():
            require(key in actual, path + ':MISSING:' + key)
            equal(actual[key], value, path + '.' + key)
    elif isinstance(expected, float):
        require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-6), path + ':NUMBER')
    else:
        require(actual == expected, path + ':MISMATCH')


def reconstruct_resources(raw):
    """Re-derive cumulative-tick conversion, consecutive identity CPU, and footprints."""
    timebase = raw['resource_measurements']['mach_timebase']
    numer, denom = timebase['numer'], timebase['denom']
    require(numer > 0 and denom > 0, 'TIMEBASE')
    previous, previous_ns = {}, None
    derived, total_cpu, total_wall, intervals, partial = [], 0, 0, 0, 0
    complete_footprints = []
    for sample in raw['samples']:
        usage = sample['resource_usage']
        now = usage['sample_monotonic_ns']
        wall = None if previous_ns is None else now - previous_ns
        require(wall is None or wall > 0, 'RESOURCE_CLOCK_ORDER')
        equal(usage['wall_delta_ns'], wall, 'wall_delta_ns')
        current, records, deltas = {}, [], []
        for row in usage['processes']:
            identity = (row['pid'], tuple(row['birth']))
            require(identity not in current, 'DUPLICATE_PROCESS_IDENTITY')
            ticks = row['user_time_mach_ticks'] + row['system_time_mach_ticks']
            cpu_ns = ticks * numer // denom
            equal(row['user_time_ns'], row['user_time_mach_ticks'] * numer // denom, 'user_time_ns')
            equal(row['system_time_ns'], row['system_time_mach_ticks'] * numer // denom, 'system_time_ns')
            equal(row['cpu_time_ns'], cpu_ns, 'cpu_time_ns')
            old = previous.get(identity)
            delta = None
            if old and old['proc_start_abstime'] == row['proc_start_abstime'] and wall:
                difference = cpu_ns - old['cpu_time_ns']
                if difference >= 0:
                    delta = difference
            equal(row['cpu_delta_ns'], delta, 'process_cpu_delta_ns')
            current[identity] = dict(row, cpu_time_ns=cpu_ns)
            records.append(dict(row, cpu_delta_ns=delta))
            if delta is not None:
                deltas.append(delta)
        count = sample['processes']
        complete_memory = bool(count) and len(records) == count
        complete_cpu = complete_memory and len(deltas) == count and set(current) == set(previous)
        footprint = sum(row['phys_footprint_bytes'] for row in records)
        cpu = sum(deltas) if deltas else None
        independent = {'wall_delta_ns': wall, 'attempted_processes': count,
                       'sampled_processes': len(records), 'cpu_delta_processes': len(deltas),
                       'cpu_delta_ns': cpu,
                       'cpu_percent_one_core': 100 * cpu / wall if cpu is not None and wall else None,
                       'cpu_observed_identity_coverage_complete': complete_cpu,
                       'memory_observed_identity_coverage_complete': complete_memory,
                       'phys_footprint_bytes': footprint if complete_memory else None,
                       'observed_phys_footprint_bytes': footprint if records else None}
        equal(usage, independent, 'resource_usage')
        if complete_memory:
            complete_footprints.append(footprint)
        if not (complete_memory and complete_cpu):
            partial += 1
        if cpu is not None and wall:
            total_cpu += cpu
            total_wall += wall
            intervals += 1
        derived.append(dict(sample, resource_usage=dict(independent, processes=records)))
        previous, previous_ns = current, now
    summary = {'total_samples': len(derived), 'partial_samples': partial,
               'valid_cpu_intervals': intervals, 'observed_cpu_delta_ns': total_cpu,
               'measured_wall_delta_ns': total_wall,
               'observed_cpu_mean_percent_one_core': 100 * total_cpu / total_wall if total_wall else None,
               'peak_observed_tree_phys_footprint_bytes': max(complete_footprints, default=None)}
    equal(raw['resource_measurements'], summary, 'resource_measurements')
    equal(raw['peak_tree_rss_kib'], max(s['rss_kib'] for s in derived), 'peak_tree_rss_kib')
    return derived, summary


def resource_window(samples, start_ms, end_ms):
    selected = [s for s in samples if s.get('phase', 'running') == 'running'
                and start_ms <= s['elapsed_ms'] < end_ms and s['processes'] > 0]
    sums = {'cpu': 0, 'wall': 0, 'complete_cpu': 0, 'complete_wall': 0, 'intervals': 0, 'complete_intervals': 0}
    roles = {}
    for sample in selected:
        usage = sample['resource_usage']
        wall, delta = usage['wall_delta_ns'], usage['cpu_delta_ns']
        inside = bool(wall and sample['elapsed_ms'] - wall / 1e6 >= start_ms)
        if inside and delta is not None:
            sums['cpu'] += delta
            sums['wall'] += wall
            sums['intervals'] += 1
            if usage['cpu_observed_identity_coverage_complete']:
                sums['complete_cpu'] += delta
                sums['complete_wall'] += wall
                sums['complete_intervals'] += 1
        grouped = {}
        for process in usage['processes']:
            role = process['role']
            state = roles.setdefault(role, {'rss': [], 'footprint': [], 'count': [], 'identities': set(), 'cpu': 0})
            state['identities'].add((process['pid'], tuple(process['birth'])))
            if inside and process['cpu_delta_ns'] is not None:
                state['cpu'] += process['cpu_delta_ns']
            group = grouped.setdefault(role, [0, 0, 0])
            group[0] += process['resident_bytes']
            group[1] += process['phys_footprint_bytes']
            group[2] += 1
        for role, values in grouped.items():
            for field, value in zip(('rss', 'footprint', 'count'), (values[0] / MIB, values[1] / MIB, values[2])):
                roles[role][field].append(value)
    role_results = {}
    for role, state in roles.items():
        role_results[role] = {'rss_mib': distribution(state['rss']), 'footprint_mib': distribution(state['footprint']),
                              'process_count': distribution(state['count']), 'observed_identities': len(state['identities']),
                              'cpu_delta_ns': state['cpu'],
                              'cpu_percent_one_core': 100 * state['cpu'] / sums['wall'] if sums['wall'] else None}
    return {'clock': 'python_monotonic', 'requested_start_ms': start_ms, 'requested_end_ms': end_ms,
            'sample_count': len(selected),
            'observed_sample_span_ms': selected[-1]['elapsed_ms'] - selected[0]['elapsed_ms'] if len(selected) > 1 else None,
            'rss_mib': distribution([s['rss_kib'] / 1024 for s in selected]),
            'physical_footprint_mib': distribution([s['resource_usage']['phys_footprint_bytes'] / MIB for s in selected
                                                   if s['resource_usage']['phys_footprint_bytes'] is not None]),
            'process_count': distribution([s['processes'] for s in selected]),
            'observed_cpu_percent_one_core': 100 * sums['cpu'] / sums['wall'] if sums['wall'] else None,
            'complete_identity_cpu_percent_one_core': 100 * sums['complete_cpu'] / sums['complete_wall'] if sums['complete_wall'] else None,
            'cpu_intervals': sums['intervals'], 'complete_identity_cpu_intervals': sums['complete_intervals'],
            'measured_cpu_wall_seconds': sums['wall'] / 1e9,
            'roles': role_results, 'gpu_percent': None, 'unique_physical_mib': None}


def audit_frames(telemetry, manifest, fps, animated):
    accounting = telemetry['accounting_v2']
    require(all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in accounting.values()), 'ACCOUNTING_TYPE')
    require(accounting['paints'] == sum(accounting[k] for k in CLASSIFICATIONS), 'PAINT_CONSERVATION')
    require(accounting['pending'] == accounting['leased'] == accounting['retained_leases'] == accounting['retained_bytes'] == 0,
            'RETAINED_AFTER_CLOSE')
    require(telemetry['native_executed'] is True and telemetry['samples_truncated'] is False, 'FRAME_PROVENANCE_OR_TRUNCATION')
    require(telemetry['sample_capacity_drops'] == 0, 'FRAME_SAMPLE_DROPS')
    rows = telemetry['samples']
    require(len(rows) == accounting['consumed'], 'CONSUMED_SAMPLE_COUNT')
    require(telemetry['successful_disk_writes'] - telemetry['completion_rejected'] == accounting['consumed'], 'COMPLETION_ACCOUNTING')
    for row in rows:
        require(len(row) == 4 and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in row), 'FRAME_ROW')
        require(row[2] >= row[1], 'NATIVE_CLOCK_ORDER')
    for a, b in zip(rows, rows[1:]):
        require(b[0] > a[0] and b[1] >= a[1] and b[2] > a[2], 'FRAME_SEQUENCE')
    start = manifest['created_ns'] + 10_000_000_000
    end = start + 60_000_000_000
    selected = [row for row in rows if start <= row[2] < end]
    require(manifest['closed_ns'] >= end, 'INCOMPLETE_NATIVE_WINDOW')
    ages = distribution([(row[2] - row[1]) / 1e6 for row in selected])
    rate = len(selected) / 60
    actual_paint_ns = manifest['first_nontransparent_paint_ns']
    require(actual_paint_ns >= manifest['created_ns'] > 0, 'FIRST_ACTUAL_PAINT_CLOCK')
    ttff = (actual_paint_ns - manifest['created_ns']) / 1e6
    gates = {'first_actual_paint_within_3000_ms': ttff <= 3000,
             'frame_age_p95_within_100_ms': ages['p95'] is not None and ages['p95'] <= 100 if animated else None,
             'animated_acquisition_fps_at_least_95_percent': rate >= .95 * fps if animated else None}
    return {'identity': [manifest['instance'], manifest['generation'], manifest['epoch']],
            'animated': animated, 'clock': 'native_steady_clock', 'window_seconds': 60,
            'start_ns': start, 'end_ns': end, 'retained_acquisitions': len(selected),
            'acquisition_fps_in_window': rate, 'frame_age_ms': ages, 'first_actual_paint_ms': ttff,
            'consumer_work_ms': distribution([row[3] / 1e6 for row in selected]),
            'consumer_work_total_ms': sum(row[3] for row in selected) / 1e6,
            'consumer_work_over_100_ms': sum(row[3] > 100_000_000 for row in selected),
            'consumer_completion_age_ms': distribution([(row[2] + row[3] - row[1]) / 1e6 for row in selected]),
            'acquisition_gap_ms': distribution([(b[2] - a[2]) / 1e6 for a, b in zip(selected, selected[1:])]),
            'largest_consumer_work': [
                {'acquired_native_ns': row[2], 'epoch_relative_seconds': (row[2] - manifest['created_ns']) / 1e9,
                 'work_ms': row[3] / 1e6}
                for row in sorted(selected, key=lambda row: row[3], reverse=True)[:8]],
            'copy_total_ms': accounting['copy_ns'] / 1e6,
            'copy_mean_us_per_accepted_paint': accounting['copy_ns'] / accounting['paints'] / 1000 if accounting['paints'] else None,
            'copied_bytes': accounting['copied_bytes'], 'paint_conservation': True,
            'retained_bytes_after_close': accounting['retained_bytes'], 'gates': gates,
            'status': 'PASS' if all(value is not False for value in gates.values()) else 'FAIL',
            'scope': 'Owned native disk consumer; neither audiovisual output FPS nor end-to-end latency.'}


class Evidence:
    def __init__(self, root):
        self.root = root.resolve(strict=True)
        self.hashes = {}

    def read(self, path):
        path = path.absolute()
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(LAB.resolve()), 'EVIDENCE_ESCAPES_LAB')
        require(path == resolved and resolved.is_file(), 'EVIDENCE_SYMLINK_OR_NOT_FILE')
        data = resolved.read_bytes()
        self.hashes[str(resolved.relative_to(LAB))] = digest(data)
        return data

    def json(self, path):
        return json.loads(self.read(path))


def audit_run(root):
    evidence = Evidence(root)
    report = evidence.json(root / 'report.json')
    require(report['native_host_executed'] is True and report['requested']['rss_limit_mib'] == 2048, 'RUN_PROVENANCE')
    require([report['requested'][key] for key in ('width', 'height', 'fps')] == [640, 360, 30], 'SELECTED_MATRIX_CELL')
    require(report['requested']['scenario'] in ('steady', 'static', 'mixed'), 'SUSTAINED_SCENARIO_REQUIRED')
    compressed = evidence.read(root / 'supervision.json.gz')
    require(digest(compressed) == report['supervision_gzip_sha256'], 'SUPERVISION_GZIP_HASH')
    raw_bytes = gzip.decompress(compressed)
    require(digest(raw_bytes) == report['supervision_sha256'], 'SUPERVISION_RAW_HASH')
    raw = json.loads(raw_bytes)
    equal(report['supervision'], {k: v for k, v in raw.items() if k != 'samples'}, 'SUPERVISION_SUMMARY')
    require(raw['sample_retention']['dropped_oldest'] == 0, 'RESOURCE_SAMPLE_TRUNCATION')
    require(raw['sample_retention']['retained'] == len(raw['samples']), 'RESOURCE_RETAINED_COUNT')
    build_data = evidence.read(LAB / report['build_report'])
    require(digest(build_data) == report['build_report_sha256'], 'BUILD_REPORT_HASH')
    build = json.loads(build_data)
    main_hashes = [b.get('sha256') for b in build['binaries'] if b.get('role') == 'main']
    # Build schemas identify the main executable by its bundle-relative path.
    if not main_hashes:
        main_hashes = [b.get('sha256') for b in build['binaries'] if b.get('path', '').endswith('/MacOS/MotiveBrowserFixture')]
    require(report['expected_executable_sha256'] in main_hashes, 'EXECUTABLE_PIN')
    main_binary = next(b for b in build['binaries'] if b.get('path', '').endswith('/MacOS/MotiveBrowserFixture'))
    require(digest(evidence.read(LAB / main_binary['path'])) == report['expected_executable_sha256'], 'RETAINED_BINARY_HASH')
    for path, expected in report['collector_sha256'].items():
        require(digest(evidence.read(LAB / path)) == expected, 'COLLECTOR_SOURCE_HASH:' + path)
    rows, resource_summary = reconstruct_resources(raw)
    duration = report['requested']['duration_ms']
    ranges = {'startup_warmup': (0, 10000), 'steady': (10000, min(70000, duration)),
              'last_10_seconds': (max(0, duration - 10000), duration)}
    windows = {key: resource_window(rows, *bounds) for key, bounds in ranges.items()}
    for key, window in windows.items():
        equal(report['resources'][key], window, 'resources.' + key)
    native = evidence.json(root / 'instances.json')
    require(native['native_executed'] is True and len(native['instances']) == report['requested']['instances'], 'NATIVE_INSTANCE_COUNT')
    require(len(report['instances']) == report['requested']['instances'], 'EPOCH_COUNT')
    native_identities = {(i['instance'], i['generation'], i['epoch']) for i in native['instances']}
    require(len(native_identities) == len(native['instances']), 'DUPLICATE_NATIVE_IDENTITY')
    frames = []
    for item in report['instances']:
        identity = tuple(item['identity'])
        require(identity in native_identities and identity[1] == report['native_generation'], 'INSTANCE_IDENTITY')
        manifest = item['manifest']
        require(tuple(manifest[k] for k in ('instance', 'generation', 'epoch')) == identity, 'MANIFEST_IDENTITY')
        original = next(i for i in native['instances'] if i['instance'] == identity[0])
        epoch = next(e for e in original['epochs'] if e['epoch'] == identity[2])
        equal(manifest, {'created_ns': epoch['started_ns'], 'closed_ns': epoch['ended_ns'],
                         'first_nontransparent_paint_ns': epoch['first_nontransparent_paint_ns']}, 'EPOCH_TIMESTAMPS')
        folder = root / ('instance-%d-g%d-e%d' % identity)
        telemetry = evidence.json(folder / 'frames.json')
        equal(item['telemetry'], {k: v for k, v in telemetry.items() if k != 'samples'}, 'TELEMETRY')
        require(telemetry['accounting_v2']['copied_bytes'] == telemetry['accounting_v2']['paints']
                * manifest['width'] * manifest['height'] * 4, 'COPY_TRAFFIC_ACCOUNTING')
        require(telemetry['onpaint_callbacks'] == telemetry['accounting_v2']['paints']
                + telemetry['onpaint_busy'] + telemetry['onpaint_invalid'], 'CALLBACK_ACCOUNTING')
        for name, sample in item['samples'].items():
            meta = evidence.json(folder / (name + '.json'))
            equal(sample['metadata'], meta, 'FRAME_METADATA')
            require(tuple(meta[k] for k in ('instance', 'generation', 'epoch')) == identity, 'FRAME_IDENTITY')
            pixels_gz = evidence.read(folder / (name + '.bgra.gz'))
            pixels = gzip.decompress(pixels_gz)
            require(digest(pixels_gz) == sample['gzip_sha256'] and digest(pixels) == sample['raw_sha256'], 'PIXEL_HASH')
            require(len(pixels) == sample['raw_bytes'] == meta['stride'] * meta['height'], 'PIXEL_SIZE')
        scenario = report['requested']['scenario']
        animated = scenario == 'steady' or (scenario == 'mixed' and identity[0] == 1)
        require(original['closed'] is True and original['failed'] is False, 'NATIVE_INSTANCE_NOT_HEALTHY_CLOSED')
        audited = audit_frames(telemetry, manifest, report['requested']['fps'], animated)
        equal(item['native_steady_frames'], {key: audited[key] for key in
              ('start_ns', 'end_ns', 'window_seconds', 'retained_acquisitions', 'acquisition_fps_in_window',
               'frame_age_ms', 'consumer_work_ms')}, 'NATIVE_STEADY_FRAMES')
        frames.append(audited)
    phases = [json.loads(line) for line in evidence.read(root / 'lifecycle.jsonl').splitlines() if line]
    phase_times = {}
    for item in phases:
        require(item['phase'] not in phase_times, 'DUPLICATE_NATIVE_PHASE')
        phase_times[item['phase']] = item['observed_ns']
    close_ms = (phase_times['shutdown_return'] - phase_times['close_requested']) / 1e6
    shutdown_ms = (phase_times['shutdown_return'] - phase_times['shutdown_enter']) / 1e6
    require(close_ms >= shutdown_ms >= 0, 'NATIVE_SHUTDOWN_CLOCK')
    for frame, item in zip(frames, report['instances']):
        frame['first_actual_paint_since_host_initialize_ms'] = (
            item['manifest']['first_nontransparent_paint_ns'] - phase_times['initialize_enter']) / 1e6
        for stall in frame['largest_consumer_work']:
            stall['host_initialize_relative_seconds'] = (stall['acquired_native_ns'] - phase_times['initialize_enter']) / 1e9
    gates = {'retained_report_pass': report['status'] == 'PASS',
             'full_python_steady_window': duration >= 70000 and windows['steady']['observed_sample_span_ms'] is not None
                                          and windows['steady']['observed_sample_span_ms'] >= 58000,
             'rss_peak_within_2048_mib': raw['peak_tree_rss_kib'] <= 2048 * 1024,
             'native_close_to_shutdown_within_5000_ms': close_ms <= 5000,
             'first_actual_paint_since_host_initialize_within_3000_ms': all(
                 0 <= frame['first_actual_paint_since_host_initialize_ms'] <= 3000 for frame in frames),
             'supervisor_shutdown_within_5000_ms': raw['shutdown_ms'] <= 5000,
             'normal_exit': raw['reason'] == 'exit' and raw['returncode'] == 0,
             'observed_tree_cleanup': raw['final_cleanup_observed_tree'] is True
                                      and raw['final_remaining_observed_live_pids'] == []
                                      and raw['final_remaining_observed_pids'] == [],
             'all_instances': all(frame['status'] == 'PASS' for frame in frames)}
    return {'run': root.name, 'status': 'PASS' if all(gates.values()) else 'FAIL', 'gates': gates,
            'requested': report['requested'], 'main_executable_sha256': report['expected_executable_sha256'],
            'credential_backend': report['credential_backend'], 'resources': windows,
            'resource_totals': resource_summary, 'peak_tree_rss_mib': raw['peak_tree_rss_kib'] / 1024,
            'native_close_to_shutdown_ms': close_ms, 'native_cef_shutdown_ms': shutdown_ms,
            'supervisor_shutdown_ms': raw['shutdown_ms'], 'instances': frames,
            'input_sha256': evidence.hashes}


def audit_suite(root):
    paths = sorted(root.glob('*/report.json'))
    results = []
    for path in paths:
        try:
            results.append(audit_run(path.parent))
        except (ValueError, KeyError, OSError, TypeError, IndexError) as error:
            results.append({'run': path.parent.name, 'status': 'FAIL', 'audit_error': str(error)})
    plan_path = root / 'plan.json'
    suite = json.loads(plan_path.read_bytes())['source']['suite'] if plan_path.is_file() else 'capacity'
    require(suite in ('capacity', 'static-mixed'), 'SUSTAINED_SUITE_REQUIRED')
    expected = ({f'animated-{n}-r{rep}' for n in (1, 3, 5) for rep in (1, 2, 3)} if suite == 'capacity'
                else {f'{mode}-{n}-r{rep}' for mode, n in (('static', 1), ('mixed', 5)) for rep in (1, 2, 3)})
    names = {item['run'] for item in results}
    for item in results:
        if 'requested' in item:
            parts = item['run'].split('-')
            expected_scenario = 'steady' if parts[0] == 'animated' else parts[0]
            if item['requested']['instances'] != int(parts[1]) or item['requested']['scenario'] != expected_scenario:
                item['status'], item['audit_error'] = 'FAIL', 'SUITE_CASE_IDENTITY'
    summary = root / 'summary.json'
    summary_hash = None
    if summary.is_file():
        summary_bytes = summary.read_bytes()
        summary_hash = digest(summary_bytes)
        for case in json.loads(summary_bytes)['cases']:
            path = LAB / case['report']
            require(digest(path.read_bytes()) == case['report_sha256'], 'MATRIX_REPORT_HASH:' + case['name'])
    accepted = []
    comparisons = {}
    for count in (1, 3, 5):
        group = [r for r in results if r['run'] in {f'animated-{count}-r{i}' for i in (1, 2, 3)}]
        if len(group) == 3 and all(r['status'] == 'PASS' for r in group):
            accepted.append(count)
        valid = [r for r in group if 'resources' in r]
        comparisons[str(count)] = {'repetitions': len(valid)}
        if valid:
            comparisons[str(count)].update({
                'steady_rss_mib_median_of_run_medians': statistics.median(r['resources']['steady']['rss_mib']['median'] for r in valid),
                'peak_tree_rss_mib_max': max(r['peak_tree_rss_mib'] for r in valid),
                'steady_footprint_mib_median_of_run_medians': statistics.median(r['resources']['steady']['physical_footprint_mib']['median'] for r in valid),
                'steady_cpu_percent_median': statistics.median(r['resources']['steady']['observed_cpu_percent_one_core'] for r in valid),
                'startup_cpu_percent_median': statistics.median(r['resources']['startup_warmup']['observed_cpu_percent_one_core'] for r in valid)})
    conservative_capacity = None
    for count in (1, 3, 5):
        if count not in accepted:
            break
        conservative_capacity = count
    status = 'FAIL' if any(r['status'] == 'FAIL' for r in results) else ('PASS' if expected <= names else 'PARTIAL')
    return {'status': status, 'suite': suite,
            'scope': 'Independent audit of retained owned native 640x360@30 selected-pin runs; full H19 matrix remains PARTIAL.',
            'missing_suite_cases': sorted(expected - names), 'accepted_animated_capacity': conservative_capacity,
            'counts_passing_all_repetitions': accepted,
            'highest_count_passing_all_repetitions': max(accepted, default=None),
            'capacity_rule': 'Conservative tested tier stops at first failing or incomplete smaller tested tier; never skip a failed tier.',
            'comparisons': comparisons, 'runs': results, 'matrix_summary_sha256': summary_hash,
            'auditor_sha256': digest(Path(__file__).read_bytes()), 'gpu_percent': None, 'unique_physical_mib': None,
            'limits': ['CPU excludes unobserved process lifetimes and supervisor overhead; 100% is one core.',
                       'RSS may double-count shared pages; summed process footprints are not unique RAM.',
                       'Python and native monotonic clocks are never subtracted from each other.',
                       'Static instances have no target sustained animation FPS; their empty frame-age samples remain null.',
                       'No AV compositor, third-party content, default Keychain backend, release sandbox, or leak-freedom claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    result = audit_run(root) if (root / 'report.json').is_file() else audit_suite(root)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'accepted_animated_capacity': result.get('accepted_animated_capacity')}))
    return 1 if result['status'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
