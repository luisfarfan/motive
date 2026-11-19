#!/usr/bin/env python3
"""Verify/download only the pinned public source files used by the H19 audit.

Never starts a browser, calls Security.framework, or reads a user's keychain.
The lock is evidence, not an allowlist for running code downloaded by this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def verify_sources(index, root, fetch=False):
    results = []
    for source in index["sources"]:
        if "error" in source:
            continue  # Retained failed research lookups have no source assertion.
        local = root / source["cache"]
        if not local.resolve().is_relative_to((root / ".cache/h19-source-research").resolve()):
            raise ValueError("SOURCE_CACHE_ESCAPE")
        expected_prefix = ("https://raw.githubusercontent.com/" + source["repository"]
                           + "/" + source["revision"] + "/")
        if source["url"] != expected_prefix + source["path"]:
            raise ValueError("SOURCE_URL_MISMATCH")
        if fetch and not local.exists():
            with urllib.request.urlopen(source["url"], timeout=30) as response:
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) != source["bytes"] or hashlib.sha256(data).hexdigest() != source["sha256"]:
                raise ValueError("DOWNLOADED_SOURCE_CHANGED")
            local.parent.mkdir(parents=True, exist_ok=True)
            with local.open("xb") as stream:
                stream.write(data)
        if not local.is_file() or local.is_symlink():
            results.append({"path": source["path"], "status": "MISSING"})
            continue
        data = local.read_bytes()
        valid = len(data) == source["bytes"] and hashlib.sha256(data).hexdigest() == source["sha256"]
        results.append({"path": source["path"], "status": "PASS" if valid else "HASH_MISMATCH"})
    return {"status": "PASS" if results and all(r["status"] == "PASS" for r in results) else "FAIL",
            "scope": "source bytes only; no native security or distribution acceptance",
            "native_executed": False, "files": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="fetch missing pinned public files")
    args = parser.parse_args()
    index = json.loads((ROOT / "research/h19-source-index.json").read_text())
    result = verify_sources(index, ROOT, args.fetch)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
