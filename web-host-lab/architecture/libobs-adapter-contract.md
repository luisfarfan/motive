# Future libobs source adapter

**Design only: no Production integration or source registration in H16.**
Read-only reference: OBS 33.0.1 and BrowserSource::Render in both browser pins,
plus Motive's current owner/native adapter. H15 retains exclusive ownership.

## Smallest production change

Add a visual source definition containing package capability/hash, stable source
ID, approved property values, viewport/FPS and policy version. Do not expose file
paths, URLs, scripts, helper flags or IPC descriptors through the project/MCP.
The existing engine owns one manager and all source/scene references. Runtime
instance/generation, frame sequence and watchdog state are never persisted.

Register a custom-draw video-only libobs source, conceptually using
OBS_SOURCE_VIDEO | OBS_SOURCE_CUSTOM_DRAW | OBS_SOURCE_SRGB. Do not register
OBS_SOURCE_ASYNC_VIDEO with CEF observation timestamps as AV PTS. No audio flag,
capture/mix/encoder/output, or separate media-clock thread is required.

## Frame boundary

Required metadata: protocol version, instance/generation, viewport epoch,
monotonic paint index, width/height, stride, BGRA8, premultiplied-alpha flag,
sRGB target declaration, observation nanoseconds, bounded dirty rectangles and
exact byte length. Validate identity, limits, overflow, color/layout and sequence
before publishing to the source mailbox. Current Rust mailbox checks the bounded
owned-buffer contract; C++ fixture exercises the CEF API shape. FFI and frame
transport between them do not exist yet.

Initial cross-process transport should copy complete frames from the CEF mailbox
on a worker into a separate bounded binary channel; it is not MCP or control JSON.
Check length before allocating at the receiver, discard superseded frames and
never block the CEF callback or libobs tick waiting for transport. Shared-memory
rings need their own ownership/sealing, torn-write and hostile-header tests and
are deferred. The measured CPU-copy baseline must precede IOSurface optimization.

On OBS tick/render: try-acquire newest valid frame, upload only if identity/index
changed, then release the CPU lease. Upload/create/destroy textures on the correct
OBS graphics context. Do not acquire a blocking CEF lock or synchronously invoke
the browser from render. No new frame means repeat existing texture under OBS's
clock if policy permits. A stopped/failed/revoked host blanks the source and reports
health; a static healthy element may explicitly hold its last frame. Animated
freshness budgets use observed age; a heartbeat alone cannot prove fresh pixels.

CPU upload uses GS_BGRA and full-frame update initially. Carry dirty rectangles
for telemetry/future optimization only; dropping intermediate partial updates
would lose changes. Use ONE/INVSRCALPHA for premultiplied content, save/restore
blend and framebuffer-sRGB state, verify RGB/alpha edges over black/white/color
backgrounds. No HDR, wide-gamut or arbitrary color-space claim in this contract.

Resize/restart invalidates pending frames before allocating a new texture and
publishes a new epoch/generation. Release old GPU objects only when render no
longer references them. Do not accept A→B→A late paints just because dimensions
match. Initial browser recreation is allowed; optimized WasResized needs proof
of an ordering barrier and correct scaling/device-scale behavior.

## Lifetime and receipts

Scene layers refer to the same source identity. Manager computes aggregate
visibility; a hidden layer must not suspend a source still visible elsewhere.
Web Element hidden=cancel is distinct from existing native video's semantics.
Removal: revoke operation/channel → invalidate frame lease/texture → request close
on host UI thread → wait asynchronously for OnBeforeClose and helper-tree reap →
release host state. Never wait on that chain inside the OBS render callback.

Show Control owns intent, dedup and cooldown. Host admission is an acknowledgment,
first paint is a separate observation, and OBS consumption is a third receipt.
Retain owner session/revision and action provenance through each step; uncertain
delivery requires reconciliation and no replay. Renderer replies cannot advance
Production revision or start recording/streaming. Failure of one source must not
reset libobs's global clock or other recording/streaming destinations.

Acceptance after H15: real source upload and decoded composite alpha/cadence,
same-owner CLI/MCP/GPUI controls, race/resize/cancel/crash tests, resource release,
offline package operation, 3/5-source performance and full relevant regression
suites. Buffers or screenshots outside Motive satisfy none of those native gates.

## H18 isolated implementation

`poc/browser-host/src/adapter.rs` implements/test-drives upload/repeat/blank
admission using existing Frame identities, viewport epochs, age, sequence,
aggregate visible references and permanent revocation. It never calls OBS.
`poc/frame-bridge` now connects the compiled CEF callback to the existing Rust
mailbox and bounded host-side consumer. The C++/Rust ABI is tested with synthetic
bytes; CEF pixels and actual graphics uploads remain BLOCKED. The native
process-to-owner transport/manager is still pending H17 handoff and authorization.
