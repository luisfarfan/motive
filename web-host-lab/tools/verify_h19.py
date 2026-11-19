#!/usr/bin/env python3
"""H19 non-browser verification. Never launches CEF or rewrites H16/H18 evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

LAB=Path(__file__).resolve().parents[1]
REPO=LAB.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    output=(args.output_dir or LAB/'evidence'/('H19-static-'+uuid.uuid4().hex[:12])).absolute()
    if not output.is_relative_to(LAB/'evidence'):
        raise ValueError('LAB_EVIDENCE_REQUIRED')
    output.mkdir(mode=0o700)
    (LAB/'.cache').mkdir(exist_ok=True)
    checks=[]
    def check(name,command,timeout=180):
        try:
            result=subprocess.run([str(x) for x in command],cwd=REPO,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),text=True,capture_output=True,timeout=timeout)
            content=result.stdout+result.stderr
            code=result.returncode
        except subprocess.TimeoutExpired:
            content='bounded check deadline exceeded\n';code=124
        (output/(name+'.log')).write_text(content)
        checks.append({'name':name,'status':'PASS' if code==0 else 'FAIL','returncode':code,
                       'command':[str(x) for x in command],'log_sha256':hashlib.sha256(content.encode()).hexdigest()})
        print(name,checks[-1]['status'],flush=True)
        return code==0
    for name,path,features in [('contracts','browser-host',[]),('bridge','frame-bridge',['--features','creator-bridge'])]:
        manifest=LAB/'poc'/path/'Cargo.toml'
        check(name+'-rust',['cargo','test','--offline','--locked','--manifest-path',manifest,*features])
        check(name+'-clippy',['cargo','clippy','--offline','--locked','--manifest-path',manifest,*features,'--all-targets','--','-D','warnings'])
        check(name+'-fmt',['cargo','fmt','--manifest-path',manifest,'--','--check'])
    check('python',[sys.executable,'-m','unittest','discover','-s',LAB/'tests','-p','test_*.py','-v'])
    check('security-python',[sys.executable,'-m','unittest','discover','-s',LAB/'tests','-p','h19_security*_test.py','-v'])
    check('runtime-node',['node','--test',LAB/'tests/runtime-interop.test.mjs'])
    check('goal-bootstrap-node',['node','--test',REPO/'creator-runtime-lab/binding/tests/native-bootstrap.test.mjs'])
    manifest=LAB/'poc/frame-bridge/Cargo.toml'
    if check('bridge-release',['cargo','build','--offline','--locked','--release','--features','creator-bridge','--manifest-path',manifest]):
        lib=LAB/'poc/frame-bridge/target/release/libmotive_frame_bridge.a'
        for name,file,link in [('frame-abi','frame_bridge.cc',True),('frame-consumer','native_frame_consumer.cc',True),('multi-policy','native_multi_policy.cc',False),('bridge-policy','native_bridge_policy.cc',True)]:
            binary=output/name
            command=['clang++','-std=c++20','-arch','arm64','-O2','-Wall','-Wextra','-Werror',LAB/'tests'/file]
            if link:command += [lib,'-framework','Security','-framework','CoreFoundation','-framework','SystemConfiguration','-lresolv','-lpthread']
            command += ['-o',binary]
            if check(name+'-build',command):
                check(name,[binary])
                binary.unlink() # generated non-CEF binary; retain logs, not binaries
    summary={'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL',
             'date_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'cef_executed':False,
             'native_scope':'compiled synthetic C ABI/policy tests only, not Chromium rendering',
             'third_party_execution':'BLOCKED','production_modified':False,
             'source_sha256':{str(p.relative_to(LAB)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for directory in ('poc','tools','tests') for p in sorted((LAB/directory).rglob('*'))
                  if p.is_file() and 'target' not in p.parts and '__pycache__' not in p.parts}}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
