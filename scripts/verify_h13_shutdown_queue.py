#!/usr/bin/env python3
"""Race a real legacy shutdown with the next queued recording request.

Requires the caller's device/bundle lock and an existing signed, healthy, idle
app with controlled sources. Deliberately exits that app; never launches/builds
one. Run at most twice, relaunching separately between attempts. The sequential
socket worker makes this scheduling-sensitive: EOF is INCONCLUSIVE, not proof
that the command gate ran. No production test hook or artificial delay is used.
"""
import argparse
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / 'target/Motive.app'
SOCKET = ROOT / 'var/run/motive.sock'


def connect(command):
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stream.settimeout(8)
    try:
        stream.connect(str(SOCKET))
        stream.sendall((json.dumps({'origin': 'cli', 'command': command}) + '\n').encode())
        return stream
    except BaseException:
        stream.close()
        raise


def response(stream):
    with stream, stream.makefile('rb') as reader:
        line = reader.readline(1048577)
        if not line:
            return {'transport': 'eof'}
        if len(line) > 1048576 or not line.endswith(b'\n'):
            raise RuntimeError('Invalid or oversized response')
        return json.loads(line)


def call(command):
    return response(connect(command))


def alive(pid):
    try:
        os.kill(pid, 0)
        # A caller may retain the launched child until this verifier returns.
        # An unreaped zombie has exited and owns no multimedia workers.
        status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='],
                                capture_output=True, text=True)
        return status.returncode == 0 and not status.stdout.strip().startswith('Z')
    except ProcessLookupError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--attempt', type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    directory = ROOT / 'var/evidence' / f'h13-shutdown-queue-{time.time_ns()}'
    directory.mkdir(parents=True)
    report = {'attempt': args.attempt, 'result': 'FAIL', 'started_ns': time.time_ns()}
    streams = []
    try:
        common = pathlib.Path(subprocess.check_output(
            ['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        common = common if common.is_absolute() else ROOT / common
        lock = common.resolve().parent / 'var/run/physical-test.lock/OWNER'
        lock_owner = lock.read_text()
        assert 'H13' in lock_owner and str(ROOT) in lock_owner, 'Wrong canonical lock owner'
        report['shared_lock'] = {'path': str(lock), 'owner': lock_owner}
        signed = subprocess.run(['codesign', '--verify', '--verbose=2', str(APP)],
                                capture_output=True, text=True, timeout=30)
        report['codesign'] = {'code': signed.returncode, 'stderr': signed.stderr}
        assert signed.returncode == 0, 'Existing bundle signature must verify'
        # The development bundle has an absolute Frameworks symlink. --strict
        # portability is a separate known limitation, not this lifecycle gate.
        binary = APP / 'Contents/MacOS/motive'
        report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        before = call({'op': 'status'})
        assert before.get('ok') is True, before
        state = report['before'] = before['state']
        pid = state['pid']
        owner = pathlib.Path(subprocess.check_output(
            ['ps', '-p', str(pid), '-o', 'comm='], text=True).strip())
        assert owner.resolve() == binary.resolve(), 'Owner must be this signed bundle'
        assert not state['output_lifecycle']['native_busy'], 'Outputs must be idle'
        assert not state['output_lifecycle']['shutdown_pending'], 'Already shutting down'
        assert not state['issues'] and not state['recovery_required'], 'Healthy production required'
        preflight = report['preflight'] = call({'op': 'preflight_output', 'target': 'recording'})
        assert preflight.get('ok') is True, preflight
        recordings = ROOT / 'var/recordings'
        files_before = set(recordings.glob('*.mkv'))
        assert lock.read_text() == lock_owner, 'Canonical lock changed before shutdown'
        shutdown = connect({'op': 'shutdown'})
        streams.append(shutdown)
        start = connect({'op': 'start_output', 'target': 'recording'})
        streams.append(start)
        stopped = report['shutdown'] = response(shutdown)
        assert stopped.get('ok') is True, stopped
        assert stopped['state']['output_lifecycle']['shutdown_pending'] is True
        try:
            started = response(start)
        except (ConnectionResetError, BrokenPipeError) as error:
            started = {'transport': type(error).__name__}
        report['queued_start'] = started
        if started.get('ok') is True:
            # A failing old build may have opened a native output. Request safe
            # cancellation if it remains reachable; never kill its process.
            try:
                report['failure_cleanup'] = call({'op': 'cancel_all_outputs'})
            except (OSError, ValueError) as error:
                report['failure_cleanup'] = {'transport': str(error)}
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        report['exited'] = not alive(pid)
        assert lock.read_text() == lock_owner, 'Canonical lock changed during shutdown'
        report['new_recordings'] = sorted(str(path) for path in set(recordings.glob('*.mkv')) - files_before)
        assert not report['new_recordings'], 'Queued request created a recording'
        assert report['exited'], 'App did not exit; inspect it without force-killing'
        assert started.get('ok') is not True, 'Queued request started an output after shutdown'
        if 'transport' in started or started.get('error', {}).get('code') == 'TIMEOUT':
            report['result'] = 'INCONCLUSIVE'
            report['reason'] = 'No admission response observed before exit; EOF or control-worker reply timeout is not a gate PASS'
        else:
            assert started.get('error', {}).get('code') == 'SHUTDOWN_PENDING', started
            assert stopped['state']['output_lifecycle']['shutdown_pending'] is True
            for target in ('recording', 'streaming'):
                slot = started['outputs'][target]
                assert not slot['native_busy'], slot
                assert slot['attempt_id'] == state['outputs'][target]['attempt_id'], slot
            report['result'] = 'PASS'
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        for stream in streams:
            stream.close()
        (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'report': str(directory / 'report.json')}))
    return {'PASS': 0, 'INCONCLUSIVE': 2, 'FAIL': 1}[report['result']]


if __name__ == '__main__':
    raise SystemExit(main())
