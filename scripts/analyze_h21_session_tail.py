#!/usr/bin/env python3
"""Apply the historical terminal-packet classifier to closed H21 session media.

This is separate from full-duration media gates. It reuses decoded packet probes
without altering the native trace, stop bracket, or historical tolerances.
"""
import argparse
import json
from pathlib import Path
import shutil

from verify_h14_collection import digest, lock, require, save
from verify_h14_output_integrity import correlate_tail
from h21_tail_semantics import interpret_tail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); lock()
    source = args.report.resolve(strict=True)
    run = json.loads(source.read_text())
    owner = json.loads(source.parent.with_name(source.parent.name+'-owner').joinpath('report.json').read_text())
    require(owner['owner_exit'] == 0 and not owner['cleanup_errors'], 'Owner cleanup not verified')
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    for script in (Path(__file__), Path(__file__).with_name('verify_h14_output_integrity.py'),
                   Path(__file__).with_name('h21_tail_semantics.py')):
        shutil.copy2(script, out/script.name)
    result = {'status':'FAIL', 'source_sha256':digest(source),
              'analyzer_sha256':digest(Path(__file__)),
              'classifier_sha256':digest(Path(__file__).with_name('verify_h14_output_integrity.py')),
              'semantics_sha256':digest(Path(__file__).with_name('h21_tail_semantics.py')),
              'scope':'Recorded terminal dispatch trace versus actual container packets; not every packet of an arbitrary-length session.',
              'media':[]}
    try:
        require(run.get('runtime_status') == 'PASS', 'Runtime did not pass')
        analysis_path = args.analysis/'analysis.json'
        analysis = json.loads(analysis_path.read_text())
        result['media_analysis_sha256'] = digest(analysis_path)
        require(analysis['source_sha256'] == result['source_sha256'], 'Media analysis belongs to another report')
        for medium in run['media']:
            target = medium['target']
            bound = [m for m in analysis['media'] if m['target'] == target and m['path'] == medium['path']]
            require(len(bound) == 1, 'Media analysis target binding missing')
            probe_path = args.analysis / (target+'-probe.json')
            probe = json.loads(probe_path.read_text())
            row = {'target':target, 'probe_sha256':digest(probe_path), 'media_sha256_at_decode':bound[0]['sha256']}
            result['media'].append(row)
            initial = run.get('initial_traces', {}).get(target)
            final = run.get('final_traces', {}).get(target)
            if not initial or not final:
                row['tail_accounting'] = {'status':'INCONCLUSIVE', 'reason':'initial_or_final_trace_not_recorded'}
            else:
                require(initial['output']['attempt_id'] == final['output']['attempt_id'], 'Output attempt changed')
                row['tail_accounting'] = correlate_tail(initial['packet_trace'], final['packet_trace'], probe['packets'])
            row['obs_stop_semantics'] = interpret_tail(row['tail_accounting'])
        states = [row['tail_accounting']['status'] for row in result['media']]
        require(len(states) == 2, 'Both destinations required')
        result['status'] = ('FAIL' if 'FAIL' in states else
                            'PASS' if all(s == 'TRACED_TAIL_PRESENT' for s in states) else 'PARTIAL')
        semantic_states = [row['obs_stop_semantics']['status'] for row in result['media']]
        result['obs_stop_semantics_status'] = ('PASS' if all(s == 'PASS' for s in semantic_states)
                                               else 'FAIL' if 'FAIL' in semantic_states else 'INCONCLUSIVE')
    except Exception as error: result['error'] = repr(error)
    result['source_unchanged'] = digest(source) == result['source_sha256']
    if not result['source_unchanged']: result['status'] = 'FAIL'
    save(out/'analysis.json', result)
    print(json.dumps({'status':result['status'], 'error':result.get('error')}))
    return int(result['status'] == 'FAIL')


if __name__ == '__main__': raise SystemExit(main())
