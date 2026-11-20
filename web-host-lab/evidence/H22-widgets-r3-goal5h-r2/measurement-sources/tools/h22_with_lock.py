#!/usr/bin/env python3
"""Run an authorized local H22 command under Motive's canonical physical slot.

Never remove a foreign lock. Native commands must retain their own external
deadline/RSS supervisor; this wrapper is coordination, not process confinement.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]


def owned_native_processes():
    rows = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True).splitlines()
    found = []
    for row in rows:
        pid, _, command = row.strip().partition(' ')
        # Only executable paths, never shell command text or other app processes.
        if command.startswith(str(REPO.parent / 'motive')) and '/Contents/MacOS/' in command:
            found.append(int(pid))
    return found


def main():
    if len(sys.argv) < 2:
        raise SystemExit('command required')
    common = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=REPO, text=True).strip())
    lock = common.parent / 'var/run/physical-test.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    owner = {'task': 'H22', 'token': token, 'pid': os.getpid(),
             'process_start': subprocess.check_output(['ps', '-p', str(os.getpid()), '-o', 'lstart='], text=True).strip(),
             'worktree': str(REPO), 'started_utc': datetime.now(timezone.utc).isoformat(),
             'bounded_window': 'one command; native runner deadline <=720s per case, RSS <=2048MiB',
             'command': sys.argv[1:]}
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        print('PHYSICAL_SLOT_BUSY: ' + str(lock / 'OWNER'), flush=True)
        return 75
    (lock / 'OWNER').write_text(json.dumps(owner, indent=2) + '\n')
    code = 1
    sleep_guard = None
    try:
        busy = owned_native_processes()
        if busy:
            print('EXISTING_MOTIVE_NATIVE_PROCESSES: ' + str(busy), flush=True)
            return 75
        print('H22_PHYSICAL_SLOT_ACQUIRED ' + token, flush=True)
        # Scoped idle-sleep assertion only; no pmset/global settings, display
        # assertion, lid/forced-sleep override or persistence after this owner.
        sleep_guard = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print('H22_TEMPORARY_IDLE_SLEEP_ASSERTION pid=' + str(sleep_guard.pid), flush=True)
        code = subprocess.call(sys.argv[1:], cwd=REPO)
        return code
    finally:
        if sleep_guard is not None:
            if sleep_guard.poll() is None:sleep_guard.terminate()
            try:sleep_guard.wait(timeout=2)
            except subprocess.TimeoutExpired:sleep_guard.kill();sleep_guard.wait(timeout=2)
            print('H22_IDLE_SLEEP_ASSERTION_RELEASED', flush=True)
        # A failed command does not prove cleanup. Keep ownership if any of this
        # worktree's native app processes survived, and report the exact PIDs.
        rows = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True).splitlines()
        remaining = [int(r.strip().split(' ', 1)[0]) for r in rows
                     if r.strip().split(' ', 1)[-1].lstrip().startswith(str(REPO) + '/')
                     and '/Contents/MacOS/' in r]
        current = json.loads((lock / 'OWNER').read_text())
        if current.get('token') == token and not remaining:
            (lock / 'OWNER').unlink()
            lock.rmdir()
            print('H22_PHYSICAL_SLOT_RELEASED', flush=True)
        else:
            print('PHYSICAL_LOCK_RETAINED_CLEANUP_REQUIRED ' + str(remaining), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
