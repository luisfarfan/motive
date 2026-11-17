#!/usr/bin/env python3
"""Build the pinned official obs-outputs module with the H8 lifecycle patch.
No installation or mutation of the downloaded OBS.app/source tree.
"""
import hashlib
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPS = ROOT / '.deps'
SOURCE = DEPS / 'obs-studio-33.0.1'
BUILD = ROOT / 'target/obs-outputs-h8'
SDK = DEPS / 'obs-deps-2026-10-23-universal'
ARCHIVE = DEPS / 'macos-deps-2026-10-23-universal.tar.xz'
SHA256 = '6ded92c5d97f1d1b5effa07be13cc9f539826aa9c65013a15872328e39acffbf'

def main():
    if not ARCHIVE.exists():
        temporary = ARCHIVE.with_suffix('.part')
        urllib.request.urlretrieve('https://github.com/obsproject/obs-deps/releases/download/2026-10-23/' + ARCHIVE.name, temporary)
        temporary.rename(ARCHIVE)
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == SHA256, 'OBS build dependency checksum mismatch'
    source_archive = DEPS / 'obs-studio-33.0.1.tar.gz'
    assert hashlib.sha256(source_archive.read_bytes()).hexdigest() == '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b', 'OBS source checksum mismatch'
    with tarfile.open(source_archive) as archive:
        for name in ['rtmp-stream.c', 'rtmp-stream.h']:
            expected = archive.extractfile('obs-studio-33.0.1/plugins/obs-outputs/' + name).read()
            assert (SOURCE / 'plugins/obs-outputs' / name).read_bytes() == expected, 'Pinned RTMP source was modified'
    if not SDK.exists():
        SDK.mkdir()
        with tarfile.open(ARCHIVE) as archive:
            archive.extractall(SDK, filter='data')
    BUILD.mkdir(parents=True, exist_ok=True)
    stamp = hashlib.sha256(pathlib.Path(__file__).read_bytes() + (ROOT / 'native/patches/obs-33.0.1-rtmp-lifecycle.patch').read_bytes()).hexdigest()
    if (BUILD / 'stamp').exists() and (BUILD / 'stamp').read_text() == stamp and (BUILD / 'obs-outputs.so').exists():
        return
    plugin = BUILD / 'source'
    if plugin.exists():
        shutil.rmtree(plugin)
    shutil.copytree(SOURCE / 'plugins/obs-outputs', plugin)
    subprocess.run(['patch', '-p1', '-i', str(ROOT / 'native/patches/obs-33.0.1-rtmp-lifecycle.patch')], cwd=plugin, check=True)
    files = ['obs-outputs.c', 'flv-mux.c', 'flv-output.c', 'mp4-mux.c', 'mp4-output.c', 'net-if.c', 'null-output.c',
             'rtmp-av1.c', 'rtmp-hevc.c', 'rtmp-stream.c', 'rtmp-windows.c']
    files += ['librtmp/' + x + '.c' for x in ['amf', 'cencode', 'hashswf', 'log', 'md5', 'parseurl', 'rtmp']]
    sources = [plugin / f for f in files] + [SOURCE / 'shared' / f / (f + '.c') for f in ['happy-eyeballs', 'opts-parser', 'bpm']]
    caption_sources = [SOURCE / 'deps/libcaption/src' / (x + '.c') for x in ['caption', 'cea708', 'eia608', 'eia608_charmap', 'eia608_from_utf8', 'mpeg', 'scc', 'srt', 'utf8', 'xds']]
    frameworks = DEPS / 'OBS.app/Contents/Frameworks'
    output = BUILD / 'obs-outputs.so'
    includes = [ROOT / 'native', plugin, SOURCE / 'libobs', SOURCE / 'deps/libcaption', SOURCE / 'deps/libcaption/caption', DEPS / 'simde-0.8.2', SDK / 'include']
    includes += [SOURCE / 'shared' / x for x in ['happy-eyeballs', 'opts-parser', 'bpm']]
    # Match OBS's static caption target: only referenced objects are linked.
    objects = []
    for source in caption_sources:
        obj = BUILD / (source.stem + '.o')
        subprocess.run(['clang', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-O2', '-c', str(source),
                        '-I', str(SOURCE / 'deps/libcaption/caption'), '-o', str(obj)], check=True)
        objects.append(str(obj))
    caption = BUILD / 'libcaption.a'
    caption.unlink(missing_ok=True)
    subprocess.run(['ar', 'rcs', str(caption), *objects], check=True)
    cmd = ['clang', '-arch', 'arm64', '-mmacosx-version-min=15.0', '-O2', '-g', '-bundle', '-DUSE_MBEDTLS', '-DCRYPTO', '-DENABLE_HEVC',
           '-Wno-deprecated-declarations', '-Wno-ignored-qualifiers']
    cmd += [arg for path in includes for arg in ['-I', str(path)]] + list(map(str, sources))
    cmd += ['-F', str(frameworks), '-framework', 'libobs', '-framework', 'Foundation', '-framework', 'Security',
            str(caption), str(SDK / 'lib/libjansson.a'), '-L', str(frameworks), '-lmbedtls', '-lmbedx509', '-lmbedcrypto', '-lz',
            '-Wl,-rpath,' + str(frameworks), '-o', str(output)]
    subprocess.run(cmd, check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(output)], check=True)
    (BUILD / 'stamp').write_text(stamp)
    print(output, hashlib.sha256(output.read_bytes()).hexdigest())

if __name__ == '__main__':
    main()
