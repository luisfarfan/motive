"""Scalar equivalence only; physical mode/cleanup gates require native evidence."""
import unittest
from h21_display_mode import equivalent_mode


class DisplayModeComparison(unittest.TestCase):
    def test_alias_does_not_hide_physical_configuration_changes(self):
        original = dict(width=3840,height=1080,pixel_width=3840,pixel_height=1080,
                        refresh_hz=240,mode_id=111,io_flags=3)
        alias = dict(original, mode_id=110)
        self.assertTrue(equivalent_mode(original, alias))
        for key,value in [('width',3200),('height',900),('pixel_width',7680),
                          ('pixel_height',2160),('refresh_hz',120),('io_flags',7)]:
            self.assertFalse(equivalent_mode(original,dict(alias,**{key:value})),key)

    def test_missing_physical_properties_are_not_equivalent(self):
        original = dict(width=3840,height=1080,pixel_width=3840,pixel_height=1080,
                        refresh_hz=240,mode_id=111,io_flags=3)
        for key in original.keys()-{'mode_id'}:
            incomplete = dict(original);del incomplete[key]
            self.assertFalse(equivalent_mode(original,incomplete),key)


if __name__=='__main__':unittest.main()
