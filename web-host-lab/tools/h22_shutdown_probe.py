#!/usr/bin/env python3
"""One diagnostic Goal lifecycle run; sample only a delayed owned shutdown.

Uses the immutable candidate and canonical physical lock through h22_trial.
No process enumeration, credentials, global changes, or native code changes.
This instrumented contrast cannot replace the original acceptance failure.
"""
import argparse
import ctypes
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / 'poc/browser-host'))
from supervisor import _LIBPROC, birth_identity

NAME = 'H22-goal-shutdown-probe-r1'
GENERATION = 900000
BUILD = 'h22-native-multi-goal-load3-ephemeral'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default=NAME)
    parser.add_argument('--generation', type=int, default=GENERATION)
    parser.add_argument('--wait-seconds', type=int, default=1800)
    args = parser.parse_args()
    if not re.fullmatch(r'H22-goal-shutdown-probe-r[1-9][0-9]*', args.name) or not 1 <= args.generation < 2**63 - 4 or not 1 <= args.wait_seconds <= 7200:
        raise ValueError('CLOSED_DIAGNOSTIC_ARGUMENTS')
    output = LAB / 'evidence' / (args.name + '-observer')
    output.mkdir(mode=0o700)
    (output / 'observer-source.py').write_bytes(Path(__file__).read_bytes())
    cache = LAB / '.cache/h19-owned-runs'
    previous = set(cache.iterdir())
    executable = LAB / '.cache' / BUILD / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'
    expected = json.loads((LAB / 'evidence/H22-native-multi-goal-load3-ephemeral-build.json').read_bytes())['binaries'][0]['sha256']
    if hashlib.sha256(executable.read_bytes()).hexdigest() != expected:
        raise ValueError('IMMUTABLE_EXECUTABLE_HASH')
    stop = threading.Event()
    observation = {'status': 'NOT_TRIGGERED', 'sample_duration_seconds': 1,
                   'sample_interval_ms': 1, 'maximum_sample_command_seconds': 4,
                   'trigger': 'same owned PID/birth remains inside CefShutdown for at least 200 ms',
                   'expected_executable_sha256': expected}

    def observe():
        try:
            while not stop.wait(.1):
                for private in set(cache.iterdir()) - previous:
                    manifest = private / 'fixture/instances.json'
                    trace = private / 'fixture/lifecycle.jsonl'
                    if not manifest.is_file() or not trace.is_file():
                        continue
                    try:
                        data = json.loads(manifest.read_bytes())
                        rows = [json.loads(line) for line in trace.read_bytes().splitlines()]
                    except (OSError, ValueError):
                        continue
                    if data.get('scenario') != 'goal-lifecycle' or not any(
                            x['generation'] == args.generation for x in data.get('instances', [])):
                        continue
                    phases = {x['phase'] for x in rows}
                    if 'shutdown_enter' not in phases:
                        continue
                    observation['raw_evidence_root'] = str(private)
                    if 'shutdown_return' in phases:
                        observation['status'] = 'SHUTDOWN_RETURNED_BEFORE_TRIGGER'
                        return
                    pid = data['host_pid']
                    birth = birth_identity(pid)
                    path = ctypes.create_string_buffer(4096)
                    if birth is None or _LIBPROC.proc_pidpath(pid, path, len(path)) <= 0 or Path(os.fsdecode(path.value)).resolve() != executable.resolve():
                        observation['status'] = 'IDENTITY_UNAVAILABLE_NO_SAMPLE'
                        return
                    if stop.wait(.2):
                        return
                    phases = {json.loads(line)['phase'] for line in trace.read_bytes().splitlines()}
                    if 'shutdown_return' in phases or birth_identity(pid) != birth:
                        observation['status'] = 'SHUTDOWN_RETURNED_BEFORE_TRIGGER'
                        return
                    observation.update(pid=pid, birth=list(birth), status='SAMPLING')
                    command = ['/usr/bin/sample', str(pid), '1', '1', '-mayDie', '-file', str(output / 'owned-host.sample.txt')]
                    with (output / 'sample-command.log').open('xb') as log:
                        try:
                            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=4)
                            observation.update(status='SAMPLED' if result.returncode == 0 else 'SAMPLE_FAILED', sample_returncode=result.returncode)
                        except subprocess.TimeoutExpired:
                            observation['status'] = 'SAMPLE_COMMAND_DEADLINE'
                    observation['same_identity_after_sample'] = birth_identity(pid) == birth
                    sample = output / 'owned-host.sample.txt'
                    if sample.exists():
                        observation['sample_sha256'] = hashlib.sha256(sample.read_bytes()).hexdigest()
                    return
        except Exception as error:
            observation.update(status='OBSERVER_ERROR', error_type=type(error).__name__, error=str(error))

    worker = threading.Thread(target=observe, daemon=False)
    worker.start()
    command = [sys.executable, str(LAB / 'tools/h22_trial.py'), '--build', BUILD,
               '--name', args.name, '--scenario', 'goal-lifecycle', '--instances', '3',
               '--seconds', '45', '--width', '640', '--height', '360', '--generation', str(args.generation)]
    started = time.monotonic()
    attempts = 0
    try:
        with (output / 'native.log').open('x') as log:
            while True:
                code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT)
                if code != 75 or time.monotonic() - started >= args.wait_seconds:
                    break
                attempts += 1
                time.sleep(3)
    finally:
        stop.set()
        worker.join(timeout=5)
    if worker.is_alive():
        raise RuntimeError('OBSERVER_NOT_STOPPED')
    observation.update(native_returncode=code, slot_busy_attempts=attempts,
                       elapsed_seconds=time.monotonic() - started,
                       limits=['Diagnostic contrast only; sampling may change shutdown latency.',
                               'An unsampled fast close does not resolve the original intermittent failure.',
                               'Only this explicitly launched executable and PID/birth can be sampled.'])
    (output / 'observation.json').write_text(json.dumps(observation, indent=2) + '\n')
    print(json.dumps(observation))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
