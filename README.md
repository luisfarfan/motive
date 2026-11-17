<p align="center">
  <img src="docs/assets/motive-banner.svg" alt="Motive — Your production. Your machine." width="100%" />
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: GPL-3.0-or-later" src="https://img.shields.io/badge/license-GPL--3.0--or--later-65dfbc?style=flat-square" /></a>
  <img alt="Platform: Apple Silicon" src="https://img.shields.io/badge/platform-Apple_Silicon-8daafa?style=flat-square" />
  <img alt="Built with Rust, GPUI and libobs" src="https://img.shields.io/badge/built_with-Rust_·_GPUI_·_libobs-e8ba84?style=flat-square" />
  <img alt="Status: experimental" src="https://img.shields.io/badge/status-experimental-c58af9?style=flat-square" />
</p>

<p align="center">
  A free, open-source production studio for macOS.<br />
  Native controls. Real media. One local engine.
</p>

<p align="center">
  <a href="#-get-started">Get started</a> ·
  <a href="#-one-production-three-controls">CLI & MCP</a> ·
  <a href="#-verification">Verification</a> ·
  <a href="docs/plan.md">Roadmap</a>
</p>

---

Motive is an early native streaming and recording studio built with **Rust, GPUI Kit and libobs**. It brings the interface, command line and AI-agent controls to the **same running production**. No account, hosted backend or subscription is required.

> **Experimental developer preview.** Recording and local loopback streaming work. This is not yet a packaged release or a full replacement for OBS Studio. The current interface is in Spanish; this README is in English.

**Status — November 17, 2026:** H11 adds native overlays and widgets to the shared core and CLI/MCP. Its real-media checks pass; acceptance remains conditional on the open H1–H10 regression checks. GPUI integration uses the [overlay contract](docs/h11-overlay-ui-contract.md) and is separate from this core increment.

## ✨ What is taking shape

| | Capability | Implementation |
|---|---|---|
| 🪟 | Window capture | Select an individual application window through ScreenCaptureKit |
| 📷 | Camera input | Explicit camera selection through the official OBS AVFoundation module |
| 🎙️ | Global audio mixer | Reusable microphone UIDs + controlled tone, independent gain/mute, peak/RMS and explicit per-input recovery |
| 🎬 | Local recording | H.264 + AAC in MKV, encoded and muxed by libobs |
| 🎨 | Scene editor | Multiple scenes and reusable sources; layer position, size, visibility and order; editable original overlays |
| 🧩 | Overlay engine | Native text, managed images/video, shapes, widgets and original presets; per-layer fade/slide/scale through CLI/MCP |
| ↔️ | Canvas variants | Independent landscape/portrait layer layouts at 960 × 540 and 540 × 960, with aspect-preserving fit |
| 🔌 | Source recovery | Availability checks, controlled output stop and explicit reconnection |
| 🤖 | Agent control | Local MCP and CLI commands, shared state and structured errors |
| 💾 | Project state | Version 4 for H11 definitions; existing projects remain v3, with v1–v3 loading and stable scene/source/layer IDs |

## 🚀 Get started

You need an Apple Silicon Mac, Xcode with the Metal toolchain, Rust/Cargo and Python 3. FFmpeg/ffprobe are needed for the media verification scripts.

The development environment has been exercised on **macOS 27.2**, Apple M5 Pro, Rust 1.99.1 and Python 3.13.15. The binary targets macOS 15.0+, but that entire OS range has **not** been tested. Allow roughly 4 GB for dependencies and build artifacts.

```sh
git clone https://github.com/luisfarfan/motive.git
cd motive
python3 scripts/bootstrap.py
python3 scripts/bundle.py
open target/Motive.app
```

The bootstrap fetches pinned, checksum-verified **OBS Studio 33.0.1** and its full source tree, plus **SIMDe 0.8.2**, into `.deps/`. It does not install global packages. Cargo.lock pins **GPUI Kit 0.10.0** and its **GPUI 0.3.12** dependency.

