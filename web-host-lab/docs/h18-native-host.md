# H18 native host: prepared, not executed

H18 links the existing H16 fixture into an ARM64 AppKit development app with the
matching upstream wrapper, framework and five helper roles. There is no Qt,
Production, libobs, or second audiovisual clock in this process. **CEF execution,
real OnPaint/alpha, process isolation and Chromium performance remain BLOCKED.**

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

Output: `.cache/h18-native/MotiveBrowserFixture.app`. Input framework files are
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
epoch, stride and monotonic observation time are carried to the consumer. Alpha
is explicitly **unverified**, until the existing native pixel checker observes
real half-alpha fixture pixels. Observation time never becomes audiovisual PTS.

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
stop. Native crash, resize, final-close and helper cleanup are unexecuted.

A viewport change/restart currently means a **new process/generation**, with a new
origin and cache directory. There is no unproved `WasResized` ordering shortcut.
The executable accepts only the three reviewed dimensions, 30/60 FPS and a short
bounded duration, always the original three embedded H16 fixture files. It
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
there is no path resolver or network fallback. The generalized broker-to-native
inventory bridge and native event dispatcher remain pending. The Creator Runtime
MessagePort adapter is separately tested; this app does not yet execute it.

`src/adapter.rs` supplies tested admission decisions for future libobs upload,
repeat or blank: exact source generation/epoch, sequence, monotonic age, aggregate
layer visibility, explicit static hold and irreversible revocation. It makes no
OBS calls and creates no textures. Actual process-to-Production frame transport,
graphics-context ownership, uploads and alpha blending still require H17's handoff
and native tests. Neither this policy nor JavaScript replies establish libobs draw.

## Concrete exception scope for owner review

**Not granted and not executed.** The ready artifact is the `.app` above; its
current exact executable SHA-256 is `38a1f280f8c539b144ea6e0b9e6b28b336efca79e6605011484cd55cf0179d14` (also in the build report).
The proposed first exception covers only one invocation of that exact local app,
its bundled helpers, the embedded Motive-owned HTML/CSS/JS, **640×360, 30 FPS,
5 seconds**, no inputs/devices, no package content, no external URLs and no
recording/streaming/Production. Run under the external supervisor with a fresh
0700 root, minimal environment, closed inherited descriptors, a 10-second hard
deadline and the predeclared 2048 MiB emergency tree-RSS limit. Preserve exit,
observed process tree, first/latest BGRA, telemetry and cleanup evidence.

Prerequisites left before that invocation: the owner's explicit, narrowly scoped
repository-policy exception; rechecking the exact sealed bundle hash and static
signature; and review of the launcher configuration above. Local development
sealing is complete. Developer ID, hardened-runtime/JIT role entitlements,
notarization, Apple App Sandbox, real browser-process confinement and third-party
execution are **not prerequisites that this narrow smoke test claims to satisfy**:
they remain separate unopened gates. If startup is rejected or sandbox setup
fails, stop and retain the failure; do not disable the sandbox or alter macOS
permissions. Real frames/alpha and helper cleanup must pass before expanding to
960×540, 540×960, 60 FPS or benchmarks.

The request is necessarily explicit because `AGENTS.md` says “Para cualquier
trabajo de navegador usar únicamente proxima-browser MCP” and the H18 task
specifically requires owner approval before native CEF execution. Building and
signing this local app did not grant that exception.
