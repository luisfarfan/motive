#!/usr/bin/env python3
"""Explicit supervised launcher for the pinned Motive-owned CEF smoke fixture.

Never called by verify_h18. No arbitrary executable, URL, package or JS argument.
This tool does not authorize third-party content or prove an OS sandbox.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time
import uuid
import zlib

LAB = Path(__file__).resolve().parents[1]
VIEWPORTS = {(640, 360), (960, 540), (540, 960)}
LEGACY_SMOKE_HASHES = {
    "38a1f280f8c539b144ea6e0b9e6b28b336efca79e6605011484cd55cf0179d14",
    "3d9be2d6ebefd0b07ce7736e831f51585d96996b8e8554fcdd68ecf2acab72b5",
}
PIN = "0343233fc462384c2f1f58a4222028bc6171f05948a822241f89df2faa7cee8d"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path, maximum, *, allow_hardlinks=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and (allow_hardlinks or info.st_nlink == 1) and 0 <= info.st_size <= maximum, "REGULAR_BOUNDED_FILE_REQUIRED")
        data = bytearray()
        while chunk := os.read(fd, min(65536, maximum + 1 - len(data))):
            data.extend(chunk)
            require(len(data) <= maximum, "FILE_SIZE")
        after = os.fstat(fd)
        require((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "FILE_CHANGED")
        return bytes(data)
    finally:
        os.close(fd)


def object_pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "JSON_DUPLICATE")
        value[key] = item
    return value


def parse_json(data):
    return json.loads(data, object_pairs_hook=object_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON_NUMBER")))


def read_json(path, maximum=2 * 1024**2):
    return parse_json(regular_bytes(path, maximum))


def write_new(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def save_json(path, value):
    write_new(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def canonical_directory(path):
    absolute = Path(os.path.abspath(path))
    require(absolute.resolve(strict=True) == absolute, "SYMLINK_DIRECTORY_FORBIDDEN")
    require(absolute.is_dir(), "DIRECTORY_REQUIRED")
    return absolute


def expected_binary_paths():
    prefix = Path("MotiveBrowserFixture.app/Contents")
    paths = {prefix / "MacOS/MotiveBrowserFixture"}
    for suffix in ("", " (Alerts)", " (GPU)", " (Plugin)", " (Renderer)"):
        name = "MotiveBrowserFixture Helper" + suffix
        paths.add(prefix / "Frameworks" / (name + ".app") / "Contents/MacOS" / name)
    return paths


def match_build_report(build_root, expected_sha256):
    """Select only a retained local build report with this exact artifact identity."""
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None, "EXPECTED_SHA256")
    build_root = canonical_directory(build_root)
    require(build_root.is_relative_to(LAB / ".cache"), "GENERATED_LOCAL_BUILD_REQUIRED")
    wanted = build_root / "MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture"
    matches = []
    for path in sorted((LAB / "evidence").glob("H18-native*-build.json")):
        report = read_json(path)
        binaries = report.get("binaries", [])
        if not binaries:
            continue
        first = binaries[0]
        if first.get("sha256") != expected_sha256 or LAB / first.get("path", "") != wanted:
            continue
        profile = report.get("profile", report.get("candidate_profile"))
        if profile is None and expected_sha256 in LEGACY_SMOKE_HASHES:
            profile = "owned-smoke"
        require(profile == "owned-smoke", "OWNED_SMOKE_PROFILE_REQUIRED")
        require(report.get("status") == "PASS" and report.get("cef", {}).get("sha256") == PIN,
                "MATCHING_PINNED_BUILD_REQUIRED")
        matches.append((path, report))
    require(len(matches) == 1, "ONE_MATCHING_BUILD_REPORT_REQUIRED")
    return build_root, matches[0][0], matches[0][1]


def verify_inventory(build_root, report, expected_sha256):
    """Hash only the exact expected main/helper roles and matching CEF framework."""
    bundle = build_root / "MotiveBrowserFixture.app"
    require(canonical_directory(bundle) == bundle, "BUNDLE_DIRECTORY")
    allowed = expected_binary_paths()
    actual = set()
    binaries = []
    for record in report["binaries"]:
        relative = Path(record["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "BUILD_INVENTORY_PATH")
        path = LAB / relative
        require(path.is_relative_to(build_root), "BUILD_INVENTORY_OUTSIDE_ROOT")
        short = path.relative_to(build_root)
        require(short in allowed and short not in actual, "BUILD_INVENTORY_ROLE")
        actual.add(short)
        require(path.resolve(strict=True) == path, "BINARY_SYMLINK")
        data = regular_bytes(path, 32 * 1024**2, allow_hardlinks=True)
        require(sha(data) == record["sha256"], "BINARY_HASH_MISMATCH")
        binaries.append({"path": str(short), "sha256": sha(data), "bytes": len(data)})
    require(actual == allowed and binaries[0]["sha256"] == expected_sha256, "BUILD_INVENTORY_INCOMPLETE")
    framework = bundle / "Contents/Frameworks/Chromium Embedded Framework.framework"
    executable = (framework / "Chromium Embedded Framework").resolve(strict=True)
    require(executable.is_relative_to(framework), "FRAMEWORK_SYMLINK_ESCAPE")
    digest = hashlib.sha256()
    with executable.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    require(digest.hexdigest() == report["framework_sha256"], "FRAMEWORK_HASH_MISMATCH")
    signature = subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "--deep", str(bundle)],
                               capture_output=True, timeout=30)
    require(signature.returncode == 0, "BUNDLE_SIGNATURE_INVALID")
    return {"status": "PASS", "scope": "static artifact identity and local development signature",
            "binaries": binaries, "framework_sha256": digest.hexdigest(),
            "signature_verified": True, "sandbox_verified": False}


def validate_options(args):
    require((args.width, args.height) in VIEWPORTS, "REVIEWED_VIEWPORT_REQUIRED")
    require(args.fps in (30, 60), "REVIEWED_FPS_REQUIRED")
    require(args.generation is None or 1 <= args.generation <= 2**64 - 1, "GENERATION")
    require(1000 <= args.duration_ms <= 15000, "FIXTURE_DURATION")
    require(math.isfinite(args.deadline_seconds) and args.duration_ms / 1000 < args.deadline_seconds <= 25,
            "SUPERVISOR_DEADLINE")
    require(64 <= args.rss_limit_mib <= 2048, "SUPERVISOR_RSS_LIMIT")


def decode_counter(pixels, width, height):
    """Decode the original fixture's eight opaque binary bars, modulo 256 only."""
    if len(pixels) != width * height * 4 or width <= 268 or height <= 104:
        return {"status": "NOT_EVALUATED", "value_modulo_256": None, "reason": "frame layout unavailable"}
    value, samples = 0, []
    for bit in range(8):
        offset = (104 * width + 136 + bit * 18) * 4
        sample = tuple(pixels[offset:offset + 4])
        samples.append(sample)
        if sample[3] != 255:
            return {"status": "NOT_EVALUATED", "value_modulo_256": None, "reason": "counter bar is not opaque", "samples_bgra": samples}
        if all(250 <= channel <= 255 for channel in sample[:3]):
            value |= 1 << bit
        elif not all(49 <= channel <= 53 for channel in sample[:3]):
            return {"status": "NOT_EVALUATED", "value_modulo_256": None, "reason": "counter bar outside fixture colors", "samples_bgra": samples}
    return {"status": "PASS", "value_modulo_256": value, "samples_bgra": samples,
            "scope": "visible JS counter modulo 256, not host frame index or PTS"}


