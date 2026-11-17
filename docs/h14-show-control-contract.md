# H14 — Show Control owner receipts and durable intent

B3 source candidate adds the explicit [animated widget trigger](h14-animated-trigger.md):
one durable intent, one native operation and source lifecycle receipts covering
only its own contiguous changes. The [real B3 verification](h14-show-control-b3-verification.md)
observed native GPUI/MCP celebrations in decoded MKV and loopback RTMP, including
entry, hold and exit, with the corresponding owner receipts and journal.

Status: **PARTIAL — real B3 installation, celebration media and owner integration
verified within the recorded coverage**. Concurrent GPUI editing remains pending;
cancellation before the first native tick remains `NOT_OBSERVED`. This document
supersedes the conservative own-revision limitation of the
[original adapter design](../show-control/docs/integration.md). Full output delivery
and A/V synchronization remain separate gates.

The crate still owns rules, cooldowns, counters, deduplication and action history.
`Production` remains the sole authority for scenes, native operations, source
health and revisions. Event payloads cannot create a receipt or grant trust.

## Live owner integration

`src/show_control.rs` is a child of the existing `core` module. It temporarily
takes its `State` out of the same `Production` while the backend borrows
`&mut Production`; it does not create a second engine or send commands over a
socket. The outer GPUI owner heartbeat calls `poll_health` then
`poll_show_control` once. Inner command health polling never runs rules. Closing
an MCP client therefore does not cancel the owner runtime.

Dispatch rebuilds the typed action against a fresh projection of the real graph,
checks its exact PID/revision, synchronizes the intent journal, and invokes the
existing allowlisted `Production::apply` commands without yielding. During this
scope, `apply` skips its usual leading health poll because the adapter has just
performed that check; the post-command polls remain and retain their provenance.
Cut/Fade configure/select remains two commands in one owner turn, with a check
between them. A partial failure is uncertain, never described as a rollback.
Selecting the current scene is an acknowledged no-op and cannot claim an old
native operation ID.

The bounded revision ledger records explicit command deltas, individual native
animation IDs, individual transition IDs, source lifecycle IDs, and external
deltas. Audio, output, import, UI/MCP and unrelated lifecycle changes cannot
enter an own receipt. Native IDs are registered at acceptance before polling.
Source changes can be attributed only to the exact source in the synchronous
event/update dispatch scope; later autonomous timer/hide changes are
conservatively external. The ledger keeps 4096 deltas; a gap or eviction denies
rebasing. Its 512-operation limit fails closed rather than forgetting an owner.

Operation tokens contain a fresh 128-bit random owner session, namespace,
native ID and owner serial. Animation completion requires the native terminal
phase **and** the existing model/acknowledgment barrier. Transition completion
requires the matching native ID and terminal phase. A successful widget/text
call is a control acknowledgment; it is not proof of a rendered frame. Unknown
observations remain reconcilable and never replay. A failed native cancel reply
after durable cancel intent still forces explicit reconciliation.

Only existing overlays/widgets, animations, cancellation, Cut/Fade and compatible
text definitions enter this adapter. Rules cannot start external streaming,
install sources, run shell code, synthesize audio or create another media clock.

## Shared control and native UI contract

The following JSON operations use the same CLI transport and MCP tools:

| Operation | Required fields | Effect |
|---|---|---|
| `show_control_status` | none | Bounded shared rules, Deck, jobs, receipts and history |
| `press_show_control` | `session`, `button_id`, `event_id` | Submit an existing nonsensitive button; stable event ID deduplicates |
| `cancel_show_control` | `session`, `job_id` | Durable cancellation request; does not claim native completion |
| `reconcile_show_control` | `session`, `job_id` | Observe only; never resume remaining actions |
| `save_show_control` | none | Explicit private configuration v1 save |
| `load_show_control` | none | Explicit restore into a new **disarmed** session |
| `arm_show_control` | `pid`, `revision` | Exact owner revision plus binding fingerprint check |

Remote job controls require the exact random session returned by status. PID
and numeric job IDs can be reused after restart, so those values alone are
insufficient. No public command accepts confirmation booleans, owner receipts,
arbitrary native operations or journal paths. `configure_show_control` accepts
typed Config/Deck through the owner/CLI; it is not a published MCP enrollment
tool. Creator Pack installation uses the same owner method after its review.

