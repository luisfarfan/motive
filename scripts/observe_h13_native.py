#!/usr/bin/env python3
"""Read-only CLI/MCP evidence while a person/CUA operates the native studio.

Requires the canonical physical lock and an existing signed app. Never starts
outputs, changes production, launches devices or drives UI. Write STOP inside
the printed evidence directory to end observation; that does not stop Motive.
This collector is evidence, not an automatic declaration of acceptance.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time

from h7_support import Client, EXE, ROOT, process_sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=3600)
    parser.add_argument('--allow-shutdown', action='store_true')
    args = parser.parse_args()
    assert 1 <= args.seconds <= 7200
    common = pathlib.Path(subprocess.check_output(
        ['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
    if not common.is_absolute():
        common = ROOT/common
    owner = (common.resolve().parent/'var/run/physical-test.lock/OWNER').read_text()
    assert 'H13' in owner and str(ROOT) in owner
    directory = ROOT/'var/evidence'/f'h13-native-{time.time_ns()}'
    directory.mkdir()
    print(directory, flush=True)
    report = dict(collector_ok=False, acceptance='not evaluated by collector',
                  directory=str(directory), actions=[], attempts={}, samples=0,
                  shared_lock_owner=owner)
    binary = ROOT/'target/Motive.app/Contents/MacOS/motive'
    report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    signature = subprocess.run(['codesign', '--verify', str(binary.parents[2])],
                               capture_output=True, text=True)
    assert signature.returncode == 0, signature.stderr
    client = Client()
    state = None
    try:
        start = time.monotonic()
        last_action = None
        last_cli = 0
        previous_cpu = None
        previous_time = None
        with (directory/'observations.jsonl').open('w') as stream:
            while time.monotonic()-start < args.seconds and not (directory/'STOP').exists():
                try:
                    current = client.state()
                except BaseException:
                    if (args.allow_shutdown and state and
                            state['output_lifecycle']['shutdown_pending']):
                        report['observed_shutdown'] = True
                        break
                    raise
                now = time.monotonic()
                if state is None:
                    report['initial'] = current
                    report['pid'] = current['pid']
                assert current['pid'] == report['pid'], 'Production process changed'
                cpu, rss = process_sample(current['pid'])
                row = dict(monotonic=now, elapsed=now-start, state=current, rss_mib=rss,
                           cpu_percent=None if previous_cpu is None else
                           100*(cpu-previous_cpu)/(now-previous_time))
                previous_cpu, previous_time = cpu, now
                action = current['last_action']
                if action != last_action:
                    report['actions'].append(dict(elapsed=now-start,
                        revision=current['revision'], action=action))
                    last_action = action
                for target, slot in current['outputs'].items():
                    if slot['attempt_id'] is not None:
                        report['attempts'][f"{target}:{slot['attempt_id']}"] = slot
                if now-last_cli >= 10:
                    cli = json.loads(subprocess.check_output(
                        [str(EXE), 'ctl', '{"op":"outputs"}'], timeout=10))
                    assert cli['ok'] and cli['pid'] == current['pid']
                    row['cli_outputs'] = cli
                    last_cli = now
                stream.write(json.dumps(row, separators=(',', ':'))+'\n')
                stream.flush()
                state = current
                report['samples'] += 1
                report['last'] = current
                (directory/'report.json').write_text(json.dumps(report, indent=2))
                # Avoid retaining the entire MCP transcript twice in memory.
                client.ops.clear()
                time.sleep(.5)
        report['collector_ok'] = True
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['finished_monotonic'] = time.monotonic()
        (directory/'report.json').write_text(json.dumps(report, indent=2))
        client.close()
        print(directory/'report.json', flush=True)


if __name__ == '__main__':
    main()
