import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_network_check import inspect_netlog


def log(address=None,kind=1,error=-130):
    events=[{'type':3,'source':{'id':1},'params':{'url':'http://127.0.0.1:18720/h22-owned-proxy-control'}},
        {'type':4,'source':{'id':1},'phase':2,'params':{'net_error':error}},
        {'type':5,'source':{'id':2},'params':{'url':'http://127.0.0.1:18720/h22-owned-proxy-control'}},
        {'type':6,'source':{'id':2},'params':{'proxy_info':'PROXY 127.0.0.1:18719'}}]
    if address:events.append({'type':kind,'source':{'id':3},'phase':1,'params':{'address':address}})
    return json.dumps({'constants':{'logEventPhase':{'PHASE_END':2},'logEventTypes':{
        'TCP_CONNECT_ATTEMPT':1,'UDP_CONNECT':2,'REQUEST_ALIVE':3,'URL_REQUEST_START_JOB':4,
        'HTTP_STREAM_JOB_CONTROLLER':5,'PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST':6}},'events':events}).encode()


class NetworkDiagnosticTests(unittest.TestCase):
    def test_positive_request_rejection_passes_without_claiming_os_confinement(self):
        result=inspect_netlog(log(),0,0,[])
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['security_third_party'],'BLOCKED')
        self.assertTrue(result['owned_control_resolution_rejected'])
        self.assertNotIn('127.0.0.1',json.dumps(result))

    def test_all_socket_attempts_fail_even_proxy_or_udp(self):
        for address,kind in [('192.0.2.1:443',1),('127.0.0.1:18719',1),('127.0.0.1:18720',1),('[2001:db8::1]:53',2)]:
            self.assertEqual(inspect_netlog(log(address,kind),0,0,[])['status'],'FAIL')

    def test_listener_hits_components_and_wrong_rejection_fail(self):
        for proxy,direct,manifests in [(1,0,[]),(0,1,[]),(0,0,['component/1/manifest.json'])]:
            self.assertEqual(inspect_netlog(log(),proxy,direct,manifests)['status'],'FAIL')
        for code in (0,-105,-324,None):self.assertEqual(inspect_netlog(log(error=code),0,0,[])['status'],'FAIL')

    def test_empty_log_missing_control_cannot_pass(self):
        data=json.loads(log());data['events']=[]
        self.assertEqual(inspect_netlog(json.dumps(data).encode(),0,0,[])['status'],'FAIL')
        data=json.loads(log());data['events'][2]['params']['url']='http://127.0.0.1:18720/different-control'
        self.assertEqual(inspect_netlog(json.dumps(data).encode(),0,0,[])['status'],'FAIL')

    def test_missing_schema_and_ring_sized_log_fail_closed(self):
        with self.assertRaises(KeyError):inspect_netlog(b'{}',0,0,[])
        with self.assertRaisesRegex(ValueError,'TRUNCATION'):inspect_netlog(b' '*7*1024**2,0,0,[])


if __name__=='__main__':unittest.main()
