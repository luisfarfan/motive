#!/usr/bin/env python3
"""Explicit serial native H19 suites, one owned host tree at a time, fixed 2 GiB stop."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_owned_fixture import LAB, canonical_directory, save_json


def cases(suite):
    if suite == 'capacity':
        # Balanced order across three fresh-process/profile repetitions.
        return [(f'animated-{count}-r{rep}', count, 'steady', 72000)
                for rep, order in enumerate(((1,3,5),(3,5,1),(5,1,3)), 1) for count in order]
    if suite == 'static-mixed':
        return [(f'{mode}-{count}-r{rep}', count, mode, 72000)
                for rep in range(1,4) for mode,count in [('static',1),('mixed',5)]]
    if suite == 'diagnostics':
        return [(mode+'-3', 3, mode, duration) for mode,duration in
                [('security',8000),('lifecycle',30000),('resize',8000),('hidden',10000),
                 ('events',8000),('slow',8000),('slow-consumer',8000),('crash',8000)]]
    if suite == 'soak':
        return [('lifecycle-3-600s',3,'lifecycle',600000)]
    raise ValueError('FIXED_SUITE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['capacity','static-mixed','diagnostics','soak'], required=True)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.absolute()
    canonical_directory(output.parent)
    if not output.is_relative_to(LAB/'evidence'):
        raise ValueError('LAB_EVIDENCE_REQUIRED')
    output.mkdir(mode=0o700)
    started = time.monotonic()
    result = {'suite':args.suite,'status':'RUNNING','rss_limit_mib':2048,'layout':'one CEF host, distinct contexts',
              'warmup_seconds':10,'sample_seconds':60,'cases':[],
              'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'binary_sha256':args.expected_sha256,'full_frozen_matrix':'PARTIAL; selected CEF pin and640x360@30 subset'}
    save_json(output/'plan.json',{'cases':cases(args.suite),'source':result})
    for index,(name,count,scenario,duration) in enumerate(cases(args.suite)):
        destination = output/name
        print('H19 native case '+name,flush=True)
        command = [sys.executable,str(LAB/'tools/run_h19_multi.py'),'--build-root',str(args.build_root),
                   '--expected-sha256',args.expected_sha256,'--output-dir',str(destination),
                   '--instances',str(count),'--scenario',scenario,'--duration-ms',str(duration),
                   '--deadline-seconds',str(min(720,duration/1000+15)),
                   '--generation',str(time.monotonic_ns()//1000)]
        code = subprocess.call(command)
        report_path = destination/'report.json'
        report = json.loads(report_path.read_text()) if report_path.is_file() else {}
        entry = {'name':name,'returncode':code,'status':report.get('status','FAIL'),
                 'report':str(report_path.relative_to(LAB)),
                 'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path.exists() else None}
        result['cases'].append(entry)
        save_json(output/f'progress-{index+1:02d}.json', result)
        if code or entry['status'] != 'PASS':
            result['status']='FAIL';break
    else:
        result['status']='PASS'
    result['elapsed_seconds']=time.monotonic()-started
    result['scope']='Scoped run gates only. Analyze scenario and sustained performance acceptance separately.'
    save_json(output/'summary.json',result)
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
