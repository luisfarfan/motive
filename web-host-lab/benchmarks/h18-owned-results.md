# H18 owned CEF resource results

The first 1-host and 3-host trials completed. The 5-host trial **failed the
aggregate RSS limit during startup** and was cancelled. All observed PID/birth
identities were gone after cleanup. These are real short native measurements;
the full frozen benchmark protocol remains unaccepted.

Each widget had its own CEF browser host and fresh private profile. All three
trials used the same ephemeral owned-smoke binary, 640×360 at 30 requested FPS,
5-second requested duration, 250 ms sampling sleep, 10-second per-host deadline
and **2048 MiB aggregate RSS emergency limit**. There was one trial per host count,
in order 1→3→5, without warmup or steady-state sampling. “Cold startup” here means
fresh processes/profiles; OS file caches were not flushed.

| Hosts | Result | Observed processes | Driver wall | Observed CPU / driver wall¹ | Peak latest RSS sum | Maximum available footprint sum² | Observed cleanup |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | PASS, short trial | 7 | 5.423 s | 12.15% | 658.70 MiB | 367.62 MiB | PASS |
| 3 | PASS, short trial | 21 | 5.591 s | 32.98% | 1993.27 MiB | 1136.14 MiB | PASS |
| 5 | FAIL, RSS cancellation | 34 | 1.335 s | 131.15%, truncated startup | 2880.17 MiB | 812.87 MiB, incomplete | PASS |

¹ 100% means one occupied CPU core. The numerator is observed CPU from valid
consecutive identity samples: 659,033,832 ns, 1,843,912,124 ns and 1,750,805,579 ns,
respectively. The denominator is experiment start to final host-thread join,
including startup, shutdown and diagnostic collection; collector CPU is excluded.
This is not steady-state utilization. In particular, the startup-only 5-host
percentage must not be compared as a sustained scaling result against 1 or 3.

² Footprint is an asynchronous sum of each host's latest available per-process
`ri_phys_footprint`. It is neither a simultaneous unique-page total nor the sum
of independent host maxima. At the 5-host RSS peak, footprint was **null** because
one latest host sample was incomplete. Its 812.87 MiB maximum came from an earlier
available aggregate; it does not establish lower memory use than 3 hosts. MiB
means 1,048,576 bytes. RSS also counts some shared pages more than once.

## What these trials establish

The 3-host RSS peak was 2,041,104 KiB, leaving just **56,048 KiB / 54.73 MiB / 2.67%**
below the emergency boundary. Passing this one short trial is not evidence that
three hosts are a safe supported capacity. Five hosts first crossed the boundary
at 2,277,616 KiB and reached 2,949,296 KiB before cancellation completed. The limit
is a sampled emergency stop, not an allocation cap; overshoot is real and retained.

All five hosts report `reason=cancelled`, with exit codes 0, 5, 0, 5 and 0. Three
retained real frame samples; two exited before frame delivery. Their orderly-run
gates failed because the experiment was aborted. This does not by itself show a
recurrence of the earlier native shutdown hang. Final observed PID lists are
empty for every host. That cleanup claim covers observed identities, not an
unobserved hostile escape or OS sandboxing. `shutdown_ms` covers the supervisor's
cleanup phase; it is not native browser-close latency.

Process counts are measured, not “one process per widget.” The 1/3-host runs each
observed seven processes per host, including helpers. The aborted 5-host run
observed 34 identities, of which 30 had a successful resource/role sample. Four
must remain unclassified. Role labels identify executable basenames; the absence
of an observed `gpu_helper` label does not establish that GPU activity was absent. GPU utilization
remains null.

## Audit and measurement limits

The read-only audit recomputed **93 host samples and 476 per-process rows** from
the retained source files. Mach CPU ticks convert through the recorded 125/3
timebase; valid deltas require consecutive matching PID, birth and process-start
identity. Host totals, experiment CPU rates, footprint sums, and aggregate RSS
and footprint peaks all reproduce. Aggregate samples replay against their exact
per-host sample sequences without a mismatch. Embedded supervision objects equal
their separately retained files, and no sample was dropped by the 256-row limit.

The formulas are:

- `cpu_ns = floor((user_ticks + system_ticks) × numer / denom)`.
- `interval_cpu_% = 100 × sum(valid CPU deltas) / actual wall_delta_ns`.
- `driver_cpu_% = 100 × sum(valid host CPU deltas) / launch_to_join_wall_ns`.
- Aggregate RSS and footprint sum the latest available host observations; a
  missing host footprint makes that aggregate footprint null.

New processes, failed reads, work before the first/after the last sample and
processes shorter than the sampling interval can be missed. Complete observed
identity coverage does not mean complete coverage of all work. The requested
250 ms is a sleep target: actual median intervals were 279.36, 294.54 and 343.15 ms;
the longest was 362.56 ms. The reported age of the latest host callbacks reached
357.07 ms; that age excludes time already spent collecting the process snapshot
and must not be treated as a complete RSS observation-latency bound.
Per-host p95 values in the raw reports have very small sample counts, include
startup, and are not aggregate or repeated-trial percentiles.

Python monotonic and native C++ observation timestamps have different origins on
this Mac. CPU/wall calculations use only the Python clock. No cross-clock TTFF or
frame age is derived. Native-only frame timing requires its own analysis. No
60-second steady-state trial, repetitions, soak, shared-host topology, OBS
comparison, native texture cost or GPU measurement is established here.

## Sources and next step

The exact reports are [1 host](../evidence/H18-perf-owned-1-first/report.json),
[3 hosts](../evidence/H18-perf-owned-3-first/report.json) and
[5 hosts](../evidence/H18-perf-owned-5-first/report.json). The machine-readable
[audit summary](../evidence/H18-owned-resource-summary.json) records SHA-256 for
all three reports, their nine individual `supervision.json` files and the
[build report](../evidence/H18-native-ephemeral-build.json). It retains the source
metric values, sample coverage, cleanup outcomes and formulas. All runs pin main
binary `4f77eea5e899f98ad57cb3a4bed047dcb0c87a8b8d784a361ac73606d2fca8f7`
and identical collector hashes. The candidate uses its recorded owned-test
credential backend, `chromium-use-mock-keychain`.

**Keep the 2 GiB RSS emergency boundary. Do not repeat the same five-host layout
as a capacity test or raise its quota.** First use controlled one-host profiles
to identify browser/helper overhead. Treat a repeat of three hosts as a guarded
diagnostic with very little margin. A multi-widget single-host design needs its
own isolation, lifecycle and resource experiment; its cost cannot be inferred
from these independent-host runs. Complete the frozen protocol's warmup,
repetitions and scenarios before making a performance or capacity claim.
