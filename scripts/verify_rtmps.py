#!/usr/bin/env python3
"""Independent local TLS rejection test; never installs trust or disables verification.
A valid IP-SAN self-signed fixture is trusted only by a Python control client.
Motive/libobs must reject it using the unchanged macOS trust store.
"""
import socket,ssl,threading
from h7_support import *
c=Client();report={'ok':False,'server_events':[]};listener=None;thread=None
try:
    assert c.state()['output']=='idle'
    tls=EVIDENCE/'h7-tls';tls.mkdir(exist_ok=True)
    key=tls/'key.pem';cert=tls/'cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],capture_output=True,check=True)
    key.chmod(0o600)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(2);listener.settimeout(15);port=listener.getsockname()[1]
    def server():
        for _ in range(2):
            try:
                peer,_=listener.accept();peer.settimeout(10)
                try:
                    with context.wrap_socket(peer,server_side=True) as secure:
                        report['server_events'].append({'handshake':'accepted','version':secure.version()})
                        secure.recv(4096)
                except ssl.SSLError as e:
                    report['server_events'].append({'handshake':'rejected','error':str(e)});peer.close()
            except Exception as e:report['server_events'].append({'error':repr(e)})
    thread=threading.Thread(target=server);thread.start()
    # Positive control for the owned fixture, scoped to this Python context only.
    control=ssl.create_default_context(cafile=str(cert))
    with socket.create_connection(('127.0.0.1',port)) as raw:
        with control.wrap_socket(raw,server_hostname='127.0.0.1') as secure:secure.sendall(b'owned TLS fixture control')
    c.call('configure_stream',endpoint={'transport':'rtmps','port':port})
    pre=c.call('preflight_output',target='streaming')['preflight'];assert not pre['network_tested']
    start=c.call('start_stream')['state'];end=c.wait(lambda s:s['output']=='error',20)
    assert end['output_code']==-2 and end['recovery_required']
    assert end['stats']['output_bytes']==0
    thread.join(timeout=10);assert not thread.is_alive()
    assert report['server_events'][0]['handshake']=='accepted'
    assert report['server_events'][1]['handshake']=='rejected'
    assert c.call('start_stream',expect=False)['error']['code']=='RECOVERY_REQUIRED'
    c.call('recover_output');assert c.state()['output']=='idle'
    report.update({'ok':True,'start':start,'failure':end,'preflight':pre,'certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),
        'scope':'Untrusted-root rejection only. Trusted RTMPS media delivery and isolated hostname rejection not verified. No trust-store changes.'})
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        c.stop()
        if c.state()['output']=='error':c.call('recover_output')
    except Exception as e:report['cleanup_error']=repr(e)
    if listener:listener.close()
    if thread:thread.join(timeout=16)
    report['operations']=c.ops;c.close();(EVIDENCE/'h7-rtmps.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k in ('ok','server_events','scope','error')},indent=2))
