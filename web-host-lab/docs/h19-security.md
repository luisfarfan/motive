# H19 — Keychain and security boundaries

**Third-party HTML/JS and a production credential configuration remain BLOCKED.**
H19 keeps the real CEF sandbox enabled, a closed owned resource inventory, fresh
private roots, independent in-memory contexts, bounded typed IPC and external
supervision. None of those features alone confines the browser process. The
owned test build is explicitly marked `chromium-use-mock-keychain`; it is not a
candidate production credential backend.

This investigation is dated 2026-11-18, America/Lima. It did not query, enumerate,
read or change the owner's Keychain, certificates, browser profiles or global
permissions. H18's original Keychain failures remain unchanged. New static source
and signature inspection does not count as a new native trial.

## Exact source correspondence and reproducibility

Runtime: **CEF 150.0.19+gcf60f42 / Chromium 150.0.7871.252**, API 15000. CEF source
revision `cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3`; source archive SHA-256
`ee99a7c1cf8e5d24951f291c749461c0586dd430fd24d861ede0bc77df172de0`.
The [source index](../research/h19-source-index.json) records exact URL, version,
length and SHA-256 for the relevant Chromium files and ten CEF files verified
against that archive. Failed research lookups are recorded as errors and do not
count as verified source. Context7 was consulted for API discovery; conclusions
below use the pinned code, not current `master` documentation.

```sh
python3 web-host-lab/tools/h19_security_sources.py --fetch
python3 -m unittest discover -s web-host-lab/tests -p 'h19_security*_test.py' -v
```

The first command obtains missing pinned public source files into the ignored
research cache and verifies their hashes. Neither command loads Chromium or
calls any credential API. [Complete 29-file verification](../research/h19-source-verification-complete.json);
the [earlier 27-file verification](../research/h19-source-verification.json) is retained.

## Why an ephemeral browser can reach Keychain

The supported source-level chain is now precise:

1. `BrowserProcessImpl::PreMainMessageLoopRun` constructs `OSCryptAsync` and
   immediately calls `GetInstance` to initialize its providers. This happens at
   browser startup independently of a widget's cookie usage. The CEF
   `chrome_runtime.patch` retains this call.
   [Chromium browser startup](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/browser/browser_process_impl.cc),
   [matching CEF patch](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/patch/patches/chrome_runtime.patch).
