# Visual IPC v1 — checkpoint G

H16 adds a private **transport envelope**, not another Web Element schema:

```json
{"protocol":1,"instance":1,"generation":1,"expires_ms":1000,"message":{"version":1,"seq":17,"kind":"event","name":"goal.scored","payload":{"team":"Club del Puerto","home":2,"away":1}}}
```

`message` is the existing Element Lab v1 shape. Its version/seq/kind and event,
properties, cancel, resume, dispose forms are unchanged. The native trusted
manager assigns identity/generation/sequence and expiry (monotonic milliseconds
relative to channel creation). A renderer cannot create trusted host events.
Use finite exact integers <=2^53-1 when crossing JavaScript. A channel never changes
identity; restart closes it and creates another. Host checks OS peer/launch identity
in addition to these fields; that native binding is still pending.

Implementation: `poc/browser-host/src/ipc.rs`. Four-byte big-endian length before
UTF-8 JSON. Absolute read deadline covers prefix and payload. Limit is at most
16,384+512 bytes; per-element messages obey the existing smaller contract limit.
Duplicates at every nesting level, unknown fields, malformed/deep JSON, invalid
types, wrong identity, stale sequence, expired/far-future deadlines and invalid
properties/events are rejected. No raw diagnostic or input payload is logged.
Strings use UTF-16 length matching the existing JS runtime. Validate a property
patch completely before committing any value.

Rejected attempts with a valid channel sequence consume that sequence. Event and
property admission shares a rolling one-second quota from the manifest (8 for
goal-celebration). Cancel/resume/dispose bypass that quota. Native control must
have a separate reserved lane, because a single stream still has head-of-line
blocking. The prototype tests gate priority but does not claim an implemented
multi-process priority supervisor. No event backlog: lifecycle admits a new event
only in ready; no automatic replay after timeout/crash.

Transport errors are terminal: close the channel; do not continue after consuming
an oversized header or partial body. The nonblocking contract adapter has a 1 ms
wait between WouldBlock reads and a 250 ms write deadline. Production integration
should register readiness in the native event loop rather than call it on GPUI.
Two OS socket endpoints are exercised with fragmented writes, EOF, huge prefix
and a silent peer. This is real local transport testing, not a CEF process test.

Renderer → host channel will permit only bounded status/ack enums with a matching
event sequence, main-frame sender and generation. It must not use this host →
renderer admission function. No response may become a Production command. Renderer
readiness is not proof of sandbox, successful rendering or a finished native job.
This return-channel CEF wiring remains part of the native gate.

Lifecycle module enforces active duration (from existing max_active_ms), explicit
cancel/resume, close acknowledgment, failure and generation changes. Its watchdog
must be called by the external supervisor; a pure state machine cannot terminate
a blocked OS process. Admission, lifecycle and CEF calls are separate testable
modules; the native dispatcher joining them is not implemented yet.

Failures retained: G-ipc-initial-failure.log and G-ipc-diagnostic.log show macOS
rejecting SO_RCVTIMEO with EINVAL; rounding did not fix it (separate failure log).
The cause of setsockopt rejection is not established. The implementation changed
to nonblocking I/O with an absolute deadline; all eight IPC cases then passed.
