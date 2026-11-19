"""Owned HTTP and Rust subprocess tests. No browser, CEF, or production launch."""
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h18_fixture_server',HERE/'serve_fixture.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class FixtureServerTests(unittest.TestCase):
    def setUp(self):
        self.server=module.FixtureServer(0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.stop_worker();self.server.server_close()
    def request(self,path,data=None,origin=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Origin':origin if origin is not None else self.server.origin,'X-Motive-Fixture':'h18','Content-Type':'application/json'}
        conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers)
        response=conn.getresponse();body=response.read();status=response.status;conn.close();return status,body
    def test_opaque_widget_and_other_origins_cannot_create_owner_session(self):
        for origin in ['null','http://127.0.0.1:1','https://example.invalid']:
            self.assertEqual(self.request('/api/session',{},origin)[0],403)
            self.assertIsNone(self.server.worker)
    def test_inventory_only_and_no_arbitrary_paths(self):
        self.assertEqual(self.request('/api/session',{})[0],200)
        for name in ['/widget/../Cargo.toml','/widget/%2e%2e/Cargo.toml','/etc/passwd','/widget/index.html/extra']:
            self.assertEqual(self.request(name)[0],404)
        status,body=self.request('/widget/goal.mjs')
        self.assertEqual(status,200)
        self.assertEqual(body,(HERE.parents[1]/'element-lab/web-elements/goal-celebration/goal.mjs').read_bytes())
    def test_real_owned_rust_worker_rejects_commands_and_is_reaped_on_restart(self):
        _,raw=self.request('/api/session',{});first=json.loads(raw);old=self.server.worker
        self.assertTrue(json.loads(self.request('/api/command',{'command':'ready'})[1])['ok'])
        refused=json.loads(self.request('/api/command',{'command':'start_recording'})[1])
        self.assertEqual(refused['code'],'FIXTURE_COMMAND')
        _,raw=self.request('/api/session',{});second=json.loads(raw)
        self.assertEqual(second['generation'],first['generation']+1)
        self.assertEqual(old.poll(),0)
        self.assertNotEqual(old.pid,self.server.worker.pid)
    def test_oversize_input_and_unknown_route_fail_closed(self):
        self.assertEqual(self.request('/api/session',{'payload':'x'*1024})[0],400)
        self.assertIsNone(self.server.worker)
        self.assertEqual(self.request('/api/eval',{'script':'alert(1)'})[0],400)
    def test_pipeline_requires_property_ack_and_does_not_grant_native_outcome(self):
        session=json.loads(self.request('/api/session',{})[1])
        command=lambda value:json.loads(self.request('/api/command',value)[1])
        self.assertTrue(command({'command':'ready'})['ok'])
        self.assertEqual(command({'command':'goal'})['code'],'PROPERTIES_UNACKNOWLEDGED')
        properties=command({'command':'properties'});seq=properties['dispatch']['message']['seq']
        ack={'protocol':1,**session['identity'],'kind':'visual_ack','seq':seq,'accepted':True}
        self.assertTrue(command({'command':'ack','ack':ack})['ok'])
        event=command({'command':'goal'})
        self.assertTrue(event['ok']);self.assertFalse(event['native_terminal_outcome'])
        self.assertEqual(set(event['dispatch']['message']['payload']),{'team','home','away'})

if __name__=='__main__':unittest.main()
