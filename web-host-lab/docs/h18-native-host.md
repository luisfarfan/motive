# H18 native host: real smoke and independent Goal bridge

H18 links the existing H16 fixture into an ARM64 AppKit development app with the
matching upstream wrapper, framework and five helper roles. There is no Qt,
Production, libobs, or second audiovisual clock in this process. **The owner authorized local Motive fixture execution. Real OnPaint/BGRA, alpha, 100 new-process cycles and the four fixed Goal closures passed their scoped gates.** Orderly shutdown initially failed in Chromium Keychain work; those failures remain retained. Later runs use the explicit test Keychain backend. CPU/RSS/footprint trials now exist, with a five-host RSS failure; full performance acceptance, OS confinement and third-party execution remain unaccepted.

## Reproduce only authorized work

From the H18 worktree, with the H16 pin A archive and extracted SDK in this lab's
ignored `.cache/`:

```sh
python3 web-host-lab/tools/verify_h18.py
```

The script runs Rust contracts/FFI, Clippy/format, Python broker and supervisor,
Node interop, the native build and a C++ ABI test. The C++ test uses synthetic
bytes and does not link or load CEF. The supervisor tests launch short-lived,
owned Python processes, never a browser. H16 historical evidence is not rewritten.

`tools/build_native.py` verifies the archive plus 931 API, wrapper and runtime
files before building 213 upstream wrapper translation units using their macOS
source list. The SDK's original sources are unchanged. CMake is not required and
no tool is installed globally. The matching pin remains:

- CEF `150.0.19+gcf60f42+chromium-150.0.7871.252`, API `15000`.
- Archive SHA-256 `0343233fc462384c2f1f58a4222028bc6171f05948a822241f89df2faa7cee8d`.
- Matching source revision `cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3`.

The original immutable output remains `.cache/h18-native/MotiveBrowserFixture.app`. New diagnostic and ephemeral builds use separate roots. Input framework files are
verified byte-for-byte before local ad-hoc sealing. Its downloaded signature had
an incomplete resource seal; that initial failure is retained. The local copy's
nested dylibs, framework, helpers and outer app are sealed inside-out without
Keychain access, certificates, entitlements or global policy changes.
`codesign --verify --strict --deep` passes statically. Pre/post-sign framework
hashes and exact final executable hashes appear in
[H18-native-build.json](../evidence/H18-native-build.json). A code-signature check
is not sandbox, Gatekeeper, notarization, launch or JIT evidence.

## Actual prepared pipeline and lifetime

`OnPaint` checks owned browser/main view, dimensions and dirty rectangles, then
passes the callback's complete BGRA8 image to a small trusted C ABI. That ABI
calls **the existing H16 Rust Mailbox**. The Rust contract remains safe Rust; only
`poc/frame-bridge` contains the documented raw-pointer boundary. The callback
copies synchronously, and no CEF pointer survives it. Input index/generation,
epoch, stride and monotonic observation time are carried to the consumer. Metadata conservatively keeps alpha unverified. The separate real native pixel report verifies the original fixture’s transparent and half-alpha patches; that observation does not certify arbitrary content or a libobs upload. Observation time never becomes audiovisual PTS.

Logical pixel residency is one leased frame + one pending frame + one transient
callback copy: at most three complete owned buffers. At 640×360 that is
2,764,800 bytes; it excludes Chromium, allocator/page cache, stacks, telemetry and
future GPU texture memory. The consumer cannot acquire another frame while its
lease is live. Coalescing retains a complete latest image; contention drops a
paint without blocking CEF. Leases retain owned bytes through revocation, but
`lease_valid` becomes false, preventing stale use as valid visual state.

The consumer is a separate host thread; no disk work happens in OnPaint. It saves
two bounded raw samples (`first.bgra`, `latest.bgra`), metadata and up to 1024
telemetry rows. Callback busy/invalid counts and maximum publish duration are separate from disk-consumer duration; publish includes validation/lock/copy overhead and is not an isolated memcpy benchmark. Both disk samples are overwritten/created only within the fresh
private launch directory. There is no unbounded frame queue and no zero-copy
claim. FFI tests prove copying, ABI fields, generation/epoch rejection, stale and
future times, one consumer, revocation lifetime and 100 synthetic create/destroy
cycles. Those synthetic tests do not prove CEF lifecycle; the independent real
100-cycle evidence below does so only for fresh processes.

