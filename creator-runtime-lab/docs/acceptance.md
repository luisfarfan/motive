# H18 acceptance — 2026-11-18 (America/Lima)

**Overall: PARTIAL.** The isolated Creator Runtime foundation is implemented,
and the owned CEF host has produced real BGRA frames and the original transparent
Goal Celebration through native IPC. This is not acceptance of an official
installer, third-party sandbox, production capacity or Elements in a Motive
recording/stream. H17 has not handed off the shared core.

[Machine-readable closure](../evidence/H18-final-acceptance.json) indexes the
33 principal reports/logs and hashes the final isolated implementation. Each
frozen native artifact retains its own build and execution provenance.

Worktree `motive-h18`, branch `codex/h18-creator-runtime`, starts at the fetched
`origin/main` baseline `15ffbad307c5439270130979dae0e9d66d92d700`. Implementation is
confined to `creator-runtime-lab/` and `web-host-lab/`. The owner explicitly
requested the additional [AGENTS.md](../../AGENTS.md) policy change allowing
supervised native tests of owned Motive content without repeated exceptions.
Production, native product code, Show Control, root Cargo, design and original
Element Lab packages remain unchanged. No push, merge, rebase or release occurred.

## P0 / P1 / P2 matrix

“PASS offline” applies to the strict isolated model, never a production mutation.
“PASS native fixture” applies to the exact owned content/artifacts in the reports.

