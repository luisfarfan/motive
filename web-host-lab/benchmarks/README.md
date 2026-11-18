# Performance protocol — checkpoint J

**BLOCKED: native host was not executed.** CPU, RSS/footprint per tree, GPU, first
frame, actual FPS, load/resize/shutdown latency, repeated/dropped frames and orphan
counts are all NOT_EVALUATED. No percentage improvement over OBS is reported.
`protocol.json` fixes scenarios, order and gates before measurement. A failure at
60 FPS cannot erase a 30 FPS result. Keep raw failed trials and the same limits.

Collector contract for the later authorized runner:

- Pin source/archive/framework/helper hashes, API version, macOS/architecture,
  toolchain, signing entitlements, fixture hashes, viewport/FPS and process layout.
- Capture root PID/start identity and all descendants, including reparented child
  identities already observed. Use PID+start identity, never a process-name kill.
  Sample CPU time deltas/wall time (100%=one full core) and RSS of each process.
  RSS sums may count shared pages repeatedly. Obtain footprint separately using
  supported macOS inspection; do not equate malloc allocations with resident pages.
- GPU only when attributable by an observed tool; otherwise null/unavailable.
  No fabricated zero. Capture tree start/end snapshots and wait/reap results.
- Timestamp request, DOM load, first accepted paint, resize request/first new epoch,
  close request/final browser close/last helper exit using the same monotonic domain.
  Native AV PTS remains absent. For each frame record index, byte hash, observation
  and consumption times, dimensions/epoch, overwrite/drop reason, JS visual counter.
- Distinguish paints observed, mailbox coalesces, busy drops, consumer draws,
  repeated last texture and pixel-identical frames. Requested FPS is not delivered
  FPS. A static page should not be rejected for not repainting each output tick.
- Compare incremental tree cost N=2 minus N=1, N=3 minus N=2, and total N=5. The
  required 3/5 cases are not extrapolated from a single widget. Run both process
  layouts only after security permits sharing; fresh profiles in every repetition.
- Report medians and p95 with sample count, failures and thermal/background limits.
  High load triggers cancellation, then bounded tree shutdown, never higher limits.

H18 adds a linked, locally sealed AppKit fixture and an external supervisor
exercised with owned non-browser processes. The fixture now copies OnPaint into
the existing Rust mailbox and retains two bounded disk samples plus at most 1024
frame telemetry rows. It separates accepted mailbox paints, coalesces, busy and
invalid callbacks, observed/acquired timestamps, maximum callback publish time,
and disk-consumer duration. Publish duration includes gate/lock/copy overhead;
disk-consumer duration includes file writes and lease release. Neither is an
isolated memcpy benchmark or libobs upload time. No CEF sample has been collected.

The supervisor observes public process identity, RSS and `ps %cpu`, and applies
external deadline/cancel/RSS termination. `ps %cpu` is the platform's reported
statistic, not the requested CPU-time delta sampler. Footprint, GPU, load/DOM and
full resize/shutdown timestamps, pixel hashes/counter analysis and repeated native
texture draws remain unimplemented/unmeasured. The smoke app accepts short runs;
the full 60-second/soak/scenario harness still needs native authorization and
implementation. [H18-benchmark-status.json](../evidence/H18-benchmark-status.json)
keeps every Chromium metric null and every scenario BLOCKED. Non-browser supervisor
results and synthetic C ABI cycles are not substituted for Chromium measurements.

`evidence/J-buffer-budget.json` is arithmetic only: three transient CPU buffers per
mailbox (callback copy + pending + leased), excluding Chromium, GPU, textures,
transport copies and allocator overhead. It is not a resource benchmark or an
RSS limit. No measurement for three/five active Web Elements is available.
