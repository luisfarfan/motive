import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from h22_xpc_check import classify

class XpcClassification(unittest.TestCase):
    def test_original_native_reply_and_boolean_equivalent(self):
        r=json.loads((ROOT/'evidence/H22-xpc-r1/report.json').read_text())
        self.assertTrue(classify(r))
        r['reply']['direct_file_opened']=False
        self.assertTrue(classify(r))

    def test_no_missing_or_loosely_falsy_acceptance(self):
        original=json.loads((ROOT/'evidence/H22-xpc-r1/report.json').read_text())
        for value in (None,'',[],{},'0',1,0.0):
            r=copy.deepcopy(original);r['reply']['direct_file_opened']=value
            self.assertFalse(classify(r),repr(value))
        for field in ('file_errno','network_errno','capability_bytes','cef_loaded','keychain_called'):
            r=copy.deepcopy(original);del r['reply'][field]
            self.assertFalse(classify(r),field)

if __name__=='__main__':unittest.main()
