# System audio after H10

System audio remains a separate increment. H10's public enum intentionally
accepts only an explicit microphone UID and the controlled tone; it cannot
select arbitrary plugins, media paths, system audio or per-scene audio.

The pinned official OBS 33.0.1 module already contains an audio-only
`sck_audio_capture` source. Its ScreenCaptureKit implementation supports desktop
and application targets, sets `capturesAudio`, excludes its own process's audio,
and delivers samples through the same OBS source API. It also attaches a dummy
video stream output that its delegate discards. This is a documented source-code
finding, not evidence that Motive has implemented or tested system capture.

The next increment should introduce a separate typed identity for an explicitly
selected application or desktop. Persist bundle/display identity, resolve it
uniquely at restoration, and share one native capture per target. Do not overload
a microphone UID or silently select the current/default desktop. Decide whether
overlapping app/desktop sources should be rejected to prevent duplicate sound.

Before integration, verify normal macOS permission behavior, app exit/relaunch,
no packets versus silence, sample-rate conversion and clock drift, capture of
owned audio only, and exclusion of Motive's own output. Use a separate controlled
fixture application playing known frequencies, compare decoded recording/RTMP
against per-input and master meters, and test Cut/Fade independence. Microphone
plus system capture must not double-capture audio already attached to a visual
source. Monitoring stays off. No driver installation, system routing change or
global permission/trust modification is part of H10.

Primary source: [OBS 33.0.1 mac-sck-audio-capture.m](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-audio-capture.m),
especially `init_audio_screen_stream` and `sck_audio_capture_info`.
