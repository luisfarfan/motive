# H7 — Output profiles and local RTMP

Base: `f53c410`, 2026-11-16, Apple M5 Pro / macOS 27.2, OBS 33.0.1,
development build. GPUI, visual assets and Design System files are unchanged.
No public stream, release, new global dependency or trust-store change.

## Working scope

One `Production` owns scene-v3 state, runtime output selection and the existing
libobs engine. Recording and RTMP share `start_encoded`: the same hardware-first
selection, CBR/High-profile settings, keyframe interval, B-frame policy and
160 kb/s stereo AAC. Both use the active canvas/video/audio clocks. Output and
encoder references are released before the next output; no simultaneous output
or second engine is introduced. Automatic fallback to x264 remains limited to
video initialization before output starts, never after a partial file/stream.

The fixed legacy UDP loopback command remains for regression compatibility.
It still uses FFmpeg/libx264 at its historical settings and explicitly reports
that encoder. New configurable recording/RTMP profiles do not configure that
legacy diagnostic path; it is not exposed as a second configurable policy.

`obs-outputs` supplies `rtmp_output`, including RTMP, TLS, packet scheduling and
network errors. A small original `obs_service_info` adapter supplies only the
validated local endpoint and fixed fixture name through public libobs APIs.
The stock `rtmp-services` catalog is not loaded: its module loader starts a
platform-catalog updater. Motive neither rewrites the transport nor loads a
Twitch/YouTube integration to connect to a local receiver.

## Profiles, preferences and scenes

`src/output.rs` (a module of the core) defines a small typed profile:

```json
{
  "id": "local-demo",
  "encoder": "auto",
  "bitrate_kbps": 2500,
  "rate_control": "cbr",
  "keyframe_seconds": 2,
  "frame_reordering": true
}
```

- Encoder: `auto`, `videotoolbox` or `x264`; explicit VT remains strict.
- CBR is the only implemented rate control. VBR/CRF/quality presets are rejected.
- Bitrate validation: 250–20,000 kb/s; keyframes: 1–10 seconds. These are accepted
  bounds, not a claim that every value has been benchmarked. Runs exercised
  1,800 and 2,500 kb/s, and 1/2-second keyframes.
- Reordering defaults to the previous enabled behavior. `false` explicitly maps
  to official VT `bframes=false` / x264 `bf=0`. This may change compression
  efficiency and quality at a fixed bitrate; no quality equivalence is claimed.
- At most 16 profiles, unique bounded IDs, strict fields and enums.
- Resolution/FPS fields are rejected. Outputs use the existing 960×540 or
  540×960 canvas at 30 FPS. Capabilities identify these limits; there is no
  per-profile scaling, FPS control, multistream or simultaneous dual canvas.

Scene persistence stays **version 3**, unchanged. Profiles have their own
`var/output-profiles.json`, **version 1**, written atomically with owner-only
permissions. `save_output_profiles` / `load_output_profiles` are explicit.
The profile file contains definitions, never scenes, endpoints or credentials.

Selected recording/streaming profile IDs and the endpoint are runtime
preferences. Both initially select `standard` (the former recording defaults);
the endpoint is unset on every launch. Loading definitions preserves selection
when the ID exists, otherwise it selects the first validated definition.
This permits restoring a collection that removed the original `standard` ID.

Both outputs can select one shared profile or explicitly select different
profiles. Editing a shared definition affects both *next* outputs. `set_encoder`
is a compatibility command that edits the selected recording profile in memory;
it also applies to RTMP if RTMP selects that same profile. It persists only when
profiles are explicitly saved. No active encoder changes in place.

## CLI and MCP contract

All commands route through the same core; no production-file edits or clicks:

```sh
./target/debug/motive ctl '{"op":"output_capabilities"}'
./target/debug/motive ctl '{"op":"output_profiles"}'
./target/debug/motive ctl '{"op":"upsert_output_profile","profile":{"id":"local-demo","encoder":"auto","bitrate_kbps":2500,"rate_control":"cbr","keyframe_seconds":2,"frame_reordering":true}}'
./target/debug/motive ctl '{"op":"select_output_profile","target":"streaming","profile_id":"local-demo"}'
./target/debug/motive ctl '{"op":"configure_stream","endpoint":{"transport":"rtmp","port":19351}}'
./target/debug/motive ctl '{"op":"preflight_output","target":"streaming"}'
./target/debug/motive ctl '{"op":"start_stream"}'
./target/debug/motive ctl '{"op":"status"}'
./target/debug/motive ctl '{"op":"stop_output"}'
```