**Keep the app in this checkout.** This ad-hoc-signed development bundle links to `.deps/` using local paths. A self-contained, signed and notarized release is still future work. Launch the bundle rather than `cargo run` so the official muxing helper is in the expected location.

Ad-hoc rebuilds change the code identity and can require macOS permissions again. If you already have a local Apple Development identity, use `python3 scripts/bundle.py --sign-identity "YOUR_EXISTING_IDENTITY"` for a stable development identity. The script never creates certificates or changes the keychain. Close Motive before rebuilding.

### Make your first recording

1. Start with the built-in pattern, or click **Abrir fuente de prueba** and **Capturar fuente de prueba** for a controlled window.
2. Use **Elegir ventana**, **Elegir cámara** or **Elegir micrófono** to select a source. Complete any normal macOS permission prompts. Only select content you intend to capture.
3. Check that the preview is ready and the audio level responds. If Stage Manager hides the selected window, show that window to let capture receive its first frame. **Audio: tono de prueba** supplies an owned 440 Hz test fixture when a physical microphone is unnecessary.
4. Click **Grabar**, then **Finalizar salida**. Wait for `idle`; recordings are saved under `var/recordings/`.
5. Switch canvas orientation while idle. **Guardar proyecto** and **Restaurar proyecto** use `var/project.json`.

Window restoration requires a unique application bundle ID and window title; ambiguous or missing matches need an explicit selection. Camera and microphone selections use device UIDs. No source is selected automatically at launch. The global Audio Mixer has its own version-1 store (`save_audio_mixer` / `load_audio_mixer`), separate from project v3/v4 and output profiles.

Recording defaults to **Apple VideoToolbox hardware H.264** when available, with x264 fallback before output starts. Recording and local RTMP share validated encoder/bitrate/CBR/keyframe/reordering profiles, stored separately from project v3/v4 with explicit save/load. Canvas dimensions and 30 FPS remain fixed. `encoders`, `output_capabilities` and `output_profiles` report the effective configuration; `set_encoder` edits the selected recording profile (also used by RTMP when it selects that profile). See [hardware measurements](docs/videotoolbox-verification.md) and [H7 output verification](docs/h7-output-verification.md) for contracts, reproduction and limits.

### When a source disappears

The core checks source health once per second, and before commands. Audio Mixer inputs isolate a failed capture and keep the remaining mix/output running until explicit `reconnect_audio_input`; inspect `audio_mixer.issues`. The legacy single-input selector retains the controlled-stop policy described below. A missing window/device, revoked permission or stalled microphone data produces a structured issue. If an output is active, Motive requests a controlled stop and retains the reason. **Reconectar fuentes** retries the selected sources while idle; it never starts recording automatically. A closed window must be opened and selected again.

Silence is distinct from missing audio packets. Camera health also watches actual incoming frames; a static image is not itself a stall. Recovery is tracked per source, so changing audio cannot acknowledge a failed window. See [scene verification](docs/scene-graph-verification.md) for tested behavior and hardware limits.

### Build a composition

Use **Añadir fuente** to add a window, webcam, overlay or existing source. Select a layer on the canvas or in the layer list; drag, resize or edit its numeric transform. The eye toggles visibility and the layer menu changes order. Command+Z / Shift+Command+Z undo and redo compatible transform edits; a concurrent CLI/MCP change invalidates that local history. Removing a layer does not implicitly delete its shared source; release unused sources with the shared `remove_source` command.

The native studio has light/dark themes, compact layout, real audio level and explicit capture/output recovery. Gesture previews commit once on release to avoid rebuilding scenes for every pointer event. See [native UI verification and shortcuts](docs/ui-native-verification.md) for evidence and current limits.

Geometry, layer order and overlay color can change during recording. Scene selection supports official OBS **Cut and Fade** during recording/local RTMP, with target preparation, shared capture resources and explicit cancellation. Graph edits wait for the transition to finish; adding/removing capture resources and directly changing layer visibility require a stopped output. Each orientation has its own transforms. See [H9 contracts and real verification](docs/h9-scene-transitions-verification.md).