The native UI thread owns all CEF browser references. Close revokes the mailbox,
hides/closes owned browsers, waits for `OnBeforeClose`, then exits the CEF loop.
The consumer is joined before state destruction; `CefShutdown` runs after browser
references are cleared. An early initialization failure also joins the consumer.
The configured-duration close task is cooperative; the external supervisor is the hard
stop. Default-backend real runs reached final browser close and loop return, then stalled at CefShutdown; the subsequent ephemeral test-backend smoke and 100 fresh-process cycles closed cleanly. The supervisor removed every observed owned process after the failed runs' deadline. These cycles do not test hot reload, in-process browser recreation, OS suspend/resume or live resize.

A viewport change/restart currently means a **new process/generation**, with a new
origin and cache directory. There is no unproved `WasResized` ordering shortcut.
The executable accepts only the three reviewed dimensions, 30/60 FPS and a short
bounded duration, with an explicit build profile: original three-file smoke,
fixed owned Goal inventory or separately reviewed fixed diagnostics. It
accepts no URL, package, script, device or IPC endpoint. It removes inherited
environment data before loading CEF. The trusted launcher also closes inherited
file descriptors and passes a minimal environment. This is not OS confinement.

## External supervision and future libobs boundary

`poc/browser-host/supervisor.py` assigns a session and increasing generations,
starts a new process group, samples tree RSS and public per-process resource data, enforces deadline/cancel/RSS,
handles root crashes and terminates observed children, including previously observed children that changed sessions when a supervisor callback fails. PID identity uses public
macOS `proc_pidinfo` start seconds/microseconds plus current user. Signals are
preceded by identity rechecks; they never target process names. Cleanup (including disappearance of observed zombies) is verified
for the observed owned tree, including parent-crash tests. Kernel signal delivery
is not atomic with identity sampling; unobserved process escape is not prevented.
This supervisor is therefore **not a sandbox for hostile processes**. Public
`proc_pid_rusage` provides cumulative CPU ticks converted with the measured Mach
timebase and `ri_phys_footprint`; consecutive identity-matched deltas supply CPU
observations. Missing samples remain unavailable. Historical ps CPU and legacy
null footprint fields are retained; they do not erase the new measured fields.

The existing broker is reused unchanged and continues denying third-party
execution. Native fixture bytes are generated from a fixed three-file inventory;
there is no path resolver or network fallback. The separate Goal profile generates its immutable inventory through the existing broker, with exact host/widget asset separation. Its real typed transport and pixels are assessed separately below.

`src/adapter.rs` supplies tested admission decisions for future libobs upload,
repeat or blank: exact source generation/epoch, sequence, monotonic age, aggregate
layer visibility, explicit static hold and irreversible revocation. It makes no
OBS calls and creates no textures. Actual process-to-Production frame transport,
graphics-context ownership, uploads and alpha blending still require H17's handoff
and native tests. Neither this policy nor JavaScript replies establish libobs draw.

## Authorized native observations and shutdown diagnosis

The owner explicitly authorized the original SHA-256 `38a1f280f8c539b144ea6e0b9e6b28b336efca79e6605011484cd55cf0179d14`: 640×360, 30 FPS, 5 seconds under the external 10-second deadline and 2048 MiB emergency RSS limit, fresh 0700 root and minimal environment. The original bundle remains intact. `AGENTS.md` now permits local owned Motive native tests while retaining third-party, production and security boundaries.

[The original run](../evidence/H18-native-smoke-run.json) produced real first/latest BGRA and changing visual counters. [The pixel check](../evidence/H18-native-smoke-pixels.json) observes transparent corners, half-red premultiplied BGRA and the premultiplication bound. The run failed its deadline; cleanup removed all observed owned identities. Neither frames nor cleanup changes the orderly-close failure.

