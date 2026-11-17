# H14 — Show Control owner receipts and durable intent

Status: **crate foundation implemented; live integration and multimedia acceptance
pending**. This document supersedes only the conservative own-revision limitation
of the [original adapter design](../show-control/docs/integration.md). It does not
claim a live adapter, installed pack, native Deck, animation or recording.

The crate still owns rules, cooldowns, counters, deduplication and action history.
`Production` remains the sole authority for scenes, native operations, source
health and revisions. Event payloads cannot create a receipt or grant trust.

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
owner adapter, native Deck/MATCHDAY installation and visible recorded/RTMP
celebration before claiming live Show Control.