def alpha_checks(pixels, width, height):
    require(len(pixels) == width * height * 4, "FRAME_LAYOUT")
    offset = (50 * width + 50) * 4
    corner, red = tuple(pixels[:4]), tuple(pixels[offset:offset + 4])
    checks = {"transparent_corner": corner == (0, 0, 0, 0),
              "half_alpha_red": red[:2] == (0, 0) and 126 <= red[2] <= 129 and 126 <= red[3] <= 129,
              "premultiplied_bound": all(max(pixels[i:i + 3]) <= pixels[i + 3] + 1 for i in range(0, len(pixels), 4))}
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "samples_bgra": {"corner": corner, "red": red},
            "scope": "fixture pixel arithmetic; not complete color calibration or libobs blending"}


def preview_png(pixels, width, height):
    """Derived PNG only. Unpremultiply BGRA to ordinary RGBA; retain raw bytes separately."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            at = (y * width + x) * 4
            b, g, r, a = pixels[at:at + 4]
            rows.extend((min(255, (r * 255 + a // 2) // a) if a else 0,
                         min(255, (g * 255 + a // 2) // a) if a else 0,
                         min(255, (b * 255 + a // 2) // a) if a else 0, a))
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def collect_samples(fixture_root, output, width, height, generation, png=False):
    records = {}
    for name in ("first", "latest"):
        record = {"status": "NOT_EVALUATED", "frame_index": None, "metadata_present": False}
        pixels_path, metadata_path = fixture_root / (name + ".bgra"), fixture_root / (name + ".json")
        if not pixels_path.exists():
            record["reason"] = "native consumer produced no sample file"
            records[name] = record
            continue
        pixels = regular_bytes(pixels_path, 1920 * 1080 * 4)
        record.update(raw_bytes=len(pixels), raw_sha256=sha(pixels))
        if len(pixels) != width * height * 4:
            record.update(status="FAIL", reason="incomplete native sample")
            records[name] = record
            continue
        record.update(status="PASS", dimensions_source="authorized_launch_configuration")
        if metadata_path.exists():
            metadata = read_json(metadata_path, 65536)
            save_json(output / (name + ".json"), metadata)
            require(metadata.get("native_executed") is True and metadata.get("generation") == generation and
                    (metadata.get("width"), metadata.get("height"), metadata.get("stride")) == (width, height, width * 4),
                    "FRAME_METADATA_MISMATCH")
            record.update(metadata_present=True, dimensions_source="native_metadata", metadata=metadata)
            record["frame_index"] = metadata.get("index") if type(metadata.get("index")) is int else None
        compressed = gzip.compress(pixels, compresslevel=6, mtime=0)
        write_new(output / (name + ".bgra.gz"), compressed)
        record["compressed"] = {"file": name + ".bgra.gz", "bytes": len(compressed), "sha256": sha(compressed), "algorithm": "gzip"}
        record["alpha"] = alpha_checks(pixels, width, height)
        record["counter"] = decode_counter(pixels, width, height)
        if png:
            data = preview_png(pixels, width, height)
            write_new(output / (name + ".png"), data)
            record["preview"] = {"file": name + ".png", "sha256": sha(data), "derived_from_raw_bgra": True}
        records[name] = record
    return records


def classify(supervision, samples):
    latest = samples.get("latest", {})
    frame_delivery = "PASS" if latest.get("status") == "PASS" else "FAIL"
    alpha = latest.get("alpha", {}).get("status", "NOT_EVALUATED")
    first_counter = samples.get("first", {}).get("counter", {}).get("value_modulo_256")
    latest_counter = latest.get("counter", {}).get("value_modulo_256")
    counter_changed = ("PASS" if first_counter != latest_counter else "NOT_EVALUATED") if None not in (first_counter, latest_counter) else "NOT_EVALUATED"
    orderly = "PASS" if supervision.get("reason") == "exit" and supervision.get("returncode") == 0 else "FAIL"
    cleanup = "PASS" if supervision.get("final_cleanup_observed_tree") is True and supervision.get("final_remaining_observed_pids") == [] else "FAIL"
    gates = {"frame_delivery": frame_delivery, "alpha_pixels": alpha, "visible_counter_changed": counter_changed,
             "orderly_shutdown": orderly, "observed_tree_cleanup": cleanup,
             "third_party_isolation": "NOT_EVALUATED", "libobs_integration": "NOT_EVALUATED"}
    required = [frame_delivery, alpha, counter_changed, orderly, cleanup]
    status = "PASS" if all(s == "PASS" for s in required) else "PARTIAL" if "PASS" in required else "FAIL"
    return {"status": status, "gates": gates, "counter_delta_modulo_256":
            ((latest_counter - first_counter) % 256 if None not in (first_counter, latest_counter) else None),
            "counter_wrap_possible": True}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--build-root", type=Path, required=True)
    result.add_argument("--expected-sha256", required=True)
    result.add_argument("--output-dir", type=Path, help="New evidence directory; default unique directory under web-host-lab/evidence")
    result.add_argument("--width", type=int, default=640)
    result.add_argument("--height", type=int, default=360)
    result.add_argument("--fps", type=int, default=30)
    result.add_argument("--generation", type=int, help="Positive owner-chosen generation; default fresh monotonic value")
    result.add_argument("--duration-ms", type=int, default=5000)
    result.add_argument("--deadline-seconds", type=float, default=10)
    result.add_argument("--rss-limit-mib", type=int, default=2048)
    result.add_argument("--png", action="store_true", help="Write derived PNG previews in addition to unchanged compressed BGRA")
    result.add_argument("--preflight-only", action="store_true", help="Verify artifact and signature without launching a process")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    report = {"status": "FAIL", "native_host_executed": False, "third_party_content_allowed": False,
              "production_connected": False, "sandbox_verified": False}
    output = None
    output_created = False
    try:
        validate_options(args)
        build_root, report_path, build_report = match_build_report(args.build_root, args.expected_sha256)
        inventory = verify_inventory(build_root, build_report, args.expected_sha256)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        output = Path(os.path.abspath(args.output_dir or (LAB / "evidence" / ("H18-owned-fixture-" + run_id))))
        canonical_directory(output.parent)
        output.mkdir(mode=0o700)  # Fresh only: never overwrite or clean someone else's evidence.
        output_created = True
        report.update(run_id=run_id, static_inventory=inventory, build_report=str(report_path.relative_to(LAB)),
                      build_report_sha256=sha(regular_bytes(report_path, 2 * 1024**2)),
                      expected_executable_sha256=args.expected_sha256, requested={"width": args.width, "height": args.height,
                      "fps": args.fps, "duration_ms": args.duration_ms, "deadline_seconds": args.deadline_seconds,
                      "rss_limit_mib": args.rss_limit_mib}, source_identity=build_report.get("source_sha256"))
        if args.preflight_only:
            report.update(status="PASS", scope="static_preflight_only", native_host_executed=False)
        else:
            cache = LAB / ".cache" / "owned-fixture-runs"
            cache.mkdir(exist_ok=True)
            canonical_directory(cache)
            private = cache / run_id
            private.mkdir(mode=0o700)
            fixture_root, supervisor_root = private / "fixture", private / "supervisor"
            fixture_root.mkdir(mode=0o700)
            supervisor_root.mkdir(mode=0o700)
            spec = importlib.util.spec_from_file_location("motive_owned_supervisor", LAB / "poc/browser-host/supervisor.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            supervisor = module.Supervisor(supervisor_root, deadline_seconds=args.deadline_seconds,
                                            rss_limit_kib=args.rss_limit_mib * 1024)
            generation = args.generation if args.generation is not None else time.monotonic_ns()
            executable = build_root / "MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture"
            command = [str(executable), "--owned-fixture", str(fixture_root), str(generation), str(args.width),
                       str(args.height), str(args.fps), str(args.duration_ms)]
            report.update(scope="owned_cef_smoke_fixture", native_generation=generation, raw_evidence_root=str(private))
            try:
                supervision = supervisor.run(command)
                report["native_host_executed"] = True
            except BaseException as error:
                supervision = supervisor.last_report or {}
                report["supervisor_error_type"] = type(error).__name__
                report["native_host_executed"] = bool(supervision.get("observed_processes", 0))
            report["supervision"] = supervision
            save_json(output / "supervision.json", supervision)
            samples = collect_samples(fixture_root, output, args.width, args.height, generation, args.png)
            report.update(samples=samples, **classify(supervision, samples))
            for name in ("frames.json", "lifecycle.jsonl"):
                path = fixture_root / name
                if path.exists():
                    data = regular_bytes(path, 2 * 1024**2)
                    write_new(output / name, data)
            report["limits"] = ["Cleanup concerns the observed tree, not proof against hostile process escape.",
                "ps CPU is a sampled estimate; footprint and GPU are not measured.",
                "Missing frame metadata remains missing; no host index or PTS is synthesized.",
                "A changed visible counter is modulo 256 and does not measure every displayed frame."]
        save_json(output / "report.json", report)
        print(json.dumps({"status": report["status"], "native_host_executed": report["native_host_executed"],
                          "gates": report.get("gates"), "report": str(output / "report.json")}, indent=2))
        return 0 if report["status"] == "PASS" else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report["error"] = {"type": type(error).__name__, "code": str(error)[:512]}
        if output_created and not (output / "report.json").exists():
            save_json(output / "report.json", report)
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
