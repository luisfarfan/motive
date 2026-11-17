"""JSON/report contracts only. Never import or execute a legacy runner."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from regression_reports import FAILURE_FIELDS, PRIMARY_REPORTS, primary_acceptance, primary_report_path

SCRIPTS = Path(__file__).resolve().parent


class PrimaryReportTests(unittest.TestCase):
    def test_map_covers_exactly_the_23_wrapper_suites_without_importing_runner(self):
        tree = ast.parse((SCRIPTS / 'verify_h13_regressions.py').read_text())
        suites = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                    ('LEGACY', 'OVERLAYS', 'PERFORMANCE') for target in node.targets):
                suites.extend(ast.literal_eval(node.value))
        self.assertEqual(len(suites), 23)
        self.assertEqual(set(PRIMARY_REPORTS), set(suites))

    def test_every_suite_requires_its_exact_fresh_primary(self):
        for suite, pattern in PRIMARY_REPORTS.items():
            name = pattern.replace('*', '1794956586218721')
            with self.subTest(suite=suite):
                self.assertEqual(primary_report_path(suite, [name, 'unrelated/report.json']), name)
                with self.assertRaises(ValueError):
                    primary_report_path(suite, ['unrelated/report.json'])

    def test_fixed_alias_is_primary_not_its_duplicate_run_or_nested_stage(self):
        candidates = ['h11-runtime.json', 'h11-runtime-123/report.json',
                      'h11-runtime-123/widgets/report.json']
        self.assertEqual(primary_report_path('verify_h11_runtime.py', candidates), 'h11-runtime.json')
        with self.assertRaises(ValueError):
            primary_report_path('verify_h11_runtime.py', candidates[1:])

    def test_dynamic_run_names_are_exact_numeric_and_never_chosen_by_recency(self):
        suite = 'verify_h11_lifecycle.py'
        for invalid in ('h11-lifecycle-/report.json', 'h11-lifecycle-abc/report.json',
                        'h11-lifecycle-123/child/report.json', 'h11-lifecycle-１２３/report.json'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                primary_report_path(suite, [invalid])
        with self.assertRaises(ValueError):
            primary_report_path(suite, ['h11-lifecycle-123/report.json', 'h11-lifecycle-124/report.json'])

    def test_unknown_suite_and_noncanonical_paths_fail_closed(self):
        with self.assertRaises(ValueError):
            primary_report_path('unknown.py', ['report.json'])
        for path in ('/h1-acceptance.json', '../h1-acceptance.json', 'x/../h1-acceptance.json', './h1-acceptance.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                primary_report_path('verify_h1.py', [path])

    def test_ok_true_does_not_hide_cleanup_or_other_top_level_failure(self):
        for field in FAILURE_FIELDS:
            value = ['owned cleanup failed'] if field == 'cleanup_errors' else 'private evidence detail'
            with self.subTest(field=field):
                assessment = primary_acceptance({'ok': True, field: value})
                self.assertEqual(assessment['status'], 'FAIL')
                self.assertEqual(assessment['issues'], [{'code': 'PRIMARY_REPORTED_FAILURE', 'field': field}])
                self.assertNotIn('private evidence detail', json.dumps(assessment))

    def test_expected_nested_protocol_failures_and_cleanup_note_are_not_rejected(self):
        document = {'ok': True, 'cleanup_errors': [], 'cleanup_note': 'Loopback remains selected.',
                    'failure': {'output': 'error', 'error': 'expected TLS rejection'},
                    'peer_errors': ['expected peer EOF'],
                    'operations': [{'ok': False, 'error': {'code': 'RECOVERY_REQUIRED'}},
                                   {'cleanup_error': 'nested fixture data is not the primary outcome'}]}
        self.assertEqual(primary_acceptance(document)['status'], 'PASS')

    def test_explicit_success_is_required_and_not_coerced(self):
        for document in (None, [], 'PASS', {}, {'ok': False}, {'ok': 1}, {'ok': 'true'}):
            with self.subTest(document=document):
                self.assertEqual(primary_acceptance(document)['status'], 'FAIL')

    def test_reported_build_hash_must_match_but_not_all_legacy_reports_emit_one(self):
        expected = 'a' * 64
        self.assertEqual(primary_acceptance({'ok': True}, expected)['status'], 'PASS')
        for field in ('app_sha256', 'bundle_sha256'):
            self.assertEqual(primary_acceptance({'ok': True, field: expected}, expected)['status'], 'PASS')
            result = primary_acceptance({'ok': True, field: 'b' * 64}, expected)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['issues'][0]['code'], 'PRIMARY_BUILD_MISMATCH')


class RetainedPrimaryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compile just two pure functions from the wrapper AST. Importing the
        # runner would initialize paths/control; the test must never do that.
        tree = ast.parse((SCRIPTS / 'verify_h13_regressions.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('check', 'assess_retained_primary')]
        if len(nodes) != 2:
            raise AssertionError('Expected wrapper helper functions')
        namespace = {'hashlib': hashlib, 'json': json, 'primary_acceptance': primary_acceptance,
                     'primary_report_path': primary_report_path}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pure-wrapper-functions>', 'exec'), namespace)
        cls.assess = staticmethod(namespace['assess_retained_primary'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='motive-primary-report-unit-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'run'
        self.suite = 'verify_h1.py'
        self.name = PRIMARY_REPORTS[self.suite]
        self.copy = self.directory / 'reports' / self.suite / self.name
        self.copy.parent.mkdir(parents=True)

    def retain(self, document):
        content = json.dumps(document).encode()
        self.copy.write_bytes(content)
        return {'reports': {self.name: hashlib.sha256(content).hexdigest()}}

    def test_ok_true_cleanup_error_in_fresh_copy_fails_and_preserves_original_bytes(self):
        entry = self.retain({'ok': True, 'cleanup_error': 'source removal failed'})
        before = self.copy.read_bytes()
        # A later successful alias outside this run cannot repair retained evidence.
        (self.directory / self.name).write_text('{"ok":true}')
        result = self.assess(self.suite, entry, self.directory, 'a' * 64)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['path'], str(self.copy))
        self.assertEqual(self.copy.read_bytes(), before)
        self.assertEqual(result['sha256'], entry['reports'][self.name])

    def test_historical_copy_not_marked_fresh_is_not_eligible(self):
        self.retain({'ok': True})
        result = self.assess(self.suite, {'reports': {}}, self.directory, None)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['issues'][0]['code'], 'PRIMARY_UNAVAILABLE_OR_INVALID')

    def test_retained_hash_tampering_and_invalid_json_fail(self):
        entry = self.retain({'ok': True})
        self.copy.write_text('{"ok":true,"changed":true}')
        self.assertEqual(self.assess(self.suite, entry, self.directory, None)['status'], 'FAIL')
        self.copy.write_bytes(b'{invalid')
        entry['reports'][self.name] = hashlib.sha256(self.copy.read_bytes()).hexdigest()
        self.assertEqual(self.assess(self.suite, entry, self.directory, None)['status'], 'FAIL')

    def test_clean_fresh_primary_has_independent_acceptance_and_hash(self):
        entry = self.retain({'ok': True, 'cleanup_errors': [], 'operations': [{'ok': False, 'error': 'expected'}]})
        result = self.assess(self.suite, entry, self.directory, None)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['sha256'], entry['reports'][self.name])
        self.assertNotIn('exit_code', result)


if __name__ == '__main__':
    unittest.main()
