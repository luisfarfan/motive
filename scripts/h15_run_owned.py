#!/usr/bin/env python3
"""Run one bounded local suite against a fresh portable owner under the shared lock.

Never attaches to an existing owner, loads user projects, kills Motive or opens
devices. The explicit suite remains responsible for its own fixtures/cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from verify_h14_collection import Client, ROOT, default_owner, digest, lock, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command or not 1 <= args.timeout <= 1800:
        parser.error('explicit bounded suite command required')
    lock()
    app = args.app.resolve(strict=True)
    binary = app / 'Contents/MacOS/motive'
    assert (app / 'Contents/Resources/MotivePortable.json').is_file()
    data = Path.home() / 'Library/Application Support/local.motive.studio'
    assert not (data / 'run/motive.sock').exists(), 'Existing owner; close normally first'
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
    env.update(MOTIVE_TEST_APP=str(app), MOTIVE_TEST_DATA_ROOT=str(data),
               MOTIVE_TEST_RECORDINGS_ROOT=str(Path.home() / 'Movies/Motive'))
    env['PATH'] = str(app / 'Contents/MacOS') + ':' + env.get('PATH', '/usr/bin:/bin')
    build = {'binary_sha256': digest(binary),
             'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'inputs': {str(p.relative_to(ROOT)): digest(p) for p in sorted(
                 [*ROOT.glob('src/**/*'), *ROOT.glob('native/**/*'), ROOT/'Cargo.toml', ROOT/'Cargo.lock', ROOT/'build.rs']) if p.is_file()}}
    save(out / 'build-binding.json', build)
    report = {'command': args.command, 'app': str(app), 'binary_sha256': build['binary_sha256'],
              'cleanup_errors': [], 'status': 'FAIL'}
    owner = suite = client = None
    with (out/'owner.log').open('x') as log, (out/'suite.log').open('x') as suite_log:
        try:
            owner = subprocess.Popen([str(binary)], cwd='/', env=env, stdout=log, stderr=log)
            report['owner_pid'] = owner.pid
            for _ in range(150):
                try:
                    client = Client(app, owner.pid, out)
                    default_owner(client.state())
                    break
                except (OSError, ValueError):
                    assert owner.poll() is None, 'Owner exited at startup'
                    time.sleep(.1)
            else:
                raise RuntimeError('Owner startup timeout')
            suite = subprocess.Popen(args.command, cwd=ROOT, env=env, stdout=suite_log, stderr=suite_log)
            report['suite_exit'] = suite.wait(timeout=args.timeout)
            report['status'] = 'PASS_RUNNER' if report['suite_exit'] == 0 else 'FAIL_RUNNER'
        except Exception as error:
            report['error'] = str(error)
        finally:
            if suite and suite.poll() is None:
                report['cleanup_errors'].append('Suite still active; owner retained for explicit recovery')
            elif owner and owner.poll() is None and client:
                try:
                    report['shutdown'] = client.call('request_shutdown')['ok']
                    owner.wait(timeout=25)
                except Exception as error:
                    report['cleanup_errors'].append(str(error))
            report['owner_exit'] = owner.poll() if owner else None
            save(out / 'report.json', report)
    print(json.dumps(report))
    return int(report['status'] != 'PASS_RUNNER' or bool(report['cleanup_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
