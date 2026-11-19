#!/usr/bin/env python3
"""Owned loopback QA: immutable H16 broker + offline Rust owner, no production.
Never serves arbitrary paths. API rejects opaque widget Origin and cross-origin
requests; no arbitrary events, commands, files, networking or executable payloads.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('h16_asset_broker', ROOT/'web-host-lab/poc/browser-host/asset_broker.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from web_contract import validate_web

class FixtureServer(HTTPServer):
    def __init__(self, port):
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.worker = None
        self.generation = 0
        self.broker = None
        self.manifest, self.report, _ = validate_web(ROOT/'element-lab/web-elements/goal-celebration')
        self.web = {('/'+name): (HERE/'web'/name).read_bytes() for name in ['index.html','fixture.mjs','fixture.css','port-adapter.mjs']}
        self.fingerprint = hashlib.sha256((ROOT/'element-lab/web-elements/goal-celebration/web-element.json').read_bytes()).hexdigest()
    def stop_worker(self):
        if self.worker is not None:
            self.worker.stdin.close()
            try: self.worker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.worker.terminate()
                try: self.worker.wait(timeout=1)
                except subprocess.TimeoutExpired: self.worker.kill(); self.worker.wait(timeout=1)
            self.worker.stdout.close()
            self.worker = None
        if self.broker: self.broker.close()
    def session(self):
        self.stop_worker()
        self.generation += 1
        binary = HERE/'target/debug/examples/fixture_host'
        self.worker = subprocess.Popen([str(binary), self.fingerprint, str(self.generation)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=HERE, close_fds=True, env={'PATH':os.defpath,'LANG':'C'})
        self.broker = module.AssetBroker(ROOT/'element-lab/web-elements/goal-celebration', 1, self.generation)
        return {'generation':self.generation,'identity':{'instance':1,'generation':self.generation},'contract':self.manifest,'native_terminal_outcome':False}
    def dispatch(self, request):
        if self.worker is None: raise ValueError('FIXTURE_NO_SESSION')
        data = json.dumps(request, separators=(',',':')).encode()+b'\n'
        if len(data)>1024: raise ValueError('FIXTURE_SIZE')
        self.worker.stdin.write(data); self.worker.stdin.flush()
        with selectors.DefaultSelector() as poll:
            poll.register(self.worker.stdout, selectors.EVENT_READ)
            if not poll.select(timeout=2):
                self.stop_worker(); raise ValueError('FIXTURE_DEADLINE')
        data=self.worker.stdout.readline(16385)
        if not data.endswith(b'\n') or len(data)>16384:
            self.stop_worker(); raise ValueError('FIXTURE_OUTPUT')
        return json.loads(data)

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(2)
    def log_message(self, *_): pass
    def send(self, status, data, kind='application/json', headers=()):
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        for key,value in headers: self.send_header(key,value)
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.headers.get('Host')!=self.server.origin.removeprefix('http://'): return self.send(403,b'{}')
        name=self.path.split('?',1)[0]
        if name=='/':name='/index.html'
        if name in self.server.web:
            kind='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
            policy="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            return self.send(200,self.server.web[name],kind,[('Content-Security-Policy',policy)])
        if name.startswith('/widget/') and self.server.broker:
            resource=self.server.broker.request(self.server.broker.origin+'/'+name.removeprefix('/widget/'))
            if resource:
                # H16 broker's inventory is unchanged. This owned iframe harness
                # changes frame-ancestors only to admit its trusted parent.
                headers=[(k,v.replace("frame-ancestors 'none'","frame-ancestors 'self'")) for k,v in resource.headers]
                headers.append(('Access-Control-Allow-Origin','*')) # opaque, scripts-only iframe imports
                return self.send(200,resource.data,resource.media_type,headers)
        return self.send(404,b'{}')
    def do_POST(self):
        if (self.headers.get('Host')!=self.server.origin.removeprefix('http://') or self.headers.get('Origin')!=self.server.origin
            or self.headers.get('X-Motive-Fixture')!='h18' or self.headers.get('Content-Type')!='application/json'):
            return self.send(403,b'{"code":"FIXTURE_ORIGIN"}')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>1024:raise ValueError('FIXTURE_SIZE')
            value=json.loads(self.rfile.read(size))
            if self.path=='/api/session' and value=={}: result=self.server.session()
            elif self.path=='/api/command' and type(value) is dict: result=self.server.dispatch(value)
            else:raise ValueError('FIXTURE_ROUTE')
            self.send(200,json.dumps(result).encode())
        except (ValueError,OSError,subprocess.SubprocessError): self.send(400,b'{"code":"FIXTURE_REQUEST"}')

if __name__=='__main__':
    port=int(sys.argv[1]) if len(sys.argv)>1 else 8788
    server=FixtureServer(port)
    print(server.origin,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.stop_worker();server.server_close()
