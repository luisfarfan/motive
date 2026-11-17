#!/usr/bin/env python3
"""Real local RTMP and recording, typed profiles, refusal/loss/recovery via MCP.
Only connects to 127.0.0.1. Requires FFmpeg and a signed idle Motive.
"""
import os,signal,socket
from h7_support import *
c=Client();receiver=None;report={'ok':False,'checks':[]}
def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def listen(port,label):
    path=EVIDENCE/f'h7-{label}-{time.time_ns()}.flv'
    log=(EVIDENCE/f'h7-{label}-receiver.log').open('w')
    p=subprocess.Popen(['ffmpeg','-nostdin','-v','info','-listen','1','-i',f'rtmp://127.0.0.1:{port}/live/motive','-c','copy',str(path)],stdout=subprocess.DEVNULL,stderr=log)
    log.close();deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        assert p.poll() is None,'Receiver exited before listening'
        found=subprocess.run(['lsof','-a','-p',str(p.pid),'-iTCP:'+str(port),'-sTCP:LISTEN'],capture_output=True)
        if found.returncode==0:return p,path
        time.sleep(.1)
    p.terminate();p.wait();raise AssertionError('No receiver listener')
try:
    project=setup_owned(c);before=c.state();base=c.call('output_profiles')['store'];assert base['version']==1
    caps=c.call('output_capabilities')['capabilities']
    assert caps['canvas']['fps_configurable'] is True
    assert caps['canvas']['production_resolution_configurable'] is True
    assert caps['canvas']['profile_resolution_configurable'] is False
    assert caps['canvas']['configuration']['fps']==30
    if before['output_configuration']['endpoint'] is None:
        assert c.call('preflight_output',expect=False,target='streaming')['error']['code']=='ENDPOINT_REQUIRED'
    else:
        assert not c.call('preflight_output',target='streaming')['preflight']['network_tested']
    p=profile('local-test',bitrate=1800,keyframes=1)
    c.call('upsert_output_profile',profile=p)
    for target in ('recording','streaming'):c.call('select_output_profile',target=target,profile_id=p['id'])
    assert c.call('remove_output_profile',expect=False,id=p['id'])['error']['code']=='PROFILE_IN_USE'
    revision=c.state()['revision']
    for bad in [dict(p,bitrate_kbps=0),dict(p,keyframe_seconds=0),dict(p,width=1920),dict(p,fps=60),dict(p,rate_control='vbr')]:
        c.call('upsert_output_profile',expect=False,profile=bad);assert c.state()['revision']==revision
    marker='OWNED_SECRET_REJECTION_PROBE'
    for bad in [{'transport':'rtmp','port':19351,'key':marker},{'transport':'rtmp','port':19351,'host':'example.com'},{'transport':'rtmp','port':0},{'transport':marker,'port':19351}]:
        rejected=c.call('configure_stream',expect=False,endpoint=bad);assert marker not in json.dumps(rejected)
        assert c.state()['revision']==revision
    c.call('save_output_profiles');c.call('upsert_output_profile',profile=dict(p,bitrate_kbps=1900));c.call('load_output_profiles')
    assert c.state()['output_configuration']['recording']==p and c.state()['project']==project
    pf=c.call('preflight_output',target='recording')['preflight'];assert pf['ready'] and not pf['network_tested']
    started=c.call('start_recording')['state'];record_metrics=measure(c,8,'recording');stopped=c.stop()
    record_media=media(started['output_path'],7,pixels=True);assert record_media['max_keyframe_gap']<=1.1
    report['recording']={'started':started,'stop':stopped,'metrics':record_metrics,'media':record_media}
    port=free_port();receiver,path=listen(port,'rtmp')
    c.call('configure_stream',endpoint={'transport':'rtmp','port':port});assert c.call('preflight_output',target='streaming')['preflight']['ready']
    started=c.call('start_stream')['state'];assert started['output'] in ('connecting','streaming')
    ready=c.wait(lambda s:s['output']=='streaming');assert ready['encoding']['selected_hardware']
    for op,args in [('start_recording',{}),('configure_stream',{'endpoint':{'transport':'rtmp','port':port}}),('upsert_output_profile',{'profile':p})]:
        assert c.call(op,expect=False,**args)['error']['code']=='OUTPUT_BUSY'
    metrics=measure(c,20,'streaming');stopped=c.stop();assert stopped['end']['output']=='idle'
    receiver.wait(timeout=10);receiver=None
    streamed=media(path,18,pixels=True);assert streamed['max_keyframe_gap']<=1.1
    assert c.state()['project']==project
    assert stopped['end']['stats']['output_dropped_frames']==0
    assert stopped['end']['stats']['video_skipped_frames']==ready['stats']['video_skipped_frames']
    assert stopped['end']['stats']['lagged_frames']==ready['stats']['lagged_frames']
    report['stream']={'started':started,'ready':ready,'stop':stopped,'metrics':metrics,'media':streamed}
    # Connection refused; preflight is explicitly not a network probe.
    port=free_port();c.call('configure_stream',endpoint={'transport':'rtmp','port':port});c.call('start_stream')
    refused=c.wait(lambda s:s['output']=='error');assert refused['output_code']==-2 and refused['recovery_required']
    assert c.call('start_stream',expect=False)['error']['code']=='RECOVERY_REQUIRED'
    c.call('select_audio',id='tone');assert c.state()['recovery_required']
    c.call('recover_output');assert not c.state()['recovery_required'] and c.state()['project']==project
    report['refused']=refused
    port=free_port();receiver,path=listen(port,'disconnected');c.call('configure_stream',endpoint={'transport':'rtmp','port':port});c.call('start_stream');c.wait(lambda s:s['output']=='streaming')
    time.sleep(3);receiver.terminate();receiver.wait(timeout=10);receiver=None
    lost=c.wait(lambda s:s['output']=='error');assert lost['output_code']==-5 and lost['recovery_required']
    time.sleep(2);assert c.state()['output']=='error','Must not silently reconnect'
    c.call('recover_output');assert c.state()['project']==project
    report['disconnected']=lost
    receiver,path=listen(port,'recovered');c.call('start_stream');c.wait(lambda s:s['output']=='streaming');time.sleep(4)
    stop=c.stop();receiver.wait(timeout=10);receiver=None
    report['recovered']={'stop':stop,'media':media(path,3,pixels=True)}
    assert c.state()['project']==project
    tools=c.rpc('tools/list')['tools'];assert all(t['annotations']['destructiveHint'] for t in tools if t['name'] in ('shutdown','load_project','remove_source','save_output_profiles'))
    assert next(t for t in tools if t['name']=='set_test_window')['_meta']['motive/category']=='development'
    report['checks']=['same project throughout recording/RTMP','typed profile bounds and unsupported geometry rejected','secret-bearing fields rejected without echo','explicit profile save/load','RTMP H264/AAC+overlay decoded','controlled stop','connection refused','receiver loss, no automatic retry, explicit recovery','MCP destructive/development annotations']
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        c.stop()
        if c.state()['output']=='error':c.call('recover_output')
        for target in ('recording','streaming'):c.call('select_output_profile',target=target,profile_id='standard')
        c.call('remove_output_profile',id='local-test');c.call('save_output_profiles');c.call('select_audio',id='none')
    except Exception as e:report['cleanup_error']=repr(e)
    if receiver and receiver.poll() is None:receiver.terminate();receiver.wait(timeout=8)
    report['operations']=c.ops;c.close();(EVIDENCE/'h7-rtmp.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k in ('ok','checks','error')},indent=2))
