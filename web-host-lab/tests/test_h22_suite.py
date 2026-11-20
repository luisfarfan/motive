import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_suite import performance_only_failure

class ContinueGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.result={'native_returncode':0,'analysis.json':{'returncode':0},'workload-analysis.json':{'returncode':1}}
        self.data={'report.json':{'status':'PASS','network_lab':{'status':'PASS'}},'analysis.json':{'functional_status':'PASS'},'workload-analysis.json':{'functional_status':'PASS','performance_status':'FAIL','status':'FAIL'}}
    def tearDown(self):self.tmp.cleanup()
    def write(self):
        for name,data in self.data.items():(self.root/name).write_text(json.dumps(data))
    def test_only_cadence_failure_can_continue(self):
        self.write();self.assertTrue(performance_only_failure(self.root,self.result))
    def test_missing_and_malformed_evidence_cannot_continue(self):
        self.assertFalse(performance_only_failure(self.root,self.result));self.write();(self.root/'analysis.json').write_text('bad');self.assertFalse(performance_only_failure(self.root,self.result))
    def test_security_native_or_functional_failure_cannot_continue(self):
        for filename,field,value in [('report.json','status','FAIL'),('analysis.json','functional_status','FAIL'),('workload-analysis.json','functional_status','FAIL')]:
            old=self.data[filename][field];self.data[filename][field]=value;self.write();self.assertFalse(performance_only_failure(self.root,self.result));self.data[filename][field]=old
        self.data['report.json']['network_lab']['status']='FAIL';self.write();self.assertFalse(performance_only_failure(self.root,self.result))
    def test_native_exit_cannot_continue(self):
        self.write();self.result['native_returncode']=1;self.assertFalse(performance_only_failure(self.root,self.result))
if __name__=='__main__':unittest.main()
