#!/usr/bin/env python3
"""Assemble a new self-contained ARM64 Motive.app; never replace a running app.

No installer is published and no notarization is implied. This script copies
only the plugins Motive opens and their recursive Mach-O dependencies. Source
and license provenance are recorded separately from runtime verification.
"""
import argparse
import json
import pathlib
import plistlib
import shutil
import subprocess
import tempfile

from portable_support import (PLUGINS, SYSTEM_PREFIXES, audit, fix_rpaths, inside,
                              load_commands, macho, sha256, thin_arm64)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OBS = ROOT / '.deps/OBS.app/Contents'
SDK = ROOT / '.deps/obs-deps-2026-10-23-universal'
PATCHED_PLUGINS = {
    'obs-outputs': ROOT / 'target/obs-outputs-h8/obs-outputs.so',
    'mac-capture': ROOT / 'target/mac-capture-h14/mac-capture.so',
}


def copy_framework_dependency(relative, contents, copied):
    if relative in copied:
        return
    source = OBS / 'Frameworks' / relative
    if not inside(source, OBS / 'Frameworks') or not source.is_file():
        raise RuntimeError(f'Unresolved OBS dependency: {relative}')
    if '.framework/' in relative:
        name = relative.split('/', 1)[0]
        destination = contents / 'Frameworks' / name
        if not destination.exists():
            shutil.copytree(OBS / 'Frameworks' / name, destination, symlinks=True)
    else:
        destination = contents / 'Frameworks' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    copied.add(relative)
    for dependency in load_commands(source)['dependencies']:
        if dependency.startswith(SYSTEM_PREFIXES):
            continue
        if not dependency.startswith('@rpath/'):
            raise RuntimeError(f'Unexpected dependency in {relative}: {dependency}')
        copy_framework_dependency(dependency[7:], contents, copied)


def rust_licenses(destination):
    metadata = json.loads(subprocess.check_output(
        ['cargo', 'metadata', '--locked', '--offline', '--format-version', '1',
         '--filter-platform', 'aarch64-apple-darwin'], cwd=ROOT, text=True))
    nodes = {n['id']: n for n in metadata['resolve']['nodes']}
    selected, pending = set(), [metadata['resolve']['root']]
    while pending:
        package = pending.pop()
        if package in selected:
            continue
        selected.add(package)
        pending.extend(d['pkg'] for d in nodes[package]['deps'])
    records = []
    cached_path = ROOT / 'target/portable-licenses/manifest.json'
    cached = json.loads(cached_path.read_text()) if cached_path.exists() else {'records': []}
    cached = {(p['package'], p['version']): p for p in cached['records']}
    for package in metadata['packages']:
        if package['id'] not in selected:
            continue
        directory = pathlib.Path(package['manifest_path']).parent
        files = set()
        for path in directory.iterdir():
            if path.is_file() and path.name.lower().startswith(('license', 'licence', 'copying', 'notice')):
                files.add(path)
        if package.get('license_file'):
            files.add(directory / package['license_file'])
        target = destination / 'Rust' / f"{package['name']}-{package['version']}"
        target.mkdir(parents=True, exist_ok=True)
        for path in sorted(files):
            if path.is_file():
                shutil.copy2(path, target / path.name)
        upstream = cached.get((package['name'], package['version']))
        cached_files = []
        if not files and upstream:
            for record in upstream['files']:
                path = ROOT / 'target/portable-licenses' / target.name / record['file']
                if sha256(path) != record['sha256']:
                    raise RuntimeError(f'Cached license hash mismatch: {path}')
                shutil.copy2(path, target / path.name)
                cached_files.append(path.name)
        records.append({'name': package['name'], 'version': package['version'],
                        'license': package.get('license'), 'repository': package.get('repository'),
                        'license_files': sorted(p.name for p in files if p.is_file()) + cached_files,
                        'upstream_notice_provenance': upstream if cached_files else None})
    (destination / 'RUST-DEPENDENCIES.json').write_text(json.dumps(records, indent=2) + '\n')
    return [p['name'] for p in records if not p['license_files']]