| Priority / gate | Status | Evidence and boundary |
|---|---|---|
| P0 audit / reuse | PASS | [Reuse matrix](reuse-audit.md); imports existing types, broker, mailbox and Web Element API; no new audiovisual owner |
| P0 definition / instance / source / layer | PASS offline | Stable definition/package identity, approved instance properties, typed receipt-only source/layer IDs; no scene per element |
| P0 composition in existing scene | PASS offline | [Seven examples](../evidence/H18-sdk-examples.json), including Creator Tech + Lower Third + Community Alert + Goal and two retained capture reservations: **1 scene / 14 sources / 14 layers / 4 assets**, 40 simulated receipts |
| P0 properties / H/V / z-order / visibility | PASS offline | Independently validated layouts and properties; append order; one source may have multiple placements without duplicating assets |
| P0 budgets | PASS offline | 8 scenes / 16 sources / 32 layers / 4 video resources unchanged; 256 MiB visual estimate; 128 assets /512 MiB inventory /64 MiB each; checked arithmetic |
| P0 package identity / bytes / compatibility | PASS offline | Existing experimental ZIP, version and hash checks, dependency closure, actual PNG and upstream Rust validation; seven original archives unchanged |
| P0 paths / ZIP / staging / cleanup | PASS tested boundary | [Importer](../importer/README.md): inventory, quotas, hashes, symlinks, no-follow ancestors and owned-inode cleanup; foreign entries preserved with recovery path; not same-user process confinement |
| P0 licenses | PARTIAL | Declared license and locally approved exact text checked; the existing format does not establish authorship or per-resource provenance |
| P0 import plans / receipts | PASS offline | Real Show Control `PlanStep`/property/action types; exact before/after graph, session, revision, fingerprint and ordered receipt checks; `sim-*` IDs explicitly synthetic |
| P0 partial / uncertain installation | PASS offline | Journal, snapshot and sidecar retained; CLI exits 1 on partial result; no implicit retry/replay; owner capability cannot be recovered from serialized input |
| P0 removal / recovery | PARTIAL | Owned-object removal proposal preserves shared resources; conflict/orphan assessment tested; no actual deletion or atomic rollback promise |
| P0 matching native CEF bundle | PASS static | Pinned CEF 150.0.19 + Chromium 150.0.7871.252; 213 unchanged upstream wrapper units /931 verified files; AppKit, five helper roles, local ad-hoc seals; no Qt/global installation |
| P0 initialization / OSR / orderly close | PASS native fixture | [Ephemeral smoke](../../web-host-lab/evidence/H18-native-ephemeral-smoke/report.json) and [viewport matrix](../../web-host-lab/evidence/H18-native-variants.json); default-Keychain failures retained separately |
| P0 actual frame pipeline | PASS native fixture | Real `OnPaint` → synchronous owned BGRA8 copy → original H16 Rust mailbox → independent consumer; width/height/stride/index/generation/monotonic observation carried; no CEF pointer retained |
| P0 alpha / premultiplication / pixels | PASS native fixture | Transparent corners, half-red patch, bounded BGRA and visible counter; original Goal active/complete transparency independently inspected; CPU-copy only, no zero-copy claim |
| P0 viewport / requested FPS variants | PASS native fixture | 640×360, 960×540, 540×960 at requested 30/60 FPS; five-second functional trials, not delivered-FPS or steady-state capacity certification |
| P0 bounded mailbox / stale / revoke | PASS contract; native diagnostics scoped below | At most one leased + one pending + one transient complete buffer; coalescing, invalid/stale generations and revocation tested; no host observation timestamp is used as media PTS |
| P0 external supervisor | PASS observed boundary | Deadline, cancel, aggregate RSS, PID/birth/UID checks, failure cleanup; real CEF trees cleaned after normal, aborted and failed runs; polling is not hostile-process confinement |
| P0 repeated lifecycle | PASS native fixture | [100 fresh-process cycles](../../web-host-lab/evidence/H18-native-cycles-100/summary.json): 100/100 frame/alpha/close/cleanup gates; stable artifact/runner hashes; not 100 recreations inside one long-lived host or a leak proof |
| P0 security callbacks / broker / IPC | PARTIAL | Fixed immutable inventory, exact navigation and permission policies, authenticated main-frame/process/generation message admission; [per-surface matrix](../../web-host-lab/docs/h18-security-checkpoint.md) retains unproved OS boundaries |
| P0 real Keychain boundary | FAIL / BLOCKED | Original native process reached `SecItemCopyMatching` and stalled at shutdown. The explicit Chromium test backend avoids that path; it proves neither real Keychain denial nor OS confinement |
| P0 third-party execution | BLOCKED | Browser/renderer/GPU/network file, egress, Keychain, JIT, profile and escape restrictions not established. No third-party HTML ran; sandbox was never disabled |
| P1 Goal public API / MessagePort | PASS controlled DOM and native fixture | Original widget/API/assets unchanged; fixed outer bootstrap; 11 DOM checks plus reduced motion via proxima-browser, separate native pixels/IPC |
| P1 typed native Goal dispatcher | PASS native fixture | Fixed `CefProcessMessage` and typed V8 values; browser/process/main-frame/exact URL/generation/size/arrival-time TTL checks; only approved properties and team/home/away projection; no payload-built JS |
| P1 Goal lifecycle | PASS native fixture | [Four-run closure](../evidence/binding/native-binding-closure.json): normal/H/V completion, repeated event rejected, cancel/resume/dispose; actual transparent BGRA, close and cleanup independently checked |
| P1 live Show Control authority | PARTIAL | Existing simulation ingress and offline owner grant reused; real scheduler, durable production intent and live owner integration await H17; JS ACK is never a native terminal or OBS draw receipt |
| P1 persistence / restore | PASS isolated | Package/hash/definition/property/resource reverification, incompatible/orphan assessment; sidecar restores disarmed, local-review-required, without events, scripts or process handles |
| P1 official format / project migration | NOT_EVALUATED | `motive-element-lab-review` remains experimental; no production format bump. Synthetic v1–v5 opaque-byte tests are not certification of the Production loader |
| P1 performance | PARTIAL, capacity failure retained | Actual short native scenarios, public CPU/physical-footprint sampling and 1/3/5 process experiments; full frozen warmup/steady/repetition/soak protocol remains incomplete |
| P1 five independent hosts under 2 GiB RSS | FAIL | [Resource audit](../../web-host-lab/benchmarks/h18-owned-results.md): startup crossed aggregate limit and was cancelled; quota unchanged, observed cleanup passed |
| P1 GPU / OBS comparison | NOT_EVALUATED | No attributable GPU measurement or comparable OBS trial; null is not zero; no claimed advantage over OBS |
| P1 libobs adapter preparation | PASS contract code | Tested upload/repeat/blank policy: generation/epoch, age, visibility and revocation; no graphics texture/API calls or native transport into Production |
| P1 Production / MKV / RTMP | BLOCKED | Explicit H17 shared-file handoff and integration authorization required; no stream/recording started and no output media claimed |
| P2 creator experience | PARTIAL | SDK local library/review/properties/H/V/compatibility/budget/proposed install/state/errors plus existing passive previews; no new editor/marketplace, GPUI awaits handoff |

