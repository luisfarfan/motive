#!/usr/bin/env python3
"""Read-only comparison of the live retirement receipt with final owned evidence."""
import gzip
import hashlib
import json
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
ROOT = LAB / 'evidence/H19-candidate-soak/lifecycle-3-600s'
RECEIPT = ROOT.parent / 'live-retired-epochs.json'
OUTPUT = LAB / 'research/h19-soak-retirement-match.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    hashes = {}
    def read(path):
        data = path.read_bytes()
        hashes[str(path.relative_to(LAB))] = sha(data)
        return data
    receipt = json.loads(read(RECEIPT))
    report = json.loads(read(ROOT / 'report.json'))
    manifest = json.loads(read(ROOT / 'instances.json'))
    packed = read(ROOT / 'supervision.json.gz')
    assert sha(packed) == report['supervision_gzip_sha256']
    expanded = gzip.decompress(packed)
    assert sha(expanded) == report['supervision_sha256']
    raw = json.loads(expanded)
    assert receipt['observed_owned_arguments_match'] is True
    assert manifest['host_pid'] == receipt['host_pid']
    host = [(s['elapsed_ms'], p) for s in raw['samples']
            for p in s['resource_usage']['processes']
            if p['pid'] == receipt['host_pid'] and p['birth'] == receipt['host_birth']
            and p['role'] == 'browser_host']
    assert host and len({p['proc_start_abstime'] for _, p in host}) == 1
    assert len(receipt['retired_epochs']) == 5
    matched = []
    for retired in receipt['retired_epochs']:
        name = retired['epoch']
        assert '/' not in name and name.startswith('instance-')
        data = read(ROOT / name / 'frames.json')
        assert sha(data) == retired['frames_sha256']
        counts = json.loads(data)['accounting_v2']
        assert counts['paints'] == retired['paints']
        assert counts['retained_bytes'] == retired['retained_bytes'] == 0
        assert counts['retained_leases'] == retired['retained_leases'] == 0
        assert counts['pending'] == counts['leased'] == 0
        matched.append({'epoch': name, 'sha256': sha(data), 'accepted_paints': counts['paints'],
                        'retained_bytes': 0, 'retained_leases': 0, 'pending': 0, 'leased': 0})
    memberships = []
    for item in manifest['instances']:
        pid = item['renderer_pid_reported']
        observed = [(s['elapsed_ms'], p) for s in raw['samples']
                    for p in s['resource_usage']['processes'] if p['pid'] == pid and p['role'] == 'renderer']
        births = sorted({tuple(p['birth']) for _, p in observed})
        memberships.append({'instance': item['instance'], 'generation': item['generation'],
                            'renderer_pid': pid, 'observed_births': [list(b) for b in births],
                            'identity_unambiguous_in_retained_tree': len(births) == 1,
                            'observations': len(observed),
                            'first_observed_python_elapsed_ms': observed[0][0] if observed else None,
                            'last_observed_python_elapsed_ms': observed[-1][0] if observed else None})
    result = {'status': 'PASS', 'scope': 'Match of prior external live-host receipt and final immutable epoch ledgers; logical bytes only.',
              'receipt_observed_utc': receipt['observed_utc'], 'host_pid': receipt['host_pid'],
              'host_birth': receipt['host_birth'], 'host_identity_corroborated': True,
              'host_observations': len(host), 'receipt_owned_arguments_match': True,
              'matched_retired_epochs': matched, 'renderer_membership': memberships,
              'input_sha256': hashes, 'checker_sha256': sha(Path(__file__).read_bytes()),
              'limits': ['Liveness at receipt time is the recorded external observation, not a retroactive OS query.',
                         'Renderer observation offsets use Python monotonic; never subtract native lifecycle offsets.',
                         'Zero logical retired-frame bytes does not measure allocator caches, Chromium heaps or released physical pages.',
                         'This match does not override a separate functional lifecycle failure.']}
    with OUTPUT.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'matched_epochs': len(matched), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()