The diagnostic build preserves a bounded `lifecycle.jsonl` and writes frames/telemetry before shutdown. It reached `before_close`, `loop_return`, `consumer_joined`, `frame_report_written`, `shutdown_enter`, but no `shutdown_return`. A second implementation makes close/quit idempotent and removes the post-loop quit; [that run still failed](../evidence/H18-native-close-once-run.json). [Pinned Chromium source and hashes](../../creator-runtime-lab/evidence/binding/native-keychain-research.json) support the diagnosis. The retained owned-process sample shows a worker blocked in `SecItemCopyMatching` → `SecKeychainItemCopyContent` → SecurityServer decrypt. Opaque CEF nearest-export symbols are not treated as exact internal call names.

The isolated ephemeral smoke root is `.cache/h18-native-ephemeral`, compiled with the matching Chromium public `use-mock-keychain` switch via trusted `OnBeforeCommandLineProcessing`. Its profile explicitly reports `credential_backend: chromium-use-mock-keychain`. Chromium uses its test Keychain backend for this ephemeral fixture; this is **not evidence of real Keychain denial or an OS sandbox**. No credential is read by the adapter, no Keychain setting/permission is changed, and no sandbox bypass is enabled. The report [H18-native-ephemeral-build.json](../evidence/H18-native-ephemeral-build.json) records the exact artifact. [The subsequent supervised ephemeral smoke](../evidence/H18-native-ephemeral-smoke/report.json) passed real pixels, orderly exit0, shutdown return and zero observed remaining processes. This confirms the controlled test-backend configuration only; default-backend failures are retained.

## Fixed native Goal bridge

The separate `.cache/h18-native-bridge-alpha-ephemeral` profile embeds the unchanged Goal HTML/CSS/modules and the reviewed fixed outer bootstrap. The browser process owns an offline `motive-creator-binding` grant and the existing Show Control simulation ingress; its C ABI emits only admitted H16 visual envelopes. It never exposes Production or gives JavaScript an owner-grant constructor.

`CefProcessMessage` checks actual browser identity, process direction, main frame, exact generation URL, argument count and byte limits. The renderer installs its native status function only in the trusted outer context. It constructs V8 data values and calls fixed functions; there is no payload-built JavaScript, eval or ExecuteJavaScript. The opaque sandboxed iframe receives the unchanged visual message through its private MessagePort. Statuses are finite schema-checked observations and cannot establish libobs draw or native terminal outcome.

A trusted shared monotonic origin lets the renderer recheck expiry at arrival; queued IPC cannot freeze the browser's sent time. Context release invalidates the capability. Rust tests and a linked C++ boundary/FFI test cover stale generation, role/frame/URL mismatch, excess size, delayed expiry, duplicate acknowledgements and the original event projection without loading CEF. The compiled bridge is separately reviewed; static success does not prove delivery.

The real Goal runs retain fixed lifecycle markers for bootstrap, ready, dispatch, acknowledgements and visual completion, without raw renderer diagnostics. A third bounded `visual.bgra` sample is acquired about 600 ms after the validated active observation using the same owned lease, with no extra callback copy. Its pixels are inspected independently of those observations. No original smoke alpha patch is assumed for the Goal profile.

Developer ID, hardened runtime/JIT release entitlements, notarization, Apple App Sandbox, per-role confinement and third-party execution remain separate gates. The scoped lifecycle/resource observations below do not accept the full benchmark matrix, Production/libobs integration or recordings.

## Real Goal execution

