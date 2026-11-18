//! Contract tests only: this backend represents an owner, not real multimedia.
use motive_show_control::actions::{
    Action, Animation, AnimationKind, Easing, LayerBinding, PreparedAction, ProductionSnapshot,
    Revision, SourceKind, SourceReadiness, WidgetEvent,
};
use motive_show_control::model::{Error, Event, Payload, Scalar};
use motive_show_control::runtime::*;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
struct Owner {
    snapshot: ProductionSnapshot,
    sent: Vec<Revision>,
    asynchronous: bool,
    completion: bool,
    foreign_before_dispatch: bool,
    foreign_during_operation: bool,
    omit_dispatch_receipt: bool,
    omit_terminal_receipt: bool,
    simulated: bool,
    corrupt_receipt: Option<&'static str>,
}
impl Owner {
    fn new() -> Self {
        Self {
            snapshot: ProductionSnapshot {
                pid: 71,
                revision: 10,
                sources: BTreeMap::from([("title".into(), SourceReadiness::Ready)]),
                source_kinds: BTreeMap::from([("title".into(), SourceKind::Text)]),
                ..ProductionSnapshot::default()
            },
            ..Self::default()
        }
    }
    fn receipt(&self, key: &str, before: Revision, operation: Option<&str>) -> MutationReceipt {
        let mut receipt = MutationReceipt {
            action_key: key.into(),
            operation_id: operation.map(str::to_owned),
            before,
            after: self.snapshot.version(),
        };
        match self.corrupt_receipt {
            Some("key") => receipt.action_key = "another-action".into(),
            Some("before") => receipt.before.revision += 1,
            Some("pid") => receipt.after.pid += 1,
            Some("regression") => receipt.after.revision = before.revision - 1,
            Some("operation") => receipt.operation_id = Some("another-operation".into()),
            _ => {}
        }
        receipt
    }
}
impl Backend for Owner {
    fn snapshot(&self) -> ProductionSnapshot {
        self.snapshot.clone()
    }
    fn simulated(&self) -> bool {
        self.simulated
    }
    fn dispatch(&mut self, _: &PreparedAction, _: &str) -> DispatchOutcome {
        panic!("checked owner method required")
    }
    fn poll(&mut self, _: &str) -> Completion {
        panic!("checked owner poll required")
    }
    fn request_cancel(&mut self, _: &str) -> Result<(), Error> {
        Ok(())
    }
    fn dispatch_checked(
        &mut self,
        _: &PreparedAction,
        key: &str,
        expected: Revision,
    ) -> DispatchReport {
        if self.foreign_before_dispatch {
            self.snapshot.revision += 1;
        }
        if self.snapshot.version() != expected {
            return DispatchReport::legacy(DispatchOutcome::Rejected(Error::new(
                "STALE_REVISION",
                "owner guard",
            )));
        }
        self.sent.push(expected);
        self.snapshot.revision += 1;
        let operation = self.asynchronous.then_some("animation-17");
        let outcome =
            operation.map_or(DispatchOutcome::Completed, |op| DispatchOutcome::Accepted {
                operation_id: op.into(),
            });
        DispatchReport {
            outcome,
            receipt: (!self.omit_dispatch_receipt).then(|| self.receipt(key, expected, operation)),
        }
    }
    fn poll_checked(&mut self, operation: &str, key: &str, expected: Revision) -> PollReport {
        if !self.completion {
            return PollReport::legacy(Completion::Pending);
        }
        self.snapshot.revision += 1;
        if self.foreign_during_operation {
            // Terminal observation is valid, but the owner cannot certify a clean revision chain.
            self.snapshot.revision += 1;
            PollReport::legacy(Completion::Completed)
        } else {
            PollReport {
                completion: Completion::Completed,
                receipt: (!self.omit_terminal_receipt)
                    .then(|| self.receipt(key, expected, Some(operation))),
            }
        }
    }
}
fn runtime(owner: &Owner, count: usize) -> Runtime<ManualClock> {
    runtime_actions(
        owner,
        (0..count)
            .map(|_| Action::ShowOverlay {
                source_id: "title".into(),
            })
            .collect(),
    )
}

