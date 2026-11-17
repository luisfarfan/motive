# H10 — Shared Audio Mixer contract

Real acceptance and final limits are recorded in the H10 verification report.
The implementation lives in the H10 worktree. GPUI should call
`Production::apply(Command, "UI")` on its existing owner and read
`Production::audio_mixer_status()` / `status.audio_mixer`. Do not create OBS
sources, audio threads, gain/mute state or persistence in the UI.

## Initial interface

`core::audio::{AudioSource, AudioInput, AudioStore}` owns the desired model.
An input has a stable `audio-N` ID, display name, typed source, `gain_db` and
`muted`. `source` is `{kind:"tone"}` or
`{kind:"microphone",device_id:"explicit UID from devices"}`. Adding the same
source returns the existing channel and preserves its controls. One capture per
physical UID, one controlled tone; currently at most eight inputs.

| Command | Arguments | Initial contract |
|---|---|---|
| `audio_mixer` | none | Read-only PID, revision, desired store and native runtime |
| `add_audio_input` | `name`, `source` | Idle only; default −6 dB; reuses source identity |
| `remove_audio_input` | `input_id` | Idle only; explicitly releases the source |
| `set_audio_gain` | `input_id`, `gain_db` | Finite −60..24 dB; works while recording/streaming |
| `set_audio_mute` | `input_id`, `muted` | Works live; retains capture, gain and timestamps |
| `disconnect_audio_input` | `input_id` | Releases only that native capture, including live; retains desired channel |
| `reconnect_audio_input` | `input_id` | Explicit release/reopen, including live; preserves ID/gain/mute; never starts output |
| `save_audio_mixer` | none | Atomic explicit save to `var/audio-mixer.json` v1 |
| `load_audio_mixer` | none | Idle only; validates entire file before mutation; reuses present device identities |

CLI JSON uses `op`; MCP tools use the same name and arguments without `op`.
All inputs reject missing/extra fields, wrong types and unsupported source kinds.
Callers should use IDs from the returned store. Native `instance_id` is a
process-scoped lifecycle diagnostic, not a persistent ID.
Join store and runtime by `id`, never by array index: native slot order can differ
after loading an earlier document. A query has PID/revision; each mutation returns
the full shared `state`. A failed mutation also returns the current mixer so
callers can render a failed reopen without inventing success or rolling back
unrelated controls.

## Meter semantics

The per-input meter is **post-fader, pre-manual-mute**, using the official
`obs_volmeter` in OBS 33.0.1. `peak_dbfs[2]` is sample peak and `rms_dbfs[2]`
is RMS per callback/channel. `input_peak_dbfs[2]` is pre-fader. A muted input's
meter deliberately remains visible; show a separate mute indicator.
These are signal measurements, not perceived loudness/LUFS or true peak.

`runtime.mix` measures libobs mix 0, **post-fader/post-mute, pre-clamp**, through
the official raw audio callback with `allow_clipping=true`. It only observes
samples: it does not mix, alter, re-clock or encode them. Normal encoder clamp
and AAC behavior remain libobs-owned. It reports sample peak/RMS, frames,
native timestamp and blocks reaching full scale. The two input peaks cannot
simply be added to reconstruct the final peak (phase matters).

Values are dBFS; JSON `null` means silence (negative infinity), not 0 dBFS.
`stale` and `age_ms` distinguish absent/recent delivery from silence with fresh
packets. Meters may update faster than UI/status polling, and changes take
effect on libobs' audio timeline. Do not animate them as if every snapshot
covered the whole time since the preceding UI poll.

Monitoring is always `off`; no monitoring control, filters, system audio or
per-scene routing is exposed. Video Cut/Fade continues on channel 0; audio
inputs on channels 1..8 feed mix 0 continuously. Output encoders and scene
resources are not replaced by gain/mute operations.

The legacy `select_audio` and `project.audio` remain supported by the same
registry for H1–H9. They are compatibility controls for the previous main input,
not a second audio engine. New GPUI mixer controls should use the typed API.

## Health, persistence and recovery

Runtime types are `AudioRuntime`, `AudioInputRuntime`, `AudioPhase`, `AudioLevels`,
`AudioIssue` and `AudioIssueCode`. Native callbacks only update metrics; the owner
polls health on the existing cadence (about one second) and before commands.
Revision changes on lifecycle/control changes, not on every meter sample.

| Phase / issue | Meaning / action |
|---|---|
| `warming` / `AUDIO_NOT_READY` | Source created; waiting for packets; preflight rejects start |
| `ready` | Fresh sample delivery, including digital silence |
| `disconnected` / `AUDIO_DISCONNECTED` | Intentional capture release; informational; starting with remaining inputs is allowed |
| `failed` / `DEVICE_UNAVAILABLE` | Explicit UID disappeared; no fallback to the default device |
| `failed` / `MICROPHONE_PERMISSION_DENIED` | Restore normal macOS permission, then reconnect |
| `failed` / `AUDIO_STALLED` | No recent packets (3 s), after a 4 s initial grace; reconnect explicitly |
| `failed` / `AUDIO_CREATE_FAILED` | libobs failed to create the source/meter |
| `AUDIO_STATE_UNAVAILABLE` | Native snapshot unavailable (`runtime.available=false`); preflight rejects start; restart the studio |
| `AUDIO_INPUT_CLIPPING` | Warning: pre-fader input reached full scale; lower device gain |
| `AUDIO_MIX_CLIPPING` | Warning: native sum reached full scale; lower input gain |
| `AUDIO_HEADROOM_LOW` | Warning: current native sum above −1 dBFS |

Each issue includes `input_id` (null for the overall mix), `code`, `severity`
(`info`, `warning`, `error`) and a recovery hint. Render these fields directly;
do not infer device health from meter amplitude or the display name.

Clipped-block counters latch observations for the lifetime of the native input or
mix. They are not counts of individual clipped samples, nor evidence of clipping
in every later recording. The first two clipping warnings remain while their
counters are nonzero; the low-headroom warning follows current samples. No hidden
limiter, normalization or automatic gain is applied. A latched mix-clipping
warning takes precedence over low headroom. Meter sample peaks do not
predict all AAC/inter-sample overshoot.

A failed channel is removed from mix 0 and remains latched until explicit
reconnection. Other mixer channels and the active output continue. Reopening
waits for the old native capture to finish destruction, preventing overlapping
captures of one UID. The original single-input legacy selector keeps its former
controlled-stop/recovery policy; use the mixer commands for the new flow.
Visual/output failures retain H1–H9's existing stop policy.

The store contains only `{version:1,next_id,inputs}`. It does not extend project
v3 or output-profile v1, store device names from inventory, or persist levels,
permissions, faults, timestamps, native instance IDs, disconnected state, or
monitoring. No capture auto-restores at launch. Loading while idle reuses healthy
captures, retries failed/disconnected desired entries, and retains unavailable
entries with their stable IDs and structured failure. Inspect returned issues:
successful document load does not claim that every physical device is ready.
Saving scenes/profiles and loading audio do not rewrite the other files.

The controlled tone is a fixed 440 Hz, −24 dBFS stereo source fixture using
`obs_source_output_audio`; phase and timestamps follow sample position. Its
producer is not a mixer. Libobs alone resamples, applies gain/mute, combines
sources and feeds the shared 48 kHz stereo mix to existing recording/RTMP
encoders. Source timestamps and offset remain untouched by controls.
