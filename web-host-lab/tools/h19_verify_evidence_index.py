#!/usr/bin/env python3
"""Verify retained H19 bytes without launching CEF, compiling or rewriting results.

This checks integrity only. In particular, an integrity PASS preserves the soak
functional FAIL and does not promote overall H19 or third-party acceptance.
"""
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / 'web-host-lab/evidence/H19-final-evidence-index.json'


def checked_path(relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Non-repository path: {relative}')
    path = ROOT / relative
    if not path.parent.resolve().is_relative_to(ROOT):
        raise ValueError(f'Parent escapes repository: {relative}')
    return path


def file_identity(path):
    if path.is_symlink():
        data = os.readlink(path).encode()
        return len(data), hashlib.sha256(data).hexdigest(), '120000'
    if not path.is_file():
        raise ValueError(f'Missing regular file: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    mode = '100755' if path.stat().st_mode & 0o111 else '100644'
    return path.stat().st_size, digest.hexdigest(), mode


def verify_rows(rows, mode_key):
    errors = []
    seen = set()
    for row in rows:
        relative = row['path']
        try:
            if relative in seen:
                raise ValueError('Duplicate path')
            seen.add(relative)
            actual = file_identity(checked_path(relative))
            expected = (row['bytes'], row['sha256'], row[mode_key])
            if actual != expected:
                raise ValueError('Bytes, SHA-256 or executable mode differ')
        except (OSError, ValueError) as error:
            errors.append({'path': relative, 'error': str(error)})
    return errors


def main():
    index = json.loads(INDEX.read_text())
    errors = verify_rows(index['files'], 'mode')
    protected = json.loads(checked_path(index['protected_manifest']).read_text())
    errors.extend(verify_rows(protected['protected_manifest'], 'baseline_mode'))
    result = {
        'integrity_status': 'FAIL' if errors else 'PASS',
        'indexed_files': len(index['files']),
        'protected_baseline_files': len(protected['protected_manifest']),
        'errors': errors,
        'h19_acceptance': 'PARTIAL',
        'native_executed': False,
        'scope': 'Retained bytes and executable modes; not benchmark or security acceptance.',
    }
    print(json.dumps(result, sort_keys=True))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
