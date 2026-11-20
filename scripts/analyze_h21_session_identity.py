#!/usr/bin/env python3
"""Audit recorded identities at sampled points, without claiming native lifetime proof."""
import argparse
import json
from pathlib import Path
import subprocess

from verify_h14_collection import digest, lock, require, save


def fingerprint(state):
    return {
        'pid': state['pid'],
        'sources': sorted((s['id'], s['kind'], s['instance_id']) for s in state['sources']),
        'sck_creation': sorted((s['id'], s['capture_diagnostics']['created_ns'])
                               for s in state['sources'] if s.get('capture_diagnostics')),
        'source_instances_created': state['transition']['source_instances_created'],
        'audio': sorted((s['id'], s['instance_id']) for s in state['audio_mixer']['runtime']['inputs']),
        'audio_instances_created': state['audio_mixer']['runtime']['instances_created'],
        'output_attempts': {target: slot['attempt_id'] for target, slot in state['outputs'].items()},
    }


def audit(initial, observations, duration):
    expected = fingerprint(initial)
    previous_frames = {s['id']: s['frames'] for s in initial['sources']}
    previous_output = {t: s['stats']['output_frames'] for t, s in initial['outputs'].items()}
    times = []
    for row in observations:
        state = row['state']
        require(fingerprint(state) == expected, 'Production/source/audio/output identity changed')
        elapsed = row['elapsed_s']
        require(elapsed >= 0 and (not times or elapsed > times[-1]), 'Invalid observation timeline')
        before, after = row['host_bracket_s']
        require(before <= after, 'Invalid query bracket')
        times.append(elapsed)
        for source in state['sources']:
            require(source['frames'] >= previous_frames[source['id']], 'Source frame counter regressed')
            previous_frames[source['id']] = source['frames']
        for target, slot in state['outputs'].items():
            require(slot['phase'] == 'active', 'Output was not active at an observation')
            require(slot['encoding']['selected_hardware'], 'Hardware encoder identity changed')
            require(slot['stats']['output_frames'] >= previous_output[target], 'Output frame counter regressed')
            require(slot['stats']['output_dropped_frames'] == 0, 'Output drops observed')
            previous_output[target] = slot['stats']['output_frames']
    require(times, 'No observations')
    gaps = [right-left for left, right in zip(times, times[1:])]
    largest = max(gaps, default=0)
    coverage = times[0] <= 5 and duration-times[-1] <= 5 and largest <= 5
    return {'status': 'PASS' if coverage else 'PARTIAL', 'identity': expected,
            'samples': len(times), 'first_elapsed_s': times[0], 'last_elapsed_s': times[-1],
            'largest_sample_gap_s': largest, 'sample_coverage_5s': coverage,
            'source_final_frames': previous_frames, 'output_final_frames': previous_output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); lock()
    source = args.report.resolve(strict=True); journal = source.with_name('samples.jsonl')
    run = json.loads(source.read_text())
    owner = json.loads(source.parent.with_name(source.parent.name+'-owner').joinpath('report.json').read_text())
    require(owner['owner_exit'] == 0 and not owner['cleanup_errors'], 'Owner cleanup not verified')
    require(run.get('runtime_status') == 'PASS' and not run['cleanup_errors'], 'Runtime did not pass')
    require(subprocess.run(['ps','-p',str(run['owner_pid']),'-o','pid='],
                          stdout=subprocess.DEVNULL).returncode == 1, 'Owner still present')
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    result = {'status':'FAIL', 'source_sha256':digest(source), 'journal_sha256':digest(journal),
              'analyzer_sha256':digest(Path(__file__)),
              'scope':'Recorded observations only; not proof of pixels, callback lifetime, absence of UAF/leaks, or unobserved native SCStream internals.'}
    try:
        with journal.open() as lines:
            result.update(audit(run['initial_state'], (json.loads(line) for line in lines), run['requested_seconds']))
    except Exception as error: result['error'] = repr(error)
    result['source_unchanged'] = result['source_sha256'] == digest(source) and result['journal_sha256'] == digest(journal)
    if not result['source_unchanged']: result['status'] = 'FAIL'
    save(out/'analysis.json', result)
    print(json.dumps({k:result.get(k) for k in ('status','samples','largest_sample_gap_s','error')}))
    return int(result['status'] != 'PASS')


if __name__ == '__main__': raise SystemExit(main())
