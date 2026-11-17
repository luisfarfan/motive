# Independent-module security review

Scope: Show Control's offline Rust model/runtime/checkpoints and proposed adapter
boundary, reviewed 2026-11-17. Tests use synthetic events and a scripted backend.
They establish deterministic control behavior, not libobs completion, actual
provider authentication, Keychain integration or end-to-end live safety.

## Boundaries enforced by this increment

- The executable is a simulator. It imports neither Motive nor libobs, opens no
  control socket and requires the simulated marker for injected events. A
  simulated event is rejected by a non-simulated backend before dispatch.
- Event payloads cannot construct `Trust`; trusted origin/user/confidence sets
  come from the embedding adapter. Claimed confidence without an approved origin
  fails its condition. This is an interface boundary, not cryptographic proof:
  a future network adapter must authenticate before constructing that context.
- Commands are tagged intents, with no shell/JavaScript/raw MCP escape hatch.
  Sound is unavailable; prepared speech remains inert text. Packs cannot use
  their contents to grant external file access or load remote code.
- Rules, nested sequences, conditions, input bytes, variables, queue admission,
  per-event action expansion and decision history have bounds. Cycle lineage
  and correlation budgets cover internally emitted events. Counter overflow
  fails rather than wraps. A full event admission is rejected atomically.
- The deduplication journal fails closed at capacity. It does not silently evict
  old identifiers and then replay them. Rejected full-queue events remain
  consumed; retrying requires an explicitly new event and operator intent.
- Timeout/cancellation is distinct from native termination. Unresolved jobs
  retain capacity and require explicit observation; uncertain dispatch is never
  retried automatically. Restoring a checkpoint cancels queued steps, retains
  unresolved native outcomes and never resumes mutations by itself.
- Checkpoint parsing validates versions, fields, counts and ranges. It is not an
  authenticated file format or a durable write-ahead journal: an embedding live
  adapter must persist intent atomically before dispatch. Someone allowed to
  replace local definitions/checkpoints is already inside the configuration trust
  boundary. No exactly-once guarantee across crashes is claimed.

## Review findings and retained regressions

| Finding | Resolution / regression |
|---|---|
| Busy policy did not recognize preparation's `PRODUCTION_BUSY` code | Recognize the actual code; `production_busy_obeys_explicit_defer_policy` verifies defer then timeout without dispatch. |
| Child-event admission could prune a vector during a tick using cached indices | Schedule by stable job IDs and prune outside child admission; `pruning_during_child_event_cannot_invalidate_dispatch_indices` crosses the terminal-history bound. |
| Local sequence step adopted a new production revision without user review | Preserve the admission revision; `local_step_does_not_silently_rebase_a_stale_multimedia_intent` verifies a local count followed by stale multimedia rejection. |
| Counter actions accepted longer names than checkpoint variables | Align validated identifier domains; `every_accepted_counter_identifier_can_round_trip_through_checkpoint` prevents accepted but unrestorable state. |
| Old native operation tokens could be observed after process restart | Check process identity before polling/reconciliation/cancellation; dedicated tests ensure no completion or cancellation of a reused token. |
| Uncertain jobs could free queue capacity or be pruned as ordinary terminal history | Retain them until explicit reconciliation; `unresolved_native_operation_keeps_capacity_reserved`. |

The first 24-test adversarial run reproduced two failures (22 passed): revision
rebasing dispatched a stale intent, and a valid 100-character counter name could
not restore. Both cases remain as tests. After corrections, the same 24 tests
passed; subsequent process-identity/reconciliation tests extend that coverage.
The initial busy/pruning findings were corrected before their first test run,
so they are code-review findings with regressions, not claimed observed crashes.

Reproduce from the isolated checkout:

```sh
cargo test --manifest-path show-control/Cargo.toml --test runtime_adversarial
```

The tests also cover priority/FIFO order, partial sequence failure, accepted vs
completed state, repeated cancellation, strict origin/confidence, source recovery
with stale revision, core PID changes, no replay after restoration, conservative
cooldown restoration to a new monotonic epoch, draft-v0 migration, malformed
checkpoint rejection and bounded journal exhaustion.

## Remaining live-integration work

There is no live adapter, OAuth client, audio tap, STT, TTS, soundboard or pack
installer. Authorization scopes and provenance must be verified at the eventual
provider boundary, never inferred from payload text. Final preparation/dispatch
must run on the Production owner because today's public API lacks atomic
expected-revision validation. Native completion needs actual observed tokens and
barriers, and a process restart requires explicit operator reconciliation.

Production sequences conservatively stop on revision changes until an approved
own-mutation receipt contract exists. The runtime is single-owner, not a
concurrent distributed scheduler. Protected H13 files, the running app and device
permissions were outside this audit and untouched by these tests.
