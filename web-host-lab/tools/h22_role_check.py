#!/usr/bin/env python3
"""Finite native role probe audit; a successful observation can prove BLOCKED."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def analyze(root):
    hashes={}
    def read(name):
        b=(root/name).read_bytes();hashes[name]=hashlib.sha256(b).hexdigest();return b
    report=json.loads(read('report.json'));raw=read('supervision.json.gz')
    if hashes['supervision.json.gz']!=report['supervision_gzip_sha256']:raise ValueError('SUPERVISION_HASH')
    supervision=json.loads(gzip.decompress(raw));stderr=read('supervisor-stderr.log').decode()
    rows=[]
    for line in stderr.splitlines():
        if not line.startswith('H22_BOUNDARY '):continue
        row=json.loads(line[len('H22_BOUNDARY '):])
        if row['role'] not in ('browser_host','gpu','renderer','network_service','storage_service','utility'):raise ValueError('ROLE')
        for field in ('after_cef_sandbox_initialize','seatbelt_argument','file_opened','loopback_connected'):
            if type(row[field]) is not bool:raise ValueError('BOOL')
        for field in ('file','loopback'):
            success=row[field+('_opened' if field=='file' else '_connected')]
            if (success and row[field+'_errno']!=0) or (not success and row[field+'_errno']<=0):raise ValueError('RESULT_ERRNO')
        identities={tuple(p['birth']) for sample in supervision['samples'] for p in sample.get('resource_usage',{}).get('processes',[]) if p['pid']==row['pid']}
        if len(identities)>1:raise ValueError('PID_REUSE')
        row['supervisor_birth']=list(next(iter(identities))) if identities else None
        row['attribution']='owned instrumented executable stderr; supervised PID/birth also observed' if identities else 'owned instrumented executable stderr only; short-lived PID not birth-attributed by sampler'
        rows.append(row)
    roles={row['role'] for row in rows}
    if not {'browser_host','gpu','renderer','network_service','storage_service','utility'}<=roles:raise ValueError('INCOMPLETE_ROLE_OBSERVATION')
    if not all(row['file_opened'] and row['loopback_connected'] for row in rows if row['role']=='browser_host'):raise ValueError('POSITIVE_CONTROL')
    if not report['owned_loopback_canary']['bound'] or not report['owned_loopback_canary']['closed'] or report['owned_loopback_canary']['accepted_connections']<1:raise ValueError('CANARY')
    if not supervision['final_cleanup_observed_tree']:raise ValueError('CLEANUP')
    return {'audit_status':'PASS','third_party_security':'BLOCKED','credential_configuration':'MOCK_LAB_ONLY',
        'rows':rows,'canary':report['owned_loopback_canary'],'input_sha256':hashes,
        'limits':['One own decoy file and one own loopback endpoint only; no general egress or filesystem certification.',
            'Probe runs after helper sandbox initialization and before framework load; not renderer JavaScript privilege.',
            'Browser and utility positive access, plus network service egress, require an OS capability boundary.',
            'No Keychain, credentials, devices, Internet destination or personal browser was tested.'],
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=analyze(a.root)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('audit_status','third_party_security','credential_configuration')}))
