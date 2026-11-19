# H19 native multi-widget host

H19 extends the existing AppKit/CEF fixture. It does not introduce another engine,
Qt, a Production instance or a media clock. Execution remains restricted to the
compiled owned inventory. Third-party admission and a production credential
configuration are **BLOCKED**; the executed development profiles explicitly use
Chromium's test Keychain backend. See [security](h19-security.md) and
[distribution](h19-distribution.md) for the independent gates.

On the shared Mac, builds and physical/native trials also require the common
`/Users/luisfarfan/Developer/products/motive/var/run/physical-test.lock` directory.
Acquire it with an exclusive `mkdir`, then write an `OWNER` file recording the
worktree, task, process identity and intended bounded window. An existing lock
means wait or coordinate with its owner; never remove a foreign lock. Release
only a matching own lock after observed native cleanup and build completion.
Read-only evidence audits do not need this physical-test slot. The H20 capture
worktree uses the same slot; coordination is not a Browser/OBS integration handoff.

## Ownership and fault domains

One `Host` owns the CEF loop and the UI-thread collection of browser instances.
Each instance owns its immutable identity/generation, unique `motive://iN-gG/`
origin, exact resource inventory, separately created in-memory RequestContext,
viewport epoch, Rust mailbox, bounded disk consumer, health and lifecycle trace.
The Goal profile additionally owns an independent offline binding and finite
status/event channel. Original Goal assets and its public API remain unchanged.

Distinct contexts isolate the configured storage domains; they do **not** prove
OS isolation or force independent renderer processes. The renderer reports its
PID from native code, and the external supervisor corroborates PID/start identity.
A termination immediately revokes all live instances mapped to the same PID.
Unknown mappings are conservatively included in that failure domain. Proven
unrelated renderer identities remain live. Actual browser closes are posted to
the next CEF UI task because closing from the termination callback violates an
upstream navigation-lock constraint observed in H18. Shared-process propagation
has policy tests; the retained native runs must establish which topology actually
occurred rather than claim Chromium was forced to share a renderer.

`OnBeforeClose` releases the instance's context and joins/finalizes its consumer.
The host quits only when its bounded shutdown was requested and all browser
creates/final closes have settled. `CefShutdown` follows the CEF loop and cleared
browser references. The external supervisor still supplies the hard time/RSS
limit and checks the observed owned process identities. This is not hostile
process-escape containment.

The original single-widget CLI remains. The multi CLI accepts only bounded
widget counts, reviewed dimensions/FPS, generation values with restart headroom,
a finite scenario name and a fresh private directory. It accepts no URL, package,
script, credential, arbitrary endpoint or Production handle. The native entry
clears inherited environment data; that does not confine native filesystem access.

## Resize, visibility and frames

Hot resize is deliberately narrower than a general resize API. The UI thread
revokes the old epoch, stops its consumer, preserves its final counters/frames,
allocates a fresh mailbox/consumer and calls supported `WasResized`/`Invalidate`.
An instance never reuses a geometry within the same browser generation. This
prevents a delayed A-sized paint from being accepted after A→B→A: that transition
is rejected and requires cold browser replacement. Matching dimensions alone is
not a general CEF synchronization barrier. Each completed epoch has its own
retained directory and `instances.json` history entry.

The final 600 s candidate run retained correct epoch accounting but failed the
independent peer-continuity gate: resizing C coincided with a 458.98 ms gap in D
against the unchanged 250 ms limit. Hot resize remains a constrained experiment,
not an accepted Production transition. The owner-side manager retains cold
replacement, whose integrated execution and peer cadence still require proof.
See the [final results](h19-results.md) for this failure and footprint growth.

The smoke hidden scenario uses `WasHidden` and observes suppression/resumption;
it does not claim JavaScript suspension. Suspension closes a browser; explicit
recreation receives a new generation. The separate Goal-hidden profile cancels
through the existing binding while active, waits for the matching accepted ACK,
and then hides. Its fixed resume operation similarly waits for its ACK before
showing/invalidation. Acceptance additionally requires real active pixels and
native OSR/cleanup evidence, not just acknowledgements. The standalone Goal
controls profile retains repeat rejection, cancel, resume and dispose. Only
instance 1 receives the fixed Goal event; peer instances bootstrap/properties
and remain Ready, enabling state-contamination checks.