The same tools exist in MCP, plus `remove_output_profile`,
`save_output_profiles`, `load_output_profiles` and `recover_output` (39 tools
total). `preflight_output` checks idle/recovery state, source readiness, profile
validation and module availability. It explicitly reports `network_tested:false`
and `encoder_initialized:false`; it is not a promise that a receiver is alive
or its certificate is trusted. Starting always repeats validation.

Endpoints accept only `transport:rtmp|rtmps` and an unprivileged port. The host
is always **127.0.0.1**, path `/live/motive`; no arbitrary host, URL, stream key,
username or password is accepted. `motive` is a public test name, not a secret.
Unknown fields/values produce generic validation messages without reflecting
input values. State includes effective profiles, sanitized output error codes,
selected encoder, native counters and recovery requirements.

Mutation errors preserve profiles, scene state and revision. Profile/endpoint
changes require idle output. `start_stream` acknowledges asynchronous startup:
observe `connecting`, then `streaming` or `error`. `stop_output` on a connected
stream requests graceful finalization; observe `stopping`, then `idle`.
The RTMP output's official shutdown-buffer timeout is set to three seconds.
Automatic reconnect is disabled. Refusal and receiver loss latch output recovery;
`recover_output` acknowledges only that fault after shutdown and never restarts
or clears unrelated source recovery. Existing `reconnect_sources` still works.

MCP annotations now mark destructive operations such as deletion, replacing
persisted state, shutdown, snapshot overwrite and stopping output. Read queries
are idempotent; operations are closed-world (loopback only). `snapshot`,
`shutdown` and `set_test_window` are labeled development tools in descriptions
and `_meta["motive/category"]`. They remain available in this development build
for existing regression scripts; annotations are not an authorization boundary.

## Pending-handshake cancellation limitation

A real owned TCP server accepted a connection but withheld the RTMP handshake.
Calling the official force-stop from the control owner blocked MCP until its
five-second timeout. Moving that call to a worker exposed a crash in the OBS
plugin's `pthread_join`: its connection thread can detach while stop joins it.
The worker approach was **removed**, not left in production.

The final core returns `OUTPUT_CONNECTING` immediately for `stop_output` while
the native handshake is pending. It neither force-joins nor pretends to cancel.
MCP status and preview continue progressing; wait for connection success/failure,
then stop/recover explicitly. Closing the owned silent peer produces a real
connection failure and allows recovery. Native network timeouts still belong to
OBS; Motive does not claim an independent bounded handshake deadline. Immediate
handshake cancellation remains unsupported pending an upstream-safe API/fix.

A source fault during connection still latches source recovery and defers the
normal stop until the output becomes active. Resources cannot be replaced and
core shutdown is rejected while a connection/output is pending.

## VideoToolbox stop experiment

`scripts/verify_vt_stop.py` records eight owned pattern/animated-overlay clips:
VT and x264, two repetitions each with reordering on/off, alternating order.
Canvas, bitrate, profile, audio and graceful stop command are unchanged. Every
file is fully decoded; ffprobe records every timestamp gap, B-frame count,
keyframe interval and duration. Stop acknowledgement/finalization and interval
process CPU/RSS are retained. This short experiment is not a new performance
benchmark or a visual-quality comparison.

With reordering enabled, the experiment reproduced end-boundary gaps in both
encoders. All four disabled-reordering trials had no gaps over 50 ms and zero
B-frames. Steady-state timestamps were continuous in all eight. This verifies
an **opt-in mitigation**, not a universal encoder repair. Defaults remain enabled
so compression behavior does not silently change.

Pinned OBS VT source queues compressed samples, consumes one queued sample per
encode invocation and invalidates the compression session at destruction without
calling `VTCompressionSessionCompleteFrames`. This is relevant implementation
evidence, not proof of the precise cause: x264 also reproduced the boundary
behavior. No private session access, custom drain or OBS encoder rewrite was used.

### Measured stop experiment

