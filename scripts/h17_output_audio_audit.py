#!/usr/bin/env python3
"""Read-only H17 audit of retained B6 media metadata; never opens the owner.

This replays packet correlation over existing ffprobe JSON. It does not claim
a new decode or physical trial. Outputs are created exclusively at --output.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import types

from test_h14_output_accounting import fixture
from verify_h14_output_integrity import correlate_tail

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '15ffbad307c5439270130979dae0e9d66d92d700'
B6 = 'fe58dc5ca406eb0427d40c5b5a47473aad5d251a75f9d87e170eae9b51cd7d47'


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def load(path, evidence):
    path = Path(path).resolve(strict=True)
    digest = sha(path)
    value = json.loads(path.read_text())
    evidence[str(path)] = digest
    return value


def baseline_correlator():
    source = subprocess.check_output(
        ['git', 'show', BASELINE + ':scripts/verify_h14_output_integrity.py'], cwd=ROOT)
    module = types.ModuleType('h17_baseline_output_audit')
    module.__file__ = str(ROOT / 'scripts/verify_h14_output_integrity.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module.correlate_tail, hashlib.sha256(source).hexdigest()


def reproductions(previous):
    rows = []
    for name in ('missing_final_callback', 'reused_container_packet', 'active_snapshot'):
        initial, final, packets = fixture()
        if name == 'missing_final_callback':
            final['packets'].pop()
            final['summary']['trace_missed_records'] = 1
            packets.pop()
        elif name == 'reused_container_packet':
            final['packets'][-1]['pts'] = 0
            packets.pop()
        else:
            final['summary']['quiescent_observed_ns'] = None
        before = previous(initial, final, packets)
        after = correlate_tail(initial, final, packets)
        assert before['status'] == 'TRACED_TAIL_PRESENT', before
        assert after['status'] != 'TRACED_TAIL_PRESENT', after
        rows.append({'name': name, 'status': 'PASS', 'scope': 'synthetic_analyzer_regression',
                     'before': before, 'after': after})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--audio-report', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('--output already exists; evidence is never overwritten')
    evidence = {}
    matrix = load(args.matrix, evidence)
    previous, previous_sha = baseline_correlator()
    report = {'version': 1, 'status': 'PARTIAL', 'binary_sha256': B6,
              'baseline_revision': BASELINE, 'baseline_correlator_sha256': previous_sha,
              'current_correlator_sha256': sha(ROOT / 'scripts/verify_h14_output_integrity.py'),
              'script_sha256': sha(__file__), 'physical_execution': 'NOT_EVALUATED',
              'fresh_decode': 'NOT_EVALUATED', 'complete_delivery': 'PARTIAL',
              'analyzer_regressions': reproductions(previous), 'media': [], 'audio': []}
    missing = {'normal': Counter(), 'intentional_partial': Counter()}
    for case in matrix['cases']:
        assert len(case['reports']) == 1, case
        primary = load(case['reports'][0], evidence)
        assert primary['app_sha256'] == B6, case['name']
        assert primary.get('functional_status') == 'PASS', case['name']
        for medium in primary['media']:
            analysis = medium['analysis']
            timeline = load(analysis['timeline']['path'], evidence)
            assert evidence[str(Path(analysis['timeline']['path']).resolve())] == analysis['timeline']['sha256']
            media_path = Path(medium['path']).resolve(strict=True)
            evidence[str(media_path)] = sha(media_path)
            assert evidence[str(media_path)] == analysis['sha256']
            original = analysis['tail_accounting']
            current = correlate_tail(medium['initial_trace'], medium['final_trace'], timeline['packets'])
            assert current['status'] == original['status'], (case['name'], current, original)
            absent = {kind: data['absent'] for kind, data in current['kinds'].items()}
            group = 'intentional_partial' if analysis['expected_partial'] else 'normal'
            for kind, packets in absent.items():
                missing[group].update(kind + ':' + packet['stop_relation'] for packet in packets)
            report['media'].append({'case': case['name'], 'target': medium['target'],
                'status': 'PARTIAL', 'metadata_reanalysis': 'PASS',
                'expected_partial': analysis['expected_partial'],
                'historical_functional_status': analysis['status'],
                'classification_unchanged': True, 'original_classifier_result': original['status'],
                'current_correlation': current, 'path': str(media_path),
                'raw_counter_differences': analysis['raw_counter_differences']})
    report['missing_traced_packets'] = {kind: dict(counts) for kind, counts in missing.items()}
    for path in args.audio_report:
        audio = load(path, evidence)
        assert audio['binary_sha256'] == B6 and audio['ok'] is True, path
        trials = []
        for trial in audio['trials']:
            assert trial['ok'] is True, (path, trial['name'])
            trials.append({key: trial[key] for key in ('name', 'application_continuity',
                'tone_continuity', 'silence_observations', 'av_pulses', 'old_pid', 'new_pid') if key in trial})
        report['audio'].append({'path': str(path.resolve()), 'metadata_audit': 'PASS',
                               'fresh_execution': 'NOT_EVALUATED', 'trials': trials})
    report['input_hashes'] = evidence
    # Re-read every input after the audit; the historical artifacts are immutable.
    assert all(sha(path) == digest for path, digest in evidence.items())
    report['historical_inputs_unchanged'] = 'PASS'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps({'output': str(args.output.resolve()), 'status': report['status'],
                      'media': len(report['media']), 'missing_traced_packets': report['missing_traced_packets']}))


if __name__ == '__main__':
    main()
