#!/usr/bin/env python3
"""One bounded same-binary diagnostic of late UI heartbeat stalls.

Own controlled widget-soak only; one 1s sample after a late 200ms heartbeat gap.
No global settings, debugger connection, browser automation or native changes.
The sampled run does not replace the original performance failure.
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
import supervisor
from h22_process_snapshot import NativeSnapshot

NAME = 'H22-widget-stall-probe-r1'
GENERATION = 910000
BUILD = 'h22-native-multi-widgets3-ephemeral'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default=NAME)
    parser.add_argument('--generation', type=int, default=GENERATION)
    parser.add_argument('--wait-seconds', type=int, default=1800)
    args = parser.parse_args()
    if not re.fullmatch(r'H22-widget-stall-probe-r[1-9][0-9]*', args.name) or not 1 <= args.generation < 2**63 - 32 or not 1 <= args.wait_seconds <= 7200:
        raise ValueError('CLOSED_DIAGNOSTIC_ARGUMENTS')
    output = LAB / 'evidence' / (args.name + '-observer')
    output.mkdir(mode=0o700)
    (output / 'observer-source.py').write_bytes(Path(__file__).read_bytes())
    executable = LAB / '.cache' / BUILD / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'
    expected = json.loads((LAB / 'evidence/H22-native-multi-widgets3-ephemeral-build.json').read_bytes())['binaries'][0]['sha256']
    if hashlib.sha256(executable.read_bytes()).hexdigest() != expected:
        raise ValueError('IMMUTABLE_EXECUTABLE_HASH')
    result = {'scope': 'one diagnostic owned run; no capacity acceptance',
              'native_build_sha256': expected, 'sample_count_limit': 1,
              'sample_duration_seconds': 1, 'sample_command_deadline_seconds': 4,
              'trigger_after_native_seconds': 450, 'trigger_observed_gap_ms': 200,
              'status': 'NO_SAMPLE_TRIGGERED', 'heartbeat_gaps': []}
    active = {}
    stop = threading.Event()

    def observe():
        try:
            snapshot = NativeSnapshot(supervisor)
            owned = None
            private = None
            last_stamp = None
            last_change = time.monotonic()
            last_scan = 0
            sampled = False
            recorded = set()
            first_stamp = None
            while not stop.wait(.05):
                now = time.monotonic()
                if owned is None:
                    root = active.get('root')
                    if root is None or now - last_scan < 1:
                        continue
                    last_scan = now
                    current = snapshot()
                    leader = current.get(root[0])
                    if leader is None or leader.birth != root[1]:
                        continue
                    children = {leader.pid}
                    while True:
                        added = {p.pid for p in current.values() if p.parent in children} - children
                        if not added:
                            break
                        children.update(added)
                    for pid in children:
                        p = current[pid]
                        path = ctypes.create_string_buffer(4096)
                        if supervisor._LIBPROC.proc_pidpath(pid, path, len(path)) > 0 and Path(os.fsdecode(path.value)).resolve() == executable.resolve() and supervisor.birth_identity(pid) == p.birth:
                            owned = p
                            result['owned_host'] = {'pid': pid, 'birth': list(p.birth)}
                            break
                    continue
                if supervisor.birth_identity(owned.pid) != owned.birth:
                    return
                if private is None:
                    matches = list((LAB / '.cache/h19-owned-runs').glob(f'*/fixture/instance-1-g{args.generation}-e1/lifecycle.jsonl'))
                    if len(matches) > 1:
                        raise ValueError('AMBIGUOUS_OWNED_RUN')
                    if not matches:
                        continue
                    private = matches[0].parent.parent
                    result['raw_evidence_root'] = str(private.parent)
                path = private / 'lifecycle.jsonl'
                with path.open('rb') as stream:
                    first = json.loads(stream.readline())
                    stream.seek(max(0, path.stat().st_size - 8192))
                    lines = stream.read(8192).splitlines()
                first_stamp = first['observed_ns']
                heartbeats = []
                for line in lines:
                    try:
                        row = json.loads(line)
                        if row['phase'] == 'ui_heartbeat':
                            heartbeats.append(row['observed_ns'])
                    except (ValueError, KeyError):
                        continue
                if not heartbeats:
                    continue
                stamp = heartbeats[-1]
                if stamp != last_stamp:
                    last_stamp = stamp
                    last_change = now
                    continue
                native_seconds = (stamp - first_stamp) / 1e9
                stale_ms = (now - last_change) * 1000
                if native_seconds < 450 or stale_ms < 200:
                    continue
                if stamp not in recorded and len(result['heartbeat_gaps']) < 1000:
                    recorded.add(stamp)
                    info = supervisor.BsdInfo()
                    count = supervisor._LIBPROC.proc_pidinfo(owned.pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
                    flags = info.prefix[0] if count == ctypes.sizeof(info) else None
                    result['heartbeat_gaps'].append({'last_native_heartbeat_ns': stamp,
                        'native_seconds': native_seconds, 'observer_stale_ms': stale_ms,
                        'proc_bsd_flags': flags,
                        'resource_starvation_throttled': bool(flags & 0x800) if flags is not None else None,
                        'resource_starvation_suspended': bool(flags & 0x1000) if flags is not None else None})
                if sampled:
                    continue
                sampled = True
                if supervisor.birth_identity(owned.pid) != owned.birth:
                    result['status'] = 'IDENTITY_CHANGED_NO_SAMPLE'
                    return
                command = ['/usr/bin/sample', str(owned.pid), '1', '1', '-mayDie', '-file', str(output / 'owned-host.sample.txt')]
                with (output / 'sample-command.log').open('xb') as log:
                    try:
                        sampled_process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=4)
                        result.update(status='SAMPLED' if sampled_process.returncode == 0 else 'SAMPLE_FAILED', sample_returncode=sampled_process.returncode)
                    except subprocess.TimeoutExpired:
                        result['status'] = 'SAMPLE_COMMAND_DEADLINE'
                sample = output / 'owned-host.sample.txt'
                if sample.exists():
                    result['sample_sha256'] = hashlib.sha256(sample.read_bytes()).hexdigest()
        except Exception as error:
            result.update(status='OBSERVER_ERROR', error_type=type(error).__name__, error=str(error))

    worker = threading.Thread(target=observe, daemon=False)
    worker.start()
    command = [sys.executable, str(LAB / 'tools/h22_trial.py'), '--build', BUILD,
               '--name', args.name, '--scenario', 'widget-soak', '--instances', '3',
               '--seconds', '600', '--width', '640', '--height', '360', '--generation', str(args.generation)]
    started = time.monotonic()
    attempts = 0
    try:
        with (output / 'native.log').open('x') as log:
            while True:
                child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                birth = supervisor.birth_identity(child.pid)
                active['root'] = (child.pid, birth)
                code = child.wait()
                active.pop('root', None)
                if code != 75 or time.monotonic() - started >= args.wait_seconds:
                    break
                attempts += 1
                time.sleep(3)
    finally:
        stop.set()
        worker.join(timeout=5)
    if worker.is_alive():
        raise RuntimeError('OBSERVER_NOT_STOPPED')
    result.update(native_returncode=code, slot_busy_attempts=attempts,
                  elapsed_seconds=time.monotonic() - started,
                  limits=['Sampling may change scheduling; no acceptance based on this contrast.',
                          'BSD starvation flags do not measure App Nap or identify a blocking stack.',
                          'Only public process metadata for attribution, then one explicitly owned PID/birth is sampled.',
                          'A non-reproduction does not erase the original 600s failure.'])
    (output / 'observation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
