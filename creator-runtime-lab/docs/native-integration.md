# H17 handoff and minimal integration

H17 remains active in the chat **Cerrar fiabilidad y beta de Motive** and worktree
`motive-h17` on `codex/h17-production-reliability`. Read-only status was inspected
on 2026-11-18. No explicit release of shared files or integration authorization
has been received. H18 changes only `creator-runtime-lab/` and `web-host-lab/`.
Production/native/Show Control/root Cargo/main bundler are unchanged here.

After an explicit handoff and owner authorization:

1. Borrow the current Production snapshot/capabilities on its owner thread.
   Extend the current local review capability to hold verified package bytes,
   exact plan fingerprint, session/revision and expiry. Persist intent **before**
   each dispatched step; a UI/MCP boolean or package field cannot mint it.
2. Adapt the existing creator-pack step executor to attach to existing scenes.
   Existing `CreateOverlay` already produces a source plus its first layer;
   `AddLayer` reuses sources. Derive stable IDs only from successful owner
   receipts/differences. Revalidate global graph, asset and decoder budgets.
3. Resolve resources through the existing authorized asset broker/normalizer.
   Bind its actual returned asset IDs, never package paths or symbolic hashes as
   presumed native IDs. Native normalization may change bytes: retain the
   original archive hash and the actual managed asset receipt separately.
4. Keep disabled visual bindings separate from the installed graph. Extend the
   actual Show Control backend with the reviewed web visual action only after
   host isolation gates pass. Its durable intent, cancellation, dedup and
   reconciliation remain authoritative. A JS ACK is not a native terminal result.
5. Add BrowserHostManager to that same owner. The isolated H18 frame admission
   policy is ready for its future libobs adapter: consume newest BGRA under OBS's
   clock, upload/change/free textures in OBS graphics context, blank on failed or
   revoked generation and account aggregate visibility across all scene layers.
   No second renderer, audio web, MCP frames or host timestamps as media PTS.
6. Connect the independently tested fixed MessagePort bootstrap through a typed
   CEF process-message dispatcher with peer/main-frame/generation authentication.
   That native dispatcher is not implemented in the owned static fixture yet.
7. Persist actual installation state and resource mappings through an approved
   compatibility decision. Restore disarmed, recheck original package and managed
   asset hashes, report orphans/incompatibilities, and never replay events.
8. Expose library/review/properties/state in the existing GPUI design and shared
   CLI/MCP operations, keeping native local approval as the final authority.

Acceptance then requires real transparent Goal Celebration in preview, MKV and
local RTMP, decoded alpha/motion/timestamps, resize/cancel/crash/restart, source
removal during output, helper cleanup and H17 regression gates. Offline planner,
DOM, ABI and build checks cannot substitute those media results. No push, merge,
rebase, release or public streaming is part of H18.