fn runtime_actions(owner: &Owner, actions: Vec<Action>) -> Runtime<ManualClock> {
    let rule = Rule {
        id: "show".into(),
        enabled: true,
        event_kind: "manual.button_pressed".into(),
        priority: 1,
        conditions: vec![],
        actions,
        cooldown_ms: 0,
        debounce_ms: 0,
        timeout_ms: 1000,
        busy_policy: BusyPolicy::Reject,
        failure_policy: FailurePolicy::Stop,
    };
    let mut runtime = Runtime::new(
        Config {
            schema_version: 1,
            rules: vec![rule],
            variables: BTreeMap::new(),
            queue_capacity: 4,
            rate_limit: 10,
            rate_window_ms: 1000,
            max_actions_per_event: 32,
        },
        ManualClock::default(),
    )
    .unwrap();
    runtime
        .submit(
            Event {
                schema_version: 1,
                id: "button-1".into(),
                origin: "local".into(),
                timestamp_ms: 1,
                correlation_id: "manual-1".into(),
                external_id: None,
                simulated: false,
                payload: Payload::ManualButtonPressed {
                    button_id: "show".into(),
                },
            },
            &Trust {
                authorized_origins: BTreeSet::from(["local".into()]),
                ..Trust::default()
            },
            &owner.snapshot(),
        )
        .unwrap();
    runtime
}

#[test]
fn synchronous_sequence_advances_only_acknowledged_own_revisions() {
    let mut owner = Owner::new();
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    runtime.tick(&mut owner);
    assert_eq!(
        owner.sent.iter().map(|r| r.revision).collect::<Vec<_>>(),
        [10, 11]
    );
    assert_eq!(runtime.jobs[0].state, JobState::Completed);
    assert_eq!(runtime.jobs[0].expected.revision, 12);
    assert_eq!(runtime.jobs[0].records[0].revision_receipts.len(), 1);
}

#[test]
fn concurrent_edit_after_acknowledgment_blocks_next_step() {
    let mut owner = Owner::new();
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    owner.snapshot.revision += 1;
    runtime.tick(&mut owner);
    assert_eq!(owner.sent.len(), 1);
    assert_eq!(runtime.jobs[0].state, JobState::Rejected);
    assert_eq!(
        runtime.jobs[0].records[1].code.as_deref(),
        Some("STALE_REVISION")
    );
    assert_eq!(runtime.jobs[0].expected.revision, 11);
}

#[test]
fn owner_checks_revision_again_at_dispatch() {
    let mut owner = Owner::new();
    owner.foreign_before_dispatch = true;
    let mut runtime = runtime(&owner, 1);
    runtime.tick(&mut owner);
    assert!(owner.sent.is_empty());
    assert_eq!(runtime.jobs[0].state, JobState::Rejected);
}

#[test]
fn invalid_receipt_never_retries_or_rebases() {
    for corruption in ["key", "before", "pid", "regression", "operation"] {
        let mut owner = Owner::new();
        owner.corrupt_receipt = Some(corruption);
        let mut runtime = runtime(&owner, 2);
        runtime.tick(&mut owner);
        runtime.tick(&mut owner);
        assert_eq!(owner.sent.len(), 1, "{corruption}");
        assert_eq!(
            runtime.jobs[0].state,
            JobState::NeedsReconciliation,
            "{corruption}"
        );
        assert_eq!(runtime.jobs[0].expected.revision, 10);
        assert_eq!(
            runtime.jobs[0].records[0].code.as_deref(),
            Some("INVALID_MUTATION_RECEIPT")
        );
    }
}

#[test]
fn async_sequence_waits_for_terminal_receipt_then_advances_chain() {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    runtime.tick(&mut owner);
    assert_eq!(runtime.jobs[0].state, JobState::AwaitingCompletion);
    assert_eq!(owner.sent.len(), 1);
    owner.completion = true;
    runtime.tick(&mut owner);
    assert_eq!(
        owner.sent.iter().map(|r| r.revision).collect::<Vec<_>>(),
        [10, 12]
    );
    assert_eq!(runtime.jobs[0].records[0].revision_receipts.len(), 2);
}

#[test]
fn terminal_observation_with_foreign_revision_does_not_rebase() {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    owner.completion = true;
    owner.foreign_during_operation = true;
    runtime.tick(&mut owner);
    assert_eq!(owner.sent.len(), 1);
    assert_eq!(runtime.jobs[0].records[0].stage, Stage::Completed);
    assert_eq!(runtime.jobs[0].state, JobState::Rejected);
    assert_eq!(runtime.jobs[0].expected.revision, 11);
}

#[test]
fn bad_terminal_operation_receipt_retains_uncertainty() {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    owner.completion = true;
    owner.corrupt_receipt = Some("operation");
    runtime.tick(&mut owner);
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert_eq!(
        runtime.jobs[0].records[0].operation_id.as_deref(),
        Some("animation-17")
    );
    assert_eq!(owner.sent.len(), 1);
}

