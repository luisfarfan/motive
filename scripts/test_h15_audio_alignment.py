import copy
import unittest
from h15_audio_alignment import align_samples


class AudioClockTests(unittest.TestCase):
    def test_priming_and_host_epoch_are_explicit_without_fitting_signal(self):
        anchor = {'before':100.,'after':100.01,'trace':{'clock':'obs.os_gettime_ns',
            'observed_ns':50000000000,'snapshot_busy':False,
            'summary':{'trace_missed_records':0,'trace_overwritten_records':0},
            'packets':[{'sequence':1,'media_type':'audio','pts':-1024,'dts':-1024,
                        'sys_dts_usec':49000000,'size':42}]}}
        packets = [{'pts_time':'-0.021','size':'42'}]
        frames = [{'best_effort_timestamp_time':'0.000','nb_samples':1024},
                  {'best_effort_timestamp_time':'0.021','nb_samples':1024}]
        self.assertAlmostEqual(align_samples(anchor,packets,frames,2048)['first_sample_host_s'],99.026)
        for kind in ('wide_clock','lost_prefix','size','samples','gap'):
            a,p,f = copy.deepcopy((anchor,packets,frames))
            if kind=='wide_clock': a['after']+=.1
            if kind=='lost_prefix': a['trace']['packets'][0]['sequence']=2
            if kind=='size': p[0]['size']='43'
            if kind=='samples': f[0]['nb_samples']=1023
            if kind=='gap': f[1]['best_effort_timestamp_time']='0.1'
            with self.assertRaises(ValueError): align_samples(a,p,f,2048)


if __name__ == '__main__': unittest.main()