The mixed composition uses **83,252 asset bytes** and **112,291,104 estimated
visual bytes**. The capture entries are reservations in an offline snapshot;
no camera/gameplay device was opened. The visual estimate is not measured RSS.

## Native evidence and performance boundaries

The successful smoke artifact is SHA-256
`4f77eea5e899f98ad57cb3a4bed047dcb0c87a8b8d784a361ac73606d2fca8f7`.
It uses the explicitly recorded `chromium-use-mock-keychain` backend with owned
fixed content. Chromium rendering and IPC are real; the credential backend is
for tests. The normal Goal alpha/H/V artifact is `07c0a5eee69689241a5feb5ee17fb904c2545bb0d195aac387a7fe13dc4afbfd`;
controls use `fda3ddaedeb4b0d8a91cc367e8857166529dc6dc75cce7398e249c19eb8ac267`.
[Native host details](../../web-host-lab/docs/h18-native-host.md) retain builds,
original failures and the fixed credential/backend and outer-CSS changes.
The initial opaque Goal result is not retrospectively promoted to alpha PASS.

The first native smoke and two shutdown diagnostics failed before the test
backend change. The retained public sample shows an attempted Keychain access;
no secret return or absence of an OS prompt is asserted. The first Goal bridge
transport run worked but its iframe canvas was opaque. Matching the trusted
outer document's color scheme to the unchanged widget fixed that separate pixel
failure. Transport success never overrode the alpha failure.

The [1/3/5-host audit](../../web-host-lab/benchmarks/h18-owned-results.md)
recomputes 93 host samples and 476 process rows from source reports. One and
three independent hosts completed their short run. Peaks were **658.70 MiB** and
**1993.27 MiB RSS**, leaving only **54.73 MiB** for three below the emergency
boundary. Five reached **2880.17 MiB** between sampled checks and shutdown;
that overshoot is retained. Its startup-only CPU and incomplete footprint are
not comparable with the completed five-second runs. Observed process counts
were 7, 21 and 34, not a presumed one process per widget. Physical footprint
is sampled separately from RSS; GPU remains unavailable.

The 100 cycles took 160.241 seconds and observed a maximum tree RSS of 753,488
KiB. All 100 lifecycle/pixel/cleanup gates passed; counter progression passed in
92 and was NOT_EVALUATED in eight whose first retained image was blank. Those
counter gaps are preserved, not converted into 100 counter passes. Each cycle
used a fresh process/profile/generation; this cannot establish absence of a
long-lived in-process leak. Raw BGRA, metadata, lifecycle, supervision and
compressed progress history remain available.

The [native timing audit](../../web-host-lab/evidence/H18-native-timing-summary.json)
checks 115 host runs and 351 file hashes. Across the 100 cycles, native
initialization median/p95 was **89.69/101.06 ms**, initialize-enter to the first
retained paint **211.30/250.14 ms**, and `CefShutdown` **21.16/26.09 ms**. These
intervals use one native clock; they are not launch-to-first-frame latency.
In the six short viewport trials, active consumer observations were
30.09–30.11 or 59.95–60.16 frames/s, with observed frame-age p95 no greater than
12.32 ms. This is neither sustained output FPS nor OBS rendering. Copy-only
cost, GPU, OBS upload and cross-clock Popen TTFF remain unavailable. The audit
retains 31 accepted paints not accounted for as acquisition/coalescing without
inventing a loss cause.

