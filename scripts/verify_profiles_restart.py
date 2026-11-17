#!/usr/bin/env python3
"""Explicit profile-v1 and scene-v3 save/restart/load, via the shared core only."""
import os
from h7_support import *
c=Client();report={'ok':False}
try:
    original=c.state();assert original['output']=='idle'
    assert all(s['spec']['kind'] in ('pattern','overlay') for s in original['project']['graph']['sources'])
    p=profile('persist-test',encoder='x264',bitrate=2100,keyframes=3,reorder=False)
    c.call('upsert_output_profile',profile=p);c.call('select_output_profile',target='streaming',profile_id=p['id'])
    c.call('configure_stream',endpoint={'transport':'rtmp','port':19351});c.call('save_output_profiles')
    project=c.call('save_project')['state']['project'];old_pid=c.state()['pid'];c.call('shutdown')
    until=time.monotonic()+15
    while True:
        try:os.kill(old_pid,0)
        except ProcessLookupError:break
        assert time.monotonic()<until
        time.sleep(.2)
    subprocess.run(['open','--stdout',str(EVIDENCE/'h7-restart-runtime.log'),'--stderr',str(EVIDENCE/'h7-restart-stderr.log'),str(ROOT/'target/Motive.app')],check=True)
    until=time.monotonic()+15
    while not (ROOT/'var/run/motive.sock').exists():
        assert time.monotonic()<until
        time.sleep(.2)
    boot=c.state();assert boot['pid']!=old_pid
    assert boot['output_configuration']['endpoint'] is None and boot['output_configuration']['streaming_profile']=='standard'
    assert c.call('load_project')['state']['project']==project
    c.call('load_output_profiles')
    restored=c.call('output_profiles')['store'];assert p in restored['profiles']
    c.call('select_output_profile',target='streaming',profile_id=p['id'])
    assert c.call('preflight_output',expect=False,target='streaming')['error']['code']=='ENDPOINT_REQUIRED'
    assert c.state()['project']==project
    # The saved set may omit the former default ID. Loading must still be usable.
    c.call('select_output_profile',target='recording',profile_id=p['id']);c.call('remove_output_profile',id='standard');c.call('save_output_profiles')
    c.call('upsert_output_profile',profile=profile('standard',encoder='auto'))
    c.call('select_output_profile',target='recording',profile_id='standard');c.call('load_output_profiles')
    assert c.state()['output_configuration']['recording_profile']==p['id']
    report.update({'ok':True,'before':original,'after_restart':boot,'restored':restored,'final':c.state()})
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        c.call('upsert_output_profile',profile=profile('standard',encoder='auto'))
        for target in ('recording','streaming'):c.call('select_output_profile',target=target,profile_id='standard')
        c.call('remove_output_profile',id='persist-test');c.call('save_output_profiles')
    except Exception as e:report['cleanup_error']=repr(e)
    report['operations']=c.ops;c.close();(EVIDENCE/'h7-profiles-restart.json').write_text(json.dumps(report,indent=2))
print('Profiles v1 survive explicit save/restart/load; scene v3 preserved; runtime endpoint resets: PASS')
