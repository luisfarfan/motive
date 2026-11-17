# H8 — Deferred RTMP cancellation and macOS Keychain

Development verification on the same Apple Silicon Mac as H7, 2026-11-16.
This increment keeps one Production/libobs engine, project v3, profile v1,
fixed canvas dimensions/30 FPS, VideoToolbox/x264 policy and the existing GPUI
files. No public destination, public stream, global trust change or release.
**Trusted RTMPS media delivery remains pending**, for the reason below.

## Connection lifecycle and the upstream boundary

H7 retained a real `_pthread_join` crash from an experimental force-stop worker
and a five-second control timeout from stopping on the main thread. Those
failures remain in ignored `var/evidence/h7-pilot/`; H8 does not repeat that
unsafe experiment. No ad hoc stop thread or `obs_output_force_stop` remains in
Motive's bridge.

In OBS 33.0.1, `init_send` emits the public start signal before `connect_thread`
clears its private `connecting` flag. Failure emits stop before that thread's
last log/detach/store. A stop/destroy can join the same thread that detaches
itself. The send worker also emits stop before its final resource accesses.
Consequently, a start/stop signal, `obs_output_active`, connection time or an
arbitrary sleep is not a worker-completion barrier.

The official release API still reported 33.0.1 as latest (published October 29).
Master `e8a9a13bfc9da18391e873efc71522dbdc47be06` retained these lifecycle paths.
Search found historical thread fixes, but no later verified fix for this case.
Release/master evidence is in `var/evidence/h8-upstream/`.

A narrow downstream patch is therefore included at
`native/patches/obs-33.0.1-rtmp-lifecycle.patch`:

- Connection/send workers remain joinable and are reaped exactly once, instead
  of racing joins against self-detachment.
- Final atomic stores follow the last worker accesses, including early
  connection failures and thread-creation failure.
- A public libobs procedure-handler extension, `get_thread_state`, reports
  `connecting` and `workers_active`. It reaps only after the final stores; it
  never joins a pending network handshake. Its caller must serialize control
  and must not call it from output callbacks.
- Motive polls that procedure on its existing owner thread. Missing support
  fails closed. It requires both plugin workers and libobs capture to finish
  before exposing idle/error as quiescent or allowing resource replacement.

`build.rs` invokes `scripts/build_obs_outputs.py`. It builds the official output
module with this patch, not a new RTMP implementation. The official source and
OBS dependency archive checksums are pinned; the original source/OBS.app remain
unchanged. Build dependencies live under `.deps/` and the module under
`target/obs-outputs-h8/obs-outputs.so`. There is no global install. All transport,
codec, TLS and certificate-loading code remains unchanged. This is **not an
upstream-accepted fix**, and only the macOS ARM64/no-auto-reconnect configuration
has been exercised. Re-evaluate/remove the patch when upstream provides a
suitable lifecycle API/fix.

### Shared CLI/MCP behavior

| Operation/state | Meaning |
|---|---|
| `stop_output` while connecting | Existing `OUTPUT_CONNECTING` guard remains; no unsafe immediate stop |
| `cancel_output` | Idempotent request to stop; returns promptly through the shared core |
| `cancel_pending` | Handshake is still running; cancellation is queued, not completed |
| `stopping` | Handshake worker finished; native graceful stop/drain is pending |
| `idle` / `error`, `output_lifecycle.native_busy=false` | Plugin workers reaped and libobs capture inactive; metrics/resources may be retained until reset/new output |
| `request_shutdown` | Development operation: request cancellation and exit only after quiescence; other mutations are rejected meanwhile |
| `shutdown` | Existing immediate shutdown still requires quiescence |
| `recover_output` | Acknowledge a completed failure; never starts another connection |

Status also includes `cancel_requested`, `cancel_deferred` and
`shutdown_pending`. Repeated cancellation does not start another worker. Source
failure uses the same deferred path. The UI close guard remains unchanged.
MCP cancellation/shutdown annotations are destructive; deferred shutdown stays
in the development category. No secret-management mutations are MCP tools.

An entirely silent receiver hit the real approximately 30-second OBS receive
timeout. A receiver that continually makes partial progress may take longer;
there is no new overall handshake deadline or immediate cancellation claim.
MCP stays available during that wait. Reaping can wait for a worker's final
return/scheduler dispatch, but does not wait for network IO. This is not a formal
wait-free API or an exhaustive proof over all OS/plugin schedules.

Normal shutdown is guarded. If the native owner is unexpectedly dropped with an
active output, the bridge retains its memory until process exit rather than
force-stopping and freeing memory still referenced by workers.

