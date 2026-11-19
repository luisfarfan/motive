# H19 → H20: compiled owner and source contract

The isolated Rust `BrowserHostManager` in
[`poc/browser-host/src/manager.rs`](../poc/browser-host/src/manager.rs) compiles
without CEF, libobs, GPUI or Production. Its tests exercise real Rust objects and
owned frame bytes. They are **contract evidence**, not native browser, graphics,
OS-isolation or audiovisual-output evidence. H17 still owns Production; no
integration authorization is implied by this document.

H20 may reuse the existing mailbox, admission, lifecycle and visual-message
contracts after handoff. It must connect them to the existing Production owner,
its reviewed package capabilities and its graphics context. It must not introduce
another Production, renderer, event schema, audiovisual clock or video-over-MCP
transport. Web audio remains disabled.

## Identity and responsibilities

| Value | Implemented contract | Native integration responsibility |
|---|---|---|
| Instance/generation | Immutable `Identity`; stale lookup rejected; generation ledger prevents reuse after disposal | Owner assigns IDs and never accepts renderer-supplied authority |
| Viewport/epoch | Validated dimensions, stride/byte bounds, immutable mailbox epoch | Native producer supplies its real geometry; receiver rejects mismatched epochs |
| Package/inventory | `OwnedFixtureDescriptor` retains both SHA-256 identities | Existing importer/broker must verify the actual bytes and grant access; nonzero hashes alone confer no trust |
| Origin | Descriptor generates an origin from instance/generation | Bind the actual `motive://iN-gG/` native origin to the descriptor and exact inventory; no caller-supplied origin or URL is admitted |
| Request context | Fresh nonzero context token; reuse rejected | Create and release the corresponding native context. Distinct tokens/contexts are not OS sandboxes |
| Host | PID plus supervisor-observed start token | Authenticate the launched process and detect PID reuse; a PID field in JS is not evidence |
| Browser/renderer | Browser ID tied to host identity; renderer may be unknown | Bind CEF browser callbacks and independently observed processes. Unknown renderer assignment means unknown failure isolation |
| Properties/events | Existing `ipc::Gate` and creator `Binding` remain authoritative | Reuse reviewed bindings, typed visual projections, sequence/expiry/rate checks and cancellation lane |
| Frames | Existing `Mailbox`, `Lease` and `Admission` | Implement bounded binary host→owner transport and OBS graphics-context upload; neither exists in this module |
| Health/lifecycle | Existing `Lifecycle`, immediate revocation, close and reap observations | Perform asynchronous CEF actions and external watchdog cleanup; a state transition cannot kill or reap a process |

`register_owned_fixture` is deliberately named for the laboratory. It is not a
production package approval API. The manager accepts a caller-specified active
limit from 1 to 16 and retains at most 1024 identity/context ledger entries.
These are implementation bounds, **not measured supported widget capacity**.
Exhaustion fails admission; it does not silently reuse a context or generation.
Native H19 has its own narrower reviewed scenario and history bounds.

## Owner-side call sequence

1. Create a manager using the capacity admitted by the measured policy. Register
   an owned fixture descriptor after inventory review. Registration starts the
   existing lifecycle deadline; it neither launches CEF nor claims readiness.
2. Bind `browser_created(identity, browser, now_ms)` only to the authenticated
   native creation observation. Process identity includes the process-start
   token. The native CEF fixture separately observes actual first paint and
   useful pixels; browser creation does not establish either.
3. Update `set_visible_references` with the total visible scene-layer references
   for the source. A hidden layer cannot suppress a source still used elsewhere.
   Zero references blanks admission and cancels active lifecycle state. The owner
   must send the existing visual cancel/visibility operation to the host; this
   contract does not invoke CEF.
4. Deliver properties/events through the existing reviewed `Binding` and `Gate`.
   A renderer ACK is a visual-channel observation only. It cannot mutate
   Production, start recording/streaming or prove native resource release.
5. Poll the existing lifecycle deadlines from the owner/watchdog. `poll` revokes
   frame admission on timeout, then the external supervisor must close or reap
   the exact owned tree. Never terminate unrelated processes by name.

The tests in [`tests/manager.rs`](../poc/browser-host/tests/manager.rs) are executable
examples of registration, multiple layers, cross-instance frame rejection,
shared-renderer failure, replacement and terminal disposal. They deliberately
use controlled synthetic process identities and must not be cited as OS-process
or CEF cleanup evidence.

## Frame transport and future OBS draw

The host copies the complete BGRA callback image before `OnPaint` returns. Alpha,
stride, dimensions, instance, generation, epoch, index and monotonic observation
survive the owned mailbox boundary. Dirty rectangles remain metadata: coalescing
partial deltas would lose earlier changes. The callback never retains a CEF
pointer. No IOSurface, Metal sharing or GPU zero-copy is implemented.

