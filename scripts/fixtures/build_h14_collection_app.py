#!/usr/bin/env python3
"""Build only the owned H14 collection-behavior experiment; never launch it.

Root must hold the canonical physical lock. Do not build during measurement or
another release build. This does not replace/sign Motive or the H13 fixture.
"""
import argparse
import hashlib
import json
import pathlib
import plistlib
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--sign-identity', default='-')
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    common = pathlib.Path(subprocess.check_output(
        ['git', 'rev-parse', '--git-common-dir'], cwd=root, text=True).strip())
    if not common.is_absolute():
        common = root / common
    lock = common.resolve().parent / 'var/run/physical-test.lock/OWNER'
    if not lock.is_file() or json.loads(lock.read_text())['worktree'] != str(root):
        raise SystemExit('Canonical physical-test lock must belong to this worktree.')
    app = root / 'target/H14CollectionFixture.app'
    executable = app / 'Contents/MacOS/MotiveCollectionFixture'
    if subprocess.run(['pgrep', '-f', re.escape(str(executable))], capture_output=True).returncode == 0:
        raise SystemExit('Close this exact fixture before rebuilding it.')
    source = pathlib.Path(__file__).with_name('h14_collection_app.m')
    executable.parent.mkdir(parents=True, exist_ok=True)
    command = ['clang', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-fobjc-arc', '-fblocks',
               '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
               '-framework', 'AppKit', '-framework', 'CoreGraphics', str(source), '-o', str(executable)]
    subprocess.run(command, check=True)
    with (app / 'Contents/Info.plist').open('wb') as destination:
        plistlib.dump({'CFBundleIdentifier': 'local.motive.collectionfixture',
            'CFBundleName': 'Motive Collection Fixture', 'CFBundleDisplayName': 'Motive Collection Fixture',
            'CFBundleExecutable': executable.name, 'CFBundlePackageType': 'APPL',
            'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
            'LSMinimumSystemVersion': '15.0', 'NSHighResolutionCapable': True,
            'LSAppNapIsDisabled': True}, destination)
    subprocess.run(['codesign', '--force', '--sign', args.sign_identity, str(app)], check=True)
    provenance = {'version': 1, 'source': str(source),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'command': command,
        'binary_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'sdk_path': subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip(),
        'launched': False, 'physical_result': 'NOT_RUN'}
    (root / 'target/h14-collection-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(app)


if __name__ == '__main__':
    main()
