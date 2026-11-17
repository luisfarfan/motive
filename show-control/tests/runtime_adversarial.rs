//! Adversarial tests use a scripted backend, never libobs or the live Motive socket.
use motive_show_control::actions::{
    Action, PreparedAction, ProductionSnapshot, SourceKind, SourceReadiness,
};
use motive_show_control::model::{Error, Event, Payload, Scalar};
use motive_show_control::runtime::{
    Backend, BusyPolicy, Completion, Condition, Config, DispatchOutcome, FailurePolicy, JobState,
    ManualClock, Rule, Runtime, Stage, Trust,
};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

struct ScriptedBackend {
    snapshot: ProductionSnapshot,
    dispatches: Vec<(Action, String)>,
    outcomes: VecDeque<DispatchOutcome>,
    completions: VecDeque<Completion>,
    polls: Vec<String>,
    cancels: Vec<String>,
    simulation: bool,
}
impl Default for ScriptedBackend {
    fn default() -> Self {
        Self {
            snapshot: ProductionSnapshot {
                pid: 7,
                revision: 12,
                active_scene: "program".into(),
                sources: ["a", "b", "c"]
                    .into_iter()
                    .map(|id| (id.into(), SourceReadiness::Ready))
                    .collect(),
                source_kinds: ["a", "b", "c"]
                    .into_iter()
                    .map(|id| (id.into(), SourceKind::Text))
                    .collect(),
                ..ProductionSnapshot::default()
            },
            dispatches: Vec::new(),
            outcomes: VecDeque::new(),
            completions: VecDeque::new(),
            polls: Vec::new(),
            cancels: Vec::new(),
            simulation: false,
        }
    }
}
impl Backend for ScriptedBackend {
    fn snapshot(&self) -> ProductionSnapshot {
        self.snapshot.clone()
    }
    fn simulated(&self) -> bool {
        self.simulation
    }
    fn dispatch(&mut self, action: &PreparedAction, key: &str) -> DispatchOutcome {
        self.dispatches.push((action.action.clone(), key.into()));
        self.outcomes
            .pop_front()
            .unwrap_or(DispatchOutcome::Completed)
    }
    fn poll(&mut self, operation: &str) -> Completion {
        self.polls.push(operation.into());
        self.completions.pop_front().unwrap_or(Completion::Pending)
    }
    fn request_cancel(&mut self, operation: &str) -> Result<(), Error> {
        self.cancels.push(operation.into());
        Ok(())
    }
}
fn rule(id: &str, source: &str, priority: u8) -> Rule {
    Rule {
        id: id.into(),
        enabled: true,
        event_kind: "manual.button_pressed".into(),
        priority,
        conditions: vec![],
        actions: vec![Action::ShowOverlay {
            source_id: source.into(),
        }],
        cooldown_ms: 0,
        debounce_ms: 0,
        timeout_ms: 1000,
        busy_policy: BusyPolicy::Reject,
        failure_policy: FailurePolicy::Stop,
    }
}
fn config(rules: Vec<Rule>) -> Config {
    Config {
        schema_version: 1,
        rules,
        variables: BTreeMap::new(),
        queue_capacity: 16,
        rate_limit: 1000,
        rate_window_ms: 1000,
        max_actions_per_event: 128,
    }
}
fn event(n: u64) -> Event {
    Event {
        schema_version: 1,
        id: format!("event-{n}"),
        origin: "test".into(),
        timestamp_ms: n,
        correlation_id: format!("root-{n}"),
        external_id: None,
        simulated: false,
        payload: Payload::ManualButtonPressed {
            button_id: "test-button".into(),
        },
    }
}
fn trust() -> Trust {
    Trust {
        authorized_origins: BTreeSet::from(["test".into()]),
        ..Trust::default()
    }
}
fn show_ids(backend: &ScriptedBackend) -> Vec<&str> {
    backend
        .dispatches
        .iter()
        .map(|(a, _)| match a {
            Action::ShowOverlay { source_id } => source_id.as_str(),
            _ => panic!("expected overlay action"),
        })
        .collect()
}

