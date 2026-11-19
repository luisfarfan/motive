#!/usr/bin/env python3
"""One bounded A→B→A with independent AppKit focus and decoded owned-window pixels.

Requires the canonical lock, a portable app, and prebuilt owned fixture/probe.
Launches fresh processes; never loads stores, physical devices or external RTMP.
LaunchServices activation is a request only: two uncorroborated attempts stop
this test with HUMAN_ACTION_REQUIRED. No CUA, AX, global preferences or TCC edits.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from h15_focus import corroborate, fixture_at_probe_end
from verify_h14_collection import (Client, ROOT, default_owner, digest, executable,
                                  lines, lock, process_identity, require, save)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arm', choices=('default', 'join-all'), default='default')
    parser.add_argument('--unobserved-upstream', action='store_true',
                        help='H20 only: verified unmodified OBS module; SCK internals remain unobserved.')
    args = parser.parse_args()
    lock()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    app = args.app.resolve(strict=True)
    require((app / 'Contents/Resources/MotivePortable.json').is_file(), 'Portable app required')
    owner_binary = executable(app, 'local.motive.studio')
    fixture_app = ROOT / 'target/H14CollectionFixture.app'
    fixture_binary = executable(fixture_app, 'local.motive.collectionfixture')
    probe = ROOT / 'target/MotiveFocusProbe'
    report = {'status': 'BLOCKED', 'app': str(app), 'binary_sha256': digest(owner_binary),
              'focus_probe_sha256': digest(probe), 'system_observations': [],
              'markers': [], 'cleanup_errors': [], 'proves_full_output_delivery': False}
    handles = []
    owner = fixture = trial = control = None
    env = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
    env['PATH'] = '/usr/bin:/bin'

    def launch(binary, arguments, stem):
        stdout = (out / (stem + '.jsonl')).open('x')
        stderr = (out / (stem + '.stderr')).open('x')
        handles.extend([stdout, stderr])
        return subprocess.Popen([str(binary), *arguments], cwd='/', env=env, stdout=stdout, stderr=stderr)

    def checkpoint():
        save(out / 'report.json', report)

    try:
        # Do not attach to or replace a user's existing production.
        socket = Path.home() / 'Library/Application Support/local.motive.studio/run/motive.sock'
        require(not socket.exists(), 'Existing control socket: owner must be closed normally first')
        owner = launch(owner_binary, [], 'owner')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                control = Client(app, owner.pid, out)
                initial = control.state()
                default_owner(initial)
                break
            except (OSError, ValueError):
                require(owner.poll() is None, 'Owner exited during startup')
                time.sleep(.1)
        else:
            raise ValueError('Owner startup timeout')
        report['owner'] = process_identity(owner.pid, owner_binary)
        fixture = launch(fixture_binary, ['--collection-arm', args.arm], 'fixture')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            events = lines(out / 'fixture.jsonl')
            ready = next((e for e in events if e['event'] == 'ready'), None)
            states = [e for e in events if e['event'] == 'window_state']
            if ready and states and isinstance(states[-1].get('cg_own_window_metadata'), dict):
                break
            require(fixture.poll() is None, 'Fixture exited during startup')
            time.sleep(.1)
        require(ready is not None, 'Fixture ready timeout')
        window = ready['window_id']
        report['fixture'] = process_identity(fixture.pid, fixture_binary)
        manifest = {'version': 1, 'trial_id': 'h15-focus', 'arm': args.arm, 'seconds': 45,
                    'owner': {'bundle': str(app), 'pid': owner.pid},
                    'fixture': {'bundle': str(fixture_app), 'pid': fixture.pid, 'window_id': window,
                                'log': str(out / 'fixture.jsonl'),
                                'build_manifest': str(ROOT / 'target/h14-collection-build.json')},
                    'markers': str(out / 'markers.jsonl'),
                    'receiver_ffmpeg': str(app / 'Contents/MacOS/ffmpeg')}
        save(out / 'manifest.json', manifest)
        trial_log = (out / 'trial.stdout').open('x')
        handles.append(trial_log)
        trial = subprocess.Popen([sys.executable, str(ROOT / 'scripts/verify_h14_collection.py'),
                                  'run', '--lock-held', '--manifest', str(out / 'manifest.json'),
                                  '--output', str(out / 'capture'),
                                  *(['--unobserved-upstream'] if args.unobserved_upstream else [])],
                                 stdout=trial_log, stderr=trial_log)
        deadline = time.monotonic() + 20
        while 'awaiting_fixture_front_marker' not in (out / 'trial.stdout').read_text():
            require(trial.poll() is None and time.monotonic() < deadline, 'Capture preparation failed')
            time.sleep(.1)

        def observe(phase, expected):
            value = json.loads(subprocess.check_output([str(probe), str(expected), str(window)], text=True))
            own = fixture_at_probe_end(value, lines(out / 'fixture.jsonl'))
            assessment = corroborate(value, own, fixture_pid=fixture.pid, window_id=window, expected_pid=expected)
            row = {'phase': phase, 'host_monotonic': time.monotonic(), 'probe': value,
                   'fixture': own, 'assessment': assessment}
            report['system_observations'].append(row)
            checkpoint()
            return row

        phases = [('fixture_front', fixture.pid, fixture_app), ('studio_front', owner.pid, app),
                  ('fixture_return', fixture.pid, fixture_app)]
        started = None
        for index, (phase, expected, bundle) in enumerate(phases):
            if started is not None:
                prior_phase, prior_pid, _ = phases[index-1]
                while time.monotonic() < started + index * 15:
                    require(trial.poll() is None, 'Capture exited before focus transition')
                    observe(prior_phase, prior_pid)
                    time.sleep(.5)
            for attempt in range(2):
                subprocess.run(['/usr/bin/open', '-a', str(bundle)], check=True)
                time.sleep(1.5)
                row = observe(phase, expected)
                if row['assessment']['status'] == 'PASS':
                    break
            else:
                report['reason'] = 'HUMAN_ACTION_REQUIRED'
                raise ValueError('Focus request uncorroborated after two attempts')
            save(out / (phase + '-probe.json'), row['probe'])
            subprocess.run([sys.executable, str(ROOT / 'scripts/verify_h14_collection.py'), 'mark',
                            '--lock-held', '--manifest', str(out / 'manifest.json'), '--phase', phase,
                            '--system-probe', str(out / (phase + '-probe.json')),
                            '--note', 'Independent system PID plus contemporaneous fixture active/key'],
                           check=True, stdout=subprocess.DEVNULL)
            report['markers'] = lines(out / 'markers.jsonl')
            started = report['markers'][0]['host_monotonic']
        while time.monotonic() < started + 45 and trial.poll() is None:
            observe('fixture_return', fixture.pid)
            time.sleep(.5)
        report['capture_exit'] = trial.wait(timeout=25)
        # Independent system PID evidence must cover the interior of every phase.
        boundaries = [m['host_monotonic'] for m in report['markers']] + [started+45]
        coverage = {}
        for i, (phase, _, _) in enumerate(phases):
            rows = [r for r in report['system_observations']
                    if boundaries[i]+2 <= r['host_monotonic'] <= boundaries[i+1]-2]
            span = rows[-1]['host_monotonic']-rows[0]['host_monotonic'] if rows else 0
            gap = max((b['host_monotonic']-a['host_monotonic'] for a, b in zip(rows, rows[1:])), default=0)
            coverage[phase] = {'status': 'PASS' if len(rows) >= 3 and span >= 5 and gap <= 2.5
                              and all(r['assessment']['status'] == 'PASS' for r in rows) else 'BLOCKED',
                              'samples': len(rows), 'span_s': span, 'max_gap_s': gap}
        report['focus_coverage'] = coverage
        report['status'] = 'PARTIAL' if all(r['status'] == 'PASS' for r in coverage.values()) else 'BLOCKED'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    finally:
        # The bounded child owns output cleanup; never kill it or the native owner.
        if trial and trial.poll() is None:
            try:
                report['capture_exit'] = trial.wait(timeout=75)
            except subprocess.TimeoutExpired:
                report['cleanup_errors'].append('Capture still active; owner retained for recovery')
        if owner and control and (trial is None or trial.poll() is not None):
            try:
                reply = control.call('request_shutdown')
                report['shutdown_ok'] = reply['ok']
                owner.wait(timeout=20)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                report['cleanup_errors'].append(str(error))
        if fixture and fixture.poll() is None and owner and owner.poll() is not None:
            fixture.terminate()
            fixture.wait(timeout=8)
        report['owner_exit'] = owner.poll() if owner else None
        report['fixture_exit'] = fixture.poll() if fixture else None
        checkpoint()
        for handle in handles:
            handle.close()
    print(json.dumps({'output': str(out), 'status': report['status'], 'cleanup_errors': report['cleanup_errors']}))
    return int(bool(report['cleanup_errors'] or report.get('error')))


if __name__ == '__main__':
    raise SystemExit(main())
