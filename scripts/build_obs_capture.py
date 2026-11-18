#!/usr/bin/env python3
"""Build OBS 33.0.1 mac-capture with SCK diagnostics and strict admission.

Pinned upstream bytes stay untouched; all patched sources/objects live in target.
Diagnostics remain observational. Admission rejects absent/mismatched windows
and failed stream-output registration; buffering, timestamps and active-session
recovery are unchanged.
"""
import hashlib
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
ARCHIVE_SHA = '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b'


def main():
    archive_path = DEPS / 'obs-studio-33.0.1.tar.gz'
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == ARCHIVE_SHA
    plugin_source = SOURCE / 'plugins/mac-capture'
    with tarfile.open(archive_path) as archive:
        for path in plugin_source.iterdir():
            if path.suffix not in ('.m', '.h', '.c'):
                continue
            expected = archive.extractfile('obs-studio-33.0.1/plugins/mac-capture/' + path.name).read()
            assert path.read_bytes() == expected, f'Pinned capture source changed: {path.name}'
    inputs = [pathlib.Path(__file__), PATCH, ADMISSION_PATCH, ADMISSION_OBSERVATION_PATCH,
              ROOT / 'native/sck-diagnostics.h', ROOT / 'native/sck-diagnostics.m']
    stamp = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
    output = BUILD / 'mac-capture.so'
    if output.exists() and (BUILD / 'stamp').exists() and (BUILD / 'stamp').read_text() == stamp:
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    patched = BUILD / 'source'
    if patched.exists():
        shutil.rmtree(patched)
    shutil.copytree(plugin_source, patched)
    subprocess.run(['patch', '-p1', '-i', str(PATCH)], cwd=patched, check=True)
    subprocess.run(['patch', '-p1', '-i', str(ADMISSION_PATCH)], cwd=patched, check=True)
    subprocess.run(['patch', '-p1', '-i', str(ADMISSION_OBSERVATION_PATCH)], cwd=patched, check=True)
    sources = sorted(p for p in patched.iterdir() if p.suffix in ('.m', '.c'))
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
        obj = BUILD / (source.stem + '.o')
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
    (BUILD / 'stamp').write_text(stamp)
    print(output, hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
