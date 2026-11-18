#!/usr/bin/env python3
"""Build only FFmpeg's official CLI programs against the pinned OBS libraries.

Build dependencies stay in target/portable-tools; this never installs globally
or alters .deps. The programs and their libraries are copied into the app by
bundle_portable.py. No Homebrew dependency is included.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = '38b88335f99e76ed89ff3c93f877fdefce736c13'
SOURCE_URL = f'https://github.com/FFmpeg/FFmpeg/archive/{COMMIT}.tar.gz'
SOURCE_SHA256 = '2ae7e42343cfffb811d15cfe98b6d005f082595fcdf034d30a4ff90cfed9f9c6'
# This exact FFmpeg commit is pinned by obs-deps tag 2026-10-23,
# deps.ffmpeg/99-ffmpeg.zsh. OBS supplies the already-built shared libraries.
LIBRARIES = {'avutil': 60, 'avcodec': 62, 'avformat': 62, 'avdevice': 62,
             'avfilter': 11, 'swresample': 6, 'swscale': 9}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be 1..16')
    work = ROOT / 'target/portable-tools'
    work.mkdir(parents=True, exist_ok=True)
    archives = work / 'archives'
    archives.mkdir(exist_ok=True)
    archive = archives / f'FFmpeg-{COMMIT}.tar.gz'
    if not archive.exists():
        temporary = archive.with_suffix('.part')
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.rename(archive)
    if digest(archive) != SOURCE_SHA256:
        raise SystemExit('FFmpeg source checksum mismatch')
    source = work / 'source'
    source_stamp = work / 'source.sha256'
    if not source.exists():
        source.mkdir()
        with tarfile.open(archive) as stream:
            for member in stream.getmembers():
                parts = pathlib.PurePosixPath(member.name).parts
                if not parts or parts[0] != f'FFmpeg-{COMMIT}':
                    raise SystemExit('Unexpected FFmpeg archive root')
                if len(parts) == 1:
                    continue
                member.name = str(pathlib.PurePosixPath(*parts[1:]))
                stream.extract(member, source, filter='data')
        source_stamp.write_text(SOURCE_SHA256 + '\n')
    elif not source_stamp.exists() or source_stamp.read_text().strip() != SOURCE_SHA256:
        raise SystemExit(f'Unverified existing source tree: {source}; use a fresh target/portable-tools directory')
    frameworks = ROOT / '.deps/OBS.app/Contents/Frameworks'
    library_hashes = {}
    for name, major in LIBRARIES.items():
        path = frameworks / f'lib{name}.dylib'
        listing = subprocess.check_output(['otool', '-arch', 'arm64', '-L', str(path)], text=True)
        if not re.search(rf'@rpath/lib{name}\.dylib \(compatibility version {major}\.0\.0', listing):
            raise SystemExit(f'Unexpected OBS ABI for {name}')
        library_hashes[name] = digest(path)
    build = work / 'build'
    build.mkdir(exist_ok=True)
    configure = [str(source / 'configure'), '--cc=clang', '--arch=aarch64', '--target-os=darwin',
                 '--disable-autodetect', '--disable-static', '--enable-shared', '--disable-doc',
                 '--disable-ffplay', '--enable-ffmpeg', '--enable-ffprobe', '--disable-network',
                 '--disable-debug', '--enable-rpath', '--install-name-dir=@rpath',
                 '--extra-cflags=-mmacosx-version-min=15.0',
                 '--extra-ldflags=-mmacosx-version-min=15.0 -Wl,-rpath,@executable_path/../Frameworks']
    configuration = {'source': SOURCE_SHA256, 'libraries': library_hashes, 'configure': configure}
    fingerprint = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    stamp = work / 'build.sha256'
    if not (stamp.exists() and stamp.read_text().strip() == fingerprint
            and (build / 'ffmpeg').is_file() and (build / 'ffprobe').is_file()):
        with (work / 'configure.log').open('w') as log:
            subprocess.run(configure, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
        make = ['make', f'-j{args.jobs}']
        for name, major in LIBRARIES.items():
            directory = build / f'lib{name}'
            directory.mkdir(exist_ok=True)
            for filename in [f'lib{name}.dylib', f'lib{name}.{major}.dylib']:
                link = directory / filename
                if link.is_symlink():
                    link.unlink()
                elif link.exists():
                    raise SystemExit(f'Refusing to replace a built library: {link}')
                link.symlink_to((frameworks / f'lib{name}.dylib').resolve())
                # Keep the official Makefile/CLI sources intact. These exact
                # shared-library targets are supplied by the verified OBS bundle.
                make.extend(['-o', f'lib{name}/{filename}'])
        with (work / 'build.log').open('w') as log:
            subprocess.run([*make, 'ffmpeg', 'ffprobe'], cwd=build, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        stamp.write_text(fingerprint + '\n')
    report = {'schema_version': 1, 'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
              'source_commit': COMMIT, 'obs_deps_tag': '2026-10-23',
              'obs_library_sha256': library_hashes, 'configure': configure,
              'tools': {name: {'path': str(build / name), 'sha256': digest(build / name)}
                        for name in ['ffmpeg', 'ffprobe']},
              'note': 'Programs only; shared libraries remain the pinned official OBS binaries.'}
    (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(work / 'manifest.json')


if __name__ == '__main__':
    main()
