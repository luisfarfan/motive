# NEON ARENA — Play Together

Version 0.2.0 · GPL-3.0-or-later · Motive contributors.

An angular, luminous collection for games, rewards and shared moments. Original geometric assets, native editable typography and six compositions in both design960 orientations. This extends the existing neon-arena fixture, retaining its collection identity and relevant source/animation symbols; it does not overwrite the original.

## Deliverables and truthful status

- `manifest.json`: exact CreatorPack v1 schema; 6 scenes, 12 reusable overlay sources, 27 total layers, 12 animation definitions and 12 properties.
- `assets/`: two transparent PNG resources with original editable SVG sources and provenance. No customizable text is baked into an asset.
- `previews/`: twelve SVG/PNG composition studies generated from the manifest. They approximate native typography and illustrate widgets after show/trigger; lower thirds and alerts are hidden initially in Motive. Empty frames are genuinely empty. These are not recordings, real captures or native acceptance evidence.
- `deck.json`, `rules.json`, `events.jsonl`: typed manual event examples and disabled provider rules. No platform connection, credential, script, sound or code execution.
- `recipes.json`: explicit capture slots for later user selection; captures are not included in the manifest.
- `metadata.json`: catalog information kept outside the strict native manifest.
- `migration-from-0.1.json`: explicit symbol/definition changes for a future reviewed update; no automatic in-place migration.

Validation reports: [asset/geometry gate](../../evidence/contracts-validation.json) and [authoritative Rust contract](../../evidence/contracts-native.json). These reports describe the last independently executed check, not a claim embedded in the manifest.

Native integration is pending: the observed H14 installer supports embedded MATCHDAY and rejects resource descriptors. These image-based packs validate as v1 proposals but cannot be installed by that observed installer. No installer is supplied here.

## Compositions

- Starting Soon: `previews/starting-horizontal.png` and `-vertical.png`.
- Gameplay: `previews/live-horizontal.png` and `-vertical.png`.
- Camera Focus: `previews/camera-horizontal.png` and `-vertical.png`.
- Community Interaction: `previews/community-horizontal.png` and `-vertical.png`.
- Be Right Back: `previews/brb-horizontal.png` and `-vertical.png`.
- Ending: `previews/ending-horizontal.png` and `-vertical.png`.

## Personalize safely

The 12 declared properties edit native text, widget title/subtitle and background shape color. A long title is contained as a block and does not automatically wrap: keep explicit newlines, review both orientations, and shorten text if it becomes too small. Widget palette, fonts, durations and images are not `set_property` targets in v1. Direct definition edits require the official inspector/owner validation and preserve source identity restrictions.

Every source is shared. Editing the presenter changes all presenter layers; starting, pause and ending titles have independent sources so edits do not corrupt other compositions. The countdown is shared between Starting Soon and BRB: scene change does not reset it. Its default is five minutes; Reset/Start must be deliberate. A counter in Show Control remains internal state, never implied as a live widget binding.

The pack reserves 4 source slots and 5 layer slots in an empty production. `recipes.json` shows optional capture layers. Existing projects and multiple packs require a fresh global capacity/budget preflight. Resources need authorized local staging and hash/decode verification by the official importer.

## Motion and operation

Declared Fade is linear; Slide/Scale use bounded native easing. Layer timing is 100–10000 ms. Reduced-motion recipes use immediate Show/Hide or Cut, not an invalid 0 ms animation. Widget appearance has its own native 300 ms behavior; source show/trigger and layer motion are distinct. Do not overlap multiple operations on one layer; wait for the owner acknowledgement. Four simultaneous animations is the authored budget, below the engine limit of eight.

Manual Deck rehearsal never changes Production. Provider rules are disabled until a trusted event adapter and user authorization exist. Source/layer/scene symbols must be resolved from official installer replies, never guessed.

## Reproduce

From `creator-experience/`: `python3 packs/tools/generate.py`, then run the independent validator described in `../../validation/README.md`. The generator uses Python stdlib and macOS Swift/AppKit, performs no capture and writes only within `packs/`. Run the independent validator before distributing changes. Source SVGs are design files, not accepted native resources. Widget and text rendering are approximations; exact native review remains pending.