The first native Goal run delivered the original event through the fixed bridge and rendered the expected title/team/score, but its completed iframe stayed opaque. That [partial result](../evidence/H18-native-goal-smoke/inspection.json) is preserved. The W3C [color adjustment rule](https://www.w3.org/TR/2025/CR-css-color-adjust-1-20251216/#color-scheme-effect) requires an opaque canvas when the embedding element and document use different color schemes. Matching only the trusted outer CSS to the original widget's dark scheme fixed the observed background; original widget hashes are unchanged.

[The second real run](../evidence/H18-native-goal-alpha-smoke/report.json), generation 11 at 640×360, 30 FPS, for 5 seconds, passed native bootstrap/properties/event/ack/completion, exit0 and observed process cleanup. [Visual inspection](../evidence/H18-native-goal-alpha-smoke/inspection.json) confirms GOOOOL, Club del Puerto and 2:1 from actual BGRA. Its active sample has transparent and partially transparent pixels with the premultiplication bound; first/latest samples are fully transparent. These are native pixels and IPC observations, still not libobs draw, Production integration, OS confinement or a benchmark.

The reproducible launcher is `tools/run_owned_goal.py`; it verifies an explicit artifact hash, profile, matching pin, helpers/framework and development signature, then uses the external supervisor with fresh private roots. Its Goal checks never apply the original smoke's red-patch/counter test. Native execution is deliberately separate from `verify_h18.py`.

## Fixed native lifecycle controls

The separately compiled `owned-goal-controls` profile uses a native-only enum to
request exactly one repeat-rejection probe, cancel, resume and dispose through
the existing Binding. JavaScript has no route to that C ABI. The repeat is
rejected while active, without a backlog. Cancel/resume progress only after the
expected acknowledgement; dispose revokes admission immediately. Its final
acknowledgement is a bounded observation of the expected sequence and cannot
reopen the binding or certify process cleanup.

Five Rust tests, Clippy and the linked C++ FFI test pass without loading CEF.
The separate artifact in `H18-native-bridge-controls-ephemeral-build.json` has
not been executed by those checks. Its fixed native scenario requires all
observations and independently verifies final pixels, real browser shutdown and
external cleanup when run with `run_owned_goal.py --control-scenario`.

[The real fixed control run](../evidence/H18-native-goal-controls/report.json) then
passed at 640×360, 30 FPS, generation 14: repeat rejected, cancel/resume/dispose
observed in order, retained active pixels, final transparent pixels, exit 0 and
zero observed remaining processes. [Independent source and pixel inspection](../evidence/H18-native-goal-controls/inspection.json)
keeps the final ACK distinct from native shutdown and cleanup. Horizontal
[960×540](../evidence/H18-native-goal-horizontal/report.json) and vertical
[540×960](../evidence/H18-native-goal-vertical/report.json) normal Goal runs also passed their own native
IPC, visible content, alpha, completed transparency and cleanup checks.

## Real serial lifecycle cycles

[100 cycles](../evidence/H18-native-cycles-100/summary.json) passed with the same
`4f77eea5e899…` ephemeral smoke binary, fresh generations and one new process/browser
per cycle: 640×360, requested 30 FPS, 1000 ms duration, 6 s external deadline and
2 GiB RSS limit. Total elapsed time was 160.241 s. Every cycle retained real frame
and alpha checks, orderly exit 0 and zero remaining observed processes. The
visible counter changed in 92 cycles; eight remain NOT_EVALUATED and were not
used to fabricate lifecycle success. `run_native_cycles.py` preserves individual
reports and incremental summaries and stops at the first required-gate failure.

This demonstrates 100 fresh host lifecycles, not 100 browser recreations within
one host, hot reload, dynamic resize, contamination freedom or long-lived leak
freedom. Rust generation/revocation tests and native process observations retain
their separate scopes.

[The replacement sequence](../evidence/H18-native-replacements/summary.json)
separately passed generations 30→31→32 using the unchanged `4f77eea5e899…` smoke
artifact: 640×360 initial, 640×360 cold reload, then 540×960 replacement. Each
prior native tree was observed reaped before the next launch, with a fresh root,
generation and admission. This is cold suspend/resume in the lifecycle contract
and reload/resize by process replacement. It is not system sleep/wake, hot
reload, in-place `WasResized`, or JavaScript heap restoration. Origin strings in
the summary are constructed from the contract, not independent network probes.

[The retained timing audit](../evidence/H18-native-timing-summary.json) checks 115
host runs and 351 source-file hashes across the viewport, resource and cycle
evidence. Native same-clock observations support frame age, retained-sample rate
and close/shutdown intervals. The first retained paint may be blank or follow
coalesced callbacks; it is not actual first paint or content-ready latency.
Consumer work includes file writes and lease release, not an isolated copy or
libobs upload. The exact retained frame-consumer header matches the build; the
whole fixture source snapshot was not recovered byte-for-byte. No Python/native
clock calibration or displayed-output FPS is inferred.

## Audited short resource trials

[The read-only audit](../evidence/H18-owned-resource-summary.json) recomputed 93
host samples and 476 process rows from three real 1/3/5-host trials using the same
ephemeral smoke artifact. Each independent host requested one 640×360 widget at
30 FPS for five seconds. This is an independent-host topology, not multiple
widgets inside one Chromium host.

| Hosts | Trial result | Observed CPU, one core = 100% | Peak sampled RSS | Maximum available sampled footprint |
|---|---|---|---|---|
| 1 | Completed | 12.15% | 658.70 MiB | 367.62 MiB |
| 3 | Completed | 32.98% | 1993.27 MiB | 1136.14 MiB |
| 5 | Cancelled by 2 GiB aggregate RSS limit | 131.15%, truncated startup | 2880.17 MiB | 812.87 MiB; unavailable at RSS peak |

CPU divides observed identity-matched CPU deltas by launch-to-join wall time;
it omits unsampled process work and collector overhead. Memory totals combine
asynchronous latest observations; RSS can double-count shared pages and footprint
is not unique physical RAM or coalition accounting. Three hosts left only
54.73 MiB RSS headroom. Five hosts did not complete nominal duration, and its
incomplete footprint cannot support a lower-memory claim. Every observed tree
was cleaned up; that does not convert the five-host failure into a pass.

There was one short cold-start trial per topology, without the frozen warmup,
repetition or soak protocol. Actual sampling intervals reached 362.56 ms despite
the nominal 250 ms target. GPU remains null, and there is no OBS comparison,
synchronized cross-clock latency, steady-state capacity or full benchmark PASS.

## Fixed native diagnostics

Separate immutable owned profiles exercise narrow failure/lifecycle paths with
fresh generations, 640×360, requested 30 FPS, five-second duration, ten-second
supervision and the explicit test Keychain backend. These are real CEF trials;
they do not complete the frozen benchmark protocol or execute creator-supplied
scripts.

| Profile / exact report | Observed result |
|---|---|
| [Static](../evidence/H18-native-diagnostic-static/report.json), gen 20 | PASS: one JS paint marker, two native paints; alpha, revocation, native close and observed cleanup |
| [Hidden](../evidence/H18-native-diagnostic-hidden/report.json), gen 21 | PASS: settled hidden callback count remained 31→31, no accepted samples during that window; document hidden/visible events and resumed OSR; maximum observed paint gap 2013.11 ms |
| [Slow JS](../evidence/H18-native-diagnostic-slow/report.json), gen 22 | PASS: fixed blocking phase observed for 500.122 ms, maximum retained paint gap 455.20 ms; native close and cleanup |
| [Slow consumer](../evidence/H18-native-diagnostic-slow-consumer/report.json), gen 24 | PASS: deliberate 100 ms consumer delay, 140 accepted paints, 41 acquisitions and 98 coalesced frames; bounded mailbox and clean close |
| [Controlled renderer exit](../evidence/H18-native-diagnostic-crash-posix/report.json), gen 26 | PASS of expected-error handling: renderer raw status 22016 decodes to exit 86, admission revoked, CefShutdown returned, host exits 42 as specified, zero observed remaining processes |

Host exit 42 is not a healthy render completion. It records the deliberate child
failure, and retained pixels remain offline evidence after revocation. The first
[crash attempt](../evidence/H18-native-diagnostic-crash/report.json) terminated
the host with SIGSEGV; the [deferred-close attempt](../evidence/H18-native-diagnostic-crash-deferred/report.json)
closed and cleaned up but misclassified the raw POSIX status and exited 43. Both
failures remain unchanged. [Pinned-source research](../evidence/H18-native-crash-research.json)
records immediate admission revocation, close deferred outside the CEF renderer
termination callback, and public POSIX status decoding.

The final positive smoke regression uses a separate `59ebe9378186…` artifact
containing those shutdown changes. Its [first run](../evidence/H18-native-final-smoke/report.json)
remains PARTIAL because the initial counter sample was blank, while frames,
alpha, orderly close and cleanup passed. [The same-artifact repeat](../evidence/H18-native-final-smoke-repeat/report.json)
passed all those gates including counter progression; it does not rewrite the
earlier observation or substitute its hash for the 100-cycle artifact.

Hidden/resumed OSR does not test system suspend/resume or dynamic resize. A
controlled `_exit(86)` does not test memory corruption, hostile process escape
or the OS sandbox. The slow-consumer counters demonstrate bounded coalescing in
this run; they do not measure all Chromium memory or prove in-process leak freedom.