The native UI calls `configure_show_control`, `press_show_control`,
`cancel_show_control`, and `reconcile_show_control` on its one Production. A
sensitive button uses `prepare_show_control_confirmation` and displays the
returned token's `label()`, `button_id()` and exact `actions()`. It consumes that
non-Clone, non-Deserialize token with `confirm_show_control_local(token,event_id)`.
The token binds owner session, PID, revision, button/configuration and 60 seconds
of monotonic time. No RPC may mint or serialize it.

The crate's existing `DeckRuntime` owns cooldown, pending and history once.
`authorize_live`/`press_live` require the embedding owner's validated local
authority; this model permission itself does not establish Production authority.
`finish_live` records real completed/rejected/cancelled/reconciliation results.
It cannot label a simulated press as live, nor finish a live request through
`finish_simulation`. GPUI must not implement another cooldown counter.

Status exposes the last 16 jobs, last 4 records per job, 64 decisions and 32
native operation entries, with total counts and limits. It omits copied text
plans and arbitrary string variables; full dispatch evidence stays in private
journals. Missing older entries from this projection do not permit replay.

## Explicit configuration persistence

`show-control/configuration.json` is a separate version-1 document containing
typed Config, Deck and a SHA-256 fingerprint of actual scene/layer/source IDs,
source types and immutable resource bindings. Live selection, text, visibility
and transforms are excluded so the deck's own legitimate actions do not
invalidate it. A structural identity or resource change requires review.
Scenes, profile stores and audio documents are not rewritten.

The private store is bounded to 1 MiB, requires a 0700 owned directory and 0600
regular file, refuses symlinks/unknown fields/future versions, and saves with
exclusive temporary creation, file synchronization, rename and directory
synchronization. It never chmods or deletes an incompatible existing store.
After a rename/directory-sync failure, durability is uncertain, not rolled back.

Loading creates no jobs and grants no authority to replay. Explicit arming checks
the supplied PID/revision and current binding fingerprint; new button presses
also reject replaced bindings. The configuration is never auto-loaded, armed or
saved. Each session has a new durable journal; at 128 retained directory entries
new sessions are refused until an explicit archive/review. Past-session journals
remain evidence for `IntentJournal::read`; their native tokens cannot cancel or
resume operations in a new process.

The [B3 persistence verification](../var/evidence/h14-persistence-b3-01/verification.json)
confirmed real GPUI save/restore, exact project roundtrip, restored rules/deck,
an unarmed new session, no replayed jobs and idle outputs after a normal restart.
Its post-restart AX/core evidence does not establish full-resolution visual
acceptance: those screenshots showed a Stage Manager thumbnail.

## Checked dispatch and attributed revisions

The `Backend` trait retains its original methods. Two new methods have defaults
that call the old methods and return **no receipt**:

```rust
fn dispatch_checked(
    &mut self,
    action: &PreparedAction,
    action_key: &str,
    expected: Revision,
) -> DispatchReport;

fn poll_checked(
    &mut self,
    operation_id: &str,
    action_key: &str,
    expected: Revision,
) -> PollReport;
```

`DispatchReport` contains the existing `DispatchOutcome` plus an optional
`MutationReceipt`; `PollReport` contains `Completion` and an optional receipt.
Legacy backends and local actions preserve the admission revision. They cannot
silently adopt the newest snapshot merely because an action finished.

A receipt contains `action_key`, optional `operation_id`, exact `before` and
`after` revisions (`pid`, `revision`). The Runtime accepts it only when:

- The action key matches the actual job/action, currently
  `correlation_id:job_id:action_index`.
- `before` equals the job's current expected revision exactly.
- Both revisions belong to the same nonzero owner PID and do not regress.
- For an accepted or completed native operation, the operation ID matches the
  one returned by dispatch. A synchronous completion has no operation ID.
- The report is a real accepted/completed dispatch or completed poll. Pending,
  unknown, simulated or rejected reports cannot advance revisions.

