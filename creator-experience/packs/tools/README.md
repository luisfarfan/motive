# Original artwork and pack generator

Run `python3 packs/tools/generate.py` from `creator-experience/`. Python stdlib orchestrates the offline generator; Swift/AppKit renders local vector primitives to PNG. No dependency download, server, browser, capture API, application launch, native Motive test or global configuration change is involved.

The script generates strict manifests, catalog/migration/recipe sidecars, editable SVG asset sources, transparent PNG assets, twelve composition previews and two alert previews per pack, and contact sheets. All outputs stay under `packs/`. Swift's module cache is directed to `tools/.build/module-cache`. Temporary `render-jobs.json` contains absolute local paths while rendering and is removed on success; it is never a distribution artifact.

The drawable descriptions are common to the SVG and PNG outputs. AppKit and browser typography have different metrics, and neither is native libobs/FreeType evidence. SVG previews embed the generated PNG assets for portability. The script no longer needs an absolute checkout path or sibling application fixture: an extracted `motive-packs` tree can retain this directory unchanged. The copied GPL text is in `LICENSE.txt`.

No font binaries or third-party media are included. Only the transparent PNGs named in a manifest's `resources` list are proposed importer inputs; SVGs, scripts, previews and sidecars are authoring/documentation material, not executable pack payload.
