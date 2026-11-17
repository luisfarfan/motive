#!/usr/bin/env python3
"""Materialize a local corresponding-source candidate; never publish it.

The manifest distinguishes copied sources, unavailable archives, unresolved
notices and upstream submodules. It deliberately does not certify legal or
binary reproducibility merely because downloads succeeded.
"""
import argparse
import concurrent.futures
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

from portable_support import sha256
from build_portable_media_tools import SOURCE_SHA256, SOURCE_URL, COMMIT
from portable_source_submodules import prepare_proofs, review as review_submodules

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / 'target/portable-sources/archives'


def fetch_source(record, allow_fetch):
    name = record['name']
    extension = '.tar.xz' if record['archive_url'].endswith('.tar.xz') else '.tar.gz'
    cache_version = record.get('archive_version') or record.get('revision') or record['version']
    path = CACHE / f"{name}-{cache_version}{extension}"
    result = {**record, 'file': path.name}
    try:
        local = record.get('local')
        if not path.exists() and local and pathlib.Path(local).is_file():
            shutil.copy2(local, path)
        if not path.exists():
            if not allow_fetch:
                raise ValueError('Archive not cached; use --fetch for the pinned source')
            temporary = path.with_suffix(path.suffix + '.part')
            with urllib.request.urlopen(record['archive_url'], timeout=45) as response, temporary.open('wb') as target:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 256 * 1024 * 1024:
                        raise ValueError('Source archive exceeds bound')
                    target.write(chunk)
            temporary.rename(path)
        digest = sha256(path)
        if record.get('sha256') and digest != record['sha256']:
            raise ValueError('Source archive checksum differs from pinned recipe')
        submodules = []
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.isfile() and pathlib.PurePosixPath(member.name).name == '.gitmodules':
                    submodules.append({'path': member.name,
                                       'contents': archive.extractfile(member).read(65536).decode(errors='replace')})
            archive_revision = archive.pax_headers.get('comment')
        result.update(status='PASS', sha256=digest, bytes=path.stat().st_size,
                      archive_revision=archive_revision, submodules_to_review=submodules)
    except (OSError, ValueError, tarfile.TarError) as error:
        result.update(status='BLOCKED', error=str(error))
    result.pop('local', None)
    return result