#[test]
fn priorities_and_fifo_are_stable_across_multiple_events() {
    let mut backend = ScriptedBackend::default();
    let mut runtime = Runtime::new(
        config(vec![
            rule("low", "a", 1),
            rule("high", "b", 9),
            rule("same", "c", 9),
        ]),
        ManualClock::default(),
    )
    .unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime
        .submit(event(2), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(show_ids(&backend), ["b", "c", "b", "c", "a", "a"]);
    let keys: BTreeSet<_> = backend.dispatches.iter().map(|(_, key)| key).collect();
    assert_eq!(keys.len(), backend.dispatches.len());
}

#[test]
fn queue_admission_is_atomic_and_full_events_do_not_replay() {
    let backend = ScriptedBackend::default();
    let mut cfg = config(vec![rule("first", "a", 1), rule("second", "b", 2)]);
    cfg.queue_capacity = 3;
    let mut runtime = Runtime::new(cfg, ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    assert_eq!(
        runtime
            .submit(event(2), &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "QUEUE_FULL"
    );
    assert_eq!(runtime.jobs.len(), 2);
    assert_eq!(
        runtime
            .submit(event(2), &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "DUPLICATE"
    );
}

#[test]
fn accepted_is_not_completed_and_sequence_waits_for_observation() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "animation-42".into(),
    });
    let mut r = rule("sequence", "a", 1);
    r.actions.push(Action::ShowOverlay {
        source_id: "b".into(),
    });
    let mut runtime = Runtime::new(config(vec![r]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::AwaitingCompletion);
    assert_eq!(runtime.jobs[0].records[0].stage, Stage::Accepted);
    runtime.tick(&mut backend);
    assert_eq!(backend.dispatches.len(), 1);
    backend.completions.push_back(Completion::Completed);
    runtime.tick(&mut backend);
    assert_eq!(backend.dispatches.len(), 2);
    assert_eq!(runtime.jobs[0].state, JobState::Completed);
}

#[test]
fn accepted_timeout_stays_unresolved_and_is_never_redispatched() {
    let clock = ManualClock::default();
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "pending-1".into(),
    });
    let mut runtime = Runtime::new(config(vec![rule("pending", "a", 1)]), clock.clone()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    clock.advance(1000);
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert_ne!(runtime.jobs[0].records[0].stage, Stage::Completed);
    runtime.tick(&mut backend);
    assert_eq!(backend.dispatches.len(), 1);
}

#[test]
fn explicit_reconciliation_observes_old_operation_without_resuming_sequence() {
    let clock = ManualClock::default();
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "pending-1".into(),
    });
    let mut r = rule("pending", "a", 1);
    r.actions.push(Action::ShowOverlay {
        source_id: "b".into(),
    });
    let mut runtime = Runtime::new(config(vec![r]), clock.clone()).unwrap();
    let id = runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap()[0];
    runtime.tick(&mut backend);
    clock.advance(1000);
    runtime.tick(&mut backend);
    backend.completions.push_back(Completion::Completed);
    assert_eq!(
        runtime.reconcile(id, &mut backend).unwrap(),
        JobState::Cancelled
    );
    assert_eq!(runtime.jobs[0].records[0].stage, Stage::Completed);
    runtime.tick(&mut backend);
    assert_eq!(show_ids(&backend), ["a"]);
}

#[test]
fn core_restart_cannot_complete_an_old_operation_with_a_reused_token() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "native-1".into(),
    });
    let mut runtime = Runtime::new(
        config(vec![rule("pending", "a", 1)]),
        ManualClock::default(),
    )
    .unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    backend.snapshot.pid += 1;
    backend.completions.push_back(Completion::Completed);
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert!(backend.polls.is_empty());
    assert_ne!(runtime.jobs[0].records[0].stage, Stage::Completed);
}

#[test]
fn explicit_reconciliation_rejects_operation_from_a_previous_process() {
    let clock = ManualClock::default();
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "native-1".into(),
    });
    let mut runtime = Runtime::new(config(vec![rule("pending", "a", 1)]), clock.clone()).unwrap();
    let id = runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap()[0];
    runtime.tick(&mut backend);
    clock.advance(1000);
    runtime.tick(&mut backend);
    backend.snapshot.pid += 1;
    backend.completions.push_back(Completion::Completed);
    assert!(runtime.reconcile(id, &mut backend).is_err());
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert!(backend.polls.is_empty());
}

#[test]
fn cancellation_never_targets_a_reused_token_in_a_new_process() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "native-1".into(),
    });
    let mut runtime = Runtime::new(
        config(vec![rule("pending", "a", 1)]),
        ManualClock::default(),
    )
    .unwrap();
    let id = runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap()[0];
    runtime.tick(&mut backend);
    backend.snapshot.pid += 1;
    assert!(runtime.cancel(id, &mut backend).is_err());
    assert!(backend.cancels.is_empty());
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
}

