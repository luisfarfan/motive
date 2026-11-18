# H18 security checkpoint

**Third-party execution BLOCKED.** The compiled fixture has no package loader and
serves only Motive's three original embedded files. Native CEF execution has not
been authorized or performed. Static checks, typed contracts and process tests
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
| Helpers | Generic, Alerts, GPU, Plugin, Renderer match SDK suffix list; local signatures verify | **PARTIAL:** static packaging passes; role launch, sandbox, JIT, crash and zero remaining helpers unexecuted |
| Filesystem | Broker descriptor-relative validation/no-follow; native fixture has immutable arrays; private output directory | Broker tests **PASS**; **BLOCKED** native direct-file access, browser privilege and process filesystem policy |
| Keychain | No credentials, Keychain calls, secret payloads or personal profile in adapter | **BLOCKED:** absence of adapter API is not denial of OS access by Chromium/browser process |
| HTTP/HTTPS/external navigation | Exact inventory membership, initial main-frame URL only, redirect denial, no fallback | **PARTIAL** compiled policy; **BLOCKED** actual request/redirect/background egress observations |
| Localhost/LAN/link-local | All non-inventory schemes/URLs rejected in broker, including loopback cases | Broker tests **PASS**; **BLOCKED** native requests, DNS resolution and background network paths |
| WebSocket | CSP connect-src none, no network request resource fallback | **BLOCKED:** CEF network/WebSocket path denial and OS egress cannot be inferred from CSP |
| WebRTC | Devices denied and no connectivity capability granted | **BLOCKED:** ICE/STUN/data-channel paths need dedicated tests; no claim callbacks cover them |
| Downloads | CanDownload false and download cancellation | **PARTIAL** compile; **BLOCKED** observed no filesystem side effects |
| Popups / unmanaged windows | Popup callback denies; non-primary clients close immediately | **PARTIAL** compile; **BLOCKED** actual popup/new-window/task cleanup |
| Devices and permissions | Media callback cancels, permission prompt denies; no device entitlements or usage prompts added | **BLOCKED:** real API denials and absence of TCC prompts must be observed without changing permissions |
| Clipboard | No host clipboard bridge, CSP/permission policy, permission prompt denies | **BLOCKED:** browser read/write denial and activation paths untested |
| IPC | Existing typed Rust gate enforces size, sequence, generation, allowlists, rate/deadline | Contract tests **PASS**; native authenticated dispatcher and peer binding **PARTIAL**; no Production/MCP exposed to JS |
| Cookies/profiles | Fresh origin per generation, private root cache, new in-memory request context | **BLOCKED:** prove no reuse/persistence/service worker contamination; new context is not a sandbox |
| JIT | Matching renderer/GPU entitlement references recorded; no broad exceptions added | **NOT_EVALUATED:** no native JS or hardened release test; do not add unsigned-executable-memory/library-validation exceptions speculatively |
| CPU/RSS/deadline | External supervisor tests terminate owned Python trees; CEF callback mailbox bounded | Non-browser tests **PASS**; Chromium exhaustion/whole-tree cost **BLOCKED**; footprint/GPU null |
| Process crash/escape | PID+microsecond birth tracking; group isolation; finally cleans observed escaped child after exception | Owned fixture tests **PASS**; malicious unobserved escape and CEF helpers **BLOCKED**; polling is not confinement |
| Close/restart | Native final-close flow compiled, Rust generations/revocation tested; fresh origin/root required | **PARTIAL:** no live native final-close/100 cycles; no replay, no reuse of revoked admission |
| Alpha/frame ownership | C++↔Rust copied callback bytes, one lease, bounded coalescing tested without CEF | ABI/ownership **PASS**; actual OnPaint, premultiplication and libobs **BLOCKED** |

No `no_sandbox=true`, private sandbox APIs, remote debugging, external browser
connection or global HTTP server is used. No third-party package was executed.
The supervisor cannot certify unobserved escaped children and must not be used to
justify accepting hostile HTML. Its error cleanup reports any still-observed
processes, including zombies, and retains structured failure state.

## Required next evidence

First, obtain the narrow owned-fixture exception described in
[h18-native-host.md](h18-native-host.md). On that exact hash observe one native
launch, first/latest decoded BGRA and alpha patches, counter changes, orderly
close and all helper identities disappearing. Any failed startup/policy check
stays a failure; no sandbox-disabled fallback.

After this smoke test, actual OS confinement of the browser process and every
relevant role remains a separate design/verification requirement. Then use
controlled malicious fixtures for each surface above, quotas and process escape,
repeated lifecycle and contamination tests. Third-party imports, native Goal
Celebration and Production integration cannot be inferred from any earlier pass.
