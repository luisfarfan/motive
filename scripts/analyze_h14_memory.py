#!/usr/bin/env python3
"""Derive memory metrics from existing H14 evidence; no app, IPC or media access."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


MEMORY_FIELDS = {
    'rss_bytes': ('vm', 'resident_bytes'),
    'footprint_bytes': ('vm', 'physical_footprint_bytes'),
    'compressed_bytes': ('vm', 'compressed_bytes'),
    'malloc_in_use_bytes': ('malloc', 'in_use_bytes'),
    'malloc_allocated_bytes': ('malloc', 'allocated_bytes'),
}
COUNTERS = ('rendered_frames', 'preview_copies', 'preview_busy_drops',
            'lagged_frames', 'video_skipped_frames')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {'count': 0, 'min': None, 'median': None, 'p95': None, 'max': None}
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Non-finite measurement')
    return {'count': len(values), 'min': values[0], 'median': statistics.median(values),
            'p95': values[math.ceil(.95 * len(values)) - 1], 'max': values[-1]}


def memory_values(row):
    return {name: row['memory'][group][field]
            for name, (group, field) in MEMORY_FIELDS.items()}


def difference(current, previous):
    return {name: current[name] - previous[name] for name in current}


def counter_deltas(rows):
    result = {}
    for key in COUNTERS:
        values = [row['stats'][key] for row in rows]
        reset = any(new < old for old, new in zip(values, values[1:]))
        result[key] = {'reset_observed': reset,
                       'delta': None if reset else values[-1] - values[0]}
    return result


def summarize_phase(name, seconds, rows):
    sources = [source for row in rows for source in row['overlays_runtime']['sources']]
    clocks = {}
    for row in rows:
        for source in row['overlays_runtime']['sources']:
            clocks.setdefault(source['id'], []).append(source['media_time_ms'])
    return {
        'name': name, 'seconds': seconds, 'samples': len(rows),
        'cpu_percent_one_core': distribution(row['cpu_percent'] for row in rows),
        'memory': {name: distribution(memory_values(row)[name] for row in rows)
                   for name in MEMORY_FIELDS},
        'first_memory': memory_values(rows[0]), 'last_memory': memory_values(rows[-1]),
        'native_collection_us': distribution(row['memory']['collection_us'] for row in rows),
        'memory_rpc_ms': distribution(row['memory_rpc_ms'] for row in rows),
        'status_rpc_ms': distribution(row['status_rpc_ms'] for row in rows),
        'source_observations': len(sources),
        'source_counts_per_sample': [len(row['overlays_runtime']['sources']) for row in rows],
        'source_states': dict(Counter(source['media_state'] for source in sources)),
        'all_children_single_and_silent': all(
            source['child_instances_created'] == 1 and source['audio_mixers'] == 0
            for source in sources) if sources else None,
        'source_media_clocks_ms': clocks,
        'source_clocks_constant': {key: len(set(values)) == 1 for key, values in clocks.items()},
        'counters': counter_deltas(rows),
    }


def analyze(directory):
    report = json.loads((directory / 'report.json').read_text())
    rows = [json.loads(line) for line in (directory / 'samples.jsonl').read_text().splitlines()]
    if not rows:
        raise ValueError('No samples')
    if report['samples_sha256'] != sha256(directory / 'samples.jsonl'):
        raise ValueError('Sample hash does not match report')
    phases = []
    for phase in report['phases']:
        selected = [row for row in rows if row['phase'] == phase['name']]
        if len(selected) != phase['summary']['samples']:
            raise ValueError('Phase sample count does not match report')
        phases.append(summarize_phase(phase['name'], phase['seconds'], selected))
    if sum(phase['samples'] for phase in phases) != len(rows):
        raise ValueError('Unknown or duplicate phases')

    discrepancies = []
    for previous, current in zip(rows, rows[1:]):
        if previous['phase'] != current['phase']:
            continue
        old, new = previous['memory'], current['memory']
        elapsed = (new['monotonic_ns'] - old['monotonic_ns']) / 1e9
        if elapsed <= 0:
            raise ValueError('Non-increasing native clock')
        seconds = sum(new['cpu'][key] - old['cpu'][key]
                      for key in ('user_seconds', 'system_seconds'))
        discrepancies.append(abs(seconds * 100 / elapsed - current['cpu_percent']))

    baseline = phases[0]['last_memory']
    by_name = {phase['name']: phase for phase in phases}
    comparisons = []
    for phase in phases:
        if not phase['name'].endswith('_hidden_paused'):
            continue
        prefix = phase['name'].removesuffix('_hidden_paused')
        hidden = by_name[prefix + '_hidden']
        released = by_name[prefix + '_released']
        before = hidden['cpu_percent_one_core']['median']
        after = phase['cpu_percent_one_core']['median']
        comparisons.append({
            'cycle': prefix, 'hidden_cpu_median': before, 'paused_cpu_median': after,
            'cpu_difference_percentage_points': after - before,
            'cpu_reduction_percent_of_hidden': (1 - after / before) * 100 if before else None,
            'pause_last_memory_delta_from_hidden': difference(phase['last_memory'], hidden['last_memory']),
            'released_last_memory_delta_from_paused': difference(released['last_memory'], phase['last_memory']),
        })

    initial, final = report['initial'], report['final']
    initial_graph, final_graph = initial['project']['graph'], final['project']['graph']
    native = distribution(row['memory']['collection_us'] for row in rows)
    rpc = distribution(row['memory_rpc_ms'] for row in rows)
    return {
        'version': 1, 'scope': 'offline derivation, not leak or causal attribution',
        'analyzer_sha256': sha256(Path(__file__)),
        'inputs': {name: sha256(directory / name)
                   for name in ('report.json', 'samples.jsonl', 'operations.jsonl')},
        'app_sha256': report['app_sha256'], 'instrument_sha256': report['instrument_sha256'],
        'pid': initial['pid'], 'plan': report['plan'], 'fixture': report['fixture'],
        'status': report['status'], 'measurement_completed': report['measurement_completed'],
        'cleanup_errors': report['cleanup_errors'], 'sample_count': len(rows),
        'phase_duration_sum_seconds': sum(phase['seconds'] for phase in phases),
        'sample_span_seconds': rows[-1]['monotonic'] - rows[0]['monotonic'],
        'native_collection_us': native, 'memory_rpc_ms': rpc,
        'status_rpc_ms': distribution(row['status_rpc_ms'] for row in rows),
        'budgets': report['budgets'], 'budget_observations': report['budget_observations'],
        'memory_rpc_over_budget_count': sum(row['memory_rpc_ms'] > report['budgets']['rpc_p95_ms']
                                            for row in rows),
        'maximum_sampled_footprint_bytes': max(memory_values(row)['footprint_bytes'] for row in rows),
        'native_statuses': dict(Counter(row['memory']['status'] for row in rows)),
        'cpu_available_json_types': dict(Counter(type(row['memory']['cpu']['available']).__name__
                                                for row in rows)),
        'cpu_available_boolean_true_count': sum(row['memory']['cpu']['available'] is True for row in rows),
        'cpu_recalculation': {'intervals': len(discrepancies),
                              'maximum_absolute_difference': max(discrepancies, default=None)},
        'phases': phases, 'within_cycle_hidden_pause_comparisons': comparisons,
        'released_last_deltas_from_baseline': {
            phase['name']: difference(phase['last_memory'], baseline)
            for phase in phases if phase['name'].endswith('_released')},
        'sample_span_counters': counter_deltas(rows),
        'issue_samples': sum(bool(row['issues']) for row in rows),
        'output_attempt_observed': any(output['attempt_id'] is not None
                                      for row in rows for output in row['outputs'].values()),
        'cleanup_state': {
            'sources_equal': initial_graph['sources'] == final_graph['sources'],
            'scenes_equal': initial_graph['scenes'] == final_graph['scenes'],
            'active_scene_equal': initial_graph['active_scene'] == final_graph['active_scene'],
            'variant_equal': initial['project']['variant'] == final['project']['variant'],
            'video_equal': initial['video'] == final['video'],
            'output_configuration_equal': initial['output_configuration'] == final['output_configuration'],
            'mixer_store_equal': initial['audio_mixer']['store'] == final['audio_mixer']['store'],
            'overlay_sources_remaining': len(final['overlays']['runtime']['sources']),
            'overlay_animations_busy': final['overlays']['runtime']['animations']['busy'],
            'initial_revision': initial['revision'], 'final_revision': final['revision'],
            'initial_graph_next_id': initial_graph['next_id'], 'final_graph_next_id': final_graph['next_id'],
            'initial_project_version': initial['project']['version'],
            'final_project_version': final['project']['version'],
        },
        'decoded_freshness': report['decoded_freshness'],
        'audio_video_sync': report['audio_video_sync'], 'gpu_utilization': report['gpu_utilization'],
        'leak_classification': 'INCONCLUSIVE_NO_OWNERSHIP_OR_ALLOCATION_STACK_EVIDENCE',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--output', type=Path, help='New output file; existing paths are never overwritten')
    args = parser.parse_args()
    encoded = json.dumps(analyze(args.evidence), indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x') as handle:
            handle.write(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
