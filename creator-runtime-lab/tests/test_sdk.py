from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import stat
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "sdk"))
import runtime
from common import LabError


class SdkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = Path(self.tmp.name)
        self.lower = runtime.PACKAGES / "lower-third.motivepack"

    def tearDown(self):
        self.tmp.cleanup()

    def rejects(self, code, function):
        with self.assertRaises(LabError) as result:
            function()
        self.assertEqual(result.exception.code, code)

    def cli(self, args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = runtime.main(args)
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_catalog_reports_seven_native_candidates_and_blocked_web(self):
        catalog = runtime.library()
        self.assertFalse(catalog["capabilities_observed_live"])
        self.assertEqual(len(catalog["entries"]), 8)
        self.assertEqual(sum(e["status"] == "PASS" for e in catalog["entries"]), 7)
        web = next(e for e in catalog["entries"] if e["content_kind"] == "web_element")
        self.assertEqual(web["status"], "BLOCKED")
        self.assertFalse(web["proposed_installation_available"])

    def test_catalog_keeps_invalid_candidate_visible(self):
        (self.root / "bad.motivepack").write_bytes(b"bad zip")
        report = runtime.library(self.root)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["entries"][0]["error"]["code"], "PACKAGE_ZIP")

    def test_plan_is_explicitly_offline_and_preserves_existing_scene(self):
        report = runtime.run([self.lower])
        self.assertTrue(report["scene_ids_preserved"])
        self.assertEqual(report["changes"], {"new_scenes": 0, "new_instances": 1, "new_sources": 2, "new_layers": 2, "new_assets": 1})
        self.assertFalse(report["owner_authorized"])
        self.assertFalse(report["installed_in_production"])
        self.assertNotIn("simulation", report)
        self.assertTrue(report["staging_reverified_and_cleaned"])
        self.assertTrue(all(s["operation"] != "create_scene" for s in report["plans"][0]["steps"]))
        self.assertEqual(set(report["plans"][0]["initial_bindings"]["scenes"].values()), {"fixture-scene"})

    def test_mixed_creator_tech_lower_community_goal_with_capture_reservations(self):
        paths = [runtime.PACKAGES / (name + ".motivepack") for name in
                 ("creator-tech-minimal", "lower-third", "community-alert", "goal-celebration")]
        fixture = runtime.capture_fixture()
        report = runtime.run(paths, snapshot=fixture, target_scenes=fixture["scenes"], mode="simulate")
        self.assertEqual(report["final_budget"]["scenes"], 1)
        self.assertEqual(report["final_budget"]["sources"], 14)
        self.assertEqual(report["final_budget"]["layers"], 14)
        self.assertEqual(report["changes"]["new_scenes"], 0)
        after = report["simulation"]["snapshot"]
        for key, value in fixture["sources"].items():
            self.assertEqual(after["sources"][key], value)
        self.assertEqual({layer["scene"] for layer in after["layers"].values()}, set(fixture["scenes"]))
        self.assertTrue(all(not rule["enabled"] for i in report["simulation"]["store"]["instances"]
                            for rule in i["visual_bindings"]["rules"]))
        self.assertTrue(report["final_budget"]["texture_bytes"] < 256 * 1024**2)

    def test_shared_placements_reuse_sources_and_assets_with_distinct_layers(self):
        snapshot = runtime.fixture_snapshot(["scene-b", "scene-a"])
        report = runtime.run([self.lower], snapshot=snapshot, target_scenes=snapshot["scenes"], mode="simulate")
        self.assertTrue(report["scene_ids_preserved"])
        self.assertEqual(report["changes"]["new_sources"], 2)
        self.assertEqual(report["changes"]["new_assets"], 1)
        self.assertEqual(report["changes"]["new_layers"], 4)
        self.assertEqual(len(report["simulation"]["installations"][0]["bindings"]["sources"]), 2)

    def test_properties_and_independent_horizontal_vertical_layout_overrides(self):
        review = runtime.review_package(self.lower, runtime._policy(runtime.fixture_snapshot()))
        layer = review.manifest["scenes"][0]["layers"][0]
        pair = {side: deepcopy(layer[side]) for side in ("horizontal", "vertical")}
        pair["horizontal"]["x"] = 100
        pair["vertical"]["x"] = 20
        pair["vertical"]["visible"] = False
        overrides = {"custom-lower": {"properties": {"lower-third-title": {"type": "text", "value": "Samira"}},
                                      "layouts": {layer["id"]: pair}}}
        report = runtime.run([self.lower], instance_ids=["custom-lower"], overrides=overrides, mode="simulate")
        self.assertEqual(report["plans"][0]["properties"]["lower-third-title"]["value"], "Samira")
        bound = report["simulation"]["installations"][0]["bindings"]["layers"]
        selected = next(value for key, value in bound.items() if "content-layer" in key)
        result = report["simulation"]["snapshot"]["layers"][selected]
        self.assertEqual(result["horizontal"]["x"], 100)
        self.assertEqual(result["vertical"]["x"], 20)
        self.assertFalse(result["vertical"]["visible"])

    def test_unknown_property_instance_and_layout_are_errors(self):
        self.rejects("INSTANCE_UNKNOWN", lambda: runtime.run([self.lower], overrides={"foreign": {}}))
        self.rejects("PACK_REFERENCE", lambda: runtime.run([self.lower], instance_ids=["lower"], overrides={"lower": {
            "properties": {"missing": {"type": "text", "value": "no"}}}}))
        self.rejects("OVERRIDES", lambda: runtime.run([self.lower], instance_ids=["lower"], overrides={"lower": {"script": "no"}}))

    def test_owner_busy_missing_scene_capability_and_quota_fail_closed(self):
        busy = runtime.fixture_snapshot()
        busy["busy"] = True
        self.rejects("OWNER_BUSY", lambda: runtime.run([self.lower], snapshot=busy))
        self.rejects("SCENE_MISSING", lambda: runtime.run([self.lower], target_scenes=["missing-scene"]))
        incapable = runtime.fixture_snapshot()
        incapable["capabilities"] = []
        self.rejects("CAPABILITY_UNAVAILABLE", lambda: runtime.run([self.lower], snapshot=incapable))
        full = runtime.fixture_snapshot()
        for index in range(16):
            identifier = f"existing-source-{index}"
            full["sources"][identifier] = {"id": identifier, "definition": None, "texture_bytes": 1,
                                          "video": False, "installation": None}
        self.rejects("GLOBAL_BUDGET", lambda: runtime.run([self.lower], snapshot=full))

    def test_cli_typed_set_new_report_and_private_store(self):
        output, store = self.root / "report.json", self.root / "sidecar.json"
        code, report = self.cli(["simulate", str(self.lower), "--set", 'lower-third-title="Samira"',
                                 "--output", str(output), "--store-output", str(store)])
        self.assertEqual(code, 0)
        self.assertEqual(report["plans"][0]["properties"]["lower-third-title"]["value"], "Samira")
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)
        self.assertEqual(json.loads(store.read_bytes())["evidence_scope"], "offline-model-only")
        before = output.read_bytes()
        code, error = self.cli(["review", str(self.lower), "--output", str(output)])
        self.assertEqual(code, 1)
        self.assertEqual(error["error"]["code"], "LOCAL_RUNTIME")
        self.assertEqual(output.read_bytes(), before)

    def test_sidecar_restore_rechecks_archives_and_never_arms_or_executes(self):
        simulated = runtime.run([self.lower], mode="simulate")["simulation"]
        store = self.root / "sidecar.json"
        runtime._write_new(store, runtime.encode(simulated["store"]))
        report = runtime.assess_restore(store, [self.lower], simulated["snapshot"])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["report"]["compatible"], ["instance-1-lower-third"])
        self.assertFalse(report["report"]["show_control_armed"])
        self.assertEqual(report["report"]["scripts_started"], 0)
        self.assertEqual(report["report"]["historical_events_replayed"], 0)
        self.assertTrue(report["report"]["requires_local_review"])
        missing = runtime.assess_restore(store, [], simulated["snapshot"])
        self.assertEqual(missing["status"], "PARTIAL")
        self.assertEqual(missing["report"]["issues"][0]["code"], "PACKAGE_REVERIFY_REQUIRED")
        incapable = deepcopy(simulated["snapshot"])
        incapable["capabilities"] = []
        unavailable = runtime.assess_restore(store, [self.lower], incapable)
        self.assertTrue(any(i["code"] == "CAPABILITY_UNAVAILABLE" for i in unavailable["report"]["issues"]))

    def test_sidecar_unknown_fields_and_activation_claims_are_rejected(self):
        simulated = runtime.run([self.lower], mode="simulate")["simulation"]
        store = self.root / "sidecar.json"
        bad = deepcopy(simulated["store"])
        bad["credential"] = "not-a-real-secret"
        store.write_bytes(runtime.encode(bad))
        self.rejects("STORE_SCHEMA", lambda: runtime.assess_restore(store, [self.lower], simulated["snapshot"]))
        bad = deepcopy(simulated["store"])
        bad["instances"][0]["visual_bindings"]["rules"][0]["enabled"] = True
        store.write_bytes(runtime.encode(bad))
        self.rejects("STORE_AUTHORITY", lambda: runtime.assess_restore(store, [self.lower], simulated["snapshot"]))

    def test_foreign_staging_entries_survive_sdk_and_restore_cleanup(self):
        simulated = runtime.run([self.lower], mode="simulate")["simulation"]
        store = self.root / "sidecar.json"
        runtime._write_new(store, runtime.encode(simulated["store"]))
        original_stage = runtime.stage_package
        for operation in (lambda: runtime.run([self.lower]),
                          lambda: runtime.assess_restore(store, [self.lower], simulated["snapshot"])):
            created = []
            def interfere(reviewed, root):
                stage = original_stage(reviewed, root)
                foreign = stage.path / "foreign-retain.txt"
                foreign.write_text("controlled test-owned foreign entry")
                created.append((stage.path, foreign))
                return stage
            with self.subTest(operation=operation), patch.object(runtime, "stage_package", side_effect=interfere):
                try:
                    with self.assertRaises(LabError) as caught:
                        operation()
                    self.assertEqual(caught.exception.code, "STAGING_RECONCILIATION")
                    operation_path, foreign = created[0]
                    self.assertEqual(foreign.read_text(), "controlled test-owned foreign entry")
                    self.assertTrue((operation_path / "reviewed.motivepack").exists())
                    workspace = operation_path.parent.parent
                    self.assertEqual(caught.exception.recovery_path, str(workspace))
                    self.assertTrue(workspace.exists())
                finally:
                    # Explicit test-fixture disposal after verifying preservation.
                    # Every file here was created by this test, including the intrusion.
                    if created:
                        shutil.rmtree(created[0][0].parent.parent)

    def test_snapshot_io_rejects_duplicate_keys_and_symlinks(self):
        snapshot = self.root / "snapshot.json"
        snapshot.write_text('{"session":"one","session":"two"}')
        self.rejects("JSON_DUPLICATE", lambda: runtime.read_json(snapshot))
        link = self.root / "link.json"
        link.symlink_to(snapshot)
        self.rejects("FILE_BOUNDARY", lambda: runtime.read_json(link))

    def test_partial_installation_retains_receipts_actual_budget_and_private_store(self):
        snapshot = runtime.fixture_snapshot()
        collision = "sim-1-source-2"
        snapshot["sources"][collision] = {"id": collision, "definition": None,
            "texture_bytes": 0, "video": False, "installation": None}
        snapshot_path = self.root / "snapshot.json"
        snapshot_path.write_bytes(runtime.encode(snapshot))
        store_path = self.root / "partial-store.json"
        code, report = self.cli(["simulate", str(self.lower), "--snapshot", str(snapshot_path),
                                 "--store-output", str(store_path)])
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "PARTIAL")
        state = report["simulation"]["installations"][0]
        self.assertEqual(state["phase"], "partial")
        self.assertEqual(state["error"], "ID_CONFLICT")
        self.assertEqual(len(state["receipts"]), 1)
        self.assertEqual(report["final_budget"]["sources"], 1)
        self.assertEqual(report["final_budget"]["resource_count"], 1)
        self.assertEqual(json.loads(store_path.read_bytes())["instances"][0]["installation_phase"], "partial")
        self.assertEqual(report["simulation"]["snapshot"]["sources"][collision], snapshot["sources"][collision])

    def test_batch_review_rejection_keeps_earlier_installed_state(self):
        report = runtime.run([self.lower, self.lower], instance_ids=["same", "same"], mode="plan")
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["simulation"]["stopped_on_error"]["code"], "INSTANCE_CONFLICT")
        self.assertEqual(len(report["simulation"]["installations"]), 1)
        self.assertEqual(len(report["simulation"]["store"]["instances"]), 1)
        self.assertEqual(report["final_budget"]["sources"], 2)


if __name__ == "__main__":
    unittest.main()