At most two receipts are retained per action: dispatch and terminal observation.
An invalid receipt marks the action uncertain and the job
`NeedsReconciliation`; a known native operation ID remains available. It never
causes automatic retry. The next multimedia step uses only the last accepted
receipt's revision and therefore rejects a later unrelated UI/MCP edit.

These checks validate the chain, **not its provenance**. Only the owner adapter
may construct receipts. It must prove that every revision in an attributed
range belongs to this action. The receipt must not be accepted as JSON supplied
by a client, rule, pack or voice provider.

## Owner integration requirements

1. Run the final freshness check and command application in the same owner turn.
   Refresh native lifecycle state before validating the expected revision.
   Rebuild the prepared commands from the typed action and current snapshot;
   a cached `PreparedAction.commands` vector is not dispatch authority.
2. Persist the exact intent successfully before calling `Production::apply`.
   A journal failure prevents dispatch. Do not unlock/yield between the final
   revision check and the mutation.
3. Execute only the allowlisted existing-source commands. A Cut/Fade action
   still has configure/select steps: retain partial failure rather than claiming
   rollback or atomic installation. Stop if an intermediate step fails.
4. Construct and persist the synchronous receipt using the exact observed
   before/after revisions. Return acceptance separately from native completion.
5. For an animation or scene operation, retain owner session, action key,
   operation namespace/ID, source identity and revision attribution until the
   native terminal state and required acknowledgment barrier are observed.
6. A terminal receipt may cover only attributed changes. If a concurrent command,
   unrelated source lifecycle, import or failure changed the revision, withhold
   revision advancement. The operation may still be observed completed; the next
   action is then rejected as stale rather than continuing under new authority.

H13 `poll_overlays` increments a revision for an aggregate of animation jobs
**and** source phase/visibility changes. `poll_health` also increments for audio
and scene lifecycle. A pending operation's continued existence does not prove
ownership of that aggregate delta. The live adapter must track attribution at
those mutation sites or conservatively refuse continuation.

An owner-generated operation token must carry a fresh process-session identity;
PID alone can be reused by macOS. The owner must reject tokens from another
session before consulting native numeric operation IDs. A new Runtime instance
must not gain permission to reuse an old action key in the same journal.

`Completed` must describe its observation precisely. A control acknowledgment,
updated definition or elapsed duration does not prove presentation in a rendered
frame. Native progress/completion and recorded/received media remain separate
evidence. There is no new multimedia clock in Show Control.

## Durable intent journal

`motive_show_control::journal::IntentJournal` creates a **new** journal for one owner
session. The embedding application supplies an absolute path through its trusted
macOS data-path policy. Events and packs cannot select journal paths. The parent
must already be a private, non-symlink directory (0700); `create_new` refuses an
existing file or symlink. The new file is 0600. Header creation synchronizes the
file and its directory; each subsequent append calls `File::sync_all` before
success is returned.

The schema-1 JSON-lines entries are header, intent, dispatch result, operation
completion and cancellation intent. Limits are **64 KiB per record, 16 MiB and
4096 records per journal**. There is no silent eviction, truncation or rotation.
The owner must handle a full journal before admitting more work.

```text
final owner revision check
→ begin(DispatchIntent) + successful durability barrier
→ Production command(s)
→ record_dispatch(DispatchReport) + successful durability barrier
→ native observation
→ record_completion(PollReport)
```

`begin_cancel` persists the known action/operation before issuing its one cancel
request. Cancellation is not completion; a native barrier may remain pending.
The journal rejects duplicate intent, duplicate dispatch result, mismatched
operation/receipt and repeated cancellation. A write/sync error poisons that
writer: subsequent appends fail closed.

If persisting a result fails after mutation, the adapter must return uncertainty,
retain any known token in its owner registry, and never retry the mutation. An
intent without a result is deliberately **uncertain**, even if the process may
have failed before sending it. The journal cannot solve that crash ambiguity or
provide exactly-once execution.

`IntentJournal::read` is read-only. It bounds input, rejects symlinks/non-private
files, verifies opened file identity, validates the record sequence, and rejects
unknown versions/fields or a partial final line. Corrupt bytes remain intact for
diagnostics; recovery does not repair, append, apply commands or resume jobs.
Recovered accepted operation records retain their IDs; uncertain completions
also retain their operation in the original entries. An operator/owner must
reconcile them against the original session, never a reused native token.

