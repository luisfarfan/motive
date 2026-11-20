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


def is_h19_reproduction_name(name):
    # A fresh, bounded build label never selects a URL, package or Chromium flag.
    # This permits reproduction without replacing any retained build artifact.
    return re.fullmatch(r'h19-native-multi-(?:goal-(?:controls-)?)?repro-[a-z0-9]{1,24}-ephemeral', name) is not None


def is_h22_name(name):
    return re.fullmatch(r'h22-native-multi-(?:goal-(?:controls-)?)?[a-z0-9]{1,24}-ephemeral', name) is not None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--build-name', default='h18-native-ephemeral')
    parser.add_argument('--bridge', action='store_true')
    parser.add_argument('--multi', action='store_true')
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--diagnostic', choices=['static','hidden','slow','crash','slow-consumer'])
    parser.add_argument('--mock-keychain', action='store_true')
    parser.add_argument('--app-sandbox-probe', action='store_true', help='H22-only compatibility diagnostic; never production acceptance')
    parser.add_argument('--widgets', action='store_true', help='H22 original Lower Third and Community Alert web workloads')
    parser.add_argument('--role-probe', action='store_true', help='H22 fixed owned native filesystem/loopback probes after CEF sandbox initialization')
    parser.add_argument('--network-lab', action='store_true', help='H22 owned-only profile: updater disabled, rejecting private proxy and default redacted NetLog; not OS confinement')
    args = parser.parse_args()
    if args.network_lab and (not is_h22_name(args.build_name) or not args.multi or not args.mock_keychain or args.role_probe or args.app_sandbox_probe):
        raise ValueError('H22_NETWORK_LAB_PROFILE')
    if args.role_probe and (not is_h22_name(args.build_name) or not args.multi or not args.mock_keychain or args.bridge or args.widgets or args.app_sandbox_probe):
        raise ValueError('H22_NATIVE_ROLE_PROBE')
    if args.widgets and (not is_h22_name(args.build_name) or not args.multi or args.bridge or args.app_sandbox_probe):
        raise ValueError('H22_WIDGET_PROFILE')
    if args.app_sandbox_probe and (not is_h22_name(args.build_name) or not args.multi or not args.mock_keychain or args.bridge):
        raise ValueError('APP_SANDBOX_H22_MOCK_ONLY')
    diagnostic_modes = {'static':1,'hidden':2,'slow':3,'crash':4,'slow-consumer':5}
    diagnostic_names = {'h18-native-' + mode + '-ephemeral' for mode in diagnostic_modes} | {'h18-native-crash-deferred-ephemeral','h18-native-crash-posix-ephemeral'}
    multi_names = {'h19-native-multi-ephemeral','h19-native-multi-goal-ephemeral','h19-native-multi-goal-controls-ephemeral','h19-native-multi-v2-ephemeral','h19-native-multi-goal-v2-ephemeral','h19-native-multi-v3-ephemeral','h19-native-multi-goal-v3-ephemeral','h19-native-multi-goal-controls-v3-ephemeral','h19-native-multi-final-ephemeral','h19-native-multi-goal-final-ephemeral','h19-native-multi-goal-controls-final-ephemeral','h19-native-multi-goal-hidden-ephemeral'}
    if is_h19_reproduction_name(args.build_name) or is_h22_name(args.build_name):
        multi_names.add(args.build_name)
    if args.multi:
        if args.build_name not in multi_names or args.diagnostic:
            raise ValueError('MULTI_PROFILE_MISMATCH')
        if args.bridge != ('-goal-' in args.build_name) or args.controls != ('-controls-' in args.build_name):
            raise ValueError('MULTI_BRIDGE_PROFILE_MISMATCH')
        report_name = args.build_name.replace('h22-', 'H22-', 1).replace('h19-', 'H19-', 1) + '-build.json'
        if (ROOT / 'evidence' / report_name).exists():
            raise ValueError('H19_BUILD_EVIDENCE_IMMUTABLE_USE_FRESH_REPRO_NAME')
    else:
        if args.diagnostic and (args.bridge or (args.build_name != 'h18-native-' + args.diagnostic + '-ephemeral' and not (args.diagnostic == 'crash' and args.build_name in {'h18-native-crash-deferred-ephemeral','h18-native-crash-posix-ephemeral'}))):
            raise ValueError('DIAGNOSTIC_REQUIRES_FIXED_OWN_BUILD_ROOT')
        if bool(args.diagnostic) != (args.build_name in diagnostic_names):
            raise ValueError('DIAGNOSTIC_PROFILE_MISMATCH')
        if args.controls != (args.build_name == 'h18-native-bridge-controls-ephemeral') or (args.controls and not args.bridge):
            raise ValueError('CONTROLS_REQUIRE_SEPARATE_BRIDGE_PROFILE')
        if args.bridge != args.build_name.startswith('h18-native-bridge'):
            raise ValueError('BUILD_ROOT_AND_BRIDGE_PROFILE_MUST_MATCH')
        if args.bridge and args.build_name not in {'h18-native-bridge','h18-native-bridge-ephemeral','h18-native-bridge-alpha-ephemeral','h18-native-bridge-controls-ephemeral','h18-native-bridge-final-ephemeral'}:
            raise ValueError('BRIDGE_NEEDS_SEPARATE_BUILD_ROOT')
    if args.mock_keychain != args.build_name.endswith('-ephemeral'):
        raise ValueError('EPHEMERAL_PROFILE_AND_KEYCHAIN_BACKEND_MUST_MATCH')
    if not 1 <= args.jobs <= 8:
        raise ValueError('BUILD_JOBS')
    entry = next(e for e in json.loads((ROOT / 'research/sources.lock.json').read_text())['sources'] if e['id'] == 'cef-obs-7871')
    verified = verify_tree(entry, ('include/', 'libcef_dll/', 'Release/', 'CREDITS.html', 'LICENSE.txt'))
    sdk = ROOT / entry['source']
    if args.build_name not in multi_names | diagnostic_names | {'h18-native-diagnostic','h18-native-close-once','h18-native-final-ephemeral','h18-native-bridge','h18-native-ephemeral','h18-native-bridge-ephemeral','h18-native-bridge-alpha-ephemeral','h18-native-bridge-controls-ephemeral','h18-native-bridge-final-ephemeral'}:
        raise ValueError('ISOLATED_BUILD_NAME_REQUIRED')
    build = ROOT / '.cache' / args.build_name
    report_name = (args.build_name.replace('h22-', 'H22-', 1).replace('h19-', 'H19-', 1) if args.multi else 'H18-native-' + args.build_name.removeprefix('h18-native-')) + '-build'
    build.mkdir(parents=True, exist_ok=True)
    compiler = run(['clang++', '--version']).splitlines()[0]
    flags = ['-std=c++20', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-DCEF_API_VERSION=15000', '-DCEF_USE_SANDBOX', '-DNDEBUG', '-O2', '-fno-rtti', '-fno-strict-aliasing', '-fstack-protector-strong', '-I' + str(sdk)]
    if args.multi:
        flags.append('-DMOTIVE_MULTI_BROWSER')
    if args.app_sandbox_probe:
        flags.append('-DMOTIVE_APP_SANDBOX_PROBE')
    if args.widgets:
        flags.append('-DMOTIVE_WIDGET_FIXTURES')
    if args.role_probe:
        flags.append('-DMOTIVE_ROLE_PROBE')
        decoy=build/'h22-owned-decoy';decoy.write_bytes(b'MOTIVE_H22_OWNED_DECOY_NO_SECRET\n');decoy.chmod(0o600)
        (build/'h22_role_probe_config.h').write_text('#define H22_ROLE_DECOY '+json.dumps(str(decoy))+'\n')
    if args.bridge:
        flags.append('-DMOTIVE_GOAL_BRIDGE')
    if args.mock_keychain:
        flags.append('-DMOTIVE_EPHEMERAL_KEYCHAIN')
    if args.network_lab:
        flags.append('-DMOTIVE_H22_NETWORK_LAB')
    if args.controls:
        flags.append('-DMOTIVE_GOAL_CONTROLS')
    if args.diagnostic:
        flags.append('-DMOTIVE_DIAGNOSTIC_MODE=' + str(diagnostic_modes[args.diagnostic]))
    wrapper_flags = [flag for flag in flags if not flag.startswith('-DMOTIVE_')]
    fingerprint = hashlib.sha256(json.dumps([entry['sha256'], compiler, wrapper_flags]).encode()).hexdigest()[:16]
    objects = build / ('wrapper-' + fingerprint)
    if not objects.exists():
        previous = next((p for p in (ROOT / '.cache').glob('h*-native*/wrapper-' + fingerprint) if p != objects and p.is_dir()), objects)
        if previous.is_dir() and previous != objects:
            shutil.copytree(previous, objects)
        else:
            objects.mkdir()
    sources = wrapper_sources(sdk)

    def compile_wrapper(path):
        obj = objects / (str(path.relative_to(sdk)).replace('/', '_') + '.o')
        if not obj.exists():
            run(['clang++', *wrapper_flags, '-DWRAPPING_CEF_SHARED', '-fno-exceptions', '-c', path, '-o', obj])
        return obj

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        object_paths = list(workers.map(compile_wrapper, sources))
    archive = objects / 'libcef_dll_wrapper.a'
    run(['ar', '-rcs', archive, *object_paths])
    run(['cargo', 'build', '--offline', '--locked', '--release', '--manifest-path', ROOT / 'poc/frame-bridge/Cargo.toml', *(['--features','creator-bridge'] if args.bridge else [])])
    # Fixed owned fixtures only. Goal assets go through the existing H16 broker.
    generated = build / 'fixture_assets.hpp'
    rows = ['#pragma once', '#include <map>', '#include <string>', '#include <cstddef>',
            'struct Asset { const unsigned char* bytes; size_t size; const char* mime;' + (' bool widget;' if args.bridge else '') + ' };']
    files = []
    broker_report = None
    if args.bridge:
        sys.path.insert(0, str(ROOT / 'poc/browser-host'))
        from asset_broker import AssetBroker
        directory = ROOT.parent / 'element-lab/web-elements/goal-celebration'
        broker = AssetBroker(directory, 1, 1)
        manifest_bytes = (directory / 'web-element.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        for asset in manifest['assets']:
            resource = broker.request(broker.origin + '/' + asset['path'])
            if resource is None:
                raise ValueError('BROKER_INVENTORY_MISSING')
            files.append(('widget/' + asset['path'], resource.media_type, resource.data, True))
        host = ROOT.parent / 'creator-runtime-lab/binding/web'
        for source, target, mime in [('native-bootstrap.html','index.html','text/html'),('native-bootstrap.mjs','native-bootstrap.mjs','text/javascript'),('native-bootstrap.css','native-bootstrap.css','text/css'),('port-adapter.mjs','port-adapter.mjs','text/javascript')]:
            files.append(('host/' + target, mime, (host / source).read_bytes(), False))
        rows.append('inline constexpr unsigned char GoalManifestJson[]={' + ','.join(str(v) for v in manifest_bytes) + '};')
        rows.append('inline constexpr size_t GoalManifestJsonSize=sizeof(GoalManifestJson);')
        rows.append('inline constexpr char GoalDefinitionHash[]="' + hashlib.sha256(manifest_bytes).hexdigest() + '";')
        broker_report = dict(broker.report)
        broker.close()
    else:
        for name, mime in [('index.html','text/html'),('fixture.css','text/css'),('fixture.js','text/javascript')]:
            source = ROOT / 'poc/fixtures' / ('h19/fixture.js' if args.multi and name == 'fixture.js' else 'diagnostics/' + args.diagnostic + '.js' if args.diagnostic and name == 'fixture.js' else name)
            if args.widgets and name=='fixture.js':source=ROOT/'poc/fixtures/h22/fixture.js'
            files.append((name,mime,source.read_bytes(),False))
    entries = []
    for i, (name, mime, data, widget) in enumerate(files):
        rows.append(f'inline constexpr unsigned char asset{i}[]={{' + ','.join(str(v) for v in data) + '};')
        extra = (',' + str(widget).lower()) if args.bridge else ''
        entries.append(f'{{"motive://i1-g1/{name}",{{asset{i},sizeof(asset{i}),"{mime}"{extra}}}}}')
    rows.append('inline const std::map<std::string,Asset> Assets={' + ','.join(entries) + '};')
    generated.write_text('\n'.join(rows) + '\n')
    inventory = [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'widget': widget} for name,mime,data,widget in files]
    native = ROOT / 'poc/browser-host/native'
    native_flags = [*flags, '-I' + str(build), '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-missing-field-initializers']
    snapshot = build / 'source-snapshot'
    snapshot.mkdir(exist_ok=True)
    source_snapshots = {}
    inputs = list(native.glob('*')) + list((ROOT / 'poc/browser-host/src').glob('*.rs')) + list((ROOT / 'poc/frame-bridge/src').glob('*.rs'))
    inputs += [ROOT / 'tools/build_native.py', ROOT / 'poc/fixtures/h19/fixture.js']
    if args.widgets:inputs.append(ROOT/'poc/fixtures/h22/fixture.js')
    for source in inputs:
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_snapshots[str(relative)] = digest(target)
    shutil.copy2(generated, snapshot / 'fixture_assets.hpp')
    source_snapshots['fixture_assets.hpp'] = digest(snapshot / 'fixture_assets.hpp')
    if args.role_probe:
        shutil.copy2(build/'h22_role_probe_config.h',snapshot/'h22_role_probe_config.h')
        source_snapshots['h22_role_probe_config.h']=digest(snapshot/'h22_role_probe_config.h')
    own_objects = []
    for filename in ['main.mm', 'fixture.mm', 'helper.cc', *(['renderer_bridge.cc'] if args.bridge else ['multi_renderer.cc'] if args.multi else ['diagnostic_renderer.cc'] if args.diagnostic else [])]:
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
    run(['clang++', *own_objects[:2], *own_objects[3:], archive, rust_lib, *link_flags, '-o', executable])
    helper = build / 'helper'
    run(['clang++', own_objects[2], *own_objects[3:], archive, *link_flags, '-o', helper])

    def plist(path, name, identifier):
        path.write_bytes(plistlib.dumps({'CFBundleName': name, 'CFBundleDisplayName': name, 'CFBundleExecutable': name, 'CFBundleIdentifier': identifier, 'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0', 'CFBundleVersion': '18', 'LSMinimumSystemVersion': '15.0', 'LSUIElement': True, 'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication'}))
    bundle_id = 'org.motive.lab.h22.cefsandbox' if args.app_sandbox_probe else 'org.motive.lab.browserfixture'
    plist(contents / 'Info.plist', 'MotiveBrowserFixture', bundle_id)
    binaries = [executable]
    # Suffixes exactly match pinned cef_variables.cmake, including Alerts.
    for suffix, identifier in [('', ''), (' (Alerts)', '.alerts'), (' (GPU)', '.gpu'), (' (Plugin)', '.plugin'), (' (Renderer)', '.renderer')]:
        name = 'MotiveBrowserFixture Helper' + suffix
        dest = frameworks / (name + '.app') / 'Contents'
        (dest / 'MacOS').mkdir(parents=True, exist_ok=True)
        binary = dest / 'MacOS' / name
        shutil.copy2(helper, binary)
        plist(dest / 'Info.plist', name, bundle_id + '.helper' + identifier)
        binaries.append(binary)
    (contents / 'Resources').mkdir(exist_ok=True)
    shutil.copy2(sdk / 'LICENSE.txt', contents / 'Resources/CEF-LICENSE.txt')
    shutil.copy2(sdk / 'CREDITS.html', contents / 'Resources/Chromium-CREDITS.html')
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
    main_entitlements, helper_entitlements = [], []
    if args.app_sandbox_probe:
        for label, values in [('main', {'com.apple.security.app-sandbox': True}),
                              ('helper', {'com.apple.security.app-sandbox': True, 'com.apple.security.inherit': True})]:
            path=build/(label+'.entitlements')
            path.write_bytes(plistlib.dumps(values))
            if label=='main':main_entitlements=['--entitlements',str(path)]
            else:helper_entitlements=['--entitlements',str(path)]
    for helper_app in sorted(frameworks.glob('*Helper*.app')):
        signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', *helper_entitlements, helper_app]))
    signing.append(run(['codesign', '--force', '--sign', '-', '--timestamp=none', *main_entitlements, bundle]))
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
    report = {'status': 'PASS', 'profile': ('owned-multi-goal-controls' if args.controls else 'owned-multi-goal' if args.bridge else 'owned-multi') if args.multi else 'owned-diagnostic-' + args.diagnostic if args.diagnostic else 'owned-goal-controls' if args.controls else 'owned-goal-bridge' if args.bridge else 'owned-smoke', 'diagnostic_profile': args.diagnostic, 'credential_backend': 'chromium-use-mock-keychain' if args.mock_keychain else 'chromium-default', 'native_executed': False, 'native_execution_gate': 'NOT_EVALUATED_CANDIDATE' if args.bridge else 'AUTHORIZED_OWNED_DIAGNOSTIC_NOT_RUN_BY_BUILD', 'sandbox_verified': False, 'bundle_signed_for_distribution': False, 'development_ad_hoc_sealed': True, 'signature_verification': signature_verification, 'pre_sign_framework_sha256': pre_sign_framework_sha256, 'cef': entry, 'verified_upstream_files': verified, 'wrapper_translation_units': len(sources), 'compiler': compiler, 'build_seconds': round(time.monotonic() - started, 3), 'framework_sha256': digest(framework / 'Chromium Embedded Framework'), 'binaries': inspections, 'fixture_inventory': inventory, 'broker_report': broker_report, 'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sorted(native.iterdir()) if p.is_file()}, 'source_snapshot': str(snapshot.relative_to(ROOT)), 'source_snapshot_sha256': source_snapshots, 'frame_bridge_sha256': digest(ROOT / 'poc/frame-bridge/src/lib.rs')}
    report['app_sandbox_probe'] = args.app_sandbox_probe
    report['controlled_widget_fixtures'] = args.widgets
    report['native_role_probe'] = args.role_probe
    report['network_lab'] = args.network_lab
    report['app_sandbox_entitlements'] = ({'main':{'com.apple.security.app-sandbox':True},
        'helpers':{'com.apple.security.app-sandbox':True,'com.apple.security.inherit':True}} if args.app_sandbox_probe else None)
    (ROOT / 'evidence' / (report_name + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'native_executed', 'native_execution_gate', 'verified_upstream_files', 'wrapper_translation_units', 'build_seconds']}))
    print(bundle)


if __name__ == '__main__':
    started = time.monotonic()
    main()
