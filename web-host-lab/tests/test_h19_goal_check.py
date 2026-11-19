import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h19_goal_check import phase_order, EvidenceError

class GoalEvidenceOrder(unittest.TestCase):
    def test_hiding_requires_cancel_ack_before_native_hide(self):
        trace=[{'phase':name,'observed_ns':time} for name,time in [('cancel',1),('ack',2),('hide',3)]]
        self.assertEqual(phase_order(trace,['cancel','ack','hide'])['ack'],2)
        trace[1]['observed_ns']=4
        with self.assertRaisesRegex(EvidenceError,'ORDER'):phase_order(trace,['cancel','ack','hide'])
        trace.append({'phase':'ack','observed_ns':5})
        with self.assertRaisesRegex(EvidenceError,'EXACTLY_ONCE'):phase_order(trace,['cancel','ack','hide'])

if __name__=='__main__':unittest.main()
