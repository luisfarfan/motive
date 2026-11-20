import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_workload_check import active_windows,active_gap,event_accounting

class IntermittentAudit(unittest.TestCase):
    def test_idle_is_not_animation_but_full_active_interval_is_measured(self):
        self.assertEqual(active_gap([0,101,130,160,190,201,1000],100,200),30/1e6)
        self.assertEqual(active_gap([0,201,1000],100,200),100/1e6)

    def test_cancelled_event_is_retained_and_new_event_is_distinct(self):
        trace=[{'phase':phase,'observed_ns':at} for phase,at in
            [('visual_active',1),('hidden_cancel_dispatched',10),('visual_active',20),('visual_complete',30)]]
        self.assertEqual(active_windows(trace),[(1,10,False,'hidden_cancel_dispatched'),(20,30,True,'visual_complete')])

    def test_overlapping_or_unterminated_activity_is_not_accepted(self):
        with self.assertRaises(ValueError):active_windows([{'phase':'visual_active','observed_ns':1}])
        with self.assertRaises(ValueError):active_windows([{'phase':'visual_active','observed_ns':n} for n in (1,2)])

    def test_lost_event_cannot_be_hidden_by_good_fps_elsewhere(self):
        for phases in [('fixture_event_dispatched','fixture_event_dispatched'),
                       ('fixture_event_dispatched','close_requested'),('fixture_event_dispatched',)]:
            with self.assertRaises(ValueError):event_accounting([{'phase':p,'observed_ns':n} for n,p in enumerate(phases)],False,False)

    def test_static_rejection_is_distinct_from_missing_activity(self):
        tr=[{'phase':p,'observed_ns':n} for n,p in enumerate(('fixture_event_dispatched','fixture_event_rejected'))]
        self.assertEqual(event_accounting(tr,False,True)['events'][0]['outcome'],'static_rejected')
        with self.assertRaises(ValueError):event_accounting(tr,False,False)

    def test_explicit_interruption_is_not_an_active_ack(self):
        tr=[{'phase':p,'observed_ns':n} for n,p in enumerate(('fixture_goal_dispatched','remove_requested','close_requested'))]
        r=event_accounting(tr,True,False)
        self.assertEqual(r['events'][0]['outcome'],'explicitly_interrupted_before_active')
        self.assertIsNone(r['maximum_dispatch_to_active_ms'])

    def test_one_goal_bootstrap_is_not_replayed_activity(self):
        tr=[{'phase':'visual_active','observed_ns':100}]
        self.assertEqual(event_accounting(tr,True,False)['bootstrap_activities'],1)
        with self.assertRaises(ValueError):event_accounting(tr*2,True,False)
        with self.assertRaises(ValueError):event_accounting(tr,False,False)

if __name__=='__main__':unittest.main()
