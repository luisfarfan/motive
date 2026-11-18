# Security boundaries and stop gates

**Third-party execution BLOCKED.** A manifest, CSP, denied JavaScript methods or
a process named Helper is not a sandbox. This laboratory does not certify CEF
process restrictions, egress denial, HOME/Keychain isolation or resource ceilings.

Threat model: package controls all HTML/CSS/JS, can lie about readiness, flood IPC,
allocate memory, loop forever, navigate, use workers/WebSocket/WebRTC, guess assets
and exploit Chromium. The trusted native manager imports bytes, chooses policies
and authorizes only visual projections. Other same-user native processes and a
compromised OS are outside the package model, but are not protected by a Unix file
mode alone. The host/browser process is an additional privileged attack surface.

| Boundary | Implementation/evidence in H16 | Required before third-party use |
|---|---|---|
| Import inventory | Immutable byte snapshot, hashes, strict paths, no-follow opens and limits; tests | Connect to official importer and descriptor capability |
| Message authority | Typed visual messages, identity/generation/sequence/size/rate/deadline; tests | Bind channels to OS peer/launch identity, CEF sender/main frame and manager ownership |
| Requests/navigation | Native fixture callback denial and exact managed resource responses, compile-only | HTTP/HTTPS/file/data/blob/redirect/WebSocket/WebRTC/worker/background egress probes |
| Permissions | Native fixture denies devices/prompts/popups/downloads/dialogs | Observe denial and no TCC prompts on exact signed binary |
| CEF sandbox | Official scoped sandbox loader prepared, no no_sandbox escape | Verify actual renderer/GPU/network restrictions, failure is fatal |
| Browser-process OS boundary | Design only | Supported Apple confinement compatible with CEF/JIT/helpers; prove no HOME/Keychain/arbitrary FS, credentials or egress |
| Resource exhaustion | Bounded own queues and buffers; watchdog state tested | External process watchdog/kill, tree RSS/footprint limits, restart containment |
| Native timing/cleanup | Contract generations and final-close states | Real crash, 100 close cycles, helper reaping, descriptor/texture cleanup |

CEF M138+ macOS: dynamically load framework's libcef_sandbox.dylib through
CefScopedSandboxContext at helper entry **before** LoadInHelper; keep context
alive until process exit. Fail initialization, never retry without sandbox.
This uses Chromium's supported sandbox, not a homemade sandbox-exec/Seatbelt
profile. CEF's default restrictions are role-specific and permit legitimate
browser-mediated resources. A signed hardened runtime is not Apple App Sandbox;
App Sandbox compatibility for this host remains an independent research/runtime gate.

Asset requests use exact canonical URL membership of a per-instance immutable map,
not a regex firewall. Import never supplies filesystem paths to a renderer. No
network resource fallback when handler lookup fails; cancel all other schemes
and origins, initial navigation only, redirects/popups/downloads denied. CSP and
Permissions-Policy are defense in depth. CEF callbacks do not prove coverage of
DNS prefetch, browser services, WebSocket/WebRTC or compromised native processes.
Therefore an offline fixture is not sufficient evidence for egress confinement.

No shell/Production/MCP/device/clipboard API is registered. Renderer replies carry
only finite status values; discard diagnostic strings that might include paths,
URLs or secrets. No inherited sockets, credentials, profile migration or global
command-line passthrough. OS permissions must not be relaxed to get a passing run.

Native exception requested only after a reviewable fixture exists. Until then,
authorized tests exercise contracts and local byte brokers without a browser.
The eventual authorization would permit the owned fixture only, not third-party
packages or a change to global macOS policy.
