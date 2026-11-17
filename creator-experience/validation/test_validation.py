"""Negative controls for byte and authoring boundaries, no engine or devices."""
import pathlib
import struct
import tempfile
import unittest
import zlib

from validate import png, safe_file, svg


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def image(rows=b"\0\xff\xff\xff\xff"):
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class AssetBoundaryTests(unittest.TestCase):
    def setUp(self):
        target = pathlib.Path(__file__).parent / "target"
        target.mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=target)
        self.root = pathlib.Path(self.scratch.name)

    def tearDown(self):
        self.scratch.cleanup()

    def write_png(self, content):
        path = self.root / "example.png"
        path.write_bytes(content)
        return path

    def test_valid_png_decodes_all_rows(self):
        self.assertEqual(png(self.write_png(image()))["decoded_scanline_bytes"], 5)

    def test_corrupted_crc_rejected(self):
        content = bytearray(image())
        content[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            png(self.write_png(content))

    def test_decompression_cannot_exceed_declared_dimensions(self):
        with self.assertRaisesRegex(ValueError, "decompression"):
            png(self.write_png(image(b"\0" * 1_000_000)))

    def test_invalid_filter_rejected_after_decompression(self):
        with self.assertRaisesRegex(ValueError, "filter"):
            png(self.write_png(image(b"\5\xff\xff\xff\xff")))

    def test_trailing_payload_rejected(self):
        with self.assertRaisesRegex(ValueError, "trailing"):
            png(self.write_png(image() + b"unexpected"))

    def test_svg_script_and_remote_dependencies_rejected(self):
        path = self.root / "example.svg"
        for content in ('<svg><script>noop</script></svg>', '<svg><image href="https://example.invalid/asset.png"/></svg>'):
            path.write_text(content)
            with self.assertRaises(ValueError):
                svg(path)

    def test_symlink_and_parent_traversal_rejected(self):
        target = self.write_png(image())
        (self.root / "link.png").symlink_to(target)
        with self.assertRaises(ValueError):
            safe_file(self.root, "link.png")
        with self.assertRaises(ValueError):
            safe_file(self.root, "../example.png")


if __name__ == "__main__":
    unittest.main(verbosity=2)
