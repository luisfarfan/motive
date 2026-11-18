#!/usr/bin/env python3
"""Run all authorized static checks. No browser, CEF executable, app or device."""
import sys
sys.dont_write_bytecode=True
import datetime,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
BASE='130b626168cbe1336afb85c3810fa6be5e6b2b11'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',CARGO_HOME=str(ROOT/'.cache/cargo-home'),CARGO_TARGET_DIR=str(ROOT/'poc/browser-host/target'))
Path(env['CARGO_HOME']).mkdir(parents=True,exist_ok=True)
config=ROOT/'.cache/cargo-local.toml'
config.write_text('[source.crates-io]\nreplace-with="h16-vendor"\n[source.h16-vendor]\ndirectory='+json.dumps(str(ROOT/'.cache/rust-vendor'))+'\n')
manifest=str(ROOT/'poc/browser-host/Cargo.toml')
checks=[]
def run(name,cmd,stdout_path=None):
    result=subprocess.run(cmd,cwd=REPO,env=env,text=True,capture_output=True,timeout=180)
    (ROOT/'evidence'/f'M-{name}.log').write_text(result.stdout+result.stderr)
    if stdout_path is not None and result.returncode==0:stdout_path.write_text(result.stdout)
    checks.append({'name':name,'status':'PASS' if result.returncode==0 else 'FAIL','returncode':result.returncode,'command':cmd})
    print(name,checks[-1]['status'],flush=True)
    return result.returncode==0
cargo=lambda sub:['cargo',sub,'--manifest-path',manifest,'--offline','--locked','--config',str(config)]
run('rust-tests',cargo('test'))
run('clippy',cargo('clippy')+['--all-targets','--','-D','warnings'])
run('format',['cargo','fmt','--manifest-path',manifest,'--','--check'])
run('security',[sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v'])
if run('projection',cargo('run')+['--example','project_goal'],ROOT/'evidence/K-goal-message.json'):
    run('runtime',['node','--test',str(ROOT/'tests/runtime-interop.test.mjs')])
run('native-api',[sys.executable,str(ROOT/'tools/compile_native_api.py')])
run('source-audit',[sys.executable,str(ROOT/'tools/audit_sources.py')])
changed=set(subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO,text=True).splitlines())
changed.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=REPO,text=True).splitlines())
violations=sorted(p for p in changed if not p.startswith('web-host-lab/'))
checks.append({'name':'scope','status':'FAIL' if violations else 'PASS','outside_lab':violations})
code={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for parent in ['poc','tests','tools'] for p in (ROOT/parent).rglob('*') if p.is_file() and 'target' not in p.parts and '__pycache__' not in p.parts}
report={'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base':BASE,'tested_head_before_final_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','native_cef_executed':False,'native_linked':False,'production_integrated':False,'native_security':'BLOCKED',
        'checks':checks,'implementation_sha256':code}
(ROOT/'evidence/M-static-summary.json').write_text(json.dumps(report,indent=2)+'\n')
print('Static suite:',report['status'],'; native runtime: BLOCKED')
sys.exit(0 if report['status']=='PASS' else 1)
