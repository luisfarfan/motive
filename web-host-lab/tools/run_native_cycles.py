#!/usr/bin/env python3
"""Explicit serial lifecycle runs of the verified, owned CEF smoke process.

Each cycle launches a NEW host process and browser through run_owned_fixture.py.
This is not create/destroy testing inside one host, a leak proof, or Production
acceptance. Nothing launches on import; this tool is not part of verify_h18.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

LAB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("motive_cycles_owned_launcher", LAB / "tools/run_owned_fixture.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)

REQUIRED_GATES = ("frame_delivery", "alpha_pixels", "orderly_shutdown", "observed_tree_cleanup")
REQUESTED = {"width": 640, "height": 360, "fps": 30, "duration_ms": 1000,
             "deadline_seconds": 6, "rss_limit_mib": 2048}
# Admission reserve covers a 30s static signature timeout, 6s process deadline,
# bounded supervisor cleanup, and analysis. Never kill the supervisor to save time.
FINISH_RESERVE_SECONDS = 45


def assess_report(report, expected_sha256, generation, returncode):
    """Counter observation is retained, but does not decide lifecycle success."""
    computed = launcher.classify(report.get("supervision", {}), report.get("samples", {}))
    gates = {key: computed["gates"][key] for key in REQUIRED_GATES}
    identity_ok = (report.get("scope") == "owned_cef_smoke_fixture"
                   and report.get("native_host_executed") is True
                   and report.get("native_host_execution_attempted") is True
                   and report.get("expected_executable_sha256") == expected_sha256
                   and report.get("native_generation") == generation
                   and report.get("requested") == REQUESTED
                   and report.get("static_inventory", {}).get("status") == "PASS"
                   and report.get("credential_backend") == "chromium-use-mock-keychain"
                   and not report.get("error") and not report.get("supervisor_error_type"))
    consistent = (report.get("status") == computed["status"]
                  and report.get("gates") == computed["gates"]
                  and returncode == (0 if computed["status"] == "PASS" else 1))
    passed = identity_ok and consistent and all(value == "PASS" for value in gates.values())
    supervision = report.get("supervision", {})
    return {"status": "PASS" if passed else "FAIL", "gates": gates,
            "identity_verified": identity_ok, "launcher_result_consistent": consistent,
            "launcher_status": report.get("status"), "launcher_returncode": returncode,
            "native_host_executed": report.get("native_host_executed"),
            "generation": generation, "visible_counter_changed": computed["gates"]["visible_counter_changed"],
            "counter_delta_modulo_256": computed["counter_delta_modulo_256"],
            "counter_observations": {name: report.get("samples", {}).get(name, {}).get("counter", {})
                                     for name in ("first", "latest")},
            "supervision_reason": supervision.get("reason"), "returncode": supervision.get("returncode"),
            "elapsed_ms": supervision.get("elapsed_ms"), "peak_tree_rss_kib": supervision.get("peak_tree_rss_kib"),
            "resource_measurements": supervision.get("resource_measurements"),
            "raw_evidence_root": report.get("raw_evidence_root")}


def run_sequence(count, budget_seconds, run_one, snapshot, clock=time.monotonic):
    """Sequential, fail-closed orchestration; injected callbacks permit no-browser tests."""
    start = clock()
    result = {"status": "RUNNING", "requested_cycles": count, "completed_cycles": 0,
              "passed_cycles": 0, "native_process_runs_observed": 0,
              "native_process_runs_unknown": 0, "cycles": [], "stop_reason": None}

    def publish():
        result["elapsed_seconds"] = round(clock() - start, 3)
        result["counter_observation_counts"] = dict(Counter(row.get("visible_counter_changed", "NOT_EVALUATED")
                                                            for row in result["cycles"]))
        snapshot(result)

    publish()
    for index in range(1, count + 1):
        if clock() - start + FINISH_RESERVE_SECONDS > budget_seconds:
            result.update(status="PARTIAL", stop_reason="TIME_BUDGET_NO_NEW_LAUNCH")
            break
        result["active_cycle"] = index
        publish()  # If interrupted, evidence records an unfinished attempt, never PASS.
        try:
            row = run_one(index)
        except Exception as error:
            row = {"status": "FAIL", "native_host_executed": None,
                   "error_type": type(error).__name__, "error_code": str(error)[:512]}
        row["cycle"] = index
        result["cycles"].append(row)
        result["completed_cycles"] += 1
        result["native_process_runs_observed"] += row.get("native_host_executed") is True
        result["native_process_runs_unknown"] += row.get("native_host_executed") is None
        result.pop("active_cycle", None)
        if row.get("status") != "PASS":
            result.update(status="FAIL", stop_reason="CYCLE_FAILED")
            publish()
            break
        result["passed_cycles"] += 1
        publish()
    if result["passed_cycles"] == count:
        result.update(status="PASS", stop_reason="ALL_REQUESTED_LIFECYCLES_PASSED")
    publish()
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--build-root", type=Path, required=True)
    result.add_argument("--expected-sha256", required=True)
    result.add_argument("--output-dir", type=Path, help="New directory; existing evidence is never overwritten")
    result.add_argument("--cycles", type=int, default=100)
    result.add_argument("--budget-seconds", type=float, default=600)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        launcher.require(1 <= args.cycles <= 100, "CYCLE_COUNT_1_TO_100")
        launcher.require(math.isfinite(args.budget_seconds) and FINISH_RESERVE_SECONDS <= args.budget_seconds <= 600,
                         "BUDGET_45_TO_600_SECONDS")
        build_root, build_path, build = launcher.match_build_report(args.build_root, args.expected_sha256)
        launcher.require(build.get("credential_backend") == "chromium-use-mock-keychain", "FIXTURE_MOCK_KEYCHAIN_REQUIRED")
        paths = [Path(__file__).resolve(), LAB / "tools/run_owned_fixture.py", LAB / "poc/browser-host/supervisor.py", build_path]

        def fingerprints():
            return {str(path.relative_to(LAB)): launcher.sha(launcher.regular_bytes(path, 2 * 1024**2)) for path in paths}

        pinned_sources = fingerprints()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        output = Path(os.path.abspath(args.output_dir or (LAB / "evidence" / ("H18-native-cycles-" + run_id))))
        launcher.canonical_directory(output.parent)
        output.mkdir(mode=0o700)
        base = {"schema_version": 1, "scope": "new_owned_process_and_browser_per_cycle",
                "expected_executable_sha256": args.expected_sha256, "build_root": str(build_root),
                "source_sha256": pinned_sources, "requested_per_cycle": REQUESTED,
                "budget_seconds": args.budget_seconds, "finish_reserve_seconds": FINISH_RESERVE_SECONDS,
                "budget_semantics": "Total launch admission budget. Current supervisor cleanup always finishes; no forced outer timeout.",
                "in_process_browser_recreation_tested": False, "in_process_leaks_verified": False,
                "sandbox_verified": False, "production_connected": False,
                "limits": ["PASS applies only to the four lifecycle gates of the requested new-process cycles.",
                           "Visible counter remains an independent observation, including NOT_EVALUATED.",
                           "New-process cycles cannot establish absence of leaks in a long-lived host.",
                           "Cleanup covers the supervisor-observed tree, not arbitrary hostile process escape."]}
        sequence_number, last_printed, last_generation = 0, -1, 0

        def snapshot(result):
            nonlocal sequence_number, last_printed
            launcher.save_json(output / f"progress-{sequence_number:04d}.json", base | result)
            sequence_number += 1
            completed = result["completed_cycles"]
            terminal = result["status"] != "RUNNING"
            if terminal or (completed % 10 == 0 and completed != last_printed):
                print(json.dumps({key: result[key] for key in ("status", "completed_cycles", "passed_cycles", "elapsed_seconds", "stop_reason")}), flush=True)
                last_printed = completed

        def run_one(index):
            nonlocal last_generation
            launcher.require(fingerprints() == pinned_sources, "RUNNER_OR_BUILD_REPORT_CHANGED")
            generation = max(time.monotonic_ns(), last_generation + 1)
            launcher.require(generation <= 2**64 - 1, "GENERATION_OVERFLOW")
            last_generation = generation
            directory = output / f"cycle-{index:03d}"
            options = ["--build-root", str(build_root), "--expected-sha256", args.expected_sha256,
                       "--output-dir", str(directory), "--generation", str(generation)]
            for key, value in REQUESTED.items():
                options.extend(["--" + key.replace("_", "-"), str(value)])
            # Invoke the existing verifier/supervisor without a shell or alternate executable.
            # The launcher re-hashes main/helper/framework bytes and verifies the signature each time.
            with (output / f"cycle-{index:03d}-stdout.log").open("x") as stdout, (output / f"cycle-{index:03d}-stderr.log").open("x") as stderr:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = launcher.main(options)
            report_path = directory / "report.json"
            data = launcher.regular_bytes(report_path, 2 * 1024**2)
            result = assess_report(launcher.parse_json(data), args.expected_sha256, generation, code)
            result.update(report=str(report_path.relative_to(output)), report_sha256=launcher.sha(data))
            if fingerprints() != pinned_sources:
                result.update(status="FAIL", source_changed_during_cycle=True)
            return result

        result = run_sequence(args.cycles, args.budget_seconds, run_one, snapshot)
        launcher.save_json(output / "summary.json", base | result)
        print(json.dumps({"status": result["status"], "summary": str(output / "summary.json")}), flush=True)
        return 0 if result["status"] == "PASS" else 1
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__, "error_code": str(error)[:512]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
