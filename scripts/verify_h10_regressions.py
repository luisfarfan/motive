#!/usr/bin/env python3
"""Run unchanged H1–H9 real suites serially and retain per-run evidence.
Requires the signed idle bundle and exclusive device/bundle ownership already
coordinated with other worktrees. No fixtures or assertions are substituted.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-id', required=True)
    parser.add_argument('--microphone-id', required=True)
    args = parser.parse_args()
    output = ROOT / 'var/evidence' / f'h10-regressions-{time.time_ns()}'
    output.mkdir(parents=True)
    suites = [
        ('verify_control.py', []),
        ('verify_control_delivery.py', []),
        ('verify_h1.py', ['--camera-id', args.camera_id, '--microphone-id', args.microphone_id]),
        ('verify_scenes.py', ['--camera-id', args.camera_id]),
        ('verify.py', []),
        ('verify_encoding.py', []),
        ('verify_encoding_fallback.py', []),
        ('verify_output_recovery.py', []),
        ('verify_rtmp.py', []),
        ('verify_rtmps.py', []),
        ('verify_connect_stop.py', []),
        ('verify_vt_stop.py', []),
        ('verify_profiles_restart.py', []),
        ('verify_h8_lifecycle.py', []),
        ('verify_h8_keychain.py', []),
        ('verify_h9_transitions.py', ['--camera-id', args.camera_id]),
        ('verify_h9_faults.py', []),
    ]
    app = ROOT / 'target/Motive.app/Contents/MacOS/motive'
    report = {'ok': False, 'app_sha256': hashlib.sha256(app.read_bytes()).hexdigest(), 'suites': []}
    manifest = output / 'manifest.json'
    try:
        for name, options in suites:
            started = time.monotonic()
            before = {p: p.stat().st_mtime_ns for p in (ROOT / 'var/evidence').glob('*.json')}
            with (output / (name + '.log')).open('w') as log:
                result = subprocess.run(['python3', str(ROOT / 'scripts' / name), *options],
                                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            entry = {'suite': name, 'exit_code': result.returncode, 'seconds': time.monotonic()-started, 'reports': {}}
            for path in (ROOT / 'var/evidence').glob('*.json'):
                if before.get(path) != path.stat().st_mtime_ns:
                    contents = path.read_bytes()
                    (output / path.name).write_bytes(contents)
                    entry['reports'][path.name] = hashlib.sha256(contents).hexdigest()
            report['suites'].append(entry)
            manifest.write_text(json.dumps(report, indent=2))
            print(f'{name}: exit {result.returncode}, {entry["seconds"]:.1f}s', flush=True)
            if result.returncode:
                raise RuntimeError(f'{name} failed; evidence retained in {output}')
        assert hashlib.sha256(app.read_bytes()).hexdigest() == report['app_sha256']
        report['ok'] = True
    finally:
        manifest.write_text(json.dumps(report, indent=2))
        print(manifest, flush=True)


if __name__ == '__main__':
    main()
