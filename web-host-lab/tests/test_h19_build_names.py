import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_native import is_h19_reproduction_name


class ReproductionNames(unittest.TestCase):
    def test_reproduction_is_closed_profile_with_fresh_label(self):
        for name in ('h19-native-multi-repro-r1-ephemeral',
                     'h19-native-multi-goal-repro-r1-ephemeral',
                     'h19-native-multi-goal-controls-repro-r1-ephemeral'):
            self.assertTrue(is_h19_reproduction_name(name))
        for name in ('../outside', 'h19-native-multi-repro-a/b-ephemeral',
                     'h19-native-multi-repro--ephemeral', 'h19-native-multi-repro-x',
                     'h19-native-multi-repro-'+'x'*25+'-ephemeral'):
            self.assertFalse(is_h19_reproduction_name(name))


if __name__ == '__main__':
    unittest.main()
