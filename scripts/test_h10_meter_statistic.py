#!/usr/bin/env python3
"""Unit tests for the verifier's statistic, not physical audio acceptance."""
import math, statistics, unittest
from verify_h10_mixer import db, isolated_rms

class MeterStatistic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A deterministic nonstationary signal demonstrates why median buffer
        # RMS cannot be compared to the energy RMS of a whole second.
        cls.pcm=[(.1 if 1.2<=i/48000<1.6 else .01)*math.sin(2*math.pi*1000*i/48000) for i in range(4*48000)]
        cls.stage={'samples':[]}
        for i in range(1,20):
            seconds=i*.2;offset=round(seconds*48000);block=cls.pcm[offset:offset+960]
            rms=db(math.sqrt(sum(x*x for x in block)/len(block)))
            cls.stage['samples'].append({'seconds':seconds,'state':{'audio_mixer':{'runtime':{'inputs':[{'levels':{'rms_dbfs':[rms,rms]}}]}}}})
    def test_same_window_same_statistic_accepts_transient_signal(self):
        r=isolated_rms(self.pcm,self.stage,0)
        self.assertLess(abs(r['error_db']),.01)
        second=self.pcm[48000:96000]
        old=db(math.sqrt(sum(x*x for x in second)/len(second)))-r['native_median_dbfs']
        self.assertGreater(abs(old),10)
    def test_wrong_meter_calibration_still_fails_original_tolerance(self):
        pcm=[x*2 for x in self.pcm]
        r=isolated_rms(pcm,self.stage,0)
        self.assertAlmostEqual(r['error_db'],20*math.log10(2),places=4)
        self.assertGreater(abs(r['error_db']),2)
    def test_incomplete_audio_cannot_pass(self):
        with self.assertRaises(AssertionError):isolated_rms(self.pcm[:48000],self.stage,0)

if __name__=='__main__':unittest.main()
