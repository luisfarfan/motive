# Integration after H15 — checkpoint K

Nothing in Production, native engine, GPUI, Show Control runtime, package schema
or main packaging changed. This is a plan plus a tested data projection.

## Existing contracts and actual interoperability

Reuse `element-lab/element-spec/web-element.schema.json`, SDK `validate_web`, its
descriptor-relative no-follow `common.read_bytes`, and the example manifest's
properties/events/lifecycle/limits. The broker returns exactly the validated
bytes, retaining the original hashes. No second element format, arbitrary URL
capability or native install command is introduced.

`projection::goal_message` reads the actual Show Control fixture's
`motive.custom_event` / `goal-scored` and projects only typed team/home/away to
`goal.scored`. It does not authenticate the source or trust `origin`/`simulated`.
The future owner must check its already-approved binding and current identity.
The offline example runs that projection through the Rust gate, then the original
Element Lab runtime accepts the unchanged output in a Node test. This proves
schema/runtime interoperability, not a Show Control live dispatch or DOM/CEF render.

Important integration gap found in the real example: `goal.mjs` bootstraps via a
parent `postMessage` with exactly one MessagePort. Loading it as an isolated CEF
top-level document alone does **not** create MotiveElement or start the widget.
The future trusted renderer adapter must supply that bootstrap (host-controlled
outer document + port, or a reviewed adapter of the bootstrap to CEF process
messages), retaining the public MotiveElement API. Do not inject arbitrary JS
strings from event data. A same-renderer outer document is not a security sandbox;
all authority still remains outside it. That adapter is not implemented here.

## Minimal staged work

1. Finish authorized native fixture bundle/supervisor, sandbox and resource-access
   tests. Bind exact CEF archive/API/framework/helpers. Confirm both 30 FPS layouts,
   alpha, shutdown and process metrics before 60 FPS. No production changes needed.
2. Connect the tested Rust gates/lifecycle and buffer contract to the native CEF
   adapter through a small typed boundary. Add two-way status admission, process
   watchdog, reserved cancel lane, generation/resize teardown and safe frame
   transport. Test bootstrap and the actual goal example under owned-content policy.
3. After H15, add BrowserHostManager to the existing owner; no second Production.
   Installation accepts a reviewed immutable package capability, not paths/URLs.
   Capabilities report unavailable until native gates pass. Trust is minted by
   local approved import/binding flow, never a deserialized confirmation boolean.
4. Register a minimal visual libobs source through the existing engine adapter.
   Production holds source ID/generation, host status and texture; the source
   consumes latest complete frames on OBS's clock. Follow the separate adapter
   contract. Do not load OBS's Qt plugin or enable browser audio.
5. Extend the actual owner Show Control backend with one typed visual action,
   retaining durable intent, binding fingerprints, session/revision validation,
   cooldown and dedup in the existing crate. Preserve own-mutation receipts and
   `needs_reconciliation` for uncertain outcomes. A JS receipt is not a native
   rendered-frame receipt and cannot justify replay or continuing a timed-out job.
6. GPUI exposes reviewed properties, visibility, explicit resume/restart and health
   through those same owner operations. CLI/MCP receive bounded IDs/status only;
   no bytes, arbitrary scripts, raw errors or renderer command-line flags.
7. Persist only package identity/hash/version, approved properties, placement and
   policy version in an explicit future project revision. Restore disarmed with
   no event replay. Source and visual-layer identity remain separate for reuse.
8. Integrate portable assets/signing/source notices only after the bundle/license
   review. Re-run the actual H15 regressions with real libobs media acceptance
   when authorized. No native acceptance can be inherited from these unit tests.

Cancellation on hidden matches existing Web Element `on_hidden=cancel`; it must
not silently alter H11 native video visibility semantics. Multiple scene layers
referencing the same source share its event state; policy should consider total
active visibility, not one layer's eye icon. Suspend and source removal revoke
frames/channels; explicit resume starts a fresh host generation when closed.

Validation: K-rust.log, K-goal-message.json and K-runtime.log. The initial JS test
import-path error is retained separately. No native scene, recording or stream
was involved in these tests.
