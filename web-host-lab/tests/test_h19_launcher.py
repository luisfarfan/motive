import argparse
import importlib.util
import socket
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_h19_multi as runner


def args(**changes):
    values = dict(instances=3, scenario='steady', width=640, height=360, fps=30,
                  duration_ms=72000, deadline_seconds=85, rss_limit_mib=2048,
                  generation=19001, expected_sha256='a'*64)
    values.update(changes)
    return argparse.Namespace(**values)


class H19Launcher(unittest.TestCase):
    def test_closed_configuration_bounds(self):
        runner.validate_options(args())
        for change in ({'instances': 6}, {'rss_limit_mib': 2049}, {'scenario': 'arbitrary'},
                       {'duration_ms': 600001}, {'generation': 2**53}, {'fps': 90},
                       {'deadline_seconds': float('nan')}, {'width': 4096},
                       {'scenario': 'lifecycle', 'instances': 5}):
            with self.assertRaises(ValueError):
                runner.validate_options(args(**change))

    def test_canary_owns_port_and_closes_without_requests(self):
        # No browser. Bind first, then prove a second launcher cannot point at an
        # unrelated existing service by reusing the port. Skip if owner is busy.
        try:
            canary = runner.OwnedCanary()
        except OSError:
            self.skipTest('fixed canary port already in use; no requests sent')
        try:
            with self.assertRaises(OSError):
                runner.OwnedCanary()
            self.assertEqual(canary.connections, 0)
        finally:
            canary.close()


if __name__ == '__main__':
    unittest.main()
