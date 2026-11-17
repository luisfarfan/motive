# Future integration with the Production owner

Baseline inspected: Motive `b52d135`, H12, 2026-11-17. This is the adapter design,
not a live integration claim. Show Control does not instantiate `Production`,
open libobs, capture audio/video, connect to the control socket, or advance media
time. H13 must stabilize before any main-app integration is implemented.

## Existing authority and boundaries

Read-only evidence: [H11 contract](../../docs/h11-overlay-ui-contract.md),
[H12 contract](../../docs/h12-creative-studio-contract.md),
[H9 lifecycle](../../docs/h9-scene-transitions-verification.md),
[core commands](../../src/core.rs),
[H11 schemas](../../src/overlays/protocol.rs),
[overlay lifecycle](../../src/overlays/production.rs).

UI, CLI and MCP already converge on one owner. A future adapter must run its
final precondition check and command dispatch on that same owner. Show Control
owns rules, counters, deduplication and decisions; `Production` alone owns
scenes, source health, revisions, output state and native operations. Cached
snapshots may advise preparation but cannot authorize a stale mutation.

`pid + revision` identify a snapshot. Revision is not a media clock and does not
advance for every animation progress sample. H11 has **no public
`expected_revision` or compare-and-swap command**. Any revision guard in this
crate is a prepared-adapter precondition, not a field that can be sent to today's
CLI/MCP. The future owner must compare immediately before applying. Two separate
socket calls (`status`, then mutation) do not make an atomic check.

The independent runtime conservatively retains the admission revision across
every sequence step. Neither a local counter increment nor a native completion
silently adopts the latest snapshot revision. Consequently a later multimedia
step fails stale after any owner revision change, including a previous step's
own mutation. Live multi-step continuation requires a future receipt contract
that identifies the acknowledged own-mutation revision and rejects unrelated
edits; this crate does not pretend that contract already exists.

## Intent mapping to existing commands

| Show Control intent | Existing command(s) | Preparation / observed result |
|---|---|---|
| Show or hide existing source | `overlay_event {source_id,event:"show"/"hide"}` | Verify the source is an H11 overlay. This affects every layer sharing it. It does not set a layer's `visible`. |
| Trigger widget | `overlay_event {source_id,event:"trigger"}` | Lower third/alert only; preserve native error for an incompatible source. Triggering an alert can restart its deadline. |
| Start/reset countdown | `overlay_event` with `timer_start` / `timer_reset` | Countdown source only. Reset does not start. Native timer owns progress, including while hidden/off-scene. |
| Animate layer | `animate_overlay {scene_id,layer_id,animation}` | Active scene, correct layer/source, no Cut/Fade and available slot. Store returned operation ID; observe native phase plus acknowledgment barrier. |
| Cancel layer animation | `cancel_overlay_animation {operation_id}` | A request, not immediate restoration. Observe terminal state; unknown/evicted IDs fail. |
| Request Cut/Fade | `configure_transition {transition}` then `select_scene {scene_id}` | Cut duration 0; Fade 100–5000 ms. This is a two-command intent, not an atomic existing command. Stop if configure fails; never silently proceed with an old preference. |
| Update text | `update_overlay {source_id,definition}` | Read complete current definition; change only the intended text/title, preserve kind/asset/widget type and every other field; owner-side revision check. No existing `set_text` command. |
| Local counter/notification | No multimedia command | Execute only in Show Control; distinguish its completion from native media completion. |
| Sequence | Ordered approved intents | Stop on required-step failure; retain completed step results. There is no rollback of a shown alert or completed scene cut. |
| Sound/TTS | None | Unavailable until an approved audio playback contract exists. Text preparation must never report speech played. |

An update's command acknowledgment does not prove a rendered frame: OBS may
apply an update later. Do not label source presentation or a transition complete
just because a wall-clock duration passed. An adapter may report a synchronous
control mutation as accepted, with its narrower observed state, while leaving
visual completion unavailable if the core lacks a corresponding operation.

## Concurrency and readiness

The H12 restrictions remain authoritative until superseded by a reviewed H13
contract:

- Source events can run live and independently of Cut/Fade/layer animation.
  Creating/removing sources, changing variants, adding/removing layers and
  loading projects require idle. A live rule cannot create a missing source.
- Stable scene means no layer animation or Cut/Fade pending. Text/style update
  needs stability; video definition update additionally needs idle. Geometry and
  order edits permit a stable live scene; changing a layer's `visible` needs idle.
