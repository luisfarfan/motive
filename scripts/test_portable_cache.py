#!/usr/bin/env python3
"""Check cache writes cannot escape through predictable or dangling symlinks."""
import hashlib
import io
import pathlib
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import prepare_portable_sources
from portable_cache import write_cache_atomically
from portable_source_submodules import prepare_proofs


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.outside = self.root / 'outside'

    def test_dangling_or_existing_target_symlink_is_rejected_without_writing(self):
        path = self.cache / 'entry'
        path.symlink_to(self.outside)
        for existing in [False, True]:
            if existing:
                self.outside.write_bytes(b'original')
            with self.assertRaises(ValueError):
                write_cache_atomically(path, lambda target: target.write(b'changed'))
            self.assertTrue(path.is_symlink())
            if existing:
                self.assertEqual(self.outside.read_bytes(), b'original')
            else:
                self.assertFalse(self.outside.exists())

    def test_symlink_created_during_staging_is_rejected_and_temp_is_removed(self):
        path = self.cache / 'entry'

        def writer(target):
            target.write(b'new')
            path.symlink_to(self.outside)

        with self.assertRaises(ValueError):
            write_cache_atomically(path, writer)
        self.assertFalse(self.outside.exists())
        self.assertEqual(list(self.cache.iterdir()), [path])

    def test_validation_failure_never_publishes_partial_cache(self):
        def invalid(_):
            raise ValueError('bad hash')

        path = self.cache / 'entry'
        with self.assertRaises(ValueError):
            write_cache_atomically(path, lambda target: target.write(b'bad'), invalid)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_proof_rejects_dangling_symlink_before_network_or_write(self):
        path = self.cache / 'example-rev-tree.json'
        path.symlink_to(self.outside)
        with patch('portable_source_submodules.urllib.request.urlopen') as network:
            result = prepare_proofs([{'source': 'example', 'revision': 'rev', 'url': 'https://example.invalid',
                                      'sha256': 'unused'}], self.cache, True)
        network.assert_not_called()
        self.assertEqual(result[0]['status'], 'BLOCKED')
        self.assertFalse(self.outside.exists())
        self.assertTrue(path.is_symlink())

    def archive(self):
        memory = io.BytesIO()
        with tarfile.open(fileobj=memory, mode='w:gz') as stream:
            data = b''
            member = tarfile.TarInfo('example/.gitmodules')
            member.size = len(data)
            stream.addfile(member, io.BytesIO(data))
        return memory.getvalue()

    def test_archive_ignores_legacy_part_symlink_and_publishes_verified_bytes(self):
        data = self.archive()
        path = self.cache / 'example-1.tar.gz'
        legacy = path.with_suffix(path.suffix + '.part')
        legacy.symlink_to(self.outside)
        record = {'name': 'example', 'version': '1', 'archive_url': 'https://example.invalid/archive.tar.gz',
                  'sha256': hashlib.sha256(data).hexdigest()}
        with patch.object(prepare_portable_sources, 'CACHE', self.cache), \
                patch('prepare_portable_sources.urllib.request.urlopen', return_value=io.BytesIO(data)):
            result = prepare_portable_sources.fetch_source(record, True)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(path.read_bytes(), data)
        self.assertTrue(legacy.is_symlink())
        self.assertFalse(self.outside.exists())

    def test_archive_dangling_destination_rejects_download_and_local_copy(self):
        data = self.archive()
        path = self.cache / 'example-1.tar.gz'
        path.symlink_to(self.outside)
        original = self.root / 'original.tar.gz'
        original.write_bytes(data)
        record = {'name': 'example', 'version': '1', 'archive_url': 'https://example.invalid/archive.tar.gz',
                  'local': str(original), 'sha256': hashlib.sha256(data).hexdigest()}
        with patch.object(prepare_portable_sources, 'CACHE', self.cache), \
                patch('prepare_portable_sources.urllib.request.urlopen') as network:
            result = prepare_portable_sources.fetch_source(record, True)
        network.assert_not_called()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertTrue(path.is_symlink())
        self.assertFalse(self.outside.exists())


if __name__ == '__main__':
    unittest.main()
