"""Negative/known-value checks for the offline pixel reader, not capture proof."""
import unittest

from analyze_h21_capture_lifecycle import HEIGHT, WIDTH, counters


def frame_with_panels(values):
    raw = bytearray(WIDTH * HEIGHT * 3)
    for index, value in enumerate(values):
        x0, x1, y0, y1 = 20 + index*380, 350 + index*380, 50, 350
        base = bytes((217,31,31) if index == 0 else (20,199,199))
        for y in range(y0, y1+1):
            begin = (y*WIDTH+x0)*3
            raw[begin:begin+(x1-x0+1)*3] = base*(x1-x0+1)
        if value is None:
            continue
        for bit in range(16):
            x = round(x0+(x1-x0)*(.07+bit*.055))
            y = round(y0+(y1-y0)*.725)
            color = bytes([255 if (value >> bit)&1 else 0])*3
            for dy in range(-3,4):
                for dx in range(-3,4):
                    begin = ((y+dy)*WIDTH+x+dx)*3
                    raw[begin:begin+3] = color
    return raw


class CapturePixels(unittest.TestCase):
    def test_black_frame_has_no_source(self):
        self.assertEqual(counters(bytes(WIDTH*HEIGHT*3)), {'red':None,'cyan':None})

    def test_colored_panels_alone_are_not_valid_counters(self):
        decoded = counters(frame_with_panels([None,None]))
        self.assertIsNone(decoded['red']['counter'])
        self.assertIsNone(decoded['cyan']['counter'])

    def test_distinct_source_counters_and_wrap_values(self):
        decoded = counters(frame_with_panels([0xA509,65535]))
        self.assertEqual(decoded['red']['counter'],0xA509)
        self.assertEqual(decoded['cyan']['counter'],65535)

    def test_partial_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            counters(bytes(WIDTH*HEIGHT*3-1))


if __name__ == '__main__':
    unittest.main()
