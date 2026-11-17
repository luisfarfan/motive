# H10 — Global audio mixer with libobs

Implemented on the independent `codex/h10-audio-mixer` worktree, based on H9
`bd23c63`. No changes to `src/main.rs`, `src/ui/` or `design/`. No public
transmission, push, merge, release, global installation or macOS permission
modification. Device/bundle use is coordinated with the GPUI worktree through
the shared `var/run/physical-test.lock` and coordination log.

## Architecture and official APIs

H9 owned one `obs_source_t` on global channel 1, selected as either microphone
or looping WAV. A capture callback reported a clamped peak and sample flow.
Recording and RTMP already encoded mix 0, while Cut/Fade used video channel 0.

H10 replaces that single audio owner with a bounded registry of eight inputs on
global channels 1..8. `core::audio` owns typed source identity, stable IDs and
validated controls. The native registry uses one official CoreAudio input per
physical UID and one owned tone source. Repeated add reuses the existing channel;
restoration reconciles by source identity even when persistent IDs change.

`obs_source_set_volume` and `obs_source_set_muted` enqueue native audio actions.
`obs_source_set_audio_mixers(source,1)` routes each input to mix 0. Libobs alone
resamples, sums, aligns samples, applies the actions and feeds the existing AAC
encoder. Gain/mute and individual recovery never reset output encoders or visual
sources. Monitoring is explicitly `OBS_MONITORING_TYPE_NONE` on every creation.

`obs_volmeter` supplies post-fader/pre-manual-mute sample peak and RMS per input,
plus pre-fader input peak. The raw mix callback uses `allow_clipping=true` to
observe the native sum before the output clamp. Its bounded measurement loop
never modifies or returns replacement samples. Callbacks hold short metric locks;
the existing owner thread performs lifecycle/control operations. Detaching
callbacks synchronizes their completion before freeing metric state.

The tone is an owned source fixture, fixed at 440 Hz and −24 dBFS stereo,
implemented through `obs_source_output_audio`. Its sample position defines phase
and timestamps, using the monotonic host clock; it does not derive time from
UI/MCP polling. It skips elapsed blocks after a prolonged scheduling delay
instead of producing an unbounded catch-up burst. This is a source producer,
not a parallel DSP mixer. Mic timestamps from CoreAudio pass through unchanged.

Primary sources, checked against the pinned OBS 33.0.1 tree:

