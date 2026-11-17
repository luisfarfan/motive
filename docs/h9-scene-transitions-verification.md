# H9 — Live scene switching with official OBS Cut/Fade

Verified on the development Apple M5 Pro / macOS 27.2 Mac, November 16, 2026.
One Production, one libobs video clock and one active output. GPUI, Claude's
Design System, the H8 RTMP patch and its build script are unchanged. No public
transmission, global installation, trust change, push or release.

## Implementation and lifecycle

`native/scene-switch.inc` uses the official `cut_transition` and
`fade_transition` sources from OBS 33.0.1's already loaded `obs-transitions`
module. The existing scenes and capture sources remain owned by the graph.
Selecting a scene no longer calls graph reconciliation: it neither rebuilds
scene items nor creates a camera, encoder, muxer, service or connection.

Output channel 0 holds an OBS transition. Changing transition kind uses
`obs_transition_swap_begin`, `obs_set_output_source`, then
`obs_transition_swap_end`, the official reference/texture transfer pattern.
`obs_transition_start(..., OBS_TRANSITION_MODE_AUTO, ...)` renders/times the
change. The stop signal publishes an atomic counter only; the existing owner
polls it and corroborates completion with the locked public
`obs_transition_get_source(..., OBS_TRANSITION_SOURCE_A)` getter before committing
the active scene ID and advancing the shared revision. OBS emits its stop signal
outside the state lock; a late notification from a cancelled operation alone
must not complete a subsequent transition. Neither
MCP nor a new worker marks the video clock. The existing owner polls health
once per second and before commands; preparation and reported completion can
therefore lag native frames by that polling interval without MCP traffic.

Before going on air, a cold target acquires a balanced `obs_source_inc_active`
reference. The previous program remains visible. Every visible target resource
must pass health checks; camera data must be recent (within 500 ms, and newly
observed for an off-air camera). A cold capture also waits two video ticks after
metadata/data readiness. Preparation has an eight-second deadline. The transition
acquires B before the temporary activation is released. Cut/Fade preserve the
existing native camera resource shared by both scenes.

A target-only failure during Fade cuts back to the previous scene, retaining
the output. Failure of the previous/shared on-air resource also rolls back,
then uses the existing source-health stop/recovery policy. Completion is checked
before outgoing-source health, so an already finished transition does not fail
because its retired source subsequently disappears. Rollback and graph exchange
hold the replacement tree active across reference changes. Graph edits are
rejected while preparing/running; otherwise their previous restrictions remain.

Failure results retain the exact source IDs/codes observed at failure. This was
necessary in a real run: a transient window-inventory rejection recovered before
the next status request, which previously produced an empty `blocked_sources`
array beside a failed result. The corrected code preserves that observation.

Audio remains the existing global channel 1. These visual transitions do not
crossfade microphones or add per-scene audio routing.

### Public source evidence

Research used official documentation and the checksum-pinned open source tree,
without REA or proprietary artifacts:

