# Apple Silicon hardware encoding

Follow-up: [H7 output verification](h7-output-verification.md) extends encoder
selection into profiles and reports the bounded frame-reordering experiment.
The measurements below are retained as the original H6 evidence.

Date: 2026-11-16. Base: `a046049` on `main`. Apple M5 Pro, macOS 27.2,
OBS 33.0.1, Rust development build. This increment changes the multimedia
core and its adapters; it does not modify GPUI, visual tokens or design files.

## Integration and selection

Motive loads the official `mac-videotoolbox` module from the pinned OBS bundle
as an optional module. `obs_post_load_modules` finishes its asynchronous
enumeration. Available IDs are intersected with libobs's registered H.264
encoders; Apple's public `VTCopyVideoEncoderList` supplies the advertised
hardware capability. No private OBS structures or custom compression session
are used, and no encoder is rewritten.

Observed registered H.264 encoders on this Mac:

| ID | Capability | Motive selection |
|---|---|---|
| `com.apple.videotoolbox.videoencoder.ave.avc` | Apple hardware | Preferred by `auto`; explicit `videotoolbox` |
| `obs_x264` | Software | Explicit `x264`; automatic fallback |
| `com.apple.videotoolbox.videoencoder.h264` | Apple software | Enumerated, not selected as hardware |

The OBS module also has HEVC/ProRes support; this increment exposes only the
H.264 recording path. Inventory capability is not a fabricated utilization
measurement. In actual recordings the official OBS module logged **“session
created with hardware encoding”**, after checking its VideoToolbox session.

`Production.recording_encoder` is the single runtime preference. The existing
UI recording command, CLI and MCP all use it. It defaults to `auto` at launch
and deliberately remains outside the unchanged project-v3 schema. Loading a
project does not change the current preference; restarting resets it to `auto`.

```sh
./target/debug/motive ctl '{"op":"encoders"}'
./target/debug/motive ctl '{"op":"set_encoder","encoder":"auto"}'
./target/debug/motive ctl '{"op":"set_encoder","encoder":"videotoolbox"}'
./target/debug/motive ctl '{"op":"set_encoder","encoder":"x264"}'
./target/debug/motive ctl '{"op":"start_recording"}'
```

The same `encoders` and `set_encoder` tools are available over stdio MCP (28
tools total). Selection requires stopped output. Unknown names/fields are
rejected, and unavailable explicit hardware returns `ENCODER_UNAVAILABLE`
without changing the preference/revision. `status.encoding` provides the
preference, registered inventory, optional-module status, selected encoder and
fallback reason. `selected_id` describes the current or last started output,
whereas `preference` applies to the next recording.

## Fallback and lifecycle

- `auto` chooses registered hardware, or x264 if the module/device is absent.
- If video initialization returns failure, `auto` releases the unsuccessful
  output/video encoder and tries x264 once **before writing video**. Explicit
  `videotoolbox` is strict and never silently changes to software.
- Video initialization uses public `obs_output_initialize_encoders` before AAC
  is attached. OBS 33.0.1 ignores its flags parameter, so merely passing a
  VIDEO flag would not isolate video failure. AAC is attached afterwards.
- Audio, disk and muxer failures do not trigger codec fallback. There is no
  automatic encoder switch or restart in a partially written recording.
  Existing output-error latching and explicit recovery remain in the core.
- `MOTIVE_DISABLE_VIDEOTOOLBOX=1` is a per-process startup diagnostic/safe-mode
  switch that omits the optional module. It changes no global setting or OS
  permission. Inventory reports `VIDEOTOOLBOX_DISABLED`; `auto` then uses x264.
- Existing stop-signal plus inactive-output checks, callback disconnection,
  native reference release and empty-file cleanup are retained.

Recording stays H.264 High / NV12 input (decoded yuv420p), BT.709 limited range,
960×540 or 540×960 at 30 FPS, 2,500 kb/s CBR target, 2-second keyframe interval,
48 kHz stereo AAC at 160 kb/s, MKV. x264 retains `veryfast`; encoder-specific
defaults such as frame reordering remain those of the official plugins. Equal
targets are not a claim of identical rate control, visual quality or file size.

The existing fixed UDP loopback path remains FFmpeg/libx264. Recording policy
does not change it; telemetry identifies `libx264 (loopback)` explicitly.

## Reproducible comparison

Use a signed, idle app and a disposable production containing only owned
patterns/overlays. No camera or private-window recording is required for the
benchmark. Keep the build, preview, canvas and system conditions unchanged:

```sh
python3 scripts/verify_encoding_fallback.py
python3 scripts/verify_control.py
python3 scripts/verify_encoding.py --seconds 60 --rounds 2
```

