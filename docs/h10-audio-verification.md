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
Snapshots copy metrics under the lock and perform JSON allocation after unlock.

The tone is an owned source fixture, fixed at 440 Hz and −24 dBFS stereo,
implemented through `obs_source_output_audio`. Its sample position defines phase
and timestamps, using the monotonic host clock; it does not derive time from
UI/MCP polling. It skips elapsed blocks after a prolonged scheduling delay
instead of producing an unbounded catch-up burst. This is a source producer,
not a parallel DSP mixer. Mic timestamps from CoreAudio pass through unchanged.
Block arithmetic divides before scaling to nanoseconds, avoiding the intermediate
integer overflow of multiplying a multi-day frame count by one billion. This
arithmetic review does not substitute for a long-session physical test.

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
The original report is retained in
`var/evidence/h10-pilot-history/04-increment1-success/h10-pilot.json`, with its
referenced recording. `var/evidence/h10-pilot.json` holds the later final CLI run.
FFmpeg's mono downmix in this pilot adds approximately 3 dB for identical stereo
channels; the expanded meter checks decode the left channel directly.

The first retained pilot failed a spectral gain assertion with the old looped
WAV. Native meters showed the requested 12 dB change, but a one-second coherent
frequency projection measured only 9.08 dB. The deterministic source subsequently
passed. A later run also showed a startup phase change with the deterministic
source: the whole-second projection reported −6.07 dB while all 100 ms spectral
windows retained the tone. The earlier attribution to WAV looping was not
established and is withdrawn; the startup phase change's cause remains unisolated.

The final spectral estimator measures every 100 ms Hann-windowed magnitude and
combines their squared amplitudes, avoiding cancellation between windows with
different phase. It excludes no low window. Applied to that retained failure,
it measures −12.058 dB, agreeing with the native −12 dB control. The acceptance
range remains −13..−11 dB. Separate complete-section 100 ms continuity, decoded
RMS/peaks and packet-timestamp checks remain mandatory. Coherent measurements are
also retained for comparison. Synthetic checks validated only the estimator;
all acceptance signals still come from actual recordings. Evidence remains in
`h10-pilot-history/01-looped-file/` and `06-startup-phase/`.

## Extended acceptance and regressions

`verify_h10_mixer.py` passed on the final expanded implementation, using the same
signed executable for recording and loopback RTMP, followed by a real restart.
App SHA-256: `f3062b1802b6343977bcf7cbae634f0bb00e4677455a2d593de7b64e5dd70f44`.
The report and full exchanges are in `var/evidence/h10-mixer.json`.

Local media retained for review (private, ignored by Git):

- [Final CLI recording](../var/recordings/motive-1794888748887069.mkv)
- [MCP recording](../var/recordings/motive-1794889136118145.mkv)
- [RTMP receiver capture](../var/evidence/h10-stream-1794889175297679000.flv)
- [Recording after restart/load](../var/recordings/motive-1794889221695854.mkv)
- [Intentional clipping only](../var/recordings/motive-1794889215174242.mkv)

| Observation | Recording MKV | RTMP → FFmpeg FLV |
|---|---:|---:|
| Decoded audio duration | 37.568 s | 37.760 s |
| Decoded video frames | 1129 | 1134 |
| Tone gain change, requested −12 dB | -11.989 dB | -12.087 dB |
| Physical mic gain change, requested −12 dB | -12.005 dB | -11.968 dB |
| Tone isolated RMS vs native meter | +0.014 dB | -0.025 dB |
| Mic isolated RMS vs native meter | +0.381 dB | +0.714 dB |
| Maximum decoded sample peak | -11.33 dBFS | -15.18 dBFS |
| Native mix saturated blocks during acceptance | 0 | 0 |
| Audio packets / maximum PTS gap | 1762 / 22 ms | 1770 / 22 ms |
| Maximum interior video frame PTS gap | 34 ms | 34 ms |
| Maximum video gap including finalization | 34 ms | 67 ms |
| Distinct decoded intermediate Fade colors | 38 | 39 |
| Median process CPU | 44.2% | 44.5% |
| Median RSS | 103.7 MiB | 105.8 MiB |

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
window retained the 440 Hz component (minimum amplitude 0.007906 / 0.007905).
Recovery and the complete Cut/Fade sections also retain that component in every
100 ms window; raw per-window extrema are in the report. Native tone instance,
visual source/scene-build counters, output path and PID remain unchanged, and
encoded-frame counters increase. Only the explicitly reopened mic gets a new
native instance. Audio PTS remain increasing without a clock reset or packet gap.
Decoded stripe colors independently prove that video changed and blended.

The RTMP finalization tail remains the documented H7–H9 issue: 67 ms at the end
of this run; all interior video gaps are at most 34 ms. The verifier retains the
tail rather than describing the file as uniformly gap-free. Two initial MKV
video packets have no DTS with B-frame reordering; available DTS are increasing,
and all decoded video frame PTS and audio packet PTS are checked.

A separate deliberately saturated recording raised `AUDIO_MIX_CLIPPING` with
145 observed full-scale blocks and a current native mix peak of +1.532 dBFS.
Decoded AAC peak was +0.727 dBFS after the standard output clamp/codec. The
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
while audio was saved/restored, and both documents restored normally. A new
three-second recording then confirmed the restored −18 dB tone gain (amplitude
0.007938, about −42 dBFS) and muted microphone (997 Hz amplitude 1.12e−8).