#[test]
fn receipt_checkpoint_is_explicit_v2_and_restore_never_resumes() {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    let serialized = runtime.checkpoint().unwrap();
    let value: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    assert_eq!(value["schema_version"], 2);
    let mut restored = Runtime::restore(&serialized, ManualClock::default()).unwrap();
    restored.tick(&mut owner);
    assert_eq!(restored.jobs[0].state, JobState::NeedsReconciliation);
    assert_eq!(owner.sent.len(), 1);
    let mut old_version = value;
    old_version["schema_version"] = 1.into();
    assert!(Runtime::restore(&old_version.to_string(), ManualClock::default()).is_err());
}

#[test]
fn explicit_reconciliation_does_not_resume_next_step_even_with_owned_receipt() {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    let mut runtime = runtime(&owner, 2);
    runtime.tick(&mut owner);
    runtime.cancel(1, &mut owner).unwrap();
    owner.completion = true;
    assert_eq!(
        runtime.reconcile(1, &mut owner).unwrap(),
        JobState::Cancelled
    );
    runtime.tick(&mut owner);
    assert_eq!(owner.sent.len(), 1);
}

fn animated_owner() -> Owner {
    let mut owner = Owner::new();
    owner.asynchronous = true;
    owner.snapshot.active_scene = "live".into();
    owner
        .snapshot
        .source_kinds
        .insert("title".into(), SourceKind::Alert);
    owner
        .snapshot
        .scenes
        .insert("live".into(), vec!["title".into()]);
    owner.snapshot.layers.insert(
        "title-layer".into(),
        LayerBinding {
            scene_id: "live".into(),
            source_id: "title".into(),
        },
    );
    owner
}

fn entrance() -> Animation {
    Animation {
        kind: AnimationKind::ScaleIn,
        easing: Easing::EaseOut,
        duration_ms: 500,
        distance: 0.,
        scale_from: 0.5,
    }
}

fn animated_trigger() -> Action {
    Action::TriggerAnimatedWidget {
        source_id: "title".into(),
        scene_id: "live".into(),
        layer_id: "title-layer".into(),
        animation: entrance(),
    }
}

fn followed_by_counter(action: Action) -> Vec<Action> {
    vec![
        action,
        Action::IncrementCounter {
            name: "goals".into(),
            amount: 1,
        },
    ]
}

#[test]
fn animated_trigger_with_both_receipts_runs_following_counter_once() {
    let mut owner = animated_owner();
    let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
    runtime.tick(&mut owner);
    runtime.tick(&mut owner); // Pending without a receipt is permitted.
    assert_eq!(runtime.jobs[0].state, JobState::AwaitingCompletion);
    assert!(!runtime.variables.contains_key("goals"));
    owner.completion = true;
    runtime.tick(&mut owner);
    runtime.tick(&mut owner);
    assert_eq!(owner.sent.len(), 1);
    assert_eq!(runtime.jobs[0].state, JobState::Completed);
    assert_eq!(runtime.jobs[0].expected.revision, 12);
    assert_eq!(runtime.jobs[0].records[0].revision_receipts.len(), 2);
    assert_eq!(runtime.variables.get("goals"), Some(&Scalar::Int(1)));
}

#[test]
fn animated_trigger_without_dispatch_receipt_keeps_uncertain_identity_and_never_retries() {
    for asynchronous in [true, false] {
        let mut owner = animated_owner();
        owner.asynchronous = asynchronous;
        owner.omit_dispatch_receipt = true;
        let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
        runtime.tick(&mut owner);
        runtime.tick(&mut owner);
        let job = &runtime.jobs[0];
        assert_eq!(owner.sent.len(), 1);
        assert_eq!(job.state, JobState::NeedsReconciliation);
        assert_eq!(job.expected.revision, 10);
        assert_eq!(job.cursor, 0);
        assert_eq!(job.records.len(), 1);
        assert_eq!(job.records[0].stage, Stage::Uncertain);
        assert_eq!(
            job.records[0].code.as_deref(),
            Some("MISSING_MUTATION_RECEIPT")
        );
        assert_eq!(
            job.records[0].operation_id.as_deref(),
            asynchronous.then_some("animation-17")
        );
        assert!(job.records[0].revision_receipts.is_empty());
        assert!(!runtime.variables.contains_key("goals"));
    }
}

