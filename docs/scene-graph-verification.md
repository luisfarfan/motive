# First scene editor — implementation and real verification

Date: 2026-11-16. Apple M5 Pro, macOS 27.2, development build, OBS 33.0.1.
This extends the existing GPUI/libobs application. No mock renderer, public
transmission, proprietary assets or REA dependency was introduced.

## What works

One shared `Production` owns the scene graph and native engine. Scenes contain
layers that reference reusable visual sources: window, camera, owned pattern
or owned animated overlay. Position, contain rectangle, visibility and order
are stored independently for landscape and portrait. Stable IDs survive save,
process shutdown and explicit project restoration.

The v3 project migrates v1/v2 and rejects unknown fields, invalid references,
duplicate IDs, unbounded geometry and duplicate camera resources for one device.
Use `add_layer` to reuse that camera. Limits are 8 scenes, 16 sources, 32 layers
total, 64 KiB control/project input and bounded coordinates/dimensions. Higher
order draws above lower order; equal order is resolved by layer ID.

The GPUI editor exposes scene selection/creation, source addition/reuse, layer
selection, position/size increments, visibility, order and overlay accent color.
Unused sources can be explicitly released. All production edits use the same
commands as CLI and MCP. MCP exposes 26 tools; it transports neither video nor
arbitrary filesystem paths. The existing local socket restrictions remain.

Geometry, order and overlay color work during recording. Source/layer creation
and removal, scene selection and visibility changes require a stopped output.
The legacy owned-overlay visibility command retains its live behavior.

## Defects and stability work

- **Unrelated recovery acknowledgement:** reproduced by terminating an owned
  external window during recording, then selecting different audio. The old
  boolean cleared although the window was missing. Recovery now tracks source
  IDs separately from audio/output. The real H1 regression checks this sequence.
- **Cold-source readiness:** health previously read native state twice, allowing
  a ready result with a stale zero-frame camera counter. One snapshot now drives
  the reported issues. Native health follows the committed scene's visibility,
  including sources awaiting asynchronous activation.
- **Frame-age underflow:** a frame arriving after the observation's clock sample
  could yield an enormous unsigned age. The observation now reads time after
  reading the arrival timestamp.
- **Camera lifecycle:** reconnecting while an old capture session still existed
  produced a CoreMediaIO/AVFoundation crash on this Mac. Camera replacement now
  detaches its layers, releases the old session and waits for OBS destruction
  before opening the same device. Failed reopening leaves the source explicitly
  unavailable; its identity is retained. A device is represented by one resource.
- **Output finalization:** OBS emits its stop signal before its internal end
  thread necessarily clears `active`. The engine waits for both conditions
  before exposing completion and disconnects the callback before releasing the
  output/encoders. Failed starts discard only empty reserved files.
- **Output recovery:** terminating only Motive's mux helper produces structured
  `OUTPUT_FAILED`, output code `-8` in this run and latched recovery. Changing
  audio cannot clear it. Explicit reconnection/reset permits fresh recordings;
  output never resumes automatically. A failed file is retained as evidence,
  without claiming it was finalized successfully.
- **Preview:** sequence is checked before allocating/copying a Rust frame.
  Existing GPUI image release remains in place. No zero-copy redesign or
  speculative codec change was made.

## Acceptance evidence

`scripts/verify_scenes.py` uses the real stdio MCP adapter for every production
mutation. CLI independently observes the same PID/revision. It starts an owned
animated AppKit window and uses the explicitly selected built-in camera; no
personal application window is selected. FFmpeg decodes the produced MKVs.

| Required journey | Evidence |
|---|---|
| Two simultaneous visual inputs | External ScreenCaptureKit window + AVFoundation webcam in one recorded composition; live camera frame counter and nonempty camera region |
| Secondary position and size | Webcam moves from `(640,32), 288×162` to `(600,48), 320×180` during recording; camera counter continues rather than restarting |
| Editable recorded overlay | Accent changes mint → coral; rectangle changes from `(32,436), 320×72` to `(60,420), 400×90`; decoded pixel regions verify both |
| MCP changes reflected in UI | Read-only native AX/screenshot inspection showed scene `Window + camera · MCP`, webcam `(600,48) 320×180 z2`, overlay `(60,420) 400×90 z3` and the composed preview |
| Save/close/open/recover | Graceful `shutdown`, socket and process exit, new PID, `load_project`, exact project/ID/layout equality, then another valid recording |
| Recording and regressions | Extended three-layer recording, order/visibility recordings, repeated recording after muxer failure, original H1 and horizontal/vertical/loopback checks |

Order is checked with two overlapping, differently colored owned overlays.
Moving the upper layer below the window changes the decoded pixels; hiding it
also exposes the expected lower overlay. Portrait edits are asserted not to
change landscape transforms. A second scene reuses the window source and can
be selected/removed without duplicating the capture resource.

Final observed results: the three-layer file is **66.033 s / 1,981 video
frames**, H.264 + AAC, decoded without errors. After reopening, the restored
composition recorded **3.133 s / 92 frames**. The muxer-recovery run completed
three camera reconnections and three subsequent files of **2.100, 2.100 and
2.133 s**, each with 62 video frames. H1's physical-camera/microphone file is
**8.500 s / 255 frames**, with non-silent decoded audio (RMS 0.09649).
The final original regression also passed: horizontal **65.700 s / 1,968
frames**, portrait **4.166 s / 123 frames**, and local loopback **5.021333 s /
150 frames**, with decoded H.264/AAC, non-silent audio and overlay motion.

