#!/usr/bin/env python3
"""Read-only compatibility against a supplied H14 checkout; no Motive execution."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=pathlib.Path, help="Existing H14 checkout, read-only")
    args = parser.parse_args()
    here = pathlib.Path(__file__).resolve().parent
    collection = here.parent
    repo = collection.parent
    checkout = args.checkout.resolve(strict=True)
    destination = here / "target" / "h14-compat"
    destination.mkdir(parents=True, exist_ok=True)
    evidence = collection / "evidence"
    files = ["show-control/src/packs.rs", "show-control/src/deck.rs", "show-control/src/actions.rs", "show-control/src/runtime.rs", "src/creator_packs.rs"]

    def hashes():
        return {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in files}

    report = {
        "h14_commit": subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip(),
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "read_only": True,
        "dirty_h14_workspace": bool(subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True).strip()),
        "source_hashes": hashes(),
        "scope": "Independent Show Control parser/action simulation, no Motive/native importer execution",
    }
    manifest = '[package]\nname="creator-h14-compatibility"\nversion="0.1.0"\nedition="2024"\npublish=false\n[workspace]\n[dependencies]\nmotive-show-control={path=' + json.dumps(os.path.relpath(checkout / "show-control", destination)) + '}\nserde_json="1"\n[[bin]]\nname="creator-h14-compatibility"\npath="../../src/main.rs"\n'
    (destination / "Cargo.toml").write_text(manifest)
    commands = [
        ["cargo", "generate-lockfile", "--offline", "--manifest-path", str(destination / "Cargo.toml")],
        ["cargo", "run", "--quiet", "--offline", "--locked", "--manifest-path", str(destination / "Cargo.toml"), "--target-dir", str(here / "target" / "h14-build"), "--", "creator-experience/packs/creator-tech", "creator-experience/packs/neon-arena"],
    ]
    log, failed = [], False
    for command in commands:
        process = subprocess.run(command, text=True, capture_output=True, cwd=repo)
        log.append(process.stderr)
        if command[1] == "run":
            try:
                checked = json.loads(process.stdout)
                (evidence / "contracts-h14-compatibility.json").write_text(json.dumps(checked, indent=2) + "\n")
                report["check_status"] = checked["status"]
            except json.JSONDecodeError:
                report["check_status"] = "FAIL"
        if process.returncode:
            failed = True
            break
    report["source_hashes_after"] = hashes()
    report["source_stable_during_check"] = report["source_hashes"] == report["source_hashes_after"]
    report["status"] = "PASS" if not failed and report["source_stable_during_check"] and report.get("check_status") == "PASS" else "FAIL"
    (evidence / "contracts-h14-build.log").write_text("\n".join(log).rstrip() + "\n")
    (evidence / "contracts-h14-snapshot.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "h14_commit", "source_stable_during_check")}, indent=2))
    return report["status"] != "PASS"


if __name__ == "__main__":
    sys.exit(main())
