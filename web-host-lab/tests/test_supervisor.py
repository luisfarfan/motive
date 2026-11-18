import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('motive_supervisor', ROOT / 'poc/browser-host/supervisor.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.cache')
        self.root = Path(self.temp.name)
        self.reports = []

    def tearDown(self):
        self.temp.cleanup()

    def supervisor(self, **kw):
        return module.Supervisor(self.root, **kw)

    def run_owned(self, supervisor, code, **kw):
        result = supervisor.run([sys.executable, '-c', code], **kw)
        self.reports.append(result)
        self.assertTrue(result['cleanup_observed_tree'], result)
        self.assertTrue(result['final_cleanup_observed_tree'], result)
        return result

    def test_exit_and_restart_use_distinct_generations(self):
        s = self.supervisor()
        a = self.run_owned(s, 'print("owned non-browser fixture")')
        b = self.run_owned(s, 'raise SystemExit(9)')
        self.assertEqual((a['generation'], b['generation']), (1, 2))
        self.assertEqual((a['returncode'], b['returncode']), (0, 9))

    def test_external_deadline_terminates_child_tree(self):
        r = self.run_owned(self.supervisor(deadline_seconds=0.4),
            'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); time.sleep(30)')
        self.assertEqual(r['reason'], 'deadline')
        self.assertGreaterEqual(r['observed_processes'], 2)
        self.assertLess(r['elapsed_ms'], 3000)

    def test_cancellation_and_rss_limit_are_external(self):
        r = self.run_owned(self.supervisor(), 'import time; time.sleep(30)', cancelled=lambda: True)
        self.assertEqual(r['reason'], 'cancelled')
        # Limit below the interpreter's resident footprint; not a CEF memory result.
        r = self.run_owned(self.supervisor(rss_limit_kib=1), 'import time; time.sleep(30)')
        self.assertEqual(r['reason'], 'rss_limit')

    def test_parent_crash_does_not_leave_observed_child(self):
        code = 'import subprocess,sys,time,os; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); time.sleep(.15); os._exit(11)'
        r = self.run_owned(self.supervisor(), code)
        self.assertEqual(r['returncode'], 11)
        self.assertGreaterEqual(r['observed_processes'], 2)

    def test_exception_cleans_observed_child_that_changed_session(self):
        s = self.supervisor()
        started = time.monotonic()
        def cancel_check():
            if time.monotonic() - started > .3:
                raise RuntimeError('controlled supervisor callback failure')
            return False
        code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import os,time; os.setsid(); time.sleep(30)"]); time.sleep(30)'
        with self.assertRaisesRegex(RuntimeError, 'controlled supervisor'):
            s.run([sys.executable, '-c', code], cancelled=cancel_check)
        self.assertTrue(s.last_report['final_cleanup_observed_tree'], s.last_report)
        self.assertEqual(s.last_report['reason'], 'supervisor_error')
        self.assertFalse(s.active)

    def test_invalid_root_and_limits(self):
        os.chmod(self.root, 0o755)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_ROOT'): self.supervisor()
        os.chmod(self.root, 0o700)
        with self.assertRaisesRegex(ValueError, 'LIMITS'): self.supervisor(deadline_seconds=0)
        with self.assertRaisesRegex(ValueError, 'ABSOLUTE'): self.supervisor().run(['python3'])


if __name__ == '__main__': unittest.main()
