#!/usr/bin/env python3
"""Hash the local H22 delivery and verify its declared repository scope.

No network, writes to existing artifacts, native launches or process control.
The output itself is excluded so the manifest can be independently rechecked.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path(__file__).resolve().parents[2]
BASE='25aca10dfeaa22345a7c4d9d232613ffb496bf1a'


def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args])


def collect(output):
    modified=git('diff','--name-only','HEAD','-z').decode().split('\0')
    untracked=git('ls-files','--others','--exclude-standard','-z').decode().split('\0')
    paths=sorted(set(p for p in modified+untracked if p))
    allowed=lambda p:p.startswith('web-host-lab/') or p in ('README.md','docs/plan.md','docs/decisions.md')
    outside=[p for p in paths if not allowed(p)]
    protected=['src','native','build.rs','show-control']
    protected_diff=git('diff','--name-only',BASE,'--',*protected).decode().splitlines()
    historical=git('ls-tree','-r','--name-only',BASE,'--','web-host-lab/evidence','web-host-lab/docs').decode().splitlines()
    history_changes=[]
    for path in historical:
        current=REPO/path
        if not current.is_file() or current.is_symlink() or current.read_bytes()!=git('show',BASE+':'+path):
            history_changes.append(path)
    files={};excluded=[]
    for path in paths:
        current=REPO/path
        if current.resolve()==output.resolve():continue
        if current.is_symlink():raise ValueError('DELIVERY_SYMLINK '+path)
        if not current.is_file():excluded.append(path);continue
        if current.stat().st_size>64*1024**2:raise ValueError('DELIVERY_OVERSIZE '+path)
        data=current.read_bytes()
        files[path]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return {'status':'PASS' if not outside and not protected_diff and not history_changes and not excluded else 'FAIL',
        'base_commit':BASE,'current_head':git('rev-parse','HEAD').decode().strip(),
        'scope':'local uncommitted H22 source, documentation, research and evidence; no publish or Product acceptance',
        'outside_declared_scope':outside,'protected_production_diff':protected_diff,
        'historical_files_checked':len(historical),'historical_files_changed':history_changes,
        'removed_or_nonregular_files':excluded,'files':files,
        'total_bytes':sum(v['bytes'] for v in files.values()),
        'limits':['Ignored caches, SDKs, target directories and local binaries are not delivery artifacts.',
            'Hashes identify local bytes; they do not establish security or capacity acceptance.',
            'Read after all owned experiments finish; an active log would legitimately change.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=collect(a.output)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='files'}))
    raise SystemExit(result['status']!='PASS')
