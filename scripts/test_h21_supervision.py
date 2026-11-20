"""Safety-supervisor process ownership tests; no Motive, capture or devices."""
import subprocess
import sys
import unittest
from h21_supervision import terminate_owned_child


class OwnedTermination(unittest.TestCase):
    def test_terminates_and_reaps_only_the_given_child(self):
        own=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])
        other=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])
        try:
            result=terminate_owned_child(own,'test deadline','test-sha')
            self.assertEqual(result['pid'],own.pid)
            self.assertLess(result['exit_code'],0)
            self.assertFalse(result['normal_shutdown'])
            self.assertIsNone(other.poll())
        finally:
            for child in (own,other):
                if child.poll() is None: child.terminate()
                child.wait(timeout=5)

    def test_completed_child_is_not_signaled(self):
        own=subprocess.Popen([sys.executable,'-c','pass'])
        self.assertEqual(own.wait(timeout=5),0)
        self.assertIsNone(terminate_owned_child(own,'test deadline','test-sha'))
        self.assertEqual(own.returncode,0)


if __name__=='__main__':unittest.main()