| Encoder | Reordering | Trials with final gaps | Largest gaps | Stop-to-idle range |
|---|---|---:|---|---|
| VideoToolbox | Enabled | 2 / 2 | 67 / 133 ms | 0.340–0.341 s |
| VideoToolbox | Disabled explicitly | 0 / 2 | None over 50 ms | 0.198–0.201 s |
| x264 | Enabled | 2 / 2 | 133 / 67 ms | 1.141–1.174 s |
| x264 | Disabled explicitly | 0 / 2 | None over 50 ms | 1.027–1.028 s |

### Measured recording and RTMP smoke run

Same process, owned pattern + animated overlay, active canvas 960×540 at 30 FPS,
VT hardware, 1,800 kb/s CBR, 1-second GOP target, reordering enabled, AAC 160 kb/s.
The full scene-v3 document is asserted identical before/after each output and
after receiver-failure recovery. These are short workload observations, **not**
a controlled recording-versus-streaming performance benchmark.

| Output | File duration / decoded frames | App CPU median | RSS median (range) | Stop-to-idle |
|---|---|---:|---|---:|
| Recording MKV | 8.166 s / 244 | 43.69% | 100.39 MiB (98.08–102.48) | 0.338 s |
| Local RTMP → receiver FLV | 20.665 s / 615 | 43.67% | 97.83 MiB (94.88–99.92) | 0.339 s |

CPU uses differences in cumulative `ps time` over wall-clock intervals, with
100% equal to one CPU core. Medians omit the first three seconds. Only Motive
is measured here: the receiver, mux helper, OS video services and other apps
are excluded. These samples do not demonstrate a memory improvement or lack
of long-term leaks. Raw half-second samples remain in `h7-rtmp.json`.

Both files fully decode to H.264/AAC; non-silent stereo audio and moving overlay
pixels pass. Maximum keyframe gap was 0.967 s. RTMP added no native render lag,
video-skipped frames or output-drop counter. Recording/stream tail gaps were
66 / 133 ms with the default B-frame policy; zero native counters do not imply
frame-perfect endings. No public endpoint or latency/energy benchmark was used.

Connection refusal produced native code **-2** (`OUTPUT_CONNECT_FAILED`),
receiver termination **-5** (`OUTPUT_DISCONNECTED`). Both required explicit
recovery; restarting the owned receiver then produced another decodable stream.
The final pending-handshake guard returned in **0.032 s** while render frames
continued advancing. The failure/crash from the discarded force-stop attempts
is preserved rather than presented as a successful cancellation test.

## RTMPS and future credentials

`scripts/verify_rtmps.py` starts a local TLS fixture with a valid 127.0.0.1 SAN
and a self-signed certificate. A separate Python client trusting only that
fixture validates the server successfully. Motive then rejects it using the
unchanged macOS trust anchors: OBS logs certificate verification failure, the
server receives `unknown ca`, output reports connect failure and zero bytes,
and explicit recovery is required. There is no plaintext retry.

**Verified:** untrusted-root rejection. **Not verified:** trusted RTMPS media
delivery or isolated hostname-mismatch rejection. The pinned official mbedTLS
path loads `SecTrustCopyAnchorCertificates`, sets the hostname and requires peer
verification. No insecure switch or custom CA override is exposed. A positive
trusted RTMPS test needs an appropriate controlled certificate/environment;
this cycle did not modify global trust to manufacture that result.

Credential support is intentionally absent. The next design should store secret
bytes as application-owned macOS Keychain items, expose only opaque references
and availability metadata, and resolve secrets only inside the native/core
boundary when starting an authorized output. Enrollment/replacement needs a
local user flow; MCP, profiles, scenes, URLs and process arguments must never
carry secret bytes. Lock/unavailable/access-denied cases must be structured
errors. Before enabling public endpoints, audit/redact all libobs/service logs
and errors, reject credential-bearing URL forms, and test locked-keychain and
revocation behavior. This is a design boundary, not an implemented credential
manager. Apple's [Keychain Services](https://developer.apple.com/documentation/security/keychain-services)
provides encrypted secret storage and application access controls.

## Reproduction and evidence

Open a signed, idle Motive with an owned pattern/overlay production. FFmpeg,
ffprobe and OpenSSL are the already available local tools; no global install.

```sh
python3 scripts/verify_vt_stop.py
python3 scripts/verify_rtmp.py
python3 scripts/verify_rtmps.py
python3 scripts/verify_connect_stop.py
python3 scripts/verify_profiles_restart.py
```

