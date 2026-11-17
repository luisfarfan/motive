#!/usr/bin/env python3
"""Index actual manifest animations for documentation; no dispatch or playback."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    entries = []
    for folder in sorted((ROOT / "packs").iterdir()):
        manifest = folder / "manifest.json"
        if not manifest.exists():
            continue
        pack = json.loads(manifest.read_text())
        scenes = {scene["id"]: scene for scene in pack["scenes"]}
        metadata = json.loads((folder / "metadata.json").read_text())
        slugs = {scene["id"]: scene["slug"] for scene in metadata["scenes"]}
        for animation in pack["animations"]:
            scene = scenes[animation["scene_id"]]
            layer = next(layer for layer in scene["layers"] if layer["id"] == animation["layer_id"])
            outgoing = animation["kind"].endswith("_out")
            entries.append({
                "pack_id": pack["id"],
                "manifest": f"../packs/{folder.name}/manifest.json",
                "animation": animation,
                "source_ref": layer["overlay_id"],
                "purpose": "Retirar el elemento sin detener las salidas" if outgoing else "Presentar el elemento de forma acotada",
                "editable_parameters": ["duration_ms"] + (["distance"] if animation["kind"].startswith("slide") else ["scale_from"] if animation["kind"].startswith("scale") else []),
                "compatibility": "H11 layer_animation contract; runtime binding and native acceptance pending",
                "illustrative_previews": {o: f"../packs/{folder.name}/previews/{'alert' if '-alert-' in animation['id'] else slugs[scene['id']]}-{o}.png" for o in ("horizontal", "vertical")},
                "interactive_preview": "../prototype/#motion",
                "reduced_motion_recipe": {"kind": "fade_out" if outgoing else "fade_in", "easing": "linear", "duration_ms": 100, "distance": 0, "scale_from": 1},
            })
    (ROOT / "motion" / "catalogue.json").write_text(json.dumps({
        "catalogue_version": 1,
        "role": "Authoring sidecar only; not a new Motive runtime schema",
        "source": "Actual PackAnimation values; each references a valid scene and layer",
        "patterns": entries,
        "scene_transition": {"purpose": "Pause bridge", "target": "brb scene selected by user", "transition": {"kind": "fade", "duration_ms": 350}, "reduced_motion": {"kind": "cut"}, "compatibility": "H9 scene_transition; separate from PackAnimation"},
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Indexed {len(entries)} real pack animation definitions")


if __name__ == "__main__":
    main()