Every accepted `OnPaint` copies complete BGRA synchronously through the existing
Rust bridge. No callback pointer survives return. Generation/epoch, dimensions,
stride, index and native monotonic observation accompany each owned frame.
Dirty rectangles are validated, but complete buffers are retained because
coalescing arbitrary deltas would lose edits. No zero-copy or libobs upload is
claimed. The copied-byte/time counters measure the implemented CPU copy, including
page faults and timing overhead; they do not measure GPU upload.

`accounting_v2` classifies accepted paints into pending, leased, coalesced, stale,
consumed, released-unconsumed, close-invalidated and generation-revoked outcomes.
Acquisition is an overlapping transition count. The sink calls `complete` only
following successful disk writes; revocation during a write can leave a retained
pixel observation while rejecting its use as a completed current frame. Native
counters separately report disk attempts/successes, rejected completions and
sample-capacity drops. `samples_truncated` means the fixed 65,536-row cap was hit,
not that a lease was revoked. These are laboratory consumer samples, not displayed
or encoded audiovisual FPS.

The first accepted paint and first nontransparent paint use the native monotonic
clock. Nonzero alpha is a pixel observation, **not** a content-specific useful-frame
or Goal-completion assertion. Benchmark derivation must use its own retained
pixel oracles and distinguish warmup from steady state. Native observation time
never becomes multimedia PTS; libobs remains the future audiovisual owner.

## Reproduction

Builds do not launch Chromium. The following uses the existing verified CEF pin,
its wrapper, local ad-hoc seals and private lab build roots:

```sh
python3 web-host-lab/tools/build_native.py --multi \
  --build-name h19-native-multi-repro-r1-ephemeral --mock-keychain
python3 web-host-lab/tools/build_native.py --multi --bridge \
  --build-name h19-native-multi-goal-repro-r1-ephemeral --mock-keychain
python3 web-host-lab/tools/build_native.py --multi --bridge --controls \
  --build-name h19-native-multi-goal-controls-repro-r1-ephemeral --mock-keychain
```

H19 build names are immutable once their build report exists: the builder
refuses reuse before modifying that artifact. Choose a fresh bounded reproduction
suffix (for example `r2`) for another build. Current Goal source also supports the
`hidden` scenario in the same Goal reproduction binary; the original Goal-hidden
artifact remains separate evidence from the earlier Goal build.
`--mock-keychain` is a test profile selector, not a production fix.

Use the external launcher, not direct native execution. For a fresh reproduction,
use the exact main executable SHA-256 from its new build report and its matching
build root. The following example intentionally selects the retained immutable
smoke-final artifact; its hash is an identity check, not a promise that compiling
current sources reproduces those bytes:

```sh
python3 web-host-lab/tools/run_h19_multi.py \
  --build-root web-host-lab/.cache/h19-native-multi-final-ephemeral \
  --expected-sha256 edccc2eef22cd2f7ef336c4256023b42555da97a8b1b9f18498a6ed715a07bd6 \
  --output-dir web-host-lab/evidence/H19-new-owned-run \
  --instances 3 --scenario steady --duration-ms 72000 \
  --deadline-seconds 85 --rss-limit-mib 2048
```

The output directory must be new. The launcher owns the decoy/listener for the
security scenario and stops if its loopback port is occupied. Do not manually
point probes at an existing service. The lifecycle scenario starts exactly three
widgets and requires at least 25 seconds. It creates/removes/replaces instances,
hides/resumes, performs a one-way hot resize, exercises a controlled renderer exit
and recreates the affected widget, then closes the host. The maintained H19
reports distinguish each build, run, failure, scope and incomplete acceptance.

Compile-only regressions are retained in
[H19-native-api-regressions.json](../evidence/H19-native-api-regressions.json).
Its initial harness failure is preserved separately: the harness omitted the
existing build's upstream aggregate-initializer warning option; aligning the
harness flags produced eight passing H18 profile checks without a source change.
`tests/native_multi_policy.cc` checks shared/unknown PID failure propagation,
generation headroom and the no-geometry-reuse rule without loading CEF.

