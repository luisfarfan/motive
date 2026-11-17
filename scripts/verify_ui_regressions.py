#!/usr/bin/env python3
"""Run the existing real-media suites against the signed native UI bundle.

Reserve var/run/physical-test.lock before running. All reports/media stay in
ignored var/. This does not automate the editor gestures; see the UI QA report.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EXE = VERIFY.client_executable
BUNDLE = VERIFY.app_bundle
OUT = ROOT / 'var/evidence/ui/regressions'


def ctl(op, **args):
    response = json.loads(subprocess.check_output(
        [str(EXE), 'ctl', json.dumps({'op': op, **args})]))
    assert response['ok'], response
    return response


def restart(name):
    state = ctl('status')['state']
    assert state['output'] in ('idle', 'error'), state['output']
    if state['output'] == 'error':
        ctl('recover_output')
    ctl('shutdown')
    deadline = time.monotonic() + 15
    while subprocess.run(['ps', '-p', str(state['pid'])], capture_output=True).returncode == 0:
        assert time.monotonic() < deadline, 'Native owner did not shut down'
        time.sleep(.1)
    subprocess.run(['open', '-n', '--stdout', str(OUT / (name + '-runtime.log')),
                    '--stderr', str(OUT / (name + '-stderr.log')), str(BUNDLE)], check=True)
    deadline = time.monotonic() + 15
    while not (VERIFY.socket).exists():
        assert time.monotonic() < deadline, 'Control socket did not appear'
        time.sleep(.1)
    ctl('status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-id', required=True)
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--from-case', help='Resume at a named case, keeping earlier reports')
    args = parser.parse_args()
    owner = (ROOT / 'var/run/physical-test.lock/OWNER').read_text()
    assert owner.startswith('UI task:'), 'Another task owns the physical test window'
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ('h9-transitions', 'verify_h9_transitions.py', ['--camera-id', args.camera_id], 'h9-transitions.json'),
        ('h9-faults', 'verify_h9_faults.py', [], 'h9-faults.json'),
        ('control', 'verify_control.py', [], 'control-integration.json'),
        ('delivery', 'verify_control_delivery.py', [], 'h9-control-delivery.json'),
        ('h1', 'verify_h1.py', ['--camera-id', args.camera_id, '--microphone-id', args.microphone_id], 'h1-acceptance.json'),
        ('scene-graph', 'verify_scenes.py', ['--camera-id', args.camera_id], 'scene-acceptance.json'),
        ('base', 'verify.py', [], 'acceptance.json'),
        ('encoding', 'verify_encoding.py', ['--seconds', '15', '--rounds', '1'], 'encoding-comparison.json'),
        ('fallback', 'verify_encoding_fallback.py', [], 'encoding-fallback.json'),
        ('recovery', 'verify_output_recovery.py', [], 'output-recovery.json'),
        ('rtmp', 'verify_rtmp.py', [], 'h7-rtmp.json'),
        ('rtmps', 'verify_rtmps.py', [], 'h7-rtmps.json'),
        ('connect-stop', 'verify_connect_stop.py', [], 'h7-connect-stop.json'),
        ('vt-stop', 'verify_vt_stop.py', [], 'h7-vt-stop.json'),
        ('profiles', 'verify_profiles_restart.py', [], 'h7-profiles-restart.json'),
        ('h8-lifecycle', 'verify_h8_lifecycle.py', [], 'h8-lifecycle.json'),
        ('h8-keychain', 'verify_h8_keychain.py', [], 'h8-keychain.json'),
    ]
    digest = hashlib.sha256((BUNDLE / 'Contents/MacOS/motive').read_bytes()).hexdigest()
    manifest = {'bundle_sha256': digest, 'cases': []}
    if args.from_case:
        names = [case[0] for case in cases]
        assert args.from_case in names, 'Unknown case'
        start = names.index(args.from_case)
        previous = json.loads((OUT / 'manifest.json').read_text())
        assert previous['bundle_sha256'] == digest, 'Cannot resume across bundle changes'
        completed = previous['cases'][:start]
        assert [r['name'] for r in completed] == names[:start]
        assert all(r['exit_code'] == 0 and r.get('ok') for r in completed)
        manifest['cases'] = completed
        cases = cases[start:]
    for name, script, script_args, artifact in cases:
        restart(name)
        if name == 'base':
            ctl('set_test_window', open=True)
            time.sleep(.5)
        started = time.monotonic()
        wall_start = time.time()
        print('RUN', name, flush=True)
        with (OUT / (name + '.log')).open('w') as log:
            proc = subprocess.run(['python3', str(ROOT / 'scripts' / script), *script_args],
                                  stdout=log, stderr=subprocess.STDOUT)
        record = {'name': name, 'script': script, 'exit_code': proc.returncode,
                  'seconds': time.monotonic() - started}
        file = ROOT / 'var/evidence' / artifact
        if file.exists() and file.stat().st_mtime >= wall_start:
            shutil.copy2(file, OUT / artifact)
            record.update(artifact=artifact, sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                          ok=json.loads(file.read_text()).get('ok'))
        manifest['cases'].append(record)
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(json.dumps(record), flush=True)
        if proc.returncode:
            raise SystemExit(proc.returncode)
    assert len(manifest['cases']) == 17 and all(r['exit_code'] == 0 and r.get('ok') for r in manifest['cases'])
    print('ALL 17 EXISTING REAL-MEDIA SUITES PASSED', flush=True)


if __name__ == '__main__':
    main()
