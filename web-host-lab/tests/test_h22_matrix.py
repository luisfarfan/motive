import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_matrix import verify_audit_inputs,observed_case_result


class MatrixProvenanceTests(unittest.TestCase):
    def test_operation_pass_does_not_invent_cadence(self):
        native={'status':'PASS','network_lab':{'status':'PASS'}}
        audit={'status':'PASS','functional_status':'PASS','performance_status':'NOT_EVALUATED'}
        self.assertEqual(observed_case_result(native,audit),'PASS')
        self.assertEqual(audit['performance_status'],'NOT_EVALUATED')

    def test_missing_workload_does_not_pass_intermittent_case(self):
        native={'status':'PASS','network_lab':{'status':'PASS'}}
        self.assertEqual(observed_case_result(native,{'status':'PASS'},requires_workload=True),'NOT_EVALUATED')

    def test_failed_closure_cannot_be_overridden_by_workload_pass(self):
        native={'status':'PASS','network_lab':{'status':'PASS'}}
        self.assertEqual(observed_case_result(native,{'status':'FAIL'},{'status':'PASS'},True),'FAIL')

    def test_stale_audit_cannot_certify_changed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);report=root/'report.json';report.write_bytes(b'{}')
            data={'input_sha256':{'report.json':hashlib.sha256(b'{}').hexdigest()}}
            self.assertEqual(verify_audit_inputs(root/'analysis.json',data),data['input_sha256'])
            report.write_bytes(b'{"changed":true}')
            with self.assertRaisesRegex(ValueError,'AUDIT_INPUT_HASH'):verify_audit_inputs(root/'analysis.json',data)

    def test_summary_without_run_binding_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'AUDIT_REPORT_UNBOUND'):
            verify_audit_inputs(Path('/unused/analysis.json'),{'input_sha256':{}})

    def test_input_cannot_escape_run_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'report.json').write_bytes(b'{}')
            data={'input_sha256':{'report.json':hashlib.sha256(b'{}').hexdigest(),'../other':'0'*64}}
            with self.assertRaisesRegex(ValueError,'INPUT_PATH'):verify_audit_inputs(root/'analysis.json',data)


if __name__=='__main__':unittest.main()
