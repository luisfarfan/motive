"""Verify pinned gitlink material without executing or extracting source code."""
import configparser
import hashlib
import json
import pathlib
import urllib.request
from portable_cache import regular_cache_file, write_cache_atomically


def relative_path(value):
    path = pathlib.PurePosixPath(value)
    if not value or not path.parts or path.is_absolute() or '..' in path.parts or str(path) != value:
        raise ValueError('Invalid submodule path')
    return path


def declarations(record):
    result = {}
    for item in record.get('submodules_to_review', []):
        # Archives have one upstream root directory, retained in evidence paths.
        location = pathlib.PurePosixPath(item['path'])
        parent = pathlib.PurePosixPath(*location.parts[1:-1])
        config = configparser.ConfigParser(interpolation=None, strict=True)
        config.read_string(item['contents'])
        for section in config.sections():
            if not section.startswith('submodule '):
                raise ValueError('Unexpected .gitmodules section')
            path = str(parent / relative_path(config[section]['path']))
            if path in result:
                raise ValueError('Duplicate submodule declaration')
            result[path] = config[section]['url'].removesuffix('.git').rstrip('/')
    return result


def validate_tree(data, spec):
    if hashlib.sha256(data).hexdigest() != spec['sha256']:
        raise ValueError('Git tree proof checksum mismatch')
    tree = json.loads(data)
    if tree['sha'] != spec['revision'] or tree.get('truncated') is not False:
        raise ValueError('Git tree proof is incomplete or has a different revision')
    links = {}
    for item in tree['tree']:
        if item['type'] != 'commit':
            continue
        path = str(relative_path(item['path']))
        if path in links or item.get('mode') != '160000':
            raise ValueError('Invalid or duplicate gitlink')
        links[path] = item['sha']
    return links


def prepare_proofs(specs, cache, allow_fetch):
    cache.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in specs:
        name = f"{spec['source']}-{spec['revision']}-tree.json"
        if pathlib.PurePosixPath(name).name != name:
            raise ValueError('Invalid proof filename')
        path = cache / name
        result = {**spec, 'file': name}
        try:
            if not regular_cache_file(path):
                if not allow_fetch:
                    raise ValueError('Pinned gitlink proof not cached; use --fetch')
                request = urllib.request.Request(spec['url'], headers={'User-Agent': 'Motive-source-review'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise ValueError('Git tree proof exceeds bound')
                validate_tree(data, spec)
                write_cache_atomically(path, lambda stream: stream.write(data))
            if path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('Invalid cached gitlink proof')
            links = validate_tree(path.read_bytes(), spec)
            result.update(status='PASS', gitlinks=links)
        except (OSError, ValueError, KeyError) as error:
            result.update(status='BLOCKED', error=str(error))
        records.append(result)
    return records


def review(records, proofs):
    sources = {item['name']: item for item in records}
    by_source = {item['source']: item for item in proofs}
    children = {}
    issues = []
    for record in records:
        if 'parent_source' not in record:
            continue
        try:
            parent = sources[record['parent_source']]
            path = str(relative_path(record['submodule_path']))
            key = (parent['name'], path)
            if key in children or parent['revision'] != record['parent_revision']:
                raise ValueError('Duplicate submodule mapping or incorrect parent revision')
            if record.get('archive_revision') != record['revision']:
                raise ValueError('Submodule archive does not identify the pinned commit')
            children[key] = record
        except (KeyError, ValueError) as error:
            issues.append({'source': record['name'], 'error': str(error)})
    for record in records:
        name = record['name']
        try:
            declared = declarations(record)
            proof = by_source.get(name)
            if proof is None:
                if declared or record.get('parent_source'):
                    raise ValueError('Source with submodules or a parent has no exhaustive git tree proof')
                continue
            if proof['status'] != 'PASS' or record['status'] != 'PASS':
                raise ValueError('Source archive or git tree proof is blocked')
            if record['revision'] != proof['revision']:
                raise ValueError('Source revision differs from tree proof')
            if record.get('archive_revision') != proof['revision']:
                raise ValueError('Source archive revision differs from tree proof')
            links = proof['gitlinks']
            mapped = {path: child for (parent, path), child in children.items() if parent == name}
            if set(links) != set(declared) or set(links) != set(mapped):
                raise ValueError('Gitlinks, .gitmodules and materialized mappings differ')
            for path, revision in links.items():
                child = mapped[path]
                repository = child['upstream_url'].removesuffix('.git').rstrip('/')
                if child['revision'] != revision or repository != declared[path] or child['status'] != 'PASS':
                    raise ValueError('Submodule material does not match its declared repository and gitlink')
        except (KeyError, ValueError, configparser.Error) as error:
            issues.append({'source': name, 'error': str(error)})

    def location(name, seen):
        if name in seen:
            raise ValueError('Cycle in submodule mapping')
        record = sources[name]
        if 'parent_source' not in record:
            return name
        return location(record['parent_source'], {*seen, name}) + '/' + str(relative_path(record['submodule_path']))

    layout = []
    for record in records:
        if 'parent_source' not in record:
            continue
        try:
            layout.append({'source': record['name'], 'archive': record['file'],
                           'archive_sha256': record['sha256'], 'revision': record['revision'],
                           'parent_source': record['parent_source'], 'parent_revision': record['parent_revision'],
                           'submodule_path': record['submodule_path'],
                           'unpack_under': location(record['name'], set()), 'strip_components': 1,
                           'role': record['role']})
        except (KeyError, ValueError) as error:
            issues.append({'source': record['name'], 'error': str(error)})
    return {'status': 'PASS' if not issues else 'PARTIAL', 'issues': issues,
            'layout': layout, 'proofs': proofs,
            'scope': 'pinned gitlink archives and transitive inventory only; no rebuild or distribution certification'}
