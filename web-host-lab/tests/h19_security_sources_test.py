"""Negative source provenance checks; these never execute native content."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from h19_security_sources import verify_sources
from h19_distribution_audit import inventory


class Provenance(unittest.TestCase):
    def test_missing_changed_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".cache/h19-source-research/cef/source.cc"
            path.parent.mkdir(parents=True)
            row = {"path": "source.cc", "cache": str(path.relative_to(root)), "bytes": 3,
                   "sha256": hashlib.sha256(b"abc").hexdigest(), "repository": "chromiumembedded/cef",
                   "revision": "fixed", "url": "https://raw.githubusercontent.com/chromiumembedded/cef/fixed/source.cc"}
            self.assertEqual(verify_sources({"sources": [row]}, root)["status"], "FAIL")
            path.write_bytes(b"abc")
            self.assertEqual(verify_sources({"sources": [row]}, root)["status"], "PASS")
            path.write_bytes(b"xyz")
            self.assertEqual(verify_sources({"sources": [row]}, root)["files"][0]["status"], "HASH_MISMATCH")
            with self.assertRaises(ValueError):
                verify_sources({"sources": [{**row, "cache": "../outside"}]}, root)
            with self.assertRaises(ValueError):
                verify_sources({"sources": [{**row, "url": "https://example.invalid/arbitrary"}]}, root)

    def test_failed_research_lookup_never_counts_as_verified_source(self):
        with tempfile.TemporaryDirectory() as directory:
            result = verify_sources({"sources": [{"error": "404"}]}, Path(directory))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["files"], [])

    def test_inventory_rejects_external_links_and_avoids_internal_alias_double_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "Fixture.app"
            bundle.mkdir()
            (bundle / "real").write_bytes(b"abc")
            (bundle / "alias").symlink_to("real")
            result = inventory(bundle)
            self.assertEqual(result["apparent_file_bytes"], 3)
            self.assertEqual(result["unique_inode_file_bytes"], 3)
            (root / "outside").write_bytes(b"owned-decoy")
            (bundle / "escape").symlink_to("../outside")
            with self.assertRaisesRegex(ValueError, "BUNDLE_SYMLINK_ESCAPE"):
                inventory(bundle)


if __name__ == "__main__":
    unittest.main()
