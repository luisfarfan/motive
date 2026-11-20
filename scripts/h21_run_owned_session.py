#!/usr/bin/env python3
"""H21: supervise one bounded personal session against a fresh portable owner.

Never attaches to an existing owner, loads user projects or opens devices.
Normal shutdown is preferred. An unacknowledged safety deadline terminates only
the fresh child owned by this supervisor, before bounded Display covers expire.
This is a failed run; remaining fixtures retain the canonical lease for cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import time

from verify_h14_collection import Client, ROOT, default_owner, digest, lock, save
from h21_session_state import console_locked
from h21_supervision import terminate_owned_child


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command or not 1 <= args.timeout <= 4200:
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
    abort_file = out / 'abort-requested.json'
    env['MOTIVE_TEST_ABORT_FILE'] = str(abort_file)
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
            report['disk_free_bytes_at_start'] = shutil.disk_usage(out).free
            if report['disk_free_bytes_at_start'] < 10 * 1024**3:
                report['status'] = 'BLOCKED'
                raise RuntimeError('Less than 10 GiB available; no physical session started')
            report['console_locked_at_start'] = console_locked()
            if report['console_locked_at_start']:
                report['status'] = 'BLOCKED'
                raise RuntimeError('Console locked; no owner or physical fixture started')
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
            deadline = time.monotonic() + args.timeout
            abort_deadline = None
            next_console_check = 0
            while suite.poll() is None:
                # Reap an owner that closed itself. Otherwise a child verifier
                # observing ps sees our zombie and mistakes it for live native
                # ownership, even though normal shutdown already completed.
                owner.poll()
                reason = None
                if owner.poll() is not None:
                    reason = 'Production owner exited during the supervised session'
                else:
                    rss = subprocess.check_output(['ps', '-p', str(owner.pid), '-o', 'rss='], text=True).strip()
                    if int(rss) > 1536 * 1024:
                        reason = 'Production RSS exceeded the explicit 1536 MiB session bound'
                if time.monotonic() >= deadline:
                    reason = 'Supervised session deadline exceeded'
                if time.monotonic() >= next_console_check:
                    try:
                        if console_locked():
                            reason = 'Console locked during the physical session'
                    except Exception as error:
                        reason = 'Console state could not be verified: ' + str(error)
                    if shutil.disk_usage(out).free < 5 * 1024**3:
                        reason = 'Less than 5 GiB remain for the supervised local session'
                    next_console_check = time.monotonic() + 5
                if reason and abort_deadline is None:
                    report['supervisor_abort'] = reason
                    save(abort_file, {'reason': reason, 'owner_pid': owner.pid})
                    abort_deadline = time.monotonic() + 30
                if abort_deadline is not None and time.monotonic() >= abort_deadline:
                    # A bounded cover must not expire while our capture owner
                    # remains alive. Popen still owns this unreaped child, so
                    # this cannot target a reused PID or a user's production.
                    if owner.poll() is None:
                        report['forced_owner_termination'] = terminate_owned_child(
                            owner, 'Safety abort unacknowledged for 30 seconds', build['binary_sha256'])
                    raise RuntimeError('Safety abort unacknowledged; test owner terminated, fixture cleanup requires inspection')
                time.sleep(.5)
            report['suite_exit'] = suite.returncode
            report['status'] = 'PASS_RUNNER' if report['suite_exit'] == 0 and not report.get('supervisor_abort') else 'FAIL_RUNNER'
        except Exception as error:
            report['error'] = str(error)
        finally:
            if suite and suite.poll() is None:
                if not abort_file.exists():
                    save(abort_file, {'reason':'Supervisor error; stop the owned session', 'owner_pid':owner.pid if owner else None})
                try:
                    suite.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    report['cleanup_errors'].append('Suite still active; fixtures require explicit inspection')
            if (not suite or suite.poll() is not None) and owner and owner.poll() is None and client:
                try:
                    report['shutdown'] = client.call('request_shutdown')['ok']
                    owner.wait(timeout=25)
                except Exception as error:
                    report['cleanup_errors'].append(str(error))
            if owner and owner.poll() is None:
                report['forced_owner_termination'] = terminate_owned_child(
                    owner, 'Normal cleanup did not establish owner exit before cover deadline', build['binary_sha256'])
                report['status'] = 'FAIL_RUNNER'
            report['owner_exit'] = owner.poll() if owner else None
            save(out / 'report.json', report)
    print(json.dumps(report))
    return int(report['status'] != 'PASS_RUNNER' or bool(report['cleanup_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
