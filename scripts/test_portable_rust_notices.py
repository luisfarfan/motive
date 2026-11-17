#!/usr/bin/env python3
"""Integrity rejection tests; fixture text is not a third-party license audit."""
import io
import json
import pathlib
import tarfile
import tempfile
import unittest
from portable_rust_notices import sha256, supplement


class NoticeIntegrity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='motive-notice-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.directory = self.root / 'registry/src/test-index/fixture-1.0.0'
        self.directory.mkdir(parents=True)
        self.notice = b'Fixture license text, not an upstream notice.\n'
        self.spec = {'name': 'fixture', 'version': '1.0.0', 'declared_license': 'MIT',
                     'selected_license': 'MIT', 'repository': 'https://example.invalid/fixture',
                     'method': 'github_license_only_child', 'declared_revision': 'a' * 40,
                     'notice_revision': 'b' * 40, 'commit_url': 'fixture:commit',
                     'notice_url': 'fixture:license', 'notice_sha256': sha256(self.notice)}
        self.commit = {'sha': 'b' * 40, 'parents': [{'sha': 'a' * 40}],
                       'files': [{'filename': 'LICENSE', 'status': 'added'}]}
        members = {'Cargo.toml': b'[package]\nname="fixture"\nversion="1.0.0"\nlicense="MIT"\n',
                   '.cargo_vcs_info.json': json.dumps({'git': {'sha1': 'a' * 40}}).encode(),
                   'src/lib.rs': b'// Fixture source header.\npub fn fixture() {}\n'}
        archive = self.root / 'registry/cache/test-index/fixture-1.0.0.crate'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as output:
            for path, data in members.items():
                target = self.directory / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                member = tarfile.TarInfo('fixture-1.0.0/' + path)
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))
        self.spec['crate_sha256'] = sha256(archive.read_bytes())
        (self.root / 'Cargo.lock').write_text('[[package]]\nname="fixture"\nversion="1.0.0"\nchecksum="' + self.spec['crate_sha256'] + '"\n')

    def request(self, url):
        return json.dumps(self.commit).encode() if url == 'fixture:commit' else self.notice

    def resolve(self):
        return supplement(self.root, self.root / 'notices', self.directory, self.spec, self.request)

    def test_verified_child_preserves_original_declaration_and_evidence_hashes(self):
        record = self.resolve()
        self.assertEqual(record['published_files_verified'], 3)
        files = {item['file']: item for item in record['files']}
        self.assertIn('PUBLISHED-Cargo.toml', files)
        self.assertIn('PUBLISHED-SOURCE-HEADERS.txt', files)
        self.assertEqual(len(record['proof']), 1)
        for item in files.values():
            data = (self.root / 'notices/fixture-1.0.0' / item['file']).read_bytes()
            self.assertEqual(sha256(data), item['sha256'])

    def test_wrong_parent_or_code_change_does_not_resolve_notice(self):
        for commit in [
            {'sha': 'b' * 40, 'parents': [{'sha': 'c' * 40}], 'files': self.commit['files']},
            {**self.commit, 'files': self.commit['files'] + [{'filename': 'src/lib.rs', 'status': 'modified'}]},
        ]:
            self.commit = commit
            with self.assertRaisesRegex(ValueError, 'license-only child'):
                self.resolve()

    def test_modified_registry_or_license_bytes_are_rejected(self):
        path = self.directory / 'src/lib.rs'
        original = path.read_bytes()
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Registry content differs'):
            self.resolve()
        path.write_bytes(original)
        self.notice = b'Changed remote text'
        with self.assertRaisesRegex(ValueError, 'license text checksum mismatch'):
            self.resolve()


if __name__ == '__main__':
    unittest.main()
