"""Resolver contract only; no Motive process, devices, store contents or media."""
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

from verification_paths import verification_paths


class VerificationPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root, self.home = self.base / 'repo', self.base / 'home'
        self.bundle = self.base / 'Motive.app'
        contents = self.bundle / 'Contents'
        (contents / 'Resources').mkdir(parents=True)
        (contents / 'MacOS').mkdir()
        self.marker = contents / 'Resources/MotivePortable.json'
        self.marker.write_text(json.dumps({'version': 1, 'runtime_layout': 'macos-portable-v1'}))
        (contents / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'local.motive.studio', 'CFBundleExecutable': 'motive'}))
        executable = contents / 'MacOS/motive'
        executable.write_bytes(b'not executed')
        executable.chmod(0o700)
        self.env = {'MOTIVE_TEST_APP': str(self.bundle),
                    'MOTIVE_TEST_DATA_ROOT': str(self.home / 'Library/Application Support/local.motive.studio'),
                    'MOTIVE_TEST_RECORDINGS_ROOT': str(self.home / 'Movies/Motive')}

    def tearDown(self):
        self.temporary.cleanup()

    def resolve(self, env=None):
        return verification_paths(self.root, environ=self.env if env is None else env, home=self.home)

    def test_development_defaults_are_deterministic_and_read_only(self):
        value = self.resolve({})
        self.assertFalse(value.portable)
        self.assertEqual(value.client_executable, self.root / 'target/debug/motive')
        self.assertEqual(value.data_root, self.root / 'var')
        self.assertEqual(value.recordings_root, self.root / 'var/recordings')
        self.assertEqual(value.diagnostics_root, self.root / 'var/evidence')
        self.assertFalse(self.root.exists())

    def test_portable_uses_one_binary_and_real_user_paths_without_creating_them(self):
        value = self.resolve()
        self.assertEqual(value.app_executable, value.client_executable)
        self.assertEqual(value.socket, Path(self.env['MOTIVE_TEST_DATA_ROOT']) / 'run/motive.sock')
        self.assertEqual(value.diagnostics_root, self.home / 'Library/Logs/Motive')
        self.assertEqual(value.manifest()['diagnostics_root'], str(value.diagnostics_root))
        self.assertFalse(self.home.exists())
        self.assertTrue(value.portable)

    def test_partial_empty_relative_and_traversal_overrides_are_rejected(self):
        for key in self.env:
            for bad in (None, '', 'relative', '/absolute/../escape'):
                env = self.env.copy()
                if bad is None:
                    del env[key]
                else:
                    env[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    self.resolve(env)

    def test_wrong_user_stores_or_recordings_are_rejected(self):
        for key in ('MOTIVE_TEST_DATA_ROOT', 'MOTIVE_TEST_RECORDINGS_ROOT'):
            env = dict(self.env, **{key: str(self.base / 'other')})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.resolve(env)

    def test_bundle_identity_marker_and_escape_are_rejected(self):
        for marker in ({'version': True, 'runtime_layout': 'macos-portable-v1'},
                       {'version': 2, 'runtime_layout': 'macos-portable-v1'},
                       {'version': 1, 'runtime_layout': 'macos-portable-v1', 'extra': 1}):
            self.marker.write_text(json.dumps(marker))
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.resolve()
        self.marker.write_text(json.dumps({'version': 1, 'runtime_layout': 'macos-portable-v1'}))
        executable = self.bundle / 'Contents/MacOS/motive'
        executable.unlink()
        executable.symlink_to('/bin/sh')
        with self.assertRaises(ValueError):
            self.resolve()

    def test_wrong_bundle_identifier_is_rejected(self):
        info = self.bundle / 'Contents/Info.plist'
        info.write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'local.other.app', 'CFBundleExecutable': 'motive'}))
        with self.assertRaises(ValueError):
            self.resolve()

    def test_data_symlink_alias_is_rejected(self):
        data = Path(self.env['MOTIVE_TEST_DATA_ROOT'])
        data.parent.mkdir(parents=True)
        destination = self.base / 'other'
        destination.mkdir()
        data.symlink_to(destination)
        with self.assertRaises(ValueError):
            self.resolve()

    def test_portable_lock_requires_exact_worktree_and_known_owner(self):
        paths = self.resolve()
        self.assertTrue(paths.lock_matches(json.dumps({'owner': 'Codex H14 root', 'worktree': str(self.root)})))
        self.assertTrue(paths.lock_matches(json.dumps({'owner': 'H15 root', 'worktree': str(self.root)})))
        for value in ({'owner': 'Codex H13 root', 'worktree': str(self.root)},
                      {'owner': 'Codex H14 root', 'worktree': str(self.root) + '-other'}):
            self.assertFalse(paths.lock_matches(json.dumps(value)))
        self.assertFalse(paths.lock_matches('H14 ' + str(self.root)))

    def test_h17_canonical_owner_requires_exact_identity_and_worktree(self):
        paths = self.resolve()
        self.assertTrue(paths.lock_matches(json.dumps({
            'owner': 'h17-root', 'worktree': str(self.root)})))
        for value in (
            {'owner': 'h17-root', 'worktree': str(self.root) + '-other'},
            {'owner': 'h17-root', 'worktree': str(self.root) + '/'},
            {'owner': 'h17-root-other', 'worktree': str(self.root)},
            {'owner': 'other h17-root', 'worktree': str(self.root)},
            {'owner': 'h17-root ', 'worktree': str(self.root)},
            {'owner': None, 'worktree': str(self.root)},
            {'owner': 'h17-root'},
        ):
            with self.subTest(lock=value):
                self.assertFalse(paths.lock_matches(json.dumps(value)))


if __name__ == '__main__':
    unittest.main()
