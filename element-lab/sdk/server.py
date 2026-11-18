"""Loopback-only authoring harness with an explicit route/file allowlist."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit,unquote
from common import LAB,LabError,encode,loads,read_bytes,read_json,require
from compiler import compile_element
from templates import TEMPLATES
from web_contract import validate_web
from preview import svg

BASE_CSP="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
WIDGET_CSP="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'; media-src 'none'; frame-ancestors 'self'"

def native_request(value):
    require(type(value) is dict and set(value)=={'template','properties'} and value['template'] in TEMPLATES and type(value['properties']) is dict,
            'REQUEST_SCHEMA','Choose a bundled template and typed properties')
    return compile_element(LAB/'native-elements'/value['template']/'element.json',value['properties'])

class Handler(BaseHTTPRequestHandler):
    server_version='MotiveElementLab/0.1'
    def log_message(self,format,*args):pass
    def send_data(self,data,content_type='application/json',code=200,widget=False):
        self.send_response(code);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',WIDGET_CSP if widget else BASE_CSP)
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()')
        # Sandboxed opaque-origin modules may load only these public bundled assets.
        if widget:self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers();self.wfile.write(data)
    def error(self,error,code=400):
        self.send_data(encode({'status':'FAIL','error':{'code':getattr(error,'code','REQUEST_ERROR'),'message':str(error)}}),code=code)
    def host(self):
        require(self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}','HOST','Loopback Host required')
    def do_GET(self):
        try:
            self.host();url=urlsplit(self.path);path=unquote(url.path)
            if path=='/':path='/web-elements/runtime-prototype/index.html'
            if path=='/guide':
                data=read_bytes(LAB,'sdk/README.md').decode();self.send_data(('<!doctype html><meta charset="utf-8"><title>Guía</title><pre>'+escape(data)+'</pre>').encode(),'text/html; charset=utf-8');return
            if path.startswith('/api/template/'):
                template=path.rsplit('/',1)[-1];require(template in TEMPLATES,'NOT_FOUND','Unknown template')
                self.send_data(read_bytes(LAB,f'native-elements/{template}/element.json'));return
            name=path.lstrip('/');require(path=='/'+name,'PATH','Invalid path')
            # Public authoring assets only. Never expose repository paths, secrets, .scratch or a directory listing.
            static={'web-elements/runtime-prototype/'+n for n in ['index.html','lab.css','host.mjs']}
            web=self.server.web_manifest
            static|={'web-elements/goal-celebration/'+a['path'] for a in web['assets']}
            static.add('web-elements/goal-celebration/web-element.json')
            for template in TEMPLATES:
                for file in (LAB/'native-elements'/template/'preview').iterdir():
                    if file.is_file():static.add(file.relative_to(LAB).as_posix())
            require(name in static,'NOT_FOUND','File is not declared for this harness')
            data=read_bytes(LAB,name,4*1024**2);content=mimetypes.guess_type(name)[0] or 'application/octet-stream'
            if name.endswith('.mjs'):content='text/javascript'
            self.send_data(data,content,widget=name.startswith('web-elements/goal-celebration/'))
        except (LabError,OSError,ValueError) as error:self.error(error,404)
    def do_POST(self):
        try:
            self.host();require(self.headers.get('Origin')==f'http://127.0.0.1:{self.server.server_port}' and
                self.headers.get('X-Element-Lab')=='authoring' and self.headers.get('Content-Type')=='application/json','ORIGIN','Same-origin authoring request required')
            length=int(self.headers.get('Content-Length','0'));require(0 < length <= 32768,'REQUEST_SIZE','Bounded JSON required')
            data=loads(self.rfile.read(length))
            if self.path=='/api/compile':
                b=native_request(data);self.send_data(encode({'manifest':b.pack,'rules':b.rules,'report':b.report,
                    'previews':{o:svg(b,b.pack['scenes'][0],o) for o in ('horizontal','vertical')}}));return
            if self.path=='/api/native-package':
                from packaging import package_bundle
                b=native_request(data);self.send_data(package_bundle(b),'application/zip');return
            if self.path=='/api/web-package':
                from packaging import package_web_bytes
                require(data=={},'REQUEST_SCHEMA','Empty object required')
                self.send_data(package_web_bytes(LAB/'web-elements/goal-celebration'),'application/zip');return
            raise LabError('NOT_FOUND','Unknown authoring endpoint')
        except (LabError,OSError,ValueError,KeyError,TypeError) as error:self.error(error)

def make_server(port=8776):
    require(1024<=port<=65535 or port==0,'PORT','Unprivileged loopback port required')
    manifest,_,_=validate_web(LAB/'web-elements/goal-celebration')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.web_manifest=manifest
    return server

def serve(port=8776):
    server=make_server(port);print(f'Element Lab: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
