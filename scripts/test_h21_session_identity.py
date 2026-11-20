import copy
import unittest

from analyze_h21_session_identity import audit


def state():
    slot = {'attempt_id':1, 'phase':'active', 'encoding':{'selected_hardware':True},
            'stats':{'output_frames':10, 'output_dropped_frames':0}}
    return {'pid':123, 'sources':[{'id':'window','kind':'window','instance_id':7,'frames':10,
                                  'capture_diagnostics':{'created_ns':400}}],
            'transition':{'source_instances_created':7},
            'audio_mixer':{'runtime':{'instances_created':1,'inputs':[{'id':'mic','instance_id':9}]}},
            'outputs':{'recording':copy.deepcopy(slot),'streaming':copy.deepcopy(slot)}}


def observation(value, elapsed):
    return {'state':value,'elapsed_s':elapsed,'host_bracket_s':[100+elapsed,100.01+elapsed]}


class SessionIdentityTests(unittest.TestCase):
    def test_scene_mute_gain_and_progress_do_not_mean_resource_recreation(self):
        initial=state(); changed=copy.deepcopy(initial)
        changed['transition']['current_scene']='safe'
        changed['audio_mixer']['store']={'inputs':[{'id':'mic','muted':True,'gain_db':-12}]}
        changed['sources'][0]['frames']=100
        for slot in changed['outputs'].values():slot['stats']['output_frames']=100
        result=audit(initial,[observation(initial,0),observation(changed,4)],5)
        self.assertEqual(result['status'],'PASS')

    def test_replaced_identity_is_rejected_even_when_outputs_stay_active(self):
        initial=state()
        changes=[lambda s:s.update(pid=124),
                 lambda s:s['sources'][0].update(instance_id=8),
                 lambda s:s['sources'][0]['capture_diagnostics'].update(created_ns=401),
                 lambda s:s['audio_mixer']['runtime']['inputs'][0].update(instance_id=10),
                 lambda s:s['outputs']['streaming'].update(attempt_id=2)]
        for change in changes:
            with self.subTest(change=change):
                changed=copy.deepcopy(initial);change(changed)
                with self.assertRaises(ValueError):audit(initial,[observation(changed,1)],2)

    def test_counter_reset_without_identity_change_is_rejected(self):
        initial=state(); changed=copy.deepcopy(initial);changed['sources'][0]['frames']=0
        with self.assertRaises(ValueError):audit(initial,[observation(changed,1)],2)

    def test_output_drops_and_software_fallback_are_rejected(self):
        for change in [lambda s:s['outputs']['recording']['stats'].update(output_dropped_frames=1),
                       lambda s:s['outputs']['streaming']['encoding'].update(selected_hardware=False)]:
            initial=state();changed=copy.deepcopy(initial);change(changed)
            with self.assertRaises(ValueError):audit(initial,[observation(changed,1)],2)

    def test_missing_interval_is_partial_despite_matching_endpoints(self):
        initial=state()
        result=audit(initial,[observation(initial,0),observation(initial,59)],60)
        self.assertEqual(result['status'],'PARTIAL')

    def test_empty_and_reordered_observations_cannot_pass(self):
        initial=state()
        for rows in [[],[observation(initial,2),observation(initial,1)]]:
            with self.assertRaises(ValueError):audit(initial,rows,3)


if __name__ == '__main__':unittest.main()