## RTMPS trust: positive test blocked, validation retained

OBS 33.0.1's macOS `RTMP_TLS_LoadCerts` calls
`SecTrustCopyAnchorCertificates`, copies those anchors into mbedTLS and sets that
chain on its TLS configuration. It provides no per-output CA file, CA directory,
`SecTrustRef`, environment override or custom test-root argument. The plugin
sets the hostname from the URL and requires certificate verification.

A temporary test keychain or a Python/openssl CA context is not an input to that
code path. `SecTrustSetAnchorCertificates` would affect a separately created
trust object, not this plugin. A development CA could be trusted by a controlled
Python client, as in the existing fixture, but that is **not** evidence of Motive
accepting trusted RTMPS. We did not patch TLS, change the system/user trust
settings, disable hostname checks, introduce a TLS-terminating proxy to bypass
libobs verification, or expose a receiver to the Internet.

The real local rejection test and the credentialed rejection both retain
`OUTPUT_CONNECT_FAILED`, zero output bytes, explicit recovery and TLS
`unknown_ca` at the controlled receiver. No stream key is sent before TLS
succeeds. Positive RTMPS audio/video decode, isolated hostname/expiry rejection
with an otherwise trusted chain, and recovery following a successful RTMPS
stream remain **unverified**. The user has no prepared public-trust certificate
or hostname. A publicly trusted controlled destination is needed for that next
verification; owning a domain is not a runtime requirement for Motive.

## Keychain, enrollment and the security boundary

Secrets are persisted only in macOS Keychain generic-password items under the
application-specific service. Project v3, output profiles and runtime status
carry no secret values. The current implementation uses official macOS
`SecItemAdd`, `SecItemCopyMatching`, `SecItemUpdate`, `SecItemDelete` and the login
Keychain's code-signing ACLs (`SecAccess`/`SecTrustedApplication`). These ACL APIs
are legacy/deprecated but available and tested on this macOS; this is not a
claim of Data Protection Keychain entitlements or iCloud support. Synchronization
is disabled.

The bundle contains a separate signed **local enrollment helper**, which has no
production engine and no export operation:

```sh
./target/Motive.app/Contents/MacOS/motive-credentials create 19472
./target/Motive.app/Contents/MacOS/motive-credentials status 'OPAQUE_REFERENCE'
./target/Motive.app/Contents/MacOS/motive-credentials replace 'OPAQUE_REFERENCE' 19472
./target/Motive.app/Contents/MacOS/motive-credentials delete 'OPAQUE_REFERENCE'
```

Create/replace prompt on the controlling terminal with echo disabled. They do
not accept secret argv, environment variables, files or piped stdin. Delete
requires typing `DELETE` locally. Only a generated `kc_` + UUID reference and a
result code are returned (0 success, 1 missing, 2 denied, 3 Keychain unavailable,
4 invalid input, 5 binding mismatch, 6 signing identity required). Keys are limited to 1–512 ASCII letters, digits,
underscore, dot or hyphen in this increment. Enrollment requires the main app
and helper to have their expected identifiers and the same nonempty signing
team; ad hoc enrollment is rejected. Bundle with the already-authorized local
development identity before using the helper.

The ACL trusts the designated requirements of the signed helper and main
executable. Queries on the production thread disable Keychain authorization UI;
missing/locked/denied credentials return structured errors instead of opening a
modal prompt and blocking MCP. The fixture verifies changed-signature denial
and continued access from an unchanged signed copy. It does not claim that
certificate renewal/team migration has been tested. Never broaden an ACL or
silently copy secrets to get around a new signing identity; re-enroll locally.

Each item is bound to an RTMPS loopback port in Keychain metadata. MCP exposes
`credential_status {credential_ref}` and
`select_stream_credential {credential_ref: string|null}`. Selection requires a
matching configured RTMPS endpoint and access to the item. Changing endpoint
clears the selection. Plain RTMP rejects credential selection. Preflight and
native service creation recheck the item/binding; deletion/rebinding therefore
prevents a subsequent connection. No query returns value, length, Keychain
attributes or a list of secrets. Queries cannot register, replace or delete
items. References are runtime-only, outside both persisted formats.

The native service resolves the key only when needed. Plaintext necessarily
exists transiently in native/libobs memory to authenticate, but is never placed
in serializable service settings or Rust/MCP state. The helper's input buffer
and service-owned copy are cleared after use. We do not claim every allocation
inside system APIs/libobs is zeroized. Deleting a Keychain item does not revoke
an already authenticated server session: stop that output explicitly before
rotation/deletion; new attempts recheck Keychain.

