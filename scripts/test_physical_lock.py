"""Exercise lease release/retention in temporary independent repositories."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class PhysicalLease(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git','init','--quiet',str(self.root)],check=True)
        scripts = self.root/'scripts'; scripts.mkdir()
        self.script = scripts/'with_physical_lock.py'
        shutil.copy2(Path(__file__).with_name('with_physical_lock.py'),self.script)
        self.lease = self.root/'var/run/physical-test.lock'

    def run_child(self, source):
        return subprocess.run([sys.executable,str(self.script),'--purpose','isolated unit test',
            '--owner','h21-root','--timeout','5','--',sys.executable,'-c',source],
            capture_output=True,text=True,timeout=10)

    def test_success_releases_own_lease(self):
        result = self.run_child('pass')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.lease.exists())

    def test_completed_failure_without_descendants_releases_lease(self):
        result = self.run_child('raise SystemExit(3)')
        self.assertEqual(result.returncode,3,result.stderr)
        self.assertFalse(self.lease.exists())

    def test_detached_cleanup_marker_retains_lease(self):
        result = self.run_child("from pathlib import Path; Path('var/run/physical-test.lock/RETAIN.json').write_text('{}')")
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requested lock retention',result.stderr)
        self.assertEqual(json.loads((self.lease/'OWNER').read_text())['owner'],'h21-root')

    def test_foreign_lease_is_unchanged_and_child_not_started(self):
        self.lease.mkdir(parents=True)
        value = '{"owner":"foreign"}\n'
        (self.lease/'OWNER').write_text(value)
        result = self.run_child("from pathlib import Path; Path('wrongly-started').touch()")
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.lease/'OWNER').read_text(),value)
        self.assertFalse((self.root/'wrongly-started').exists())


if __name__ == '__main__':
    unittest.main()
