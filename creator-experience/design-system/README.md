# Creator Experience visual system

This handoff extends the approved Motive language in `design/direction.md` and the read-only Claude Design Phase 1 boards. It does not edit those boards or claim new Claude approval. The control room stays light; only the image stage and its thumbnails are dark. Flat controls, thin dividers, system typography and one raised preview preserve Motive's hierarchy. This folder is a design reference, not a second application theme implementation.

## Two original collections

| Decision | CREATOR TECH | NEON ARENA |
|---|---|---|
| Content identity | Thoughtful, editorial, precise | Expressive, social, geometric |
| Palette | Ink, parchment, quiet mint | Midnight, violet, acid lime |
| Signature | Stacked isometric engineering plates | Receding angular portal with asymmetric light traces |
| Composition | Large left-aligned titles and breathing room | Strong title plus one luminous focal object |
| Frames | Fine perimeter and technical registration corners | Clipped corners and asymmetric luminous segments |
| Motion | Short travel, gentle scale, linear fades | Larger bounded scale and travel; no flashing or perpetual loops |

The original artwork is generated from editable vector primitives in `packs/tools/generate.py`. Each transparent PNG has a matching editable SVG in its pack's `assets/source/`. Colors in those PNGs are authored pixels. Editing native `shape_color` does not recolor a PNG or a widget. No logo, stock image, photograph or commercial font is copied; Helvetica/Menlo are runtime font requests, never redistributed files.

## Composition and adaptation

All manifests use logical 960×540 or 540×960 positions. Production H13 scales them to the configured output; packs do not contain 1080p layer coordinates. Main text has explicit line breaks. Source text is a single contained block with no word wrapping; resize or shorten a long personalization in both orientations.

Background rectangles stretch, as implemented by `native/graph.inc`. Every other source contains its intrinsic ratio inside centered layer bounds. A 16:9 frame therefore remains 16:9 in portrait; it does not become a portrait crop. Empty camera/game regions really are empty. Capture choices and any crop support must come from the application contract later.

Scene-specific Starting, BRB and Ending titles use separate sources. Identity, countdown, lower third and alerts are shared intentionally. The shared countdown is titled neutrally and retains its timer state across scene switches. Reset does not happen implicitly.

`tokens.json` records palettes, sizes, geometry and measured sRGB text contrast. Small identifiers are supplementary; the main title and lower third carry the meaning. Review native font metrics later: the independent renderer approximates FreeType positioning, contains text using estimated advances, and illustrates activated widgets. It does not establish pixel parity with libobs.

## Review conducted

The generated 1440×1120 contact sheet of each pack was inspected, including all six scenes in both orientations. Corrections retained in the final generator: visible inset portal lines, in-canvas Gameplay bounds, legible lower thirds, uncluttered resting live scenes and a camera identifier separated from the top frame. Event overlays are demonstrated in dedicated alert previews. Contact sheets label their authored, disconnected status.

This is a design review of original PNG studies. Device captures, native rendering, actual animation cadence, font fallback, full VoiceOver review and H14 installation remain outside the evidence. Color contrast does not by itself prove accessibility.