The comparison creates a scene with a full-size animated pattern, a second
pattern at `(640,32), 288×162` and the animated overlay at `(32,436), 320×72`.
It records x264 → VT → VT → x264 in one app process. The scene/resources are
unchanged between encoders, and the project is asserted equal after each
selection and recording. Cleanup uses core commands, not project-file edits.

CPU is calculated from **differences in cumulative process CPU time divided
by elapsed wall time**, not `ps %cpu`'s historical average. The first five
seconds of each trial are excluded from CPU/RSS summaries. 100% means one CPU
core. Motive and its mux helper are sampled separately. Apple's system encoder
services and other processes are not included, so app CPU reduction is not a
measurement of whole-machine energy or total system resource consumption.

Every file is fully decoded with FFmpeg. ffprobe checks codec, dimensions,
profile, pixel format, frame rate, duration, frame count, timestamps and GOP.
Decoded audio must be non-silent; pixel regions verify the secondary layer,
overlay accent and animation. Native render lag, video skipped frames, output
drops, encoded frames and preview copies are retained as separate counters.

A preliminary x264 run exposed one 66.7 ms gap at the final recording boundary
with zero native skipped-frame counters. The test now reports boundary gaps
separately and still rejects non-monotonic timestamps or gaps in the steady
recording. It does not relabel a boundary omission as zero end-to-end loss.
The preliminary report is retained in `encoding-pilot-gap.json`.

### Measured results

Four sequential recordings, one process/binary, the same three sources and
2,500 kb/s target. Each targeted 60 seconds; actual durations include sampling
and finalization overhead. CPU/RSS below are per-trial medians after warm-up:

| Order | Encoder | App CPU | App RSS (MiB) | File duration | Decoded frames | File (MB) |
|---|---|---:|---:|---:|---:|---:|
| 1 | x264 | 48.72% | 306.67 | 61.266 s | 1,838 | 20.376 |
| 2 | VideoToolbox hardware | 43.69% | 294.92 | 61.100 s | 1,830 | 20.162 |
| 3 | VideoToolbox hardware | 43.94% | 268.89 | 60.533 s | 1,815 | 19.995 |
| 4 | x264 | 48.54% | 239.84 | 60.300 s | 1,809 | 20.054 |

The median of trial CPU medians is **48.63% x264 vs 43.82% VT**: 4.81
percentage points, approximately **9.9% lower app CPU** in this workload.
This is a modest measured improvement at 540p, not a projection for 1080p/4K
or an energy claim. The mux helper's median CPU rounded to zero at `ps time`
resolution. Its median RSS was about 11.0 MiB (x264) / 12.0 MiB (VT).

Median-of-medians app RSS was 273.3 / 281.9 MiB respectively, but RSS declined
substantially across trial order for both encoders. These samples do **not**
demonstrate a memory improvement or isolate an encoder-specific allocation
difference. The per-second samples and ranges are retained in the report.

All four files decoded without errors: H.264 High, yuv420p, 30 FPS, BT.709
limited range, AAC stereo 48 kHz, audible tone, correct secondary layer and
animated overlay. Maximum observed keyframe gaps were 2.0 s for x264 and 1.9 s
for VT. No added render lag, video-skipped counter or output-drop counter was
reported during these runs. Preview busy-buffer drops were 5, 1, 2 and 3;
preview loss is separate from recording loss.

**Stop boundary limitation:** the VT files had one final video timestamp gap
each: approximately **134 ms** and **67 ms**. Steady recording timestamps were
continuous; x264 had no such gap in the four final trials, but did in the
retained preliminary run. Native zero-drop counters therefore do not imply
frame-perfect file endings. Files remain decodable. Disabling frame reordering
is a possible next controlled experiment, with a compression tradeoff; it was
not applied silently to change the comparison or hide this result.

## Local evidence

Artifacts stay under ignored `var/evidence/` and `var/recordings/`:

- `encoding-comparison.json`: full MCP exchanges, build/UI hashes, per-second
  metrics, native counters, probes, pixel/audio checks and media hashes.
- `encoding-fallback.json`: actual module omission, rejected explicit hardware,
  decoded x264 fallback file and hardware recording after restart.
- `encoding-runtime-final.log`, `encoding-restored.log`: native module/session
  confirmation and encoder/output logs; stderr is saved alongside them.
- `encoding-tests.log`, `encoding-clippy.log`, `encoding-bundle.log`: build
  checks; all prior unit tests remain and encoder validation is added.
