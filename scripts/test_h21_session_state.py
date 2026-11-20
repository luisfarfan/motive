import unittest

from h21_session_state import parse_console_locked


class SessionState(unittest.TestCase):
    def test_exact_boolean_only(self):
        self.assertTrue(parse_console_locked('  "IOConsoleLocked" = Yes\n'))
        self.assertFalse(parse_console_locked('  "IOConsoleLocked" = No\n'))

    def test_unknown_missing_or_ambiguous_is_not_unlocked(self):
        for value in ('', '"IOConsoleLocked" = 0', '"IOConsoleLocked" = No\n"IOConsoleLocked" = Yes'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_console_locked(value)
