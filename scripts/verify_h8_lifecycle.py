#!/usr/bin/env python3
"""Real RTMP workers: silent/slow handshakes, repeated deferred cancellation,
receiver failure and deferred shutdown. Loopback only; no mock libobs calls.
"""
import os,select,socket,threading
from h7_support import *
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
c=Client();report={'ok':False,'cycles':[]};owned=[]
def silent(hold):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(8)
    accepted=threading.Event();release=threading.Event()
    def run():
        try:
            peer,_=listener.accept()
            with peer:accepted.set();release.wait(hold)
        finally:listener.close()
    thread=threading.Thread(target=run);thread.start();owned.append((release,thread))
    return listener.getsockname()[1],accepted,release

def cancel(port,accepted):
    c.call('configure_stream',endpoint={'transport':'rtmp','port':port})
    c.call('start_stream');assert accepted.wait(6)
    assert c.state()['output']=='connecting'
    acknowledgements=[]
    for _ in range(6):
        start=time.monotonic();s=c.call('cancel_output')['state'];elapsed=time.monotonic()-start
        assert elapsed<2 and s['output']=='cancel_pending' and s['output_lifecycle']['native_busy'],s
        assert s['output_lifecycle']['cancel_deferred'];acknowledgements.append(elapsed)
    assert c.call('shutdown',expect=False)['error']['code']=='OUTPUT_BUSY'
    assert c.call('recover_output',expect=False)['error']['code']=='OUTPUT_BUSY'
    return acknowledgements
try:
    original=setup_owned(c);pid=c.state()['pid'];report['pid']=pid
    # The stock safety guard is still part of the contract. New deferred command
    # does not disguise a rejected immediate stop as a cancelled handshake.
    for iteration in range(12):
        port,accepted,release=silent(12);acks=cancel(port,accepted)
        pending=c.state();metrics=measure(c,2,'cancel_pending') if iteration==0 else None
        release.set();end=c.wait(lambda s:s['output']=='error',10)
        assert not end['output_lifecycle']['native_busy'] and end['output_code']==-2
        c.call('recover_output');assert c.state()['pid']==pid
        report['cycles'].append({'kind':'silent_close','iteration':iteration,'acks':acks,'pending':pending,'metrics':metrics,'end':end})
    # A completely silent peer is allowed to hit the real OBS socket timeout.
    port,accepted,release=silent(90);acks=cancel(port,accepted);start=time.monotonic()
    metrics=measure(c,5,'cancel_pending');end=c.wait(lambda s:s['output']=='error',70)
    elapsed=time.monotonic()-start;release.set();c.call('recover_output')
    report['cycles'].append({'kind':'native_timeout','seconds':elapsed,'acks':acks,'metrics':metrics,'end':end})
    # A real FFmpeg receiver behind a controlled 3-second TCP relay delay.
    backend=socket.socket();backend.bind(('127.0.0.1',0));backend_port=backend.getsockname()[1];backend.close()
    path=EVIDENCE/f'h8-cancel-after-connect-{time.time_ns()}.flv'
    with (EVIDENCE/'h8-slow-receiver.log').open('w') as log:
        receiver=subprocess.Popen(['ffmpeg','-nostdin','-v','info','-listen','1','-i',f'rtmp://127.0.0.1:{backend_port}/live/motive','-c','copy',str(path)],stdout=subprocess.DEVNULL,stderr=log)
    time.sleep(.6)
    relay=socket.socket();relay.bind(('127.0.0.1',0));relay.listen();relay.settimeout(10);port=relay.getsockname()[1];accepted=threading.Event()
    def forward():
        try:
            downstream,_=relay.accept()
            with downstream,socket.create_connection(('127.0.0.1',backend_port),timeout=10) as upstream:
                accepted.set();time.sleep(3)
                while True:
                    ready,_,_=select.select([downstream,upstream],[],[],8)
                    if not ready:break
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (upstream if source is downstream else downstream).sendall(data)
        except (ConnectionError,OSError):pass
        finally:relay.close()
    relay_thread=threading.Thread(target=forward);relay_thread.start()
    acks=cancel(port,accepted);start=time.monotonic();end=c.wait(lambda s:s['output'] in ('idle','error'),15)
    assert not end['output_lifecycle']['native_busy'];relay_thread.join(12)
    receiver.wait(timeout=12)
    report['cycles'].append({'kind':'slow_then_connect','acks':acks,'completion_seconds':time.monotonic()-start,'end':end,'receiver_exit':receiver.returncode,'path':str(path)})
    if end['output']=='error':c.call('recover_output')
    assert c.state()['project']==original
    # Closing is explicit and remains pending while native ownership is live.
    port,accepted,release=silent(20);cancel(port,accepted)
    response=c.call('request_shutdown')['state'];assert response['output']=='cancel_pending' and response['output_lifecycle']['shutdown_pending']
    assert c.call('start_recording',expect=False)['error']['code']=='SHUTDOWN_PENDING'
    # Exercise the same terminal admission gate through the real owner while
    # the silent RTMP peer makes shutdown_pending deterministic. Neither target
    # nor the early overlay dispatch may reopen work during this interval.
    rejected=[]
    for op,args in [
        ('start_output',{'target':'recording'}),
        ('start_output',{'target':'streaming'}),
        ('preflight_output',{'target':'recording'}),
        ('preflight_output',{'target':'streaming'}),
        ('import_asset',{'file_name':'h8-shutdown-must-not-import.png'}),
    ]:
        result=c.call(op,expect=False,**args)
        assert result['error']['code']=='SHUTDOWN_PENDING',result
        rejected.append({'op':op,'arguments':args,'response':result})
    queries={op:c.call(op) for op in ('overlay_state','list_assets','outputs')}
    for target in ('recording','streaming'):
        assert queries['outputs']['outputs'][target]['attempt_id']==response['outputs'][target]['attempt_id']
    time.sleep(.5);assert c.state()['output_lifecycle']['native_busy']
    release.set();deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        try:os.kill(pid,0)
        except ProcessLookupError:break
        time.sleep(.1)
    else:raise AssertionError('Motive did not finish deferred shutdown')
    report['shutdown']={'request':response,'rejected_after_request':rejected,'queries_after_request':queries,'process_exited':True}
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:
    for release,thread in owned:release.set();thread.join(4)
    report['operations']=c.ops;c.close();(EVIDENCE/'h8-lifecycle.json').write_text(json.dumps(report,indent=2))
    subprocess.run(['open','-a',str(VERIFY.app_bundle)],check=True)
    # LaunchServices returns before the socket/core exists. Hand off to the next
    # regression only after the real reopened instance answers.
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        query=subprocess.run([str(EXE),'ctl','{"op":"status"}'],capture_output=True,text=True)
        state=json.loads(query.stdout)
        if state.get('ok'):
            report['reopened']={'pid':state['state']['pid'],'output':state['state']['output']}
            break
        time.sleep(.2)
    else:
        report['ok']=False;report['reopen_error']='Core did not become available'
    (EVIDENCE/'h8-lifecycle.json').write_text(json.dumps(report,indent=2))
    assert report.get('reopened'),report.get('reopen_error')
print('H8 lifecycle PASS: real workers, deferred cancellation, timeout, slow handshake, shutdown')
