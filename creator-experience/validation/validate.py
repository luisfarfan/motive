#!/usr/bin/env python3
"""Offline authoring gates; stdlib only. No importer, engine or socket access.

Run from any directory. The Rust checker imports the actual versioned Show
Control crate; Python verifies bytes and stricter collection authoring rules.
"""
import argparse
import binascii
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import zlib
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
COLLECTION = HERE.parent
REPO = COLLECTION.parent


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, relative):
    path = root / relative
    require(not pathlib.PurePath(relative).is_absolute(), "absolute path")
    require(".." not in pathlib.PurePath(relative).parts, "path traversal")
    require(path.is_file() and not path.is_symlink(), f"missing/linked file: {relative}")
    require(path.resolve().is_relative_to(root.resolve()), f"escaped root: {relative}")
    return path


def png(path):
    data = path.read_bytes()
    require(len(data) <= 64 * 1024 * 1024, "PNG file limit")
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature")
    offset, chunks, image = 8, [], bytearray()
    width = height = channels = 0
    ended = False
    while offset < len(data):
        require(offset + 12 <= len(data), "PNG truncated chunk")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        require(end <= len(data), "PNG truncated payload")
        content = data[offset + 8:end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        require(binascii.crc32(kind + content) & 0xFFFFFFFF == checksum, "PNG CRC mismatch")
        if not chunks:
            require(kind == b"IHDR" and size == 13, "PNG first IHDR required")
        if kind == b"IHDR":
            require(not chunks, "PNG duplicate IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", content)
            require(0 < width <= 4096 and 0 < height <= 4096, "PNG validation dimension bound")
            require(depth == 8 and color in (0, 2, 4, 6), "Authoring PNG must be 8-bit grayscale/RGB/RGBA")
            require(compression == filtering == interlace == 0, "PNG unsupported encoding")
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
        elif kind == b"IDAT":
            image.extend(content)
        elif kind == b"IEND":
            require(size == 0 and end == len(data), "PNG trailing bytes")
            ended = True
        else:
            require(kind not in (b"acTL", b"fcTL", b"fdAT"), "Animated PNG is not an admitted asset")
            require(kind[0] & 32 or kind == b"PLTE", "PNG unknown critical chunk")
        chunks.append(kind)
        offset = end
    require(ended and image, "PNG incomplete image")
    expected = height * (1 + width * channels)
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(bytes(image), expected + 1)
    require(len(pixels) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, "PNG decompression size/stream mismatch")
    stride = width * channels + 1
    require(all(pixels[row * stride] <= 4 for row in range(height)), "PNG invalid row filter")
    return {"width": width, "height": height, "channels": channels,
            "decoded_scanline_bytes": len(pixels), "crc_and_zlib": "PASS"}


def svg(path):
    data = path.read_text()
    require("<!DOCTYPE" not in data and "<!ENTITY" not in data, "SVG entity declarations forbidden")
    root = ET.fromstring(data)
    for element in root.iter():
        require(element.tag.rsplit("}", 1)[-1] not in {"script", "foreignObject"}, "SVG active content")
        for key, value in element.attrib.items():
            require(not key.lower().startswith("on"), "SVG handler")
            if key.rsplit("}", 1)[-1] in {"href", "src"}:
                require(value.startswith("#") or value.startswith("data:image/png;base64,"), "SVG external dependency")
    return {"editable_source": True, "active_content": False}


def native_estimate(manifest):
    """Mirrors arithmetic only, not native graph acceptance or RSS measurement."""
    resources = {resource["id"]: resource for resource in manifest["resources"]}
    total, videos = 0, 0
    for source in manifest["overlays"]:
        definition = source["definition"]
        kind = definition["kind"]
        if kind in ("text", "shape"):
            total += definition["width"] * definition["height"] * 8
        elif kind == "widget":
            widget = definition["widget"]
            total += widget["width"] * widget["height"] * 8
        else:
            resource = resources[definition["resource_id"]]
            total += resource["width"] * resource["height"] * 8
        total += {"text": 8 * 1024**2, "widget": 16 * 1024**2}.get(kind, 0)
        videos += kind == "video"
    require(total <= 256 * 1024**2 and videos <= 4, "native planning memory/video limit")
    return {"bytes": total, "video_sources": videos, "limit_bytes": 256 * 1024**2,
            "method": "H11 overlay_native_graph arithmetic on declared dimensions",
            "native_rss_measured": False, "native_acceptance": False}


def pack_files(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    resources, previews, sources, geometries = [], [], [], []
    seen_names = set()
    for resource in manifest["resources"]:
        require(resource["file_name"] not in seen_names, "duplicate resource basename")
        seen_names.add(resource["file_name"])
        path = safe_file(directory / "assets", resource["file_name"])
        require(path.stat().st_size == resource["bytes"], f"bytes differ: {path.name}")
        require(digest(path) == resource["sha256"], f"SHA-256 differs: {path.name}")
        require(resource["kind"] == "image" and path.suffix.lower() == ".png", "This collection gate verifies PNG only; add real decoder verification before other media")
        dimensions = png(path)
        require((dimensions["width"], dimensions["height"]) == (resource["width"], resource["height"]), "declared dimensions differ")
        resources.append({"file": str(path.relative_to(directory)), "sha256": digest(path), "bytes": path.stat().st_size, **dimensions})
    for path in sorted(directory.rglob("*.svg")):
        safe_file(directory, path.relative_to(directory))
        sources.append({"file": str(path.relative_to(directory)), **svg(path)})
    for path in sorted((directory / "previews").glob("*.png")):
        previews.append({"file": str(path.relative_to(directory)), "sha256": digest(path), **png(path)})
    for scene in manifest["scenes"]:
        for orientation, dimensions in (("horizontal", (960, 540)), ("vertical", (540, 960))):
            orders = set()
            for layer in scene["layers"]:
                transform = layer[orientation]
                require(transform["order"] not in orders, f"ambiguous z-order: {scene['id']} {orientation}")
                orders.add(transform["order"])
                require(transform["x"] >= 0 and transform["y"] >= 0 and transform["x"] + transform["width"] <= dimensions[0] + .01 and transform["y"] + transform["height"] <= dimensions[1] + .01,
                        f"collection layer outside canvas: {scene['id']}/{layer['id']}/{orientation}")
            geometries.append({"scene": scene["id"], "orientation": orientation, "canvas": dimensions, "inside_canvas": True, "distinct_orders": True})
    require(manifest["license"] == "GPL-3.0-or-later", "collection license differs")
    require((directory / "README.md").is_file(), "pack README missing")
    require((directory / "metadata.json").is_file(), "discovery sidecar missing")
    metadata = json.loads((directory / "metadata.json").read_text())
    require(isinstance(metadata, dict) and metadata.get("description"), "metadata description missing")
    require(metadata.get("category") and metadata.get("tags"), "metadata category/tags missing")
    require(metadata["layout_space"] == {"horizontal": [960, 540], "vertical": [540, 960]}, "metadata coordinate space")
    require(metadata["resource_reserve"] == {"scenes": 8 - len(manifest["scenes"]), "sources": 16 - len(manifest["overlays"]), "layers": 32 - sum(len(scene["layers"]) for scene in manifest["scenes"])}, "metadata reserve does not match graph")
    safe_file(directory, metadata["cover"])
    for scene in metadata["scenes"]:
        require(any(item["id"] == scene["id"] for item in manifest["scenes"]), "metadata scene not in manifest")
        for orientation, expected in (("horizontal", (960, 540)), ("vertical", (540, 960))):
            preview = safe_file(directory, f"previews/{scene['slug']}-{orientation}.png")
            actual = png(preview)
            require((actual["width"], actual["height"]) == expected, "composition preview dimensions")
    provenance = json.loads(safe_file(directory, "assets/provenance.json").read_text())
    require(provenance["license"] == manifest["license"] and provenance["original"] and not provenance["third_party_assets"], "asset provenance mismatch")
    require(len(provenance["resources"]) == len(manifest["resources"]), "asset provenance incomplete")
    for item in provenance["resources"]:
        resource = next((r for r in manifest["resources"] if r["file_name"] == item["file_name"]), None)
        require(resource and item["sha256"] == resource["sha256"], "provenance resource hash mismatch")
        safe_file(directory / "assets", item["editable_source"])
    require(safe_file(directory, "LICENSE").stat().st_size > 1000, "full collection license missing")
    recipes = json.loads(safe_file(directory, "recipes.json").read_text())
    require(recipes["remaining_capacity"] == metadata["resource_reserve"], "recipe reserve mismatch")
    require(len(recipes["slots"]) <= metadata["resource_reserve"]["layers"], "capture recipe exceeds layer reserve")
    require(len({slot["source_role"] for slot in recipes["slots"]}) <= metadata["resource_reserve"]["sources"], "capture recipe exceeds source reserve")
    for slot in recipes["slots"]:
        scene = next((scene for scene in manifest["scenes"] if scene["id"] == slot["scene_id"]), None)
        require(scene, "recipe scene missing")
        frame = next((layer for layer in scene["layers"] if layer["id"] == slot["frame_layer_id"]), None)
        require(frame, "recipe frame missing")
        for orientation in ("horizontal", "vertical"):
            transform = slot[orientation]
            require(all(transform[key] == frame[orientation][key] for key in ("x", "y", "width", "height")), "capture/frame bounds mismatch")
            require(transform["order"] < frame[orientation]["order"], "capture occludes frame")
    migration = json.loads(safe_file(directory, "migration-from-0.1.json").read_text())
    symbols = {source["id"] for source in manifest["overlays"]}
    require(migration["retained_collection_id"] == manifest["id"] and migration["to_version"] == manifest["version"], "migration identity/version mismatch")
    require(set(migration["retained_source_symbols"]) <= symbols and not set(migration["removed_source_symbols"]) & symbols, "migration symbol declaration mismatch")
    require(resources and sources, "real PNG exports and editable SVG sources required")
    return {"pack_id": manifest["id"], "status": "PASS", "resources": resources,
            "editable_sources": sources, "previews": previews, "geometry": geometries,
            "native_planning_estimate": native_estimate(manifest),
            "license": manifest["license"], "license_file_sha256": digest(directory / "LICENSE"), "metadata": "PASS", "provenance": "PASS", "capture_recipe": "PASS", "migration_sidecar_references": "PASS (no migration performed)",
            "scope": "bytes, declarations, bounds; typography and occlusion need visual review"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rust", action="store_true", help="Only useful during asset iteration; final evidence must include Rust")
    args = parser.parse_args()
    evidence = COLLECTION / "evidence"
    evidence.mkdir(exist_ok=True)
    report = {"schema_version": 1, "mode": "offline_authoring_validation", "production_connection": False, "native_media_acceptance": False, "contracts": {}, "packs": [], "errors": []}
    for relative in ("show-control/src/packs.rs", "show-control/src/deck.rs", "show-control/src/actions.rs", "src/overlays/production.rs", "docs/h13-video-audio-contract.md"):
        report["contracts"][relative] = digest(REPO / relative)
    directories = [COLLECTION / "packs" / name for name in ("creator-tech", "neon-arena")]
    if not args.skip_rust:
        process = subprocess.run(["cargo", "run", "--quiet", "--offline", "--locked", "--manifest-path", str(HERE / "Cargo.toml"), "--target-dir", str(HERE / "target"), "--", *map(str, directories)], text=True, capture_output=True, cwd=REPO)
        (evidence / "contracts-rust.log").write_text(process.stderr)
        try:
            rust = json.loads(process.stdout)
            (evidence / "contracts-native.json").write_text(json.dumps(rust, indent=2) + "\n")
            report["rust_status"] = rust["status"]
        except json.JSONDecodeError:
            report["rust_status"] = "FAIL"
        if process.returncode:
            report["errors"].append("authoritative Rust validation failed; see contracts-native.json and contracts-rust.log")
    else:
        report["rust_status"] = "NOT_RUN"
    for directory in directories:
        try:
            report["packs"].append(pack_files(directory))
        except (ValueError, OSError, KeyError, struct.error, zlib.error, ET.ParseError) as error:
            report["packs"].append({"pack_id": directory.name, "status": "FAIL", "error": str(error)})
            report["errors"].append(f"{directory.name}: {error}")
    report["status"] = "FAIL" if report["errors"] else ("PARTIAL" if args.skip_rust else "PASS")
    (evidence / "contracts-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "rust": report["rust_status"], "packs": [{"id": p["pack_id"], "status": p["status"], "error": p.get("error")} for p in report["packs"]], "errors": report["errors"]}, indent=2))
    return bool(report["errors"])


if __name__ == "__main__":
    sys.exit(main())
