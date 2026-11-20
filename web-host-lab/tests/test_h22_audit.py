import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_audit import gaps


class ContinuityTests(unittest.TestCase):
    def test_straddling_pause_cannot_be_hidden_by_window_clipping(self):
        r=gaps([0,100_000_000,500_000_000,550_000_000],200_000_000,400_000_000)
        self.assertEqual(r['status'],'FAIL')
        self.assertEqual(r['max_gap_ms'],400)

    def test_original_limit_is_exclusive(self):
        self.assertEqual(gaps([0,250_000_000],1,249_000_000)['status'],'FAIL')
        self.assertEqual(gaps([0,249_999_999],1,249_000_000)['status'],'PASS')

    def test_missing_edge_is_not_zero_gap(self):
        with self.assertRaisesRegex(ValueError,'PEER_WINDOW_COVERAGE'):
            gaps([20,40,60],10,50)
        with self.assertRaisesRegex(ValueError,'PEER_WINDOW_COVERAGE'):
            gaps([20,40,60],30,70)


if __name__=='__main__':unittest.main()