H11 extends the core with text, transparent images, rectangles/circles, local video, countdowns, lower thirds and alerts. Original lower-third, starting-soon and BRB presets include both layouts. Source events and per-layer fade/slide/scale run on the native media clock. Layer animations and scene Cut/Fade are mutually exclusive in this increment. Imported video is visual only: its audio and monitoring stay off. Browser/HTML/JavaScript overlays are unavailable pending isolation and lifecycle work. See the [H11 verification report](docs/h11-overlay-verification.md) for measured behavior and open regressions.

## 🧠 One production, three controls

```text
 Native GPUI interface ─┐
 Local CLI ────────────┼──► Production core ──► libobs ──► Recording / loopback
 MCP stdio adapter ────┘          │                │
                         versioned state      media clock + frames
```

The app owns one engine. CLI and MCP connect to its Unix socket at `var/run/motive.sock` (directory mode `0700`, socket mode `0600`). Commands run on the same main-thread owner. MCP carries control messages and metrics; it does not carry video or drive the media clock.

```sh
./target/debug/motive ctl '{"op":"status"}'
./target/debug/motive ctl '{"op":"devices"}'
./target/debug/motive ctl '{"op":"select_source","window_id":123}'
./target/debug/motive ctl '{"op":"select_camera","id":"CAMERA_UID_FROM_DEVICES"}'
./target/debug/motive ctl '{"op":"select_audio","id":"MICROPHONE_UID_FROM_DEVICES"}'
./target/debug/motive ctl '{"op":"start_recording"}'
./target/debug/motive ctl '{"op":"stop_output"}'
./target/debug/motive ctl '{"op":"reconnect_sources"}'
```

Replace example IDs with values from `devices`. A `null` window ID restores the generated pattern; audio accepts `none`, `tone` or a listed device UID.

New scene operations use the same core. Read the returned graph to obtain IDs:

```sh
./target/debug/motive ctl '{"op":"add_source","scene_id":"scene-1","name":"Webcam","source":{"kind":"camera","device_id":"CAMERA_UID_FROM_DEVICES"}}'
./target/debug/motive ctl '{"op":"set_transform","scene_id":"scene-1","layer_id":"LAYER_ID_FROM_STATE","variant":"horizontal","transform":{"x":600,"y":48,"width":320,"height":180,"visible":true,"order":2}}'
./target/debug/motive ctl '{"op":"set_overlay_color","source_id":"overlay","color":16739166}'
./target/debug/motive ctl '{"op":"save_project"}'
```

The global Audio Mixer uses the same running core and stays independent of scene Cut/Fade:

```sh
./target/debug/motive ctl '{"op":"add_audio_input","name":"Microphone","source":{"kind":"microphone","device_id":"UID_FROM_DEVICES"}}'
./target/debug/motive ctl '{"op":"add_audio_input","name":"Test tone","source":{"kind":"tone"}}'
./target/debug/motive ctl '{"op":"audio_mixer"}'
./target/debug/motive ctl '{"op":"set_audio_gain","input_id":"ID_FROM_MIXER","gain_db":-12}'
./target/debug/motive ctl '{"op":"set_audio_mute","input_id":"ID_FROM_MIXER","muted":true}'
./target/debug/motive ctl '{"op":"save_audio_mixer"}'
```

Adding the same UID reuses its channel and controls. Gain/mute and individual
recovery work live; adding/removing channels or loading the store requires idle.
Monitoring stays off. Per-input meters are post-fader/pre-manual-mute; the final
mix meter is post-mute and detects saturation before libobs clamps the output.
See the [UI/CLI/MCP contract](docs/h10-audio-ui-contract.md) and
[real audio verification](docs/h10-audio-verification.md).

H11 exposes typed overlay definitions and runtime state through that same owner:

```sh
./target/debug/motive ctl '{"op":"overlay_capabilities"}'
./target/debug/motive ctl '{"op":"overlay_state"}'
./target/debug/motive ctl '{"op":"overlay_presets"}'
```

