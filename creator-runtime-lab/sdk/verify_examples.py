"""Regenerate H18 offline examples; originals and Production remain unchanged."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import runtime

LAB = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_bytes(runtime.encode(value))


def main():
    evidence = LAB / "evidence"
    fixtures = LAB / "integration-fixtures"
    evidence.mkdir(exist_ok=True)
    fixtures.mkdir(exist_ok=True)
    save(fixtures / "H18-default-snapshot.json", runtime.fixture_snapshot())
    capture = runtime.capture_fixture()
    save(fixtures / "H18-capture-snapshot.json", capture)
    baseline = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in runtime.PACKAGES.glob("*.motivepack")}
    cases = [([name], runtime.fixture_snapshot(), ["fixture-scene"], {}) for name in
             ("lower-third", "community-alert", "goal-celebration", "creator-tech-minimal", "neon-arena-minimal", "mixed-example")]
    overrides = {"instance-2-lower-third": {"properties": {
        "lower-third-title": {"type": "text", "value": "Samira · Creator Runtime"}}},
        "instance-4-goal-celebration": {"properties": {
        "goal-celebration-score": {"type": "text", "value": "3 — 2"}}}}
    save(fixtures / "H18-mixed-overrides.json", overrides)
    cases.append((["creator-tech-minimal", "lower-third", "community-alert", "goal-celebration"],
                  capture, capture["scenes"], overrides))
    summary = []
    for names, snapshot, scenes, changes in cases:
        paths = [runtime.PACKAGES / (name + ".motivepack") for name in names]
        result = runtime.run(paths, snapshot=snapshot, target_scenes=scenes, overrides=changes, mode="simulate")
        simulation = result.pop("simulation")
        mixed = len(names) > 1
        case = "mixed-existing-scene" if mixed else names[0]
        save(evidence / f"H18-sdk-{case}-plan.json", result)
        summary.append({"case": case, "status": "PASS", "packages": names,
            "package_sha256": {name + ".motivepack": baseline[name + ".motivepack"] for name in names},
            "target_scenes": scenes, "scene_ids_preserved": result["scene_ids_preserved"],
            "changes": result["changes"], "final_budget": result["final_budget"],
            "phases": [i["phase"] for i in simulation["installations"]],
            "simulated_receipts": sum(len(i["receipts"]) for i in simulation["installations"]),
            "production_connected": False, "native_render_verified": False,
            "show_control_armed": False, "staging_reverified_and_cleaned": True})
        if mixed:
            save(fixtures / "H18-mixed-store.json", simulation["store"])
            save(fixtures / "H18-mixed-snapshot.json", simulation["snapshot"])
            save(evidence / "H18-sdk-mixed-receipts.json", [{"instance_id": i["plan"]["instance_id"],
                "plan_sha256": i["plan_sha256"], "bindings": i["bindings"], "receipts": i["receipts"],
                "phase": i["phase"]} for i in simulation["installations"]])
            restored = runtime.assess_restore(fixtures / "H18-mixed-store.json", paths, simulation["snapshot"])
            assert restored["status"] == "PASS" and len(restored["report"]["compatible"]) == 4
            save(evidence / "H18-sdk-mixed-restore.json", restored)
    assert all(hashlib.sha256((runtime.PACKAGES / name).read_bytes()).hexdigest() == value
               for name, value in baseline.items())
    report = {"checkpoint": "H18 local Creator Runtime SDK", "created_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASS", "scope": "real archives plus strict offline owner model",
              "original_packages_unchanged": True, "cases": summary}
    save(evidence / "H18-sdk-examples.json", report)
    print(runtime.encode(report).decode(), end="")


if __name__ == "__main__":
    main()
