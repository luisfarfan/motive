#!/usr/bin/env python3
"""Read-only final check of previously observed owned PID/birth identities.

Does not enumerate unrelated process command lines, signal processes, or touch
the canonical lock. Run after the campaign driver has returned.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / 'poc/browser-host'))
from supervisor import birth_identity


def check(matrix_path):
    hashes = {}
    identities = set()
    sources = []

    def read(path):
        raw = path.read_bytes()
        hashes[str(path.relative_to(LAB))] = hashlib.sha256(raw).hexdigest()
        if path.suffix == '.gz':
            with gzip.open(path, 'rb') as stream:
                raw = stream.read(64 * 1024**2 + 1)
        if len(raw) > 64 * 1024**2:
            raise ValueError('INPUT_OVERSIZE')
        return json.loads(raw)

    def collect(samples):
        count = 0
        for sample in samples:
            processes = sample.get('resource_usage', {}).get('processes')
            if processes is None:
                processes = sample.get('processes', [])
            if not isinstance(processes, list):
                continue
            for process in processes:
                pid, birth = process.get('pid'), process.get('birth')
                if type(pid) is int and pid > 0 and isinstance(birth, list) and len(birth) == 2 and all(type(x) is int for x in birth):
                    identities.add((pid, tuple(birth)))
                    count += 1
        return count

    evidence = LAB / 'evidence'
    paths = sorted(set(evidence.glob('H22-*/**/*supervision.json')) |
                   set(evidence.glob('H22-*/**/*supervision.json.gz')))
    for path in paths:
        data = read(path)
        count = collect(data.get('samples', []))
        sources.append({'path': str(path.relative_to(LAB)), 'identity_observations': count,
                        'recorded_final_remaining': data.get('final_remaining_observed_live_pids', data.get('remaining_observed_live_pids'))})
    for path in sorted(evidence.glob('H22-*/report.json')):
        data = json.loads(path.read_bytes())
        if 'supervisor_samples' in data:
            data = read(path)
            sources.append({'path': str(path.relative_to(LAB)),
                            'identity_observations': collect(data['supervisor_samples']),
                            'recorded_final_remaining': data.get('remaining_observed_pids')})

    remaining = [{'pid': pid, 'birth': list(birth)} for pid, birth in sorted(identities)
                 if birth_identity(pid) == birth]
    matrix = read(matrix_path.resolve())
    logs = []
    log_paths = []
    for row in matrix['rows']:
        if 'native_status' not in row:
            continue
        case = row['case']
        run = LAB / row['path']
        root_name = run.name.removesuffix('-' + case)
        path = run.parent / root_name / (case + '.log')
        log_paths.append(path)
    log_paths.extend(sorted(evidence.glob('H22-*-observer/native.log')))
    for path in log_paths:
        raw = path.read_bytes()
        hashes[str(path.relative_to(LAB))] = hashlib.sha256(raw).hexdigest()
        text = raw.decode()
        markers = {key: text.count(marker) for key, marker in {
            'lock_acquired': 'H22_PHYSICAL_SLOT_ACQUIRED ',
            'lock_released': 'H22_PHYSICAL_SLOT_RELEASED',
            'sleep_guard_started': 'H22_TEMPORARY_IDLE_SLEEP_ASSERTION pid=',
            'sleep_guard_released': 'H22_IDLE_SLEEP_ASSERTION_RELEASED'}.items()}
        status = 'PASS' if all(value == 1 for value in markers.values()) else 'FAIL'
        observation = path.parent / 'observation.json'
        if path.name == 'native.log' and path.parent.name.endswith('-observer') and observation.exists():
            receipt = read(observation)
            native_report = path.parent.parent / path.parent.name.removesuffix('-observer') / 'report.json'
            if receipt.get('native_returncode') == 75 and not native_report.exists() and all(value == 0 for value in markers.values()):
                status = 'NOT_EXECUTED_SLOT_BUSY'
        logs.append({'path': str(path.relative_to(LAB)), **markers,
                     'status': status})
    lock = Path('/Users/luisfarfan/Developer/products/motive/var/run/physical-test.lock/OWNER')
    try:
        owner = json.loads(lock.read_bytes())
        lock_observation = {key: owner.get(key) for key in ('owner', 'worktree', 'purpose', 'acquired_utc')}
    except FileNotFoundError:
        lock_observation = {'owner': None}
    own_lock = lock_observation.get('worktree') == str(LAB.parent)
    passed = bool(identities and logs) and not remaining and not own_lock and all(x['status'] in ('PASS', 'NOT_EXECUTED_SLOT_BUSY') for x in logs)
    return {'status': 'PASS' if passed else 'FAIL', 'observed_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'sampled owned PID/birth identities and release receipts; not complete OS confinement',
            'observed_distinct_identities': len(identities), 'remaining_owned_identities': remaining,
            'sources': sources, 'native_lock_receipts': logs,
            'canonical_lock_observation_read_only': lock_observation,
            'input_sha256': hashes, 'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limits': ['An unobserved escaped process cannot be excluded by this check.',
                       'PID reuse is distinguished by birth identity and current UID.',
                       'Foreign lock ownership is only observed and never modified.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.matrix)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('status', 'observed_distinct_identities', 'remaining_owned_identities')}))
    raise SystemExit(result['status'] != 'PASS')