This is local filesystem durability, not an authenticated format or a promise
against disk failure, malicious same-user replacement or every power-loss case.
No audio, credentials or transcriptions belong in this journal. Intent text is
the user's overlay text already admitted to the local production.

## Checkpoint compatibility and recovery

Checkpoints without receipts remain schema 1. If a job contains revision receipts,
the writer emits schema **2** explicitly. Reader support remains v0/v1 and adds
v2; v1 rejects a hidden receipt extension. Receipt counts, identities and chains
are validated. Old project/mixer/output formats are not touched.

Restoring a queued job cancels it. Restoring an accepted job requires explicit
reconciliation. `reconcile` only observes the known operation and never resumes
remaining sequence steps, even if a valid terminal receipt arrives. Timeout,
uncertain result and cancel request cannot free an unresolved native operation
for automatic redispatch.

## Verification scope

`show-control/tests/runtime_receipts.rs` verifies owner revision rechecking,
synchronous and asynchronous own chains, concurrent edit rejection, forged or
mismatched receipts, operation identity, explicit v2 restoration and observation
without replay. `show-control/tests/journal.rs` exercises real temporary files:
intent/result separation, incomplete crash tail, permissions and symlinks,
duplicate/mismatched writes and bounded failure preserving the prior bytes.

Run `cargo test --locked`, `cargo clippy --locked --all-targets -- -D warnings`
and `cargo fmt -- --check` in `show-control/`. These are crate contract and
filesystem tests, **not multimedia acceptance**. H14 still requires the actual
owner/Deck/MATCHDAY exercise and decoded recorded/RTMP celebration for any tested
binary; the [B3 report](h14-show-control-b3-verification.md) supplies that evidence
for its stated coverage. At the live-adapter integration checkpoint, the root suite passed 111 tests,
the independent Show Control crate passed 111 tests, and both Clippy runs with
`-D warnings` passed after live-adapter integration. These counts include
domain/storage/receipt checks, not physical assertions.

## Real verification harness and B3 evidence

`scripts/verify_h14_show_control.py --plan` is offline and performs no app or
device operation. Execution requires `--lock-held`, an already-open signed
`--app`, its real `--data-dir`, and a fresh `--output` directory. It checks the
canonical git-common-directory physical lock's H14 owner text, exact process
executable, idle outputs, a GPUI-installed complete MATCHDAY binding table, an
armed session, an idle countdown and an empty/controlled-tone mixer.

It uses the real H13 `Client` and `Receiver`, selects MATCHDAY Live, creates
temporary output profiles, starts simultaneous recording and **loopback** RTMP,
submits MCP/CLI goal/countdown events, observes own revision receipts, rejects
cooldown and a repeated event after cooldown, attempts a real MCP/CLI concurrent
edit, and disconnects MCP while a native animation is pending. CLI then observes
the same owner and output attempts completing. It never installs MATCHDAY,
invents a UI origin, writes a configuration store or starts an external
destination. Output attempts and canonical lock identity are checked throughout.

The harness retains snapshots, MCP/CLI transcript, current owner journal, native
operation IDs, unchanged recorded/received media, hashes, decoded PTS, audio
measurements and contact sheets. It restores selected profiles, local
credentials, approved destination selection, controlled tone state, touched
layouts/visibility and the prior scene/transition when the same owner is safe to
modify. The real goal counter/history/dedup evidence remains. If the previous
loopback endpoint was unset, there is no unset command, so its temporary endpoint
is explicitly reported as a retained change. No project/audio/profile/Show
Control/destination store is saved; their before/after hashes are compared.

The [B3 run and independent media audit](h14-show-control-b3-verification.md)
verified the real GPUI celebration, decoded entry/hold/exit in both outputs,
cooldown, duplicate rejection, MCP/CLI concurrent-edit fencing and continuation
after MCP disconnect. Overall acceptance remains **PARTIAL**: concurrent GPUI
editing is still pending, and the two pre-first-tick cancellation attempts stayed
`NOT_OBSERVED`. Exact packet delivery and A/V synchronization remain separate
H14 output gates. A prepared harness or an unobserved race supplies no additional
physical acceptance.
