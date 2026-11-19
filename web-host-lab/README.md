# H16 — Motive Browser Engine laboratory

The following H16 record is historical. Current H18 observations are recorded in
[H18 continuation](#h18-continuation) below.

Independent research and contract implementation based on remote main
`130b626168cbe1336afb85c3810fa6be5e6b2b11`, 2026-11-18. All H16 changes live here.
H15 owns production. No application, CEF process, capture, recording or stream
is started by the static test workflow. No changes to `.deps/` or global tools.

**PARTIAL laboratory; native rendering and third-party isolation BLOCKED.**
Read [the final decision](docs/final-decision.md), [audit](research/obs-browser-analysis.md)
and [build instructions](docs/build-and-test.md). Static contract tests are not
CEF runtime evidence. The native fixture is explicitly gated by repository
policy; proxima-browser is the only authorized browser QA tool.

Direction: CEF upstream runtime/wrapper, a small separate host, CPU-copy OSR,
existing Web Element v1, bounded channels, no Qt or OBS frontend in that host.
The future libobs source remains owned and clocked by Motive's one Production.

Source archives and binaries used for static inspection are checksum pinned
in [sources.lock.json](research/sources.lock.json) and cached only in `.cache/`.
They are not vendored, published, executed, or installed into Motive.


## H18 continuation

H18 now supplies a linked ARM64 AppKit development bundle with the pinned CEF
wrapper/framework/helpers, local ad-hoc seals, a C ABI to the existing Rust
mailbox, a bounded consumer, future libobs admission policy and an external
supervisor. **Owned native lifecycle/pixels pass in the tested profiles; overall
integration and third-party isolation remain PARTIAL/BLOCKED.** Original shutdown
failures reached real Keychain work and remain retained. Later fixtures use
Chromium's explicit in-memory test Keychain backend, which is not an OS sandbox.

- [100 serial native cycles](evidence/H18-native-cycles-100/summary.json) passed
  frame delivery, alpha, orderly exit and observed cleanup. Each cycle creates a
  new host process/browser; this does not prove repeated recreation or leak
  freedom inside a long-lived host. The visible counter changed in 92 cycles and
  remained NOT_EVALUATED in eight. [Cold replacements](evidence/H18-native-replacements/summary.json)
  separately passed reload and viewport change with reap and fresh generations,
  without preserving a JS heap or testing system suspend.
- [Four Goal closures](../creator-runtime-lab/evidence/binding/native-binding-closure.json)
  retain real typed CefProcessMessage delivery, Goal content, transparency,
  horizontal/vertical layouts and cancel/resume/dispose through the offline owner.
  JS acknowledgements remain distinct from native paint, shutdown and cleanup.
- [Audited resource trials](evidence/H18-owned-resource-summary.json) measured
  CPU, RSS and physical footprint for 1/3/5 independent smoke hosts. One and
  three hosts completed; five crossed the fixed 2 GiB aggregate RSS emergency
  limit and were cancelled. These short cold-start observations do not accept
  steady-state capacity, the full benchmark protocol or a shared-host topology.
  GPU utilization remains unmeasured.
- [Retained timing audit](evidence/H18-native-timing-summary.json) checks 115 host
  runs and 351 source-file hashes. It derives native same-clock frame age,
  retained-sample rates and shutdown intervals; it does not claim content-ready
  latency, displayed video FPS or libobs upload timing.
- [Fixed native diagnostics](docs/h18-native-host.md#fixed-native-diagnostics)
  cover static content, hidden/resumed OSR, a 500 ms JS stall, a slow consumer and
  controlled renderer exit. The successful crash recovery is an expected error
  outcome; its two earlier failures remain retained.

Run `python3 web-host-lab/tools/verify_h18.py` for build/static checks and
non-browser tests. Read [the artifact and scoped execution gate](docs/h18-native-host.md),
[per-surface security matrix](docs/h18-security-checkpoint.md) and
[H18 static results](evidence/H18-static-summary.json). H16 documents above are
historical; H18 does not rewrite their earlier unlinked state or acceptance.
