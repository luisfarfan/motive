#!/usr/bin/env python3
"""Archive bounded local source snapshots; never compile, load or launch an app.

Archives are immutable. Recorded hashes are checked before bytes are admitted.
An exact-hash recovery from the working tree/Git is explicitly distinguished
from a snapshot recorded by the build. Missing sources remain missing.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_SOURCE_BYTES = 16 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') for p in path.parts):
        raise ValueError('UNSAFE_RECORDED_PATH')
    return Path(*path.parts)


def lab_path(value):
    path = LAB / relative(value)
    if not path.resolve().is_relative_to(LAB.resolve()):
        raise ValueError('PATH_OUTSIDE_LAB')
    return path


def read_source(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        return None
    return path.read_bytes()


def recover_exact(path, expected):
    """Only equality with the recorded SHA permits recovery; never patch bytes."""
    candidate = lab_path(path)
    data = read_source(candidate)
    if data is not None and sha(data) == expected:
        return data, 'working_tree_exact_hash_recovery'
    # Fixed source path only, no revision expressions supplied by a report.
    repo_path = 'web-host-lab/' + path
    revisions = subprocess.run(['git', 'log', '--all', '--format=%H', '--', repo_path],
                               cwd=REPO, capture_output=True, text=True, check=True).stdout.splitlines()
    for revision in revisions[:100]:
        result = subprocess.run(['git', 'show', revision + ':' + repo_path], cwd=REPO,
                                capture_output=True)
        if result.returncode == 0 and len(result.stdout) <= MAX_SOURCE_BYTES and sha(result.stdout) == expected:
            return result.stdout, 'git_exact_hash_recovery:' + revision
    return None, None


def immutable_write(path, data):
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError('REFUSE_CHANGED_EXISTING_ARTIFACT:' + str(path))
    else:
        with path.open('xb') as output:
            output.write(data)


def tar_bytes(files):
    if sum(len(data) for data in files.values()) > MAX_ARCHIVE_SOURCE_BYTES:
        raise ValueError('ARCHIVE_SOURCE_BUDGET')
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            info.mtime = 0
            info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(memory.getvalue(), compresslevel=6, mtime=0)


def verify_archive(path, expected_files):
    actual = {}
    total = 0
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            relative(member.name)
            if not member.isfile() or member.name in actual or member.size > MAX_SOURCE_BYTES:
                raise ValueError('INVALID_ARCHIVE_MEMBER')
            total += member.size
            if total > MAX_ARCHIVE_SOURCE_BYTES:
                raise ValueError('ARCHIVE_BUDGET')
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError('MISSING_ARCHIVE_DATA')
            data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) != member.size:
                raise ValueError('ARCHIVE_LENGTH')
            actual[member.name] = sha(data)
    if actual != expected_files:
        raise ValueError('ARCHIVE_HASH_OR_INVENTORY_MISMATCH')


def preserve(report_path, output):
    raw_report = report_path.read_bytes()
    report = json.loads(raw_report)
    main = report['binaries'][0]
    binary = lab_path(main['path'])
    build = binary.parents[3]
    if not build.is_relative_to(LAB / '.cache'):
        raise ValueError('BUILD_OUTSIDE_CACHE')
    snapshot = lab_path(report['source_snapshot']) if report.get('source_snapshot') else build / 'source-snapshot'
    recorded = dict(report.get('source_snapshot_sha256', {}))
    coverage = 'build_recorded_snapshot' if recorded else 'legacy_native_hash_recovery'
    for path, expected in report['source_sha256'].items():
        if path in recorded and recorded[path] != expected:
            raise ValueError('REPORT_SOURCE_HASH_DISAGREEMENT')
        recorded[path] = expected
    bridge_path = 'poc/frame-bridge/src/lib.rs'
    if bridge_path in recorded and recorded[bridge_path] != report['frame_bridge_sha256']:
        raise ValueError('REPORT_BRIDGE_HASH_DISAGREEMENT')
    recorded[bridge_path] = report['frame_bridge_sha256']
    if len(recorded) > 256:
        raise ValueError('SOURCE_COUNT_LIMIT')
    files = {'build-report.json': raw_report}
    source_rows, unavailable = [], []
    for path, expected in sorted(recorded.items()):
        relative(path)
        source = snapshot / path
        if not source.resolve().is_relative_to(snapshot.resolve()):
            raise ValueError('SNAPSHOT_PATH_ESCAPE')
        data = read_source(source)
        origin = 'build_recorded_snapshot' if report.get('source_snapshot_sha256') else 'recovered_native_snapshot_exact_hash'
        if data is not None and sha(data) != expected:
            raise ValueError('SNAPSHOT_HASH_MISMATCH:' + path)
        if data is None:
            data, origin = recover_exact(path, expected)
        if data is None:
            unavailable.append({'path': path, 'expected_sha256': expected,
                                'reason': 'No exact bytes found in retained snapshot, working tree, or local Git path history.'})
            continue
        files['sources/' + path] = data
        source_rows.append({'path': path, 'expected_sha256': expected, 'actual_sha256': sha(data),
                            'bytes': len(data), 'origin': origin})
    generated = snapshot / 'fixture_assets.hpp'
    observations = []
    if 'fixture_assets.hpp' not in recorded:
        data = read_source(generated)
        if data is not None:
            files['observed-generated/fixture_assets.hpp'] = data
            observations.append({'path': 'fixture_assets.hpp', 'sha256': sha(data),
                                 'origin': 'retained_generated_file_observed_after_build',
                                 'build_report_recorded_source_hash': False})
    actual_main = sha(binary.read_bytes()) if binary.is_file() and not binary.is_symlink() else None
    if actual_main is not None and actual_main != main['sha256']:
        raise ValueError('MAIN_BINARY_HASH_MISMATCH')
    entry = {
        'build_report': str(report_path.relative_to(LAB)), 'build_report_sha256': sha(raw_report),
        'profile': report['profile'], 'main_binary': main['path'],
        'main_binary_sha256': main['sha256'], 'observed_main_binary_sha256': actual_main,
        'main_binary_hash_verified': actual_main == main['sha256'],
        'snapshot_root': str(snapshot.relative_to(LAB)), 'snapshot_kind': coverage,
        'recorded_sources': source_rows, 'unavailable_recorded_sources': unavailable,
        'unrecorded_generated_observations': observations,
        'recorded_hash_coverage': 'PASS' if not unavailable else 'PARTIAL',
        'complete_build_inputs': 'NOT_ESTABLISHED',
        'limits': [
            'Archive contains only recorded/recovered own source inputs, not CEF binaries or the complete upstream source tree.',
            'Recorded source hashes verify byte correspondence; they do not prove a reproducible binary rebuild.',
            'Cargo manifests/locks and all dependency sources were not included in the historical source snapshot map.',
            'Legacy reports did not record all Rust dependency source hashes; no missing bytes are synthesized.'
        ]
    }
    files['provenance.json'] = canonical_json(entry)
    file_hashes = {name: sha(data) for name, data in files.items()}
    archive_name = report_path.stem.removesuffix('-build') + '-sources.tar.gz'
    archive_path = output / archive_name
    packed = tar_bytes(files)
    immutable_write(archive_path, packed)
    verify_archive(archive_path, file_hashes)
    return {**entry, 'archive': str(archive_path.relative_to(LAB)), 'archive_sha256': sha(packed),
            'archive_bytes': len(packed), 'archive_members_sha256': file_hashes,
            'archive_integrity': 'PASS'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='evidence/H19-build-sources')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    output = lab_path(args.output)
    if args.verify_only:
        index = json.loads((output / 'index.json').read_text())
        for row in index['builds']:
            archive = lab_path(row['archive'])
            if sha(archive.read_bytes()) != row['archive_sha256']:
                raise ValueError('ARCHIVE_FILE_HASH_MISMATCH')
            verify_archive(archive, row['archive_members_sha256'])
        print(json.dumps({'archive_integrity': 'PASS', 'builds': len(index['builds']),
                          'recorded_hash_coverage': index['recorded_hash_coverage']}))
        return
    output.mkdir(parents=True, exist_ok=True)
    reports = sorted((LAB / 'evidence').glob('H19-native-*-build.json'))
    rows = [preserve(path, output) for path in reports]
    index = {'format': 1, 'native_executed': False, 'archive_integrity': 'PASS',
             'recorded_hash_coverage': 'PASS' if all(r['recorded_hash_coverage'] == 'PASS' for r in rows) else 'PARTIAL',
             'builds': rows}
    immutable_write(output / 'index.json', canonical_json(index))
    print(json.dumps({'archive_integrity': 'PASS', 'recorded_hash_coverage': index['recorded_hash_coverage'],
                      'builds': len(rows), 'unavailable': sum(len(r['unavailable_recorded_sources']) for r in rows),
                      'archive_bytes': sum(r['archive_bytes'] for r in rows)}))


if __name__ == '__main__':
    main()
