#!/usr/bin/env python3
"""Reproduce independent-module evidence. Never starts Motive or accesses devices."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)
checks = []

def command(name, args, expected=0, json_output=False):
    started = time.monotonic()
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
    (EVIDENCE / (name + ".log")).write_text(result.stdout + result.stderr)
    checks.append(dict(name=name, command=args, exit_code=result.returncode,
                       expected_exit=expected, passed=result.returncode == expected,
                       elapsed_seconds=round(time.monotonic() - started, 3)))
    if result.returncode != expected:
        raise RuntimeError(f"{name} failed; see evidence/{name}.log")
    if json_output:
        data = json.loads(result.stdout)
        (EVIDENCE / (name + ".json")).write_text(json.dumps(data, indent=2) + "\n")
        return data
    return result.stdout + result.stderr

started = datetime.datetime.now(datetime.timezone.utc).isoformat()
tests = command("tests", ["cargo", "test", "--locked"])
command("clippy", ["cargo", "clippy", "--locked", "--all-targets", "--", "-D", "warnings"])
command("fmt", ["cargo", "fmt", "--", "--check"])
binary = str(ROOT / "target/debug/motive-show")
command("build", ["cargo", "build", "--locked"])
for scenario in ["goal", "donation", "chat", "burst"]:
    args = [binary, "simulate", scenario]
    if scenario != "burst":
        args.append("examples/packs/matchday.json")
    data = command(scenario, args, json_output=True)
    assert data["mode"] == "simulation_only" and data["live_commands_sent"] == 0
    assert all(job["state"] in ["simulated", "cancelled"] for job in data["jobs"])
for name in ["matchday", "creator-tech", "neon-arena"]:
    data = command("pack-" + name, [binary, "plan-pack", f"examples/packs/{name}.json"], json_output=True)
    assert data["executable"] is False
for button in ["goal", "countdown", "lower-third", "lower-entry", "brb", "live", "community", "celebrate"]:
    data = command("deck-" + button, [binary, "deck-press", "examples/decks/matchday.json", "examples/packs/matchday.json", button, "--confirm"], json_output=True)
    assert data["simulation"]["jobs"] and all(j["state"] == "simulated" for j in data["simulation"]["jobs"])
command("deck-confirmation-required", [binary, "deck-press", "examples/decks/matchday.json", "examples/packs/matchday.json", "brb"], expected=1)
command("loaded-definition", [binary, "run", "examples/rules/matchday.json", "examples/events/goal.jsonl"], json_output=True)
command("loaded-pack-definition", [binary, "run", "examples/rules/matchday.json", "examples/events/goal.jsonl", "examples/packs/matchday.json"], json_output=True)
for path in sorted((ROOT / "examples/events").glob("*.jsonl")):
    command("schema-" + path.stem, [binary, "validate-event", str(path)], json_output=True)
command("schema-rules", [binary, "validate-config", "examples/rules/matchday.json"], json_output=True)
command("design-previews", ["python3", "design/render_preview.py"])
files = [ROOT/"Cargo.toml", ROOT/"Cargo.lock"]
for directory in ["src", "tests", "examples"]:
    files.extend(p for p in (ROOT/directory).rglob("*") if p.is_file())
source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
result = dict(schema_version=1, scope="independent_simulation_only", started_utc=started,
              core_baseline="b52d135", native_tests_executed=False, live_commands_sent=0,
              tests_passed=sum(map(int, re.findall(r"test result: ok\. (\d+) passed", tests))),
              checks=checks, source_sha256=source_hashes,
              caveat="Durations are test command elapsed time, not production CPU, memory or media performance benchmarks.")
(EVIDENCE/"verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"ok": True, "tests_passed":result["tests_passed"], "checks":len(checks), "report":"show-control/evidence/verification.json"}))
