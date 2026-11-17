#!/usr/bin/env python3
"""Reject unsafe cancellation of an owned pending handshake; keep the core responsive."""
import socket,threading
from h7_support import *
c=Client();report={'ok':False};release=threading.Event();accepted=threading.Event();peer_errors=[]
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(15)
def peer():
    try:
        connection,_=listener.accept();accepted.set()
        with connection:release.wait(10)
    except Exception as e:peer_errors.append(repr(e))
thread=threading.Thread(target=peer);thread.start()
try:
    assert c.state()['output']=='idle';original=c.state()['project']
    c.call('configure_stream',endpoint={'transport':'rtmp','port':listener.getsockname()[1]})
    started=c.call('start_stream')['state'];assert accepted.wait(5)
    before=c.wait(lambda s:s['output']=='connecting')
    start=time.monotonic();response=c.call('stop_output',expect=False);elapsed=time.monotonic()-start
    assert elapsed<2 and response['error']['code']=='OUTPUT_CONNECTING',(elapsed,response)
    first=c.state();time.sleep(.5);second=c.state()
    assert first['output']=='connecting' and second['stats']['rendered_frames']>first['stats']['rendered_frames']
    release.set();end=c.wait(lambda s:s['output'] in ('idle','error'))
    if end['output']=='error':c.call('recover_output')
    assert c.state()['project']==original
    report.update({'ok':True,'before':before,'response':response,'stop_ack_seconds':elapsed,'responsive':second,'end':end})
except BaseException as e:report['error']=repr(e);raise
finally:
    release.set();thread.join(timeout=12);listener.close()
    try:
        c.wait(lambda s:s['output'] in ('idle','error'),15)
        if c.state()['output']=='error':c.call('recover_output')
    except Exception as e:report['cleanup_error']=repr(e)
    report['operations']=c.ops;report['peer_errors']=peer_errors;c.close();(EVIDENCE/'h7-connect-stop.json').write_text(json.dumps(report,indent=2))
print('Pending handshake: cancellation rejected promptly, core responsive; peer close -> error -> explicit recovery: PASS')
