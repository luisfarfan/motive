#!/usr/bin/env python3
"""Owned random dummy credentials only. Real macOS Keychain; no secret in argv,
stdin, report, fixture files or MCP. Enrollment uses a controlling PTY.
"""
import os,pty,re,secrets,select,shutil,socket,ssl,threading
from h7_support import *
HELPER=ROOT/'target/Motive.app/Contents/MacOS/motive-credentials'
c=Client();report={'ok':False};refs=[];dummy_values=[]
def local(args,answer):
    pid,fd=pty.fork()
    if pid==0:os.execv(str(HELPER),[str(HELPER),*args])
    captured=b'';sent=False;deadline=time.monotonic()+12
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([fd],[],[],.1)
            if ready:
                try:chunk=os.read(fd,65536)
                except OSError:break
                if not chunk:break
                captured+=chunk
                if not sent and (b'(hidden;' in captured or b'Type DELETE:' in captured):
                    os.write(fd,answer+b'\n');sent=True
            ended,_=os.waitpid(pid,os.WNOHANG)
            if ended:break
        else:
            os.kill(pid,15);raise AssertionError('Local Keychain helper timeout; no secret logged')
    finally:
        os.close(fd)
        try:os.waitpid(pid,0)
        except ChildProcessError:pass
    assert sent
    for dummy in dummy_values:assert dummy not in captured,'Secret was echoed'
    lines=re.findall(rb'\{"ok"[^\r\n]*\}',captured)
    assert lines,'No structured local result'
    return json.loads(lines[-1])
def new_dummy():
    value=('owned-test-'+secrets.token_hex(24)).encode();dummy_values.append(value);return value
try:
    initial=c.state();assert initial['output']=='idle'
    report['initial_native_logs_suppressed']=initial['encoding']['native_logs_suppressed']
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(10)
    port=listener.getsockname()[1]
    enrolled=local(['create',str(port)],new_dummy());assert enrolled['ok'],enrolled
    reference=enrolled['credential_ref'];refs.append(reference);report['enrollment']=enrolled
    status=c.call('credential_status',credential_ref=reference);assert status['access']=='available',status
    # Queries carry only ref/access; values are neither serialized nor queryable.
    assert set(status)=={'ok','credential_ref','access'}
    tools=c.rpc('tools/list')['tools'];names=[x['name'] for x in tools]
    assert not any(x in names for x in ['get_credential','export_credential','create_credential','delete_credential'])
    c.call('configure_stream',endpoint={'transport':'rtmp','port':port})
    assert c.call('select_stream_credential',credential_ref=reference,expect=False)['error']['code']=='CREDENTIAL_REQUIRES_TLS'
    c.call('configure_stream',endpoint={'transport':'rtmps','port':port+1})
    assert c.call('select_stream_credential',credential_ref=reference,expect=False)['error']['code']=='CREDENTIAL_BINDING_MISMATCH'
    c.call('configure_stream',endpoint={'transport':'rtmps','port':port})
    c.call('select_stream_credential',credential_ref=reference)
    c.call('preflight_output',target='streaming')
    # Exercise the native secret resolver/service against an untrusted TLS
    # receiver. TLS must fail before any RTMP application bytes (or key) leave.
    tls=EVIDENCE/'h8-keychain-tls';tls.mkdir(exist_ok=True);key=tls/'key.pem';cert=tls/'cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],capture_output=True,check=True)
    key.chmod(0o600);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    events=[]
    def reject():
        peer,_=listener.accept();peer.settimeout(10)
        try:
            with context.wrap_socket(peer,server_side=True) as secure:
                events.append({'unexpected_tls_accept':True})
        except ssl.SSLError as e:events.append({'rejected':True,'reason':str(e)})
        finally:peer.close();listener.close()
    thread=threading.Thread(target=reject);thread.start()
    c.call('start_stream');failed=c.wait(lambda x:x['output']=='error',20);thread.join(12)
    assert failed['output_code']==-2 and failed['stats']['output_bytes']==0
    assert failed['encoding']['native_logs_suppressed'] and events[0].get('rejected'),events
    report['credentialed_tls_rejection']={'end':failed,'events':events}
    c.call('recover_output')
    # A different signing identity must not read without an OS authorization UI.
    changed=ROOT/'target/h8-credentials-changed-signature';shutil.copy2(HELPER,changed)
    subprocess.run(['codesign','--force','--sign','-','--identifier','local.motive.changed-signature',str(changed)],capture_output=True,check=True)
    start=time.monotonic();denied=subprocess.run([str(changed),'status',reference],capture_output=True,text=True,timeout=4)
    denial=json.loads(denied.stdout);assert denial['result']==2 and denied.returncode==1,denial
    report['changed_signature']={'result':denial,'seconds':time.monotonic()-start}
    # Same signing identity, fresh binary copy, remains authorized by requirement.
    same=ROOT/'target/h8-credentials-same-signature';shutil.copy2(HELPER,same)
    allowed=json.loads(subprocess.check_output([str(same),'status',reference],text=True));assert allowed['ok']
    report['same_signature']=allowed
    replaced=local(['replace',reference,str(port+1)],new_dummy());assert replaced['ok']
    assert c.call('preflight_output',target='streaming',expect=False)['error']['code']=='CREDENTIAL_BINDING_MISMATCH'
    c.call('configure_stream',endpoint={'transport':'rtmps','port':port+1})
    c.call('select_stream_credential',credential_ref=reference)
    assert local(['delete',reference],b'DELETE')['ok'];refs.remove(reference)
    assert c.call('credential_status',credential_ref=reference)['access']=='CREDENTIAL_MISSING'
    assert c.call('preflight_output',target='streaming',expect=False)['error']['code']=='CREDENTIAL_MISSING'
    assert c.call('start_stream',expect=False)['error']['code']=='CREDENTIAL_MISSING'
    c.call('select_stream_credential',credential_ref=None)
    # Unknown secret fields must be rejected and never echoed. Public dummy marker only.
    marker='NOT-A-CREDENTIAL-test-marker'
    for op,args in [('credential_status',{'credential_ref':reference,'secret':marker}),('select_stream_credential',{'credential_ref':reference,'value':marker}),('configure_stream',{'endpoint':{'transport':'rtmps','port':port,'key':marker}})]:
        response=c.call(op,expect=False,**args);assert marker not in json.dumps(response)
    for dummy in dummy_values:
        assert dummy.decode() not in json.dumps(c.ops)
        for path in [ROOT/'var/project.json',ROOT/'var/output-profiles.json',*EVIDENCE.glob('h8*runtime.log'), EVIDENCE/'encoding-restored.log', EVIDENCE/'encoding-restored-stderr.log']:
            if path.exists():assert dummy not in path.read_bytes(),str(path)
    report.update({'ok':True,'secret_export_tools':False,'plaintext_files_or_responses':False,'replace_rebind_revoke':True})
except BaseException as e:report['error']=repr(e);raise
finally:
    for reference in refs:
        try:local(['delete',reference],b'DELETE')
        except Exception:report['cleanup_required_reference']=reference
    try:c.call('select_stream_credential',credential_ref=None)
    except Exception:pass
    report['operations']=c.ops;c.close();(EVIDENCE/'h8-keychain.json').write_text(json.dumps(report,indent=2))
print('H8 Keychain PASS: register/replace/revoke, denied changed identity, opaque MCP, no plaintext persistence')
