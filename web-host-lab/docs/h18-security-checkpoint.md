# H18 security checkpoint

**Third-party execution BLOCKED.** The compiled fixture has no package loader and
serves only a fixed Motive-owned inventory (smoke or reviewed Goal profile). The owner authorized local fixture execution; original smoke produced real frames but stalled during shutdown in a Chromium Keychain task. The subsequent explicit test-Keychain-backend smoke passed orderly close and observed cleanup. Static checks, typed contracts and process tests
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
| Network/service processes | Generic/role helpers bundled; page requests deny external inventory misses | **BLOCKED:** actual process roles, DNS/background services and browser-mediated networking need observation |
| Helpers | Generic, Alerts, GPU, Plugin, Renderer match SDK suffix list; local signatures verify | **PARTIAL:** static packaging passes; actual helpers launched and supervisor observed-tree cleanup passed after deadline; effective sandbox/JIT/crash acceptance remains unverified |
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
| IPC | Existing typed Rust gate enforces size, sequence, generation, allowlists, rate/deadline | Contract tests **PASS**; native browser/process/frame/generation/URL dispatcher now compiled and pure-boundary tested; live transport **NOT_EVALUATED**; no Production/MCP exposed to JS |
| Cookies/profiles | Fresh origin per generation, private root cache, new in-memory request context | **BLOCKED:** prove no reuse/persistence/service worker contamination; new context is not a sandbox |
| JIT | Matching renderer/GPU entitlement references recorded; no broad exceptions added | **PARTIAL:** original own JS visibly animated; no hardened release/JIT role acceptance; do not add unsigned-executable-memory/library-validation exceptions speculatively |
| CPU/RSS/deadline | External supervisor tests terminate owned Python trees; CEF callback mailbox bounded | Non-browser tests **PASS**; Chromium exhaustion/whole-tree cost **BLOCKED**; footprint/GPU null |
| Process crash/escape | PID+microsecond birth tracking; group isolation; finally cleans observed escaped child after exception | Owned fixture tests **PASS**; observed CEF helper cleanup after deadline **PASS**; malicious unobserved escape **BLOCKED**; polling is not confinement |
| Close/restart | Native final-close flow compiled, Rust generations/revocation tested; fresh origin/root required | **FAIL** default Chromium Keychain shutdown; **PASS** one ephemeral test-backend close/cleanup; repeated cycles remain separate evidence; no replay/reuse of revoked admission |
| Alpha/frame ownership | C++↔Rust copied callback bytes, one lease, bounded coalescing tested without CEF | ABI/ownership **PASS**; actual OnPaint and original half-alpha smoke **PASS**; Goal native pixels and libobs remain separate gates |

No `no_sandbox=true`, private sandbox APIs, remote debugging, external browser
connection or global HTTP server is used. No third-party package was executed.
The supervisor cannot certify unobserved escaped children and must not be used to
justify accepting hostile HTML. Its error cleanup reports any still-observed
processes, including zombies, and retains structured failure state.

## Required next evidence

The owned-fixture exception has been granted and native pixels observed. The explicit ephemeral test-Keychain backend passed shutdown_return/exit0 and observed cleanup. Expansion requires retaining the same bounded supervision and evaluating each result separately. Retain all default-backend failures. Every failed startup/policy check stays a failure; there is no sandbox-disabled fallback. See [the native report](h18-native-host.md).

After this smoke test, actual OS confinement of the browser process and every
relevant role remains a separate design/verification requirement. Then use
controlled malicious fixtures for each surface above, quotas and process escape,
repeated lifecycle and contamination tests. Third-party imports, native Goal transport/draw and Production integration cannot be inferred from any earlier pass.
