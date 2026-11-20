#!/usr/bin/env python3
"""Real owner/CLI/MCP and project v1–v6 load/save round trips, pattern only.

Run through h15_run_owned under the canonical lock. Historical documents are
controlled inputs to load_project, never direct mutations of running Production.
The user's project bytes/mode are restored only if our last write still matches.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from h7_support import Client, VERIFY
from verify_h14_collection import default_owner, lock, save


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock()
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    path = VERIFY.data_root / 'project.json'
    original = path.read_bytes() if path.exists() else None
    mode = stat.S_IMODE(path.stat().st_mode) if original is not None else None
    if original is not None:
        backup = out / 'project.original'; backup.write_bytes(original); backup.chmod(0o600)
    report = {'status': 'FAIL', 'cases': [], 'cleanup_errors': [],
              'binary_sha256': digest(VERIFY.app_executable.read_bytes()),
              'original_sha256': digest(original) if original is not None else None,
              'scope': 'Real production load/save with controlled pattern documents; no physical identity restoration.'}
    current_bytes = original
    client = None
    try:
        client = Client(); initial = client.state(); default_owner(initial)
        cli = json.loads(subprocess.check_output([str(VERIFY.app_executable), 'ctl', '{"op":"status"}'], text=True))
        assert cli['ok'] and cli['state']['pid'] == initial['pid']
        assert cli['state']['revision'] == initial['revision']
        client.call('set_overlay', visible=False)
        cli = json.loads(subprocess.check_output([str(VERIFY.app_executable), 'ctl', '{"op":"status"}'], text=True))
        assert cli['state']['project']['overlay'] is False and cli['state']['pid'] == initial['pid']
        report['shared_owner'] = {'pid': initial['pid'], 'status': 'PASS',
                                 'ui': 'The fresh GPUI process owns Production; no UI gesture is claimed.'}
        baseline = copy.deepcopy(initial['project'])
        for version in range(1, 7):
            project = copy.deepcopy(baseline); project['version'] = version
            if version < 3: project.pop('graph', None)
            if version >= 5:
                project['video'] = {'version': 1, 'resolution': 'full_hd1080',
                                    'fps': 60 if version == 5 else 30, 'coordinate_space': 'design960'}
            if version == 6:
                project['capture_safe_scene'] = project['graph']['active_scene']
            current_bytes = (json.dumps(project, indent=2) + '\n').encode()
            path.write_bytes(current_bytes); path.chmod(0o600)
            loaded = client.call('load_project')['state']
            assert loaded['pid'] == initial['pid']
            assert loaded['project']['graph'] == baseline['graph']
            assert loaded['project'].get('video') == project.get('video')
            assert loaded['project'].get('capture_safe_scene') == project.get('capture_safe_scene')
            assert all(not s['native_busy'] for s in loaded['outputs'].values())
            assert not loaded['audio_mixer']['store']['inputs']
            client.call('save_project'); current_bytes = path.read_bytes()
            durable = json.loads(current_bytes)
            assert durable == client.state()['project']
            client.call('set_overlay', visible=False)
            restored = client.call('load_project')['state']
            assert restored['project'] == durable
            report['cases'].append({'input_version': version, 'saved_version': durable['version'],
                'status': 'PASS', 'sha256': digest(current_bytes),
                'graph_and_stable_ids': 'PASS', 'restored_from_disk': 'PASS'})
            save(out / ('v' + str(version) + '.json'), durable)
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        try:
            observed = path.read_bytes() if path.exists() else None
            assert observed == current_bytes, 'Project changed by another writer; restoration withheld'
            if original is None:
                if path.exists(): path.unlink()
            else:
                path.write_bytes(original); path.chmod(mode)
            assert (path.read_bytes() if path.exists() else None) == original
            report['project_restored'] = True
        except Exception as error:
            report['cleanup_errors'].append(str(error)); report['status'] = 'FAIL'
        if client:
            report['mcp'] = client.ops; client.close()
        save(out / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'cases', 'cleanup_errors')}))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