- Only active-scene layers animate. One operation per layer and at most eight
  simultaneous layer jobs. Cut/Fade excludes these jobs. `running` and
  `cancel_pending` are occupied; a terminal job with `pending_ack:true` is still
  busy. The owner performs acknowledgment internally; no public ack command
  exists.
- H9 prepares cold target captures off-air and keeps the previous scene until
  completion. A failed target preserves the previous scene. Show Control must
  not recreate cameras, claim a cold scene ready, or perform an automatic device
  reconnect. A source-ready snapshot allows another preparation check, not a
  replay of a previously sent mutation.
- A missing/revoked resource is a typed failure. A busy resource may be deferred
  only before dispatch, under an explicit bounded deadline. Revalidate PID,
  revision, selected variant, target identity and source health when dequeued.
  If the expected revision changed, return stale state for caller review rather
  than silently changing the user's intention.
- Shutdown, import, transition preparation and recovery states must come from
  `Production`; an adapter cannot override them. No audio selection or output
  recovery is implied by an automation rule.

## Delivery and cancellation contract

Keep a Show Control action ID separate from native animation/import/transition
operation IDs. Native counters are independent namespaces. A saved action
record includes event/rule identity, adapter session, expected revision, dispatch
state and returned native token when available.

Stages are validated → prepared → sent → accepted → observed terminal. Rejected
and failed are explicit. A simulator may produce plans or simulated outcomes,
but must not claim that a real core accepted/completed them.

Before live dispatch, persist a durable intent marker. After an uncertain write
or lost response, query the owner and reconcile by known token/context. Never
automatically retry `trigger`, `select_scene` or a text mutation merely because
the transport timed out. Without a native idempotency key there is no general
exactly-once guarantee. A crash between send and acknowledgment must remain
uncertain and require reconciliation or user resolution.

Canceling queued work removes its unstarted steps. Canceling accepted media work
requires the corresponding native operation ID and observes its eventual
terminal state; cancellation is not rollback. A timeout of an accepted native
operation ends the automation's waiting policy, not the native operation's life.
It remains unresolved until observed, and incompatible work stays blocked.

The implemented `reconcile` method only observes an existing operation; it never
replays the mutation or resumes the rest of an interrupted sequence. Unresolved
jobs retain queue capacity. Polling, reconciliation and cancellation must reject
an operation from a different Production process, even if its numeric token was
reused after restart.

On restart, load versioned Show Control configuration and bounded dedup/local
state independently from Motive project v3/v4, output profiles and mixer state.
Do not resume queued or uncertain media writes automatically. Preserve their
interruption/uncertainty records. Monotonic deadlines belong to an epoch; restore
remaining cooldown conservatively, never reinterpret saved monotonic numbers as
the new process clock. A retention bound limits deduplication guarantees and
must be visible to operators.

## Creator Pack installation boundary

Offline validation can propose `create_scene`, `create_overlay`, `add_layer` and
`set_transform`, plus bindings of symbolic pack references to future returned
IDs. These are proposals, not executable raw MCP. Future installation must:

1. Require idle, current resource budgets and a reviewed plan; separate optional
   unsupported capabilities from required failures.
2. Stage explicitly authorized local assets through the existing asset boundary.
   H12's native file picker is the authority for external file access; packs
   cannot choose paths or automatically download URLs.
3. Resolve source/layer IDs from returned graphs. `create_overlay` creates a
   default secondary layer; it does not return a preordained layer ID.
4. Count shared sources once but all layers, and account for both 960×540 and
   540×960 layouts. Respect eight scenes, sixteen sources, thirty-two layers,
   native definition dimensions and resource budgets.
5. Record partial installation outcomes and let the owner remove only known
   created resources after reference checks. Existing commands do not provide
   an atomic pack transaction. No “installable” claim is warranted until this
   complete path is implemented and verified against real outputs.

## Narrow next integration increment

After H13 review, add the owner-side adapter with only existing-source
show/hide/trigger and one explicit Cut/Fade request, an armed local mode and
read-only monitoring. Confirm a manual deck event changes the existing core
state and appears in a controlled recording/RTMP receiver. Then verify accepted
animation completion, conflicting controls from UI/MCP, source failure, restart
and transport uncertainty. Keep voice/provider work synthetic until this path
passes; do not merge a second engine, multimedia scheduler or GPUI state store.
