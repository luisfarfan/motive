#!/usr/bin/env python3
"""H18 checks: CEF build/static inspection and non-browser execution only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
EVIDENCE = ROOT / 'evidence'
checks = []


def check(name, command, timeout=180):
    r = subprocess.run([str(x) for x in command], cwd=REPO, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), text=True, capture_output=True, timeout=timeout)
    (EVIDENCE / f'H18-current-{name}.log').write_text(r.stdout + r.stderr)
    checks.append({'name': name, 'status': 'PASS' if r.returncode == 0 else 'FAIL', 'command': [str(x) for x in command], 'returncode': r.returncode})
    print(name, checks[-1]['status'], flush=True)
    return r.returncode == 0


def main():
    for name, path in [('rust-contracts', 'poc/browser-host'), ('frame-bridge', 'poc/frame-bridge')]:
        manifest = ROOT / path / 'Cargo.toml'
        check(name, ['cargo', 'test', '--offline', '--locked', '--manifest-path', manifest])
        check(name + '-clippy', ['cargo', 'clippy', '--offline', '--locked', '--manifest-path', manifest, '--all-targets', '--', '-D', 'warnings'])
        check(name + '-fmt', ['cargo', 'fmt', '--manifest-path', manifest, '--', '--check'])
    check('python', [sys.executable, '-m', 'unittest', 'discover', '-s', ROOT / 'tests', '-p', 'test_*.py', '-v'])
    check('node', ['node', '--test', ROOT / 'tests/runtime-interop.test.mjs'])
    check('projection', ['cargo', 'run', '--offline', '--locked', '--manifest-path', ROOT / 'poc/browser-host/Cargo.toml', '--example', 'project_goal'])
    if check('native-build', [sys.executable, ROOT / 'tools/build_native.py', '--build-name', 'h18-native-ephemeral', '--mock-keychain'], timeout=600):
        binary = ROOT / '.cache/frame-bridge-test'
        if check('frame-abi-build', ['clang++', '-std=c++20', '-arch', 'arm64', '-O2', '-Wall', '-Wextra', '-Werror', ROOT / 'tests/frame_bridge.cc', ROOT / 'poc/frame-bridge/target/release/libmotive_frame_bridge.a', '-framework', 'Security', '-framework', 'SystemConfiguration', '-lresolv', '-lpthread', '-o', binary]):
            check('frame-abi', [binary])  # Does not link/load CEF.
    manifest = ROOT / 'poc/frame-bridge/Cargo.toml'
    check('bridge-rust', ['cargo', 'test', '--offline', '--locked', '--manifest-path', manifest, '--features', 'creator-bridge'])
    check('bridge-clippy', ['cargo', 'clippy', '--offline', '--locked', '--manifest-path', manifest, '--features', 'creator-bridge', '--all-targets', '--', '-D', 'warnings'])
    if check('bridge-build', [sys.executable, ROOT / 'tools/build_native.py', '--build-name', 'h18-native-bridge-ephemeral', '--mock-keychain', '--bridge'], timeout=600):
        binary = ROOT / '.cache/native-bridge-policy-test'
        if check('bridge-policy-build', ['clang++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', ROOT / 'tests/native_bridge_policy.cc', ROOT / 'poc/frame-bridge/target/release/libmotive_frame_bridge.a', '-framework', 'Security', '-framework', 'CoreFoundation', '-lresolv', '-lpthread', '-o', binary]):
            check('bridge-policy', [binary])  # No CEF linkage or execution.
    code = {}
    for parent in ('poc', 'tests', 'tools'):
        for p in (ROOT / parent).rglob('*'):
            if p.is_file() and 'target' not in p.parts and '__pycache__' not in p.parts:
                code[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    summary = {'date_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'FAIL', 'checks': checks,
        'native_cef_executed': False, 'cef_onpaint_pixels': 'SEE_SEPARATE_NATIVE_REPORTS', 'native_sandbox': 'BLOCKED', 'production_integrated': False,
        'scope': 'static native CEF build; synthetic frame C ABI; contracts; owned non-browser process supervision', 'implementation_sha256': code}
    (EVIDENCE / 'H18-current-static-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
