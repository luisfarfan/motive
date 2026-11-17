#!/usr/bin/env python3
"""Run unchanged H1–H10 real suites serially on the same signed H11 bundle.

Caller must already own the shared physical/bundle lock. No signing, settings
changes or public network destinations are performed here.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time

from verify_h10_regressions import ROOT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-id', required=True)
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--group', choices=('all', 'legacy', 'mixer'), default='all')
    parser.add_argument('--suite', action='append', choices=(
        'verify_control.py', 'verify_control_delivery.py', 'verify_h1.py',
        'verify_scenes.py', 'verify.py', 'verify_encoding.py',
        'verify_encoding_fallback.py', 'verify_output_recovery.py',
        'verify_rtmp.py', 'verify_rtmps.py', 'verify_connect_stop.py',
        'verify_vt_stop.py', 'verify_profiles_restart.py', 'verify_h8_lifecycle.py',
        'verify_h8_keychain.py', 'verify_h9_transitions.py', 'verify_h9_faults.py',
        'verify_h10_audio.py', 'verify_h10_mixer.py'),
        help='Run selected unchanged suites, each with its original prerequisites.')
    parser.add_argument('--keep-going', action='store_true',
                        help='Retain every failure and finish independent suites; final exit still fails.')
    args = parser.parse_args()
    run = ROOT/'var/evidence'/('h11-regressions-'+str(time.time_ns()))
    run.mkdir(parents=True)
    app = ROOT/'target/Motive.app/Contents/MacOS/motive'
    report = {'ok': False, 'app_sha256': hashlib.sha256(app.read_bytes()).hexdigest(), 'suites': []}
    try:
        suites = []
        if args.group in ('all', 'legacy'):
            suites.append(('verify_h10_regressions.py', ['--camera-id', args.camera_id,
                                                       '--microphone-id', args.microphone_id], 2400))
        if args.group in ('all', 'mixer'):
            suites.extend((name, ['--microphone-id', args.microphone_id], 360)
                          for name in ('verify_h10_audio.py', 'verify_h10_mixer.py'))
        if args.suite:
            suites = []
            for name in dict.fromkeys(args.suite):
                options = []
                if name in ('verify_h1.py', 'verify_scenes.py', 'verify_h9_transitions.py'):
                    options += ['--camera-id', args.camera_id]
                if name in ('verify_h1.py', 'verify_h10_audio.py', 'verify_h10_mixer.py'):
                    options += ['--microphone-id', args.microphone_id]
                suites.append((name, options, 420))
        for name, options, timeout in suites:
            start = time.monotonic()
            pid = prepare(name, run)
            before = {p: p.stat().st_mtime_ns for p in (ROOT/'var/evidence').glob('*.json')}
            entry = {'suite': name, 'pid': pid, 'reports': {}}
            report['suites'].append(entry)
            with (run/(name+'.log')).open('w') as log:
                result = subprocess.run(['python3', str(ROOT/'scripts'/name), *options],
                                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, timeout=timeout)
            entry.update({'seconds': time.monotonic()-start, 'exit_code': result.returncode})
            for path in (ROOT/'var/evidence').glob('*.json'):
                if before.get(path) != path.stat().st_mtime_ns:
                    contents = path.read_bytes()
                    (run/path.name).write_bytes(contents)
                    entry['reports'][path.name] = hashlib.sha256(contents).hexdigest()
            if name == 'verify_h10_regressions.py':
                candidates = list((ROOT/'var/evidence').glob('h10-regressions-*/manifest.json'))
                if candidates:
                    manifest = max(candidates, key=lambda p: p.stat().st_mtime_ns)
                    entry['legacy_manifest'] = str(manifest)
                    entry['legacy'] = json.loads(manifest.read_text())
            (run/'manifest.json').write_text(json.dumps(report, indent=2))
            print(name, 'exit', result.returncode, 'seconds', round(entry['seconds'], 1), flush=True)
            if not args.keep_going:
                assert result.returncode == 0, f'{name} failed; original evidence retained in {run}'
            assert hashlib.sha256(app.read_bytes()).hexdigest() == report['app_sha256']
        report['ok'] = all(entry['exit_code'] == 0 for entry in report['suites'])
    finally:
        (run/'manifest.json').write_text(json.dumps(report, indent=2))
        print(run/'manifest.json', flush=True)
    assert report['ok'], f'Failures retained in {run}; no acceptance criteria changed'


if __name__ == '__main__':
    main()
