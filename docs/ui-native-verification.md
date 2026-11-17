# Native studio UI — UI-0 through UI-3

Historical checkpoint (7280c5c). Current UI modules, H10 integration and native
configuration are documented in [UI evolution verification](ui-evolution-verification.md).

This increment translates the approved Phase 1 studio into GPUI Kit 0.10. It
starts from H9 (`bd23c63`), with `design/direction.md` as the provisional token
source. Claude's files, the multimedia engine, project v3 and the CLI/MCP
contracts are unchanged. H10 Audio Mixer remains a separate worktree/task.

## Implementation

- `src/ui/theme.rs`: light/dark room and stage palettes, native system typography.
- `src/ui/components.rs`: GPUI Kit button styles and small layout helpers.
- `src/ui/studio.rs`: native title bar, real preview, scenes, layers, contextual
  popovers, device selection, output/capture state and the existing audio meter.
- `src/ui/editor.rs`: selection, numeric fields, transform drafts, snapping,
  keyboard controls and guarded transform undo/redo.
- `src/ui/fixture.rs`: the existing native controlled capture window.

`Studio` still owns exactly one `Production` and the existing control socket.
Every production edit uses `Command`; preview pixels and meters come from that
owner's libobs engine. The editor stores only the selected ID, field/gesture
**drafts**, and a bounded undo history, never an authoritative graph copy.

## Editing contract

Canvas coordinates come from the actually laid-out program rectangle, including
letterboxing. Cut/Fade scene selection continues through H9. Horizontal and
vertical transforms remain independent.

Dragging displays a provisional outline; release submits **one** `SetTransform`.
The program remains at the committed transform during the gesture. A controlled
20-command MCP experiment measured a 35.40 ms median / 42.22 ms maximum roundtrip;
21 changes including restoration built 21 scenes. That includes the existing
33 ms command pump and is **not** an isolated native-render benchmark.

Corners preserve aspect ratio; Shift permits independent dimensions. Side
handles change one dimension. Move snaps to canvas edges/centers and 32-pixel
safe margins; Command disables snapping, Shift constrains the dominant axis.
Arrows move 1 pixel, Shift+arrows 10. Command+[ / ] changes order. 1–9 selects
scenes; Command+Z / Shift+Command+Z undo/redo compatible transforms. Shift+S
shows the safe margin. Enter commits a numeric field; Escape discards a draft.
Command+S saves the project. Native Kit inputs/popovers provide tab navigation.

Undo/redo and draft commits require the same scene, variant, layer, transform
and core revision. A concurrent MCP/CLI mutation invalidates the local history
rather than overwriting the newer state. This history is session-local, covers
transforms only, and is capped at 100 entries.

## Verification status

Verified locally on 2026-11-16. **All 17 existing real-media suites passed**
after the two retained failed attempts described below. The successful cases
sum to 426.27 s, excluding restarts, failed attempts and manual interaction.
Existing H1–H9 scripts and assertions are unchanged.

`scripts/verify_ui_regressions.py` archives reports and their hashes under
`var/evidence/ui/regressions/manifest.json`. It requires the shared physical-test
lock and explicit camera/microphone IDs; it performs no public transmission.

| Existing checks | Result |
| --- | --- |
| H9 transitions and transition faults | Pass: actual recording/RTMP, shared webcam, cold window, cancellation, restore |
| Shared control and fragmented/delayed delivery | Pass |
| H1 physical camera/microphone and source recovery | Pass; physical hot-unplug limits remain unchanged |
| Scene Graph | Pass: simultaneous captures, transforms, overlay, order, visibility, persistence |
| Base media acceptance | Pass: sustained recording, vertical composition, UDP loopback |
| x264/VideoToolbox, fallback, output recovery | Pass |
| H7 RTMP, RTMPS negative, connect-stop, VT stop, profile restart | Pass; no positive RTMPS certification |
| H8 lifecycle and Keychain | Pass |

Full-media-suite bundle SHA-256:
`3ec15785fce6472bf724cf56c34f5a9f5b28799fd94f3b79284d7031179a744f`.

