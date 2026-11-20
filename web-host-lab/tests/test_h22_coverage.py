"""Coverage must retain failed executions and reject substituted evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from h22_coverage import coverage
from h22_matrix import LAB


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LAB / '.cache')
        self.root = Path(self.temp.name)
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({'suite': 'widgets', 'cases': [
            ['goal3h-r1', 'closed-build', 'goal-load', 3, 72, 640, 360, True]]}))
        self.row = {'suite': 'widgets', 'case': 'goal3h-r1', 'path': 'observed-fail',
            'build': 'closed-build', 'scenario': 'goal-load', 'instances': 3,
            'seconds': 72, 'width': 640, 'height': 360, 'fps': 30,
            'native_status': 'PASS', 'functional': 'PASS', 'performance': 'FAIL',
            'network_lab': 'PASS', 'case_result': 'FAIL'}
        self.matrix = self.root / 'matrix.json'

    def tearDown(self):
        self.temp.cleanup()

    def check_rows(self, rows):
        self.matrix.write_text(json.dumps({'rows': rows}))
        return coverage(self.matrix, [self.root])

    def test_completed_failure_is_coverage_not_acceptance(self):
        result = self.check_rows([self.row])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['groups'][0]['result'], 'FAIL')
        self.assertFalse(result['groups'][0]['admits_72s_configuration'])

    def test_duplicate_execution_cannot_replace_failure(self):
        replacement = dict(self.row, path='later-pass', performance='PASS')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_EXECUTION'):
            self.check_rows([self.row, replacement])

    def test_resolution_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValueError, 'CONFIGURATION_MISMATCH'):
            self.check_rows([dict(self.row, width=320)])

    def test_unexecuted_row_does_not_fill_coverage(self):
        pending = {k: v for k, v in self.row.items() if k != 'native_status'}
        result = self.check_rows([pending])
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['executed_cases'], 0)
        self.assertEqual(len(result['missing']), 1)

    def test_unexecuted_plan_row_can_map_to_one_actual_run(self):
        pending = {k: v for k, v in self.row.items() if k != 'native_status'}
        result = self.check_rows([pending, self.row])
        self.assertEqual(result['executed_cases'], 1)
        self.assertEqual(result['groups'][0]['result'], 'FAIL')

    def test_short_operation_pass_is_not_sustained_capacity(self):
        self.plan.write_text(json.dumps({'suite': 'widgets', 'cases': [
            ['goal3h-r1', 'closed-build', 'goal-load', 3, 12, 640, 360, True]]}))
        result=self.check_rows([dict(self.row,seconds=12,case_result='PASS',performance='NOT_EVALUATED')])
        self.assertEqual(result['groups'][0]['result'],'PASS')
        self.assertEqual(result['groups'][0]['performance_pass'],0)
        self.assertFalse(result['groups'][0]['admits_72s_configuration'])

    def test_three_missing_cadence_windows_never_admit_72s(self):
        self.plan.write_text(json.dumps({'suite': 'widgets', 'cases': [
            [f'goal3h-r{i}', 'closed-build', 'goal-load', 3, 72, 640, 360, True] for i in (1,2,3)]}))
        rows=[dict(self.row,case=f'goal3h-r{i}',path=f'observed-{i}',case_result='PASS',performance='NOT_EVALUATED') for i in (1,2,3)]
        result=self.check_rows(rows)
        self.assertFalse(result['groups'][0]['admits_72s_configuration'])


if __name__ == '__main__':
    unittest.main()
