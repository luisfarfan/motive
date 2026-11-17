#!/usr/bin/env python3
"""H9 real current-source failure, empty destination and shutdown during Fade.
Uses only the owned window fixture, pattern and tone. Never streams publicly.
"""
import os,signal
from h7_support import *
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
c=Client();report={'ok':False};pid=None;a=None;w=None;empty=None;source=None

def reopen(old):
    end=time.monotonic()+12
    while subprocess.run(['ps','-p',str(old)],capture_output=True).returncode==0:
        assert time.monotonic()<end,'Owner did not exit';time.sleep(.1)
    subprocess.run(['open',str(VERIFY.app_bundle)],check=True);time.sleep(2)
    return c.state()
try:
    project=setup_owned(c);a=project['graph']['active_scene'];assert len(project['graph']['scenes'])==1
    subprocess.run(['python3',str(ROOT/'scripts/window_fixture.py')],check=True,capture_output=True)
    old={x['pid'] for x in c.call('devices')['devices']['windows'] if x['bundle_id']=='local.motive.fixture'}
    subprocess.run(['open','-n',str(ROOT/'target/MotiveFixture.app')],check=True)
    end=time.monotonic()+10
    while True:
        windows=[x for x in c.call('devices')['devices']['windows'] if x['bundle_id']=='local.motive.fixture' and x['pid'] not in old]
        if windows:break
        assert time.monotonic()<end;time.sleep(.2)
    fixture=windows[0];pid=fixture['pid'];empty=c.call('create_scene',name='H9 empty')['state']['project']['graph']['active_scene']
    w=c.call('create_scene',name='H9 on-air window')['state']['project']['graph']['active_scene']
    c.call('add_source',scene_id=w,name='H9 disposable window',source={'kind':'window','window_id':fixture['id']})
    source=next(x['id'] for x in c.state()['project']['graph']['sources'] if x['name']=='H9 disposable window')
    c.wait(lambda s:not s['issues']);first=c.call('start_recording')['state'];time.sleep(2)
    rejected=c.call('select_scene',expect=False,scene_id=empty);assert rejected['error']['code']=='EMPTY_SCENE'
    c.call('configure_transition',transition={'kind':'fade','duration_ms':3000});pending=c.call('select_scene',scene_id=a)['state']
    assert pending['transition']['phase']=='running';time.sleep(.4);os.kill(pid,signal.SIGTERM);pid=None
    failure=c.wait(lambda s:s['transition']['phase']=='failed')
    assert failure['transition']['error']=='SCENE_CURRENT_FAILED' and failure['project']['graph']['active_scene']==w,failure
    stopped=c.wait(lambda s:s['output']=='idle');assert stopped['recovery_required'] and source in stopped['recovery_sources']
    report['current_source_failure']={'started':first,'pending':pending,'failed':failure,'stopped':stopped,'media':media(first['output_path'],1)}
    c.call('configure_transition',transition={'kind':'cut','duration_ms':0});c.call('select_scene',scene_id=a)
    assert not c.state()['recovery_required'];c.call('remove_scene',scene_id=w);w=None
    c.call('remove_source',source_id=source);source=None
    # Keep a second controlled scene for an idle preview Fade and output shutdown.
    c.call('add_layer',scene_id=empty,source_id='main')
    c.call('configure_transition',transition={'kind':'fade','duration_ms':500})
    c.call('select_scene',scene_id=empty);time.sleep(1.2)
    idle_fade=c.state();assert idle_fade['transition']['phase']=='completed' and idle_fade['output']=='idle'
    c.call('configure_transition',transition={'kind':'cut','duration_ms':0});c.call('select_scene',scene_id=a)
    # Exercise cancellation near native completion, then immediately start a
    # longer Fade. An old stop signal must not complete the new operation.
    boundary=[]
    for i in range(20):
        c.call('configure_transition',transition={'kind':'fade','duration_ms':100})
        pending=c.call('select_scene',scene_id=empty)['state'];time.sleep(.07 if i%2 else .10)
        cancelled=c.call('cancel_transition',operation_id=pending['transition']['operation_id'])['state']
        assert cancelled['transition']['phase'] in ('cancelled','completed')
        target=empty if cancelled['project']['graph']['active_scene']==a else a
        c.call('configure_transition',transition={'kind':'fade','duration_ms':400})
        started=time.monotonic();following=c.call('select_scene',scene_id=target)['state']
        assert following['transition']['operation_id']>pending['transition']['operation_id']
        end=c.wait(lambda s:s['transition']['phase']=='completed')
        elapsed=time.monotonic()-started;assert elapsed>=.35,(elapsed,following,end)
        boundary.append({'cancelled':cancelled['transition'],'next':end['transition'],'elapsed':elapsed})
        c.call('configure_transition',transition={'kind':'cut','duration_ms':0});c.call('select_scene',scene_id=a)
    report['cancel_completion_boundary']=boundary
    second=c.call('start_recording')['state'];time.sleep(2)
    c.call('configure_transition',transition={'kind':'fade','duration_ms':5000});pending=c.call('select_scene',scene_id=empty)['state'];time.sleep(.3)
    start=time.monotonic();shutdown=c.call('request_shutdown')['state'];assert time.monotonic()-start<1
    assert shutdown['transition']['phase']=='cancelled' and shutdown['project']['graph']['active_scene']==a
    report['shutdown']={'started':second,'pending':pending,'requested':shutdown,'elapsed_command':time.monotonic()-start,'reopened':reopen(second['pid']),'media':media(second['output_path'],1)}
    empty=None;a=c.state()['project']['graph']['active_scene'];report['idle_fade']=idle_fade
    report['bundle_sha256']=hashlib.sha256((VERIFY.app_executable).read_bytes()).hexdigest()
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        s=c.state();c.call('cancel_transition',operation_id=s['transition']['operation_id'])
        if s['output'] not in ('idle','error'):c.stop()
        c.call('configure_transition',transition={'kind':'cut','duration_ms':0})
        if a:c.call('select_scene',scene_id=a)
        for sid in (w,empty):
            if sid:c.call('remove_scene',scene_id=sid)
        if source:c.call('remove_source',source_id=source)
        c.call('select_audio',id='none')
    except Exception as e:report['cleanup_error']=repr(e)
    if pid:os.kill(pid,signal.SIGTERM)
    report['operations']=c.ops;c.close();(EVIDENCE/'h9-faults.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'ok':report['ok'],'error':report.get('error')}))
