#!/usr/bin/env python3
"""Classify the fixed H19 native decoy experiment without certifying a sandbox.

Only reads retained evidence. This checker cannot authorize third-party content,
replace the existing AssetBroker gate, or establish untested process restrictions.
"""
import argparse
import errno
import gzip
import hashlib
import json
from pathlib import Path


def read_json(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def classify(native, supervision, expected_instances, generation, canary=None):
    # The runner preserves raw samples in .json.gz and embeds the same terminal
    # supervision metadata in report.json. Accept either recorded representation.
    supervision = supervision.get("supervision", supervision)
    if canary is not None:
        canary = canary.get("owned_loopback_canary", canary)
    rows = native.get("instances", [])
    errors = []
    if native.get("native_executed") is not True or native.get("scenario") != "security":
        errors.append("FIXED_NATIVE_SECURITY_SCENARIO_NOT_RECORDED")
    expected = {(instance, generation) for instance in range(1, expected_instances + 1)}
    observed = [(row.get("instance"), row.get("generation")) for row in rows]
    if len(observed) != len(expected) or set(observed) != expected:
        errors.append("EXPECTED_INSTANCE_IDENTITIES_MISSING_OR_DUPLICATE")
    probes = []
    process_rows = [process for sample in supervision.get("samples", [])
                    for process in sample.get("resource_usage", {}).get("processes", [])]
    surface_phases = {"fetch_rejected": (20, 21), "websocket_failed": (22, 23),
                      "popup_not_opened": (24, 25), "cookie_unavailable": (26, 27),
                      "worker_rejected": (28, 29)}
    for row in rows:
        browser_control = row.get("browser_decoy_opened") is True and row.get("browser_decoy_errno") == 0
        renderer_observed = row.get("renderer_decoy_observed") is True
        pid = row.get("renderer_pid_reported")
        renderer_identity = type(pid) is int and pid > 0 and type(row.get("browser_id")) is int and row["browser_id"] > 0
        denied = (renderer_observed and renderer_identity and row.get("renderer_decoy_opened") is False
                  and row.get("renderer_decoy_errno") in {errno.EPERM, errno.EACCES})
        if not browser_control:
            errors.append("BROWSER_DECOY_POSITIVE_CONTROL_FAILED")
        if not denied:
            errors.append("RENDERER_FILE_DENIAL_NOT_ESTABLISHED")
        if row.get("closed") is not True or row.get("failed") is not False:
            errors.append("INSTANCE_NORMAL_CLOSE_NOT_ESTABLISHED")
        matching_processes = [process for process in process_rows
                              if process.get("pid") == pid and process.get("role") == "renderer"]
        births = {tuple(process.get("birth", [])) for process in matching_processes}
        identity_corroborated = bool(matching_processes) and len(births) == 1 and len(next(iter(births))) == 2
        if process_rows and not identity_corroborated:
            errors.append("RENDERER_PID_NOT_CORROBORATED_BY_OWNED_TREE")
        phases = row.get("security_phases", [])
        surfaces = {name: "UNEXPECTED_ALLOW" if allowed in phases else "OBSERVED_REJECTION" if denied in phases else "NOT_OBSERVED"
                    for name, (denied, allowed) in surface_phases.items()}
        if "UNEXPECTED_ALLOW" in surfaces.values():
            errors.append("APPLICATION_SECURITY_PROBE_UNEXPECTED_ALLOW")
        probes.append({"instance": row.get("instance"), "generation": row.get("generation"),
                       "browser_id": row.get("browser_id"), "renderer_pid_reported": pid,
                       "browser_open_positive_control": "PASS" if browser_control else "FAIL",
                       "renderer_owned_file_open_denial": "PASS" if browser_control and denied else "NOT_ESTABLISHED",
                       "renderer_errno": row.get("renderer_decoy_errno"),
                       "renderer_identity_corroboration": "PASS" if identity_corroborated else "NOT_EVALUATED",
                       "application_surface_observations": surfaces,
                       "callback_counters": {key: row.get(key) for key in ["blocked_resources", "blocked_navigation", "blocked_popups", "blocked_downloads", "blocked_permissions"]},
                       "scope": "one native read-only open of the owned sandbox-decoy file; not arbitrary filesystem, HOME or Keychain confinement"})
    cleanup = (supervision.get("reason") == "exit" and supervision.get("returncode") == 0
               and supervision.get("final_cleanup_observed_tree") is True
               and supervision.get("final_remaining_observed_pids") == []
               and supervision.get("final_remaining_observed_live_pids") == [])
    if not cleanup:
        errors.append("OBSERVED_TREE_NORMAL_CLEANUP_NOT_ESTABLISHED")
    result = {"status": "PASS" if not errors else "FAIL", "scope": "fixed owned native decoy experiment only",
              "expected_instances": expected_instances, "expected_generation": generation,
              "errors": sorted(set(errors)), "probes": probes,
              "observed_tree_cleanup": "PASS" if cleanup else "FAIL",
              "browser_process_filesystem_confinement": "BLOCKED",
              "keychain_production_configuration": "BLOCKED",
              "complete_os_sandbox_matrix": "BLOCKED", "third_party_execution": "BLOCKED",
              "network_os_confinement": "NOT_EVALUATED"}
    if canary is not None:
        count = canary.get("accepted_connections")
        observed_no_connections = (canary.get("bound") is True and canary.get("closed") is True
                                   and type(count) is int and count == 0)
        result["owned_loopback_canary"] = {
            "observation": "NO_ACCEPTED_CONNECTIONS" if observed_no_connections else "NOT_ESTABLISHED",
            "accepted_connections": count,
            "scope": "listener observation only; does not distinguish CSP, callback, API rejection, DNS or OS egress policies"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--supervision", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=[1, 3, 5], required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--canary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = {"instances": args.instances, "supervision": args.supervision}
    if args.canary:
        files["canary"] = args.canary
    data = {name: read_json(path) for name, path in files.items()}
    result = classify(data["instances"], data["supervision"], args.count, args.generation, data.get("canary"))
    result["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ["status", "scope", "errors", "third_party_execution"]}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
