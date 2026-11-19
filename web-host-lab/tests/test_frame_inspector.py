"""Layout validation only; no fabricated native evidence or alpha PASS."""
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frame_inspector', ROOT / 'poc/frame-consumer/check_frame.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrameInspectorLayout(unittest.TestCase):
    def test_reviewed_viewports_pass_layout_then_reject_non_native_input(self):
        for width, height in [(640, 360), (960, 540), (540, 960)]:
            meta = {'width': width, 'height': height, 'stride': width * 4, 'native_executed': False}
            with self.assertRaisesRegex(ValueError, 'NOT_NATIVE_EVIDENCE'):
                module.inspect(meta, bytes(width * height * 4))

    def test_wrong_stride_size_and_unknown_viewport_rejected(self):
        for width, height, stride, length in [(540, 960, 540 * 4 + 1, 540 * 960 * 4), (640, 360, 2560, 1), (641, 360, 2564, 641 * 360 * 4)]:
            with self.assertRaisesRegex(ValueError, 'FRAME_LAYOUT'):
                module.inspect({'width': width, 'height': height, 'stride': stride}, bytes(length))
