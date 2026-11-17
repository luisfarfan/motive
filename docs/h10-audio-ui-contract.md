# H10 — Shared Audio Mixer contract

Work in progress; real acceptance and final limits are recorded separately.
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

CLI JSON uses `op`; MCP tools use the same name and arguments without `op`.
All inputs reject missing/extra fields, wrong types and unsupported source kinds.
Callers should use IDs from the returned store. Native `instance_id` is a
process-scoped lifecycle diagnostic, not a persistent ID.

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
