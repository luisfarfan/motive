# H18 security checkpoint

**Third-party execution BLOCKED.** The compiled fixture has no package loader and
serves only a fixed Motive-owned inventory (smoke or reviewed Goal profile). The owner authorized local fixture execution; original smoke produced real frames but stalled during shutdown in a Chromium Keychain task. Subsequent explicit test-Keychain-backend runs passed 100 fresh-process lifecycle cycles and four Goal closures. Audited 1/3/5-host resource trials include a retained five-host RSS failure. Static checks, typed contracts and process tests
have distinct scopes below; none certifies Chromium confinement.

## Primary evidence

[H18-primary-sources.json](../evidence/H18-primary-sources.json) records exact
SHA-256 hashes for the pinned CEF AppKit, OnPaint, sandbox and loader sources,
verified from source archive `ee99a7c1…72de0` at commit
`cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3`. It also records the three entitlement
plists fetched from Chromium **150.0.7871.252**, the matching runtime version.
Context7 `/chromiumembedded/cef` and current official documentation were consulted;
current guidance does not replace the pinned source/API checks.

The [pinned helper example](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/tests/shared/process_helper_mac.cc)
and [CEF sandbox setup](https://chromiumembedded.github.io/cef/sandbox_setup)
require initialization before loading the framework on macOS. The compiled helper
follows that order and returns failure if initialization fails. However, the
[pinned sandbox implementation](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef_dll/sandbox/sandbox_mac.mm)
can return a context when the launch did **not require** a sandbox. Consequently,
loader success alone never proves that a process has effective restrictions.
The requested process role and actual policy must also be observed.

[CEF signing guidance](https://chromiumembedded.github.io/cef/code_signing.html)
requires role-specific review for distribution. Matching Chromium renderer and
GPU plists contain `com.apple.security.cs.allow-jit`; its main application plist
includes device capabilities that this visual-only fixture intentionally does
not copy. Apple distinguishes [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
from resource sandboxing and documents the [JIT entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-jit)
as permission for MAP_JIT under that runtime. H18's local seals are ad-hoc,
without hardened runtime or entitlements. This records the development artifact;
it does not claim a release configuration or JIT acceptance.

## Per-surface matrix

| Surface | Implemented/read evidence | Runtime gate and required proof |
|---|---|---|
| Renderer | Sandbox loader before CEF, fail on initialization failure; no raw owner API | **BLOCKED:** observe role/policy and file/network denial under real renderer compromise probes |
| Browser process | Separate executable, minimal environment, fixed content inventory | **BLOCKED:** remains a privileged attack surface; no Apple App Sandbox or proved HOME/Keychain/egress boundary |
| GPU process | Matching role helper and framework; no accelerated paint retained | **BLOCKED:** observe sandbox, GPU resources and teardown; matching JIT entitlement is research only |
| Network/service processes | Generic/role helpers bundled; owned-tree resource samples include classified and generic helpers; page requests deny external inventory misses | **BLOCKED:** complete service-role/policy identification, DNS/background services and browser-mediated egress restrictions still require dedicated observation |
| Helpers | Generic, Alerts, GPU, Plugin, Renderer match SDK suffix list; local signatures verify | **PARTIAL:** actual role/process resource observations and cleanup exist for owned CEF trials; 100 fresh-process cycles close cleanly. Bundled roles are not proof every role ran or has effective sandbox/JIT restrictions |
| Filesystem | Broker descriptor-relative validation/no-follow; native fixture has immutable arrays; private output directory | Broker tests **PASS**; **BLOCKED** native direct-file access, browser privilege and process filesystem policy |
| Keychain | The real default Chromium path reached SecItemCopyMatching and blocked shutdown; no raw credential values were captured. New ephemeral profiles select official use-mock-keychain | **FAIL** default shutdown dependency; **BLOCKED** real Keychain isolation. Test backend avoidance is not OS denial |
| HTTP/HTTPS/external navigation | Exact inventory membership, initial main-frame URL only, redirect denial, no fallback | **PARTIAL** compiled policy; **BLOCKED** actual request/redirect/background egress observations |
| Localhost/LAN/link-local | All non-inventory schemes/URLs rejected in broker, including loopback cases | Broker tests **PASS**; **BLOCKED** native requests, DNS resolution and background network paths |
| WebSocket | CSP connect-src none, no network request resource fallback | **BLOCKED:** CEF network/WebSocket path denial and OS egress cannot be inferred from CSP |
| WebRTC | Devices denied and no connectivity capability granted | **BLOCKED:** ICE/STUN/data-channel paths need dedicated tests; no claim callbacks cover them |
| Downloads | CanDownload false and download cancellation | **PARTIAL** compile; **BLOCKED** observed no filesystem side effects |
| Popups / unmanaged windows | Popup callback denies; non-primary clients close immediately | **PARTIAL** compile; **BLOCKED** actual popup/new-window/task cleanup |
| Devices and permissions | Media callback cancels, permission prompt denies; no device entitlements or usage prompts added | **BLOCKED:** real API denials and absence of TCC prompts must be observed without changing permissions |
| Clipboard | No host clipboard bridge, CSP/permission policy, permission prompt denies | **BLOCKED:** browser read/write denial and activation paths untested |
| IPC | Existing typed Rust gate enforces size, sequence, generation, allowlists, rate/deadline | Contract tests **PASS**; native browser/process/frame/generation/URL dispatcher now compiled and pure-boundary tested; live fixed Goal transport **PASS** in its own run; no Production/MCP exposed to JS |
| Cookies/profiles | Fresh origin per generation, private root cache, new in-memory request context | **BLOCKED:** prove no reuse/persistence/service worker contamination; new context is not a sandbox |
| JIT | Matching renderer/GPU entitlement references recorded; no broad exceptions added | **PARTIAL:** original own JS visibly animated; no hardened release/JIT role acceptance; do not add unsigned-executable-memory/library-validation exceptions speculatively |
| CPU/RSS/deadline | External supervisor and bounded mailbox; [audited real 1/3/5-host CPU/RSS/footprint](../evidence/H18-owned-resource-summary.json) | Measurements **PASS audit / PARTIAL protocol**: 1 and 3 completed, 5 exceeded 2 GiB RSS and was cancelled with observed cleanup. Footprint measured where available; GPU null. Steady-state capacity and hostile exhaustion confinement remain unaccepted |
| Process crash/escape | PID+microsecond birth tracking; group isolation; finally cleans observed escaped child after exception; immediate frame revocation and deferred CEF close | [Controlled renderer exit](../evidence/H18-native-diagnostic-crash-posix/report.json) **PASS expected-error handling**: renderer 86, host 42, shutdown return and observed cleanup. Two earlier crash/classification failures retained. Memory corruption and malicious unobserved escape **BLOCKED**; polling is not confinement |
| Close/restart | Native final-close flow, Rust generations/revocation and fresh origin/root | **FAIL retained** default Keychain shutdown; **PASS** [100 fresh-process cycles](../evidence/H18-native-cycles-100/summary.json), four Goal closures and [cold process replacements](../evidence/H18-native-replacements/summary.json) for reload/viewport change. No in-process recreation/leak, hot reload, OS suspend/resume or dynamic in-place resize acceptance; no replay/reuse of revoked admission |
| Alpha/frame ownership | C++↔Rust copied callback bytes, one lease, bounded coalescing contracts and real delayed-consumer run | ABI/ownership, original smoke and fixed Goal native alpha **PASS**; [100 ms consumer delay](../evidence/H18-native-diagnostic-slow-consumer/report.json) observed 140 accepted paints /41 acquired /98 coalesced. No total-memory, libobs or leak-freedom inference |

No `no_sandbox=true`, private sandbox APIs, remote debugging, external browser
connection or global HTTP server is used. No third-party package was executed.
The supervisor cannot certify unobserved escaped children and must not be used to
justify accepting hostile HTML. Its error cleanup reports any still-observed
processes, including zombies, and retains structured failure state.

## Required next evidence

The owned-fixture exception has been granted. Real pixels, four Goal closures and
100 fresh-process lifecycles passed their explicit test-backend gates; the
five-host resource trial failed its RSS policy and remains a failure. Expansion
requires the same bounded supervision and separate assessment. Retain all
default-backend failures. There is no sandbox-disabled fallback. See
[the native report](h18-native-host.md).

Actual OS confinement of the browser process and every
relevant role remains a separate design/verification requirement. Then use
controlled malicious fixtures for each surface above, quotas and process escape,
long-lived lifecycle and contamination tests. Fixed owned Goal transport has its
own real evidence; third-party execution, libobs draw and Production integration
cannot be inferred from it. The resource audit measures available CPU/RSS/footprint
with sampling limits, not hostile exhaustion resistance, unique physical RAM or
GPU cost.

[Static, hidden/resumed, slow JS and controlled-exit diagnostics](h18-native-host.md#fixed-native-diagnostics)
have their own exact native artifacts and reports. The hidden window stopped OSR
after settling and resumed; this is not system suspend or profile-contamination
testing. Expected child-error recovery does not establish hostile renderer
containment. Every gate above retains that distinction.
