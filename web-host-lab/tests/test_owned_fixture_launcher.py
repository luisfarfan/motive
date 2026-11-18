"""Launcher input/analysis tests only. NEVER launch CEF or claim native evidence."""
import argparse
from contextlib import redirect_stderr
from io import StringIO
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

LAB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("owned_fixture_launcher", LAB / "tools/run_owned_fixture.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class LauncherInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def options(self, **changes):
        return argparse.Namespace(**({"width": 640, "height": 360, "fps": 30, "duration_ms": 5000,
            "deadline_seconds": 10, "rss_limit_mib": 2048, "generation": None} | changes))

    def test_only_reviewed_dimensions_timing_generation_and_limits(self):
        for width, height in launcher.VIEWPORTS:
            launcher.validate_options(self.options(width=width, height=height))
        for changes in ({"width": 1280}, {"fps": 24}, {"duration_ms": 15001}, {"deadline_seconds": 26},
                        {"deadline_seconds": float("nan")}, {"deadline_seconds": 5}, {"rss_limit_mib": 2049}, {"generation": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                launcher.validate_options(self.options(**changes))

    def test_no_arbitrary_command_or_url_arguments(self):
        for option in ("--executable", "--url", "--package", "--script"):
            with self.subTest(option=option), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                launcher.parser().parse_args(["--build-root", "/fake", "--expected-sha256", "a" * 64, option, "untrusted"])

    def test_inventory_escape_and_hash_fail_before_signature_check(self):
        build = self.root / "build"
        bundle = build / "MotiveBrowserFixture.app"
        bundle.mkdir(parents=True)
        with patch.object(launcher, "LAB", self.root), patch.object(launcher.subprocess, "run", side_effect=AssertionError("must not reach codesign")):
            bad = {"binaries": [{"path": "../outside", "sha256": "a" * 64}]}
            with self.assertRaisesRegex(ValueError, "BUILD_INVENTORY_PATH"):
                launcher.verify_inventory(build, bad, "a" * 64)
            main = bundle / "Contents/MacOS/MotiveBrowserFixture"
            main.parent.mkdir(parents=True)
            main.write_bytes(b"synthetic inventory unit bytes; not executable")
            bad["binaries"][0]["path"] = str(main.relative_to(self.root))
            with self.assertRaisesRegex(ValueError, "BINARY_HASH_MISMATCH"):
                launcher.verify_inventory(build, bad, "a" * 64)

    def test_non_smoke_profile_cannot_use_smoke_analysis(self):
        build = self.root / ".cache/h18-native-bridge"
        build.mkdir(parents=True)
        evidence = self.root / "evidence"
        evidence.mkdir()
        document = {"status": "PASS", "profile": "owned-goal-bridge", "cef": {"sha256": launcher.PIN},
                    "binaries": [{"path": ".cache/h18-native-bridge/MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture", "sha256": "a" * 64}]}
        (evidence / "H18-native-bridge-build.json").write_text(json.dumps(document))
        with patch.object(launcher, "LAB", self.root), self.assertRaisesRegex(ValueError, "OWNED_SMOKE_PROFILE_REQUIRED"):
            launcher.match_build_report(build, "a" * 64)

    def test_synthetic_blank_has_no_counter_or_invented_frame_index(self):
        fixture, output = self.root / "fixture", self.root / "output"
        fixture.mkdir(); output.mkdir()
        (fixture / "first.bgra").write_bytes(bytes(640 * 360 * 4))
        result = launcher.collect_samples(fixture, output, 640, 360, 1)
        self.assertIsNone(result["first"]["frame_index"])
        self.assertFalse(result["first"]["metadata_present"])
        self.assertIsNone(result["first"]["counter"]["value_modulo_256"])
        self.assertEqual(result["first"]["alpha"]["status"], "FAIL")
        self.assertTrue(result["first"]["alpha"]["checks"]["transparent_corner"])
        self.assertEqual(result["latest"]["status"], "NOT_EVALUATED")

    def test_synthetic_counter_decoder_uses_pixels_modulo_256(self):
        pixels = bytearray(640 * 360 * 4)
        for bit in range(8):
            offset = (104 * 640 + 136 + bit * 18) * 4
            color = 255 if 138 & (1 << bit) else 51
            pixels[offset:offset + 4] = bytes((color, color, color, 255))
        result = launcher.decode_counter(pixels, 640, 360)
        self.assertEqual(result["value_modulo_256"], 138)
        self.assertNotIn("frame_index", result)

    def test_classification_keeps_pixel_success_separate_from_shutdown_failure(self):
        samples = {"first": {"counter": {"value_modulo_256": None}, "alpha": {"status": "FAIL"}},
                   "latest": {"status": "PASS", "counter": {"value_modulo_256": 138}, "alpha": {"status": "PASS"}}}
        report = launcher.classify({"reason": "deadline", "returncode": -15,
            "final_cleanup_observed_tree": True, "final_remaining_observed_pids": []}, samples)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["gates"]["alpha_pixels"], "PASS")
        self.assertEqual(report["gates"]["orderly_shutdown"], "FAIL")
        self.assertEqual(report["gates"]["visible_counter_changed"], "NOT_EVALUATED")
        self.assertIsNone(report["counter_delta_modulo_256"])

    def test_derived_png_unpremultiplies_without_changing_raw_bytes(self):
        pixels = bytes((0, 0, 128, 128, 0, 0, 0, 0))
        png = launcher.preview_png(pixels, 2, 1)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        offset, payload = 8, bytearray()
        while offset < len(png):
            length = struct.unpack_from(">I", png, offset)[0]
            kind, body = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + length]
            self.assertEqual(zlib.crc32(kind + body) & 0xffffffff, struct.unpack_from(">I", png, offset + 8 + length)[0])
            if kind == b"IDAT": payload.extend(body)
            offset += length + 12
        self.assertEqual(zlib.decompress(payload), bytes((0, 255, 0, 0, 128, 0, 0, 0, 0)))
        self.assertEqual(pixels, bytes((0, 0, 128, 128, 0, 0, 0, 0)))

    def test_failed_exclusive_output_does_not_write_into_foreign_directory(self):
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "retain.txt").write_text("retain")
        with patch.object(launcher, "match_build_report", return_value=(self.root, self.root / "unused.json", {})), \
             patch.object(launcher, "verify_inventory", return_value={"status": "PASS", "scope": "synthetic static test"}), \
             redirect_stderr(StringIO()):
            code = launcher.main(["--build-root", str(self.root), "--expected-sha256", "a" * 64,
                                  "--output-dir", str(foreign), "--preflight-only"])
        self.assertEqual(code, 1)
        self.assertEqual(list(foreign.iterdir()), [foreign / "retain.txt"])


if __name__ == "__main__":
    unittest.main()
