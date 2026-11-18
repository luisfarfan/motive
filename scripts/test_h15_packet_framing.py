import unittest
from h15_packet_framing import avcc_nals, parameter_sets, unhex_dump


class FramingTests(unittest.TestCase):
    def test_lengths_and_parameter_types_are_checked(self):
        self.assertEqual(avcc_nals(b'\0\0\0\2\x65\xab'), [b'\x65\xab'])
        for malformed in (b'\0', b'\0\0\0\0', b'\0\0\0\3\x65\xab'):
            with self.assertRaises(ValueError):
                avcc_nals(malformed)
        extra = bytes([1, 100, 0, 40, 255, 225, 0, 2, 103, 1, 1, 0, 2, 104, 2])
        self.assertEqual(parameter_sets(extra), [b'\x67\x01', b'\x68\x02'])
        for malformed in (extra[:10], extra[:5], extra.replace(b'\x68', b'\x67')):
            with self.assertRaises(ValueError):
                parameter_sets(malformed)
        self.assertEqual(unhex_dump('\n00000000: 0000 0002 65ab                           ....e.\n'),
                         b'\0\0\0\2\x65\xab')


if __name__ == '__main__':
    unittest.main()
