#!/usr/bin/env python3
"""Repeatable static audit of the reviewed cache; no moving branches or binaries."""
import sys
sys.dont_write_bytecode=True
import hashlib,json
from pathlib import Path
from fetch_sources import verify, verify_tree
ROOT=Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/'research/sources.lock.json').read_text())
for source in lock['sources']:verify(source)
verified_sources={source['id']:verify_tree(source, prefixes=('',)) for source in lock['sources'] if source['id'].startswith('cef-source')}
if len(verified_sources)!=2:raise ValueError('EXPECTED_TWO_CEF_SOURCES')
def files(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.is_symlink() and not p.name.startswith('._')}
a=ROOT/'.cache/cef-cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3';b=ROOT/'.cache/cef-abc1ece6a66997894c4c953ed24937603fbd74b4'
x,y=files(a),files(b)
changes=[{'path':key,'old_sha256':x.get(key),'new_sha256':y.get(key)} for key in sorted(x.keys()|y.keys()) if x.get(key)!=y.get(key)]
report={'status':'PASS','classification':'static source differences, not executed behavior','archive_count':len(lock['sources']),'verified_source_files':verified_sources,'cef_implementation_changes':changes,
        'important_recent_patches':['content_always_deny_webauthn.patch','device_bluetooth_always_denied.patch','mac_gamepad_out_of_focus.patch']}
(ROOT/'evidence/M-source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(lock['sources']),'archives;',len(changes),'CEF implementation file differences')
