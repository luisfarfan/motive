# H11 — Overlay Engine verification

Worktree `motive-h11`, branch `codex/h11-overlays`, starting at main `0370ca4`
(includes H10). Local development evidence only; no release, public stream,
push or merge. UI/Claude Design files are unchanged. The shared physical-test
lock is held for signed-app runs; offline decoders do not open capture devices.

## Native-source increment

The actual OBS 33.0.1 ARM64 registry provides FreeType v2, image source, FFmpeg
media source and Fade. Native wrappers use those children and the libobs
graphics API; libobs owns composition, timestamps, audio mixing and encoding.
Browser remains unavailable for the concrete reasons in
[the bounded CEF spike](h11-browser-spike.md).

Real H.264/AAC pilot `var/evidence/h11-visuals-1794894197682488000/report.json`:

| Check | Observed evidence |
|---|---|
| UTF-8 Latin text, newlines and live replacement | 7,342 changed text pixels through MCP; same wrapper/child instances and output |
| Empty text | Zero remaining foreground pixels in its previous box |
| Center/right block alignment | Center bounds x241–356; right x481–596 within a 600-pixel box |
| PNG alpha | Transparent region equals background; 50% blend maximum channel error 3.07/255 against the declared encoded-RGB blend |
| Rectangle/circle and borders | Decoded color probes, including yellow circle rim, pass |
| Media pause/loop/restart/stop/play | Paused difference0; moving difference9,041pixels; loop still moves after6seconds |
| Media audio isolation | Stored clip has997Hz audio; output997Hz amplitude5.28e-8 versus H10tone440Hz amplitude0.03160 |
| Container/clock | 960×540 H.26430fps + stereo AAC48kHz; full decode; interior video gap≤34ms, audio≤22ms |
| Continuity | No output drops, encoder skips, source/child recreation, mixer edits or clipping |

That 30.4-second run measured process CPU median24.7%, RSS median188.0MiB,
maximum191.2MiB. It also recorded214 cumulative render-lag frames; this is
retained as a failure of steady rendering, despite continuous encoded PTS.
The earlier basic pilot had0render lag, CPU median24.1%, RSS median175.6MiB.
These debug-process measurements include the polling observer and are not a
performance-improvement claim.

Lifecycle pilot `var/evidence/h11-lifecycle-1794894264814162000/report.json`
passed a real close/reopen/load, widget subtype replacement with only that
source recreated, reused managed image, unchanged independent H10 store and
output profiles, v3 restoration, missing-resource finalization, blocked restart,
explicit identical reimport and targeted reconnect. Both the finalized and
recovered recordings decode with continuous audio.

## Failures retained and hardening

- First snapshot exposed an absent circle rim: repeated writes to the immediate
  vertex buffer overwrote queued Metal geometry. Immutable unit-circle vertices
  and a decoded rim assertion fixed it; the original clip remains private.
- Official FFmpeg `play_pause(false)` after `stop` reports playing without
  restarting playback. `play` now calls official restart for stopped/ended
  states; pause-resume still uses play/pause. Original failure:
  `h11-visuals-1794894023544054000/report.json`.
- Helvetica does not cover the pilot's checkmark; it renders a missing-glyph
  box. UTF-8 transport and accented Latin are verified. Universal glyph fallback,
  emoji and complex-script shaping are not claimed.
- The first animation run showed457render-lag frames while the app was in the
  background. An app-scoped `NSProcessInfo` activity now spans output startup
  through actual finalization, including failure; idle retains no assertion.
  This follows [Apple's activity API](https://developer.apple.com/documentation/foundation/processinfo).
  It changes no global settings. The next equivalent run showed0render lag.
- Both animation recordings are retained. Exact pixel timing against command
  acknowledgement still needs an independently verified media-time origin;
  runtime durations alone are not acceptance evidence.
- Large v4 status requires a separate response framing limit: requests remain
  64KiB, responses are bounded at1MiB. Socket tests cover fragmentation, exact
  limits, incomplete frames and consecutive messages.

Current Rust gate:47tests pass; further runtime/preset/RTMP and H1–H10 gates are
in progress. This document is an incremental report, not an H11 completion claim.

See [UI contract](h11-overlay-ui-contract.md), [comparative research](h11-comparison.md)
and [animation lifecycle notes](h11-animation-notes.md). Evidence and media stay
under ignored `var/`; paths here are relative to this worktree.