For a manual receiver, start this in another terminal before `start_stream`:

```sh
ffmpeg -nostdin -listen 1 -i rtmp://127.0.0.1:19351/live/motive -c copy var/evidence/local-receiver.flv
```

Keep recordings, TLS fixture keys, logs and inventories in ignored `var/`.
`h7-*.json` reports retain MCP requests/responses, media probes/hashes, metrics
and failures. `h7-pilot/` retains preliminary runs, the blocked-stop response
and native crash report. `h7-before/` preserves prior H6 regression reports.

## Final regression results

All existing tests/scripts were retained. `cargo test --locked` passed **14**
tests and `cargo clippy --locked -- -D warnings` passed. Scoped Rust formatting,
Python syntax, normal bundle signature verification and `git diff --check`
passed. The final executable SHA-256 is
`a8a46b3f213688bf30dd8e23909328ac17bc72b0371e1a57d4a34b882615ee13`.

Twelve real verification reports finished with `ok:true` and no cleanup errors:

| Verification | Evidence |
|---|---|
| B-frame matrix | Eight fully decoded VT/x264 recordings; every timestamp gap retained |
| RTMP/profile contracts | Recording, local RTMP, refusal, receiver loss, explicit recovery, invalid fields and annotations |
| RTMPS rejection | Untrusted CA rejected by the real official TLS path; no trust change |
| Pending handshake | Immediate structured cancellation rejection; media/control stay responsive; peer closure and recovery |
| Profile restart | Profile v1 save/restart/load, missing selected-ID handling, unchanged scene v3, no endpoint auto-restore |
| Existing MCP control | Same PID/revision, strict commands, client disconnect preserves engine |
| Existing optional VT module fallback | Actual x264 recording when VT omitted, hardware recording after restart |
| Existing encoder regression | Both x264 and VT, three owned layers, two 15-second trials; decode/pixels/timestamps/counters pass |
| Existing baseline | VT horizontal 65.966 s / 1,979 frames; vertical 4.100 s / 122 frames; tone, overlay and UDP loopback pass |
| Existing H1 | External-window loss/recovery; audio change preserves video latch; physical camera/mic 8.566 s / 256 frames |
| Existing Scene Graph | Window + webcam + overlay 16.033 s / 479 frames; MCP transforms/color/order/visibility and save/restart/load |
| Existing mux recovery | Real helper termination latches output failure; three subsequent decoded recordings after explicit recovery |

A first H1 retry encountered two owned fixture windows with the same identity;
`SOURCE_AMBIGUOUS` correctly prevented restoration. The extra fixture launched
during activation was closed, and the unmodified script passed. Its failed
report is retained in `h7-pilot/h1-ambiguous-fixture.json`. A test initially
assumed an unset endpoint after a previous handshake test; it was corrected to
respect the existing runtime configuration. Neither case changed source identity
resolution or weakened media assertions.

`var/evidence/h7-verification-manifest.json` contains hashes for all twelve
reports, the executable and source/test files, plus the final core state.
The app is left idle, with owned pattern/overlay only, no physical audio/video
capture, no stream and no recovery latch. No UI/design files were changed.

Limits remain: one Mac/development build, short runs (not an hour-long soak),
no removable-device hot unplug or new sleep/wake coverage, no 1080p/4K/FPS
configuration, no trusted RTMPS delivery, no credential manager, and no safe
immediate cancellation of a pending native handshake. Existing development
bundle portability/notarization limits also remain.

## Next increment

Resolve pending-handshake cancellation with an upstream-safe lifecycle, then
verify trusted RTMPS end to end in a controlled trust environment. Add Keychain
credential enrollment/references and authorized endpoint validation before any
public service. Quality presets should follow visual/bitrate measurements;
resolution/FPS configuration requires real engine/composition/media tests.
No multistream, simultaneous canvases, cloud, payments or plugin marketplace.

## Primary references

- [OBS 33.0.1 public output/service APIs](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h).
- [Official RTMP transport and lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/rtmp-stream.c).
- [Official TLS verification and system roots](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/librtmp/rtmp.c).
- [VT encoder settings and lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-videotoolbox/encoder.c).
- [x264 official `bf` setting](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-x264/obs-x264.c).
- [Service catalog module startup](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/rtmp-services/rtmp-services-main.c).
