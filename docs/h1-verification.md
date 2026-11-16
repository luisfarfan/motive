# H1 — real-device verification

Date: 2026-11-16. Environment: Apple M5 Pro, macOS 27.2, OBS 33.0.1,
GPUI Kit 0.10.0. These are local development-build observations, not a claim
of support across all cameras, audio devices or macOS versions.

## Implemented

- Individual application-window selection through the official ScreenCaptureKit
  source. The inventory excludes accessory/system-agent surfaces and the studio
  itself. Choices are sorted and held stable while the picker is open.
- Explicit AVFoundation camera UID selection via `macos-avcapture`, with a
  1280×720 preset. Camera audio is disabled; audio is selected separately.
- Explicit CoreAudio microphone UID, packet-flow counter and live peak level.
  The moving system-default alias is excluded. Silence remains healthy when
  audio packets continue to arrive.
- The Production core owns commands, health policy and project state for UI,
  CLI and MCP. `select_camera` and `reconnect_sources` are available to all three.
- Window ownership/availability, device presence and permissions are checked.
  A physical microphone with no packets for three seconds reports
  `AUDIO_NOT_READY`. Health is polled once per second and before commands.
- Loss during an active output requests a controlled stop, retains `last_fault`
  and sets `recovery_required`. Reconnection never resumes recording by itself.
- Project schema v2 stores camera/microphone UIDs and window bundle ID/title.
  Restore rejects absent or ambiguous window matches. Legacy v1 can only resolve
  Motive's owned test window; it never selects the first unrelated window.

## Evidence

The reproducible scripts use the actual app, its Unix socket, libobs and macOS.
There is no mocked camera, microphone, window, encoder or disconnection in the
integration checks. The external fixture is a real separate AppKit process
rendering original controlled content.

| Journey | Result | Local evidence |
|---|---|---|
| External window selection and project restore | Passed | `var/evidence/h1-acceptance.json` |
| External source process exits during recording | Passed: output finalized, fault retained, new recording blocked | Same report; recorded MKV fully decoded by FFmpeg |
| Reopen, explicitly select and reconnect source | Passed: a new recording has valid video and audio | Same report |
| Integrated camera + physical microphone | Passed: H.264/AAC, image outside overlay, non-silent decoded audio, advancing microphone packet count | Same report; `physical` section |
| Physical-source project restore and explicit reconnect | Passed | Same report |
| UI source selection visible through CLI | Checked against shared PID, revision and `UI` origin | `var/evidence/h1-ui-selection.json`, `h1-ui-window.json` |
| MCP initialize/list/call, audio selection, camera error and reconnect | Passed; 12 tools and same production PID/revision | `var/evidence/control-integration.json` |
| Strict inputs, project identity and migration | Six unit tests passed | `var/evidence/h1-tests.log` |
| Static checks | Clippy without warnings; formatting checked | `var/evidence/h1-clippy.log` |

The physical test plays the project's quiet owned WAV fixture twice through
the current audio output and captures the actual microphone input. It does not
substitute that WAV for the microphone source. Audio and camera recordings stay
local and are excluded from Git. Source tests also inspect pixels **outside**
the overlay, so a moving overlay alone cannot satisfy video presence checks.

Exact durations, frame counts, RMS values, output paths and the signed executable
SHA-256 are in the local JSON reports. Media measurements are output metrics;
they do not establish input latency or an independently measured camera FPS.

### Final measured run

- Physical camera + microphone: **8.566000 s / 255 video frames**,
  decoded mono audio RMS **0.015491**.
- Source termination: **3.200000 s / 96 frames** in the finalized
  recording; the core reached `idle` with `SOURCE_UNAVAILABLE` retained.
- Recovered window: **3.166000 s / 93 frames** in a new recording.
- Regression: **65.566000 s / 1966 frames** landscape,
  **4.166000 s / 123 frames** portrait, and
  **5.021333 s / 150 frames** through local UDP.

The signed build hash and source checksums are in the local
`var/evidence/h1-build-identity.json`. These files contain local paths/identities
and intentionally remain outside the public repository.

## Reproduce

Open the development bundle, complete normal macOS permissions, stop outputs,
and have FFmpeg/ffprobe available. Test source content must be controlled.

```sh
python3 scripts/verify_h1.py
```

To opt into physical camera/microphone testing, prepare controlled camera
content and obtain the desired UIDs from `motive ctl '{"op":"devices"}'`:

```sh
python3 scripts/verify_h1.py \
  --camera-id 'YOUR_CAMERA_UID' \
  --microphone-id 'YOUR_MICROPHONE_UID'
python3 scripts/verify_control.py
```

The H1 script builds and launches its owned external fixture, closes only the
fixture process it started, and returns the studio to pattern + no audio in
cleanup. It never disconnects hardware or changes OS permissions automatically.
Use an idle studio with no separate `MotiveFixture` instance, since duplicate
identical windows deliberately make project restoration ambiguous.

The longer horizontal/vertical/loopback regression is `scripts/verify.py`.
It requires Motive's **Abrir fuente de prueba** window to have drawn its first
frame. Keep that source available during the test.

## Problems found and corrected

1. Ad-hoc signatures change their code identity on rebuild. Permissions granted
   to a previous identity can be displayed in Settings while the new process
   reports them unavailable. The bundle script now accepts an existing local
   Apple Development identity. On this Mac, normal Settings authorization and
   re-registering the app's obsolete screen-permission entry resolved the
   transition; no TCC database editing, reset bypass or global certificate
   installation was used. Subsequent signed rebuilds retained permissions.
2. OS window order changes when applications become active. Rebuilding a picker
   from that order while a click is in progress can select a different row.
   The inventory is now sorted and frozen while choices are visible.
3. A constrained window could compress the device list. The picker has a fixed
   scrollable area and the preview shrinks while it is open.
4. Sources can be created successfully before delivering media. Startup checks
   require actual capture dimensions and microphone packet flow. A not-yet-ready
   source cannot start an output; callers must wait and re-check state.

## Explicit limitations

- **Physical USB/Continuity hot-unplug was not exercised.** Built-in camera and
  microphone cannot be unplugged independently. Device disappearance and
  microphone stalls are implemented; their physical-removal matrix remains
  pending with removable hardware. Window process termination was exercised.
- Camera health uses permission, connection identity and initialized dimensions.
  A connected camera that freezes while retaining its last frame is not yet
  detected independently. This is a follow-up, not a verified failure mode.
- A hidden/minimized window, including one hidden by Stage Manager when
  activating Motive, may remain `CAPTURE_NOT_READY` until it becomes visible.
  This was observed in the UI journey: explicitly showing the selected fixture
  changed capture width from zero to 720 and cleared the pending state. Keep
  the source visible while initializing capture.
  Protected windows may not be capturable. No permission bypass is attempted.
- Source changes and reconnection require idle output. There is one main visual
  source and one separately selected audio source; no live device handover.
- No prolonged hardware soak, sleep/wake matrix, all-device compatibility,
  complete accessibility audit or full scene editor is claimed.
- The development app is locally signed, not notarized or self-contained.
  REA is absent from the product and was unnecessary for this implementation.

## Primary implementation references

- [OBS macOS camera module, 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-avcapture/plugin-main.m)
- [OBS camera device enumeration, 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-avcapture/plugin-properties.m)
- [OBS ScreenCaptureKit source, 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-video-capture.m)
- [OBS public source/audio callbacks, 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h)

Implementations use these public open-source interfaces. No proprietary Meld
code, assets or design was inspected or copied for H1.
