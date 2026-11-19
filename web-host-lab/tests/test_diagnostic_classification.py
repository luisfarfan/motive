"""Report classification only; synthetic dictionaries are not native evidence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_owned_diagnostic import classify

class Classification(unittest.TestCase):
    def test_crash_never_passes_as_healthy_or_without_revocation(self):
        diagnostic={'fixture_ready':True,'crash_requested':True,'renderer_terminated':True,'renderer_exit_code':22016,'renderer_decoded_exit_code':86,'revocation_confirmed':True}
        phases=[{'phase':s,'observed_ns':n} for n,s in enumerate(['renderer_exit_requested','renderer_error_observed','frame_generation_revoked','shutdown_return'])]
        samples={'latest':{'status':'PASS','alpha':{'status':'PASS'}}}
        supervision={'reason':'exit','returncode':0,'final_cleanup_observed_tree':True,'final_remaining_observed_pids':[]}
        self.assertEqual(classify('crash',diagnostic,phases,{},samples,supervision)['status'],'FAIL')
        supervision['returncode']=42
        result=classify('crash',diagnostic,phases,{},samples,supervision)
        self.assertEqual(result['status'],'PASS');self.assertFalse(result['observations']['host_healthy_exit'])
        diagnostic['revocation_confirmed']=False
        self.assertEqual(classify('crash',diagnostic,phases,{},samples,supervision)['status'],'FAIL')

if __name__=='__main__':unittest.main()