After that run, the only production-source change was the numeric text formatter
in `editor.rs`: preserve round-trippable f32 text instead of rounding to two
decimals. Final bundle SHA-256:
`a81a2324f799036f46fb534a2e98829b9ed2d308ae80b277f6bdd93310e1ae94`.
That bundle passed **24 unit tests**, production Clippy with `-D warnings`, fmt,
shared control/delivery retests, native input interaction and a decoded 92-frame
H.264/AAC recording (34 ms maximum interior timestamp gap, RMS 0.06299).
The complete 17-case media run was not repeated for that isolated formatting
change. `precision-retest.json` verifies X=64.125 and an unchanged revision after
focusing the field and pressing Enter; `final-bundle-recording.json` records the
exact delivered binary's media check.

Hash comparison of all 39 protected engine/contract/design/dependency files
matched the starting baseline. The application was closed and the physical-test
lock released to the separate H10 task after validation. No push or release was
performed.

Native interaction evidence:

- Native 1440×980 and 1024×780 shell; real preview; light/dark and recording.
- Canvas selection; numeric X edit; move and aspect-preserving resize.
- Undo/redo, MCP update reflected in fields, and rejected stale undo.
- Snapping to exactly X=32/Y=32 and visible safe-margin guides.
- Editing during a continuous 673-frame H.264/AAC recording: 34 ms maximum
  interior timestamp gap; complete decode; audio RMS 0.0630. Native sources
  and output were not restarted by a gesture.
- A source added in the native popover appeared in the same MCP graph.
- X=64.125 retained its f32 value in the core. The final formatter uses the
  shortest round-trippable f32 text, avoiding quantization on an unchanged Enter.
  NaN was rejected without a graph revision; keyboard focus has a visible ring.
- Connection refusal and a silent loopback peer produced real error, connecting
  and cancel-pending states. The banner's recovery action returned to idle.
- Closing the owned source window marked its row “Sin señal”, showed the warning
  and disabled recording. A recording-time loss also finalized the real file.
- 24 unit tests and production Clippy passed on the final source.

Real UI failures were corrected during verification: row clicks stole input
focus; an absolutely positioned measuring canvas inherited a position after the
image. The corrected input focus guard and `inset_0` measurement were retested
with actual native input and a decoded recording. The final pass also fixed a
low-contrast recovery button and an idle header that incorrectly said “Listo”
when the core already reported a capture issue. Initial artifacts are retained.

### Measured real-media samples

These are process samples from a debug build, not a before/after UI performance
benchmark. H9 uses its existing process CPU sampler; the base and scene tests use
`ps`. Samplers and scenes differ, so rows are not interchangeable comparisons.

| Scenario | Decoded frames | Median process CPU | RSS range | Output result |
| --- | ---: | ---: | ---: | --- |
| 65 s controlled native-window capture | 1,973 | 30.3% | 164.3–179.7 MiB | H.264/AAC, 65.833 s, overlay animated |
| H9 recording with webcam and scene changes | 501 | 42.27% | 222.2–303.2 MiB | 34 ms max interior PTS gap; zero output drops |
| H9 loopback RTMP with scene changes | 504 | 49.36% | 228.7–234.4 MiB | 34 ms max interior PTS gap; zero output drops |
| Window + webcam + editable overlay | See `scene-acceptance.json` | 48.2% | 298.5–303.0 MiB | Recorded pixels, order, visibility and restore passed |

The base vertical file decoded 122 frames at 540×960. Its loopback UDP receiver
file decoded 150 frames. Test-tone RMS was approximately 0.063, consistent with
the existing fixture. No render-lag frames occurred in the two H9 sequences.

### Retained failed run

The first final-bundle H9 run hit `SCENE_PREPARATION_TIMEOUT` for the cold
external fixture after repeated preparation cancellation. The old program and
recording remained active; there was no crash. The complete failure is retained
in `var/evidence/ui/regressions-failed-01/`. One clean process restart and rerun
passed the unchanged suite in 47.15 s, including cold-source activation, actual
Cut/Fade pixels, shared webcam continuity, RTMP and project restore. No timeout
was increased and no native code was changed. This is an observed intermittent
capture-start limitation, not evidence that its underlying cause was fixed.

