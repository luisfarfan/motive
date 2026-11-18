#!/usr/bin/env python3
"""Meaningful negative checks for the corresponding-source gitlink inventory."""
import copy
import hashlib
import json
import unittest

from portable_source_submodules import relative_path, review, validate_tree


def source(name, revision, modules=None, parent=None):
    result = {'name': name, 'revision': revision, 'archive_revision': revision,
              'file': name + '.tar.gz', 'sha256': 'archive-hash', 'status': 'PASS',
              'upstream_url': 'https://github.com/example/' + name, 'role': 'test'}
    if modules is not None:
        contents = ''.join(f'[submodule "{path}"]\npath = {path}\nurl = https://github.com/example/{child}.git\n'
                           for path, child in modules.items())
        result['submodules_to_review'] = [{'path': name + '/.gitmodules', 'contents': contents}]
    if parent:
        result.update(parent_source=parent[0], parent_revision=parent[1], submodule_path=parent[2])
    return result


class SubmoduleTests(unittest.TestCase):
    def setUp(self):
        self.sources = [source('root', '1', {'deps/child': 'child'}),
                        source('child', '2', {'nested/leaf': 'leaf'}, ('root', '1', 'deps/child')),
                        source('leaf', '3', {}, ('child', '2', 'nested/leaf'))]
        self.proofs = [{'source': 'root', 'revision': '1', 'status': 'PASS', 'gitlinks': {'deps/child': '2'}},
                       {'source': 'child', 'revision': '2', 'status': 'PASS', 'gitlinks': {'nested/leaf': '3'}},
                       {'source': 'leaf', 'revision': '3', 'status': 'PASS', 'gitlinks': {}}]

    def test_nested_mapping_and_empty_declaration_are_complete_material_only(self):
        result = review(self.sources, self.proofs)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['layout'][1]['unpack_under'], 'root/deps/child/nested/leaf')
        self.assertIn('no rebuild', result['scope'])

    def test_missing_transitive_or_wrong_revision_is_not_complete(self):
        self.assertEqual(review(self.sources[:2], self.proofs)['status'], 'PARTIAL')
        changed = copy.deepcopy(self.sources)
        changed[2]['revision'] = changed[2]['archive_revision'] = '4'
        self.assertEqual(review(changed, self.proofs)['status'], 'PARTIAL')
        changed = copy.deepcopy(self.sources)
        changed[1]['parent_revision'] = 'old'
        self.assertEqual(review(changed, self.proofs)['status'], 'PARTIAL')
        self.assertEqual(review(self.sources, self.proofs[:2])['status'], 'PARTIAL')

    def test_unexpected_paths_repositories_or_unverified_archive_are_rejected(self):
        for path in ['../escape', '/absolute', '.', 'a//b', 'a/../b']:
            with self.assertRaises(ValueError):
                relative_path(path)
        for key, value in [('upstream_url', 'https://github.com/unrelated/project'),
                           ('archive_revision', 'other'), ('status', 'BLOCKED')]:
            changed = copy.deepcopy(self.sources)
            changed[2][key] = value
            self.assertEqual(review(changed, self.proofs)['status'], 'PARTIAL')

    def test_tree_requires_exact_bytes_revision_and_complete_listing(self):
        tree = {'sha': '1', 'truncated': False, 'tree': [
            {'type': 'commit', 'mode': '160000', 'path': 'deps/child', 'sha': '2'}]}
        data = json.dumps(tree).encode()
        spec = {'revision': '1', 'sha256': hashlib.sha256(data).hexdigest()}
        self.assertEqual(validate_tree(data, spec), {'deps/child': '2'})
        with self.assertRaises(ValueError):
            validate_tree(data + b' ', spec)
        for key, value in [('sha', 'other'), ('truncated', True)]:
            changed = {**tree, key: value}
            data = json.dumps(changed).encode()
            with self.assertRaises(ValueError):
                validate_tree(data, {**spec, 'sha256': hashlib.sha256(data).hexdigest()})

    def test_parent_archive_must_identify_the_proven_revision(self):
        # All configured fields and the git tree can agree while the parent
        # archive is the wrong checkout. It must not close the material gate.
        for archive_revision in ['WRONG_COMMIT', None]:
            changed = copy.deepcopy(self.sources)
            changed[0]['archive_revision'] = archive_revision
            result = review(changed, self.proofs)
            self.assertEqual(result['status'], 'PARTIAL')
            self.assertTrue(any(item['source'] == 'root' and 'archive revision' in item['error']
                                for item in result['issues']))


if __name__ == '__main__':
    unittest.main()
