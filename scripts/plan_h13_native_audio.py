#!/usr/bin/env python3
"""Plan bounded offline H13 native audio measurements from observed states.

This script only reads JSONL. It never runs ffmpeg, controls Motive, listens to
audio or accesses a device. A live observer may be read as a fixed byte prefix;
its hash and incomplete final line remain explicit. This is measurement
preparation, NOT media or native acceptance.

Example:
  python3 scripts/plan_h13_native_audio.py --observations observations.jsonl \
      --pid 92305 --microphone-id audio-1 --application-id audio-2

The 440/997 Hz stimuli are caller declarations, not identified by this plan.
Native duration hints are NOT file PTS. Before PCM measurement, establish each
file's own alignment from the isolated app gain edge and retain its polling
bracket/uncertainty. Never shift RTMP by the recording's zero point. Verify a
later independent landmark before measuring the late disconnect/recovery.
"""

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def summary(values):
    clean = [v for v in values if numeric(v)]
    return {'samples': len(values), 'finite_samples': len(clean),
            'min': min(clean) if clean else None, 'max': max(clean) if clean else None,
            'median': statistics.median(clean) if clean else None}


def read_prefix(path, pid, microphone, application):
    before = path.stat(); remaining = before.st_size; consumed = 0
    digest = hashlib.sha256(); rows = []; errors = []
    with path.open('rb') as source:
        for number in range(1, 1000000):
            if remaining <= 0:
                break
            raw = source.readline(remaining)
            if not raw:
                break
            consumed += len(raw); remaining -= len(raw); digest.update(raw)
            if not raw.endswith(b'\n'):
                errors.append({'line': number, 'reason': 'partial final line', 'bytes': len(raw)})
                break
            try:
                entry = json.loads(raw); state = entry['state']
                if state['pid'] != pid:
                    continue
                require(numeric(entry['monotonic']), 'finite observer time required')
                mixer = state['audio_mixer']
                require(mixer['meter_point'] == 'post_fader_pre_mute', 'unexpected per-input meter point')
                require(mixer['mix_meter_point'] == 'post_fader_post_mute_pre_clamp', 'unexpected mix meter point')
                require(mixer['monitoring'] == 'off', 'monitoring must remain off')
                controls = {i['id']: i for i in mixer['store']['inputs']}
                runtime = {i['id']: i for i in mixer['runtime']['inputs']}
                inputs = {}
                for role, identifier in (('microphone', microphone), ('application', application)):
                    if identifier not in controls or identifier not in runtime:
                        inputs[role] = None
                        continue
                    control, live = controls[identifier], runtime[identifier]
                    require(control['source']['kind'] == ('microphone' if role == 'microphone' else 'system_application'),
                            role+' ID has unexpected source kind')
                    inputs[role] = {'id': identifier, 'gain_db': control['gain_db'], 'muted': control['muted'],
                        'source': control['source'], 'phase': live['phase'], 'issue': live['issue'],
                        'instance_id': live['instance_id'], 'levels': live['levels']}
                rows.append({'monotonic': entry['monotonic'], 'revision': state['revision'],
                    'last_action': state.get('last_action'), 'inputs': inputs,
                    'other_input_ids': sorted(set(controls)-{microphone, application}),
                    'outputs': {target: {key: slot.get(key) for key in ('attempt_id', 'phase', 'native_busy',
                        'active_duration_ms', 'failure', 'path')} for target, slot in state['outputs'].items()},
                    'transition': state.get('transition'), 'mix': mixer['runtime']['mix']})
            except (ValueError, KeyError, TypeError) as error:
                errors.append({'line': number, 'reason': str(error), 'bytes': len(raw)})
    after = path.stat()
    require(rows, 'no matching PID observations')
    require(all(b['monotonic'] > a['monotonic'] for a, b in zip(rows, rows[1:])), 'observer time is not increasing')
    return rows, {'source': str(path), 'initial_size': before.st_size, 'prefix_bytes_read': consumed,
        'prefix_sha256': digest.hexdigest(), 'final_size': after.st_size,
        'unchanged_during_read': (before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns),
        'parse_errors': errors, 'rows_for_pid': len(rows),
        'coverage': 'Fixed prefix only. Live growth and unobserved changes are not acceptance coverage.'}


def signature(row):
    inputs = {role: ({k: value[k] for k in ('id', 'gain_db', 'muted', 'phase', 'issue', 'instance_id')}
                    if value else None) for role, value in row['inputs'].items()}
    outputs = {target: {k: slot[k] for k in ('attempt_id', 'phase', 'native_busy', 'failure')}
               for target, slot in row['outputs'].items()}
    return json.dumps({'inputs': inputs, 'outputs': outputs, 'other_input_ids': row['other_input_ids']}, sort_keys=True)


def audible(value):
    return value and not value['muted'] and value['phase'] == 'ready' and value['issue'] is None


def silenced(value):
    return value and (value['muted'] or value['phase'] == 'disconnected')


