#!/usr/bin/env python3
"""Build/run a one-use App Sandbox/XPC capability probe, never CEF/Keychain.

Call under h22_with_lock.py. The private embedded service is launchd-owned, so
the watchdog additionally attributes its exact executable path and PID/birth.
No personal signing identity, permission changes, arbitrary endpoint or files.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import subprocess
import sys
import time

LAB=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--name',required=True)
    a=parser.parse_args()
    if not a.name.startswith('H22-xpc-') or not a.name.replace('-','').isalnum():raise ValueError('FIXED_NAME')
    output=LAB/'evidence'/a.name;output.mkdir(mode=0o700)
    root=LAB/'.cache'/a.name;root.mkdir(mode=0o700)
    decoy=root/'denied-decoy';decoy.write_bytes(b'MOTIVE_H22_OWNED_CAPABILITY\n');decoy.chmod(0o600)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(4);listener.settimeout(.05)
    port=listener.getsockname()[1]
    # A live endpoint and same-user readable file are actual positive controls.
    control=socket.create_connection(('127.0.0.1',port),timeout=1);accepted,_=listener.accept();accepted.close();control.close()
    config=root/'probe_config.h';config.write_text('#define H22_DECOY '+json.dumps(str(decoy))+'\n#define H22_PORT '+str(port)+'\n')
    bundle=root/'MotiveH22Probe.app';contents=bundle/'Contents'
    service=contents/'XPCServices/org.motive.lab.h22.boundary.xpc/Contents'
    (contents/'MacOS').mkdir(parents=True);(service/'MacOS').mkdir(parents=True)
    owner_binary=contents/'MacOS/MotiveH22Probe';service_binary=service/'MacOS/H22Boundary'
    logs=[]
    def run(command):
        r=subprocess.run([str(x) for x in command],capture_output=True,timeout=90)
        logs.append({'command':[str(x) for x in command],'returncode':r.returncode,
                     'output':(r.stdout+r.stderr).decode(errors='replace')[:65536]})
        (output/'build-progress.json').write_text(json.dumps(logs,indent=2)+'\n')
        if r.returncode:raise ValueError('BUILD_OR_SIGNATURE_FAILED')
    for source,binary in [('owner.m',owner_binary),('service.m',service_binary)]:
        run(['clang','-arch','arm64','-mmacosx-version-min=15.0','-fobjc-arc','-fblocks','-O2',
             '-Wall','-Wextra','-Werror','-I'+str(root),LAB/'poc/security-xpc'/source,'-framework','Foundation','-o',binary])
    common={'CFBundleVersion':'1','CFBundleShortVersionString':'0.1','LSMinimumSystemVersion':'15.0'}
    (contents/'Info.plist').write_bytes(plistlib.dumps({**common,'CFBundleIdentifier':'org.motive.lab.h22.probe',
        'CFBundleName':'MotiveH22Probe','CFBundleExecutable':'MotiveH22Probe','CFBundlePackageType':'APPL','LSUIElement':True}))
    (service/'Info.plist').write_bytes(plistlib.dumps({**common,'CFBundleIdentifier':'org.motive.lab.h22.boundary',
        'CFBundleName':'H22Boundary','CFBundleExecutable':'H22Boundary','CFBundlePackageType':'XPC!',
        'XPCService':{'ServiceType':'Application','RunLoopType':'dispatch_main'}}))
    entitlements=root/'service.entitlements';entitlements.write_bytes(plistlib.dumps({'com.apple.security.app-sandbox':True}))
    run(['codesign','--force','--sign','-','--timestamp=none','--entitlements',entitlements,service.parent])
    run(['codesign','--force','--sign','-','--timestamp=none',bundle])
    run(['codesign','--verify','--strict','--deep',bundle])
    run(['codesign','-d','--entitlements',':-',service_binary])
    (output/'build.json').write_text(json.dumps({'steps':logs,'binaries':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (owner_binary,service_binary)},'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (LAB/'poc/security-xpc').iterdir() if p.is_file()},'entitlements':{'com.apple.security.app-sandbox':True},
        'cef_loaded':False,'keychain_called':False},indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('h22_supervisor',LAB/'poc/browser-host/supervisor.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    known={};samples=[];hits=0;reason='exit';child=None
    def observe():
        table=module.snapshot()
        commands=subprocess.check_output(['ps','-axo','pid=,command='],text=True,timeout=2)
        for line in commands.splitlines():
            words=line.strip().split(None,1)
            if len(words)==2 and (words[1]==str(service_binary) or words[1].startswith(str(service_binary)+' ')):
                process=table.get(int(words[0]))
                if process:known[process.identity]=process
        if child and child.pid in table:known[table[child.pid].identity]=table[child.pid]
        current=[p for identity,p in known.items() if module.birth_identity(p.pid)==identity[1]]
        samples.append({'elapsed_ms':round((time.monotonic()-start)*1000,3),
                        'processes':[{'pid':p.pid,'birth':p.birth,'rss_kib':table[p.pid].rss_kib if p.pid in table else None} for p in current]})
        return current
    start=time.monotonic()
    try:
        with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
            child=subprocess.Popen([str(owner_binary)],cwd=root,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                close_fds=True,start_new_session=True,env={'PATH':'/usr/bin:/bin','LANG':'C','TMPDIR':str(root)})
            while time.monotonic()-start<15:
                current=observe()
                rss=sum(p['rss_kib'] or 0 for p in samples[-1]['processes'])
                if rss>256*1024:reason='rss_limit';break
                try:connection,_=listener.accept();connection.close();hits+=1
                except socket.timeout:pass
                if child.poll() is not None and not current:break
                time.sleep(.05)
            else:reason='deadline'
    finally:
        listener.close()
        for identity,p in known.items():
            if module.birth_identity(p.pid)==identity[1]:os.kill(p.pid,signal.SIGTERM)
        if child:
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)
        end=time.monotonic()+2
        while time.monotonic()<end and any(module.birth_identity(p.pid)==identity[1] for identity,p in known.items()):time.sleep(.05)
        remaining=[p.pid for identity,p in known.items() if module.birth_identity(p.pid)==identity[1]]
        for identity,p in known.items():
            if p.pid in remaining and module.birth_identity(p.pid)==identity[1]:os.kill(p.pid,signal.SIGKILL)
        if remaining:time.sleep(.2)
        remaining=[p.pid for identity,p in known.items() if module.birth_identity(p.pid)==identity[1]]
    text=(output/'stdout.log').read_text();reply=json.loads(text) if text.strip() else {}
    result={'status':'PARTIAL','scope':'one real sandboxed XPC service, NOT a CEF sandbox deployment',
        'reply':reply,'returncode':child.returncode,'reason':reason,'supervisor_samples':samples,
        'owned_listener_positive_control':True,'owned_file_positive_control':decoy.read_bytes()==b'MOTIVE_H22_OWNED_CAPABILITY\n',
        'service_endpoint_connections':hits,'remaining_observed_pids':remaining,
        'service_pid_observed':reply.get('pid') in [i[0] for i in known],
        'keychain':'NOT_CALLED','cef':'NOT_LOADED','production_credentials':'BLOCKED'}
    result['scoped_boundary_pass']=bool(child.returncode==0 and reason=='exit' and not remaining and result['service_pid_observed']
        and reply.get('direct_file_opened') is False and reply.get('file_errno') in (1,13)
        and reply.get('network_errno') in (1,13) and hits==0 and reply.get('capability_read_verified') is True)
    if not result['scoped_boundary_pass']:result['status']='FAIL'
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='supervisor_samples'},indent=2))
    return 0 if result['scoped_boundary_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
