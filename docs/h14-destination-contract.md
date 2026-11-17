# H14 — approved RTMPS destinations and local start authority

Status: **domain, native bridge, owner, GPUI and approved RTMPS service
integrated; external acceptance remains PARTIAL**. The initial domain/bridge
tests did not contact a destination, create a Keychain entry or open a sheet.
Those test limits describe that initial increment, not the later B2 run.

The [authorized private B2 RTMPS trial](h14-rtmps-b2-verification.md) subsequently
ran for **104.837 active seconds** with local GPUI start confirmation. The user
observed the controlled video and audio in YouTube Studio; the simultaneous
local MKV was independently decoded. The provider copy was not independently
downloaded or decoded, and output-tail accounting remains partial. B3 has not
repeated this external trial, so B2 evidence does not certify B3 delivery.
The earlier [H8 trust limitation](h8-streaming-verification.md) remains the
historical result for H8, with the later B2 evidence scoped separately here.

## GPUI integration

The native studio now has a **Destinos RTMPS** panel, accessible from the globe
button and from **Salidas → Configurar destinos RTMPS**. The integrated B2 flow
has separate [secure-entry verification](h14-secure-paste.md#b2-user-verification)
and [private streaming evidence](h14-rtmps-b2-verification.md). The user confirmed
successful paste/save, and the owner observed association with a durable
receipt. The native routing test and visible **Pegar** workflow do not establish
a separate physical Cmd+V result; that keyboard-path check remains unverified.
The domain checks below alone do not certify the visual flow.

The five ordinary GPUI inputs are stable ID, display name, host, port and
application path. They never accept a credential value or editable opaque
reference. A draft captures the production revision. Saving a stale draft is
rejected; Edit rereads the current owner metadata before creating a new draft.
Saving returns a `LocalDestinationReview` that the confirmation consumes through
`Rc<RefCell<Option<LocalDestinationReview>>>`; cancellation leaves a draft.
Changing the credential binding tuple clears the draft's old reference without
deleting its Keychain entry. A name-only edit preserves the existing binding.

**Asociar clave** obtains the exact current GPUI window's AppKit NSView via
`raw_window_handle::HasWindowHandle`, then calls
`begin_destination_credential_local`. Only the AppKit sheet accepts the key.
The panel displays `awaiting_user`, `writing`, terminal failure/cancellation,
attached success or explicit reconciliation with its opaque reference. It does
not turn `stored_after_cancel` into a successful association or silently delete
the stored entry.

The streaming button checks the current owner's selected mode when clicked.
An approved external selection calls `prepare_destination_start_local`, displays
the complete bound destination and profile, and consumes a
`Rc<RefCell<Option<LocalStartRequest>>>` only on affirmative confirmation. The
profile's shared reordering warnings appear in that same dialog. It then calls
`start_destination_local` directly; no `Command` or `origin:"UI"` is used as
external authority. Selection, local approval, credential enrollment and start
remain separate actions. Stop, cancellation and recovery keep the existing
shared output operations; recovery never implicitly approves another start.

The panel reports preflight as configuration/Keychain readiness, explicitly
without network or delivery validation. It blocks editing while streaming,
credential enrollment or shutdown is active, and the core revalidates each
action. Buttons and fields expose Spanish accessibility labels. No screenshot,
VoiceOver, Keychain enrollment or external streaming success is inferred from
the implementation alone.

## Separate approved-destination registry

`src/destinations.rs` is designed as a sibling of `core::output`; it reuses the
real `OutputProfile` and H8 opaque-reference validator. It is not a new public
`Command` parser. `DestinationStore` v1 is separate from project v1–v5, mixer and
output-profile stores. It permits at most sixteen destinations and 128 KiB.

Each record contains a stable 1–48-character lowercase ASCII ID, a visible name,
`protocol: "rtmps"`, canonical host, port, literal application path, optional
`kc_UUID` reference and `draft`/`approved` local-review state. No stream key,
query, custom CA, TLS override, URL, automatic reconnect or selected output is
serialized. Unknown fields and versions fail. Different approved accounts may
use the same server/application with distinct IDs and credential bindings.

Host policy:

- ASCII DNS labels, maximum 63 bytes each and 253 overall, normalized to lowercase.
  Unicode host input is rejected; IDNA conversion is not silently performed.
- DNS names require at least two labels, except explicit `localhost` for a
  controlled receiver. Empty labels, trailing dot, underscores and leading or
  trailing label hyphens are rejected.
- IPv4 uses Rust's strict address parser and canonical representation.
  Unspecified, multicast and all-ones broadcast addresses are rejected. Private
  unicast and loopback can be explicitly approved. Literal IPv6 is rejected with
  `DESTINATION_IPV6_UNSUPPORTED` in this beta: OBS 33.0.1's librtmp preserves URL
  brackets in the hostname passed to mbedTLS, while its IP SAN verifier expects
  the unbracketed address. DNS destinations resolving to IPv6 remain supported.
  This restriction does not change TLS verification or the system trust store.
- Legacy numeric, abbreviated, octal or hexadecimal IP spellings are rejected.
  Userinfo, whitespace, URL schemes, queries, fragments, escapes and separators
  cannot enter the hostname.

Ports are 1–65535, allowing ordinary RTMPS 443. The application is an explicit
absolute path of one to eight nonempty ASCII segments, 64 bytes per segment and
256 bytes total. Only alphanumerics and `-_.` are allowed within segments.
`.`/`..`, trailing slash, empty segments, percent escapes, query, fragment,
backslash and credentials in URL syntax are rejected. This initial policy may
reject a provider requiring richer application syntax; it must not be bypassed
by accepting arbitrary URLs. The key belongs in native secure entry.

## Local review, selection and validation

The domain's mutation methods are `pub(super)`, intended only for owner methods
invoked by native UI. Do not expose them as CLI/MCP/Show Control commands.

1. `upsert_local(spec)` validates a candidate copy and leaves it **draft**.
   Editing an approved destination clears its selection and validation.
2. `review_local(id)` returns a non-cloneable `LocalDestinationReview` containing
   exactly the metadata shown to the user.
3. Affirmative local confirmation consumes that review via `approve_local`.
   A registry edit in between rejects the stale review.
4. `select_approved(id)` accepts only an existing approved ID. This operation,
   listing and preflight can be exposed through the shared control API.
5. `preflight(id, CredentialCheck)` receives a fresh native Keychain access and
   exact-binding result from the owner, never from the client. It reports
   `tls_required: true`, `network_tested: false`; configuration readiness is not
   proof of TLS, an accepted key or delivered audio/video.

Validation states are `unchecked`, `configuration_ready`, `credential_missing`,
`credential_access_denied`, `credential_binding_mismatch` and
`keychain_unavailable`. Runtime selection and validation are not persisted.
Reopening a store selects nothing and starts nothing, even when the local
approval records remain approved.

The destination file is a local configuration trust boundary, not a signed
authorization certificate. Someone able to replace the private store is already
inside the local user's configuration boundary. MCP/Creator Packs must never
receive a file-writing or raw-document-load route to it.

## One-use local streaming approval

External starts must not use `origin == "UI"` or an input `confirm: true` as
authority. They require a Rust value that cannot be deserialized or cloned:

```text
prepare_local_start(owner, effective_profile, monotonic_now)
→ LocalStartRequest displayed in a native confirmation
→ confirm_local_start(request, unchanged context)
→ LocalStartGrant
→ consume_local_start(grant, unchanged context, fresh credential check)
→ AuthorizedDestinationStart consumed by the owner/native start path
```

The grant binds registry instance and generation, complete destination snapshot,
selected ID, PID, production revision and every effective `OutputProfile` field.
It expires after 60 monotonic seconds. Expired/backward clock, changed profile,
revision, process, selection, destination, removal or reloaded registry fails.
The value is consumed even on failure. A successful consumption invalidates
parallel earlier dialogs/grants before entering the native output transaction.
The owner must still enforce output readiness, shutdown admission and H8 worker
barriers. Every new attempt or recovery start needs a new local approval.

`start_output(streaming)` received from CLI/MCP or Show Control must reject an
external selection with a structured local-approval-required error. It may
continue to start the existing authorized loopback mode under its old contract.
No control command may create or redeem a serialized local grant. Recording
continues independently if the external attempt fails.

## Exact Keychain binding, version 2

H8 stores only `rtmps:PORT` in `kSecAttrGeneric`; that is insufficient to release
the same credential to another host. The new canonical binding bytes are:

```json
{"version":2,"destination_id":"private-test","protocol":"rtmps","host":"stream.example.com","port":443,"application":"/live"}
```

`DestinationSpec::credential_binding()` creates those bytes in a fixed field
order. The native reader compares them exactly with `kSecAttrGeneric` before
returning secret data. A legacy port-only entry fails with
`CREDENTIAL_BINDING_MISMATCH`; it is never silently promoted. The `kc_UUID`
syntax and login-Keychain service remain compatible with H8, but the scopes are
deliberately distinct. The reference itself is not authorization or plaintext.

`associate_credential_local(id, expected_binding, reference)` can attach a native
enrollment result only to the unchanged tuple. A destination edited while the
sheet was open cannot receive that old credential. Association resets approval
to draft. The owner must retain the request's production context and reconcile
stale or cancelled results without silently deleting a Keychain entry.

## Native secure entry and lifecycle

`native/destination-credential.{h,m}` provides `begin`, `poll`, `cancel`, `busy`,
an opaque `status` function and a **native-only** secret reader. `begin` takes the
exact live `NSWindow` from Motive, an increasing owner request ID and JSON
containing only visible name and canonical binding. No plaintext parameter or
return value exists in that bridge. Results use a fixed 64-byte C structure.

The sheet uses Apple's [NSSecureTextField](https://developer.apple.com/documentation/appkit/nssecuretextfield)
and [NSAlert completion handler](https://developer.apple.com/documentation/appkit/nsalert/beginsheetmodal(for:completionhandler:)).
It shows the complete destination and explicitly says that enrollment does not
start streaming. The key is limited to 1–512 ASCII alphanumerics or `-_.~`.
The field is cleared after confirmation/cancel. Our owned C buffer is wiped
after use; AppKit/NSString can retain internal copies, so no zero-copy or
complete-memory-erasure claim is made.

[SecItemAdd](https://developer.apple.com/documentation/security/secitemadd(_:_:))
runs on a background queue because it may block. A valid signed
`local.motive.studio` identity with a team identifier is required before entry.
The ACL trusts the signed app; arbitrary helpers are not added. The existing
non-interactive login-Keychain policy is retained. No global certificate trust,
macOS privacy permission or credential export behavior is introduced.

Native phases are `awaiting_user`, `writing`, `stored`, `cancelled`, `failed`
and `stored_after_cancel`. `busy()` remains true while the sheet or Keychain
worker is active, including the wait for its main-thread completion callback.
The owner must include this in shutdown/admission barriers, not free it on a
UI timeout. `poll(consume=true)` acknowledges only a terminal result. A new
enrollment cannot overwrite an unconsumed result.

Cancel before submission closes the sheet without a write. Once writing starts,
cancellation cannot promise absence of a stored key: `stored_after_cancel`
retains the resulting opaque reference for explicit reconciliation. There is
no automatic deletion/replacement cleanup and no hidden network start.

The secret reader returns `CFDataRef` only to native service code. It must never
be declared as a plaintext-returning Rust UI/MCP wrapper or copied into
`obs_data`. The native service must construct its URL from the same validated
tuple, enable H8 secret-log suppression **before** handing the key to OBS, wipe
its native copy on destruction, and retain H8 TLS verification and quiescence.
The integrated `motive_approved_service` handles locally authorized external
destinations separately; the H8 loopback service retains its restricted scope.

## Persistence and checks

GPUI's AppKit raw window handle supplies an `NSView`, not an `NSWindow`.
`motive_destination_credential_begin_for_view` accepts that exact live owner
view, validates its AppKit type and attachment to the application's window
content tree, and delegates using `view.window`. It never selects a key/main
window heuristically. As with all native object APIs, the caller must retain a
valid object pointer for the duration of the call.

The store path comes from the owner's trusted macOS data-path policy. Its
directory must be owned by the current user with mode 0700; the file is a regular
0600 file. Reads refuse symlinks and bound bytes. Saves validate the complete
candidate, create a private temporary file exclusively, write and synchronize,
rename atomically, then synchronize the directory. Existing incompatible files
are not chmodded, migrated or deleted. Only the temporary file created by this
save may be cleaned up on failure. A directory-sync failure after rename is an
uncertain durability result, not proof that the old contents remain.

Owner mutations stage a private registry copy, persist it, then swap it into the
owner and advance the production revision. A validation failure leaves the old
registry usable. Any persistence failure leaves the old records in memory,
clears selection/validation, reports `DESTINATION_STORE_WRITE_FAILED`, and blocks
further destination authority in that owner. In particular, a failed approval
cannot become usable in memory. Disk contents may already be the candidate if
rename succeeded; reopening still restores no selection, preflight or start
grant and requires fresh local actions. No disk rollback is claimed.

`streaming/credential-reconciliation.json` is a separate private 0600 v1 receipt
store under the same 0700 directory policy. Each record includes request ID,
owner PID, requested revision, visible destination metadata, exact canonical
binding, terminal `stored`/`stored_after_cancel` phase and opaque reference. It
contains no key. A receipt is synchronized **before** attaching the reference to
a destination or allowing normal shutdown. Stale/cancelled completions remain
unattached; reopening restores the latest result to `enrollment` and exposes all
unattached records in `reconciliation_pending`. Previously attached receipts can
be pruned when another receipt is saved; unresolved records are never silently
overwritten. At 64 unresolved records, new enrollment is rejected explicitly.

If saving a receipt fails, the consumed native result remains owned in memory.
`destination_credential_busy()` aggregates the native worker and pending receipt
so shutdown/admission guards cannot miss it. Poll retries at most once per second
after disk recovery. `enrollment.persistence_error` reports
`CREDENTIAL_RECEIPT_WRITE_FAILED`, and `shutdown_blocked: true` makes the barrier
visible. Cancel during this interval converts the eventual result to
`stored_after_cancel`; it cannot delete the Keychain item or skip durability.
Successful receipt persistence sets `receipt_persisted: true`. Cancellation,
reopening and receipt persistence never automatically select, approve or start.
An abrupt process kill between Keychain commit and receipt persistence is not an
atomic transaction across these two stores and is not certified crash-safe.

Twelve destination unit tests cover malformed hosts/paths/ports/refs/schemas,
explicit IPv6 rejection, exact binding, stale enrollment and review, account distinctions,
local grants, expiry, edit/remove/reload invalidation and private persistence.
They were compiled with the real `src/output.rs` in an isolated local harness;
all twelve plus its seven output tests pass, with Clippy `-D warnings` and
rustfmt. The AppKit bridge passes ARM64/macOS 15 ARC syntax compilation with
warnings as errors. No Keychain/runtime UI/TLS success is inferred from these
tests. Owner integration and real external verification were pending at that
initial test stage; the later B2 evidence linked above supplies a separately
scoped private run, not a claim of independently decoded remote delivery or a
repeat on B3.

Six additional owner-state tests inject save failure before and after the
rename/durability boundary, verify failed association and invalid-edit behavior,
restore cancelled receipts without association, retry receipt storage while
preserving earlier references, and reject mismatched bindings/unknown fields.
These are filesystem/domain checks, not actual Keychain cancellation or external
TLS delivery evidence.
