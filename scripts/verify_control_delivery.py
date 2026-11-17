#!/usr/bin/env python3
"""Real local control framing with delayed/fragmented delivery on macOS.
Requires the running signed app; sends read-only shared-core status commands.
No mutation retry or mock server. The listener's nonblocking accept must not
make a newly accepted peer reject a valid frame before its bytes arrive.
"""
import json,pathlib,socket,time,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
report={'ok':False,'cases':[]}
try:
    for delay,fragmented in ((0,False),(.03,False),(.1,False),(.2,False),(.03,True),(.1,True)):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(2);start=time.monotonic();peer.connect(str(ROOT/'var/run/motive.sock'))
            payload=b'{"origin":"mcp","command":{"op":"status"}}\n';time.sleep(delay)
            if fragmented:
                peer.sendall(payload[:12]);time.sleep(.05);peer.sendall(payload[12:-1]);time.sleep(.03);peer.sendall(payload[-1:])
            else:peer.sendall(payload)
            response=json.loads(peer.makefile().readline());elapsed=time.monotonic()-start
            assert response['ok'] and elapsed<1,response
            report['cases'].append({'delay':delay,'fragmented':fragmented,'elapsed':elapsed,'response':response})
    assert len({x['response']['state']['pid'] for x in report['cases']})==1
    report['bundle_sha256']=hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:(ROOT/'var/evidence/h9-control-delivery.json').write_text(json.dumps(report,indent=2))
print('Delayed and fragmented real shared-core status delivery: PASS')
