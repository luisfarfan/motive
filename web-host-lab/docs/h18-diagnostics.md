# H18 fixed native diagnostics

These are short Motive-owned CEF observations at 640×360 and 30 FPS, using the
explicit ephemeral test Keychain backend. Each launch uses a fresh private root,
5-second fixture limit, 10-second external deadline and 2048 MiB tree-RSS limit.
They do not complete the longer performance protocol, prove OS confinement or
integrate libobs/Production. Original ElementLab files are unchanged.

| Fixed profile | Observed result | Evidence |
|---|---|---|
| Static | One JS paint reported; native pipeline accepted two paints including startup. Latest visible counter is 1. | [report](../evidence/H18-native-diagnostic-static/report.json) |
| Hidden | `WasHidden(true)` at 1 s and visible again at 3 s. After 100 ms settling, callbacks stayed 31→31; no accepted sample during the pause. JS visibility events arrived; paint gap was 2013 ms, then painting resumed. | [report](../evidence/H18-native-diagnostic-hidden/report.json) |
| Slow JS | Fixed script blocks for 500 ms. Allowed native phase observations were 500.122 ms apart, with a 455.201 ms paint gap. | [report](../evidence/H18-native-diagnostic-slow/report.json) |
| Slow consumer | One owned lease held for 100 ms per acquisition: 140 accepted paints, 41 acquisitions and 98 coalesces. No unbounded queue was introduced. | [report](../evidence/H18-native-diagnostic-slow-consumer/report.json) |
| Renderer failure | Browser sends a fixed authenticated process message only to its main renderer, which calls `_exit(86)`. Native frame admission is immediately revoked; browser closes on the next UI task, returns expected error 42, and the external supervisor observes no remaining owned processes. | [report](../evidence/H18-native-diagnostic-crash-posix/report.json) |

The slow consumer retains the same three-buffer contract bound: one lease, one
pending frame and one transient callback copy. This bound is not measured total
Chromium memory. The legacy `max_disk_consumer_ns` field includes the deliberate
100 ms delay in that profile; it is not memcpy time or libobs upload time.

Renderer failure does not mean healthy exit 0. The first synchronous-close run
[segfaulted in the host](../evidence/H18-native-diagnostic-crash/report.json).
The next deferred-close run reached `shutdown_return`, but [failed the exit-code
check](../evidence/H18-native-diagnostic-crash-deferred/report.json). Both remain
FAIL evidence. The matching Chromium [POSIX process source](https://github.com/chromium/chromium/blob/150.0.7871.252/base/process/kill_posix.cc)
returns the raw wait status: 22016 decodes to exit 86 through public
`WIFEXITED`/`WEXITSTATUS` macros. The final report preserves both values and the
host's expected error 42. [Pinned source hashes and the scoped fix](../evidence/H18-native-crash-research.json)
also document the navigation lock around CEF's termination callback. The exact
cause of the initial fault is inferred; stripped nearest-export names are not
exact internal stack symbols. Controlled exit is not a memory-corruption probe.

The final common close implementation revokes frames immediately for **all**
profiles, before posting browser close. Its [normal regression](../evidence/H18-native-final-smoke-repeat/report.json)
passes pixels, changing counter, healthy exit and cleanup. The preceding
[partial sample](../evidence/H18-native-final-smoke/report.json) is retained: its
first frame was transparent before JS painted, so a first counter was unavailable;
latest counter 148, frame delivery, alpha and closure passed.

## Cold suspension, reload and viewport replacement

[The three-step chain](../evidence/H18-native-replacements/summary.json) uses the
frozen original ephemeral smoke artifact and unchanged inventory. Generations
30→31→32 run 640×360, 640×360, then 540×960. Native close and external observed
reap must pass before the next launch. Each step checks current generation,
dimensions and epoch in real frame metadata, with distinct private roots/caches
and origins constructed by the frozen generation contract.

This follows the existing H16 lifecycle's `close(false)` → `Suspended` →
`restart_after_reap` model. Suspension is teardown with a cold restart. It does
not retain the JS heap, reload within one browser or exercise an in-process
`WasResized` epoch transition. Those are not claimed as results.

Reproduction is explicit through `tools/run_owned_diagnostic.py --mode ...` and
`tools/run_native_replacements.py`; both require an exact reviewed build hash.
Static verification never invokes either runner. The diagnostic phase/crash
boundary C++ test links no CEF, and the Python classifier regression rejects a
healthy zero exit or missing revocation as a successful controlled crash.
