#!/usr/bin/env python3
"""Build the H21 owned two-window fixture under the canonical physical lock."""
import hashlib
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_h14_collection import lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='H21CaptureFixture')
    args = parser.parse_args()
    if not args.name.isascii() or not args.name.isalnum() or not args.name.startswith('H21CaptureFixture'):
        parser.error('Use an alphanumeric H21CaptureFixture candidate name')
    owner = lock()
    app = ROOT / ('target/' + args.name + '.app')
    if app.exists():
        raise SystemExit('Fixture exists; preserve it and choose a new candidate path before rebuilding')
    binary = app / 'Contents/MacOS/MotiveH21CaptureFixture'
    binary.parent.mkdir(parents=True)
    source = Path(__file__).with_name('h21_capture_app.m')
    source_copy = ROOT / ('target/' + args.name + '-source.m')
    with source_copy.open('xb') as stream:
        stream.write(source.read_bytes())
    command = ['clang', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-fobjc-arc', '-fblocks',
        '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations', '-framework', 'AppKit',
        '-framework', 'CoreGraphics', '-framework', 'AVFoundation', str(source_copy), '-o', str(binary)]
    subprocess.run(command, check=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'local.motive.h21capturefixture', 'CFBundleName': 'Motive H21 Capture Fixture',
        'CFBundleExecutable': binary.name, 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
        'CFBundleShortVersionString': '1.0', 'LSMinimumSystemVersion': '15.0',
        'NSHighResolutionCapable': True, 'LSAppNapIsDisabled': True}))
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    manifest = {'lock': owner, 'argv': command, 'source_path': str(source_copy),
                'source_sha256': hashlib.sha256(source_copy.read_bytes()).hexdigest(),
                'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'scope': 'Producer fixture only; no capture was run.'}
    (ROOT / ('target/' + args.name + '-build.json')).write_text(json.dumps(manifest, indent=2) + '\n')
    print(app)


if __name__ == '__main__':
    main()
