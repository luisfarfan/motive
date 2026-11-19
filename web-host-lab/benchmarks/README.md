# Performance protocol — checkpoint J

**PARTIAL evidence; the required benchmark matrix remains incomplete.** Real owned
CEF smoke runs now include public CPU-time deltas, physical footprint and measured
process trees. The first 1-host and 3-host short trials passed; the 5-host trial
hit the unchanged aggregate RSS emergency limit and was cancelled. All observed
trees were cleaned up. See [the results and limits](h18-owned-results.md).
These trials do not establish steady-state capacity or benchmark acceptance.
GPU, repeated matrix trials and the full per-scenario latency/FPS requirements
remain NOT_EVALUATED. No percentage improvement over OBS is reported.
`protocol.json` fixes scenarios, order and gates before measurement. A failure at
60 FPS cannot erase a 30 FPS result. Keep raw failed trials and the same limits.

Collector contract for the full protocol:

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
exercised with owned Python processes and explicitly launched owned CEF. The fixture copies OnPaint into
the existing Rust mailbox and retains two bounded disk samples plus at most 1024
frame telemetry rows. It separates accepted mailbox paints, coalesces, busy and
invalid callbacks, observed/acquired timestamps, maximum callback publish time,
and disk-consumer duration. Publish duration includes gate/lock/copy overhead;
disk-consumer duration includes file writes and lease release. Neither is an
isolated memcpy benchmark or libobs upload time. Authorized native diagnostic samples are retained in separate run reports; they are not substituted for this matrix.

The supervisor observes public process identity and RSS and applies external
deadline/cancel/RSS termination. Its versioned [resource sampler](resource-sampling.md)
uses `proc_pid_rusage` and `mach_timebase_info` for CPU deltas and per-process
physical footprint. Historical `ps %cpu` remains separately labeled; old reports
are not rewritten. The [explicit 1/3/5-host driver](owned-host-experiment.md)
keeps one widget per independent host and a single 2 GiB aggregate RSS limit.
GPU utilization, native texture costs and the full 60-second/soak/scenario harness
remain unmeasured or incomplete. Lifecycle timestamps and independent pixel
hashes/counter analysis are retained, but Python and native clock origins are not
calibrated for cross-clock TTFF. The historical
[H18-benchmark-status.json](../evidence/H18-benchmark-status.json) retains its
original blocked/null matrix; new real measurements are in
[H18-owned-resource-summary.json](../evidence/H18-owned-resource-summary.json).
Python and synthetic C ABI results are not substituted for Chromium measurements.

`evidence/J-buffer-budget.json` is arithmetic only: three transient CPU buffers per
mailbox (callback copy + pending + leased), excluding Chromium, GPU, textures,
transport copies and allocator overhead. It is not a resource benchmark or an
RSS limit. Real three-host and aborted five-host samples are now available in the
owned results; the aborted run is not evidence of five active widgets operating
for the requested duration.