Machine-readable local evidence (ignored by Git):

- `var/evidence/scene-acceptance.json`: RPC requests/replies, media paths,
  decoded pixel checks, source counters, restored state and process samples.
- `var/evidence/output-recovery.json`: real helper termination, error latch,
  per-camera reconnections and three new decoded recordings.
- `var/evidence/h1-acceptance.json`: integrated camera/microphone, real external
  window loss, audio-change regression and recovery.
- `var/evidence/acceptance.json`: original 65-second regression, portrait,
  non-silent AAC and loopback receiver.
- `var/evidence/control-integration.json`: protocol, strict nested arguments,
  shared state and continued rendering after MCP disconnect.
- `var/evidence/scene-ui-observation.json`: recorded read-only UI observation;
  the native screenshots were inspected in the working session.
- `var/evidence/scene-tests.log`, `scene-clippy.log`, `scene-bundle.log`:
  unit/build checks. All six original unit tests remain; there are 11 now.
- `var/evidence/scene-build-identity.json`: executable/source hashes and signature
  check outcomes; `scene-final-state.json`: idle studio with pattern, overlay,
  no audio and no camera/window resources left allocated by the tests.
- `var/evidence/recovery-audio-before.json`,
  `scene-hidden-window-after-reopen.json` and `scene-crash-reconnect.ips`:
  retained failures, not substituted with passing screenshots.

Recordings, camera images, device IDs and crash reports stay local. The UI
inspection was read-only; no automated clicks controlled production, and no
internal project files were edited to configure the tests.

## Reproduce

Build and launch the signed development bundle as described in README. Use
normal camera/microphone/screen permissions. Begin idle with a default project
and no other `MotiveFixture` instance (duplicate titles intentionally prevent
ambiguous restore). Choose physical UIDs from `devices` only with permission:

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/verify_control.py
python3 scripts/verify_h1.py --camera-id 'CAMERA_UID' --microphone-id 'MICROPHONE_UID'
python3 scripts/verify_scenes.py --camera-id 'CAMERA_UID' --seconds 65
python3 scripts/verify_output_recovery.py
```

`verify_scenes.py` cleans up captured sources through the core. `--leave-open`
keeps its composition/fixture available for read-only UI inspection and for
testing camera reconnection with `verify_output_recovery.py`. Release those
sources and close that fixture afterwards. The output test deliberately signals
only the mux helper whose parent is the observed Motive PID. Do not run these
scripts concurrently against one production.

For the original regression, open the owned GPUI fixture with
`ctl '{"op":"set_test_window","open":true}'`, then run `scripts/verify.py`.
It sends only to the fixed local UDP receiver. Source selection and saves in
these scripts replace the current test production; use a disposable project.

## Preview measurement and real limits

The callback still copies BGRA into one latest-frame buffer; GPUI copies only
when the sequence changes, then uploads a new image. At 960×540 a BGRA frame is
2,073,600 bytes. The report records both rendered frames and preview copies so
these costs can be inspected independently. CPU/RSS samples include capture,
software x264 encoding and UI in the app process; they exclude the mux helper
and other system processes. No capture-to-display latency or isolated preview
CPU benchmark is claimed, and no before/after speedup is inferred.

During the final three-layer recording, app CPU median/max was **51.65/56.2 %**
and RSS ranged **428.8–446.2 MiB**. Across a 61.66-second sample interval, libobs
rendered 1,850 frames and GPUI copied 1,769 (28.69 copies/s). That corresponds
to about 59.5 MB/s of pixel payload for the Rust copy alone, calculated from
frame size and count, not measured memory bandwidth. There were 5 busy-buffer
preview drops, zero added lagged render frames and zero output-dropped frames
in that interval. These are separate counters; they do not establish zero
loss or latency across every stage. A prior run's RSS fell after warm-up;
neither short run constitutes a memory-leak or long-duration soak assessment.

- Built-in camera and microphone were exercised. Physical USB/Continuity
  hot-unplug, sleep/wake, hour-long sessions and other Macs/macOS versions were
  **not** exercised.
- A passthrough async filter watches camera delivery (4-second activation grace,
  then 3 seconds without a frame is a stall). Real arrivals and reconnects were
  observed; an intentionally stalled hardware camera was **not** tested. Static
  content with arriving frames is healthy.
- Window permission, existence, owning PID and initialized dimensions are
  checked. A live window whose last texture remains frozen is **not reliably
  detected** by this implementation; pixel equality would misclassify static
  content. This remains a known stability limit.
- Stage Manager can leave a restored hidden window at `CAPTURE_NOT_READY`.
  The test normally activates its owned fixture after reopening Motive; no
  permission workaround or global setting change is used.
- Sources remain allocated while referenced by the project, even if no active
  layer shows them. Removing a layer does not promise to turn off a camera;
  explicitly release the unused source or close Motive.
- The editor uses buttons/increments, not canvas dragging or numeric text
  fields. Overlay text, images, transitions, effects and simultaneous canvases
  are not implemented. One audio selection and one output remain.
- The development bundle still depends on this checkout's `.deps/`, local
  signing and software encoders. Normal bundle/executable signature verification
  passes; `codesign --verify --strict target/Motive.app` rejects the external
  framework symlink (`invalid destination for symbolic link in bundle`). It is
  not a notarized or self-contained distributable release.

Next increment: direct numeric layer editing and selection feedback, alongside
removable-device/sleep-wake tests before permitting live scene/device changes.
Retain the current renderer until profiling identifies a concrete bottleneck.
