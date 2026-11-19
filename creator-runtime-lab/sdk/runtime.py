#!/usr/bin/env python3
"""Local H18 library/review/planning CLI; every owner operation is a strict model."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile

LAB = Path(__file__).resolve().parents[1]
ROOT = LAB.parent
PACKAGES = ROOT / "element-lab/marketplace-contract/packages"
sys.path.insert(0, str(LAB / "importer"))
from runtime_importer import ReviewPolicy, review_package, stage_package, _open_directory, _read_at
from common import LabError, encode, loads, require
from compiler import symbol
from packaging import verify_bytes, MAX_TOTAL
from schemas import CAPABILITIES

_built = False


def read_json(path: Path):
    path = Path(path)
    directory = _open_directory(path.parent)
    try:
        return loads(_read_at(directory, path.name, 1_048_576))
    finally:
        os.close(directory)


def fixture_snapshot(scenes=None):
    """Declared offline fixture; it never queries or impersonates a running owner."""
    return {"session": "offline-owner-session", "revision": 1, "busy": False,
            "capabilities": list(CAPABILITIES), "scenes": scenes or ["fixture-scene"],
            "sources": {}, "layers": {}, "assets": {}}


def capture_fixture():
    """Reserve two existing modeled capture sources; no camera/gameplay is opened."""
    snapshot = fixture_snapshot(["fixture-creator-tech-scene"])
    for index, kind in enumerate(("gameplay", "camera")):
        source, layer = "fixture-" + kind + "-source", "fixture-" + kind + "-layer"
        snapshot["sources"][source] = {"id": source, "definition": None, "texture_bytes": 960 * 540 * 8,
                                        "video": False, "installation": None}
        snapshot["layers"][layer] = {"id": layer, "source": source, "scene": snapshot["scenes"][0],
            "horizontal": {"x": 0, "y": 0, "width": 960, "height": 540, "visible": True, "order": index},
            "vertical": {"x": 0, "y": 0, "width": 540, "height": 960, "visible": True, "order": index},
            "installation": None}
    return snapshot


def _policy(snapshot):
    require(isinstance(snapshot, dict) and isinstance(snapshot.get("capabilities"), list) and
            all(isinstance(c, str) for c in snapshot["capabilities"]), "SNAPSHOT", "Explicit capability list required")
    return ReviewPolicy(available_capabilities=frozenset(snapshot["capabilities"]))


def library(directory=PACKAGES, snapshot=None):
    """Inventory full verified local candidates; keep invalid entries visible as errors."""
    directory = Path(directory)
    policy = _policy(snapshot if snapshot is not None else fixture_snapshot())
    entries = []
    fd = _open_directory(directory)
    try:
        names = sorted(name for name in os.listdir(fd) if name.endswith((".motivepack", ".motiveweb")))
        require(len(names) <= 256, "LIBRARY_LIMIT", "Local library exceeds 256 candidates")
        for name in names:
            try:
                if name.endswith(".motivepack"):
                    reviewed = review_package(directory / name, policy)
                    item = describe(reviewed)
                    item.update(file=name, status="PASS", proposed_installation_available=True)
                else:
                    data = _read_at(fd, name, MAX_TOTAL)
                    checked = verify_bytes(data)
                    item = {"file": name, "id": checked["id"], "sha256": checked["sha256"], "status": "BLOCKED",
                            "content_kind": checked["content_kind"], "integrity_verified": True,
                            "proposed_installation_available": False,
                            "reason": "Web execution requires native fixture authorization and demonstrated isolation"}
                entries.append(item)
            except (LabError, OSError) as exc:
                entries.append({"file": name, "status": "FAIL", "proposed_installation_available": False,
                                "error": {"code": getattr(exc, "code", "LOCAL_IO"), "message": str(exc)}})
    finally:
        os.close(fd)
    return {"status": "PARTIAL" if any(x["status"] == "FAIL" for x in entries) else "PASS",
            "scope": "local_offline_library", "capabilities_observed_live": False,
            "production_connected": False, "entries": entries}


def describe(reviewed):
    pack = reviewed.manifest
    return {"id": reviewed.package_id, "version": reviewed.version, "sha256": reviewed.sha256,
            "content_kind": "declarative_pack", "name": pack["name"], "properties": pack["properties"],
            "layouts": [{"authored_scene": scene["id"], "layers": scene["layers"]} for scene in pack["scenes"]],
            "preview_paths": reviewed.metadata["preview_paths"], "previews_are_approximate": True,
            "review": reviewed.report, "state": "reviewed_candidate", "installed_in_production": False}


def _run_model(request, expected_scope="strict_offline_owner_model"):
    global _built
    if not _built:
        built = subprocess.run(["cargo", "build", "--offline", "--locked", "--quiet", "--manifest-path", str(LAB / "Cargo.toml")],
            env={**os.environ, "CARGO_TARGET_DIR": str(LAB / "target")}, capture_output=True, text=True, timeout=180)
        require(built.returncode == 0, "MODEL_BUILD", built.stderr[-4000:])
        _built = True
    payload = encode(request)
    require(len(payload) <= 4_194_304, "REQUEST_SIZE", "Offline request exceeds 4 MiB")
    result = subprocess.run([str(LAB / "target/debug/motive-creator-runtime-lab")], input=payload,
                            capture_output=True, timeout=30)
    report = loads(result.stdout)
    if result.returncode and report.get("status") != "PARTIAL":
        raise LabError(report["error"]["code"], report["error"]["message"])
    require(report.get("production_connected") is False and report.get("scope") == expected_scope,
            "MODEL_SCOPE", "Unexpected owner model response")
    return report


class _StagingWorkspace:
    """Own one container, removing only its empty, identity-checked directories.

    Never wrap security-sensitive staging in TemporaryDirectory: its recursive
    cleanup would erase foreign objects deliberately preserved by StagedPackage.
    """

    def __enter__(self):
        scratch = LAB / ".scratch"
        scratch.mkdir(exist_ok=True)
        self._parent_fd = _open_directory(scratch)
        self._fd = self._stage_fd = None
        self.path = None
        try:
            self.path = Path(tempfile.mkdtemp(prefix="sdk-", dir=scratch))
            self._fd = _open_directory(self.path)
            os.mkdir("private-staging", mode=0o700, dir_fd=self._fd)
            self._stage_fd = os.open("private-staging", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._fd)
            info = os.fstat(self._fd)
            self._identity = info.st_dev, info.st_ino
            info = os.fstat(self._stage_fd)
            self._stage_identity = info.st_dev, info.st_ino
            return self.path
        except BaseException as exc:
            self._close()
            if self.path is not None:
                error = LabError("STAGING_RECONCILIATION", "Workspace construction was interrupted; preserve it for explicit recovery")
                error.recovery_path = str(self.path)
                error.original_error_code = getattr(exc, "code", None)
                raise error from exc
            raise

    def _close(self):
        for fd in (self._stage_fd, self._fd, self._parent_fd):
            if fd is not None:
                os.close(fd)
        self._stage_fd = self._fd = self._parent_fd = None

    def __exit__(self, exc_type, exc_value, traceback):
        retained = False
        try:
            outer = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
            inner = os.stat("private-staging", dir_fd=self._fd, follow_symlinks=False)
            owned = (stat.S_ISDIR(outer.st_mode) and (outer.st_dev, outer.st_ino) == self._identity and
                     stat.S_ISDIR(inner.st_mode) and (inner.st_dev, inner.st_ino) == self._stage_identity)
            if owned and os.listdir(self._fd) == ["private-staging"] and not os.listdir(self._stage_fd):
                os.rmdir("private-staging", dir_fd=self._fd)
                os.rmdir(self.path.name, dir_fd=self._parent_fd)
            else:
                retained = True
        except OSError:
            retained = True
        finally:
            self._close()
        if retained:
            error = LabError("STAGING_RECONCILIATION", "Staging was preserved for explicit recovery; no recursive cleanup was attempted")
            error.recovery_path = str(self.path)
            error.original_error_code = getattr(exc_value, "code", None)
            raise error from exc_value
        return False


def run(packages, *, snapshot=None, target_scenes=None, overrides=None, instance_ids=None, mode="plan"):
    """Review/stage exact bytes, then propose insertions into existing model scenes.

    Both modes exercise the sequential owner model. Plan presents its proposed
    operations; simulate additionally exposes explicitly simulated receipts/store.
    No receipt here is accepted as a native identity or as an installation approval.
    """
    require(mode in ("plan", "simulate"), "MODE", "Use plan or simulate")
    require(1 <= len(packages) <= 16, "REQUEST_LIMIT", "Choose 1–16 local packages")
    snapshot = deepcopy(snapshot if snapshot is not None else fixture_snapshot())
    policy = _policy(snapshot)
    scenes = list(target_scenes if target_scenes is not None else ["fixture-scene"])
    require(isinstance(overrides or {}, dict), "OVERRIDES", "Overrides must map instance IDs to properties/layouts")
    overrides = deepcopy(overrides or {})
    require(instance_ids is None or len(instance_ids) == len(packages), "INSTANCE_SELECTION", "One instance ID per package required")
    reviews, insertions, stages = [], [], []
    with _StagingWorkspace() as temporary, ExitStack() as stack:
        for index, path in enumerate(packages):
            reviewed = review_package(Path(path), policy)
            instance = instance_ids[index] if instance_ids is not None else symbol(f"instance-{index + 1}", reviewed.package_id)
            selected = overrides.pop(instance, {})
            require(isinstance(selected, dict) and selected.keys() <= {"properties", "layouts"},
                    "OVERRIDES", "Only existing property and layout overrides are admitted")
            stage = stack.enter_context(stage_package(reviewed, Path(temporary) / "private-staging"))
            stages.append(stage)
            stage.reverify()
            insertions.append({"instance_id": instance,
                "definition": {"package_id": reviewed.package_id, "version": reviewed.version, "package_sha256": reviewed.sha256},
                "pack": reviewed.manifest, "rules": reviewed.rules,
                "properties": selected.get("properties", {}), "layouts": selected.get("layouts", {}),
                "target_scenes": scenes})
            reviews.append({"instance_id": instance, **describe(reviewed)})
        require(not overrides, "INSTANCE_UNKNOWN", "Overrides reference an instance outside this proposal")
        result = _run_model({"snapshot": snapshot, "insertions": insertions})
        for stage in stages:
            stage.reverify()
    plans = [installation["plan"] for installation in result["installations"]]
    report = {"status": result["status"], "mode": mode, "scope": "sequential_strict_offline_owner_model",
              "production_connected": False, "native_render_verified": False, "capabilities_observed_live": False,
              "installed_in_production": False, "owner_authorized": False, "show_control_armed": False,
              "simulated_ids_only": True, "staging_reverified_and_cleaned": True,
              "scene_ids_preserved": set(result["snapshot"]["scenes"]) == set(snapshot["scenes"]),
              "target_scenes": scenes, "reviews": reviews, "plans": plans,
              "final_budget": result["snapshot_budget"],
              "changes": {"new_scenes": 0, "new_instances": len(plans),
                          "new_sources": len(result["snapshot"]["sources"]) - len(snapshot["sources"]),
                          "new_layers": len(result["snapshot"]["layers"]) - len(snapshot["layers"]),
                          "new_assets": len(result["snapshot"]["assets"]) - len(snapshot["assets"])},
              "limits": {"scenes": 8, "sources": 16, "layers": 32, "video_sources": 4, "texture_bytes": 256 * 1024**2},
              "notes": ["Properties change one instance; shared placements of that instance share its source state.",
                        "Plans append above existing layers and retain both layout orientations; no visual overlap acceptance is claimed.",
                        "Sequential proposals use predicted model revisions; the real owner must review current state before each operation.",
                        "Preview SVG is approximate; neither JS nor modeled receipts demonstrate native frames."]}
    if mode == "simulate" or result["status"] == "PARTIAL":
        report["simulation"] = result
    return report


def assess_restore(store_path, packages, snapshot):
    """Recheck actual archives and ask Rust to assess an inert experimental sidecar."""
    store = read_json(Path(store_path))
    verified = {}
    # Static contract availability only: Rust independently checks the destination
    # snapshot so unavailable runtime capabilities are reported as restore issues.
    policy = _policy(fixture_snapshot())
    with _StagingWorkspace() as temporary, ExitStack() as stack:
        stages = []
        for path in packages:
            reviewed = review_package(Path(path), policy)
            stage = stack.enter_context(stage_package(reviewed, Path(temporary) / "private-staging"))
            stages.append(stage)
            verified[reviewed.sha256] = reviewed.manifest
        result = _run_model({"operation": "assess_restore", "snapshot": snapshot, "store": store,
                             "verified_packages": verified}, "offline_restore_assessment")
        for stage in stages:
            stage.reverify()
    return {**result, "mode": "restore-assessment", "actual_package_hashes_reverified": sorted(verified),
            "archive_review_capabilities": "offline_contract_set", "capabilities_observed_live": False,
            "staging_reverified_and_cleaned": True, "installed_in_production": False}


def _write_new(path, data):
    path = Path(path)
    directory = _open_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="Verified local library and compatibility")
    catalog.add_argument("--directory", type=Path, default=PACKAGES)
    review = sub.add_parser("review", help="Review bytes, properties, layouts and budget")
    review.add_argument("package", type=Path)
    for mode in ("plan", "simulate"):
        command = sub.add_parser(mode, help="Offline proposals" if mode == "plan" else "Strict modeled receipts and persistence")
        command.add_argument("packages", nargs="+", type=Path)
        command.add_argument("--scene", action="append", dest="scenes")
        command.add_argument("--instance", action="append", dest="instances")
        if mode == "simulate":
            command.add_argument("--store-output", type=Path, help="Save a new experimental model sidecar, mode 0600")
        command.add_argument("--overrides", type=Path, help="Local instance map of typed properties and H/V layouts")
        command.add_argument("--set", action="append", default=[], metavar="PROPERTY=JSON", help="Single package property value; type comes from its existing declaration")
    restore = sub.add_parser("restore", help="Assess an experimental sidecar without applying or executing anything")
    restore.add_argument("store", type=Path)
    restore.add_argument("packages", nargs="*", type=Path, help="Actual archives to reverify; missing packages become restore issues")
    for command in (catalog, review, restore, *[sub.choices[m] for m in ("plan", "simulate")]):
        command.add_argument("--snapshot", type=Path, help="Local owner snapshot fixture; never a live observation")
        command.add_argument("--output", type=Path, help="New JSON file; existing outputs are refused")
    args = parser.parse_args(argv)
    try:
        snapshot = read_json(args.snapshot) if args.snapshot else fixture_snapshot()
        if args.command == "catalog":
            report = library(args.directory, snapshot)
        elif args.command == "review":
            report = {"status": "PASS", "scope": "offline_candidate_review", "production_connected": False,
                      **describe(review_package(args.package, _policy(snapshot)))}
        elif args.command == "restore":
            report = assess_restore(args.store, args.packages, snapshot)
        else:
            overrides = read_json(args.overrides) if args.overrides else {}
            require(isinstance(overrides, dict), "OVERRIDES", "Overrides must map instance IDs to properties/layouts")
            if args.set:
                require(len(args.packages) == 1, "PROPERTY_SELECTION", "--set is for one package; use --overrides for compositions")
                reviewed = review_package(args.packages[0], _policy(snapshot))
                instance = args.instances[0] if args.instances else symbol("instance-1", reviewed.package_id)
                declared = {p["id"]: p for p in reviewed.manifest["properties"]}
                selection = overrides.setdefault(instance, {})
                require(isinstance(selection, dict), "OVERRIDES", "Instance override must be an object")
                selected = selection.setdefault("properties", {})
                require(isinstance(selected, dict), "OVERRIDES", "Properties must be a typed map")
                for item in args.set:
                    key, separator, raw = item.partition("=")
                    require(separator and key in declared and key not in selected, "PROPERTY_SELECTION", "Known, unique property IDs required")
                    selected[key] = {"type": declared[key]["value"]["type"], "value": loads(raw)}
            report = run(args.packages, snapshot=snapshot, target_scenes=args.scenes, overrides=overrides,
                         instance_ids=args.instances, mode=args.command)
        data = encode(report)
        if getattr(args, "store_output", None):
            _write_new(args.store_output, encode(report["simulation"]["store"]))
        if args.output:
            _write_new(args.output, data)
        print(data.decode(), end="")
        return 0 if report["status"] == "PASS" else 1
    except (LabError, OSError, subprocess.SubprocessError) as exc:
        error = {"code": getattr(exc, "code", "LOCAL_RUNTIME"), "message": str(exc)}
        if getattr(exc, "recovery_path", None):
            error.update(staging_recovery_path=exc.recovery_path, original_error_code=exc.original_error_code)
        print(encode({"status": "FAIL", "error": error}).decode(), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
