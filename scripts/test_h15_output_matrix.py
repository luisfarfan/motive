import unittest

from verify_h15_output_matrix import matrix_outcome


def cases():
    return [{'name': str(i), 'reports': ['owned-report'], 'functional_status': 'PASS',
             'status': 'PASS'} for i in range(9)]


class MatrixOutcomeTests(unittest.TestCase):
    def test_partial_delivery_is_not_promoted_to_complete_pass(self):
        rows = cases()
        self.assertEqual(matrix_outcome(rows), 'PASS')
        rows[1]['status'] = 'PARTIAL'
        self.assertEqual(matrix_outcome(rows), 'PARTIAL')

    def test_one_failed_case_cannot_be_hidden_by_eight_successes(self):
        rows = cases()
        rows[0].update(status='FAIL', functional_status='FAIL')
        self.assertEqual(matrix_outcome(rows), 'FAIL')
        rows[0].update(status='FAIL', functional_status='PASS')
        self.assertEqual(matrix_outcome(rows), 'FAIL')

    def test_incomplete_ambiguous_or_duplicate_reports_cannot_pass(self):
        self.assertEqual(matrix_outcome(cases()[:-1]), 'FAIL')
        for reports in ([], ['one', 'two']):
            rows = cases()
            rows[0]['reports'] = reports
            self.assertEqual(matrix_outcome(rows), 'FAIL')
        rows = cases()
        rows[-1]['name'] = rows[0]['name']
        self.assertEqual(matrix_outcome(rows), 'FAIL')


if __name__ == '__main__':
    unittest.main()
