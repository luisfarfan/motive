#!/usr/bin/env python3
"""Build and statically inspect the pinned CEF fixture. NEVER execute its binary.

No CMake/global installs: compile exactly the macOS source lists in the matching
upstream libcef_dll/CMakeLists.txt, preserving the upstream wrapper unchanged.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fetch_sources import verify_tree


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(json.dumps({'command': [str(a) for a in args], 'returncode': result.returncode, 'output': result.stdout + result.stderr}))
    return result.stdout + result.stderr


def wrapper_sources(sdk):
    text = (sdk / 'libcef_dll/CMakeLists.txt').read_text()
    sources = []
    for name, body in re.findall(r'set\((LIBCEF_[A-Z_]+)\s+(.*?)\n\s*\)', text, re.S):
        if name.endswith(('_LINUX', '_WINDOWS')):
            continue
        for entry in body.split():
            if entry.endswith(('.cc', '.mm', '.c')):
                path = sdk / 'libcef_dll' / entry
                if path not in sources:
                    sources.append(path)
    if not (100 < len(sources) < 500):
        raise ValueError('UPSTREAM_SOURCE_LIST_CHANGED')
    return sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        raise ValueError('BUILD_JOBS')
    entry = next(e for e in json.loads((ROOT / 'research/sources.lock.json').read_text())['sources'] if e['id'] == 'cef-obs-7871')
    verified = verify_tree(entry, ('include/', 'libcef_dll/', 'Release/'))
    sdk = ROOT / entry['source']
    build = ROOT / '.cache/h18-native'
    build.mkdir(parents=True, exist_ok=True)
    compiler = run(['clang++', '--version']).splitlines()[0]
    flags = ['-std=c++20', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-DCEF_API_VERSION=15000', '-DCEF_USE_SANDBOX', '-DNDEBUG', '-O2', '-fno-rtti', '-fno-strict-aliasing', '-fstack-protector-strong', '-I' + str(sdk)]
    fingerprint = hashlib.sha256(json.dumps([entry['sha256'], compiler, flags]).encode()).hexdigest()[:16]
    objects = build / ('wrapper-' + fingerprint)
    objects.mkdir(exist_ok=True)
    sources = wrapper_sources(sdk)

    def compile_wrapper(path):
        obj = objects / (str(path.relative_to(sdk)).replace('/', '_') + '.o')
        if not obj.exists():
            run(['clang++', *flags, '-DWRAPPING_CEF_SHARED', '-fno-exceptions', '-c', path, '-o', obj])
        return obj

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        object_paths = list(workers.map(compile_wrapper, sources))
    archive = objects / 'libcef_dll_wrapper.a'
    run(['ar', '-rcs', archive, *object_paths])
    run(['cargo', 'build', '--offline', '--locked', '--release', '--manifest-path', ROOT / 'poc/frame-bridge/Cargo.toml'])
    # Byte inventory generated from only three reviewed, repository-owned files.
    generated = build / 'fixture_assets.hpp'
    rows = ['#pragma once', '#include <map>', '#include <string>', '#include <cstddef>', 'struct Asset { const unsigned char* bytes; size_t size; const char* mime; };']
    entries = []
    for i, (name, mime) in enumerate([('index.html', 'text/html'), ('fixture.css', 'text/css'), ('fixture.js', 'text/javascript')]):
        data = (ROOT / 'poc/fixtures' / name).read_bytes()
        rows.append(f'inline constexpr unsigned char asset{i}[]={{' + ','.join(str(v) for v in data) + '};')
        entries.append(f'{{"motive://i1-g1/{name}",{{asset{i},sizeof(asset{i}),"{mime}"}}}}')
    rows.append('inline const std::map<std::string,Asset> Assets={' + ','.join(entries) + '};')
    generated.write_text('\n'.join(rows) + '\n')
    native = ROOT / 'poc/browser-host/native'
    native_flags = [*flags, '-I' + str(build), '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-missing-field-initializers']
    own_objects = []
    for filename in ['main.mm', 'fixture.mm', 'helper.cc']:
        obj = build / (filename + '.o')
        run(['clang++', *native_flags, '-c', native / filename, '-o', obj])
        own_objects.append(obj)
    bundle = build / 'MotiveBrowserFixture.app'
    if bundle.is_symlink():
        raise ValueError('GENERATED_BUNDLE_SYMLINK')
    if bundle.exists():
        shutil.rmtree(bundle)
    contents = bundle / 'Contents'
    executable = contents / 'MacOS/MotiveBrowserFixture'
    executable.parent.mkdir(parents=True, exist_ok=True)
    frameworks = contents / 'Frameworks'
    frameworks.mkdir(exist_ok=True)
    framework = frameworks / 'Chromium Embedded Framework.framework'
    if not framework.exists():
        shutil.copytree(sdk / 'Release/Chromium Embedded Framework.framework', framework, symlinks=True)
    link_flags = ['-arch', 'arm64', '-mmacosx-version-min=15.0', '-Wl,-dead_strip', '-framework', 'AppKit', '-framework', 'Cocoa', '-framework', 'IOSurface', '-framework', 'Security', '-framework', 'SystemConfiguration', '-lresolv', '-lpthread']
    rust_lib = ROOT / 'poc/frame-bridge/target/release/libmotive_frame_bridge.a'
    run(['clang++', *own_objects[:2], archive, rust_lib, *link_flags, '-o', executable])
    helper = build / 'helper'
    run(['clang++', own_objects[2], archive, *link_flags, '-o', helper])

    def plist(path, name, identifier):
        path.write_bytes(plistlib.dumps({'CFBundleName': name, 'CFBundleDisplayName': name, 'CFBundleExecutable': name, 'CFBundleIdentifier': identifier, 'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0', 'CFBundleVersion': '18', 'LSMinimumSystemVersion': '15.0', 'LSUIElement': True, 'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication'}))
    plist(contents / 'Info.plist', 'MotiveBrowserFixture', 'org.motive.lab.browserfixture')
    binaries = [executable]
    # Suffixes exactly match pinned cef_variables.cmake, including Alerts.
    for suffix, identifier in [('', ''), (' (Alerts)', '.alerts'), (' (GPU)', '.gpu'), (' (Plugin)', '.plugin'), (' (Renderer)', '.renderer')]:
        name = 'MotiveBrowserFixture Helper' + suffix
        dest = frameworks / (name + '.app') / 'Contents'
        (dest / 'MacOS').mkdir(parents=True, exist_ok=True)
        binary = dest / 'MacOS' / name
        shutil.copy2(helper, binary)
        plist(dest / 'Info.plist', name, 'org.motive.lab.browserfixture.helper' + identifier)
        binaries.append(binary)
    (contents / 'Resources').mkdir(exist_ok=True)
    shutil.copy2(sdk / 'LICENSE.txt', contents / 'Resources/CEF-LICENSE.txt')
    # Require the copied framework to remain byte/symlink-identical to its pin.
    original_framework = sdk / 'Release/Chromium Embedded Framework.framework'
    expected_paths = {p.relative_to(original_framework) for p in original_framework.rglob('*')}
    if expected_paths != {p.relative_to(framework) for p in framework.rglob('*')}:
        raise ValueError('BUNDLE_FRAMEWORK_INVENTORY')
    for relative in expected_paths:
        original, copied = original_framework / relative, framework / relative
        if original.is_symlink():
            if not copied.is_symlink() or os.readlink(original) != os.readlink(copied):
                raise ValueError('BUNDLE_FRAMEWORK_SYMLINK')
        elif original.is_file() and (copied.is_symlink() or digest(original) != digest(copied)):
            raise ValueError('BUNDLE_FRAMEWORK_HASH')
    pre_sign_framework_sha256 = digest(framework / 'Chromium Embedded Framework')
    # Local ad-hoc development seals only. No identity lookup, Keychain changes,
    # entitlements, hardened-runtime claim or modification of the pinned SDK.
    signing = []
    for dylib in sorted(framework.rglob('*.dylib')):
        if not dylib.is_symlink():
            signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', dylib]))
    signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', framework]))
    for helper_app in sorted(frameworks.glob('*Helper*.app')):
        signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', helper_app]))
    signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', bundle]))
    signature_verification = run(['codesign', '--verify', '--strict', '--deep', bundle])
    inspections = []
    for i, binary in enumerate(binaries):
        # Apple's otool-classic treats parentheses in role names as archive
        # syntax. Inspect a byte-identical, safely named local copy instead.
        inspection_copy = build / f'inspect-{i}'
        shutil.copy2(binary, inspection_copy)
        assert digest(binary) == digest(inspection_copy)
        inspections.append({'path': str(binary.relative_to(ROOT)), 'sha256': digest(binary), 'file': run(['file', binary]).strip(), 'dependencies': run(['otool', '-L', inspection_copy]), 'dependency_inspection_sha256': digest(inspection_copy), 'code_signature': run(['codesign', '-dvv', binary])})
    # No executable is loaded to inspect its architecture or linkage.
    report = {'status': 'PASS', 'native_executed': False, 'native_execution_gate': 'BLOCKED', 'sandbox_verified': False, 'bundle_signed_for_distribution': False, 'development_ad_hoc_sealed': True, 'signature_verification': signature_verification, 'pre_sign_framework_sha256': pre_sign_framework_sha256, 'cef': entry, 'verified_upstream_files': verified, 'wrapper_translation_units': len(sources), 'compiler': compiler, 'build_seconds': round(time.monotonic() - started, 3), 'framework_sha256': digest(framework / 'Chromium Embedded Framework'), 'binaries': inspections, 'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sorted(native.iterdir()) if p.is_file()}, 'frame_bridge_sha256': digest(ROOT / 'poc/frame-bridge/src/lib.rs')}
    (ROOT / 'evidence/H18-native-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'native_executed', 'native_execution_gate', 'verified_upstream_files', 'wrapper_translation_units', 'build_seconds']}))
    print(bundle)


if __name__ == '__main__':
    started = time.monotonic()
    main()
