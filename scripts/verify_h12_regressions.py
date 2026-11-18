#!/usr/bin/env python3
"""Serial H12 regression manifest on one existing signed bundle.

Own the shared physical/device lock before running. This script never builds,
signs, changes permissions, or uses public destinations. Original suite gates
and timeouts remain intact. --stage overlays is useful after a retained legacy
manifest. Pillow must already exist in var/verify-python (requirements-h11.txt).
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time

from verify_h10_regressions import ROOT, prepare
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-id', required=True)
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--stage', choices=('all', 'legacy', 'overlays'), default='all')
    args = parser.parse_args()
    run = ROOT/'var/evidence'/f'h12-regressions-{time.time_ns()}'
    run.mkdir(parents=True)
    app = VERIFY.app_executable
    report = {'ok': False, 'app_sha256': digest(app), 'suites': [],
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'script_hashes': {p.name: digest(p) for p in (ROOT/'scripts').glob('verify*.py')}}
    suites = []
    if args.stage in ('all', 'legacy'):
        names = ('verify_control.py', 'verify_control_delivery.py', 'verify_h1.py',
                 'verify_scenes.py', 'verify.py', 'verify_encoding.py',
                 'verify_encoding_fallback.py', 'verify_output_recovery.py',
                 'verify_rtmp.py', 'verify_rtmps.py', 'verify_connect_stop.py',
                 'verify_vt_stop.py', 'verify_profiles_restart.py', 'verify_h8_lifecycle.py',
                 'verify_h8_keychain.py', 'verify_h9_transitions.py', 'verify_h9_faults.py',
                 'verify_h10_audio.py', 'verify_h10_mixer.py')
        for name in names:
            options = []
            if name in ('verify_h1.py', 'verify_scenes.py', 'verify_h9_transitions.py'):
                options += ['--camera-id', args.camera_id]
            if name in ('verify_h1.py', 'verify_h10_audio.py', 'verify_h10_mixer.py'):
                options += ['--microphone-id', args.microphone_id]
            suites.append((name, options, 'python3', 420))
    if args.stage in ('all', 'overlays'):
        python = str(ROOT/'var/verify-python/bin/python')
        suites += [('verify_h11_runtime.py', ['--transport', 'both'], python, 900),
                   ('verify_h11_visuals.py', ['--with-video'], python, 900),
                   ('verify_h11_lifecycle.py', [], python, 900)]
    try:
        for name, options, python, timeout in suites:
            assert digest(app) == report['app_sha256'], 'Bundle changed during verification'
            entry = {'suite': name, 'reports': {}}
            report['suites'].append(entry)
            start = time.monotonic()
            before = {p: p.stat().st_mtime_ns for p in (ROOT/'var/evidence').rglob('*.json')}
            # A failed prepare stops this run, rather than interrupting an output
            # or colliding with a previous fixture that did not clean up.
            entry['pid'] = prepare(name, run)
            def encoder(value):
                r = json.loads(subprocess.check_output([str(app), 'ctl', json.dumps({'op':'set_encoder', 'encoder':value})]))
                assert r['ok'], r
            if name == 'verify_h11_visuals.py':
                encoder('x264')
            try:
                with (run/(name+'.log')).open('w') as log:
                    result = subprocess.run([python, str(ROOT/'scripts'/name), *options], cwd=ROOT,
                                            stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                entry['exit_code'] = result.returncode
            except subprocess.TimeoutExpired as error:
                entry.update(exit_code=124, error=str(error))
            finally:
                if name == 'verify_h11_visuals.py':
                    encoder('auto')
                entry['seconds'] = time.monotonic()-start
                for path in (ROOT/'var/evidence').rglob('*.json'):
                    if run in path.parents or path.stat().st_mtime_ns == before.get(path):
                        continue
                    relative = path.relative_to(ROOT/'var/evidence')
                    retained = run/'reports'/relative
                    retained.parent.mkdir(parents=True, exist_ok=True)
                    retained.write_bytes(path.read_bytes())
                    entry['reports'][str(relative)] = digest(retained)
                (run/'manifest.json').write_text(json.dumps(report, indent=2))
            assert digest(app) == report['app_sha256'], 'Bundle changed during verification'
            print(name, entry['exit_code'], round(entry['seconds'], 1), flush=True)
        report['ok'] = all(e.get('exit_code') == 0 for e in report['suites'])
    finally:
        (run/'manifest.json').write_text(json.dumps(report, indent=2))
        print(run/'manifest.json', flush=True)
    assert report['ok'], f'Regression failures retained in {run}'


if __name__ == '__main__':
    main()
