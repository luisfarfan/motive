#!/usr/bin/env python3
"""Run a bounded build/test under the repository's canonical physical lock.

Never steals an existing lock. Keeps it after an abnormal child termination so
an operator must check owned descendants before releasing it.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--purpose', required=True)
    parser.add_argument('--owner', default='Motive physical verification')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or args.timeout <= 0:
        parser.error('a command and positive timeout are required')
    root = Path(__file__).resolve().parents[1]
    common = Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=root, text=True).strip())
    if not common.is_absolute():
        common = root / common
    lock = common.resolve().parent / 'var/run/physical-test.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    owner = {'owner': args.owner, 'token': token, 'pid': os.getpid(),
             'worktree': str(root), 'purpose': args.purpose,
             'acquired_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'command': command}
    try:
        lock.mkdir()
    except FileExistsError:
        raise SystemExit('Canonical physical lock occupied; refusing to run: ' + str(lock))
    (lock / 'OWNER').write_text(json.dumps(owner, indent=2) + '\n')
    child = None
    normal = False
    try:
        child = subprocess.Popen(command, cwd=root, start_new_session=True)
        try:
            code = child.wait(timeout=args.timeout)
            # The leader finishing does not prove its process group is gone.
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                normal = True
            # LaunchServices can detach a native owner from this process group.
            # A verifier that cannot prove its cleanup can retain the lease.
            if (lock / 'RETAIN.json').exists():
                normal = False
                raise RuntimeError('Verifier requested lock retention; inspect RETAIN.json and owned processes')
            if not normal:
                raise RuntimeError('Child process group remains; lock retained for inspection')
            return code
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise RuntimeError('Command timed out; lock retained for descendant inspection')
    finally:
        if normal and json.loads((lock / 'OWNER').read_text()).get('token') == token:
            (lock / 'OWNER').unlink()
            lock.rmdir()


if __name__ == '__main__':
    sys.exit(main())