def classify(inputs):
    mic, app = inputs['microphone'], inputs['application']
    if audible(app) and silenced(mic):
        return 'application_isolated'
    if audible(mic) and silenced(app):
        return 'microphone_isolated'
    if silenced(mic) and silenced(app):
        return 'both_silenced'
    if audible(mic) and audible(app):
        return 'mixed_unidentifiable_997'
    return 'unavailable_or_warming'


def native_meter(rows, role):
    values = [r['inputs'][role] for r in rows if r['inputs'][role]]
    if not values:
        return {'status': 'INCONCLUSIVE', 'reason': 'input missing'}
    levels = [v['levels'] for v in values]
    valid = [not level['stale'] and numeric(level['age_ms']) and level['age_ms'] <= 250
             and all(numeric(v) for v in level['rms_dbfs']) for level in levels]
    return {'status': 'PASS' if all(valid) else 'INCONCLUSIVE',
        'scope': 'Native sampled meter only, post-fader/pre-mute. Not decoded PCM agreement.',
        'samples': len(levels), 'invalid_sample_indices': [i for i, good in enumerate(valid) if not good],
        'rms_dbfs': [summary([v['rms_dbfs'][channel] for v in levels]) for channel in (0, 1)],
        'peak_dbfs': [summary([v['peak_dbfs'][channel] for v in levels]) for channel in (0, 1)],
        'frames': [levels[0]['frames'], levels[-1]['frames']],
        'timestamp_ns': [levels[0]['timestamp_ns'], levels[-1]['timestamp_ns']],
        'clipped_blocks': [levels[0]['clipped_blocks'], levels[-1]['clipped_blocks']],
        'instance_ids': sorted({v['instance_id'] for v in values})}


