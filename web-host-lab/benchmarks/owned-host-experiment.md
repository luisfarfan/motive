# Short owned-host experiment

`tools/run_owned_host_experiment.py` is an explicit CLI for 1, 3 or 5 concurrent
Motive smoke widgets, with **one independent CEF browser host per widget**. Each
host may create several renderer/GPU/utility helpers; the supervisor records the
observed process counts and executable roles. This is a short scaling diagnostic,
not completion of the frozen benchmark protocol or a comparison with OBS.

Run only after the owned native lifecycle checks pass. It reuses the smoke
launcher's pinned local build report, exact main/helper/framework hashes,
development signature verification, fixed argv, private fresh directories and
frame/counter analysis. No arbitrary executable, URL, package or JavaScript input
is accepted. Goal-bridge bundles are rejected by the smoke profile check. The CLI
is never invoked by an automatic verification suite.

Example for the retained ephemeral smoke candidate (replace the new output path
for every run):

```sh
python3 web-host-lab/tools/run_owned_host_experiment.py \
  --build-root web-host-lab/.cache/h18-native-ephemeral \
  --expected-sha256 4f77eea5e899f98ad57cb3a4bed047dcb0c87a8b8d784a361ac73606d2fca8f7 \
  --hosts 1 --width 640 --height 360 --fps 30 --duration-ms 5000 \
  --deadline-seconds 10 --sample-interval-ms 250 --generation 1000 \
  --output-dir web-host-lab/evidence/H18-perf-owned-1-first
```

Use `--hosts 3` and then `--hosts 5` in separate explicit invocations after
reviewing the preceding result. `--preflight-only` performs no native launch.
Allowed viewports remain 640×360, 960×540 and 540×960, at 30 or 60 requested FPS;
duration stays 1–15 seconds and the per-host hard deadline is at most 25 seconds.
The `--generation` value is a base; each host records the actual base+host-index
generation. No frame index is invented when native metadata is absent.

The emergency RSS limit applies to the sum of the latest observed host trees,
with a maximum of 2048 MiB for the entire experiment. It is not multiplied by the
number of hosts. Crossing it sets one shared cancellation event; each existing
supervisor closes its own PID/birth-checked tree. Sampling is asynchronous and can
observe an overshoot, so raw observation ages are retained. A real test launches
three owned Python processes individually below 128 MiB and verifies aggregate
cancellation plus complete observed cleanup when their sum exceeds 128 MiB.

Reports retain per-host samples and raw CPU ticks/timebase, delta CPU, physical
footprint, sampled roles, frames, compressed BGRA hashes, bounded stdout/stderr and
cleanup outcomes. Latest observed aggregate footprint is distinct from adding
independent per-host peaks, and is not a simultaneous unique-page measurement.
CPU statistics include startup/shutdown and expose complete observed-identity
intervals separately. CPU before/after sampled windows and very short processes
may be missed; collector overhead is excluded. GPU remains null. Repetitions,
10-second warmup, 60-second steady-state windows, soak, shared-host layout, thermal
control, native texture consumption and OS confinement remain separate work.

`H18-owned-host-experiment-tests.log` verifies parser boundaries, aggregate RSS,
missing-value semantics, setup failures and real Python cancellation. Those tests
do not execute CEF and do not establish native performance acceptance.
