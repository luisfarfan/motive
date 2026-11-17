# Native UI architecture

Baseline: 7280c5c. Worktree: motive-ui, branch codex/ui-evolution. No H10 code
is imported. Claude Phase 1 remains the visual authority; Phase 2–5 designs are
not published. No engine, project-v3 or profile-v1 changes are planned.

## Audit and boundaries

The original 1,190-line Studio mixed the owner loop, rendering, device inventory,
output actions and six unrelated popovers. The 724-line editor mixed pure
geometry with GPUI focus/gesture handling. Read-only status commands were also
used repeatedly during render. Input entities already had stable identity and
must remain outside render; Production remains the only authoritative state.

- `studio/mod.rs`: sole Production/socket owner, polling and command dispatch.
- `studio/workspace.rs`: native layout composition.
- `studio/chrome.rs`: title bar and common popover lifecycle.
- `studio/scenes.rs`, `sources.rs`, `audio.rs`: cohesive feature presentation.
- `studio/panels.rs`: panel routing; feature forms are separated as they grow.
- `editor/mod.rs`: focus, drafts, undo and one commit per gesture.
- `editor/geometry.rs`: pure hit testing, snapping, resize and number conversion.
- `components.rs`: stateless composition over native Kit controls.
- `theme.rs`: semantic colors and shared dimensions.

This is module composition within a single GPUI entity, not a service/event-bus
framework. Stateful Kit Inputs retain Entity<InputState>; simple view helpers
return elements. Feature modules only submit typed core Commands. No duplicate
Scene Graph or multimedia clock exists.

Pinned GPUI Kit/component 0.10 source is the implementation reference; current
upstream docs confirm Entity ownership and RenderOnce composition:
https://github.com/longbridge/gpui-kit/blob/main/website/docs/entity.md
https://github.com/longbridge/gpui-kit/blob/main/website/docs/render-once.md

## Increment 1

Mechanical module extraction, identical operation bodies. Pure geometry tests
remain in their own module. 24 tests and production Clippy pass. Native execution
is pending the existing H10 physical-test lock; no second Motive was launched.
This environmental gate does not justify weakening native acceptance tests.

## Increment 2 — native management

Native scene rename and configurable Fade, profile creation/selection/save/load,
loopback RTMP configuration and preflight ran through GPUI and were corroborated
through MCP. Actual H.264/AAC reached the local FFmpeg receiver. Two native QA
failures were retained and fixed: plain Kit Dialog needs an explicit footer;
a popover must close before opening its confirmation dialog to avoid overlap.
A stale profile draft after an MCP revision was rejected without changing bitrate.
26 unit tests and production Clippy pass. Runtime evidence is in ignored
`var/evidence/ui-evolution/`. Full regression run follows final integration.

Forms are revision-bound drafts. Profile lists are query snapshots; selecting
Edit reloads the profile from the shared core. Panel identity is an enum.
Confirmations capture the revision and reject stale intent. Components include
Kit button styles, property groups, numeric/text inputs and a real peak meter.
Editor geometry and canvas rendering are separate. Appearance/safe-margin
preferences have a strict local UI-only v1 schema; no multimedia state is stored.