The first scene-graph run also reported `SOURCE_UNAVAILABLE` for the owned
external window after capture had started; the existing safety policy finalized
the recording. Its report is retained in `regressions-failed-02/`. The unchanged
suite passed after a clean restart (33.28 s). Stage Manager/window visibility is
an environmental sensitivity already noted by the existing test, but the cause
of this particular disappearance was not established. Neither failure is hidden
by changing readiness thresholds or weakening assertions.

## Reproducing the checks

Use the normal signed bundle workflow from README. Do not replace a running
bundle. Reserve `var/run/physical-test.lock` for this task before using capture
devices; the companion runner expects its OWNER to begin `UI task:`.

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt --all -- --check
python3 scripts/verify_ui_regressions.py \
  --camera-id '<authorized device UID>' \
  --microphone-id '<authorized device UID>'
```

For compact visual QA, launch the bundle with `MOTIVE_UI_SIZE=1024x780` via
`open -n --env MOTIVE_UI_SIZE=1024x780 target/Motive.app`. The normal window is
1440×980. Compare at 1× logical pixels, without changing macOS display settings.

The interactive check uses the pattern and animated overlay, then a controlled
native window; no prototype image is substituted into the preview:

1. Select the overlay on the canvas and in the layer row. Enter X=64.125; query
   `scenes` through CLI/MCP and confirm the stored value. Try NaN and confirm no
   revision change. Tab through controls and check the blue focus indicator.
2. Move and resize the selection while recording a test tone. Check one revision
   per completed gesture, aspect ratio on a corner, numeric dimensions, undo and
   redo. Decode the recording with ffmpeg and inspect timestamps with ffprobe.
3. Make an MCP `set_transform` change after an edit. Confirm fields/preview
   reflect it and Command+Z cannot overwrite that newer revision.
4. Snap to X=32/Y=32; toggle Shift+S. Test both canvas variants independently.
5. Close the owned capture window. Confirm warning, source status and disabled
   recording; restore the pattern through the shared command and save.
6. Use a loopback-only silent receiver. Cancel from the UI and observe
   “Cancelación pendiente” until libobs releases the connection. Recover a
   refused connection explicitly. Never use a public endpoint for this test.

Archive a failed attempt before resuming with `--from-case <name>`. Resume
requires the same bundle hash and successful reports for every preceding case.

Media, private device IDs, screenshots and raw process metrics remain in ignored
`var/evidence/ui/`. `design-qa.md` records the paired reference/native comparisons.
The runner preserves the existing scripts and produces a bundle-hashed manifest;
manual gesture checks are not represented as automated tests. A pre-existing
`clippy::field_reassign_with_default` warning in `src/output.rs` affects Clippy's
all-targets mode; the production target passes `-D warnings` unchanged.

## Deliberate limits

- Only the active scene has a real thumbnail. Inactive scenes explicitly say
  “Sin vista previa”; there is no second renderer or invented scene image.
- H9 supplies one global `audio_peak` value. The UI displays one peak meter in
  dBFS, not simulated stereo channels, faders or a system-audio source. H10's
  per-input mixer is intentionally not integrated in this branch.
- Recording and a configured local RTMP output share the existing single-output
  policy. Endpoint/profile configuration remains CLI/MCP; this screen does not
  enable public destinations or transport secrets.
- No agent proposals, fake CPU readings, measured-FPS claims, text-overlay
  generator, live layer thumbnails or additional Phase 2–5 screens.
- Unused sources can be released through CLI/MCP `remove_source`; the current
  layer menu removes the layer only.
- Theme choice is session-local. Undo covers canvas, numeric and keyboard transforms. Visibility/menu actions
  and structural changes invalidate that history and are not undoable.
- Hardware/RTMPS/VideoToolbox limitations in H1–H9 remain applicable. UI work does
  not certify untested capture devices or resolve the intermittent VT tail gap.

The next UI increment should integrate the independently verified H10 contract
when it is merged, then use Claude's published foundations for additional
screens. It should not implement a second audio policy in GPUI.
