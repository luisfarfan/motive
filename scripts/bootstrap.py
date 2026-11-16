#!/usr/bin/env python3
"""Download complete, pinned OBS development artifacts into this checkout."""
import hashlib
import json
import pathlib
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPS = ROOT / '.deps'
VERSION = '33.0.1'
ARTIFACTS = [
    ('OBS-Studio-33.0.1-macOS-Apple.dmg',
     'https://github.com/obsproject/obs-studio/releases/download/33.0.1/OBS-Studio-33.0.1-macOS-Apple.dmg',
     '3d6b2eedeb56416602af635adaba32327fdf11ff9d2806a4ce7d5b608de73238'),
    ('obs-studio-33.0.1.tar.gz',
     'https://github.com/obsproject/obs-studio/archive/refs/tags/33.0.1.tar.gz',
     '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b'),
    ('simde-0.8.2.tar.gz',
     'https://github.com/simd-everywhere/simde/archive/refs/tags/v0.8.2.tar.gz',
     'ed2a3268658f2f2a9b5367628a85ccd4cf9516460ed8604eed369653d49b25fb'),
]

def main():
    DEPS.mkdir(exist_ok=True)
    for name, url, expected in ARTIFACTS:
        path = DEPS / name
        if not path.exists():
            temp = path.with_suffix(path.suffix + '.part')
            print('Downloading', url, flush=True)
            urllib.request.urlretrieve(url, temp)
            temp.rename(path)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f'Checksum mismatch: {path}; expected {expected}, got {actual}')
    if not (DEPS / f'obs-studio-{VERSION}').exists():
        with tarfile.open(DEPS / ARTIFACTS[1][0]) as archive:
            archive.extractall(DEPS, filter='data')
    if not (DEPS / 'simde-0.8.2').exists():
        with tarfile.open(DEPS / ARTIFACTS[2][0]) as archive:
            archive.extractall(DEPS, filter='data')
    if not (DEPS / 'OBS.app').exists():
        mount = DEPS / 'obs-volume'
        subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount),
                        str(DEPS / ARTIFACTS[0][0])], check=True)
        try:
            subprocess.run(['ditto', str(mount / 'OBS.app'), str(DEPS / 'OBS.app')], check=True)
        finally:
            subprocess.run(['hdiutil', 'detach', str(mount)], check=True)
    print('OBS sources and unmodified app bundle ready in', DEPS)

if __name__ == '__main__':
    main()