2. On macOS the `kUseKeychainKeyProvider` feature is enabled by default. Its
   provider posts a `USER_BLOCKING` / `MayBlock` task. Unless the explicit test
   switch is present, `GetKeyTask` selects the real `KeychainV2` singleton.
   [Feature default](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/common/chrome_features.cc),
   [Keychain provider](https://github.com/chromium/chromium/blob/150.0.7871.252/components/os_crypt/async/browser/keychain_key_provider.mm).
3. `KeychainPassword::GetPassword` requests the unbranded service/account
   `Chromium Safe Storage` / `Chromium`. `FindGenericPassword` reaches
   `SecItemCopyMatching`. If no item exists, the password code can create a
   random password in Keychain; changing the cache directory does not change
   that service identity.
   [Password lookup/create](https://github.com/chromium/chromium/blob/150.0.7871.252/components/os_crypt/common/keychain_password_mac.mm),
   [Security framework call](https://github.com/chromium/chromium/blob/150.0.7871.252/crypto/apple/keychain_v2.mm).
4. Default task traits use `SKIP_ON_SHUTDOWN`. A task that already started still
   blocks thread-pool shutdown until it finishes. Destroying a callback or
   closing the last browser does not cancel an outstanding synchronous Security
   framework operation.
   [Task shutdown semantics](https://github.com/chromium/chromium/blob/150.0.7871.252/base/task/task_traits.h).

H18's retained sample actually observed `SecItemCopyMatching` and Security
framework decryption on a thread-pool worker after final browser close, while
`CefShutdown` did not return. The new code evidence explains a causal path
consistent with that observation. The stripped sample does **not** identify every
internal Chromium frame, so attribution of that exact historical worker to this
particular provider remains an inference, not a newly symbolicated stack.
[Original finding](../evidence/H18-native-keychain-finding.json).

The host's close ordering still matters independently: revoke admissions, close
browsers, wait for `OnBeforeClose`, drop browser/context references, finish the
consumer, then call `CefShutdown` on the main application thread with no later
CEF calls. The pinned API explicitly describes the shutdown-thread and reference
requirements. This prevents host lifetime errors; it cannot cancel a running
Keychain operation inside Chromium.
[CEF application lifecycle](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/include/cef_app.h),
[browser final-close contract](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/include/cef_life_span_handler.h).

## Evaluated configuration options

| Configuration | What it changes | Keychain / shutdown decision |
|---|---|---|
| Fresh `root_cache_path` | Keeps installation data and singleton bookkeeping in an owned private directory | Retain; does not change browser-global OSCrypt |
| Empty per-context `cache_path` | New off-the-record profile with in-memory profile storage | Retain; does not prevent eager provider startup |
| No persisted session cookies | No session-cookie persistence for these contexts | Retain; not a credential isolation boundary |
| Empty cookie schemes plus `cookieable_schemes_exclude_defaults=1`, global and per context | Official API disables cookie loading and saving | Implemented for H19; reduces unused surface, not a Keychain fix |
| `use-mock-keychain` | Uses `FakeKeychainV2` in the provider | Owned tests only; explicitly ineligible for production acceptance |
| Linux `password-store=basic` | Linux-specific provider selection | Not a macOS solution; not used |
| Disable the Keychain provider with internal feature flags | Changes encryption-provider selection | Not an accepted public production configuration; not used |
| A new service name from a later CEF API | Namespacing if supported by another version | Not present in pinned API; would still access Keychain, so not a fix |

The pinned [CEF settings](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/include/internal/cef_types.h)
document both the in-memory behavior and remaining installation-specific disk
data. [CEF context creation](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef/browser/chrome/chrome_browser_context.cc)
creates a unique off-the-record profile from a primary parent profile; it is not
a wholly absent browser profile system. The Chromium
[network-context implementation](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/browser/net/profile_network_context_service.cc)
skips disk cookie storage/encryption setup for in-memory storage. This does not
remove the earlier global provider initialization. Chromium's own
[switch declaration](https://github.com/chromium/chromium/blob/150.0.7871.252/components/os_crypt/common/os_crypt_switches.h)
labels the mock backend as testing support for avoiding blocking dialogs.

No official production option meeting the no-unnecessary-credential-access
requirement was demonstrated for this pinned runtime. A default-backend retry
would exercise the very credential path the owner prohibited. **Production
Keychain and production normal-shutdown acceptance stay BLOCKED.** Normal shutdown
with the explicit test backend has separate real native evidence; it does not
certify normal Keychain behavior.

## Native security experiment and classification

The fixed `security` scenario performs a native read-only
`open(ROOT/sandbox-decoy, O_RDONLY|O_NOFOLLOW|O_CLOEXEC)` in the browser and each
renderer. The supervisor creates the exact mode-0600 owned file in a private
directory. No content is returned or logged; file descriptors close immediately.
The path travels through the trusted native creation data, not a JavaScript API.
The report records instance/generation/browser ID, reported renderer PID,
observation/allowed flags and errno.

`tools/h19_security_check.py` requires the browser positive control to succeed,
every expected renderer to report `EPERM` or `EACCES`, exact identities and
complete observed-tree cleanup. `ENOENT`, a missing reply, stale generation,
duplicate identity or a crashed process cannot pass. Its result is specifically
**one owned file-open denial**, never general filesystem/HOME/Keychain isolation.
The file lies inside the host's private root: a browser positive control does
not, by itself, demonstrate access outside an eventual host container.

A supervisor-owned loopback listener can additionally observe whether the fixed
page probes establish a TCP connection. Zero accepted connections is an endpoint
observation; classifying CSP rejection separately requires the corresponding
native/page status. It cannot prove OS egress, DNS, WebRTC/UDP or all browser
services are blocked. Missing listener setup is not a zero-connection result.

Runtime evidence is published separately by the H19 runner, bound to its exact
artifact hash. The classifier tests use synthetic records and test classification
only; they are never substituted for native observations.

### Observed three-instance native result

The [v2 security run](../evidence/H19-v2-security-3/report.json), generation
**19100**, actually executed three owned 640×360 instances. Each browser-side
positive control opened the private decoy with errno 0. Renderer PIDs
**64610 / 64612 / 64614** each reported failure with **errno 1, `EPERM`**. The
independent supervisor's raw process samples corroborate each PID as an owned
renderer with one stable birth identity. All three native instances closed,
the host exited 0, and no observed owned PID remained after final cleanup.
[Raw native manifest](../evidence/H19-v2-security-3/instances.json),
[hashed scoped classification](../research/h19-security-result.json).
Its executable SHA-256 is
`a533ac23bd8f469d1a898119762fb25e1ec54ba5f7265cc6892ccc8e8e27d010`;
the configured native duration was 8 seconds, not a sustained performance trial.

All three pages reported phases **20, 22, 24, 26, 28**: fetch rejected, WebSocket
failed, popup returned null, the test cookie was unavailable, and worker creation
failed. The owned loopback listener was bound, accepted **zero** connections and
closed. **All native resource/navigation/popup/download/permission block counters
were zero.** Therefore this run does not establish callback-mediated denial.
The web observations are consistent with the configured CSP/API restrictions;
without a dedicated CSP violation record, their precise enforcement layer is
not asserted. In contrast, the renderer's native `open` is an OS syscall denial,
independent of CSP or a JavaScript request handler. No Keychain call was made by
the probe and the runtime still used its explicit test backend.

The first classifier invocation mistakenly supplied expected generation 9011;
it correctly rejected the actual 19100 identities. That
[classifier-input failure](../research/h19-security-result-wrong-generation.json)
is preserved. Correcting the expected generation and corroborating the retained
process rows produced the scoped PASS without rerunning or changing native
evidence. This is not a native security failure or a retroactive native PASS.

```sh
python3 web-host-lab/tools/h19_security_check.py \
  --instances web-host-lab/evidence/H19-v2-security-3/instances.json \
  --supervision web-host-lab/evidence/H19-v2-security-3/supervision.json.gz \
  --canary web-host-lab/evidence/H19-v2-security-3/report.json \
  --count 3 --generation 19100 \
  --output web-host-lab/research/h19-security-new-classification.json
```

### Final selected candidate confirmation

The selected `repro-r1` artifact
`8a76e3ce6409d911cf04bd4815c5c8065d13aa21a8c620cdf839f0d7b44c311b`
repeated the same fixed experiment with generation **139533708125**. All three
browser positive controls passed; all three owned renderers returned `EPERM`
and had independently corroborated PID/birth identities. The five web rejections
were observed again, callback block counters stayed zero, the owned listener
accepted zero connections and native cleanup passed. This confirms the same
narrow result for the selected artifact without expanding its security scope.
[Candidate classification](../evidence/H19-candidate-diagnostics/security-3/analysis.json),
[candidate run and artifact provenance](../evidence/H19-candidate-diagnostics/security-3/report.json).

## Required boundary matrix

| Surface | Implemented or scoped evidence | Remaining acceptance |
|---|---|---|
| Browser process | Separate host, private root, minimal environment, closed inventory; no App Sandbox entitlement in lab artifact | **BLOCKED:** supported OS confinement of filesystem/HOME, credentials, network and exposed services |
| Renderer | Official sandbox initialized before framework load; three real native decoy opens denied with EPERM | General policy, arbitrary filesystem, broker bypass and compromised-renderer containment remain **BLOCKED** |
| GPU | Matching dedicated helper, default CEF sandbox configuration, no shared callback surface retained | **BLOCKED:** role-specific denied-resource probes and release JIT/graphics acceptance |
| Network and utilities | CEF helpers and process-tree samples; exact page-resource allowlist | **BLOCKED:** identify each actual service, DNS/background egress, localhost/private-network and mediated-resource restrictions |
| Helpers | Five expected bundle roles; signature and architecture inventory | A role's name or successful sandbox loader is not effective OS-policy proof |
| Filesystem/HOME | Existing broker no-follow, hashes and immutable snapshots; own decoy probe | Broker validation and one denial do not establish browser-process or all-renderer filesystem confinement |
| Keychain | Exact startup source path; test backend explicitly separated | **BLOCKED:** appropriate production configuration and OS denial |
| HTTP, HTTPS, localhost, LAN | Closed inventory/CSP; own loopback fetch rejected, zero accepted connections; callbacks unexercised | **BLOCKED:** all request paths and browser services; no external hosts or private services are probed |
| WebSocket | Own WebSocket failed, listener saw zero accepted connections; CSP configured | OS network isolation and exact web enforcement attribution remain unproved |
| WebRTC/DNS | No device or networking capability deliberately granted | **NOT_EVALUATED / BLOCKED:** no claim that ordinary URL callbacks cover ICE/STUN/DNS |
| Clipboard/camera/microphone | No native API bridge; permission callbacks deny; no corresponding capabilities added | Dedicated denial/prompt observations **NOT_EVALUATED**; no device or clipboard content accessed |
| Downloads/popups | Explicit CEF denial callbacks; own popup returned null, callback count zero | Download/filesystem side-effects and native popup callback denial **NOT_EVALUATED** |
| Cookies/profiles | Cookie schemes disabled; three owned cookie writes remained unavailable; distinct off-the-record contexts/origins | Contamination/reuse, service-worker lifetime and all installation data still require runtime checks |
| Workers/service workers | Owned dedicated Worker rejected; CSP `worker-src 'none'`, no arbitrary registration | Service-worker lifecycle **NOT_EVALUATED**; no OS worker/service confinement claim |
| IPC | Existing typed Gate, CEF peer/frame/browser/generation checks; no Production/MCP/CLI bridge to JS | Identity tests and owned native Goal routing do not establish a malicious-process broker audit |
| JIT | Real owned JS execution; pinned entitlement research | Hardened Runtime and least-privilege entitlements on exact signed artifact **BLOCKED** |
| Crash/escape | Owned process watchdog, PID/birth identity, revocation and cleanup | Sampled cleanup is not prevention of unobserved process escape; memory-corruption containment **BLOCKED** |
| Resource exhaustion | Fixed 2048 MiB sampled emergency RSS boundary and external deadline | Not a kernel allocation cap; retain overshoot; adversarial abuse remains **BLOCKED** |

The [pinned sandbox implementation](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef_dll/sandbox/sandbox_mac.mm)
returns a valid context even when the helper arguments did not require a sandbox.
The helper correctly follows the [official initialization order](https://chromiumembedded.github.io/cef/sandbox_setup),
but successful initialization alone is insufficient evidence for any matrix row.
Sharing one CEF browser process also shares a security/failure domain. Distinct
`CefRequestContext` objects and origins do not supply OS isolation.

## Supported confinement direction for a later gate

A public macOS candidate is a separately sandboxed XPC service hosting the
browser, with an owner-side broker that supplies immutable bytes and bounded
visual commands through an authenticated capability. Apple documents XPC as a
privilege-separation mechanism; an ordinary child process does not provide the
same boundary. An XPC service needs a deliberately restricted container and
entitlements, with no camera/microphone, clipboard bridge, owner credential access
or general network capability. This is a candidate design, not a verified CEF
deployment. [Apple XPC services](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingXPCServices.html),
[sandbox inheritance](https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html).

CEF AppKit/message-loop requirements, Chromium helper bootstrap, JIT, IPC handles
and the interaction of App Sandbox with CEF's own sandbox must be demonstrated on
the exact bundle. Omitting `network.client` is a candidate restriction, including
localhost; granting it is broad and is not a hostname allowlist. A trusted broker
must not offer arbitrary URL/path access. Keychain access requires its own proof;
an App Sandbox entitlement by itself is not that proof.
[Apple network entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.network.client),
[App Sandbox](https://developer.apple.com/documentation/security/app-sandbox).

No private Seatbelt profile, `sandbox-exec`, sandbox-disabling switch or global
permission change was introduced. If the public-container candidate proves
incompatible, retain owned content only and investigate with upstream CEF before
altering security requirements. H20 may work on contracts and controlled owned
fixtures after handoff; this report cannot authorize third-party execution or
distribution of the test credential configuration.
