#!/usr/bin/env python3
"""Independently analyze retained H19 native scenarios; never launch a browser.

Reads immutable raw native/consumer/supervisor evidence. Writes a NEW analysis
file exclusively; original report.json and all historical evidence stay intact.
PASS is scoped to the selected owned scenario, not H19, OS isolation or libobs.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat

NS_MS = 1_000_000
SETTLE_NS = 100 * NS_MS
CONTINUITY_NS = 250 * NS_MS
LAB_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {'lifecycle', 'resize', 'hidden', 'events', 'slow', 'slow-consumer', 'crash'}
TERMINAL = ('pending', 'leased', 'coalesced', 'stale', 'consumed',
            'released_unconsumed', 'invalidated_close', 'revoked_generation')


class EvidenceError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError('NONFINITE_JSON')))


class Inputs:
    def __init__(self, root):
        self.root = Path(root)
        self.hashes = {}

    def read(self, relative, maximum=16 * 1024**2, compressed=False):
        relative = Path(relative)
        require(not relative.is_absolute() and '..' not in relative.parts, 'INPUT_PATH')
        path = self.root / relative
        require(not any((self.root / Path(*relative.parts[:n])).is_symlink()
                        for n in range(1, len(relative.parts) + 1)), 'INPUT_SYMLINK')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, 'INPUT_SIZE_TYPE')
            raw = stream.read(maximum + 1)
        require(len(raw) <= maximum, 'INPUT_SIZE')
        self.hashes[str(relative)] = hashlib.sha256(raw).hexdigest()
        if compressed:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                data = stream.read(maximum + 1)
            require(len(data) <= maximum, 'DECOMPRESSED_SIZE')
            return data
        return raw

    def json(self, relative, **kwargs):
        return strict_json(self.read(relative, **kwargs))

    def trace(self, relative):
        rows = [strict_json(line) for line in self.read(relative).splitlines() if line]
        require(rows and all(isinstance(row, dict) and isinstance(row.get('phase'), str)
                            and integer(row.get('observed_ns'), 1) for row in rows), 'TRACE_SCHEMA')
        require(all(a['observed_ns'] <= b['observed_ns'] for a, b in zip(rows, rows[1:])), 'TRACE_CLOCK_ORDER')
        return rows


def phase(trace, name):
    values = [row['observed_ns'] for row in trace if row['phase'] == name]
    require(len(values) == 1, 'PHASE_EXACTLY_ONCE:' + name)
    return values[0]


def conservation(frames):
    s = frames['accounting_v2']
    require(all(integer(s.get(key)) for key in set(TERMINAL) | {'paints', 'acquired', 'retained_leases', 'retained_bytes'}),
            'ACCOUNTING_SCHEMA')
    require(s['paints'] > 0 and s['paints'] == sum(s[k] for k in TERMINAL), 'PAINT_CONSERVATION')
    require(all(s[k] == 0 for k in ('pending', 'leased', 'retained_leases', 'retained_bytes')), 'RETAINED_AFTER_JOIN')
    require(s['consumed'] <= s['acquired'] <= s['paints'], 'ACQUISITION_ACCOUNTING')
    require(all(frames.get(key) == s[key] for key in ('paints', 'acquired', 'coalesced', 'stale')), 'COUNTER_SNAPSHOT_MISMATCH')
    rows = frames['samples']
    require(isinstance(rows, list) and rows, 'NO_ACQUIRED_PAINT_OBSERVATIONS')
    require(all(isinstance(row, list) and len(row) == 4 and all(integer(v) for v in row)
                and row[0] > 0 and row[1] > 0 and row[2] >= row[1] for row in rows), 'SAMPLE_SCHEMA_CLOCK')
    require(all(a[0] < b[0] and a[1] <= b[1] and a[2] <= b[2] for a, b in zip(rows, rows[1:])), 'SAMPLE_ORDER')
    require(rows[-1][0] <= s['paints'], 'SAMPLE_INDEX')
    require(frames.get('samples_truncated') is False, 'INCOMPLETE_SAMPLE_COVERAGE')
    require(len(rows) == s['consumed'], 'CONSUMED_SAMPLE_COVERAGE')
    return {'accepted': s['paints'], 'terminal_sum': sum(s[k] for k in TERMINAL),
            'consumed': s['consumed'], 'retained_bytes': s['retained_bytes']}


def continuity(times, start, end):
    require(end > start, 'CONTINUITY_INTERVAL')
    inside = sorted(t for t in times if start <= t <= end)
    require(len(inside) >= 2, 'PEER_FRAME_OBSERVATIONS_MISSING')
    gaps = [b - a for a, b in zip([start] + inside, inside + [end])]
    maximum = max(gaps)
    require(maximum < CONTINUITY_NS, 'PEER_OBSERVATION_GAP')
    return {'observations': len(inside), 'max_gap_ms': maximum / NS_MS,
            'start_ns': start, 'end_ns': end}


def interruption(target, peers, start, end, minimum_gap_ms):
    require(end - start > 2 * SETTLE_NS, 'INTERRUPTION_INTERVAL')
    central_start, central_end = start + SETTLE_NS, end - SETTLE_NS
    times = sorted(target)
    require(not [t for t in times if central_start <= t <= central_end], 'TARGET_PAINT_DURING_SETTLED_INTERVAL')
    before = [t for t in times if t < central_start]
    after = [t for t in times if t > central_end]
    require(before and after, 'TARGET_BEFORE_AFTER_OBSERVATIONS')
    gap = after[0] - before[-1]
    require(gap >= minimum_gap_ms * NS_MS, 'TARGET_OBSERVATION_GAP_NOT_DEMONSTRATED')
    require(start - before[-1] < 1000 * NS_MS and 0 <= after[0] - end < 1000 * NS_MS,
            'TARGET_RESUME_OR_PRECEDING_FRAME_LATENCY')
    return {'settling_margin_ms_each_end': SETTLE_NS / NS_MS,
            'observed_phase_ms': (end - start) / NS_MS, 'target_paint_gap_ms': gap / NS_MS,
            'resume_to_next_observed_paint_ms': (after[0] - end) / NS_MS,
            'peers': {str(k): continuity(v, central_start, central_end) for k, v in peers.items()},
            'scope': 'retained completed-consumer paint observations; not proof of JS suspension or AV cadence'}


def resize_check(old, new):
    request = phase(old['trace'], 'resize_requested')
    begin = phase(new['trace'], 'resize_epoch_started')
    a, b = old['epoch'], new['epoch']
    require(old['identity'][:2] == new['identity'][:2] and b['epoch'] == a['epoch'] + 1, 'RESIZE_IDENTITY')
    require((a['width'], a['height']) != (b['width'], b['height']), 'RESIZE_GEOMETRY_UNCHANGED')
    require((b['width'], b['height']) == (540, 960), 'RESIZE_TARGET_GEOMETRY')
    require(a['revocation'] == 'epoch' and a['ended_ns'] <= b['started_ns'] <= begin, 'RESIZE_EPOCH_BARRIER')
    require(all(t <= request for t in old['times']), 'OLD_EPOCH_ACCEPTED_AFTER_RESIZE')
    require(all(t >= b['started_ns'] for t in new['times']), 'NEW_EPOCH_BEFORE_START')
    latency = b['first_paint_ns'] - request
    require(0 <= latency < 1000 * NS_MS, 'RESIZE_FIRST_PAINT_LATENCY')
    return {'request_ns': request, 'first_new_paint_ns': b['first_paint_ns'],
            'latency_ms': latency / NS_MS, 'maximum_latency_ms_exclusive': 1000,
            'from': [a['width'], a['height'], a['epoch']], 'to': [b['width'], b['height'], b['epoch']],
            'scope': 'one never-reused geometry transition; generic A-B-A resize NOT_EVALUATED'}


def replacement_check(old, new, reason):
    start = phase(old['trace'], reason)
    close = phase(old['trace'], 'before_close')
    create = phase(new['trace'], 'create_requested')
    ready = phase(new['trace'], 'after_created')
    a, b = old['manifest'], new['manifest']
    require(a['instance'] == b['instance'] and b['generation'] == a['generation'] + 1, 'REPLACEMENT_GENERATION')
    require(a['browser_id'] != b['browser_id'], 'REPLACEMENT_BROWSER_REUSED')
    require(start < close <= a['closed_ns'] < create < ready <= new['epoch']['first_paint_ns'], 'REPLACEMENT_NATIVE_ORDER')
    require(new['epoch']['epoch'] == 1 and not b['failed'], 'REPLACEMENT_STATE')
    result = {'old_generation': a['generation'], 'new_generation': b['generation'],
              'old_browser_id': a['browser_id'], 'new_browser_id': b['browser_id'],
              'closed_before_create': True, 'new_first_paint_ns': new['epoch']['first_paint_ns']}
    if reason == 'renderer_exit_requested':
        raw = a['renderer_exit_code']
        require(integer(raw) and raw == 22016 and os.WIFEXITED(raw) and os.WEXITSTATUS(raw) == 86,
                'CONTROLLED_RENDERER_EXIT_CODE')
        terminated = phase(old['trace'], 'renderer_terminated')
        require(a['failed'] is True and start < terminated < close, 'RENDERER_TERMINATION_ORDER')
        result.update(raw_wait_status=raw, decoded_exit_code=os.WEXITSTATUS(raw),
                      distinct_reported_renderer_pid=a['renderer_pid_reported'] != b['renderer_pid_reported'])
    return result


def targeted_events(by_id):
    require(set(by_id) == {1, 2, 3}, 'EVENT_INSTANCE_SET')
    details = {}
    for identity in (1, 2, 3):
        require(len(by_id[identity]) == 1, 'EVENT_UNEXPECTED_RESTART')
        state = by_id[identity][0]
        expected = 24 if identity == 1 else 0
        dispatched = sum(row['phase'] == 'fixture_event_dispatched' for row in state['_trace'])
        received = sum(row['phase'] == 'fixture_event_received' for row in state['_trace'])
        require(state['events_received'] == received == dispatched == expected, 'EVENT_TARGET_CONTAMINATION_OR_LOSS')
        details[str(identity)] = {'dispatched': dispatched, 'received': received}
    return {'instances': details, 'scope': 'fixed native fixture events only; no Production authority'}


def analyze(root):
    root = Path(root)
    inputs = Inputs(root)
    result = {'version': 1, 'status': 'FAIL', 'scope': 'retained owned H19 native scenario only',
              'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'gates': {}, 'input_sha256': inputs.hashes,
              'not_claimed': {'third_party_isolation': 'BLOCKED', 'production_keychain': 'BLOCKED',
                              'libobs_or_audiovisual_fps': 'NOT_EVALUATED',
                              'shared_renderer_crash': 'NOT_EVALUATED', 'leak_freedom': 'NOT_EVALUATED'}}

    def gate(name, operation):
        try:
            detail = operation()
            result['gates'][name] = {'status': 'PASS', **(detail or {})}
        except (EvidenceError, KeyError, TypeError, ValueError, OSError) as exc:
            result['gates'][name] = {'status': 'FAIL', 'reason': str(exc)[:160]}

    try:
        manifest = inputs.json('instances.json')
        report = inputs.json('report.json')
        supervision_raw = inputs.read('supervision.json.gz', maximum=64 * 1024**2, compressed=True)
        supervision = strict_json(supervision_raw)
        host_trace = inputs.trace('lifecycle.jsonl')
        scenario = manifest['scenario']
        require(scenario in SCENARIOS, 'UNSUPPORTED_SCENARIO')
        require(manifest.get('native_executed') is True and manifest.get('third_party_execution') is False,
                'OWNED_NATIVE_SCOPE')
        require(report.get('native_host_executed') is True and report.get('production_connected') is False,
                'COLLECTOR_NATIVE_SCOPE')
        require(report['supervision_gzip_sha256'] == inputs.hashes['supervision.json.gz']
                and report['supervision_sha256'] == hashlib.sha256(supervision_raw).hexdigest(), 'SUPERVISION_HASH')
        build_reader = Inputs(LAB_ROOT)
        build = build_reader.json(report['build_report'])
        require(build_reader.hashes[report['build_report']] == report['build_report_sha256'], 'BUILD_REPORT_HASH')
        require(any(binary['path'].endswith('/Contents/MacOS/MotiveBrowserFixture')
                    and binary['sha256'] == report['expected_executable_sha256'] for binary in build['binaries']),
                'BUILD_EXECUTABLE_IDENTITY')
        result['build_report'] = {'path': report['build_report'], 'sha256': report['build_report_sha256']}
        result.update(scenario=scenario, host_pid=manifest['host_pid'],
                      executable_sha256=report['expected_executable_sha256'],
                      credential_backend=report.get('credential_backend'))
        states = manifest['instances']
        require(isinstance(states, list) and 1 <= len(states) <= 32, 'INSTANCE_COUNT')
        by_id, epochs, pairs, browser_ids = {}, {}, set(), set()
        for state in states:
            instance, generation = state['instance'], state['generation']
            require(integer(instance, 1) and integer(generation, 1) and integer(state['browser_id'], 1), 'INSTANCE_IDENTITY')
            pair = instance, generation
            require(pair not in pairs and state['browser_id'] not in browser_ids, 'DUPLICATE_INSTANCE_BROWSER')
            require(state['origin'] == f'motive://i{instance}-g{generation}/', 'INSTANCE_ORIGIN')
            pairs.add(pair)
            browser_ids.add(state['browser_id'])
            by_id.setdefault(instance, []).append(state)
            require(state['closed'] is True and state['frames_written'] is True, 'INSTANCE_NOT_CLOSED_RENDERED')
            require(state['epochs'] and len(state['epochs']) <= 16, 'EPOCH_COUNT')
            all_trace = []
            for expected_epoch, epoch in enumerate(state['epochs'], 1):
                number = epoch['epoch']
                require(number == expected_epoch, 'EPOCH_SEQUENCE')
                directory = f'instance-{instance}-g{generation}-e{number}'
                trace = inputs.trace(directory + '/lifecycle.jsonl')
                require(all(row.get('instance') == instance and row.get('generation') == generation
                            and row.get('epoch') == number for row in trace), 'TRACE_IDENTITY')
                frames = inputs.json(directory + '/frames.json')
                identity = instance, generation, number
                times = [row[1] for row in frames['samples']]
                evidence = {'identity': identity, 'epoch': epoch, 'manifest': state,
                            'trace': trace, 'frames': frames, 'times': times}
                epochs[identity] = evidence
                all_trace += trace
                def validate_epoch(evidence=evidence, directory=directory):
                    epoch, identity = evidence['epoch'], evidence['identity']
                    detail = conservation(evidence['frames'])
                    require(epoch['accounting_observed'] is True and epoch['frames_written'] is True,
                            'EPOCH_ACCOUNTING_MISSING')
                    require(all(epoch[key] == 0 for key in ('pending_after_revoke', 'leased_after_join', 'retained_bytes_after_join')),
                            'EPOCH_RETAINED_RESOURCES')
                    require(epoch['started_ns'] <= epoch['first_paint_ns'] <= epoch['first_nontransparent_paint_ns'] <= epoch['ended_ns'],
                            'EPOCH_TIME_ORDER')
                    require(all(epoch['started_ns'] <= t <= epoch['ended_ns'] for t in evidence['times']), 'PAINT_OUTSIDE_EPOCH')
                    for label in ('first', 'latest'):
                        metadata = inputs.json(directory + '/' + label + '.json')
                        require(tuple(metadata[k] for k in ('instance', 'generation', 'epoch')) == identity, 'FRAME_IDENTITY')
                        require((metadata['width'], metadata['height']) == (epoch['width'], epoch['height']), 'FRAME_DIMENSIONS')
                        width, height = metadata['width'], metadata['height']
                        require(integer(width, 1) and integer(height, 1) and width * height <= 1920 * 1080
                                and metadata['stride'] == width * 4 and metadata['bgra8'] is True, 'FRAME_LAYOUT')
                        pixels = inputs.read(directory + '/' + label + '.bgra.gz', maximum=9 * 1024**2, compressed=True)
                        require(len(pixels) == width * height * 4, 'FRAME_LENGTH')
                        require(metadata['observed_ns'] >= epoch['started_ns'] and metadata['observed_ns'] <= epoch['ended_ns'],
                                'SAVED_FRAME_OUTSIDE_EPOCH')
                        if label == 'latest':
                            marker = tuple(pixels[(32 * width + 100) * 4:(32 * width + 100) * 4 + 4])
                            require(marker == (192, 64, identity[0] * 32, 255), 'FRAME_INSTANCE_PIXEL_MARKER')
                    return detail
                gate('epoch_' + directory, validate_epoch)
            state['_trace'] = sorted(all_trace, key=lambda row: row['observed_ns'])
        for values in by_id.values():
            values.sort(key=lambda row: row['generation'])
        result['instances_observed'] = len(states)
        result['epochs_observed'] = len(epochs)
        result['reported_renderer_groups'] = {str(pid): [[s['instance'], s['generation']] for s in states if s['renderer_pid_reported'] == pid]
                                               for pid in sorted({s['renderer_pid_reported'] for s in states})}

        def shutdown():
            require(supervision['returncode'] == 0 and supervision['reason'] == 'exit', 'HOST_EXIT')
            require(supervision['final_cleanup_observed_tree'] is True and not supervision['final_remaining_observed_live_pids'],
                    'OBSERVED_TREE_CLEANUP')
            budget = supervision['rss_budget']
            require(budget['limit_kib'] == 2 * 1024**2 and budget['first_exceedance'] is None
                    and supervision['peak_tree_rss_kib'] <= budget['limit_kib'], 'RSS_EMERGENCY_BUDGET')
            identities = {(p['pid'], tuple(p['birth']), p['proc_start_abstime'])
                          for sample in supervision['samples'] for p in sample['resource_usage']['processes']
                          if p['role'] == 'browser_host'}
            require(len(identities) == 1 and next(iter(identities))[0] == manifest['host_pid'], 'SINGLE_OBSERVED_HOST_IDENTITY')
            renderer_pids = {p['pid'] for sample in supervision['samples']
                             for p in sample['resource_usage']['processes'] if p['role'] == 'renderer'}
            require(all(integer(state.get('renderer_pid_reported'), 1)
                        and state['renderer_pid_reported'] in renderer_pids for state in states),
                    'REPORTED_RENDERER_NOT_OBSERVED_IN_OWNED_TREE')
            for state in states:
                trace = state['_trace']
                ready, close_request, close = phase(trace, 'after_created'), phase(trace, 'close_requested'), phase(trace, 'before_close')
                require(ready <= state['epochs'][0]['first_paint_ns'] < close_request <= close <= state['closed_ns'], 'BROWSER_CLOSE_ORDER')
                require(all(t <= close_request for epoch in state['epochs']
                            for t in epochs[state['instance'], state['generation'], epoch['epoch']]['times']), 'PAINT_ACCEPTED_AFTER_CLOSE')
                require(close < phase(trace, 'consumer_joined') < phase(trace, 'frame_report_written'), 'CONSUMER_CLOSE_ORDER')
            native = [phase(host_trace, name) for name in ('close_requested', 'quit_requested_once', 'loop_return', 'shutdown_enter', 'shutdown_return')]
            require(native == sorted(native) and max(s['closed_ns'] for s in states) <= native[1], 'HOST_SHUTDOWN_ORDER')
            return {'native_shutdown_ms': (native[-1] - native[-2]) / NS_MS,
                    'host_close_to_shutdown_return_ms': (native[-1] - native[0]) / NS_MS,
                    'observed_owned_tree_cleanup': True, 'host_process_identities': len(identities),
                    'rss_limit_mib': 2048, 'peak_sampled_rss_mib': supervision['peak_tree_rss_kib'] / 1024,
                    'scope': 'sampled owned tree only; unobserved escape and shared-page unique RAM not established'}
        gate('native_lifecycle_and_observed_cleanup', shutdown)

        def expected_failures():
            expected = set()
            if scenario in ('crash', 'lifecycle'):
                target = 1 if scenario == 'crash' else 3
                expected.add((target, by_id[target][0]['generation']))
            observed = {(s['instance'], s['generation']) for s in states if s['failed'] is True}
            require(observed == expected, 'UNEXPECTED_OR_MISSING_INSTANCE_FAILURE')
            return {'expected': sorted(expected), 'observed': sorted(observed)}
        gate('only_expected_instance_failures', expected_failures)

        def item(instance, generation_index=0, epoch=1):
            state = by_id[instance][generation_index]
            return epochs[instance, state['generation'], epoch]

        def all_times(instance, generation_index=0):
            state = by_id[instance][generation_index]
            return sorted(t for epoch in state['epochs'] for t in epochs[instance, state['generation'], epoch['epoch']]['times'])

        if scenario in ('hidden', 'lifecycle'):
            def hidden():
                target = item(1)
                begin = phase(target['trace'], 'hidden_begin')
                end = phase(target['trace'], 'hidden_end')
                peer_ids = (2, 3) if scenario == 'hidden' else (3, 4)
                return interruption(all_times(1), {i: all_times(i) for i in peer_ids}, begin, end, 3000)
            gate('hidden_observed_gap_and_peer_continuity', hidden)
        if scenario in ('resize', 'lifecycle'):
            target = 1 if scenario == 'resize' else 3
            gate('dynamic_resize_epoch_and_latency', lambda: resize_check(item(target), item(target, epoch=2)))
        if scenario == 'events':
            gate('targeted_events_exactly_24_only_instance_1', lambda: targeted_events(by_id))
        if scenario == 'slow':
            def slow():
                target = item(1)
                begin, end = phase(target['trace'], 'slow_begin'), phase(target['trace'], 'slow_end')
                require(450 * NS_MS <= end - begin < 2000 * NS_MS, 'SLOW_SCRIPT_DURATION')
                return interruption(target['times'], {i: all_times(i) for i in (2, 3)}, begin, end, 400)
            gate('slow_script_observed_stall_with_live_peers', slow)
        if scenario == 'slow-consumer':
            def slow_consumer():
                detail = {}
                for instance in (1, 2, 3):
                    frames = item(instance)['frames']
                    s = frames['accounting_v2']
                    require(frames['configured_consumer_delay_ms'] == 100 and s['coalesced'] > 0
                            and s['paints'] > s['acquired'] >= s['consumed'] > 1, 'SLOW_CONSUMER_BACKPRESSURE')
                    require(all(row[3] >= 100 * NS_MS for row in frames['samples']), 'SLOW_CONSUMER_DELAY_NOT_OBSERVED')
                    detail[str(instance)] = {'accepted': s['paints'], 'acquired': s['acquired'],
                                             'coalesced': s['coalesced'], 'consumed': s['consumed']}
                return {'instances': detail, 'scope': 'bounded coalescing; not output frame drops'}
            gate('slow_consumer_backpressure_and_coalescing', slow_consumer)
        if scenario in ('crash', 'lifecycle'):
            target = 1 if scenario == 'crash' else 3
            old_state = by_id[target][0]
            old_epoch = item(target, epoch=old_state['epochs'][-1]['epoch'])
            gate('controlled_renderer_exit_and_recovery', lambda: replacement_check(old_epoch, item(target, 1), 'renderer_exit_requested'))
        if scenario == 'lifecycle':
            def lifecycle_sequence():
                require({i: len(rows) for i, rows in by_id.items()} == {1: 2, 2: 1, 3: 2, 4: 2}, 'LIFECYCLE_INSTANCE_GENERATIONS')
                removed, a, c, d = by_id[2][0], by_id[1][0], by_id[3][0], by_id[4][0]
                remove = phase(removed['_trace'], 'remove_requested')
                closed = phase(removed['_trace'], 'before_close')
                created_d = phase(d['_trace'], 'create_requested')
                require(remove < closed < created_d and a['created_ns'] < remove < a['closed_ns']
                        and c['created_ns'] < remove < c['closed_ns'], 'REMOVE_WHILE_PEERS_LIVE')
                peer = {str(i): continuity(all_times(i), closed + 100 * NS_MS, closed + 1100 * NS_MS) for i in (1, 3)}
                restart = replacement_check(item(4), item(4, 1), 'restart_requested')
                suspend = replacement_check(item(1), item(1, 1), 'suspend_requested')
                require(not a['failed'] and not d['failed'] and not removed['failed'], 'UNEXPECTED_PEER_FAILURE')
                return {'removed_instance': 2, 'replacement_instance_created': 4,
                        'peers_after_removal': peer, 'restart_4': restart, 'suspend_resume_1': suspend}
            gate('long_lived_instance_sequence', lifecycle_sequence)
        require(result['gates'], 'NO_GATES')
        result['status'] = 'PASS' if all(g['status'] == 'PASS' for g in result['gates'].values()) else 'FAIL'
    except (EvidenceError, KeyError, TypeError, ValueError, OSError) as exc:
        result['gates']['evidence_structure'] = {'status': 'FAIL', 'reason': str(exc)[:160]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, help='New file only; defaults to RUN/analysis.json')
    args = parser.parse_args()
    output = args.output or args.run / 'analysis.json'
    report = analyze(args.run)
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'analysis': str(output),
                      'failed': {key: value for key, value in report['gates'].items() if value['status'] == 'FAIL'}}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
