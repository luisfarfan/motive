# Public macOS resource sampling

The supervisor adds version 1 `resource_measurements` and per-sample
`resource_usage`. Existing `cpu_percent_ps` remains the `ps` statistic and the
ambiguous legacy `footprint_bytes` remains null. Historical reports are untouched.

`proc_pid_rusage(RUSAGE_INFO_V0)` supplies cumulative CPU time, resident size and
physical footprint for each observed owned process. CPU values are Mach ticks;
the collector retains those raw values and converts through public
`mach_timebase_info` before taking deltas against monotonic wall time. The reported
scale is 100% for one fully occupied CPU core. The API declarations and structure
layout come from the installed public macOS SDK `libproc.h`, `sys/resource.h` and
`mach/mach_time.h`. Apple's [XNU implementation](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/bsd_kern.c)
populates these resource fields from task power counters and physical footprint.
No private API, root access, credentials, task-for-pid entitlement or GPU inspection
is used.

Every measurement checks the same UID and PID/birth identity before and after the
read. A delta also requires matching process-start absolute time and consecutive
successful observations. Failed reads, new processes and missing intervals yield
null CPU rather than a fabricated zero. Roles are classified only from observed
executable basenames; no command lines or environment are logged. A GPU helper
role is not a GPU utilization measurement: `gpu_percent` remains null.

Physical footprint is the sequential sum of per-process `ri_phys_footprint`,
separate from RSS. It is not coalition accounting or a unique-page measurement.
Complete identity coverage only means all processes in the current observed tree
were sampled. It cannot account for processes born and exited between snapshots,
CPU before the first sample or after the last one, or an unobserved escaped child.
CPU excludes the collector's process-list and sampling overhead. The existing
256-sample tail is bounded; `sample_retention` records dropped rows and rollup
counters cover all collected intervals. No cumulative child CPU is added, which
avoids counting child CPU again through its parent.

Validation uses a compiled public-SDK structure-layout probe, comparison with
Python's `process_time_ns`, identity/missing-interval tests and an owned Python
child with real CPU activity and touched memory. The first test caught the wrong
assumption that CPU ticks were nanoseconds on this machine; its failure is retained
in `H18-resource-sampler-initial-unit-failure.log`. The correction uses the observed
timebase rather than a machine-specific multiplier. Final tests and a two-process
measurement are in `H18-resource-sampler-tests.log`,
`H18-resource-supervisor-regression.log` and `H18-resource-sampler-owned.json`.
Those are Python process measurements, not CEF performance results.
