"""Owned routing diagnostic, never an OS confinement or credential certificate."""
import hashlib
import ipaddress
import json
import re


def inspect_netlog(data,proxy_connections,direct_connections,component_manifests):
    if len(data)>=7*1024**2:raise ValueError('NETLOG_POSSIBLE_RING_TRUNCATION')
    log=json.loads(data);types=log['constants']['logEventTypes'];reverse={v:k for k,v in types.items()}
    if not {'TCP_CONNECT_ATTEMPT','UDP_CONNECT','REQUEST_ALIVE','URL_REQUEST_START_JOB',
        'HTTP_STREAM_JOB_CONTROLLER','PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST'}<=set(types):raise ValueError('NETLOG_EVENT_SCHEMA')
    attempts=[]
    for event in log['events']:
        name=reverse.get(event['type'],'UNKNOWN');params=event.get('params',{})
        if name not in ('TCP_CONNECT_ATTEMPT','UDP_CONNECT') or 'address' not in params:continue
        address=params['address'];match=re.fullmatch(r'(?:\[([^\]]+)\]|([^:]+)):(\d+)',address)
        if not match:raise ValueError('NETLOG_ADDRESS_SCHEMA')
        ip=ipaddress.ip_address(match[1] or match[2]);port=int(match[3])
        attempts.append({'type':name,'approved_owned_proxy':ip.is_loopback and port==18719,
            'address_sha256':hashlib.sha256(address.encode()).hexdigest()})
    control='http://127.0.0.1:18720/h22-owned-proxy-control'
    request_ids={e['source']['id'] for e in log['events'] if reverse.get(e['type'])=='REQUEST_ALIVE'
        and e.get('params',{}).get('url')==control}
    controller_ids={e['source']['id'] for e in log['events'] if reverse.get(e['type'])=='HTTP_STREAM_JOB_CONTROLLER'
        and e.get('params',{}).get('url')==control}
    ends=[e.get('params',{}).get('net_error') for e in log['events'] if reverse.get(e['type'])=='URL_REQUEST_START_JOB'
        and e['source']['id'] in request_ids and e.get('phase')==log['constants']['logEventPhase']['PHASE_END']]
    proxies=[e.get('params',{}).get('proxy_info') for e in log['events']
        if reverse.get(e['type'])=='PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST' and e['source']['id'] in controller_ids]
    control_ok=len(request_ids)==len(controller_ids)==1 and ends==[-130] and proxies==['PROXY 127.0.0.1:18719']
    passed=control_ok and not attempts and proxy_connections==direct_connections==0 and not component_manifests
    return {'status':'PASS' if passed else 'FAIL','netlog_sha256':hashlib.sha256(data).hexdigest(),
        'policy':'closed-resolver-v2','owned_control_resolution_rejected':control_ok,'owned_control_errors':ends,
        'events':len(log['events']),'socket_attempts':attempts,'proxy_connections':proxy_connections,
        'direct_target_connections':direct_connections,'component_manifests':component_manifests,
        'scope':'default redacted Chromium NetLog, positively observed owned request failure before socket creation; not complete OS egress observation',
        'security_third_party':'BLOCKED','credential_backend':'MOCK_LAB_ONLY',
        'limits':['Proxy/host rules do not confine a compromised native process or non-Chromium network stack.',
            'No conclusion about real Keychain or all filesystem/IPC capabilities.',
            'Updater disabled for owned laboratory workload reproducibility, not a production update strategy.']}