- [Source APIs and audio actions](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-source.c).
- [Native audio summation](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-audio.c).
- [Official volume meter](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-audio-controls.c).
- [Unclamped audio observation](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/media-io/audio-io.c).
- [CoreAudio capture and device lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-audio.c).
- [Official test-source producer pattern](https://github.com/obsproject/obs-studio/blob/33.0.1/test/test-input/test-sinewave.c).

Source hashes are retained in `var/evidence/h10-research.json`. No REA or
proprietary code/assets were used. The H8 output-module patch is unchanged.

## First real increment

Before adding persistence/recovery, `verify_h10_audio.py` recorded the physical
built-in mic hearing an owned 997 Hz speaker fixture plus the independent
440 Hz source. Both frequencies were present in decoded AAC. A requested −12 dB
tone change measured **−12.066 dB**. Muting the mic reduced its 997 Hz amplitude
from about 0.0479 to 8.8e−9 in the mono-decoded pilot, while 440 Hz remained.
Unmute restored it to about 0.0477. Maximum mono-decoded sample amplitude was
0.1514, and the observed native mix had zero saturated blocks. Controls did not
change either source's native instance ID.

That pilot's app SHA-256 is
`8d3c2eca8dbc5626bea3f4b685c3e2ee161cf784880e428fb5d859439a9ae651`.
The report is `var/evidence/h10-pilot.json`, with its referenced recording.
FFmpeg's mono downmix in this pilot adds approximately 3 dB for identical stereo
channels; the expanded meter checks decode the left channel directly.

The first retained pilot failed an exact spectral gain assertion with the old
looped WAV. Native meters showed the requested 12 dB change, but a one-second
decoded window crossed a phase discontinuity and measured only 9.08 dB. A
bandpass check also found a short amplitude dip. The evidence remains under
`h10-pilot-history/01-looped-file/`. Replacing the media-file loop with the
sample-positioned source made the same assertion pass; the failed run was not
relabelled as success or discarded.

## Extended acceptance and regressions

`verify_h10_mixer.py` passed on the final expanded implementation, using the same
signed executable for recording and loopback RTMP, followed by a real restart.
App SHA-256: `85caaa31774b78c28f97706ba46ac8df493260e28d9541f004b6c976830311b7`.
The report and full exchanges are in `var/evidence/h10-mixer.json`.

| Observation | Recording MKV | RTMP → FFmpeg FLV |
|---|---:|---:|
| Decoded audio duration | 31.275 s | 31.659 s |
| Decoded video frames | 940 | 951 |
| Tone gain change, requested −12 dB | −12.014 dB | −12.004 dB |
| Physical mic gain change, requested −12 dB | −12.040 dB | −11.963 dB |
| Tone isolated RMS vs native meter | +0.017 dB | +0.018 dB |
| Mic isolated RMS vs native meter | +0.010 dB | +0.756 dB |
| Maximum decoded sample peak | −18.18 dBFS | −13.13 dBFS |
| Native mix saturated blocks during acceptance | 0 | 0 |
| Audio packets / maximum PTS gap | 1467 / 22 ms | 1484 / 22 ms |
| Maximum interior video frame PTS gap | 34 ms | 34 ms |
| Maximum video gap including finalization | 34 ms | 133 ms (tail) |
| Distinct decoded intermediate Fade colors | 37 | 38 |
| Median process CPU | 38.9% | 39.1% |
| Median RSS | 160.8 MiB | 164.0 MiB |

Measurements use the debug bundle on the development Apple M5 Pro/macOS 27.2.
CPU is process-time delta / elapsed time (one core = 100%), excluding receiver,
mux helper and speaker playback. The GPUI worktree held off compilation and
physical tests during this pass. This is an observation, not a performance
comparison. AAC is stereo 48 kHz; spectral/RMS analysis decodes the left channel
without FFmpeg's mono-downmix gain. Physical acoustic variation remains in the
measurements. All files decode without FFmpeg errors.

Both outputs include independently audible 440/997 Hz components, both fader
changes, mic mute/unmute, tone mute/unmute, explicit native mic release/reopen,
two Cuts and two 1 s Fades. Mic/tone isolation compares the decoded signal to its
own native RMS meter. During intentional mic disconnection, every tested 100 ms
window retained the 440 Hz component (minimum amplitude 0.007898 / 0.007907).
Recovery and the complete Cut/Fade sections also retain that component in every
100 ms window; raw per-window extrema are in the report. Native tone instance,
visual source/scene-build counters, output path and PID remain unchanged, and
encoded-frame counters increase. Only the explicitly reopened mic gets a new
native instance. Audio PTS remain increasing without a clock reset or packet gap.
Decoded stripe colors independently prove that video changed and blended.

The RTMP finalization tail remains the documented H7–H9 issue: 133 ms at the end
of this run; all interior video gaps are at most 34 ms. The verifier retains the
tail rather than describing the file as uniformly gap-free. Two initial MKV
video packets have no DTS with B-frame reordering; available DTS are increasing,
and all decoded video frame PTS and audio packet PTS are checked.

A separate deliberately saturated recording raised `AUDIO_MIX_CLIPPING` with
144 observed full-scale blocks and a current native mix peak of +0.829 dBFS.
Decoded AAC peak was +0.067 dBFS after the standard output clamp/codec. The
warning did not stop the encoder or apply a hidden limiter. This file is labelled
`intentional_clipping`, separate from the zero-clipping acceptance files.

CLI and MCP see the same PID/revision/store. New tools and strict rejected
arguments were checked. Adding the same physical UID retained the original
channel and instance; rejected additions left store and instance counts intact.
Saving/loading restored controls without recreating healthy captures. Removing,
re-adding in reverse order and loading the saved store reused captures under the
persisted IDs. Loading a deliberately disconnected channel reopened it. A new
process began with no audio inputs; explicit load restored both original IDs,
gains and mute state. Scene v3 and output-profile v1 files remained byte-identical
while audio was saved/restored, and both documents restored normally.

**20 Rust tests, Clippy with warnings denied, and formatting pass.** The final
serial H1–H9 real regression gate is pending the next exclusive device window.

Two expanded-verifier failures are retained: the initial missing-DTS assumption
(`02-first-expanded-timestamps`) and an absolute source-creation counter that
incorrectly assumed a fresh process on retry (`03-retry-counter`). The latter now
checks the increment from its initial snapshot. Neither required a media-engine
change or weakening the gain/mute/continuity assertions.

## Reproduction

Coordinate exclusive use of the signed bundle, camera and microphone with other
worktrees before launching. Use the existing development signing identity and
normal macOS permissions. Device IDs remain local, never committed.

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/bundle.py --sign-identity 'EXISTING_LOCAL_IDENTITY'
# Open this worktree's exact target/Motive.app path, then run:
python3 scripts/verify_h10_audio.py --microphone-id UID_FROM_DEVICES
# Start with an empty mixer before the extended suite:
python3 scripts/verify_h10_mixer.py --microphone-id UID_FROM_DEVICES
python3 scripts/verify_h10_regressions.py --camera-id UID_FROM_DEVICES --microphone-id UID_FROM_DEVICES
```

Tests use only owned visual fixtures, controlled speaker playback, the expressly
selected devices, local recordings and RTMP to 127.0.0.1. Media, UIDs, complete
control exchanges and runtime logs remain in ignored `var/`. See the
[UI integration contract](h10-audio-ui-contract.md) for commands/types/states and
[system-audio follow-up](h10-system-audio-next.md) for the independent next scope.

## Limits

- Physical USB unplug/replug, permission revocation while recording, device
  sleep/wake and long-session clock drift are not established by a controlled
  native release/reopen. Do not present that operation as a hardware hot-unplug.
- Sample peaks and AAC decoded peaks are not a true-peak or loudness standard;
  leave headroom. Clipping produces structured warnings, not a hidden limiter.
- No system capture, monitoring, filters, voice effects, per-scene audio,
  multitrack routing or master fader is included. One 48 kHz stereo mix feeds
  one output at a time, retaining H9's output constraints.
- Source health has the owner's existing polling latency. It distinguishes
  silence from absent packets, but does not prove end-to-end acoustic latency.
- Existing VideoToolbox finalization-tail and trusted-RTMPS limitations remain.
  This increment does not claim a macOS compatibility matrix or release bundle.