def add_licenses(contents, copied, require_complete=False):
    notices = contents / 'Resources/ThirdParty'
    notices.mkdir(parents=True)
    shutil.copy2(ROOT / 'LICENSE', notices / 'MOTIVE-LICENSE')
    source = ROOT / '.deps/obs-studio-33.0.1'
    obs_notices = notices / 'OBS'
    obs_notices.mkdir()
    for relative in ['COPYING', 'AUTHORS', 'deps/libcaption/LICENSE.txt',
                     'deps/blake2/LICENSE.blake2', 'deps/json11/LICENSE.txt',
                     'libobs/graphics/libnsgif/LICENSE.libnsgif',
                     'shared/media-playback/LICENSE.media-playback',
                     'plugins/obs-outputs/librtmp/COPYING']:
        target = obs_notices / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    # Includes notices for the statically linked codec dependencies inside the
    # official FFmpeg libraries as well as the visible dynamic-library closure.
    for name in ['FFmpeg', 'x264', 'freetype', 'mbedtls', 'srt', 'librist', 'jansson',
                 'simde', 'aom', 'lame', 'libogg', 'libvorbis', 'libtheora', 'libvpx',
                 'opus', 'libpng']:
        shutil.copytree(SDK / 'licenses' / name, notices / 'OBS-deps' / name)
    cli_source = ROOT / 'target/portable-tools/source'
    (notices / 'FFmpeg-CLI').mkdir()
    for path in cli_source.glob('COPYING*'):
        shutil.copy2(path, notices / 'FFmpeg-CLI' / path.name)
    missing_rust = rust_licenses(notices)
    if require_complete and missing_rust:
        raise RuntimeError('Rust notices remain unresolved: ' + ', '.join(missing_rust))
    provenance = {
        'schema_version': 1,
        'motive_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'motive_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'obs_version': '33.0.1',
        'obs_source_url': 'https://github.com/obsproject/obs-studio/archive/refs/tags/33.0.1.tar.gz',
        'obs_source_sha256': '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b',
        'obs_deps_source': 'https://github.com/obsproject/obs-deps/tree/2026-10-23',
        'ffmpeg_cli': json.loads((ROOT / 'target/portable-tools/manifest.json').read_text()),
        'plugins': list(PLUGINS), 'framework_closure': sorted(copied),
        'patched_modules': {name: {'sha256': sha256(path)} for name, path in PATCHED_PLUGINS.items()},
        'rust_packages_without_top_level_notice': missing_rust,
        'notice_status': 'PARTIAL' if missing_rust else 'PASS',
        'distribution_status': 'NOT_PUBLISHED',
        'source_distribution_gate': 'A complete corresponding-source package must accompany any binary distribution; these URLs and notices alone do not claim that gate passed.',
        'notarization': 'NOT_PERFORMED',
    }
    # Absolute build paths in build manifests are provenance, never loader input.
    (notices / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (notices / 'README.txt').write_text(
        'Motive uses official OBS Studio 33.0.1 libraries and selected plugins.\n'
        'OBS UI, browser/CEF, Qt and updater are not bundled.\n'
        'OBS output lifecycle and capture diagnostics changes are identified in PROVENANCE.json.\n'
        'Motive is GPL-3.0-or-later; bundled components retain their respective licenses.\n'
        'This is a local candidate. Do not distribute without the corresponding-source package,\n'
        'required notices, authorization and completion of the distribution gates.\n')


def sign(contents, identity, hardened):
    # Sign inner Mach-O code, then nested code bundles, then the outer app.
    options = ['--force', '--sign', identity]
    if hardened:
        options += ['--options', 'runtime']
    if identity != '-':
        options += ['--timestamp']
    binaries = [p for p in contents.rglob('*') if macho(p)]
    for path in sorted(binaries, key=lambda p: len(p.parts), reverse=True):
        identifier = ['--identifier', 'local.motive.credentials'] if path == contents / 'MacOS/motive-credentials' else []
        subprocess.run(['codesign', *options, *identifier, str(path)], check=True)
    bundles = [p for p in contents.rglob('*') if p.is_dir() and p.suffix in {'.plugin', '.framework'}]
    for path in sorted(bundles, key=lambda p: len(p.parts), reverse=True):
        subprocess.run(['codesign', *options, str(path)], check=True)
    subprocess.run(['codesign', *options, str(contents.parent)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['debug', 'release'], default='release')
    parser.add_argument('--bundle-version', default='15',
                        help='Numeric local build identity; use a new value for each candidate.')
    parser.add_argument('--skip-build', action='store_true', help='Use existing executable/modules/tools.')
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'target/portable/Motive.app')
    parser.add_argument('--sign-identity', default='-')
    parser.add_argument('--unsigned', action='store_true', help='Stage and inspect only; not runnable acceptance.')
    parser.add_argument('--hardened-runtime', action='store_true')
    parser.add_argument('--require-complete-notices', action='store_true',
                        help='Reject unresolved notices even for local staging; source distribution is a separate gate.')
    args = parser.parse_args()
    if not args.bundle_version or any(not part.isascii() or not part.isdigit()
                                     for part in args.bundle_version.split('.')):
        parser.error('--bundle-version must contain numeric components separated by periods')
    output = args.output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        parser.error('output exists; choose a new output path (no implicit replacement)')
    if output.suffix != '.app':
        parser.error('--output must end in .app')
    if not args.skip_build:
        command = ['cargo', 'build', '--locked']
        if args.profile == 'release':
            command += ['--release']
        subprocess.run(command, cwd=ROOT, check=True)
        subprocess.run(['python3', str(ROOT / 'scripts/build_portable_media_tools.py')], check=True)
        notices = subprocess.run(['python3', str(ROOT / 'scripts/prepare_portable_licenses.py')])
        if notices.returncode not in (0, 1):
            raise SystemExit('License preparation did not produce a bounded result')
    executable = ROOT / f'target/{args.profile}/motive'
    required = [executable, *PATCHED_PLUGINS.values(), ROOT / 'target/portable-tools/manifest.json',
                ROOT / 'target/portable-tools/build/ffmpeg', ROOT / 'target/portable-tools/build/ffprobe']
    for path in required:
        if not path.is_file():
            parser.error(f'missing build input: {path}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.motive-package-', dir=output.parent) as temporary:
        app = pathlib.Path(temporary) / 'Motive.app'
        contents = app / 'Contents'
        for directory in ['MacOS', 'Frameworks', 'PlugIns', 'Resources']:
            (contents / directory).mkdir(parents=True)
        shutil.copy2(executable, contents / 'MacOS/motive')
        shutil.copy2(OBS / 'MacOS/obs-ffmpeg-mux', contents / 'MacOS/obs-ffmpeg-mux')
        for name in ['ffmpeg', 'ffprobe']:
            shutil.copy2(ROOT / 'target/portable-tools/build' / name, contents / 'MacOS' / name)
        subprocess.run(['clang', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-fobjc-arc',
                        '-Wno-deprecated-declarations', '-framework', 'Foundation', '-framework', 'Security',
                        str(ROOT / 'native/credentials_cli.m'), '-o', str(contents / 'MacOS/motive-credentials')], check=True)
        for name in PLUGINS:
            destination = contents / 'PlugIns' / f'{name}.plugin'
            shutil.copytree(OBS / 'PlugIns' / f'{name}.plugin', destination, symlinks=True)
            if name in PATCHED_PLUGINS:
                shutil.copy2(PATCHED_PLUGINS[name], destination / 'Contents/MacOS' / name)
        copied = set()
        copy_framework_dependency('libobs.framework/Versions/A/libobs', contents, copied)
        copy_framework_dependency('libobs-metal.dylib', contents, copied)
        for path in list(contents.rglob('*')):
            if not macho(path):
                continue
            for dependency in load_commands(path)['dependencies']:
                if dependency.startswith(SYSTEM_PREFIXES):
                    continue
                if not dependency.startswith('@rpath/'):
                    raise RuntimeError(f'Unexpected non-system dependency: {path.name}: {dependency}')
                copy_framework_dependency(dependency[7:], contents, copied)
        for path in contents.rglob('*'):
            if path.is_symlink() and (path.readlink().is_absolute() or not inside(path, app)):
                raise RuntimeError(f'External/broken bundle symlink: {path}')
        for path in list(contents.rglob('_CodeSignature')):
            shutil.rmtree(path)
        for path in list(contents.rglob('embedded.provisionprofile')):
            path.unlink()
        for path in contents.rglob('*'):
            if macho(path):
                thin_arm64(path)
                fix_rpaths(path, contents)
        with (contents / 'Info.plist').open('wb') as stream:
            plistlib.dump({
                'CFBundleIdentifier': 'local.motive.studio', 'CFBundleName': 'Motive',
                'CFBundleDisplayName': 'Motive', 'CFBundleExecutable': 'motive',
                'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0',
                'CFBundleVersion': args.bundle_version, 'LSMinimumSystemVersion': '15.0',
                'NSHighResolutionCapable': True, 'LSAppNapIsDisabled': True,
                'NSMicrophoneUsageDescription': 'Motive usa la entrada de audio que eliges para tu producción.',
                'NSCameraUsageDescription': 'Motive usa únicamente la cámara que eliges para tu producción.',
                'NSScreenCaptureUsageDescription': 'Motive captura únicamente la ventana y el audio que eliges.',
            }, stream)
        (contents / 'Resources/MotivePortable.json').write_text(
            json.dumps({'version': 1, 'runtime_layout': 'macos-portable-v1'}) + '\n')
        add_licenses(contents, copied, args.require_complete_notices)
        if not args.unsigned:
            sign(contents, args.sign_identity, args.hardened_runtime)
        result = audit(app, require_signature=not args.unsigned)
        if result['issues']:
            print(json.dumps(result, indent=2))
            raise SystemExit('Portable bundle static audit failed; output was not installed')
        app.rename(output)
    result = audit(output, require_signature=not args.unsigned)
    result['signing_identity_requested'] = args.sign_identity if not args.unsigned else None
    result['runtime_status'] = 'NOT_EVALUATED'
    report = output.parent / (output.stem + '-portable-audit.json')
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'app': str(output), 'audit': str(report), 'static_status': result['static_status']}))


if __name__ == '__main__':
    main()