The requested A–L scenarios have the following **short diagnostic** coverage.
These statuses do not promote any scenario to the full benchmark protocol.

| Scenario | Status | Actual observation |
|---|---|---|
| A static widget | PASS native fixture | [Static](../../web-host-lab/evidence/H18-native-diagnostic-static/report.json): one JavaScript paint, two CEF paints including the initial blank; transparent/half-alpha final pixels and orderly cleanup |
| B animated widget | PASS native fixture | Owned counter smoke, six viewport/FPS configurations and original Goal; observed FPS must be calculated from retained native frames, not requested FPS |
| C three widgets | PASS short run | Three independent hosts completed; peak RSS 1993.27 MiB leaves very little margin, not supported-capacity acceptance |
| D five widgets | FAIL | Aggregate 2 GiB RSS emergency cancellation during startup; no completed five-widget trial |
| E hidden widget | PASS native fixture | [Hidden](../../web-host-lab/evidence/H18-native-diagnostic-hidden/report.json): native `WasHidden`, observed document visibility, zero OnPaint callbacks in the settled 1.9-second hidden interval, painting resumed |
| F suspended widget | PASS cold-suspension scope | [Replacement chain](../../web-host-lab/evidence/H18-native-replacements/summary.json): close/reap before resuming in a new process; no in-memory JavaScript continuation |
| G reload | PASS process-replacement scope | Same fixed inventory, new generation/profile/origin, prior tree reaped before launch; in-place reload NOT_EVALUATED |
| H resize | PASS process-replacement scope | Same chain replaces 640×360 with 540×960 and checks new generation/dimensions; hot `WasResized`/epoch transition NOT_EVALUATED |
| I repeated event | PASS native fixture | Fixed native Goal control scenario rejects the repeat while active, without a backlog; cancel/resume/dispose remain separate observations |
| J slow JavaScript | PASS native fixture | [Slow](../../web-host-lab/evidence/H18-native-diagnostic-slow/report.json): fixed approximately 500 ms renderer loop, measured native phase/paint gap, then orderly close and observed cleanup |
| K renderer failure | PASS controlled-failure recovery; initial FAIL retained | [Final recovery](../../web-host-lab/evidence/H18-native-diagnostic-crash-posix/report.json): renderer exit 86 (raw POSIX status 22016), immediate generation revocation, expected host error exit 42, native shutdown and observed cleanup; not a healthy exit or memory-corruption test |
| L 100 create/destroy cycles | PASS fresh-process scope | 100 separate host/browser lifetimes with fresh generations, all observed trees reaped; no long-lived host leak inference |

[Backpressure](../../web-host-lab/evidence/H18-native-diagnostic-slow-consumer/report.json)
also passed with a deliberately held 100 ms consumer lease: 140 accepted paints,
41 acquisitions, 98 coalesces and zero busy drops. This demonstrates the bounded
mailbox under real OnPaint load. Its consumer duration deliberately includes the
test delay; it is not an isolated memory-copy or OBS-upload benchmark.

The [initial controlled renderer failure](../../web-host-lab/evidence/H18-native-diagnostic-crash/report.json)
exposed a real host segmentation fault when browser destruction re-entered CEF's
renderer-termination callback. Reentrancy is the inferred cause from the pinned
source, not a symbolically proved stack diagnosis. Closing in a subsequent UI
task eliminated the observed fault;
frame admission is revoked immediately in every profile. The
[intermediate run](../../web-host-lab/evidence/H18-native-diagnostic-crash-deferred/report.json)
then closed and cleaned up, but failed because the fixture compared a raw POSIX
wait status with the decoded exit code. The final artifact decodes it explicitly
and retains both values. Both earlier failures remain available.
The final common host code also passed a separate
[positive smoke regression](../../web-host-lab/evidence/H18-native-final-smoke-repeat/report.json).
Its [first run](../../web-host-lab/evidence/H18-native-final-smoke/report.json)
retains PARTIAL because its first image was blank: frames/alpha/close/cleanup
passed, counter change was NOT_EVALUATED. The repeat used the same binary and
limits, and observed the counter. The replacement chain uses the previously
frozen smoke artifact and generations 30→31→32; it does not claim preservation
of the old JavaScript heap or reuse of a frame lease/cache/origin.
The [diagnostic report](../../web-host-lab/docs/h18-diagnostics.md) links the
pinned source research and distinguishes each native experiment from its pure
boundary/classification tests.

