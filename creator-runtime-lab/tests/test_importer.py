"""Real archives, strict offline Rust semantics, and real descriptor filesystem IO."""
from dataclasses import FrozenInstanceError
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "creator-runtime-lab/importer"))
from runtime_importer import ReviewPolicy, review_package, stage_package
from common import LabError, encode, loads
from packaging import make_archive
from schemas import CAPABILITIES

PACKAGES = ROOT / "element-lab/marketplace-contract/packages"
POLICY = ReviewPolicy(available_capabilities=frozenset(CAPABILITIES))


def rebuilt(data, change):
    """Recompute every hash/count to test semantics independently of corruption."""
    with zipfile.ZipFile(BytesIO(data)) as archive:
        files = {info.filename: archive.read(info) for info in archive.infolist()}
    metadata = loads(files.pop("package.json"))
    files.pop("checksums.json")
    change(files)
    manifest = loads(files["manifest.json"])
    return make_archive(files, manifest, "declarative_pack", metadata["preview_paths"])


def raw_rewrite(data, change):
    with zipfile.ZipFile(BytesIO(data)) as archive:
        files = [(info, archive.read(info)) for info in archive.infolist()]
    change(files)
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for info, body in files:
            archive.writestr(info, body)
    return out.getvalue()


class ImporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (PACKAGES / "lower-third.motivepack").read_bytes()
        cls.review = review_package(PACKAGES / "lower-third.motivepack", POLICY)

    def setUp(self):
        # Resolve the platform temp root once: macOS /var is itself a system symlink.
        self.tmp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def review_bytes(self, data, policy=POLICY):
        path = self.root / "candidate.motivepack"
        path.write_bytes(data)
        return review_package(path, policy)

    def rejects(self, code, function):
        with self.assertRaises(LabError) as result:
            function()
        self.assertEqual(result.exception.code, code)

    def test_all_seven_original_examples_and_dependency_inventory(self):
        for path in sorted(PACKAGES.glob("*.motivepack")):
            with self.subTest(package=path.name):
                reviewed = review_package(path, POLICY)
                self.assertEqual(reviewed.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertFalse(reviewed.report["official_installation_format"])
                self.assertFalse(reviewed.report["owner_authorized"])
                self.assertFalse(reviewed.report["creator_identity_verified"])
                self.assertEqual(reviewed.report["dependencies"]["resolution"], "embedded_inventory_only")
                self.assertEqual(reviewed.report["resource_bytes"], sum(map(len, reviewed.assets.values())))
                self.assertEqual(reviewed.as_bundle().pack, reviewed.manifest)

    def test_review_snapshot_and_bundle_are_independent_of_mutations(self):
        reviewed = self.review_bytes(self.original)
        (self.root / "candidate.motivepack").write_bytes(b"changed original")
        manifest = reviewed.manifest
        manifest["name"] = "changed copy"
        bundle = reviewed.as_bundle()
        bundle.pack["name"] = "another changed copy"
        bundle.assets.clear()
        self.assertEqual(reviewed.sha256, self.review.sha256)
        self.assertEqual(reviewed.manifest["name"], self.review.manifest["name"])
        self.assertTrue(reviewed.assets)
        with self.assertRaises(TypeError):
            reviewed.assets["new.png"] = b"no"
        with self.assertRaises(FrozenInstanceError):
            reviewed._archive = b"no"

    def test_caps_and_license_policy_are_caller_inputs(self):
        self.rejects("CAPABILITY_UNAVAILABLE", lambda: self.review_bytes(self.original, ReviewPolicy()))
        self.rejects("LICENSE_POLICY", lambda: self.review_bytes(self.original,
            ReviewPolicy(available_capabilities=POLICY.available_capabilities, allowed_licenses=frozenset())))
        self.rejects("LICENSE_TEXT", lambda: self.review_bytes(rebuilt(self.original,
            lambda f: f.update({"LICENSE": b"not a license " * 100}))))

    def test_resource_budget_is_not_a_memory_measurement(self):
        self.rejects("RESOURCE_BUDGET", lambda: self.review_bytes(self.original,
            ReviewPolicy(available_capabilities=POLICY.available_capabilities, max_resource_bytes=0)))
        self.rejects("STAGING_BUDGET", lambda: self.review_bytes(self.original,
            ReviewPolicy(available_capabilities=POLICY.available_capabilities, max_staging_bytes=0)))
        self.assertFalse(self.review.report["budget"]["rss_measured"])
        self.rejects("REVIEW_POLICY", lambda: ReviewPolicy(max_resource_bytes=True))
        self.rejects("REVIEW_POLICY", lambda: ReviewPolicy(max_resource_bytes=129 * 1024**2))

    def test_baseline_version_and_identity_validation(self):
        self.rejects("PACKAGE_BASELINE", lambda: self.review_bytes(self.original,
            ReviewPolicy(available_capabilities=POLICY.available_capabilities, supported_baselines=frozenset())))
        def version(files):
            manifest = loads(files["manifest.json"])
            manifest["schema_version"] = 2
            files["manifest.json"] = encode(manifest)
        self.rejects("PACK_VERSION", lambda: self.review_bytes(rebuilt(self.original, version)))
        def malformed_identity(files):
            manifest = loads(files["manifest.json"])
            manifest["id"] = "../escape"
            files["manifest.json"] = encode(manifest)
        with self.assertRaises(LabError):
            self.review_bytes(rebuilt(self.original, malformed_identity))

    def test_hash_corruption_and_malformed_zip(self):
        def corrupt(files):
            for index, (info, data) in enumerate(files):
                if info.filename == "LICENSE":
                    files[index] = (info, data + b"tamper")
        self.rejects("PACKAGE_HASH", lambda: self.review_bytes(raw_rewrite(self.original, corrupt)))
        self.rejects("PACKAGE_ZIP", lambda: self.review_bytes(b"not zip"))

    def test_nul_truncated_zip_name_is_rejected(self):
        # Replace an existing same-length name in both local and central headers.
        # Construct an equal-length alias so offsets stay valid.
        def alias(files):
            for info, _ in files:
                if info.filename == "LICENSE":
                    info.filename = "LICENSE-x"
        malicious = raw_rewrite(self.original, alias).replace(b"LICENSE-x", b"LICENSE\x00x")
        self.rejects("PACKAGE_PATH", lambda: self.review_bytes(malicious))

    def test_png_bytes_rejected_even_with_correct_container_hashes(self):
        def bad_png(files):
            manifest = loads(files["manifest.json"])
            resource = manifest["resources"][0]
            data = b"not-png"
            resource["bytes"] = len(data)
            resource["sha256"] = hashlib.sha256(data).hexdigest()
            files["assets/" + resource["file_name"]] = data
            files["manifest.json"] = encode(manifest)
        self.rejects("ASSET_CONTENT", lambda: self.review_bytes(rebuilt(self.original, bad_png)))

    def test_archive_traversal_symlink_executable_collision_and_bomb(self):
        cases = [("../escape", stat.S_IFREG | 0o644, 0),
                 ("symlink", stat.S_IFLNK | 0o777, 0),
                 ("executable", stat.S_IFREG | 0o755, 0),
                 ("license", stat.S_IFREG | 0o644, 0),
                 ("bomb", stat.S_IFREG | 0o644, zipfile.ZIP_DEFLATED)]
        for name, mode, compression in cases:
            def add(files):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = compression
                files.append((info, b"x" * 100000 if compression else b"untrusted"))
            with self.subTest(name=name), self.assertRaises(LabError):
                self.review_bytes(raw_rewrite(self.original, add))
        self.assertFalse((self.root.parent / "escape").exists())

    def test_selected_symlink_hardlink_and_symlink_ancestor(self):
        original = self.root / "original.motivepack"
        original.write_bytes(self.original)
        symlink = self.root / "symlink.motivepack"
        symlink.symlink_to(original)
        self.rejects("FILE_BOUNDARY", lambda: review_package(symlink, POLICY))
        hardlink = self.root / "hardlink.motivepack"
        os.link(original, hardlink)
        self.rejects("FILE_BOUNDARY", lambda: review_package(hardlink, POLICY))
        hardlink.unlink()
        actual = self.root / "actual"
        actual.mkdir()
        (actual / "file.motivepack").write_bytes(self.original)
        link = self.root / "ancestor"
        link.symlink_to(actual, target_is_directory=True)
        self.rejects("FILE_BOUNDARY", lambda: review_package(link / "file.motivepack", POLICY))

    def test_web_content_never_enters_declarative_path(self):
        self.rejects("PACKAGE_EXTENSION", lambda: review_package(PACKAGES / "goal-web.motiveweb", POLICY))
        self.rejects("PACKAGE_KIND", lambda: self.review_bytes((PACKAGES / "goal-web.motiveweb").read_bytes()))

    def test_staging_reverifies_archive_bytes_and_removes_only_its_operation(self):
        staging = self.root / "staging"
        staging.mkdir(mode=0o700)
        unrelated = staging / "another-operation"
        unrelated.write_text("retain me")
        with stage_package(self.review, staging) as stage:
            path = stage.path
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            self.assertEqual((path / "reviewed.motivepack").read_bytes(), self.original)
            self.assertEqual(stat.S_IMODE((path / "manifest.json").stat().st_mode), 0o400)
            self.assertEqual(stage.reverify()["package_sha256"], self.review.sha256)
            self.assertEqual(sum(p.stat().st_size for p in path.rglob("*") if p.is_file()),
                             self.review.report["staging_bytes"])
            record = json.loads((path / "staging-record.json").read_text())
            self.assertFalse(record["owner_authorized"])
            self.assertFalse(record["installed"])
        self.assertFalse(path.exists())
        self.assertEqual(unrelated.read_text(), "retain me")
        stage.cleanup()

    def test_staging_content_change_fails_reverification(self):
        stage = stage_package(self.review, self.root / "staging")
        leaf = stage.path / "manifest.json"
        leaf.chmod(0o600)
        original = leaf.read_bytes()
        leaf.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        self.rejects("STAGING_HASH", stage.reverify)
        stage.cleanup()  # Same owned inode: cleanup may discard our damaged staging.

    def test_staging_foreign_inode_or_extra_file_is_never_deleted(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                stage = stage_package(self.review, self.root / "staging")
                foreign = stage.path / ("manifest.json" if replacement else "foreign.txt")
                if replacement:
                    foreign.unlink()
                foreign.write_text("foreign content")
                self.rejects("STAGING_RECONCILIATION", stage.cleanup)
                self.assertEqual(foreign.read_text(), "foreign content")
                self.assertTrue((stage.path / "rules.json").exists())

    def test_staging_symlink_replacement_preserves_external_target(self):
        stage = stage_package(self.review, self.root / "staging")
        external = self.root / "external"
        external.write_text("must survive")
        leaf = stage.path / "manifest.json"
        leaf.unlink()
        leaf.symlink_to(external)
        self.rejects("STAGING_RECONCILIATION", stage.cleanup)
        self.assertEqual(external.read_text(), "must survive")
        self.assertTrue(leaf.is_symlink())

    def test_staging_operation_rename_does_not_remove_replacement(self):
        stage = stage_package(self.review, self.root / "staging")
        stage.path.rename(stage.path.with_name(stage.operation_id + "-moved"))
        stage.path.mkdir()
        foreign = stage.path / "foreign"
        foreign.write_text("must survive")
        self.rejects("STAGING_RECONCILIATION", stage.cleanup)
        self.assertTrue(foreign.exists())

    def test_staging_root_requires_private_mode_and_no_links(self):
        root = self.root / "public"
        root.mkdir(mode=0o755)
        self.rejects("STAGING_ROOT", lambda: stage_package(self.review, root))
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        self.rejects("STAGING_ROOT", lambda: stage_package(self.review, link))


if __name__ == "__main__":
    unittest.main()
