#!/usr/bin/env python3
"""Restart the signed app without its optional VT module; prove real x264 fallback.

Uses normal per-process launch environment (never launchctl/TCC/global settings).
Requires an idle disposable production with owned patterns/overlays only.
Production changes go through CLI; the stdio MCP selection path is tested by
verify_control.py and verify_encoding.py. Restores the project and auto mode.
"""
import json
import os
import pathlib
import subprocess
import time
from h7_support import assert_project_format

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXE=ROOT/'target/debug/motive'
APP=ROOT/'target/Motive.app'
OUT=ROOT/'var/evidence'
report={'ok':False,'responses':[]}


def ctl(op, expect=True, **fields):
    process=subprocess.run([str(EXE),'ctl',json.dumps({'op':op,**fields})],capture_output=True,text=True,timeout=15)
    value=json.loads(process.stdout);report['responses'].append({'op':op,'fields':fields,'result':value})
    assert value['ok']==expect,value
    return value


def state():return ctl('status')['state']


def wait_for(predicate, timeout=15):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        s=state()
        if predicate(s):return s
        time.sleep(.2)
    raise AssertionError(s)


def restart(disabled):
    s=state();assert s['output']=='idle',s['output']
    ctl('shutdown')
    until=time.monotonic()+15
    while True:
        try:os.kill(s['pid'],0)
        except ProcessLookupError:break
        assert time.monotonic()<until,'Native shutdown did not finish'
        time.sleep(.2)
    name='encoding-disabled' if disabled else 'encoding-restored'
    subprocess.run(['open','--env',f'MOTIVE_DISABLE_VIDEOTOOLBOX={int(disabled)}',
                    '--stdout',str(OUT/(name+'.log')),'--stderr',str(OUT/(name+'-stderr.log')),str(APP)],check=True)
    until=time.monotonic()+15
    while not (ROOT/'var/run/motive.sock').exists():
        assert time.monotonic()<until,'Studio did not start'
        time.sleep(.2)
    opened=state();assert opened['pid']!=s['pid']
    return opened


def record():
    ctl('select_audio',id='tone')
    wait_for(lambda s:not s['issues'])
    started=ctl('start_recording')['state'];time.sleep(4)
    ctl('stop_output');ended=wait_for(lambda s:s['output']=='idle')
    assert ended['output_code']==0
    path=started['output_path']
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
    v=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert v['codec_name']=='h264' and int(v['nb_read_frames'])>100
    assert any(s['codec_name']=='aac' for s in probe['streams'])
    decode=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',path,'-f','null','-'],capture_output=True,check=True)
    assert not decode.stderr,decode.stderr
    return {'started':started,'ended':ended,'probe':probe}


original=None;disabled=False
try:
    original=state();assert original['output']=='idle'
    assert all(s['spec']['kind'] in ('pattern','overlay') for s in original['project']['graph']['sources'])
    project=ctl('save_project')['state']['project'];assert_project_format(project,3,original['project'].get('video'))
    restarted=restart(True);disabled=True
    assert restarted['encoding']['preference']=='auto'
    inventory=ctl('encoders')['encoders']
    assert not inventory['videotoolbox_loaded'] and inventory['videotoolbox_id'] is None
    assert inventory['unavailable_reason']=='VIDEOTOOLBOX_DISABLED'
    rev=state()['revision']
    assert ctl('set_encoder',expect=False,encoder='videotoolbox')['error']['code']=='ENCODER_UNAVAILABLE'
    assert state()['revision']==rev
    assert ctl('load_project')['state']['project']==project
    fallback=record()
    encoding=fallback['started']['encoding']
    assert encoding['selected_id']=='obs_x264' and not encoding['selected_hardware']
    assert encoding['fallback_reason']=='VIDEOTOOLBOX_DISABLED'
    report['fallback']=fallback
    restart(False);disabled=False
    assert ctl('load_project')['state']['project']==project
    restored=record()
    encoding=restored['started']['encoding']
    assert encoding['selected_hardware'] and encoding['fallback_reason'] is None
    assert encoding['selected_id']==encoding['videotoolbox_id']
    report['restored_hardware']=restored
    report['ok']=True
except BaseException as error:
    report['error']=repr(error);raise
finally:
    try:
        ctl('stop_output');wait_for(lambda s:s['output']=='idle')
        if disabled:restart(False)
        if original:
            ctl('select_audio',id=original['project']['audio'])
            ctl('set_encoder',encoder='auto')
    except Exception as cleanup_error:report['cleanup_error']=repr(cleanup_error)
    (OUT/'encoding-fallback.json').write_text(json.dumps(report,indent=2))
print('Optional-module absence -> real x264 recording; restart -> hardware recording: PASS')
