#!/usr/bin/env python3
"""Observe the error returned after real owned-window loss; keep H1 unchanged."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from h7_support import Client
from verify_h14_collection import ROOT, default_owner, digest, lines, lock, require, save


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();lock();out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    report={'status':'FAIL','cleanup_errors':[]};client=fixture=None
    def wait(predicate):
        end=time.monotonic()+15
        while True:
            s=client.state()
            if predicate(s):return s
            require(time.monotonic()<end,'State deadline exceeded');time.sleep(.2)
    with (out/'fixture.jsonl').open('x') as log,(out/'fixture.stderr').open('x') as err:
        try:
            client=Client();default_owner(client.state());report['owner_pid']=client.state()['pid']
            binary=ROOT/'target/H21CaptureFixtureV4.app/Contents/MacOS/MotiveH21CaptureFixture'
            report['fixture_sha256']=digest(binary)
            fixture=subprocess.Popen([str(binary),'--seconds','90'],stdin=subprocess.PIPE,stdout=log,stderr=err,text=True)
            report['fixture_pid']=fixture.pid;end=time.monotonic()+10
            while True:
                row=next((r for r in lines(out/'fixture.jsonl') if r.get('windows') and isinstance(r['windows'][0]['bounds'],dict)),None)
                if row:break
                require(fixture.poll() is None and time.monotonic()<end,'Fixture not ready');time.sleep(.2)
            client.call('select_source',window_id=row['windows'][0]['window_id']);client.call('select_audio',id='tone')
            wait(lambda s:not s['issues'] and any(x['id']=='main' and x.get('capture_delivery')=='receiving' for x in s['sources']))
            report['started']=client.call('start_recording')['state'];time.sleep(3)
            fixture.stdin.write('quit\n');fixture.stdin.flush();fixture.wait(timeout=8)
            report['lost']=wait(lambda s:'SOURCE_UNAVAILABLE' in s['issues'] and s['output']=='idle')
            client.call('select_audio',id='none');client.call('select_audio',id='tone')
            response=client.call('start_recording',expect=False);report['rejected_start']=response
            report['historical_h1_code_match']=response['error']['code']=='SOURCE_UNAVAILABLE'
            require(not client.state()['outputs']['recording']['native_busy'],'Missing source must not start output')
            report['status']='PASS_DENIAL_OBSERVED'
        except Exception as error:report['error']=repr(error)
        finally:
            if client:
                try:
                    client.call('stop_output');wait(lambda s:s['output']=='idle')
                    client.call('select_source',window_id=None);client.call('select_audio',id='none')
                except Exception as error:report['cleanup_errors'].append(repr(error))
                client.close()
            if fixture and fixture.poll() is None:
                fixture.stdin.write('quit\n');fixture.stdin.flush();fixture.wait(timeout=8)
            report['fixture_exit']=fixture.poll() if fixture else None;save(out/'report.json',report)
    print(json.dumps({'status':report['status'],'code':report.get('rejected_start',{}).get('error',{}).get('code'),'error':report.get('error')}))
    return int(report['status']!='PASS_DENIAL_OBSERVED' or bool(report['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