The final CLI suite independently exercised all nine mixer operations, including
explicit release/reopen and save/remove/load. Its requested −12 dB gain change
measured −11.957 dB, with maximum mono-decoded amplitude 0.119115 and zero native
saturated blocks. Its signed binary hash matches the MCP suite.

**20 Rust tests, Clippy with warnings denied, formatting, and all 17 unchanged
H1–H9 suites pass on the same signed binary.** The final serial gate is retained
in `var/evidence/h10-regressions-1794889365392256000/manifest.json`, with per-suite
logs, runtime logs and checksums of copied reports. All tests used their original
assertions and durations, including the 65 s capture and four 60 s encoder trials.
This is evidence on this Mac with its existing permissions; branches requiring
permission denial or unavailable external hardware are not thereby established.

| Existing suite | Result | Elapsed incl. fresh start |
|---|---|---:|
| `verify_control.py` | PASS | 2.9 s |
| `verify_control_delivery.py` | PASS | 1.9 s |
| `verify_h1.py` | PASS | 26.4 s |
| `verify_scenes.py` | PASS | 36.5 s |
| `verify.py` | PASS | 80.1 s |
| `verify_encoding.py` | PASS | 253.7 s |
| `verify_encoding_fallback.py` | PASS | 13.2 s |
| `verify_output_recovery.py` | PASS | 11.2 s |
| `verify_rtmp.py` | PASS | 44.4 s |
| `verify_rtmps.py` | PASS | 1.5 s |
| `verify_connect_stop.py` | PASS | 1.9 s |
| `verify_vt_stop.py` | PASS | 63.1 s |
| `verify_profiles_restart.py` | PASS | 2.7 s |
| `verify_h8_lifecycle.py` | PASS | 46.5 s |
| `verify_h8_keychain.py` | PASS | 3.4 s |
| `verify_h9_transitions.py` | PASS | 48.7 s |
| `verify_h9_faults.py` | PASS | 28.8 s |

The final audit manifest is `var/evidence/h10-final-audit.json`. The signed app
was shut down while idle and the shared physical-test lock was released;
`var/evidence/h10-release.json` records the cleanup. No test remains running.

The regression driver gives each unchanged suite a fresh, idle signed process
and opens the documented controlled window before `verify.py`. Its first run
passed control/H1/scenes but stopped because that window prerequisite was
missing (`StopIteration`, before recording). The failed manifest is retained in
`var/evidence/h10-regressions-1794889241459665000/`. This was a driver setup
correction; no existing suite assertion or product behavior was changed.

Earlier expanded-verifier failures are retained: the initial missing-DTS assumption
(`02-first-expanded-timestamps`) and an absolute source-creation counter that
incorrectly assumed a fresh process on retry (`03-retry-counter`). The latter now
checks the increment from its initial snapshot. Neither required a media-engine
change or weakening the gain/mute/continuity assertions.

The first windowed-spectrum run found ambient microphone energy around 440 Hz
above a threshold referenced to the quiet −18 dB tone. The fixture now holds a
0 dB-fader tone reference before tone mute, preserving the same >30 dB
suppression threshold, and also mutes both inputs to check digital silence.
Final tone-mute residuals were 0.000414 / 0.000305 versus references
0.063019 / 0.062990; both-muted decoded samples were all zero. The physical mic
remains audible during tone-only mute. The failed run remains in
`07-microphone-noise-floor/`; no mixer change was made for this test correction.

A further run failed the isolated-mic RMS comparison during an acoustic
transient: its native meter reached −14.68 dBFS against a steady approximately
−31.6 dBFS. The median polled meter and an integrated decoded second do not
measure identical intervals during such a transient. That report is retained in
`08-acoustic-transient/`. A complete repeat passed the same 2 dB RMS tolerance
without changing code or thresholds. This acoustic fixture requires a quiet
room; polling snapshots do not provide sample-exact meter/file alignment.
The previous successful expanded run remains in `05-increment2-success/`.

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
# Both audio suites require and leave an empty mixer:
python3 scripts/verify_h10_mixer.py --microphone-id UID_FROM_DEVICES
python3 scripts/verify_h10_regressions.py --camera-id UID_FROM_DEVICES --microphone-id UID_FROM_DEVICES
```

Tests use only owned visual fixtures, controlled speaker playback, the expressly
selected devices, local recordings and RTMP to 127.0.0.1. Media, UIDs, complete
control exchanges and runtime logs remain in ignored `var/`. See the
[UI integration contract](h10-audio-ui-contract.md) for commands/types/states and
[system-audio follow-up](h10-system-audio-next.md) for the independent next scope.

## Limits

- A startup phase change was observed; no claim of phase-perfect startup or
  sample-exact end-to-end latency is made.
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
- Normal `codesign --verify --deep` succeeds with the existing Apple Development
  identity. Strict bundle verification rejects the existing external Frameworks
  symlink, as already documented in the H6 report. Packaging is unchanged; this
  remains a checkout-bound development bundle. Both check results are retained
  in `var/evidence/h10-signature-checks.json` / `h10-final-codesign.log`.
