# H14 — RTMPS integration review

Read-only review followed by the three bounded fixes below. No destination was
contacted, Keychain item created, app launched or physical device used by this
review. Runtime/UI files are frozen for the owner's integrated build. The
coordinating test run reports **111/111 tests passed**, including six new
filesystem/owner-state tests, and final integrated Clippy `-D warnings` passed.

## Findings corrected

- **Persistence after mutation:** save/approve/remove/credential association
  previously changed live registry state before saving. They now stage a private
  copy, save, then swap. A storage error freezes destination authority and clears
  selection/validation in the owner; a failed approval cannot become usable in
  memory. Tests inject failure before and after the rename durability boundary.
  A post-rename error does not prove disk rollback. See
  `src/destination_runtime.rs:119` and `src/destinations.rs:967`.
- **Lost late-cancellation reference:** terminal opaque references previously
  lived only in volatile enrollment status. A private versioned receipt now
  persists exact destination metadata/binding, request context, phase and
  reference before association or normal shutdown. Pending persistence joins the
  native/enrollment shutdown barrier, retries at most once per second and reports
  a visible storage error. See `src/destination_runtime.rs:168`, `:421`,
  `src/destinations.rs:299`, and `src/ui/studio/destinations.rs:176`.
- **Literal IPv6 incompatibility:** the host model accepted a path whose TLS
  hostname handling is incompatible with the pinned librtmp/mbedTLS combination.
  Literals now fail explicitly with `DESTINATION_IPV6_UNSUPPORTED`. DNS names,
  including names resolving through AAAA, remain accepted. No TLS policy or
  certificate trust was weakened. See `src/destinations.rs:43`.

## TLS and log evidence from pinned official source

The source below is the locally pinned upstream OBS 33.0.1 source, not an
inference from a successful socket connection:

- `scripts/build_obs_outputs.py:64–68` selects `USE_MBEDTLS`/`CRYPTO` and links
  mbedTLS, mbedX509 and mbedCrypto.
- `.deps/obs-studio-33.0.1/plugins/obs-outputs/librtmp/rtmp.h:92–98` configures
  `MBEDTLS_SSL_VERIFY_REQUIRED` for the TLS client.
- The same tree's `librtmp/rtmp.c:317–340` imports Apple anchor certificates via
  `SecTrustCopyAnchorCertificates`. `:948–958` sets the peer hostname before
  handshake; `:963–987` rejects certificate-verification failure.
- `librtmp/parseurl.c:85–104` preserves IPv6 URL brackets in `Link.hostname`.
  `librtmp/rtmp.c:747–758` strips them for address resolution, but `:954–957`
  passes the original bracketed value to TLS hostname verification.
- Exact mbedTLS source revision
  `c765c831e5c2a0971410692f92f7a81d6ec65ec2` is cached under
  `target/portable-sources/archives/mbedtls-c765c831e5c2a0971410692f92f7a81d6ec65ec2.tar.gz`.
  Its `library/x509_crt.c:2865–2881` passes the hostname directly to `inet_pton`;
  `:2904–2918` compares parsed bytes with iPAddress SAN. `[::1]` is therefore
  incompatible with a correct `::1` IP SAN. Ordinary canonical IPv4 has no
  brackets and follows the IPv4 SAN parser; this is code evidence, not a live
  certificate fixture result.
- Upstream `rtmp-stream.c:55–60` routes librtmp logs through `blogva`.
  `native/approved-service.inc:32–35` enables process-lifetime suppression before
  handing the secret to OBS; `native/engine.m:169–175` suppresses those free-form
  messages. Network failures use structured output codes. No key was used
  in this review to empirically certify redaction.

Exact Keychain generic-metadata comparison is in
`native/destination-credential.m:61–83`. The native worker retains busy state
until its main-thread completion; cancellation after storage returns the opaque
reference instead of deleting the item. The H8 output barrier remains in
`native/output-slots.inc:115–132`; output/service/encoder release follows that
barrier (`:153–169`). No concrete binding, one-use-grant, or worker-lifetime
bypass was identified in the reviewed paths.

## Limits remaining

- Keychain commit and filesystem receipt are two stores. Abrupt kill/crash in
  the interval before the first durable receipt can still orphan a reference;
  this is not certified crash-atomic. Normal cooperative shutdown waits for it.
- Reopened receipts show exact visible metadata and opaque reference. There is
  no UI action yet to consume an old receipt for explicit reassociation or
  deletion. Nothing automatically associates, approves, selects or starts.
  Sixty-four unresolved receipts block further enrollment rather than discard
  evidence. The full state/API contract is in `h14-destination-contract.md`.
- These checks do not prove a trusted external handshake, provider acceptance,
  received/decoded audio-video, physical sheet cancellation or actual disk-full
  behavior during Keychain completion. Those remain the owner's separately
  coordinated runtime verification.
