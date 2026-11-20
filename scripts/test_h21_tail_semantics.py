import unittest
from h21_tail_semantics import interpret_tail


class StopSemanticsTests(unittest.TestCase):
    def test_present_tail(self):
        self.assertEqual(interpret_tail({'status':'TRACED_TAIL_PRESENT'})['status'], 'PASS')

    def test_only_proven_post_bracket_absence_is_normal(self):
        for relation in ('at_or_after_stop_bracket', 'inside_stop_bracket', 'before_stop_bracket'):
            row={'status':'STOP_BOUNDARY_PACKETS_NOT_DELIVERED', 'kinds':{
                'audio':{'absent':[{'stop_relation':relation}]}}}
            expected='PASS' if relation=='at_or_after_stop_bracket' else 'INCONCLUSIVE'
            self.assertEqual(interpret_tail(row)['status'], expected)

    def test_packet_reuse_is_not_hidden_by_stop(self):
        row={'status':'STOP_BOUNDARY_PACKETS_NOT_DELIVERED', 'kinds':{
            'video':{'absent':[{'stop_relation':'at_or_after_stop_bracket',
                               'correspondence_failure':'container_packet_already_matched'}]}}}
        self.assertEqual(interpret_tail(row)['status'], 'INCONCLUSIVE')

    def test_valid_absence_remains_failure(self):
        self.assertEqual(interpret_tail({'status':'FAIL'})['status'], 'FAIL')

    def test_receiver_loss_is_not_clean_delivery_or_automatic_exoneration(self):
        result=interpret_tail({'status':'FAIL'}, receiver_interrupted=True)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['dispatch_accounting_status'], 'FAIL')

    def test_incomplete_instrument_does_not_pass(self):
        self.assertEqual(interpret_tail({'status':'INCONCLUSIVE'})['status'], 'INCONCLUSIVE')


if __name__ == '__main__': unittest.main()
