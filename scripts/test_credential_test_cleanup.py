"""Owned dummy-credential cleanup tests; no Keychain, PTY, app or legacy import."""
import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from credential_test_cleanup import credential_delete_failure


class DeleteReceiptTests(unittest.TestCase):
    reference = 'kc_00000000-0000-0000-0000-000000000000'

    def test_exact_success_receipt_is_required(self):
        success = {'ok': True, 'result': 0, 'credential_ref': self.reference}
        self.assertIsNone(credential_delete_failure(success, self.reference))
        for reply in (None, [], {'ok': True}, dict(success, ok=1), dict(success, result=False),
                      dict(success, result=2), dict(success, credential_ref='different'),
                      dict(success, ok=False)):
            with self.subTest(reply=reply):
                self.assertIsNotNone(credential_delete_failure(reply, self.reference))

    def test_rejection_reports_only_bounded_code_not_arbitrary_payload(self):
        reply = {'ok': False, 'result': 2, 'credential_ref': self.reference,
                 'secret': 'private-dummy-marker', 'error': 'arbitrary private diagnostic'}
        self.assertEqual(credential_delete_failure(reply, self.reference),
                         {'code': 'CREDENTIAL_CLEANUP_DELETE_NOT_ACKNOWLEDGED', 'native_result': 2})
        reply['result'] = 'private-dummy-marker'
        self.assertEqual(credential_delete_failure(reply, self.reference),
                         {'code': 'CREDENTIAL_CLEANUP_DELETE_NOT_ACKNOWLEDGED'})


class LegacyFinallyTests(unittest.TestCase):
    """Execute only the isolated cleanup AST with fake dependencies and JSON files."""
    def execute_cleanup(self, reply, *, body_error=False, deselect_error=False, close_error=False):
        source = Path(__file__).with_name('verify_h8_keychain.py').read_text()
        tree = ast.parse(source)
        original = next(node for node in tree.body if isinstance(node, ast.Try))
        assertion = next(node for node in tree.body if isinstance(node, ast.Assert))
        body = ast.parse("raise RuntimeError('original test failure')" if body_error
                         else "report['ok'] = True").body
        fragment = ast.Try(body=body, handlers=original.handlers, orelse=[], finalbody=original.finalbody)
        module = ast.fix_missing_locations(ast.Module(body=[fragment, assertion], type_ignores=[]))
        def clear(*_args, **_kwargs):
            if deselect_error:
                raise ValueError('private-dummy-marker must not be logged')
        def close():
            if close_error:
                raise ValueError('private-dummy-marker must not be logged')
        report = {'ok': False}
        with tempfile.TemporaryDirectory(prefix='motive-credential-cleanup-unit-') as directory:
            environment = {'report': report, 'refs': [DeleteReceiptTests.reference],
                           'local': lambda *_args: reply,
                           'credential_delete_failure': credential_delete_failure,
                           'c': SimpleNamespace(ops=[], call=clear, close=close),
                           'EVIDENCE': Path(directory), 'json': json}
            error = None
            try:
                exec(compile(module, '<isolated-legacy-cleanup>', 'exec'), environment)
            except BaseException as failure:
                error = failure
            saved = json.loads((Path(directory) / 'h8-keychain.json').read_text())
        return saved, error

    def test_cleanup_rejection_fails_after_writing_original_report(self):
        report, error = self.execute_cleanup({'ok': False, 'result': 2})
        self.assertFalse(report['ok'])
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(report['cleanup_required_reference'], DeleteReceiptTests.reference)
        self.assertEqual(report['cleanup_errors'][0]['native_result'], 2)

    def test_original_exception_is_not_replaced_by_cleanup_failure(self):
        report, error = self.execute_cleanup({'ok': False, 'result': 2}, body_error=True)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), 'original test failure')
        self.assertIn('original test failure', report['error'])
        self.assertTrue(report['cleanup_errors'])

    def test_deselect_and_close_exceptions_are_reported_without_payload(self):
        success = {'ok': True, 'result': 0, 'credential_ref': DeleteReceiptTests.reference}
        report, error = self.execute_cleanup(success, deselect_error=True, close_error=True)
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(report['cleanup_error']['code'], 'CREDENTIAL_CLEANUP_DESELECT_FAILED')
        self.assertEqual(report['cleanup_errors'][0]['code'], 'CREDENTIAL_CLEANUP_CLIENT_CLOSE_FAILED')
        self.assertNotIn('private-dummy-marker', json.dumps(report))

    def test_acknowledged_cleanup_keeps_success(self):
        report, error = self.execute_cleanup({'ok': True, 'result': 0,
                                             'credential_ref': DeleteReceiptTests.reference})
        self.assertIsNone(error)
        self.assertTrue(report['ok'])
        self.assertNotIn('cleanup_errors', report)


if __name__ == '__main__':
    unittest.main()
