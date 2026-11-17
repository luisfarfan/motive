#!/usr/bin/env python3
"""Kill only Motive's own mux helper to verify real output failure/recovery.

Requires a running, idle studio with ready visual sources. Production commands
use MCP. The process signal injects a real helper failure, not a mocked status.
No public output; recordings and evidence stay in ignored var/.
"""
import json
import os
import pathlib
import signal
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EXE = VERIFY.client_executable
report = {'ok': False, 'operations': [], 'recordings': []}
p = subprocess.Popen([str(EXE), 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def command(name, expect=True, **arguments):
    query = {'jsonrpc':'2.0', 'id':len(report['operations'])+1, 'method':'tools/call',
             'params':{'name':name, 'arguments':arguments}}
    p.stdin.write(json.dumps(query)+'\n'); p.stdin.flush()
    response = json.loads(p.stdout.readline())
    report['operations'].append({'request':query, 'response':response})
    value = json.loads(response['result']['content'][0]['text'])
    assert value['ok'] == expect, value
    return value


def state():
    return command('status')['state']


def wait_for(predicate, timeout=15):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        s = state()
        if predicate(s): return s
        time.sleep(.15)
    raise AssertionError(s)


try:
    p.stdin.write(json.dumps({'jsonrpc':'2.0','id':0,'method':'initialize',
        'params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'output-recovery','version':'1'}}})+'\n')
    p.stdin.flush()
    assert 'result' in json.loads(p.stdout.readline())
    original = state()
    assert original['output'] == 'idle' and not original['issues']
    command('select_audio', id='tone')
    wait_for(lambda s: not s['issues'])
    failed_path = command('start_recording')['state']['output_path']
    time.sleep(2)
    processes = subprocess.check_output(['ps','-axo','pid=,ppid=,comm='], text=True)
    helpers = []
    for line in processes.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts)==3 and int(parts[1])==original['pid'] and pathlib.Path(parts[2]).name=='obs-ffmpeg-mux':
            helpers.append(int(parts[0]))
    assert len(helpers)==1, helpers
    os.kill(helpers[0], signal.SIGTERM)
    failed = wait_for(lambda s: s['output']=='error' and s['output_code']!=0 and 'output' in s['recovery_sources'])
    command('select_audio', id='none')
    assert state()['recovery_required'], 'Audio must not acknowledge output failure'
    assert command('start_recording', expect=False)['error']['code']=='RECOVERY_REQUIRED'
    report['failure'] = {'state':failed, 'helper_pid':helpers[0], 'path':failed_path}
    command('select_audio', id='tone')
    command('reconnect_sources')
    wait_for(lambda s: not s['issues'] and not s['recovery_required'] and s['output_code']==0)
    for _ in range(3):
        for source in state()['project']['graph']['sources']:
            if source['spec']['kind']=='camera':
                command('reconnect_source', source_id=source['id'])
        wait_for(lambda s: not s['issues'] and not s['recovery_required'])
        path = command('start_recording')['state']['output_path']
        time.sleep(2)
        stopping = command('stop_output')['state']
        idle = wait_for(lambda s: s['output']=='idle')
        assert idle['output_code']==0
        info = json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
        video = next(s for s in info['streams'] if s['codec_type']=='video')
        assert video['codec_name']=='h264' and int(video['nb_read_frames'])>=45
        assert any(s['codec_name']=='aac' for s in info['streams'])
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',path,'-f','null','-'], capture_output=True, check=True)
        report['recordings'].append({'path':path,'duration':info['format']['duration'],
                                     'frames':video['nb_read_frames'],'stop_response':stopping['output']})
    command('select_audio', id=original['project']['audio'])
    report['ok'] = True
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    try: command('stop_output')
    except Exception: pass
    p.stdin.close(); p.wait(timeout=8)
    (ROOT/'var/evidence/output-recovery.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('operations','failure')},indent=2))
