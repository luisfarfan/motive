# Native UI architecture

Baseline: 7280c5c. Worktree: motive-ui, branch codex/ui-evolution. H10 was subsequently merged and verified in main at 0370ca4. Its three complete
commits (076b6c2, ec1b00c, 6e76820) were imported as complete checkpoints; no
partial engine integration. Claude Phase 1 remains the visual authority; Phase
2–5 designs are not published. UI work does not change the engine or the
project-v3/profile-v1 contracts.

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


## Increment 3 — H10 presentation

The mixer joins stored inputs and native runtime meters by stable ID. It owns
only Kit Slider entities, pointer focus and revision-bound gesture drafts; gain,
mute, devices, recovery and persistence remain H10 Commands. Release commits one
command. Keyboard changes use Kit's step/release behavior. Native pointer focus
needed a small adapter: Kit 0.10 does not focus its thumb on mouse-down. A real
regression moved a selected layer when pressing Left after clicking a fader;
the adapter now keeps arrows in the fader, verified against both gain and X.

Two real inputs, mute/master silence, disconnect/reconnect and mixer restore
were verified in GPUI and through MCP. A GPUI-started/stopped VT recording decoded
542 H.264 frames with AAC. Native forms also exercised create/remove scene,
source reuse/release, overlay RGB, Fade/cancel and exact X=64.125. Query profile
lists refresh after UI and MCP mutations without overwriting open drafts.
30 unit tests and Clippy pass; final media regression evidence follows.


## Capability map and ownership

| Surface | Shared commands / state | UI-owned presentation |
| --- | --- | --- |
| Scenes | create/rename/remove/select; configure/cancel transition; transition status | Selected row, native name/duration drafts |
| Sources/layers | add/reuse/remove; transform, visibility, order, overlay RGB; reconnect | Selected ID, picker choices, bounded transform history |
| Canvas | Active graph and variant, real libobs frame | Geometry, provisional outline/guides, numeric fields |
| Profiles | query/upsert/remove/select/save/load, preflight | Revision-bound profile draft and read-only list snapshot |
| RTMP | configure loopback endpoint, preflight/start/cancel/stop/recover | Transport/port draft; actual lifecycle text and stats |
| Credentials | opaque reference selection and access query | Reference draft only; no secret entry or storage |
| H10 audio | ID-keyed registry/runtime; add/gain/mute/disconnect/reconnect/remove/save/load | Kit faders, pointer focus, release revision |
| Preferences | No multimedia mutation | Explicit UI-v1 theme/safe-margin file only |
| Agent status | PID/revision/last action from shared Production | Display only; no invented proposals |
| Recording result | Core-owned last output path and encoder state | Display only; no arbitrary filesystem browsing |

The reusable library deliberately uses composition functions, not a new class
hierarchy: themed Kit buttons, rows/columns, labels/status dots, audio meters,
property groups and labelled inputs. One popover shell handles sizing/scrolling,
close, drafts and stale-state notices. One revision-bound confirmation handles
structural deletion, restore/overwrite and output stop. Scene/layer/device views
remain cohesive feature methods because each has one production use site.
Numeric fields use persistent Kit entities and the existing pure geometry tests.

Semantic light/dark colors and shared control/type dimensions live in theme.rs.
Stage geometry and one-off feature dimensions remain close to their layout;
there is no justification for a token per numeric constant. Kit owns focus rings,
menus, dialogs, inputs and slider/accessibility behavior. Layout remains macOS
native at 1440×980 and 1024×780; channels and scenes scroll independently.

## Final architecture audit

- The original Studio monolith is split into feature modules (roughly 68–301
  lines each); the owner module is 208 lines. Editor event/undo handling is 445
  lines, separated from canvas drawing and pure geometry. No dependency cycle,
  second Production, mixer, Scene Graph, output policy or renderer was added.
- Drafts/confirmation intent preserve the originating revision. MCP refreshes
  the live profile list and meters; it does not silently rebase an open draft.
  A stale gesture/form is rejected. Transform undo is local and deliberately
  invalidated by structural/remote changes; it does not claim to undo all actions.
- Removed the unreachable legacy single-input audio picker once H10 became the
  only UI mixer flow. CLI compatibility remains the engine owner's concern.
- The 33 ms owner pump, bounded request draining, one-second device/health poll
  and CPU-copy preview remain unchanged. Faders/dragging commit on release.
  No performance improvement is claimed. JSON status and per-frame presentation
  allocation remain measurable future profiling topics, not speculative fixes.
- Accessibility checks cover actual AX names/roles, keyboard focus, native
  inputs, buttons and sliders, and pointer-to-keyboard transitions. This is not
  a full VoiceOver audit or certification. Device labels truncate visually but
  retain full native names. High channel counts scroll; only two physical/test
  channels were visually exercised on this Mac.

## Explicit gaps for the next owner

- Source/layer and mixer-input renaming have no shared rename command. Scene
  rename is implemented. Inactive scene/per-layer previews need engine support;
  the UI explicitly shows no preview rather than inventing images.
- A recordings library needs a typed core list/inspect/reveal contract with
  opaque output IDs and containment under the approved recording directory,
  plus an approved screen. The UI currently exposes the real last file only.
- Secure secret registration/replacement/deletion stays in the local Keychain
  helper. A native flow needs an OS-authorized secure-entry contract; ordinary
  text fields are inappropriate. Public destinations remain prohibited.
- Agent proposals need stable proposal IDs, base revision, typed operations,
  validated preview/diff, explicit accept/discard, and a core-owned inverse with
  revision/ownership preconditions. Current MCP commands execute directly and
  the UI reports their real result. It does not manufacture approval/history.
- H11 now provides typed core contracts for text, managed images/video, shapes,
  widgets, animations and presets through CLI/MCP. Its GPUI adapter is pending;
  see the [overlay contract](h11-overlay-ui-contract.md). The current source list
  labels these as legacy graphics; the legacy color command is safely rejected
  with `USE_OVERLAY_PROPERTIES` for H11 definitions.
- Output resolution/FPS, monitoring, audio filters/system audio, multi-output,
  AI generation and extra Phase 2–5 screens remain outside current contracts.
  No fake toggles were added. The UI is usable for the implemented studio flows;
  it is not the completed Motive Design System.
