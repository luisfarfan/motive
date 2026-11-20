#!/usr/bin/env python3
"""Run unchanged H13 regressions and close their verified replacement owner.

Use through h15_run_owned under with_physical_lock. The historical regression
runner owns LaunchServices restarts and byte/mode restoration. This wrapper
adds final shutdown, retaining the canonical lease if detached cleanup fails.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from h7_support import Client
from verify_h14_collection import ROOT, digest, lock, require, save
from verification_paths import verification_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', action='append', required=True)
    parser.add_argument('--camera-id')
    parser.add_argument('--camera-prepared', action='store_true')
    parser.add_argument('--microphone-id')
    args = parser.parse_args()
    held = lock()
    paths = verification_paths(ROOT)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAIL', 'lock': held, 'cleanup_errors': []}
    before = set((ROOT / 'var/evidence').glob('h13-regressions-*'))
    command = [sys.executable, str(ROOT / 'scripts/verify_h13_regressions.py'),
               '--lock-held', '--verification-python', str(ROOT / 'var/verify-python/bin/python')]
    for suite in args.suite:
        command += ['--suite', suite]
    if args.camera_id:
        command += ['--camera-id', args.camera_id]
    if args.camera_prepared:
        command += ['--camera-prepared']
    if args.microphone_id:
        command += ['--microphone-id', args.microphone_id]
    report['command'] = command
    client = None
    try:
        with (out / 'runner.log').open('x') as log:
            result = subprocess.run(command, stdout=log, stderr=log, timeout=1500)
        report['runner_exit'] = result.returncode
        created = set((ROOT / 'var/evidence').glob('h13-regressions-*')) - before
        require(len(created) == 1, 'One new primary manifest required')
        primary = created.pop() / 'manifest.json'
        value = json.loads(primary.read_text())
        report.update(primary=str(primary), primary_sha256=digest(primary))
        # Close only the PID that the historical runner recorded restoring.
        expected = value.get('restored', {}).get('pid')
        require(isinstance(expected, int) and expected > 1, 'Restored owner identity unavailable')
        client = Client()
        state = client.state()
        require(state['pid'] == expected, 'Unexpected replacement owner')
        actual = subprocess.check_output(['ps', '-p', str(expected), '-o', 'comm='], text=True).strip()
        require(Path(actual).resolve() == paths.app_executable, 'Replacement executable differs')
        require(digest(paths.app_executable) == value['app_sha256'], 'Candidate changed')
        require(all(not s['native_busy'] for s in state['outputs'].values()), 'Outputs not quiescent')
        report['final_owner_pid'] = expected
        report['shutdown'] = client.call('request_shutdown')
        deadline = time.monotonic() + 25
        while subprocess.run(['ps', '-p', str(expected), '-o', 'pid='],
                             stdout=subprocess.DEVNULL).returncode == 0:
            require(time.monotonic() < deadline, 'Detached owner failed to exit')
            time.sleep(.2)
        report['final_owner_absent'] = True
        report['status'] = 'PASS' if value['ok'] and result.returncode == 0 else 'FAIL'
    except Exception as error:
        report['cleanup_errors'].append(repr(error))
        common = Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        if not common.is_absolute():
            common = ROOT / common
        lease = common.resolve().parent / 'var/run/physical-test.lock'
        save(lease / 'RETAIN.json', {'worktree': str(ROOT), 'report': str(out / 'report.json'),
                                   'reason': 'Detached native owner cleanup not proven', 'error': repr(error)})
    finally:
        if client:
            client.close()
        save(out / 'report.json', report)
    print(json.dumps(report))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
