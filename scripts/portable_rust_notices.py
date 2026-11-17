"""Verified supplements for four published crates with missing license texts.

Never changes the registry, resolves a moving license branch or manufactures an
upstream copyright notice. The original crate checksum is verified first.
"""
import hashlib
import json
import pathlib
import tarfile
import tomllib


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def specifications(root):
    value = json.loads((root / 'scripts/portable-rust-notice-supplements.json').read_text())
    if value['schema_version'] != 1:
        raise ValueError('Unsupported Rust notice supplement schema')
    return {(p['name'], p['version']): p for p in value['packages']}


def verified_crate(root, directory, spec):
    packages = tomllib.loads((root / 'Cargo.lock').read_text())['package']
    locked = next(p for p in packages if (p['name'], p['version']) == (spec['name'], spec['version']))
    if locked.get('checksum') != spec['crate_sha256']:
        raise ValueError('Supplement does not match Cargo.lock checksum')
    archive = directory.parent.parent.parent / 'cache' / directory.parent.name / (directory.name + '.crate')
    if archive.is_symlink() or archive.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Invalid or oversized published crate archive')
    if sha256(archive.read_bytes()) != spec['crate_sha256']:
        raise ValueError('Published crate archive checksum mismatch')
    result = {}
    prefix = directory.name + '/'
    with tarfile.open(archive, 'r:gz') as source:
        for member in source.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith(prefix) or member.size > 8 * 1024 * 1024:
                raise ValueError('Invalid or oversized published crate member')
            relative = member.name[len(prefix):]
            path = pathlib.PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or relative in result:
                raise ValueError('Invalid published crate path')
            data = source.extractfile(member).read()
            local = directory / relative
            if local.is_symlink() or local.read_bytes() != data:
                raise ValueError('Registry content differs from the checksum-verified crate')
            result[relative] = data
    package = tomllib.loads(result['Cargo.toml'].decode())['package']
    if (package['name'], package['version'], package.get('license')) != (spec['name'], spec['version'], spec['declared_license']):
        raise ValueError('Published license declaration does not match reviewed supplement')
    if spec.get('declared_revision'):
        vcs = json.loads(result['.cargo_vcs_info.json'])
        if vcs['git']['sha1'] != spec['declared_revision']:
            raise ValueError('Published VCS revision differs from reviewed supplement')
    return result


def supplement(root, cache, directory, spec, request):
    members = verified_crate(root, directory, spec)
    target = cache / directory.name
    target.mkdir(parents=True, exist_ok=True)
    files, proof = [], []
    crate_url = f"https://static.crates.io/crates/{spec['name']}/{directory.name}.crate"

    def save(name, data, url, member=None):
        (target / name).write_bytes(data)
        record = {'file': name, 'url': url, 'sha256': sha256(data)}
        if member is not None:
            record['archive_member'] = member
        files.append(record)

    def evidence(name, url):
        # Keep fresh immutable commit proof and its hash with the notices.
        data = request(url)
        save(name, data, url)
        proof.append({'file': name, 'url': url, 'sha256': sha256(data)})
        return json.loads(data)

    method = spec['method']
    if method.endswith('_license_only_child'):
        commit = evidence('UPSTREAM-LICENSE-COMMIT.json', spec['commit_url'])
        if method == 'github_license_only_child':
            valid = (commit['sha'] == spec['notice_revision']
                     and [p['sha'] for p in commit['parents']] == [spec['declared_revision']]
                     and len(commit['files']) == 1
                     and commit['files'][0]['filename'] == 'LICENSE'
                     and commit['files'][0]['status'] == 'added')
        else:
            diff = evidence('UPSTREAM-LICENSE-DIFF.json', spec['diff_url'])
            valid = (commit['id'] == spec['notice_revision']
                     and commit['parent_ids'] == [spec['declared_revision']]
                     and len(diff) == 1 and diff[0]['old_path'] == diff[0]['new_path'] == 'LICENSE'
                     and diff[0]['new_file'] is True and diff[0]['deleted_file'] is False)
        if not valid:
            raise ValueError('Upstream commit is not a license-only child of the published revision')
    elif method == 'published_crate_alternative':
        if spec['declared_license'] != 'MIT/Apache-2.0' or spec['selected_license'] != 'Apache-2.0':
            raise ValueError('Alternative selection is not the reviewed published grant')
        if spec.get('tree_url'):
            tree = evidence('UPSTREAM-RELEASE-TREE.json', spec['tree_url'])
            if tree.get('truncated'):
                raise ValueError('Incomplete source equivalence proof')
            blobs = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob'}
            for path, data in members.items():
                blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                if blobs.get(path) != blob:
                    raise ValueError('Published file differs from pinned upstream release')
    else:
        raise ValueError('Unsupported reviewed notice method')

    notice = request(spec['notice_url'])
    if sha256(notice) != spec['notice_sha256']:
        raise ValueError('Canonical license text checksum mismatch')
    save('LICENSE-' + spec['selected_license'] + '.txt', notice, spec['notice_url'])
    # Preserve published declarations/authors verbatim; these are not fabricated
    # upstream NOTICE files. Include all actual notices, even below the root.
    for path, data in members.items():
        filename = pathlib.PurePosixPath(path).name.lower()
        if filename.startswith(('license', 'licence', 'copying', 'notice', 'readme', 'authors', 'copyright')) or path in {'Cargo.toml', 'Cargo.toml.orig', '.cargo_vcs_info.json'}:
            save('PUBLISHED-' + path.replace('/', '__'), data, crate_url, path)
    headers = []
    for path, data in sorted(members.items()):
        if not path.endswith('.rs'):
            continue
        lines = data.decode('utf-8').splitlines(keepends=True)
        header = []
        for line in lines:
            if line.lstrip().startswith('//') or not line.strip():
                header.append(line)
            else:
                break
        if header:
            headers.append('Published member: ' + path + '\n' + ''.join(header))
    if headers:
        save('PUBLISHED-SOURCE-HEADERS.txt', '\n'.join(headers).encode(), crate_url)
    return {'package': spec['name'], 'version': spec['version'], 'repository': spec['repository'],
            'revision': spec.get('declared_revision'), 'notice_revision': spec.get('notice_revision'),
            'release_revision': spec.get('release_revision'),
            'selected_license': spec['selected_license'], 'method': method,
            'crate_url': crate_url, 'crate_sha256': spec['crate_sha256'],
            'published_files_verified': len(members),
            'declared_revision_available': spec.get('declared_revision_available'),
            'files': files, 'proof': proof,
            'scope': 'notice_inventory_only_not_distribution_approval'}