def make_plan(rows, guard, minimum):
    groups = []
    for row in rows:
        if not groups or signature(row) != signature(groups[-1][-1]):
            groups.append([])
        groups[-1].append(row)
    segments = []; meter_samples = []; events = []
    for index, group in enumerate(groups, 1):
        first, last = group[0], group[-1]
        lo, hi = first['monotonic']+guard, last['monotonic']-guard
        interior = [r for r in group if lo <= r['monotonic'] <= hi]
        has_output = any(s['native_busy'] and s['phase'] == 'active' for s in first['outputs'].values())
        usable = hi-lo >= minimum and len(interior) >= 4 and has_output
        segment = {'segment_id': index, 'classification': ('unmapped_additional_inputs'
                       if first['other_input_ids'] else classify(first['inputs'])),
            'other_input_ids': first['other_input_ids'],
            'observed_start': first['monotonic'], 'observed_end': last['monotonic'],
            'observed_samples': len(group), 'guard_seconds_each_edge': guard,
            'interior_monotonic': [lo, hi] if usable else None,
            'status': 'READY_FOR_ALIGNMENT' if usable else 'INSUFFICIENT_STABLE_INTERIOR',
            'controls': {role: ({k: v[k] for k in ('id', 'gain_db', 'muted', 'phase', 'issue', 'instance_id')}
                               if v else None) for role, v in first['inputs'].items()},
            'outputs': first['outputs'], 'native_duration_hints': {},
            'meter_summary': {role: native_meter(interior, role) for role in ('microphone', 'application')},
            'pcm_alignment': 'INCONCLUSIVE; native duration is not decoded PTS'}
        if usable:
            for target, slot in first['outputs'].items():
                if slot['native_busy'] and slot['phase'] == 'active':
                    segment['native_duration_hints'][target] = {
                        'attempt_id': slot['attempt_id'],
                        'first_sample_s': interior[0]['outputs'][target]['active_duration_ms']/1000,
                        'last_sample_s': interior[-1]['outputs'][target]['active_duration_ms']/1000,
                        'warning': 'Search hint only, not media PTS or cross-output alignment.'}
            for row in interior:
                meter_samples.append({'segment_id': index, **row})
        segments.append(segment)
    previous = None
    for row in rows:
        action = row['last_action']
        transition = row['transition'] or {}
        # A native output fault/cancel barrier can change without a new UI
        # command. Preserve those observations as events in their own right.
        key = (action, transition.get('operation_id'), transition.get('phase'), signature(row))
        if previous and key != previous[0]:
            before = previous[1]
            output_changes = []
            for target, slot in row['outputs'].items():
                old = {k: before['outputs'][target][k] for k in ('attempt_id','phase','native_busy','failure')}
                new = {k: slot[k] for k in ('attempt_id','phase','native_busy','failure')}
                if old != new:
                    output_changes.append({'target':target,'before':old,'after':new})
            events.append({'observed_interval_monotonic': [before['monotonic'], row['monotonic']],
                'last_action': action, 'revision': row['revision'], 'transition': transition,
                'output_changes': output_changes,
                'outputs': row['outputs'], 'inputs': {role: ({k: v[k] for k in ('id', 'gain_db', 'muted',
                    'phase', 'issue', 'instance_id')} if v else None) for role, v in row['inputs'].items()},
                'coverage': 'Observed state/action boundary; does not alone establish a GPUI gesture or media event.'})
        previous = (key, row)
    references = [s for s in segments if s['status'] == 'READY_FOR_ALIGNMENT'
                  and s['classification'] == 'application_isolated']
    gain_pairs = []
    for low in references:
        for high in references:
            lo, hi = low['controls']['application'], high['controls']['application']
            if lo['gain_db'] >= hi['gain_db'] or lo['instance_id'] != hi['instance_id']:
                continue
            common = {target: slot['attempt_id'] for target, slot in low['outputs'].items()
                      if slot['phase'] == 'active' and high['outputs'][target]['phase'] == 'active'
                      and slot['attempt_id'] == high['outputs'][target]['attempt_id']}
            if common:
                gain_pairs.append({'low_segment': low['segment_id'], 'high_segment': high['segment_id'],
                    'same_output_attempts': common, 'expected_low_minus_high_db': lo['gain_db']-hi['gain_db'],
                    'comparison': 'Same-file isolated 997 Hz Hann amplitudes; preserve historical ±1 dB tolerance.'})
    return segments, events, gain_pairs, meter_samples


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--observations', type=pathlib.Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--application-id', required=True)
    parser.add_argument('--guard-seconds', type=float, default=1)
    parser.add_argument('--minimum-seconds', type=float, default=3)
    args = parser.parse_args()
    require(args.pid > 0 and args.microphone_id != args.application_id, 'distinct explicit IDs and positive PID required')
    require(numeric(args.guard_seconds) and args.guard_seconds >= 1, 'guard must be at least one second')
    require(numeric(args.minimum_seconds) and args.minimum_seconds >= 1, 'minimum interior at least one second')
    directory = ROOT/'var/evidence'/f'h13-native-audio-plan-{time.time_ns()}'
    directory.mkdir(parents=True)
    report = {'version': 1, 'acceptance': 'NOT_EVALUATED', 'pcm_status': 'INCONCLUSIVE', 'pid': args.pid,
        'declared_stimuli_hz': {'microphone_acoustic': 440, 'system_application': 997}}
    try:
        rows, coverage = read_prefix(args.observations.resolve(strict=True), args.pid,
                                     args.microphone_id, args.application_id)
        segments, events, pairs, samples = make_plan(rows, args.guard_seconds, args.minimum_seconds)
        sample_file = directory/'meter-samples.jsonl'
        with sample_file.open('w') as stream:
            for sample in samples:
                stream.write(json.dumps(sample, separators=(',', ':'), allow_nan=False)+'\n')
        # Continuity must include every observed state, even a short failed or
        # stale phase that has no usable interior for an RMS reference.
        all_samples = directory/'observed-samples.jsonl'
        with all_samples.open('w') as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n')
        report.update(observations=coverage, segments=segments, events=events, isolated_gain_pairs=pairs,
                      observed_samples={'path':str(all_samples),'rows':len(rows),
                                        'sha256':hashlib.sha256(all_samples.read_bytes()).hexdigest()},
                      meter_samples={'path': str(sample_file), 'rows': len(samples),
                                     'sha256': hashlib.sha256(sample_file.read_bytes()).hexdigest()})
        report['planning_status'] = ('INCONCLUSIVE' if coverage['parse_errors'] else 'PLAN_WRITTEN_NOT_ACCEPTANCE')
        report['offline_followup'] = [
            'Use each output manifest entry and hash; verify completed media with analyse_h13_native.py.',
            'Find the actual isolated app -18→-6 dB edge in each file. Preserve observed event bracket and PCM transition uncertainty; do not force native duration to equal PTS.',
            'Map only stable interiors that remain inside the same state for every allowed offset; use original stereo channels and actual decoded audio timestamps.',
            'Compare isolated app997 low/high Hann 100ms amplitudes (expected -12dB, unchanged ±1dB); mixed997 is diagnostic because the microphone also captures 997Hz.',
            'Compare median native RMS with median decoded 20ms RMS in each isolated-source interval, separately by channel, with the existing 2dB tolerance. Per-input meters remain nonzero when muted.',
            'During app mute, require audible mic440 and compare microphone meter to PCM. Do not claim isolated app-mute attenuation from residual997 in the open microphone.',
            'Use mic-disconnected/app-6 as another isolated app reference. Preserve app instance/frame/timestamp continuity and establish a late media landmark before interpreting disconnect/reconnect timing.',
            'Around Cut/Fade/cancel/recovery, inspect every PCM window after alignment; lifecycle events do not grant excluded audio gaps. Mixed997 alone cannot prove app continuity without bounding acoustic contamination.',
            'Native action/transition snapshots support event coverage; visual geometry and observed GPUI gestures remain separate evidence.',
            'All PCM, gain, mute, continuity, A/V and final native acceptance remain INCONCLUSIVE until actual closed-media analysis.'
        ]
    except Exception as error:
        report['error'] = repr(error)
    output = directory/'report.json'; output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'report': str(output), 'segments': len(report.get('segments', [])),
        'isolated_gain_pairs': len(report.get('isolated_gain_pairs', [])), 'pcm_status': report['pcm_status'],
        'acceptance': report['acceptance'], 'error': report.get('error')}))
    return 1 if 'error' in report else 0


if __name__ == '__main__':
    raise SystemExit(main())