Use the returned IDs and the [overlay integration contract](docs/h11-overlay-ui-contract.md) for complete create/update/event/animation schemas. Import only files explicitly placed in `var/imports`, then pass their basename to `import_asset`; use the returned managed asset ID in definitions. Imports and animations return operation IDs whose terminal state must be observed. GPUI must dispatch these same typed commands; it must not create a second renderer, timer, asset broker or mixer. The [architecture review](docs/h11-architecture-review.md) documents persistence, memory and the same-user security boundary.

Agents control production through CLI/MCP, never by editing project files or automating clicks. Project restoration is explicit after launch with `load_project`.

For an MCP client, use an absolute path to your checkout:

```json
{
  "mcpServers": {
    "motive": {
      "command": "/absolute/path/to/motive/target/debug/motive",
      "args": ["mcp"]
    }
  }
}
```

<details>
<summary><strong>Available MCP tools</strong></summary>

`status` · `devices` · `set_overlay` · `set_variant` · `select_source` · `select_camera` · `select_audio` · `reconnect_sources` · `start_recording` · `stop_output` · `save_project` · `load_project`

`scenes` · `configure_transition` · `cancel_transition` · `create_scene` · `rename_scene` · `remove_scene` · `select_scene` · `add_source` · `remove_source` · `add_layer` · `remove_layer` · `set_transform` · `set_overlay_color` · `reconnect_source` · `snapshot` · `shutdown` · `set_test_window`

`audio_mixer` · `add_audio_input` · `remove_audio_input` · `set_audio_gain` · `set_audio_mute` · `disconnect_audio_input` · `reconnect_audio_input` · `save_audio_mixer` · `load_audio_mixer`

`encoders` · `set_encoder`

`output_capabilities` · `output_profiles` · `upsert_output_profile` · `remove_output_profile` · `select_output_profile` · `save_output_profiles` · `load_output_profiles` · `configure_stream` · `preflight_output` · `start_stream` · `recover_output`

`cancel_output` · `request_shutdown` · `credential_status` · `select_stream_credential`

`overlay_capabilities` · `overlay_state` · `list_assets` · `import_asset` · `remove_asset` · `create_overlay` · `update_overlay` · `overlay_event` · `animate_overlay` · `cancel_overlay_animation` · `overlay_presets` · `instantiate_overlay_preset`

Responses include the shared PID/revision, source issues and real engine counters. Inputs reject unknown fields. Disconnecting the MCP client leaves the production engine running.

</details>

The API accepts no arbitrary output paths, public stream URLs, shell commands or stream-key values. `configure_stream` accepts only RTMP/RTMPS and an unprivileged port at **127.0.0.1**. `cancel_output` queues safe deferred cancellation (`cancel_pending`) while a handshake finishes; `stop_output` retains its immediate-cancellation guard. Native worker completion is checked through a pinned lifecycle patch to the official OBS output module.

Credentials can be enrolled locally in **macOS Keychain** using the signed terminal helper; CLI/MCP see only opaque references, bound to an RTMPS port. Trusted RTMPS delivery remains pending: OBS 33.0.1 does not expose an isolated development-CA setting on macOS. See [H8 verification and security limits](docs/h8-streaming-verification.md). No public destination is enabled. The legacy CLI-only `start_local_stream` still sends MPEG-TS to **127.0.0.1:19350** using its original libx264 settings.

If a forced shutdown leaves a stale socket, first confirm no Motive process remains and `ctl` cannot connect, then remove only `var/run/motive.sock`. Motive never unlinks another running instance's socket.

## 🧪 Verification

