#!/usr/bin/env python3
"""Finalize a Claude Design pull into design/claude-design/<canvas>/.

Claude downloads the canvas files (project/*) and its uploaded assets
(assets/<blob-id>.<ext>) with the Artifact tool; see
.claude/skills/design-pull/SKILL.md. This script runs afterwards and needs
no network or credentials:

  python3 design/tools/finalize_pull.py <canvas-dir> --url <artifact-url> --version <id> \
      [--asset <blob-id>=<role>] ...

It writes <canvas-dir>/manifest.json (boards, files with sha256, blob map)
and fails if any /_blob/<id> referenced by an artboard is missing locally.
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

BLOB = re.compile(r"/_blob/([0-9a-f]{32})")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("canvas_dir", type=pathlib.Path)
    ap.add_argument("--url", required=True, help="claude.ai artifact URL of the canvas")
    ap.add_argument("--version", required=True, help="artifact version id that was pulled")
    ap.add_argument("--asset", action="append", default=[], help="<blob-id>=<role> description")
    args = ap.parse_args()

    root = args.canvas_dir.resolve()
    project = root / "project"
    assets = root / "assets"
    index = json.loads((project / "canvas.json").read_text())

    roles = dict(a.split("=", 1) for a in args.asset)
    local_blobs = {p.stem: p for p in assets.glob("*")} if assets.exists() else {}

    files, referenced, problems = [], {}, []
    for path in sorted(project.glob("*")):
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
        if path.suffix == ".html":
            for blob in BLOB.findall(path.read_text()):
                referenced.setdefault(blob, set()).add(rel)

    for blob, users in sorted(referenced.items()):
        if blob not in local_blobs:
            problems.append(f"missing asset {blob} referenced by {', '.join(sorted(users))}")

    boards = [
        {"file": f"project/{name}", **{k: v for k, v in index["boards"][name].items()}}
        for name in index.get("order", index["boards"].keys())
    ]
    manifest = {
        "source": {"tool": "Claude Design (Design canvas)", "url": args.url, "version": args.version},
        "pulled_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "title": index.get("title"),
        "boards": boards,
        "files": files,
        "blobs": [
            {
                "id": blob,
                "url": f"/_blob/{blob}",
                "local": local_blobs[blob].relative_to(root).as_posix() if blob in local_blobs else None,
                "sha256": sha256(local_blobs[blob]) if blob in local_blobs else None,
                "role": roles.get(blob, ""),
                "used_by": sorted(referenced.get(blob, [])),
            }
            for blob in sorted(set(referenced) | set(local_blobs))
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    print(f"{len(boards)} boards, {len(files)} files, {len(manifest['blobs'])} assets -> {root / 'manifest.json'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