- [libobs transition API](https://docs.obsproject.com/reference-sources#transitions).
- [Transition implementation, OBS 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-source-transition.c): activation, reference ownership, stop signals, automatic time and swap APIs.
- [Source activation](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-source.c) and [scene ownership](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-scene.c).
- [Official Cut](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-transitions/transition-cut.c) and [Fade](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-transitions/transition-fade.c).

Pinned-source hashes are in `var/evidence/h9-research/pinned-sources.json`.
No renderer or downstream transition plugin was added. The H8 RTMP worker
lifecycle patch was inspected and retained byte for byte.

## Shared contracts

| Command/state | Contract |
|---|---|
| `scenes` | Read-only scene list, revision, current ID, configuration and native transition result |
| `configure_transition` | Typed `{transition:{kind:"cut",duration_ms:0}}` or Fade 100–5000 ms; rejects unknown fields/kinds and invalid ranges |
| `select_scene` | Selects an existing native scene, including during recording/RTMP; returns the operation state, not a promise that preparation has finished |
| `preparing` | Target warming off-air; previous ID remains current |
| `running` | OBS Cut/Fade in progress; current ID remains previous until completion; progress comes from OBS |
| `completed` | Destination committed to the project; progress 1 |
| `failed` | Previous scene retained, structured operation error and captured `blocked_sources` available |
| `cancel_transition` | Requires the current `operation_id`; preparation cancellation retains program, running cancellation explicitly cuts back; does not stop output |
| Repeated/stale requests | Same pending target is idempotent; a different target/configuration/graph edit returns `TRANSITION_BUSY`; stale cancellation returns `TRANSITION_OPERATION_MISMATCH` |
| Terminal cancellation / selecting current | No-op, preserving the last operation/result; does not rewrite a failure as success or rewind an already completed Cut |
| Shutdown | `request_shutdown` cancels a pending visual transition, then follows H8's output-quiescence rule; ordinary `shutdown` still requires idle/quiescence |

Status adds `transition_configuration` and `transition`, including operation ID,
phase, current/from/target IDs, kind, duration, progress, error and blocked sources.
Native source-instance and scene-build counters support lifecycle verification.
Revisions advance on operation/phase changes, not on every progress or metric
sample. Both CLI and MCP dispatch to the same Production used by GPUI. No UI
file changed and no simulated clicks control production. `scenes` is read-only;
`cancel_transition` has a destructive MCP annotation because it can cut program.

Cut selection while output is idle remains synchronous and allows empty/cold
scenes for editing. Live Cut and all Fade selections prepare the target; an
empty live/Fade destination returns `EMPTY_SCENE`. Saving a project during a
pending transition is rejected rather than persisting an ambiguous current ID.

Project v3 and source/layer IDs are unchanged. Only completed selections change
its active scene ID. Transition configuration is a session preference and resets
to Cut on reopening; it is not silently added to the v3 file or output profiles.

```sh
./target/debug/motive ctl '{"op":"scenes"}'
./target/debug/motive ctl '{"op":"configure_transition","transition":{"kind":"fade","duration_ms":1000}}'
./target/debug/motive ctl '{"op":"select_scene","scene_id":"SCENE_ID_FROM_SCENES"}'
./target/debug/motive ctl '{"op":"status"}'
./target/debug/motive ctl '{"op":"cancel_transition","operation_id":42}'
```

Use the actual operation ID returned by the selection, not the example token.
Operation IDs are scoped to the Production process; query its PID/state again
after reopening. Scene/source/layer IDs remain stable across project restoration.
There is no queued transition list, automatic retry, new renderer, second canvas
or new credential/egress path.

## Real acceptance results

`scripts/verify_h9_transitions.py` drives stdio MCP against the signed app. It
uses an original animated pattern, two differently colored animated overlays,
one shared physical webcam and an owned external AppKit window. Each main output
contains 22 completed Cut changes and eight completed Fades, including 20 rapid
Cuts and six successive 300 ms Fades, plus an explicitly cancelled 3 s Fade and
a rejected unavailable target. Different-target/configuration/edit attempts while
busy, duplicate target requests and stale cancellation tokens are checked.

Final tested app SHA-256:
`78a2d222c5793aa8ab820b28a242941fe70f23331d10f2ab65650dc8cff264d5`.

| Observation | MKV recording | Loopback RTMP → FFmpeg FLV |
|---|---:|---:|
| Decoded video | H.264, 960×540, 30 FPS | H.264, 960×540, 30 FPS |
| Audio | AAC stereo, 48 kHz | AAC stereo, 48 kHz |
| Container duration | 16.933 s | 17.265 s |
| Decoded video frames | 508 | 516 |
| Maximum interior video PTS gap | 34 ms | 34 ms |
| Final video PTS gaps >50 ms | none in this run | none in this run |
| Audio packets / maximum gap | 792 / 22 ms | 805 / 22 ms |
| Audio RMS, first 2 s | 0.0630 | 0.0628 |
| Output drops / encoding skips / render-lag increase | 0 / 0 / 0 | 0 / 0 / 0 |
| Median process CPU | 44.1% | 44.2% |
| Median RSS (range) | 302.5 MiB (299.0–303.7) | 305.0 MiB (301.5–305.1) |
| Stop request to quiescence | 0.344 s | 0.344 s |

CPU is process-time delta divided by wall time, sampled during the sequence;
100% means one core. This debug build includes GPUI and physical capture, but
excludes the receiver, mux helper and other processes. These are observations,
not a performance improvement claim or a hardware comparison. No build/compile
ran concurrently with the measurements.

Both complete files decoded without FFmpeg errors. PTS remained increasing.
A separate packet check (`h9-packet-timestamps.json`) confirmed increasing video
DTS with 33–34 ms intervals in all 508/516 packets, without resetting the clock.
Full audio analysis in 100 ms windows across the same files found RMS ranges
0.06238–0.06391 (recording, 166 windows) and 0.06249–0.06366 (RTMP, 169 windows),
without an interior mute/dropout. Only codec endpoint priming/padding is excluded;
see `h9-audio-continuity.json`. The reproducible script includes this check.
Reproduce it with `ffprobe -v error -select_streams v -show_packets
-show_entries packet=dts_time,pts_time -of json RECORDING_PATH`.
This final pair had no gaps above 50 ms. The known VT finalization tail remains
unresolved: earlier retained H9 runs include 66–133 ms gaps confined to final
intervals, plus runs without gaps. The existing check excludes the final four
intervals when reporting interior gaps, while retaining every tail gap separately.
H9 does not fix or hide the H7/H8 tail.

Decoded stripe pixels prove both initial Cuts had no blended frame. The two
1 s Fades produced respectively 19/19 and 20/20 intermediate frames in recording
and RTMP, with at least 18 distinct intermediate colors per Fade. Raw RGB values
for every decoded frame are retained. Animated overlays and pattern continue;
the physical webcam's frame counter advances, its native instance ID stays the
same, and source-creation/scene-build counters do not change during either output.
The same Production PID, monotonically increasing encoder-frame counter, output
path and single receiver connection remain throughout each run.

Additional real cases:

- Cold window preparation retained the prior active ID until ready. Four repeated
  preparation cancellations returned `cancelled`, preserving the output.
- Closing the destination window during a 3 s Fade produced
  `SCENE_TARGET_FAILED`, retained its source ID/code and cut back without stopping
  the recording. Selecting it later returned `SCENE_TARGET_UNAVAILABLE` while
  each main recording/RTMP continued.
- `verify_h9_faults.py` closed the *previous on-air* window during Fade:
  `SCENE_CURRENT_FAILED`, controlled output stop, and recovery latched to that
  source. Selecting a healthy scene while idle resolved the inactive-source
  requirement through the existing recovery policy.
- Empty live destinations were rejected. An idle Fade completed without polling
  commands during its animation. Twenty cancellation/completion-boundary cycles also verify that the following
  400 ms Fade is not completed by an old stop notification. Deferred shutdown
  during a 5 s Fade returned in
  6 ms, cancelled the visual change, drained the recording and exited; the
  recording decoded and the app reopened normally.
- Save → close → new PID → load restored the identical v3 project, source/layer
  IDs and selected composition. CLI `scenes` and MCP `scenes` returned identical
  shared state/revision. The active graph is the same object read by GPUI; H9
  does not claim a new UI control or a visual-design verification.

## Reproduction and evidence

Start from the normal signed bundle with a single controlled pattern/overlay
scene. Keep physical capture content authorized. Provide local device IDs from
`devices`; do not put them in committed documents.

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/verify_h9_transitions.py --camera-id CAMERA_UID_FROM_DEVICES
python3 scripts/verify_h9_faults.py
python3 scripts/verify_control_delivery.py
```

The scripts create/remove their scenes through shared commands, never by editing
project JSON. Capture media, full MCP exchanges, decoded pixel arrays, packet
metrics, device IDs and logs remain in ignored `var/evidence/` and
`var/recordings/`. Main reports are `h9-transitions.json`, `h9-faults.json` and
`h9-control-delivery.json`;
`h9-regressions/manifest.json` records previous-suite runs. The final verification
manifest hashes code, binaries, reports and protected files.

### Final regression gate

The same final executable passed all **16 Rust tests**, Clippy with warnings
as errors, formatting, the three new integration suites and all **14 existing
real integration suites**. Existing tests/assertions were retained.

| Existing suite | Coverage | Result |
|---|---|---|
| `verify_control.py` | CLI/MCP/state, protocol errors | Pass |
| `verify_h1.py` | External window loss, physical camera/mic, reconnect | Pass |
| `verify_scenes.py` | Window + webcam + overlay, layer edits, restoration | Pass |
| `verify.py` | 65 s source recording, vertical output, local UDP | Pass |
| `verify_encoding.py` | Real x264/VT A/B media and counters | Pass |
| `verify_encoding_fallback.py` | Missing VT module → x264 → restored VT | Pass |
| `verify_output_recovery.py` | Controlled mux-helper failure and recovery | Pass |
| `verify_rtmp.py` | Recording/RTMP, refusal, receiver loss, recovery | Pass |
| `verify_rtmps.py` | Untrusted TLS rejection, no validation bypass | Pass |
| `verify_connect_stop.py` | Existing immediate handshake-stop guard | Pass |
| `verify_vt_stop.py` | Eight VT/x264/reordering/finalization trials | Pass |
| `verify_profiles_restart.py` | Profile v1 + project v3 restart contracts | Pass |
| `verify_h8_lifecycle.py` | 12 repeated-cancel cycles, real silent timeout, delayed receiver, shutdown | Pass |
| `verify_h8_keychain.py` | Real Keychain enrollment/replacement/revocation, changed-identity denial, no secret export | Pass |

Final lifecycle suite took 45.7 s; Keychain took 1.4 s. No native crash was
observed. `h9-regressions/manifest.json` contains individual durations, report
hashes and exit codes; unit/lint logs are beside it. The failed first lifecycle
run was corrected and retained, not omitted from the history. The app was left
idle with only the controlled pattern/overlay, audio off and no endpoint.

### Local control delivery correction

The H8 silent-handshake regression exposed `INVALID_REQUEST` / OS error 35 on
an otherwise valid status request. A bounded reproduction delayed delivery by
30, 100 and 200 ms after connecting to the real control socket; all three were
rejected/closed before the payload arrived. Darwin's accepted socket inherits
listener properties, including nonblocking mode. The listener intentionally
uses nonblocking accept, but the control worker had never reset its accepted
peer to blocking mode. Configuring read/write timeouts alone did not fix that.
See [Apple's accept documentation](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/accept.2.html).

The accepted peer now explicitly uses blocking IO with the existing five-second
read/write bounds, on the existing control worker only. It does not block the
media/GPUI owner or retry a mutation. `verify_control_delivery.py` sends six real
shared-core status frames with delayed and fragmented delivery, including a
separately delivered newline. All six passed in 28–235 ms with one unchanged
Production PID. The downstream RTMP patch remains unchanged.
The failed lifecycle report and delayed-delivery reproduction are preserved in
`h9-pilot/07-regressions-before-completion-guard/` and
`h9-pilot/08-delayed-control-before.json`.

### Retained failed runs

`var/evidence/h9-pilot/` retains every failed integration report and its linked
media, plus an initial successful sequence before the added fault cases:

1. A test waited for a new completion when selecting the already-current scene
   after a failed target. The contract deliberately preserves the last result;
   the waiter now checks quiescence/current ID. Cleanup also needed to remove
   shared layers before removing their source; the core correctly rejected
   `SOURCE_IN_USE`.
2. An exact color-run-index assertion failed near Fade endpoints: lossy H.264
   briefly crossed the RGB tolerance back and forth. The verifier now locates
   stable endpoints and still requires ≥10 blended frames and ≥10 distinct
   colors in each Fade. All raw samples remain. This check passed five retained
   real transition clips and correctly rejected an existing H7 clip with no
   transitions; no native rendering/encoder settings changed for the test.
3. A repeated preparation/cancellation run encountered a transient destination
   rejection. Output stayed healthy, but its source-level reason was lost on
   re-query; the failure snapshot correction described above fixes that defect.
   A cancellation arriving after failure/completion remains an honest no-op.

No native crash was observed in the H9 acceptance/fault runs. These tests do not
prove absence of every scheduler race or long-session leak.

## Remaining limits and next increment

- The eight-second preparation-timeout path is implemented, but these hardware
  runs exercised readiness and real unavailability, not a deterministic device
  that stays indefinitely unready. USB hot-unplug, frozen camera delivery,
  sleep/wake and long sessions remain untested hardware cases.
- Window readiness uses official metadata/existence checks and warmup ticks.
  ScreenCaptureKit's OBS source exposes no public frame-arrival counter here;
  this does not detect every frozen window or prove each off-air texture's age.
- Source-health response and committed state follow the existing owner poll
  cadence. Fade itself follows libobs time, independently of status polling.
- Live transition acceptance used VideoToolbox at 960×540. Existing x264 and
  vertical recording regressions are separate checks, not a complete combined
  transition/encoder/orientation matrix.
- Only H.264/AAC, the existing fixed canvas variants and one output are supported.
  Positive trusted RTMPS delivery remains blocked as documented in H8; no global
  roots, invalid-certificate exception or public destination was introduced.
- Transition preferences reset on restart. The UI's new transition controls and
  all visual-design work remain with Claude. H9 exposes the engine contracts.

Recommend the first **Audio Mixer** increment next: keep audio-source ownership
in this Production, add stable per-input channel IDs with validated gain/mute
and real peak/RMS metering, and expose them through the same CLI/MCP contracts.
Start with a physical mic plus the controlled tone, prove sample/PTS continuity,
clipping behavior, mute/gain changes, disconnect recovery and persistence before
adding filters, monitoring or per-scene audio crossfades. Keep monitoring off by
default to avoid feedback, and do not tie audio routing changes to video-scene
selection implicitly.
