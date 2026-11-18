#!/usr/bin/env python3
"""Fetch exactly reviewed archives into the lab. No builds or execution."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def verify(entry):
    path = ROOT / entry['cache']
    if not path.is_file() or hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != entry['sha256']:
        raise ValueError(f"ARCHIVE_HASH: {entry['id']}")
    return path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--extract', action='store_true')
    args = parser.parse_args()
    entries = json.loads((ROOT/'research/sources.lock.json').read_text())['sources']
    for e in entries:
        p = ROOT/e['cache']
        if not p.exists() and args.download:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix+'.partial')
            with urllib.request.urlopen(e['url'], timeout=60) as response, tmp.open('wb') as output:
                while chunk := response.read(1024*1024): output.write(chunk)
            if hashlib.file_digest(tmp.open('rb'), 'sha256').hexdigest() != e['sha256']:
                raise ValueError(f"DOWNLOAD_HASH: {e['id']}")
            tmp.rename(p)
        verify(e)
        destination = ROOT/e['source']
        if args.extract and not destination.exists():
            destination.mkdir(parents=True)
            with tarfile.open(p) as archive:
                for member in archive.getmembers():
                    parts = Path(member.name).parts[e['strip_components']:]
                    if not parts: continue
                    member.name = str(Path(*parts))
                    # tarfile's data filter rejects path and symlink escapes.
                    archive.extract(member, destination, filter='data')
        print(f"PASS {e['id']}")

if __name__ == '__main__': main()
