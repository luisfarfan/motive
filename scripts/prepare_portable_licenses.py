#!/usr/bin/env python3
"""Cache missing Rust notices from the exact Git revisions recorded in crates.

Crates.io packages sometimes omit their workspace LICENSE. This build-only
step reads their .cargo_vcs_info.json, never a moving branch, and records each
download URL and SHA-256. It does not modify Cargo's registry or user settings.
"""
import hashlib
import json
import pathlib
import re
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / 'target/portable-licenses'
# This published crate omits repository metadata. Its exact recorded commit
# exists in the author's upstream workspace; verify lib.rs before using notices.
REPOSITORY_OVERRIDES = {('zune-inflate', '0.2.54'): 'https://github.com/etemesi254/zune-image'}


def request(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Motive-local-license-audit'}), timeout=30) as response:
        content = response.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise RuntimeError('License response exceeds bound')
    return content


def local_notices(directory):
    return [p for p in directory.iterdir() if p.is_file()
            and p.name.lower().startswith(('license', 'licence', 'copying', 'notice'))]


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(subprocess.check_output(['cargo', 'metadata', '--locked', '--offline',
                                                  '--format-version', '1', '--filter-platform',
                                                  'aarch64-apple-darwin'], cwd=ROOT, text=True))
    nodes = {p['id']: p for p in metadata['resolve']['nodes']}
    selected, pending = set(), [metadata['resolve']['root']]
    while pending:
        item = pending.pop()
        if item in selected:
            continue
        selected.add(item)
        pending.extend(p['pkg'] for p in nodes[item]['deps'])
    trees, records, missing = {}, [], []
    for package in metadata['packages']:
        if package['id'] not in selected:
            continue
        directory = pathlib.Path(package['manifest_path']).parent
        if local_notices(directory) or (package.get('license_file') and (directory / package['license_file']).is_file()):
            continue
        name = f"{package['name']}-{package['version']}"
        repository = package.get('repository') or REPOSITORY_OVERRIDES.get((package['name'], package['version']), '')
        match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', repository)
        try:
            if not match:
                raise ValueError('No supported immutable GitHub provenance')
            vcs = json.loads((directory / '.cargo_vcs_info.json').read_text())
            revision = vcs['git']['sha1']
            if not re.fullmatch('[0-9a-f]{40}', revision):
                raise ValueError('Invalid source revision')
            project = match.group(1)
            if not package.get('repository'):
                path = str(pathlib.PurePosixPath(vcs.get('path_in_vcs') or '.') / 'src/lib.rs')
                upstream_source = request(f'https://raw.githubusercontent.com/{project}/{revision}/{path}')
                if upstream_source != (directory / 'src/lib.rs').read_bytes():
                    raise ValueError('Repository override does not match published crate source')
            cache_key = f'{project.replace("/", "-")}-{revision}'
            tree_file = CACHE / (cache_key + '-tree.json')
            if cache_key not in trees:
                if not tree_file.exists():
                    tree_file.write_bytes(request(f'https://api.github.com/repos/{project}/git/trees/{revision}?recursive=1'))
                tree = json.loads(tree_file.read_text())
                if tree.get('truncated'):
                    raise ValueError('Truncated repository tree')
                trees[cache_key] = tree['tree']
            path_in_vcs = pathlib.PurePosixPath(vcs.get('path_in_vcs') or '.')
            parents = {path_in_vcs, *path_in_vcs.parents, pathlib.PurePosixPath('.')}
            matches = []
            for item in trees[cache_key]:
                path = pathlib.PurePosixPath(item['path'])
                if item['type'] != 'blob' or item.get('size', 0) > 1024 * 1024:
                    continue
                filename = path.name.lower()
                direct = path.parent in parents and filename.startswith(('license', 'licence', 'copying', 'notice'))
                in_notices = (path.parent.parent in parents and
                              path.parent.name.lower() in {'license', 'licenses', 'licence', 'licences'})
                if direct or in_notices:
                    matches.append(item['path'])
            if not matches:
                raise ValueError('No license/notice at source directory or its ancestors')
            target = CACHE / name
            target.mkdir(exist_ok=True)
            files = []
            for relative in sorted(matches):
                destination = target / relative.replace('/', '__')
                url = f'https://raw.githubusercontent.com/{project}/{revision}/{relative}'
                if not destination.exists():
                    destination.write_bytes(request(url))
                files.append({'file': destination.name, 'url': url,
                              'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
            records.append({'package': package['name'], 'version': package['version'],
                            'repository': repository, 'revision': revision, 'files': files})
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            missing.append({'package': name, 'reason': str(error)})
    result = {'schema_version': 1, 'records': records, 'missing': missing,
              'status': 'PASS' if not missing else 'PARTIAL'}
    (CACHE / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'packages': len(records), 'missing': missing,
                      'manifest': str(CACHE / 'manifest.json')}))
    raise SystemExit(bool(missing))


if __name__ == '__main__':
    main()
