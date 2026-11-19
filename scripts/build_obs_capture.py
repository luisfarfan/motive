#!/usr/bin/env python3
"""Build inventoried OBS 33.0.1 mac-capture variants for H20 comparison.

Pinned upstream bytes stay untouched; all patched sources/objects live in target.
Diagnostics remain observational. Admission rejects absent/mismatched targets, invalid geometry
and failed stream-output registration; buffering, timestamps and active-session
recovery are unchanged.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPS = ROOT / '.deps'
SOURCE = DEPS / 'obs-studio-33.0.1'
BUILD = ROOT / 'target/mac-capture-h14'
PATCH = ROOT / 'native/patches/obs-33.0.1-sck-diagnostics.patch'
ADMISSION_PATCH = ROOT / 'native/patches/obs-33.0.1-sck-admission.patch'
ADMISSION_OBSERVATION_PATCH = ROOT / 'native/patches/obs-33.0.1-sck-admission-observation.patch'
GEOMETRY_PATCH = ROOT / 'native/patches/obs-33.0.1-sck-geometry-admission.patch'
MULTIMODE_PATCH = ROOT / 'native/patches/obs-33.0.1-sck-multimode.patch'
ARCHIVE_SHA = '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b'


def variant_patches(variant):
    return {'upstream': [], 'observed': [PATCH],
            'admission': [PATCH, ADMISSION_PATCH, ADMISSION_OBSERVATION_PATCH, GEOMETRY_PATCH],
            'motive': [PATCH, ADMISSION_PATCH, ADMISSION_OBSERVATION_PATCH, GEOMETRY_PATCH, MULTIMODE_PATCH]}[variant]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=['upstream', 'observed', 'admission', 'motive'], default='motive')
    parser.add_argument('--prepare-only', action='store_true', help='Copy/patch and inventory source; do not compile.')
    args = parser.parse_args()
    build = BUILD if args.variant == 'motive' else ROOT / 'target/h20' / ('mac-capture-' + args.variant)
    patches = variant_patches(args.variant)
    archive_path = DEPS / 'obs-studio-33.0.1.tar.gz'
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == ARCHIVE_SHA
    plugin_source = SOURCE / 'plugins/mac-capture'
    with tarfile.open(archive_path) as archive:
        for path in plugin_source.iterdir():
            if path.suffix not in ('.m', '.h', '.c'):
                continue
            expected = archive.extractfile('obs-studio-33.0.1/plugins/mac-capture/' + path.name).read()
            assert path.read_bytes() == expected, f'Pinned capture source changed: {path.name}'
    inputs = [pathlib.Path(__file__), *patches,
              ROOT / 'native/capture-admission.h',
              ROOT / 'native/sck-diagnostics.h', ROOT / 'native/sck-diagnostics.m']
    stamp = hashlib.sha256(args.variant.encode() + b''.join(p.read_bytes() for p in inputs)).hexdigest()
    output = build / 'mac-capture.so'
    manifest_path = build / 'manifest.json'
    if not args.prepare_only and output.exists() and manifest_path.exists() and (build / 'stamp').exists() and (build / 'stamp').read_text() == stamp and json.loads(manifest_path.read_text()).get('module_sha256') == hashlib.sha256(output.read_bytes()).hexdigest():
        return
    build.mkdir(parents=True, exist_ok=True)
    patched = build / 'source'
    if patched.exists():
        shutil.rmtree(patched)
    shutil.copytree(plugin_source, patched)
    for patch in patches:
        subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=patched, check=True)
    manifest = {'version': 1, 'variant': args.variant, 'archive_sha256': ARCHIVE_SHA,
                'input_stamp': stamp, 'built': False, 'physical_result': 'NOT_RUN',
                'patches': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patches},
                'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patched.iterdir() if p.is_file()}}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    if args.prepare_only:
        print(manifest_path)
        return
    sources = sorted(p for p in patched.iterdir() if p.suffix in ('.m', '.c'))
    if args.variant != 'upstream':
        sources.append(ROOT / 'native/sck-diagnostics.m')
    frameworks = DEPS / 'OBS.app/Contents/Frameworks'
    # Upstream also registers legacy sources with APIs obsoleted at deployment
    # 15. Compile its unchanged compatibility paths with OBS's 13.0 minimum;
    # Motive's app still requires 15.0 and only selects ScreenCaptureKit.
    common = ['clang', '-arch', 'arm64', '-mmacosx-version-min=13.0', '-O2', '-g',
              '-Wno-deprecated-declarations', '-Wno-ignored-qualifiers', '-Wno-shorten-64-to-32',
              '-I', str(ROOT / 'native'), '-I', str(patched), '-I', str(SOURCE / 'libobs'),
              '-I', str(DEPS / 'simde-0.8.2')]
    objects = []
    for source in sources:
        obj = build / (source.stem + '.o')
        subprocess.run([*common, '-c', str(source), '-o', str(obj)], check=True)
        objects.append(str(obj))
    command = ['clang', '-arch', 'arm64', '-mmacosx-version-min=13.0', '-bundle', *objects,
               '-F', str(frameworks)]
    for framework in ['libobs', 'AudioUnit', 'Cocoa', 'CoreAudio', 'CoreFoundation',
                      'CoreMedia', 'CoreVideo', 'IOSurface', 'ScreenCaptureKit']:
        command += ['-framework', framework]
    command += ['-Wl,-rpath,' + str(frameworks), '-o', str(output)]
    subprocess.run(command, check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(output)], check=True)
    (build / 'stamp').write_text(stamp)
    manifest.update(built=True, module_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    compiler=subprocess.check_output(['clang', '--version'], text=True),
                    sdk=subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(output, hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
