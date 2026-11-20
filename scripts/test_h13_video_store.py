import tempfile
import unittest
from pathlib import Path

from verify_h13_video import restore_owned_project


class ProjectStoreRestorationTests(unittest.TestCase):
    def test_restores_exact_bytes_and_original_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'project.json'
            path.write_bytes(b'owned generated project')
            path.chmod(0o644)
            restore_owned_project(path, b'owned generated project', b'original\n', 0o600)
            self.assertEqual(path.read_bytes(), b'original\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_foreign_write_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'project.json'
            path.write_bytes(b'new owner edit')
            with self.assertRaisesRegex(AssertionError, 'another writer'):
                restore_owned_project(path, b'owned generated project', b'original', 0o600)
            self.assertEqual(path.read_bytes(), b'new owner edit')

    def test_absent_original_removed_but_symlink_target_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'project.json'
            path.write_bytes(b'owned')
            restore_owned_project(path, b'owned', None, None)
            self.assertFalse(path.exists())
            target = Path(folder)/'other.json'
            target.write_bytes(b'owned')
            path.symlink_to(target)
            with self.assertRaisesRegex(AssertionError, 'symlink'):
                restore_owned_project(path, b'owned', b'original', 0o600)
            self.assertEqual(target.read_bytes(), b'owned')


if __name__ == '__main__':
    unittest.main()
