#!/usr/bin/env python3
"""Read-only inventory of a laboratory .app; no signing, loading, or notarizing."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(bundle):
    bundle = bundle.resolve(strict=True)
    rows = []
    unique_inodes = set()
    unique_bytes = 0
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            target = path.readlink().as_posix()
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(bundle):
                raise ValueError("BUNDLE_SYMLINK_ESCAPE:" + relative)
            rows.append({"path": relative, "kind": "symlink", "target": target})
        elif path.is_file():
            stat = path.stat()
            inode = (stat.st_dev, stat.st_ino)
            if inode not in unique_inodes:
                unique_inodes.add(inode)
                unique_bytes += stat.st_size
            rows.append({"path": relative, "kind": "file", "bytes": stat.st_size,
                         "sha256": sha256(path)})
    return {"files": rows,
            "apparent_file_bytes": sum(row.get("bytes", 0) for row in rows),
            "unique_inode_file_bytes": unique_bytes,
            "size_semantics": "file lengths, excluding directory/symlink bytes; not APFS physical allocation, compressed download size, RAM or RSS"}


def inspect(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return {"argv": [str(value) for value in command], "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def inspect_bundle(bundle):
    bundle = bundle.resolve(strict=True)
    result = inventory(bundle)
    framework = bundle / "Contents/Frameworks/Chromium Embedded Framework.framework"
    apps = [bundle, *sorted((bundle / "Contents/Frameworks").glob("*Helper*.app"))]
    binaries = []
    for app in apps:
        plist_path = app / "Contents/Info.plist"
        info = plistlib.loads(plist_path.read_bytes())
        binary = app / "Contents/MacOS" / info["CFBundleExecutable"]
        if not binary.resolve(strict=True).is_relative_to(bundle):
            raise ValueError("EXECUTABLE_ESCAPE")
        signature = inspect(["codesign", "-dvv", str(binary)])
        entitlements = inspect(["codesign", "-d", "--entitlements", ":-", str(binary)])
        text = signature["stderr"] + signature["stdout"]
        binaries.append({"path": binary.relative_to(bundle).as_posix(), "sha256": sha256(binary),
                         "identifier": info["CFBundleIdentifier"],
                         "minimum_system_version": info.get("LSMinimumSystemVersion"),
                         "architecture": inspect(["lipo", "-archs", str(binary)]),
                         "signature": signature, "entitlements": entitlements,
                         "ad_hoc_signature_observed": "Signature=adhoc" in text,
                         "hardened_runtime_flag_observed": bool(re.search(r"flags=.*\bruntime\b", text))})
    framework_binary = framework / "Chromium Embedded Framework"
    result.update({"bundle": str(bundle), "native_executed": False,
                   "audit_tool_sha256": sha256(Path(__file__)),
                   "artifact_sha256": binaries[0]["sha256"], "binaries": binaries,
                   "framework_binary_sha256": sha256(framework_binary),
                   "framework_architecture": inspect(["lipo", "-archs", str(framework_binary)]),
                   "signature_verification": inspect(["codesign", "--verify", "--strict", "--deep", str(bundle)]),
                   "distribution_status": "BLOCKED", "sandbox_status": "NOT_EVALUATED",
                   "notarization": "NOT_EVALUATED_NOT_REQUESTED",
                   "third_party_execution": "BLOCKED"})
    result["cef_license_present"] = (bundle / "Contents/Resources/CEF-LICENSE.txt").is_file()
    result["chromium_credits_present"] = (bundle / "Contents/Resources/Chromium-CREDITS.html").is_file()
    result["resource_bytes"] = sum(row.get("bytes", 0) for row in result["files"] if "/Resources/" in row["path"])
    result["locale_bytes"] = sum(row.get("bytes", 0) for row in result["files"] if ".lproj/" in row["path"])
    result["framework_bytes"] = sum(row.get("bytes", 0) for row in result["files"] if row["path"].startswith("Contents/Frameworks/Chromium Embedded Framework.framework/"))
    architectures = [entry["architecture"] for entry in binaries] + [result["framework_architecture"]]
    arm64 = all(entry["returncode"] == 0 and entry["stdout"].strip() == "arm64" for entry in architectures)
    unique_identifiers = len({entry["identifier"] for entry in binaries}) == len(binaries)
    result["static_inventory_status"] = "PASS" if (result["signature_verification"]["returncode"] == 0
                                                   and len(binaries) == 6 and unique_identifiers and arm64) else "FAIL"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_bundle(args.bundle)
    # New report only; never overwrite historical or prior observations.
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ["artifact_sha256", "apparent_file_bytes", "framework_bytes", "resource_bytes", "locale_bytes", "static_inventory_status", "distribution_status"]}, indent=2))
    return 0 if result["static_inventory_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