Free-form OBS logs can contain a server's reply, so once a credential is used,
Motive suppresses those logs for the rest of that process. Structured codes,
state and metrics continue, and `encoding.native_logs_suppressed` makes this
tradeoff visible. This avoids keeping a secret redaction cache or assuming that
all plugin/server messages are safe. Reopening restores normal logging until
another credential is used.

This protects the CLI/MCP contract and normal signed-app Keychain access. The
Unix socket is still a same-user control boundary, not a sandbox against an
attacker controlling the account, executable, debugger or OS. No real service
credentials were used; test items are random dummy values and are deleted in
cleanup. No public service has been enabled.

## Reproduction and evidence

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
# Bundle with your existing local signing identity, then open Motive idle.
python3 scripts/verify_connect_stop.py
python3 scripts/verify_h8_lifecycle.py
python3 scripts/verify_h8_keychain.py
python3 scripts/verify_rtmp.py
python3 scripts/verify_rtmps.py
python3 scripts/verify_vt_stop.py
python3 scripts/verify_profiles_restart.py
```

The lifecycle test uses actual TCP sockets, libobs and an FFmpeg RTMP receiver
behind a controlled delay. The Keychain test uses a PTY, real signed binaries,
real Security APIs and a locally generated untrusted TLS fixture. Neither mocks
the engine nor uses public traffic. All existing test suites remain. H8 corrects one phase-sensitive motion
check in their shared media helper, retaining its pixel thresholds and recording
the original two-frame observation alongside the additional samples. Captures, TLS fixture private keys, device IDs, full operation logs
and manifests remain in ignored `var/`.

### Retained failures and corrections

- The first plugin-load attempt used an extensionless file outside a `.plugin`
  bundle; libobs appended `.so` and correctly rejected startup. The build/loader
  now agree on the `.so` path. Startup failure was not a native crash.
- A test launched immediately after `open` returned, before the reopened core's
  socket existed. The new lifecycle test now waits for a real status response
  before handing off. The original regression script was retained unchanged.
- One x264 clip failed the old overlay check because its 0.5/1.5-second samples
  almost coincided: 168 changed channels, below the 300 threshold. Samples of
  the **same decoded clip** at 0.8, 1.1 and 1.9 seconds gave 1,248, 1,248 and
  2,400 changed channels. The shared helper now samples all four times, retains
  the 1.5-second observation and the existing >500 mint-pixel/>300-motion
  thresholds. A frozen overlay still fails. No encoder/animation change was
  made to accommodate the test.

These reports, the failed clip reference and build failure logs are retained in
`var/evidence/h8-pilot/` and `var/evidence/h8-upstream/`. Earlier baseline reports
are copied into `var/evidence/h8-baseline/` where available.

### Measured RTMP and lifecycle run

Same owned pattern, animated overlay, tone, 960×540/30, 1,800-kbps CBR profile
and one Motive process for the following recording/RTMP pair:

| Case | Decoded duration / frames | CPU median | RSS median | Stop to quiescent |
|---|---|---|---|---|
| VideoToolbox MKV | 8.166 s / 243 | 42.40% | 179.30 MiB | 0.341 s |
| Local RTMP → FFmpeg FLV | 20.799 s / 622 | 43.74% | 185.66 MiB | 0.338 s |
| RTMP after receiver-loss recovery | 4.232 s / 124 | Not sampled | Not sampled | 0.311 s |

All three decode H.264/AAC, with audible test tone and observed overlay motion.
Rendered-lag, video-skipped and output-drop counters were zero in this run;
preview busy-copy drops reached three (a separate counter). Container/encoder
frame counts differ at finalization. The recording retained two approximately
67-ms tail intervals and the recovered RTMP clip one; the longer RTMP clip had
none. These results do **not** establish that the inherited timestamp-tail
limitation has been fixed. Default reordering/quality policy is unchanged.

Twelve silent-peer close/recovery cycles plus a real native timeout and delayed
successful handshake passed. Six repeated cancellation requests per cycle had a
maximum measured acknowledgment of 41.1 ms. The silent-peer timeout completed
in 29.821 s after cancellation, with pending-state CPU median 41.96% and RSS
174.35 MiB. The three-second relay-delay case connected and finalized in 3.085 s
after the cancel requests. Explicit deferred shutdown exited and reopening
produced a new responsive PID. No new Motive crash report was observed; the
previous H7 crash remains separately preserved.

CPU uses interval process CPU time and RSS from `ps`. It includes Motive's debug
UI/preview and excludes FFmpeg receiver, mux helper and OS media services. These
are short operational measurements, not comparative efficiency claims or a
long-running memory/CPU benchmark.

### Regression results

| Check | Final observed result |
|---|---|
| Unit/static checks | 15 unit tests pass (all 14 previous tests retained); Clippy with `-D warnings`, rustfmt and diff whitespace checks pass |
| Keychain | Register, replace/rebind, missing/revoked item, unchanged signed copy and changed-signature denial pass; fresh-process log suppression verified; no dummy key in responses/project/profile/runtime logs |
| Existing handshake guard | `OUTPUT_CONNECTING` returns promptly; receiver close permits explicit recovery |
| Profiles/MCP | Explicit profile-v1 save/restart/load, scene-v3 preservation, strict fields, shared PID/revision and agent disconnect pass |
| VT/x264 reordering | Eight decoded clips pass; no interior gap ≥50 ms; reordering disabled yields no B-frames; default policy unchanged |
| Existing window/portrait/UDP | 65.966 s / 1,977 frames; portrait 4.100 s / 122; UDP 5.021 s / 150, with audio and overlay |
| Physical H1 | External window loss/recovery and audio/video recovery-latch separation pass; camera + microphone 8.533 s / 255 frames |
| Scene Graph | Window + webcam + overlay 16.033 s / 481 frames; MCP properties, order/visibility, save/close/open and restored 3.133 s / 92 frames pass |
| Mux recovery | Terminating only Motive's mux helper latches failure; three subsequent recordings decode after explicit recovery |
| Encoder regression | Real x264 fallback with VT module disabled, restored hardware selection and two 15-second comparison clips pass |

H8's RTMP-pair RSS is higher than H7's recorded approximately 100/98 MiB.
Those are not controlled before/after samples: H8's pair starts approximately
three seconds into the process versus approximately 201 seconds in the H7
recording. We have not isolated the reason and claim no memory improvement.
The repeated-handshake run stayed near 174 MiB at its first and last sampled
pending phases (174.19 versus 174.35 MiB); this is bounded evidence, not a
long-session leak guarantee.

`var/evidence/h8-verification-manifest.json` hashes the tested executable, helper,
patched module, relevant code, fourteen successful media/control reports and
retained H8 failed cases. `h8-regressions.json` retains both failed attempts and
successful reruns. All captures and reports are local. The app is left reopened
and idle, using owned pattern/overlay only, no microphone/camera, no endpoint,
no selected credential and no recovery latch. No GPUI/design file was changed
by this work; concurrent design/AGENTS changes are outside H8.

### Following increment

First review the small downstream lifecycle patch against any new upstream
fix. Add an explicitly authorized destination registry separate from scenes and
quality profiles: canonical RTMPS hostname/port/application, no userinfo/query
secrets, and local approval binding each Keychain reference to that destination.
MCP should select an already approved destination, not create arbitrary egress
or redirect a credential to another host.

Then obtain an authorized controlled endpoint with a publicly trusted
certificate and correct hostname. It can be a provider's hostname; Motive does
not need its own domain. Verify the chain/hostname rejection cases, a brief
private test-pattern/tone RTMPS transmission, decoded receiver media, receiver
loss, explicit recovery and stop before trying a real private service stream.
No external output is enabled by this H8 increment. Positive RTMPS delivery is a
prerequisite, not an inferred capability.

Remaining limits: a single Mac/development build, no hour-long soak, no new
USB hot-unplug or sleep/wake coverage, no simultaneous outputs/canvases,
no configurable resolution/FPS, no OS account-compromise protection, and no
notarized portable bundle. Current Keychain tests exercise absence, item
revocation and changed identity; they do not lock the user's whole login
keychain or modify global security settings to manufacture denial.

### Primary sources

- [Pinned RTMP lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/rtmp-stream.c)
  and [current master inspected](https://github.com/obsproject/obs-studio/blob/e8a9a13bfc9da18391e873efc71522dbdc47be06/plugins/obs-outputs/rtmp-stream.c).
- [libobs output lifecycle](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c)
  and [public procedure/output APIs](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h).
- [Unmodified TLS trust and hostname handling](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/librtmp/rtmp.c).
- [Apple Keychain items](https://developer.apple.com/documentation/security/keychain-items),
  [SecItemCopyMatching](https://developer.apple.com/documentation/security/secitemcopymatching(_:_:)),
  [SecAccessCreate](https://developer.apple.com/documentation/security/secaccesscreate(_:_:_:)).