We record what ran on real hardware and keep limitations explicit. Build success is not evidence of working media capture.

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/verify_control.py
python3 scripts/verify.py
python3 scripts/verify_scenes.py --camera-id 'YOUR_CAMERA_UID'
python3 scripts/verify_output_recovery.py
python3 scripts/verify_vt_stop.py
python3 scripts/verify_rtmp.py
python3 scripts/verify_rtmps.py
python3 scripts/verify_connect_stop.py
python3 scripts/verify_h8_lifecycle.py
python3 scripts/verify_h8_keychain.py
python3 scripts/verify_profiles_restart.py
```

The integration scripts require the app to be open and idle. `verify.py` also requires the owned test window and normal screen-capture permission. It validates decoded video/audio, source pixels outside the overlay, overlay motion, portrait layout and a loopback receiver. It records for at least 65 seconds.

H11 has 49 passing Rust tests, clean Clippy and 13 decoded clips covering native overlays, recording/RTMP, CLI/MCP and lifecycle. The current regression manifests record 14 distinct suites passing and five still failing: H1 camera content, VideoToolbox lag, window preparation in scenes and two H9 suites. Causes remain under investigation; these results do not close H11 acceptance. Follow [H11 reproduction and evidence](docs/h11-overlay-verification.md), including its local Python requirements and exclusive device/bundle lock. Never run physical suites simultaneously in different worktrees.

See [H1 verification](docs/h1-verification.md) and [scene-graph verification](docs/scene-graph-verification.md) for device tests, recovery behavior, prerequisites and evidence. The output-recovery test deliberately terminates only Motive's own mux helper. Captures, device inventories and runtime logs stay under ignored `var/`; they are not published with this repository.

## 🗺️ Direction and boundaries

- **Now:** scenes with Cut/Fade, a global Audio Mixer and native overlay/widget controls in one production core; H11 acceptance is conditional on open regressions.
- **Next:** close those regressions, integrate the GPUI overlay contract, test removable-device recovery and longer sessions.
- **Later:** isolated browser overlays, richer typography/effects, a distributable bundle, simultaneous variants and platform streaming.

The preview copies new BGRA frames through CPU memory into GPUI; it is not zero-copy. The core supports up to 8 scenes, 16 visual sources, 32 layers and 4 video sources, with one active canvas and one output. The 256 MiB visual allocation estimate is not an RSS cap: hidden decoders and resource-replacement peaks still consume memory. There are no cloud services, payments or marketplace features.

Competitive research prioritizes official documentation, open-source code and observable behavior. REA is optional research tooling, **never a product dependency**. Motive's design and implementation are independent; no proprietary Meld code, assets or designs are included.

## 🛠️ Contributing

Start with [AGENTS.md](AGENTS.md), [the plan](docs/plan.md) and [architecture decisions](docs/decisions.md). Project notes are currently in Spanish. Keep changes focused and include reproducible evidence for media behavior. Never commit recordings, device inventories, stream keys or downloaded SDK bundles.

| Directory | Responsibility |
|---|---|
| `src/main.rs` | Application startup and CLI/MCP dispatch |
| `src/ui/` | Native studio, theme, components and guarded canvas editor |
| `src/core.rs` | Shared commands, health policy and project state |
| `src/audio.rs` | Typed global audio registry, meter/health contracts and version-1 persistence validation |
| `src/overlays/` | Typed definitions, managed imports, widgets/presets and shared overlay controls |
| `src/output.rs` | Typed output profiles and loopback endpoint validation, separate from scene v3/v4 |
| `src/scene.rs` | Stable scene graph, independent layouts and validation |
| `src/control.rs` | Local socket, CLI and MCP adapter |
| `src/engine.rs` | Main-thread Rust ownership of the native engine |
| `native/engine.m` | libobs, ScreenCaptureKit and AVFoundation integration |
| `native/graph.inc` | Native scenes, source reconciliation and camera frame health |
| `native/overlays/` | OBS source wrappers, widget clocks and per-layer animation lifecycle |
| `scripts/` | Pinned bootstrap, bundle and real-media checks |

## 💚 Built on open source

Motive is licensed under **[GPL-3.0-or-later](LICENSE)**. It builds on [OBS Studio](https://github.com/obsproject/obs-studio), [GPUI Kit](https://github.com/longbridge/gpui-kit) and their communities. Third-party code retains its own licenses; see [third-party notes](docs/third-party.md).

<p align="center"><sub>Made for creators who want their production to stay on their machine.</sub></p>
