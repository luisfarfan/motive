"""Read-only strict classification of bounded native XPC evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def classify(r):
    p = r['reply']
    # NSJSONSerialization emits NSNumber(@(int-expression)) as integer 0.
    # No strings, missing values, null or arbitrary falsy values are accepted.
    denied = p.get('direct_file_opened') is False or (type(p.get('direct_file_opened')) is int and p['direct_file_opened'] == 0)
    return bool(r.get('returncode') == 0 and r.get('reason') == 'exit'
        and r.get('remaining_observed_pids') == [] and r.get('service_pid_observed') is True
        and denied and p.get('file_errno') in (1,13)
        and p.get('network_connect_return') == -1 and p.get('network_errno') in (1,13)
        and r.get('service_endpoint_connections') == 0
        and r.get('owned_listener_positive_control') is True and r.get('owned_file_positive_control') is True
        and p.get('capability_read_verified') is True and p.get('capability_bytes') == 28
        and p.get('keychain_called') is False and p.get('cef_loaded') is False)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    data=(a.root/'report.json').read_bytes();r=json.loads(data)
    result={'status':'PASS' if classify(r) else 'FAIL','scope':r['scope'],
        'original_status':r['status'],'original_report_sha256':hashlib.sha256(data).hexdigest(),
        'original_stdout_sha256':hashlib.sha256((a.root/'stdout.log').read_bytes()).hexdigest(),
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'keychain':'NOT_CALLED','cef':'NOT_LOADED','production_credentials':'BLOCKED'}
    with (a.root/'boundary-reclassification.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
