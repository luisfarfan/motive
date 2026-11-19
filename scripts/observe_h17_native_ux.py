#!/usr/bin/env python3
"""Read-only evidence companion for actual GPUI gestures on an owned portable.

Run inside h15_run_owned. The reviewer creates FINISH only after the UI work.
No command in this observer changes Production, stores, focus or permissions.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from verify_h14_collection import Client, default_owner, digest, lock, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1500)
    args = parser.parse_args()
    assert 30 <= args.seconds <= 1600
    owner_lock = lock()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    app = Path(os.environ['MOTIVE_TEST_APP']).resolve(strict=True)
    # The first read is observational; Client binds and checks the local peer.
    import socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(Path(os.environ['MOTIVE_TEST_DATA_ROOT']) / 'run/motive.sock'))
        pid = sock.getsockopt(0, 2)  # macOS SOL_LOCAL / LOCAL_PEERPID
    finally:
        sock.close()
    client = Client(app, pid, out)
    initial = client.state()
    default_owner(initial)
    save(out / 'ready.json', {'pid': pid, 'binary_sha256': digest(app / 'Contents/MacOS/motive'),
                             'lock': owner_lock, 'initial': initial})
    print('READY_FOR_NATIVE_UI', pid, flush=True)
    previous = None
    state = initial
    observed_exit = False
    deadline = time.monotonic() + args.seconds
    with (out / 'changes.jsonl').open('x') as events:
        while time.monotonic() < deadline and not (out / 'FINISH').exists():
            assert lock() == owner_lock, 'Canonical owner changed'
            try:
                state = client.state()
            except (OSError, ValueError):
                # EXPECT_CLOSE declares the forthcoming real UI gesture. A
                # failed socket alone never proves that the owner terminated.
                if (out / 'EXPECT_CLOSE').exists():
                    reap_deadline = time.monotonic() + 1
                    while time.monotonic() < reap_deadline:
                        exited = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='],
                                                capture_output=True, text=True, timeout=5)
                        if exited.returncode == 1 and not exited.stdout.strip():
                            observed_exit = True
                            break
                        time.sleep(.05)
                    if observed_exit:
                        break
                raise
            assert state['pid'] == pid
            # Preserve real state only when behavior/receipts change, not every meter tick.
            key = json.dumps([state.get(k) for k in ('revision', 'last_action')]
                + [[v.get('phase') for v in state['outputs'].values()]]
                + [state.get('show_control', {}).get('last_save'),
                   state.get('show_control', {}).get('last_save_error')], sort_keys=True)
            if key != previous:
                events.write(json.dumps({'monotonic': time.monotonic(), 'state': state}) + '\n')
                events.flush()
                previous = key
            save(out / 'latest.json', state)
            time.sleep(.5)
    final = state if observed_exit else client.state()
    save(out / 'observer-report.json', {'status': 'PASS' if observed_exit or (out / 'FINISH').exists() else 'PARTIAL',
        'scope': 'read-only observer completion, not UX acceptance', 'pid': pid,
        'observed_owner_exit': observed_exit, 'final_observation': final})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
