#!/usr/bin/env python3
"""Run under h22_with_lock. No CEF, production engine, credentials or devices."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

LAB=Path(__file__).resolve().parents[1]
REPO=LAB.parent


def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--replay-only',action='store_true');a=p.parse_args()
    if not a.name.startswith('H22-') or not a.name.replace('-','').isalnum():raise ValueError('NAME')
    out=LAB/'evidence'/a.name;out.mkdir(mode=0o700);checks=[]
    def check(name,command,timeout=240):
        command=[str(x) for x in command]
        try:r=subprocess.run(command,cwd=REPO,capture_output=True,timeout=timeout,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'));code=r.returncode;data=r.stdout+r.stderr
        except subprocess.TimeoutExpired:code=124;data=b'DEADLINE\n'
        (out/(name+'.log')).write_bytes(data);checks.append({'name':name,'command':command,'returncode':code,'log_sha256':hashlib.sha256(data).hexdigest()})
        print(name,'PASS' if code==0 else 'FAIL',flush=True);return code==0
    if not a.replay_only:
        # Existing full non-browser ABI/lifecycle suite retained as nested evidence.
        check('inherited-contracts',[sys.executable,LAB/'tools/verify_h19.py','--output-dir',out/'inherited'],480)
        manifest=LAB/'poc/frame-transport/Cargo.toml'
        for name,args in [('transport-tests',['test']),('transport-clippy',['clippy']),('transport-build',['build'])]:
            command=['cargo',*args,'--offline','--locked','--manifest-path',manifest,'--all-targets']
            if name.endswith('clippy'):command+=['--','-D','warnings']
            check(name,command)
        check('transport-fmt',['cargo','fmt','--manifest-path',manifest,'--','--check'])
        # Real installed libobs and reviewed public headers, read only. No gs_create,
        # obs_startup or GPU execution; validation does not certify texture output.
        deps=Path('/Users/luisfarfan/Developer/products/motive/.deps')
        headers=deps/'obs-studio-33.0.1/libobs';framework=deps/'OBS.app/Contents/Frameworks'
        lib=framework/'libobs.framework/Versions/A/libobs';source=LAB/'poc/obs-adapter'
        binary=out/'obs-contract'
        cmd=['clang++','-std=c++20','-arch','arm64','-O2','-Wall','-Wextra','-Werror','-I',headers,
             source/'adapter.cpp',source/'contract-test.cpp',lib,'-Wl,-rpath,'+str(framework),'-o',binary]
        if check('obs-compile-link',cmd):
            check('obs-validation-contract',[binary]);(out/'obs-binary-sha256.txt').write_text(hashlib.sha256(binary.read_bytes()).hexdigest()+'\n');binary.unlink()
        (out/'obs-inputs.json').write_text(json.dumps({'libobs_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),
            'headers':{str(x.relative_to(headers)):hashlib.sha256(x.read_bytes()).hexdigest() for x in headers.rglob('*.h')},
            'graphics_context_created':False,'gpu_texture_test':False},indent=2)+'\n')
    else:
        check('bridge-fmt',['cargo','fmt','--manifest-path',LAB/'poc/frame-bridge/Cargo.toml','--','--check'])
        check('transport-fmt',['cargo','fmt','--manifest-path',LAB/'poc/frame-transport/Cargo.toml','--','--check'])
    replay=LAB/'poc/frame-transport/target/debug/replay'
    if replay.exists() and all(x['returncode']==0 for x in checks if x['name']=='transport-build'):
        compressed=LAB/'evidence/H22-pilot-r2-goal3h/instance-1-g222300-e1/visual.bgra.gz';raw=gzip.decompress(compressed.read_bytes())
        path=out/'owned-goal.bgra';path.write_bytes(raw);path.chmod(0o600)
        spec=importlib.util.spec_from_file_location('h22_contract_supervisor',LAB/'poc/browser-host/supervisor.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        from h22_process_snapshot import NativeSnapshot
        (out/'supervised-replay').mkdir(mode=0o700)
        supervisor=module.Supervisor(out/'supervised-replay',deadline_seconds=20,rss_limit_kib=256*1024,process_snapshot=NativeSnapshot(module))
        result=supervisor.run([str(replay),str(path),'640','360'])
        (out/'replay-supervision.json').write_text(json.dumps(result,indent=2)+'\n')
        logs=list((out/'supervised-replay').glob('*/stdout.log'));receipt=json.loads(logs[0].read_text()) if logs else {}
        okay=result['returncode']==0 and result['final_cleanup_observed_tree'] and receipt.get('sha256')==hashlib.sha256(raw).hexdigest()
        checks.append({'name':'real-cef-frame-process-replay','returncode':0 if okay else 1})
        (out/'replay-provenance.json').write_text(json.dumps({'source':str(compressed.relative_to(LAB)),
            'compressed_sha256':hashlib.sha256(compressed.read_bytes()).hexdigest(),'raw_sha256':hashlib.sha256(raw).hexdigest(),
            'binary_sha256':hashlib.sha256(replay.read_bytes()).hexdigest(),'receipt':receipt,'status':'PASS' if okay else 'FAIL'},indent=2)+'\n')
        path.unlink()
    summary={'status':'PASS' if all(x['returncode']==0 for x in checks) else 'FAIL','checks':checks,
        'scope':'isolated real socket/process and pure OBS contracts; no live CEF/OBS integration or Production acceptance'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary['status']=='FAIL'


if __name__=='__main__':raise SystemExit(main())