def rust_archives(destination):
    metadata = json.loads(subprocess.check_output(['cargo', 'metadata', '--locked', '--offline',
                         '--format-version', '1', '--filter-platform', 'aarch64-apple-darwin'], cwd=ROOT, text=True))
    nodes = {n['id']: n for n in metadata['resolve']['nodes']}
    selected, pending = set(), [metadata['resolve']['root']]
    while pending:
        item = pending.pop()
        if item in selected:
            continue
        selected.add(item)
        pending.extend(n['pkg'] for n in nodes[item]['deps'])
    lock = tomllib.loads((ROOT / 'Cargo.lock').read_text())
    checksums = {(p['name'], p['version'], p.get('source')): p.get('checksum') for p in lock['package']}
    records = []
    for package in metadata['packages']:
        if package['id'] not in selected or package['source'] is None:
            continue
        row = {'name': package['name'], 'version': package['version'], 'source': package['source']}
        try:
            directory = pathlib.Path(package['manifest_path']).parent
            archive = directory.parent.parent.parent / 'cache' / directory.parent.name / (directory.name + '.crate')
            expected = checksums[(package['name'], package['version'], package['source'])]
            if not expected or not archive.is_file() or sha256(archive) != expected:
                raise ValueError('Original .crate absent or checksum differs from Cargo.lock')
            shutil.copy2(archive, destination / archive.name)
            row.update(status='PASS', sha256=expected, file=archive.name)
        except (OSError, ValueError, KeyError) as error:
            row.update(status='BLOCKED', error=str(error))
        records.append(row)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    destination = args.output.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        parser.error('output exists; choose a new source candidate directory')
    CACHE.mkdir(parents=True, exist_ok=True)
    spec = json.loads((ROOT / 'scripts/portable-sources.json').read_text())
    records = spec['sources'] + [
        {'name': 'obs-deps-build-recipes', 'version': '2026-10-23', 'revision': spec['obs_deps_revision'],
         'archive_url': f"https://github.com/obsproject/obs-deps/archive/{spec['obs_deps_revision']}.tar.gz",
         'sha256': spec['obs_deps_archive_sha256']},
        {'name': 'obs-studio', 'version': '33.0.1',
         'revision': '65c320b46e1af5c7a555161aea6182cdf7a8c524',
         'archive_version': '33.0.1',
         'archive_url': 'https://github.com/obsproject/obs-studio/archive/refs/tags/33.0.1.tar.gz',
         'sha256': '9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b',
         'local': str(ROOT / '.deps/obs-studio-33.0.1.tar.gz')},
        {'name': 'FFmpeg', 'version': '8.1.2', 'revision': COMMIT,
         'archive_url': SOURCE_URL, 'sha256': SOURCE_SHA256,
         'local': str(ROOT / f'target/portable-tools/archives/FFmpeg-{COMMIT}.tar.gz')},
    ] + spec.get('submodules', [])
    proofs_cache = ROOT / 'target/portable-sources/gitlink-proofs'
    proofs = prepare_proofs(spec.get('source_tree_proofs', []), proofs_cache, args.fetch)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        upstream = list(pool.map(lambda p: fetch_source(p, args.fetch), records))
    submodule_review = review_submodules(upstream, proofs)
    destination.mkdir(parents=True)
    native = destination / 'upstream-native'
    native.mkdir()
    for row in upstream:
        if row['status'] == 'PASS':
            shutil.copy2(CACHE / row['file'], native / row['file'])
    proof_destination = destination / 'upstream-gitlink-proofs'
    proof_destination.mkdir()
    for proof in proofs:
        if proof['status'] == 'PASS':
            shutil.copy2(proofs_cache / proof['file'], proof_destination / proof['file'])
    crates = destination / 'rust-crates'
    crates.mkdir()
    rust = rust_archives(crates)
    # Snapshot all source inputs, including uncommitted implementations, while
    # excluding ignored runtime data, .deps, build products and Git metadata.
    source = destination / 'motive'
    source.mkdir()
    files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    snapshots = []
    for raw in sorted(set(files.split(b'\0')) - {b''}):
        relative = pathlib.Path(os.fsdecode(raw))
        path = ROOT / relative
        if path.is_symlink():
            raise RuntimeError(f'Source snapshot requires review of symlink: {relative}')
        if not path.is_file():
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        snapshots.append({'path': str(relative), 'sha256': sha256(target)})
    license_manifest = ROOT / 'target/portable-licenses/manifest.json'
    notices = json.loads(license_manifest.read_text()) if license_manifest.exists() else {'status': 'NOT IMPLEMENTED', 'missing': []}
    if license_manifest.exists():
        shutil.copytree(license_manifest.parent, destination / 'upstream-rust-notices')
    blocked = [r['name'] for r in upstream + rust if r['status'] != 'PASS']
    submodules = sorted({r['source'] for r in submodule_review['issues']})
    result = {'schema_version': 1, 'status': 'PARTIAL',
              'material_status': 'PASS' if not blocked and submodule_review['status'] == 'PASS' else 'PARTIAL',
              'motive_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'motive_source_files': snapshots, 'native_sources': upstream, 'rust_sources': rust,
              'blocked_sources': blocked, 'notice_status': notices.get('status'),
              'notice_missing': notices.get('missing'), 'submodule_review_required': submodules,
              'submodule_material': submodule_review,
              'remaining_gate': 'Verify source-to-binary correspondence and reconstruction instructions before distribution; resolve any material or notice failures above. A complete gitlink inventory is not rebuild or distribution certification. No installer or source offer has been published.'}
    (destination / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    (destination / 'README.txt').write_text(
        'Local corresponding-source candidate for Motive.\n'
        'motive/ snapshots tracked and untracked non-ignored source files, with hashes in manifest.json.\n'
        'rust-crates/ retains original registry archives verified against Cargo.lock.\n'
        'upstream-native/ retains original source archives; the OBS deps archive includes its build recipes and patches.\n'
        'Submodule archives are not executed or automatically extracted. manifest.json submodule_material.layout maps each archive, pinned revision and parent subpath; strip one archive root component when assembling each location.\n'
        'upstream-gitlink-proofs/ retains checksum-verified official recursive tree responses for the parent and transitive gitlinks.\n'
        'Motive native patches and build scripts are under motive/native and motive/scripts.\n'
        'Review the unresolved gates in manifest.json before any distribution. This directory is not a publication.\n')
    print(json.dumps({'status': result['status'], 'material_status': result['material_status'],
                      'native_sources': len(upstream), 'rust_sources': len(rust),
                      'blocked_sources': blocked, 'submodule_review_required': submodules,
                      'submodule_material_status': submodule_review['status'],
                      'manifest': str(destination / 'manifest.json')}))


if __name__ == '__main__':
    main()