## Retained source correspondence

[H19-build-sources/index.json](../evidence/H19-build-sources/index.json) records
all eight built H19 artifact versions, exact main executable hashes, source
provenance, deterministic compressed archives and verified archive member hashes.
The original reports are included inside each archive and are not rewritten.

Six build reports contain build-time snapshot maps. The earliest smoke and Goal
native sources were recovered after build and matched byte-for-byte to their
original recorded hashes; the index explicitly labels that provenance. The early
Goal bridge file was recovered by exact hash from current bytes. The first smoke's
`poc/frame-bridge/src/lib.rs` SHA-256 `11156b173eb0e8c95015190d5b1bf262e8f70aa13647f24e2719f114d3d97e38`
was not found in retained snapshots, current sources or local Git path history.
It remains **unrecoverable** in this archive; later implementation is not silently
substituted. Legacy generated headers lacking a recorded source hash are retained
as later observations, not retroactively certified inputs.

Archive integrity passes, while aggregate recorded-source coverage is **PARTIAL**
for that one missing file. All named final-build snapshot hashes match. Neither
statement proves a reproducible binary rebuild or a complete corresponding-source
release: Cargo manifests/locks and all dependency sources were outside the
historical snapshot map, and upstream CEF remains separately pinned.

```sh
python3 web-host-lab/tools/h19_archive_build_sources.py --verify-only
```

The archive tool never compiles or executes a host. It refuses changed existing
archives, validates path/size limits and source hashes, and never fabricates
missing source bytes.


## Fixed-length disk consumer candidate

The immutable `h19-native-multi-repro-r1-ephemeral` artifact changes only the
laboratory latest-frame file writer: the first complete write establishes its
length with one `ftruncate`; every later accepted write must match that byte
length and borrowed descriptor and still performs a complete `pwrite` loop.
There is no reduced disk sampling, skipped frame, changed consumer sleep or new
mailbox completion rule. The first/visual file paths keep their earlier behavior.
The helper's byte-length check is not a width/height or generation authority;
those remain the immutable mailbox layout and native epoch admission checks.

Per-epoch telemetry adds `latest_file_full_writes`,
`latest_file_ftruncate_calls`, `latest_file_rejected_geometry_or_descriptor` and
`latest_file_fixed_bytes`. The rejection counter name includes geometry, but its
specific check is byte length/descriptor; it cannot independently distinguish
same-byte-length viewports. The expected successful epoch has one length-setting
call and a full latest-file write for every successful disk sink operation.
Completion rejected by concurrent revocation remains separately classified.

[The synthetic test](../evidence/H19-consumer-fixed-file-test/report.json) uses
real temporary files and the actual Rust mailbox/FrameConsumer: old trailing bytes
are removed on the first write, subsequent full writes replace every byte,
shorter/longer writes and descriptor changes are refused without changing data,
and two consumed frames preserve different `first.bgra`/`latest.bgra` values.
The reusable H19 verifier now includes that C++ test, without loading Chromium.

[Candidate source provenance](../evidence/H19-candidate-build-sources/index.json)
retains the new exact source archive separately from the original eight-build
index. The candidate executable hash is
`8a76e3ce6409d911cf04bd4815c5c8065d13aa21a8c620cdf839f0d7b44c311b`.
The code change removes redundant length-setting syscalls; it does **not** establish
that those calls caused the measured consumer stalls, nor does it establish a
performance improvement. The controlled old/new A/B and subsequent native evidence
must decide that claim. Earlier Goal functional results identify their original
immutable builds and do not automatically accept this candidate's Goal profile.

To archive only a new build, use a fresh output directory and its exact report:

```sh
python3 web-host-lab/tools/h19_archive_build_sources.py \
  --build-report evidence/H19-native-multi-repro-r1-ephemeral-build.json \
  --output evidence/H19-candidate-build-sources
python3 web-host-lab/tools/h19_archive_build_sources.py \
  --output evidence/H19-candidate-build-sources --verify-only
```
