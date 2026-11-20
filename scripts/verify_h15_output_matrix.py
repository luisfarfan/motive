#!/usr/bin/env python3
"""Bounded conservative output matrix; each case owns a fresh portable process."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from verify_h14_collection import ROOT, lock, save


def matrix_outcome(cases):
    if len(cases) != 9 or len({c['name'] for c in cases}) != 9 or any(
        len(c.get('reports', [])) != 1 or c.get('functional_status') != 'PASS'
        or c.get('status') not in ('PASS', 'PARTIAL') for c in cases
    ):
        return 'FAIL'
    return 'PARTIAL' if any(c['status'] == 'PARTIAL' for c in cases) else 'PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    app = args.app.resolve(strict=True)
    binary = app/'Contents/MacOS/motive'
    data = Path.home()/'Library/Application Support/local.motive.studio'
    cases = [(encoder, mode, 'stop') for encoder in ('videotoolbox','x264')
             for mode in ('recording','streaming','dual')]
    cases += [('videotoolbox','dual',ending) for ending in ('cancel','receiver-loss','shutdown')]
    report = {'status':'RUNNING', 'cases': [], 'frame_reordering':False, 'seconds_per_case':8}
    for encoder,mode,ending in cases:
        before = set((ROOT/'var/evidence').glob('h14-output-integrity-*'))
        name = '-'.join((encoder,mode,ending))
        command = [sys.executable,'scripts/h15_run_owned.py','--app',str(app),
            '--output',str(out/name),'--timeout','180',sys.executable,
            'scripts/verify_h14_output_integrity.py','--lock-held','--app',str(binary),
            '--store-root',str(data),'--encoder',encoder,'--mode',mode,'--ending',ending]
        if ending == 'shutdown':
            command += ['--shutdown-report',str(Path.home()/'Library/Logs/Motive/last-shutdown.json')]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=220)
        (out/(name+'.log')).write_text(result.stdout+result.stderr)
        new = set((ROOT/'var/evidence').glob('h14-output-integrity-*'))-before
        row = {'name':name,'runner_exit':result.returncode,'reports':[str(p/'report.json') for p in new]}
        for path in new:
            actual = json.loads((path/'report.json').read_text())
            row.update(status=actual['status'],functional_status=actual.get('functional_status'),
                       tail_accounting_statuses=actual.get('tail_accounting_statuses'),error=actual.get('error'))
        report['cases'].append(row)
        save(out/'report.json', report)
        wrapper = json.loads((out/name/'report.json').read_text())
        if wrapper['cleanup_errors'] or wrapper['owner_exit'] != 0:
            raise RuntimeError('Owner cleanup incomplete; no next physical case')
        print(json.dumps(row),flush=True)
    report['status'] = matrix_outcome(report['cases'])
    save(out/'report.json', report)
    return int(report['status'] == 'FAIL')


if __name__ == '__main__': raise SystemExit(main())
