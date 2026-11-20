#!/usr/bin/env python3
"""Bounded, separately sealed CEF/App Sandbox compatibility diagnostic.

Uses only the explicit laboratory mock Keychain backend. Does not test or call
real credentials. Successful initialization would not establish confinement.
Run under h22_with_lock.py; no sandbox exception or child sandbox bypass.
"""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from h22_process_snapshot import NativeSnapshot
from run_owned_fixture import collect_process_logs, invoke_supervisor, verify_inventory

LAB=Path(__file__).resolve().parents[1]
BUILD='h22-native-multi-appsandbox1-ephemeral'


def main():
    output=LAB/'evidence/H22-cef-appsandbox-r1';output.mkdir(mode=0o700)
    build=LAB/'.cache'/BUILD
    build_path=LAB/'evidence'/(BUILD.replace('h22-','H22-',1)+'-build.json')
    report=json.loads(build_path.read_text())
    if report.get('app_sandbox_probe') is not True or report['credential_backend']!='chromium-use-mock-keychain':
        raise ValueError('EXPLICIT_SANDBOX_LAB_BUILD_REQUIRED')
    verify_inventory(build,report,report['binaries'][0]['sha256'])
    private=LAB/'.cache/H22-cef-appsandbox-r1';private.mkdir(mode=0o700)
    expected=Path.home()/'Library/Containers/org.motive.lab.h22.cefsandbox/Data/Library/Caches/motive-h22-220500'
    if expected.exists():raise ValueError('FRESH_CONTAINER_RUN_REQUIRED')
    spec=importlib.util.spec_from_file_location('h22_cef_sandbox_supervisor',LAB/'poc/browser-host/supervisor.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    observer=NativeSnapshot(module)
    supervisor=module.Supervisor(private,deadline_seconds=15,rss_limit_kib=2048*1024,
        interval_seconds=.1,sample_capacity=256,inspect_roles=True,process_snapshot=observer)
    result={'status':'BLOCKED','scope':'CEF 150 App Sandbox compatibility only',
        'native_host_executed':False,'native_host_execution_attempted':False,
        'cef_sandbox_disabled':False,'real_keychain_authorized':False,'real_keychain_access_measured':False,
        'credential_backend':'chromium-use-mock-keychain','third_party_content_allowed':False,
        'build_report_sha256':hashlib.sha256(build_path.read_bytes()).hexdigest(),
        'main_sha256':report['binaries'][0]['sha256'],'entitlements':report['app_sandbox_entitlements']}
    command=[str(build/'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'),
        '--owned-multi',str(private),'220500','640','360','30','3000','1','steady']
    raw=invoke_supervisor(supervisor,command,result)
    data=(json.dumps(raw,separators=(',',':'))+'\n').encode();(output/'supervision.json.gz').write_bytes(gzip.compress(data,mtime=0))
    result['supervision_sha256']=hashlib.sha256(data).hexdigest()
    result['supervision']={k:v for k,v in raw.items() if k!='samples'}
    result['process_observer']=observer.report()
    result['diagnostic_streams']=collect_process_logs(private,output,raw)
    files=[]
    if expected.is_dir():
        for path in sorted(expected.rglob('*')):
            if path.is_symlink() or not path.is_file() or path.suffix not in ('.json','.jsonl','.bgra'):continue
            if 'cache' in path.relative_to(expected).parts:continue
            if path.stat().st_size>16*1024**2:raise ValueError('EVIDENCE_LIMIT')
            payload=path.read_bytes();relative=path.relative_to(expected)
            target=output/'native'/(str(relative)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.compress(payload,mtime=0));files.append({'path':str(relative),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
    result['native_evidence']=files
    result['initialized']=any(x['path']=='instances.json' for x in files)
    if raw.get('returncode')==0 and raw.get('final_cleanup_observed_tree') and result['initialized']:
        result['status']='PARTIAL';result['result']='CEF initialized and emitted frames; security not certified'
    else:result['result']='CEF deployment compatibility not established; no permission relaxation authorized by this probe'
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','result','initialized','native_host_executed')},indent=2))


if __name__=='__main__':main()
