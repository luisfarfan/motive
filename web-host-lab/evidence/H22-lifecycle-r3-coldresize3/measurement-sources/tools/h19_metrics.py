"""H19 retained-sample analysis. No launch, invented GPU values, or clock mixing."""
import math
import statistics


def distribution(values):
    values = sorted(values)
    if not values:
        return {'n': 0, 'median': None, 'p95': None, 'max': None}
    return {'n': len(values), 'median': statistics.median(values),
            'p95': values[max(0, math.ceil(.95 * len(values)) - 1)], 'max': values[-1]}


def resource_window(samples, start_ms, end_ms):
    # Python monotonic only. Include CPU only when BOTH ends of the consecutive
    # interval belong to this phase; never scale a partial interval into a phase.
    rows = [s for s in samples if s.get('phase', 'running') == 'running'
            and start_ms <= s['elapsed_ms'] < end_ms and s['processes'] > 0]
    cpu, complete_cpu, intervals, complete_intervals = 0, 0, [], []
    by_role = {}
    for sample in rows:
        usage = sample['resource_usage']
        wall = usage.get('wall_delta_ns')
        interval_inside = wall and sample['elapsed_ms'] - wall / 1e6 >= start_ms
        if interval_inside and usage.get('cpu_delta_ns') is not None:
            cpu += usage['cpu_delta_ns']
            intervals.append(wall)
            if usage.get('cpu_observed_identity_coverage_complete'):
                complete_cpu += usage['cpu_delta_ns']
                complete_intervals.append(wall)
        grouped = {}
        for process in usage.get('processes', []):
            role = process['role']
            group = grouped.setdefault(role, {'resident_bytes': 0, 'footprint_bytes': 0, 'processes': 0})
            group['resident_bytes'] += process['resident_bytes']
            group['footprint_bytes'] += process['phys_footprint_bytes']
            group['processes'] += 1
            metrics = by_role.setdefault(role, {'rss_mib': [], 'footprint_mib': [], 'process_count': [],
                                              'cpu_delta_ns': 0, 'identities': set()})
            metrics['identities'].add((process['pid'], tuple(process['birth'])))
            if interval_inside and process.get('cpu_delta_ns') is not None:
                metrics['cpu_delta_ns'] += process['cpu_delta_ns']
        for role, group in grouped.items():
            by_role[role]['rss_mib'].append(group['resident_bytes'] / 1024**2)
            by_role[role]['footprint_mib'].append(group['footprint_bytes'] / 1024**2)
            by_role[role]['process_count'].append(group['processes'])
    roles = {}
    for role, values in by_role.items():
        roles[role] = {k: distribution(values[k]) for k in ('rss_mib', 'footprint_mib', 'process_count')}
        roles[role].update(observed_identities=len(values['identities']),
                           cpu_delta_ns=values['cpu_delta_ns'],
                           cpu_percent_one_core=100 * values['cpu_delta_ns'] / sum(intervals) if intervals else None)
    return {'clock': 'python_monotonic', 'requested_start_ms': start_ms, 'requested_end_ms': end_ms,
            'sample_count': len(rows), 'observed_sample_span_ms': rows[-1]['elapsed_ms'] - rows[0]['elapsed_ms'] if len(rows) > 1 else None,
            'rss_mib': distribution([s['rss_kib'] / 1024 for s in rows]),
            'physical_footprint_mib': distribution([s['resource_usage']['phys_footprint_bytes'] / 1024**2 for s in rows if s['resource_usage'].get('phys_footprint_bytes') is not None]),
            'process_count': distribution([s['processes'] for s in rows]),
            'observed_cpu_percent_one_core': 100 * cpu / sum(intervals) if intervals else None,
            'complete_identity_cpu_percent_one_core': 100 * complete_cpu / sum(complete_intervals) if complete_intervals else None,
            'cpu_intervals': len(intervals), 'complete_identity_cpu_intervals': len(complete_intervals),
            'measured_cpu_wall_seconds': sum(intervals) / 1e9,
            'roles': roles, 'gpu_percent': None, 'unique_physical_mib': None,
            'memory_note': 'Sequential sums; RSS can double-count shared pages. Footprint is not unique physical RAM.'}


def frame_window(telemetry, start_ns, end_ns):
    # Native MonotonicNs only. start/end must come from native lifecycle records.
    rows = [s for s in telemetry.get('samples', []) if start_ns <= s[2] < end_ns]
    ages = [(s[2] - s[1]) / 1e6 for s in rows]
    if any(age < 0 for age in ages):
        raise ValueError('NATIVE_CLOCK_ORDER')
    duration = (end_ns - start_ns) / 1e9
    return {'clock': 'native_steady_clock', 'start_ns': start_ns, 'end_ns': end_ns,
            'window_seconds': duration, 'retained_acquisitions': len(rows),
            'acquisition_fps_in_window': len(rows) / duration if duration > 0 else None,
            'active_acquisition_fps': (len(rows) - 1) * 1e9 / (rows[-1][2] - rows[0][2]) if len(rows) > 1 and rows[-1][2] > rows[0][2] else None,
            'frame_age_ms': distribution(ages),
            'consumer_work_ms': distribution([s[3] / 1e6 for s in rows]),
            'paint_gap_ms': distribution([(b[1] - a[1]) / 1e6 for a, b in zip(rows, rows[1:])]),
            'telemetry_truncated': telemetry.get('samples_truncated'),
            'scope': 'native lab consumer acquisitions, not audiovisual output FPS or memcpy-only time'}
