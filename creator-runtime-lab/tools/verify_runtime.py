#!/usr/bin/env python3
"""Reproduce H18 offline acceptance. Never starts CEF, Motive or a browser."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
BASE = '15ffbad307c5439270130979dae0e9d66d92d700'
EVIDENCE = LAB / 'evidence'


def main():
    checks = []
    commands = [
        ('runtime-tests', ['cargo', 'test', '--offline', '--locked', '--manifest-path', 'creator-runtime-lab/Cargo.toml']),
        ('runtime-clippy', ['cargo', 'clippy', '--offline', '--locked', '--manifest-path', 'creator-runtime-lab/Cargo.toml', '--all-targets', '--', '-D', 'warnings']),
        ('runtime-format', ['cargo', 'fmt', '--manifest-path', 'creator-runtime-lab/Cargo.toml', '--', '--check']),
        ('python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'creator-runtime-lab/tests', '-p', 'test_*.py', '-v']),
        ('sdk-examples', [sys.executable, 'creator-runtime-lab/sdk/verify_examples.py']),
    ]
    for name, command in commands:
        result = subprocess.run(command, cwd=REPO, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}, capture_output=True, text=True, timeout=240)
        log = EVIDENCE / f'H18-{name}.log'
        log.write_text(result.stdout + result.stderr)
        checks.append({'name': name, 'command': command, 'returncode': result.returncode,
                       'status':'PASS' if result.returncode == 0 else 'FAIL', 'log':str(log.relative_to(REPO)),
                       'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        print(name, checks[-1]['status'], flush=True)
    changed = subprocess.check_output(['git','diff','--name-only', BASE], cwd=REPO, text=True).splitlines()
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'], cwd=REPO, text=True).splitlines()
    # The owner explicitly requested the repository CEF policy change on Nov 18.
    # This narrow root-file allowance does not release H17's production files.
    unauthorized = [p for p in set(changed + untracked) if p != 'AGENTS.md' and not p.startswith(('creator-runtime-lab/','web-host-lab/','element-lab/'))]
    originals = subprocess.check_output(['git','diff','--name-only',BASE,'--','element-lab','src','native','show-control','Cargo.toml','Cargo.lock','scripts','creator-experience','design'],cwd=REPO,text=True).splitlines()
    checks.append({'name':'isolated-scope-and-originals','status':'PASS' if not unauthorized and not originals else 'FAIL',
                   'unauthorized_paths':unauthorized,'changed_original_paths':originals})
    code = {}
    for directory in ['src','importer','sdk','tests','tools']:
        for path in sorted((LAB/directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                code[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [LAB/'Cargo.toml',LAB/'Cargo.lock']:
        code[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {'created_utc':datetime.now(timezone.utc).isoformat(), 'baseline':BASE,
        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
        'source_head_before_report_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL',
        'scope':'offline contracts, real reviewed archive bytes, strict simulated owner and inert sidecar',
        'checks':checks,'implementation_sha256':code,'production_connected':False,'native_cef_executed_by_this_tool':False,
        'native_render_verified_by_this_tool':False,'third_party_execution':'BLOCKED','h17_handoff_received':False,
        'owner_authorized_policy_change':{'path':'AGENTS.md','date':'2026-11-18','sha256':hashlib.sha256((REPO/'AGENTS.md').read_bytes()).hexdigest()},
        'dom_evidence':'creator-runtime-lab/evidence/binding/browser-final-provenance.json',
        'native_static_evidence':'web-host-lab/evidence/H18-static-summary.json'}
    (EVIDENCE/'H18-runtime-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