#[test]
fn animated_trigger_without_terminal_receipt_blocks_counter_and_reconciliation_rebase() {
    for foreign in [false, true] {
        let mut owner = animated_owner();
        let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
        runtime.tick(&mut owner);
        owner.completion = true;
        owner.foreign_during_operation = foreign;
        owner.omit_terminal_receipt = true;
        runtime.tick(&mut owner);
        runtime.tick(&mut owner);
        assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
        assert_eq!(runtime.jobs[0].records[0].stage, Stage::Uncertain);
        assert_eq!(
            runtime.jobs[0].records[0].code.as_deref(),
            Some("MISSING_MUTATION_RECEIPT")
        );
        assert_eq!(
            runtime.jobs[0].records[0].operation_id.as_deref(),
            Some("animation-17")
        );
        assert_eq!(runtime.jobs[0].expected.revision, 11);
        assert_eq!(
            runtime.reconcile(1, &mut owner).unwrap(),
            JobState::NeedsReconciliation
        );
        assert_eq!(runtime.jobs[0].expected.revision, 11);
        assert_eq!(runtime.jobs[0].records[0].revision_receipts.len(), 1);
        assert_eq!(runtime.jobs[0].cursor, 0);
        assert_eq!(owner.sent.len(), 1);
        assert!(!runtime.variables.contains_key("goals"));
    }
}

#[test]
fn missing_dispatch_receipt_cannot_be_reconciled_by_a_bare_terminal_observation() {
    let mut owner = animated_owner();
    owner.omit_dispatch_receipt = true;
    owner.omit_terminal_receipt = true;
    let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
    runtime.tick(&mut owner);
    owner.completion = true;
    assert_eq!(
        runtime.reconcile(1, &mut owner).unwrap(),
        JobState::NeedsReconciliation
    );
    assert_eq!(runtime.jobs[0].expected.revision, 10);
    assert_eq!(runtime.jobs[0].records[0].stage, Stage::Uncertain);
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("MISSING_MUTATION_RECEIPT")
    );
    assert_eq!(
        runtime.jobs[0].records[0].operation_id.as_deref(),
        Some("animation-17")
    );
    assert!(runtime.jobs[0].records[0].revision_receipts.is_empty());
    assert_eq!(owner.sent.len(), 1);
    assert!(!runtime.variables.contains_key("goals"));
}

#[test]
fn animated_trigger_invalid_terminal_receipts_preserve_existing_identity_guards() {
    for corruption in ["key", "before", "pid", "regression", "operation"] {
        let mut owner = animated_owner();
        let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
        runtime.tick(&mut owner);
        owner.completion = true;
        owner.corrupt_receipt = Some(corruption);
        runtime.tick(&mut owner);
        runtime.tick(&mut owner);
        assert_eq!(
            runtime.jobs[0].state,
            JobState::NeedsReconciliation,
            "{corruption}"
        );
        assert_eq!(
            runtime.jobs[0].records[0].code.as_deref(),
            Some("INVALID_MUTATION_RECEIPT")
        );
        assert_eq!(
            runtime.jobs[0].records[0].operation_id.as_deref(),
            Some("animation-17")
        );
        assert_eq!(runtime.jobs[0].expected.revision, 11);
        assert_eq!(owner.sent.len(), 1);
        assert!(!runtime.variables.contains_key("goals"));
    }
}

#[test]
fn legacy_widget_and_animation_keep_receipt_optional_before_local_counter() {
    for action in [
        Action::Widget {
            source_id: "title".into(),
            event: WidgetEvent::Trigger,
        },
        Action::Animate {
            scene_id: "live".into(),
            layer_id: "title-layer".into(),
            animation: entrance(),
        },
    ] {
        let mut owner = animated_owner();
        owner.omit_dispatch_receipt = true;
        owner.omit_terminal_receipt = true;
        let mut runtime = runtime_actions(&owner, followed_by_counter(action));
        runtime.tick(&mut owner);
        assert_eq!(runtime.jobs[0].state, JobState::AwaitingCompletion);
        owner.completion = true;
        runtime.tick(&mut owner);
        assert_eq!(runtime.jobs[0].state, JobState::Completed);
        assert_eq!(runtime.jobs[0].expected.revision, 10);
        assert_eq!(runtime.variables.get("goals"), Some(&Scalar::Int(1)));
        assert_eq!(owner.sent.len(), 1);
    }
}

#[test]
fn simulated_animated_trigger_does_not_require_owner_receipts() {
    let mut owner = animated_owner();
    owner.simulated = true;
    owner.omit_dispatch_receipt = true;
    owner.omit_terminal_receipt = true;
    let mut runtime = runtime_actions(&owner, followed_by_counter(animated_trigger()));
    runtime.tick(&mut owner);
    owner.completion = true;
    runtime.tick(&mut owner);
    assert_eq!(runtime.jobs[0].state, JobState::Simulated);
    assert_eq!(runtime.variables.get("goals"), Some(&Scalar::Int(1)));
    assert_eq!(runtime.jobs[0].records[1].stage, Stage::Simulated);
    assert_eq!(owner.sent.len(), 1);
}
