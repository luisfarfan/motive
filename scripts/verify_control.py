#!/usr/bin/env python3
"""Exercise the real stdio MCP adapter and the running studio's Unix socket."""
import json,pathlib,subprocess,time
root=pathlib.Path(__file__).resolve().parents[1]
exe=str(root/'target/debug/motive')
def status():
    return json.loads(subprocess.check_output([exe,'ctl','{"op":"status"}'],text=True))['state']
before=status()
p=subprocess.Popen([exe,'mcp'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
messages=[]
def rpc(method,params=None):
    request={'jsonrpc':'2.0','id':len(messages)+1,'method':method,'params':params or {}}
    p.stdin.write(json.dumps(request)+'\n');p.stdin.flush()
    result=json.loads(p.stdout.readline());messages.append({'request':request,'response':result});return result
try:
    init=rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'motive-integration','version':'1'}})
    assert init['result']['protocolVersion']=='2025-06-18'
    p.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');p.stdin.flush()
    listed=rpc('tools/list')['result']['tools']
    assert len(listed)==12
    assert {'select_camera','select_audio','reconnect_sources'} <= {t['name'] for t in listed}
    invalid=rpc('tools/call',{'name':'start_recording','arguments':{'path':'/not-allowed'}})
    assert invalid['result']['isError']
    assert status()['revision']==before['revision']
    changed=rpc('tools/call',{'name':'set_overlay','arguments':{'visible':False}})
    state=json.loads(changed['result']['content'][0]['text'])['state']
    observed=status()
    assert state['pid']==observed['pid']==before['pid']
    assert not observed['project']['overlay'] and state['revision']==observed['revision']
    changed_audio=rpc('tools/call',{'name':'select_audio','arguments':{'id':'tone'}})
    assert not changed_audio['result']['isError']
    assert status()['project']['audio']=='tone'
    restore_audio=rpc('tools/call',{'name':'select_audio','arguments':{'id':before['project']['audio']}})
    assert not restore_audio['result']['isError']
    invalid_camera=rpc('tools/call',{'name':'select_camera','arguments':{'id':'motive-nonexistent-device'}})
    assert invalid_camera['result']['isError']
    reconnect=rpc('tools/call',{'name':'reconnect_sources','arguments':{}})
    assert not reconnect['result']['isError']
    restored=rpc('tools/call',{'name':'set_overlay','arguments':{'visible':before['project']['overlay']}})
    assert not restored['result']['isError']
finally:
    p.stdin.close();p.wait(timeout=5)
after=status();time.sleep(.3);later=status()
assert later['pid']==before['pid'] and later['stats']['rendered_frames']>after['stats']['rendered_frames']
report={'ok':True,'pid':before['pid'],'messages':messages,'agent_disconnect_keeps_engine_running':True,'final_state':later}
(root/'var/evidence/control-integration.json').write_text(json.dumps(report,indent=2))
print('MCP initialize/list/call, strict errors, shared PID/revision, and disconnect verified.')