## Reproducible verification

[Runtime summary](../evidence/H18-runtime-summary.json) pins commands, exit codes,
logs, implementation hashes and scope. [Binding closure](../evidence/binding/native-binding-closure.json)
rechecks the four native artifacts/pixel samples and unchanged DOM provenance.
Historical static reports describe only the work their own tool executed;
`native_executed=false` in an earlier report does not describe later runs.

- Creator runtime: **34 Rust tests** (28 contract/state + 6 recovery), Clippy and format.
- Importer/SDK: **32 Python tests** (17 importer + 15 SDK), seven original-package scenarios, restoration assessed without activation.
- Binding: **12 Rust + 10 Node + 5 Python**, Clippy/format; original DOM provenance preserved. The five native-bootstrap Node tests are distinct from real CEF runs.
- Host contracts: **20 Rust**; C ABI: **5 Rust**, linked C++ frame/Goal-boundary checks. Synthetic ABI cycles remain distinct from the actual 100 native cycles.
- Final unchanged host contracts, Clippy/format and **2 Node** interop checks passed; [commands and logs](../../web-host-lab/evidence/H18-final-host-checks.json).
- The final complete host Python suite passed **46 tests**, including broker/frame inspection, real owned non-browser supervision, resource sampling, launchers, cycle/scaling guards and diagnostic classification; [final check](../../web-host-lab/evidence/H18-final-python-check.json). Frame-bridge format also passed after the final changes.
- Reused regressions: **48 Element Lab Python + 6 Node + 129 Show Control Rust**. H18 does not claim execution of root Motive/native production suites.

Review fixes include checked resource dimensions, actual upstream type/action
validation, native asset identities, source-definition comparison on restore,
monotonic generations, owner-bound in-memory journals, preservation of partial
batch outcomes, resource-only instance conflicts and rejection of malformed
receipt indices. The SDK outer staging workspace now removes only an empty,
identity-checked owned directory; unexpected objects survive with an explicit
recovery path. Initial failing tests and native runs remain in evidence.

## Remaining gates and integration recommendation

1. Establish OS confinement for the browser and each relevant child role before
   admitting third-party HTML. Verify actual filesystem, Keychain, networking,
   localhost/WebSocket/WebRTC, device/clipboard, profile and escape behavior;
   CSP, a process boundary, test Keychain backend and supervisor are insufficient.
2. Preserve the 2 GiB emergency limit. Investigate host/helper overhead and a
   separately reviewed topology before repeating five instances. Complete the
   frozen warmup/steady/repetition/soak protocol before claiming supported
   capacity, sustained FPS or performance relative to OBS.
3. Obtain explicit H17 shared-file handoff and authorization, then follow the
   [minimal owner integration plan](native-integration.md): real owner grant,
   durable pre-dispatch intent and receipts, managed asset broker, process/frame
   transport, OBS graphics-context texture lifetime, shared UI/CLI/MCP and
   disabled persisted bindings. Keep one audiovisual owner and OBS clock.
4. Decide official package/project compatibility explicitly. Use actual managed
   asset receipts; preserve recovery states and old project compatibility.
   The experimental sidecar and simulated IDs are not production installations.
5. Verify the transparent Goal and native elements in decoded preview/MKV/local
   RTMP, including cancellation/crash/restart/removal during output, timestamps,
   resource release and H17 regressions. Until then, elements during a real
   stream remain unaccepted.
