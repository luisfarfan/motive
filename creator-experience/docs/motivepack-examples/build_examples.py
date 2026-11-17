#!/usr/bin/env python3
"""Generate reviewable envelope/checksum examples, never ZIPs or installations.

Only projects existing controlled authoring files into proposed archive paths.
No input package is opened, extracted, executed, imported or downloaded.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def example(pack_id):
    source = ROOT / "packs" / pack_id
    pack = json.loads((source / "manifest.json").read_text())
    metadata = json.loads((source / "metadata.json").read_text())
    paths = {name: source / name for name in ("manifest.json", "rules.json", "deck.json", "LICENSE")}
    paths.update({f"assets/{r['file_name']}": source / "assets" / r["file_name"] for r in pack["resources"]})
    paths.update({f"authoring/{p.name}": p for p in sorted((source / "assets/source").glob("*.svg"))})
    paths.update({f"previews/{p.name}": p for p in sorted((source / "previews").glob("*.png"))})
    content = {name: path.read_bytes() for name, path in paths.items()}
    package = {
        "package_version": 1,
        "id": pack["id"], "version": pack["version"], "name": pack["name"],
        "author": pack["author"], "license": pack["license"],
        "description": metadata["description"], "category": metadata["category"],
        "tags": metadata["tags"], "manifest": "manifest.json", "manifest_schema_version": 1,
        "coordinate_space": "design960", "minimum_capabilities": pack["requires"],
        "preview_paths": sorted(name for name in content if name.startswith("previews/")),
        "property_ids": [prop["id"] for prop in pack["properties"]],
        "file_count": len(content) + 2, "total_uncompressed_bytes": 0,
        "compatibility_notes": [
            "Proposed container envelope; not an accepted H14 distribution format.",
            "The observed H14 importer embeds MATCHDAY and rejects external resources.",
            "These examples do not constitute installation or native audiovisual acceptance.",
        ],
    }
    # Both envelope documents count toward the total. Only the byte-count decimal
    # width can change; every SHA-256 string has a fixed length.
    for _ in range(20):
        content["package.json"] = encode(package)
        checksums = {"version": 1, "algorithm": "sha256", "files": [
            {"path": name, "bytes": len(data), "sha256": digest(data)}
            for name, data in sorted(content.items())
        ]}
        size = sum(map(len, content.values())) + len(encode(checksums))
        if size == package["total_uncompressed_bytes"]:
            break
        package["total_uncompressed_bytes"] = size
    else:
        raise ValueError("Envelope byte-count did not stabilize")
    content["checksums.json"] = encode(checksums)
    assert len(content) == package["file_count"]
    assert sum(map(len, content.values())) == package["total_uncompressed_bytes"]
    assert max(map(len, content.values())) <= 64 * 1024**2
    assert len(content) <= 256 and package["total_uncompressed_bytes"] <= 128 * 1024**2
    for entry in checksums["files"]:
        assert len(content[entry["path"]]) == entry["bytes"]
        assert digest(content[entry["path"]]) == entry["sha256"]
    for resource in pack["resources"]:
        data = content[f"assets/{resource['file_name']}"]
        assert digest(data) == resource["sha256"] and len(data) == resource["bytes"]
    (HERE / f"{pack_id}.package.json").write_bytes(content["package.json"])
    (HERE / f"{pack_id}.checksums.json").write_bytes(content["checksums.json"])
    return {
        "pack_id": pack_id, "scope": "Proposed logical payload; no archive created or installed",
        "status": "PASS", "file_count": len(content),
        "total_uncompressed_bytes": package["total_uncompressed_bytes"],
        "checksums_cover_all_files_except_self": True,
        "source_paths": {name: str(path.relative_to(ROOT)) for name, path in sorted(paths.items())},
        "generated_envelope_paths": {"package.json": f"{pack_id}.package.json", "checksums.json": f"{pack_id}.checksums.json"},
    }


if __name__ == "__main__":
    reports = [example(pack_id) for pack_id in ("creator-tech", "neon-arena")]
    (HERE / "projection-validation.json").write_bytes(encode({
        "scope": "Distribution proposal examples only", "status": "PASS",
        "archive_emitted": False, "installation_performed": False, "packs": reports,
    }))
    print(json.dumps({"status": "PASS", "examples": len(reports), "archives_created": 0}))