The host-side consumer must release a lease after its bounded transfer. A future
owner receiver validates the same immutable metadata before publishing its own
latest complete frame. The transport is binary and separate from control; it is
not MCP. A malformed/oversized/stale frame fails closed before allocation or draw.
The current C ABI is **trusted in-process FFI**, not an untrusted IPC decoder.

`frame_decision` returns the existing `Upload`, `Repeat` or `Blank` policy. H20
must perform actual texture creation/upload/destruction on OBS's graphics
context, under OBS's existing tick. A static healthy source may explicitly hold
its last texture; failed, revoked or suspended state blanks it. An observation
nanosecond is an age/health value, never a media PTS. Consumer acquisition FPS is
not audiovisual output FPS.

The mailbox uses nonblocking producer/acquire attempts, but telemetry, completion,
revocation and lease drop take its short metadata mutex. Its host-side API is
therefore **not a certified hard-real-time OBS callback API**. Keep the host
consumer/transport on a worker, and establish a nonblocking owner-side transfer
and texture-lifetime barrier before direct Production integration. Do not call
CEF, wait for shutdown, write disk files or wait on transport from OBS render.

## Exact new frame accounting

`motive_frames_stats_v2` preserves the old four-field ABI as a separate function
and supplies a new versioned structure. For one immutable mailbox:

```text
accepted paints = pending + leased + coalesced + stale + consumed
                + released_unconsumed + invalidated_close + revoked_generation
```

`acquired` counts the pending→lease transition and overlaps terminal outcomes;
it is not another summand. `coalesced` means a pending complete paint was replaced
by a newer complete paint. “Replaced” and “discarded by coalescing” describe this
one outcome, not two counters.

A sink calls `motive_frames_complete` only after successful use. Acquiring or
releasing a lease does not prove consumption. Completion is accepted once while
its mailbox is live. If revocation wins before completion, the terminal outcome
is revocation even if a disk write began earlier. Already-completed frames are
not reclassified during close.

`motive_frames_revoke_reason(..., 0)` invalidates for close; reason `1` invalidates
for generation/epoch replacement. Both classify pending and still-unclassified
leased frames once. Old bytes stay owned until their lease is released, while
visual authority is revoked immediately. `retained_leases` includes completed
or revoked leases still physically held; it differs from unclassified `leased`.
`retained_bytes` is the sum of current owned pixel lengths, excluding allocator,
CEF, transport, GPU resources and the transient callback copy. It is not RSS.

`copied_bytes` and `copy_ns` observe the full copy into previously reserved
capacity. Timing includes timer overhead, memory faults and scheduling effects;
it is not a standalone libc memcpy benchmark. No memory or CPU saving is claimed
from adding this telemetry. H16/H18 historical counters are unchanged and are not
retroactively assigned to these new terminal categories.

## Close, failure, replacement and cleanup

For a normal removal, call `close(identity, true, now_ms)` to revoke source
admission and request asynchronous native close. `browser_closed` accepts the
matching native browser identity and the real final-close observation. Only
then may `remove_disposed` succeed, and only with no retained leases. Native
browser close and host-tree reap are distinct: other browsers may still need
the shared browser/GPU/network/helper infrastructure.

A renderer failure affects every known member of that renderer. Unknown renderer
assignment is conservatively included for the same host. Other positively known
renderer assignments remain independent at this policy boundary. A host failure
revokes all its instances. These state changes do not claim that any process is
already gone. After the supervisor actually observes the exact host tree gone,
`observe_host_reaped` records that separate owner observation. Renderer strings,
ACKs and unverified booleans cannot provide that evidence.

`replace_closed` accepts a fresh generation/context only after final browser
close, or after a failed host has a supervisor reap observation. It waits for old
leases to release. A replacement starts with zero visible references and a new
lifecycle deadline; it does not replay an event. Generation may advance while a
new viewport epoch sequence restarts at 1. Disposal is terminal even if close
times out or the host crashes: it cannot be downgraded into a restart.

The compiled manager currently requires browser replacement for resize because
it has no authenticated hot-resize barrier. The native H19 experiment separately
uses `WasResized` with fresh mailbox epochs and rejects previously used geometry
within the same browser generation. That constrained A→B path does not establish
a generic A→B→A ordering guarantee. H20 should retain cold browser replacement
until its supported dynamic transition has explicit ordering/ownership evidence.

## Gates before final integration

H20 can develop the isolated transport/source adapter against these contracts.
Final Production integration still needs H17 handoff, reviewed authority from
the real owner, safe credential configuration, accepted confinement/capacity
policy, bounded authenticated transport, real OBS graphics ownership, decoded
alpha/motion/cadence and teardown evidence under recording/local streaming.
Third-party HTML/JS stays blocked until its separate OS-isolation matrix passes.
The laboratory test Keychain backend does not satisfy that gate. Developer ID,
notarization, packaging and broader macOS compatibility have their own acceptance
requirements; no release is authorized here.
