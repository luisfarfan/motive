# H18 native host: real smoke and independent Goal bridge

H18 links the existing H16 fixture into an ARM64 AppKit development app with the
matching upstream wrapper, framework and five helper roles. There is no Qt,
Production, libobs, or second audiovisual clock in this process. **The owner authorized local Motive fixture execution. Real OnPaint/BGRA and half-alpha pixels passed; orderly shutdown initially failed in Chromium Keychain work. The subsequent ephemeral test-backend smoke exits cleanly. OS confinement, third-party execution and performance acceptance remain separate unopened gates.**

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
cycles. They do not prove even one CEF create/destroy cycle.

The native UI thread owns all CEF browser references. Close revokes the mailbox,
hides/closes owned browsers, waits for `OnBeforeClose`, then exits the CEF loop.
The consumer is joined before state destruction; `CefShutdown` runs after browser
references are cleared. An early initialization failure also joins the consumer.
The five-second close task is cooperative; the external supervisor is the hard
stop. Default-backend real runs reached final browser close and loop return, then stalled at CefShutdown; the subsequent ephemeral test-backend smoke closed cleanly. The supervisor removed every observed owned process after its deadline. Resize, repeated restart and crash acceptance remain untested.

A viewport change/restart currently means a **new process/generation**, with a new
origin and cache directory. There is no unproved `WasResized` ordering shortcut.
The executable accepts only the three reviewed dimensions, 30/60 FPS and a short
bounded duration, with an explicit build profile: original three-file smoke or the fixed owned Goal inventory. It
accepts no URL, package, script, device or IPC endpoint. It removes inherited
environment data before loading CEF. The trusted launcher also closes inherited
file descriptors and passes a minimal environment. This is not OS confinement.

## External supervision and future libobs boundary

`poc/browser-host/supervisor.py` assigns a session and increasing generations,
starts a new process group, samples tree RSS/ps CPU, enforces deadline/cancel/RSS,
handles root crashes and terminates observed children, including previously observed children that changed sessions when a supervisor callback fails. PID identity uses public
macOS `proc_pidinfo` start seconds/microseconds plus current user. Signals are
preceded by identity rechecks; they never target process names. Cleanup (including disappearance of observed zombies) is verified
for the observed owned tree, including parent-crash tests. Kernel signal delivery
is not atomic with identity sampling; unobserved process escape is not prevented.
This supervisor is therefore **not a sandbox for hostile processes**.

The existing broker is reused unchanged and continues denying third-party
execution. Native fixture bytes are generated from a fixed three-file inventory;
there is no path resolver or network fallback. The separate Goal candidate now generates its immutable inventory through the existing broker, with exact host/widget asset separation. It links the typed native dispatcher described below; its live transport result must be assessed separately.

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

For a future live Goal run, fixed lifecycle markers retain bootstrap, ready, dispatch, acknowledgements and visual completion, without raw renderer diagnostics. An optional third bounded `visual.bgra` sample is acquired about 600 ms after the validated active observation using the same owned lease, with no extra callback copy. Its pixels must be inspected independently of those observations. No original smoke alpha patch is assumed for the Goal profile.

Developer ID, hardened runtime/JIT release entitlements, notarization, Apple App Sandbox, per-role confinement and third-party execution remain separate gates. No repeated lifecycle, benchmark matrix, Production/libobs integration or recordings are certified here.

## Real Goal execution

The first native Goal run delivered the original event through the fixed bridge and rendered the expected title/team/score, but its completed iframe stayed opaque. That [partial result](../evidence/H18-native-goal-smoke/inspection.json) is preserved. The W3C [color adjustment rule](https://www.w3.org/TR/2025/CR-css-color-adjust-1-20251216/#color-scheme-effect) requires an opaque canvas when the embedding element and document use different color schemes. Matching only the trusted outer CSS to the original widget's dark scheme fixed the observed background; original widget hashes are unchanged.

[The second real run](../evidence/H18-native-goal-alpha-smoke/report.json), generation 11 at 640×360, 30 FPS, for 5 seconds, passed native bootstrap/properties/event/ack/completion, exit0 and observed process cleanup. [Visual inspection](../evidence/H18-native-goal-alpha-smoke/inspection.json) confirms GOOOOL, Club del Puerto and 2:1 from actual BGRA. Its active sample has transparent and partially transparent pixels with the premultiplication bound; first/latest samples are fully transparent. These are native pixels and IPC observations, still not libobs draw, Production integration, OS confinement or a benchmark.

The reproducible launcher is `tools/run_owned_goal.py`; it verifies an explicit artifact hash, profile, matching pin, helpers/framework and development signature, then uses the external supervisor with fresh private roots. Its Goal checks never apply the original smoke's red-patch/counter test. Native execution is deliberately separate from `verify_h18.py`.