- `encoding-pre-regression/`: previous scene-editor/H1 reports retained before
  rerunning the existing scripts with automatic hardware recording enabled.

No binary, media, device inventory or runtime log is published by this cycle.

## Existing regressions, rerun with automatic hardware recording

All existing tests were retained. `cargo test --locked` passed all **12** tests;
`cargo clippy --locked -- -D warnings`, scoped Rust formatting, Python syntax
checks and `git diff --check` passed. The signed development bundle was rebuilt.

| Real check | Result |
|---|---|
| `verify_control.py` | 28 MCP tools; shared CLI/MCP state, encoder selection, invalid-policy rejection without revision change; v3 unchanged |
| `verify.py` | Hardware recording: 66.100 s / 1,980 decoded frames at 960×540; 4.100 s / 123 frames at 540×960; audio, animated overlay and local UDP loopback verified |
| `verify_h1.py` with authorized physical IDs | External-window loss finalizes the file; changing audio preserves the video recovery latch; explicit reconnect works; physical camera + microphone: 8.733 s / 259 decoded frames with non-silent AAC |
| `verify_scenes.py` with authorized camera ID | External window + webcam + overlay: 15.900 s / 476 decoded frames; MCP edits position, size, color, order and visibility; save/close/reopen retains v3 IDs/layouts and records again |
| `verify_output_recovery.py` | Terminating the owned mux helper latches a real output error; audio changes do not acknowledge it; explicit recovery then produces three fully decodable hardware recordings |

The recording states in these reports identify the Apple hardware encoder;
the baseline's loopback output still identifies libx264. These regression CPU
samples are not used for the encoder comparison above.

Normal activation of the owned fixture was needed after Stage Manager hid it.
Initial `CAPTURE_NOT_READY` attempts are retained as
`encoding-baseline-hidden-window.json` and `encoding-h1-hidden-window.json`.
Showing the selected test window restored frames without changing permissions
or capture code. Keep that window visible when reproducing the capture scripts;
no TCC or visibility bypass was introduced. Physical hot unplug remains untested.

Passing reports are `control-integration.json`, `acceptance.json`,
`h1-acceptance.json`, `scene-acceptance.json` and `output-recovery.json`, with
`encoding-*.log` transcripts. `encoding-verification-manifest.json` records
their hashes, the tested executable/source hashes and the final idle state.
Camera/microphone/window sources were released through core commands afterward.

## Limits and next increment

- Results apply to this Mac, this debug build, these three owned layers and
  these resolutions/FPS. This is not a 1080p/4K, high-FPS or hour-long soak.
- Module-unavailable fallback is exercised with real libobs/x264 output.
  Hardware exhaustion, an actual driver initialization failure and process
  crashes inside native libraries are not induced or claimed as tested.
  Automatic fallback handles failures returned by libobs, not a process crash.
- Camera/USB removal, sleep/wake and frozen-window limits from the scene-graph
  report remain. Hardware encoding does not fix source health.
- VT still receives frames through the official plugin's CPU pixel-buffer
  path. This is hardware compression, not a zero-copy preview/render rewrite.
- Short RSS measurements do not prove absence of long-term native leaks or
  account for system encoder-service memory. No energy or latency claim is made.
- The existing development bundle still links to checkout dependencies; normal
  signing works, but its external framework symlink prevents strict bundle
  verification. No release/notarization work is included.

First characterize the stop-boundary timestamp gaps with repeated short
recordings and an explicit frame-reordering comparison. Then define a small
validated recording/output configuration in the shared
core: quality target, bitrate/rate control, keyframe interval and encoder
preference, with explicit persistence/versioning. Compare visual quality and
actual bitrate before calling profiles equivalent across encoders.

RTMP/RTMPS can then use the official encoded libobs output/service interfaces,
so the same encoder policy feeds recording or a configured output. That work
needs explicit endpoint validation, credential storage without secrets in MCP
state/logs, TLS validation, reconnect/backoff and local receiver tests before
an authorized public test. Neither profiles nor configurable/public streaming
are implemented in this increment.

## Primary implementation references

- [OBS 33.0.1 VideoToolbox module](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-videotoolbox/encoder.c): dynamic registration, defaults, Apple hardware discovery/session confirmation and encode path.
- [OBS 33.0.1 public API](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h): enumeration, encoder creation/settings, output initialization and metrics.
- [OBS 33.0.1 output lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c): initialization order, ignored flags and completion semantics.
- [OBS 33.0.1 muxer](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-mux.c): encoder initialization before helper/file startup.

These pinned sources are present in `.deps/obs-studio-33.0.1`; no reverse
engineering of a proprietary encoder or application was necessary.