#[test]
fn repeated_cancel_sends_one_request_without_claiming_native_cancellation() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "native-7".into(),
    });
    let mut runtime = Runtime::new(
        config(vec![rule("pending", "a", 1)]),
        ManualClock::default(),
    )
    .unwrap();
    let id = runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap()[0];
    runtime.tick(&mut backend);
    runtime.cancel(id, &mut backend).unwrap();
    runtime.cancel(id, &mut backend).unwrap();
    assert_eq!(backend.cancels, ["native-7"]);
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert_ne!(runtime.jobs[0].records[0].stage, Stage::Cancelled);
}

#[test]
fn unresolved_native_operation_keeps_capacity_reserved() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.push_back(DispatchOutcome::Uncertain);
    let mut cfg = config(vec![rule("pending", "a", 1)]);
    cfg.queue_capacity = 1;
    let mut runtime = Runtime::new(cfg, ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::NeedsReconciliation);
    assert_eq!(
        runtime
            .submit(event(2), &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "QUEUE_FULL"
    );
}

#[test]
fn failed_sequence_stops_before_later_mutation_and_retains_result() {
    let mut backend = ScriptedBackend::default();
    backend.outcomes.extend([
        DispatchOutcome::Completed,
        DispatchOutcome::Rejected(Error::new("NATIVE_FAILURE", "fixture rejection")),
    ]);
    let mut r = rule("sequence", "a", 1);
    r.actions = vec![Action::Sequence {
        actions: vec![
            Action::ShowOverlay {
                source_id: "a".into(),
            },
            Action::ShowOverlay {
                source_id: "b".into(),
            },
            Action::ShowOverlay {
                source_id: "c".into(),
            },
        ],
    }];
    let mut runtime = Runtime::new(config(vec![r]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    for _ in 0..4 {
        runtime.tick(&mut backend);
    }
    assert_eq!(show_ids(&backend), ["a", "b"]);
    assert_eq!(runtime.jobs[0].state, JobState::Rejected);
    assert_eq!(runtime.jobs[0].records[0].stage, Stage::Completed);
    assert_eq!(
        runtime.jobs[0].records[1].code.as_deref(),
        Some("NATIVE_FAILURE")
    );
}

#[test]
fn production_busy_obeys_explicit_defer_policy() {
    let clock = ManualClock::default();
    let mut backend = ScriptedBackend::default();
    backend.snapshot.structural_busy = true;
    let mut r = rule("defer", "a", 1);
    r.busy_policy = BusyPolicy::Defer;
    let mut runtime = Runtime::new(config(vec![r]), clock.clone()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::Deferred);
    assert!(backend.dispatches.is_empty());
    clock.advance(1000);
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::TimedOut);
}

#[test]
fn source_recovery_requires_new_revision_review_then_fresh_event() {
    let mut backend = ScriptedBackend::default();
    backend
        .snapshot
        .sources
        .insert("a".into(), SourceReadiness::Recovering);
    let mut r = rule("defer", "a", 1);
    r.busy_policy = BusyPolicy::Defer;
    let mut runtime = Runtime::new(config(vec![r]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::Deferred);
    backend
        .snapshot
        .sources
        .insert("a".into(), SourceReadiness::Ready);
    backend.snapshot.revision += 1;
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs[0].state, JobState::Rejected);
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("STALE_REVISION")
    );
    assert!(backend.dispatches.is_empty());
    runtime
        .submit(event(2), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(backend.dispatches.len(), 1);
}

#[test]
fn process_identity_change_rejects_even_when_revision_matches() {
    let mut backend = ScriptedBackend::default();
    let mut runtime =
        Runtime::new(config(vec![rule("guard", "a", 1)]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    backend.snapshot.pid += 1;
    runtime.tick(&mut backend);
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("STALE_REVISION")
    );
    assert!(backend.dispatches.is_empty());
}

#[test]
fn local_step_does_not_silently_rebase_a_stale_multimedia_intent() {
    let mut backend = ScriptedBackend::default();
    let mut r = rule("mixed", "a", 1);
    r.actions.insert(
        0,
        Action::IncrementCounter {
            name: "local-count".into(),
            amount: 1,
        },
    );
    let mut runtime = Runtime::new(config(vec![r]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    backend.snapshot.revision += 1;
    runtime.tick(&mut backend);
    assert_eq!(runtime.variables["local-count"], Scalar::Int(1));
    runtime.tick(&mut backend);
    assert_eq!(
        runtime.jobs[0].records[1].code.as_deref(),
        Some("STALE_REVISION")
    );
    assert!(backend.dispatches.is_empty());
}

#[test]
fn every_accepted_counter_identifier_can_round_trip_through_checkpoint() {
    let mut backend = ScriptedBackend::default();
    let mut r = rule("counter", "a", 1);
    r.actions = vec![Action::IncrementCounter {
        name: "x".repeat(100),
        amount: 1,
    }];
    match Runtime::new(config(vec![r]), ManualClock::default()) {
        Err(_) => {} // It may be rejected at configuration admission.
        Ok(mut runtime) => {
            runtime
                .submit(event(1), &trust(), &backend.snapshot())
                .unwrap();
            runtime.tick(&mut backend);
            let checkpoint = runtime.checkpoint().unwrap();
            assert!(Runtime::restore(&checkpoint, ManualClock::default()).is_ok());
        }
    }
}

#[test]
fn unknown_and_self_asserted_origin_never_reach_the_backend() {
    let mut backend = ScriptedBackend::default();
    let mut runtime =
        Runtime::new(config(vec![rule("guard", "a", 1)]), ManualClock::default()).unwrap();
    let mut e = event(1);
    e.origin = "viewer-says-owner".into();
    assert_eq!(
        runtime
            .submit(e, &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "UNAUTHORIZED_ORIGIN"
    );
    runtime.tick(&mut backend);
    assert!(backend.dispatches.is_empty());
}

#[test]
fn asserted_voice_confidence_without_trusted_provenance_does_not_match() {
    let backend = ScriptedBackend::default();
    let mut r = rule("voice", "a", 1);
    r.event_kind = "voice.keyword_detected".into();
    r.conditions = vec![Condition::ConfidenceAtLeast { milli: 900 }];
    let mut runtime = Runtime::new(config(vec![r]), ManualClock::default()).unwrap();
    let mut e = event(1);
    e.payload = Payload::VoiceKeywordDetected {
        keyword: "gol".into(),
        confidence_milli: Some(1000),
    };
    assert!(
        runtime
            .submit(e.clone(), &trust(), &backend.snapshot())
            .unwrap()
            .is_empty()
    );
    e.id = "event-2".into();
    e.timestamp_ms = 2;
    e.correlation_id = "root-2".into();
    let mut trusted = trust();
    trusted.confidence_origins.insert("test".into());
    assert_eq!(
        runtime
            .submit(e, &trusted, &backend.snapshot())
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn simulated_event_cannot_dispatch_to_live_backend() {
    let mut backend = ScriptedBackend::default();
    let mut runtime =
        Runtime::new(config(vec![rule("guard", "a", 1)]), ManualClock::default()).unwrap();
    let mut e = event(1);
    e.simulated = true;
    runtime.submit(e, &trust(), &backend.snapshot()).unwrap();
    runtime.tick(&mut backend);
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("SIMULATION_ONLY")
    );
    assert!(backend.dispatches.is_empty());
}

#[test]
fn cycles_keep_lineage_and_stop_without_expanding_forever() {
    let mut backend = ScriptedBackend::default();
    let mut a = rule("manual", "a", 1);
    a.actions = vec![Action::EmitEvent {
        name: "loop".into(),
    }];
    let mut b = rule("loop", "b", 1);
    b.event_kind = "motive.custom_event".into();
    b.actions = vec![Action::EmitEvent {
        name: "loop".into(),
    }];
    let mut runtime = Runtime::new(config(vec![a, b]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    for _ in 0..10 {
        runtime.tick(&mut backend);
    }
    assert_eq!(runtime.jobs.len(), 2);
    assert!(runtime.jobs.iter().all(|j| j.state == JobState::Completed));
    assert!(runtime.decisions.iter().any(|d| d.code == "CYCLE_BLOCKED"));
}

#[test]
fn pruning_during_child_event_cannot_invalidate_dispatch_indices() {
    let mut backend = ScriptedBackend::default();
    let mut emitter = rule("emitter", "b", 0);
    emitter.event_kind = "motive.custom_event".into();
    emitter.conditions = vec![Condition::Equals {
        field: "name".into(),
        value: Scalar::String("emit".into()),
    }];
    emitter.actions = vec![Action::EmitEvent {
        name: "not-matched".into(),
    }];
    let mut runtime = Runtime::new(
        config(vec![rule("high", "a", 9), emitter]),
        ManualClock::default(),
    )
    .unwrap();
    for n in 0..128 {
        runtime
            .submit(event(n), &trust(), &backend.snapshot())
            .unwrap();
        runtime.tick(&mut backend);
    }
    runtime
        .submit(event(128), &trust(), &backend.snapshot())
        .unwrap();
    let mut e = event(129);
    e.payload = Payload::CustomEvent {
        name: "emit".into(),
        fields: BTreeMap::new(),
    };
    let emitter_id = runtime.submit(e, &trust(), &backend.snapshot()).unwrap()[0];
    runtime.tick(&mut backend);
    assert_eq!(
        runtime
            .jobs
            .iter()
            .find(|j| j.id == emitter_id)
            .unwrap()
            .state,
        JobState::Completed
    );
    assert!(runtime.jobs.len() <= 128);
}

#[test]
fn correlated_children_cannot_evade_the_action_budget() {
    let mut backend = ScriptedBackend::default();
    let mut a = rule("manual", "a", 1);
    a.actions = vec![Action::EmitEvent {
        name: "extra".into(),
    }];
    let mut b = rule("extra", "b", 1);
    b.event_kind = "motive.custom_event".into();
    let mut cfg = config(vec![a, b]);
    cfg.max_actions_per_event = 1;
    let mut runtime = Runtime::new(cfg, ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    assert_eq!(runtime.jobs.len(), 1);
    assert_eq!(runtime.jobs[0].state, JobState::Failed);
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("ACTION_LIMIT")
    );
    assert!(backend.dispatches.is_empty());
}

#[test]
fn journal_is_fail_closed_instead_of_silently_forgetting_ids() {
    let backend = ScriptedBackend::default();
    let clock = ManualClock::default();
    let mut runtime = Runtime::new(config(vec![]), clock.clone()).unwrap();
    for n in 0..4096 {
        clock.advance(1000);
        runtime
            .submit(event(n), &trust(), &backend.snapshot())
            .unwrap();
    }
    assert_eq!(
        runtime
            .submit(event(4096), &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "JOURNAL_FULL"
    );
    assert_eq!(
        runtime
            .submit(event(0), &trust(), &backend.snapshot())
            .unwrap_err()
            .code,
        "DUPLICATE"
    );
}

#[test]
fn counter_overflow_is_reported_without_wrapping_or_next_action() {
    let mut backend = ScriptedBackend::default();
    let mut r = rule("count", "a", 1);
    r.actions.insert(
        0,
        Action::IncrementCounter {
            name: "score".into(),
            amount: 1,
        },
    );
    let mut cfg = config(vec![r]);
    cfg.variables.insert("score".into(), Scalar::Int(i64::MAX));
    let mut runtime = Runtime::new(cfg, ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    runtime.tick(&mut backend);
    assert_eq!(runtime.variables["score"], Scalar::Int(i64::MAX));
    assert_eq!(
        runtime.jobs[0].records[0].code.as_deref(),
        Some("COUNTER_OVERFLOW")
    );
    assert!(backend.dispatches.is_empty());
}

#[test]
fn restored_queued_completed_and_uncertain_actions_never_replay() {
    let mut backend = ScriptedBackend::default();
    let mut runtime =
        Runtime::new(config(vec![rule("once", "a", 1)]), ManualClock::default()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    backend.outcomes.push_back(DispatchOutcome::Accepted {
        operation_id: "pending-2".into(),
    });
    runtime
        .submit(event(2), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    runtime
        .submit(event(3), &trust(), &backend.snapshot())
        .unwrap();
    let checkpoint = runtime.checkpoint().unwrap();
    let mut restored = Runtime::restore(&checkpoint, ManualClock::default()).unwrap();
    let before = backend.dispatches.len();
    restored.tick(&mut backend);
    assert_eq!(backend.dispatches.len(), before);
    assert_eq!(restored.jobs[0].state, JobState::Completed);
    assert_eq!(restored.jobs[1].state, JobState::NeedsReconciliation);
    assert_eq!(restored.jobs[2].state, JobState::Cancelled);
    for n in 1..=3 {
        assert_eq!(
            restored
                .submit(event(n), &trust(), &backend.snapshot())
                .unwrap_err()
                .code,
            "DUPLICATE"
        );
    }
}

#[test]
fn cooldown_restores_relative_to_new_monotonic_epoch() {
    let mut backend = ScriptedBackend::default();
    let clock = ManualClock::default();
    clock.advance(20_000);
    let mut r = rule("cooldown", "a", 1);
    r.cooldown_ms = 1000;
    let mut runtime = Runtime::new(config(vec![r]), clock.clone()).unwrap();
    runtime
        .submit(event(1), &trust(), &backend.snapshot())
        .unwrap();
    runtime.tick(&mut backend);
    clock.advance(200);
    let restored_clock = ManualClock::default();
    let mut restored =
        Runtime::restore(&runtime.checkpoint().unwrap(), restored_clock.clone()).unwrap();
    assert!(
        restored
            .submit(event(2), &trust(), &backend.snapshot())
            .unwrap()
            .is_empty()
    );
    restored_clock.advance(799);
    assert!(
        restored
            .submit(event(3), &trust(), &backend.snapshot())
            .unwrap()
            .is_empty()
    );
    restored_clock.advance(1);
    assert_eq!(
        restored
            .submit(event(4), &trust(), &backend.snapshot())
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn draft_v0_migration_retains_consumed_ids_without_inventing_pending_work() {
    let json = serde_json::json!({"schema_version":0,"config":config(vec![rule("rule", "a", 1)]),"variables":{},"consumed_event_ids":["event-1"]}).to_string();
    let mut runtime = Runtime::restore(&json, ManualClock::default()).unwrap();
    assert!(runtime.jobs.is_empty());
    assert_eq!(
        runtime
            .submit(event(1), &trust(), &ScriptedBackend::default().snapshot())
            .unwrap_err()
            .code,
        "DUPLICATE"
    );
}

#[test]
fn checkpoint_rejects_unknown_fields_versions_and_invalid_resource_bounds() {
    let runtime = Runtime::new(config(vec![rule("rule", "a", 1)]), ManualClock::default()).unwrap();
    let original: serde_json::Value = serde_json::from_str(&runtime.checkpoint().unwrap()).unwrap();
    let mut modified = original.clone();
    modified["execute_shell"] = serde_json::json!("ignored would be unsafe");
    assert!(Runtime::restore(&modified.to_string(), ManualClock::default()).is_err());
    modified = original.clone();
    modified["schema_version"] = serde_json::json!(999);
    assert!(Runtime::restore(&modified.to_string(), ManualClock::default()).is_err());
    modified = original.clone();
    modified["cooldown_remaining"] = serde_json::json!({"rule:rule":3_600_001});
    assert!(Runtime::restore(&modified.to_string(), ManualClock::default()).is_err());
    modified = original;
    modified["variables"] = serde_json::json!({"not a safe ID":{"type":"int","value":1}});
    assert!(Runtime::restore(&modified.to_string(), ManualClock::default()).is_err());
}

#[test]
fn duplicate_layer_references_cannot_overwrite_another_scene_in_simulation() {
    use motive_show_control::{packs::CreatorPack, simulation::pack_snapshot};
    let mut pack = CreatorPack::from_json(include_str!("../examples/packs/matchday.json")).unwrap();
    pack.animations.clear();
    pack.scenes[1].layers[0].id = pack.scenes[0].layers[0].id.clone();
    if pack.validate().is_ok() {
        let expected_layers: usize = pack.scenes.iter().map(|scene| scene.layers.len()).sum();
        let snapshot = pack_snapshot(&pack).unwrap();
        assert_eq!(
            snapshot.layers.len(),
            expected_layers,
            "accepted layer references must remain distinct"
        );
    }
}

#[test]
fn mismatched_manual_deck_rule_is_not_reported_as_successfully_simulated() {
    let mut deck: serde_json::Value =
        serde_json::from_str(include_str!("../examples/decks/matchday.json")).unwrap();
    deck["buttons"][0]["id"] = "wrong-goal".into();
    let path = std::env::temp_dir().join(format!(
        "motive-show-deck-mismatch-{}.json",
        std::process::id()
    ));
    std::fs::write(&path, deck.to_string()).unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_motive-show"))
        .args([
            "deck-press",
            path.to_str().unwrap(),
            concat!(env!("CARGO_MANIFEST_DIR"), "/examples/packs/matchday.json"),
            "wrong-goal",
        ])
        .output()
        .unwrap();
    std::fs::remove_file(path).unwrap();
    if output.status.success() {
        let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        let history = report["history"].as_array().unwrap();
        assert_eq!(
            history.last().unwrap()["state"]["state"],
            "rejected",
            "a mismatched rule never ran"
        );
    } else {
        let failure: serde_json::Value = serde_json::from_slice(&output.stderr).unwrap();
        assert_eq!(failure["ok"], false);
        assert!(failure["error"]["code"].is_string());
    }
}
