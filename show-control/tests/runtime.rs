use motive_show_control::{actions::*, model::*, runtime::*, simulation::*};
use std::collections::BTreeMap;

fn button(id: &str) -> Event {
    event(
        id,
        Payload::ManualButtonPressed {
            button_id: "goal".into(),
        },
    )
}
fn base(actions: Vec<Action>) -> Config {
    let mut c = demo_config();
    c.rules = vec![rule("test", "manual.button_pressed", actions)];
    c
}
fn notification() -> Action {
    Action::Notify {
        message: "controlled test".into(),
    }
}
fn drain(r: &mut Runtime<ManualClock>, b: &mut Simulator) {
    for _ in 0..40 {
        r.tick(b);
    }
}

#[test]
fn scenarios_are_simulation_with_duplicate_cooldown_and_unsupported_sound_evidence() {
    let goal = scenario("goal").unwrap();
    assert_eq!(goal.mode, "simulation_only");
    assert_eq!(goal.live_commands_sent, 0);
    assert_eq!(goal.admissions[1].error.as_ref().unwrap().code, "DUPLICATE");
    assert!(goal.decisions.iter().any(|d| d.code == "COOLDOWN"));
    assert_eq!(goal.variables["goals"], Scalar::Int(1));
    assert!(
        goal.jobs[0]
            .records
            .iter()
            .any(|r| r.code.as_deref() == Some("CAPABILITY_UNAVAILABLE"))
    );
    assert!(goal.jobs.iter().all(|j| j.state == JobState::Simulated));
    let donation = scenario("donation").unwrap();
    assert!(
        donation.jobs[0]
            .actions
            .iter()
            .any(|a| matches!(a, Action::PrepareSpeech { .. }))
    );
    let chat = scenario("chat").unwrap();
    assert!(chat.admissions[0].jobs.is_empty());
    assert_eq!(chat.admissions[1].jobs.len(), 1);
    assert!(chat.admissions[2].jobs.is_empty());
    let burst = scenario("burst").unwrap();
    assert_eq!(burst.jobs[0].state, JobState::Cancelled);
    assert_eq!(
        burst
            .admissions
            .iter()
            .filter(|a| a.error.is_some())
            .count(),
        4
    );
}
#[test]
fn equality_phrase_numeric_variable_counter_production_and_trust_are_anded() {
    let mut c = base(vec![notification()]);
    c.rules[0].event_kind = "viewer.donation".into();
    c.variables.insert("enabled".into(), Scalar::Bool(true));
    c.rules[0].conditions = vec![
        Condition::Equals {
            field: "kind".into(),
            value: Scalar::String("viewer.donation".into()),
        },
        Condition::Numeric {
            field: "amount_minor".into(),
            comparison: Comparison::GreaterEqual,
            value: 100,
        },
        Condition::Contains {
            field: "message".into(),
            phrase: "great game".into(),
            whole_word: true,
        },
        Condition::Variable {
            name: "enabled".into(),
            value: Scalar::Bool(true),
        },
        Condition::Counter {
            name: "goals".into(),
            comparison: Comparison::Equal,
            value: 0,
        },
        Condition::ProductionActive { active: false },
        Condition::AuthorizedOrigin,
        Condition::AuthorizedUser,
    ];
    let mut r = Runtime::new(c, ManualClock::default()).unwrap();
    let s = fixture_snapshot();
    let make = |id: &str, message: &str| {
        event(
            id,
            Payload::ViewerDonation {
                user_id: "creator".into(),
                amount_minor: 200,
                currency: "USD".into(),
                message: message.into(),
            },
        )
    };
    assert!(
        r.submit(make("bad", "great gameplay"), &trust(), &s)
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        r.submit(make("good", "A GREAT game!"), &trust(), &s)
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn confidence_in_payload_does_not_create_verified_provenance() {
    let mut t = trust();
    t.confidence_origins.clear();
    let mut r = Runtime::new(demo_config(), ManualClock::default()).unwrap();
    assert!(
        r.submit(
            event(
                "voice",
                Payload::VoiceKeywordDetected {
                    keyword: "gol".into(),
                    confidence_milli: Some(1000)
                }
            ),
            &t,
            &fixture_snapshot()
        )
        .unwrap()
        .is_empty()
    );
    assert_eq!(
        r.submit(button("untrusted"), &Trust::default(), &fixture_snapshot())
            .unwrap_err()
            .code,
        "UNAUTHORIZED_ORIGIN"
    );
}
#[test]
fn disabled_debounce_cooldown_and_rate_boundaries_use_monotonic_clock() {
    let clock = ManualClock::default();
    let mut c = base(vec![notification()]);
    c.rules[0].debounce_ms = 20;
    c.rules[0].cooldown_ms = 100;
    c.rate_limit = 4;
    c.rate_window_ms = 1000;
    let mut r = Runtime::new(c, clock.clone()).unwrap();
    let s = fixture_snapshot();
    assert_eq!(r.submit(button("a"), &trust(), &s).unwrap().len(), 1);
    assert!(r.submit(button("b"), &trust(), &s).unwrap().is_empty());
    assert_eq!(r.decisions.back().unwrap().code, "DEBOUNCED");
    clock.advance(20);
    assert!(r.submit(button("c"), &trust(), &s).unwrap().is_empty());
    assert_eq!(r.decisions.back().unwrap().code, "COOLDOWN");
    clock.advance(80);
    assert_eq!(r.submit(button("d"), &trust(), &s).unwrap().len(), 1);
    assert_eq!(
        r.submit(button("e"), &trust(), &s).unwrap_err().code,
        "RATE_LIMITED"
    );
    clock.advance(900);
    r.config.rules[0].enabled = false;
    assert!(r.submit(button("f"), &trust(), &s).unwrap().is_empty());
    assert_eq!(r.decisions.back().unwrap().code, "DISABLED");
}
#[test]
fn shared_cooldown_is_reserved_by_priority_inside_one_event() {
    let mut c = base(vec![notification()]);
    c.rules[0].conditions = vec![Condition::Cooldown {
        key: "exclusive".into(),
        duration_ms: 500,
    }];
    let mut high = c.rules[0].clone();
    high.id = "high".into();
    high.priority = 9;
    c.rules.push(high);
    let mut r = Runtime::new(c, ManualClock::default()).unwrap();
    let ids = r
        .submit(button("shared"), &trust(), &fixture_snapshot())
        .unwrap();
    assert_eq!(ids.len(), 1);
    assert_eq!(r.jobs[0].rule_id, "high");
}
#[test]
fn unknown_schema_extra_fields_and_invalid_config_limits_fail_closed() {
    let mut c = base(vec![notification()]);
    c.schema_version = 2;
    assert_eq!(c.validate().unwrap_err().code, "UNKNOWN_SCHEMA");
    c.schema_version = 1;
    let mut v = serde_json::to_value(&c).unwrap();
    v["shell"] = serde_json::json!("anything");
    assert!(Config::from_json(&v.to_string()).is_err());
    for capacity in [0, 257, usize::MAX] {
        c.queue_capacity = capacity;
        assert!(c.validate().is_err());
    }
    assert!(Config::from_json("not json").is_err());
}
#[test]
fn event_time_order_and_external_dedup_are_independent_of_monotonic_timeout() {
    let mut r = Runtime::new(base(vec![notification()]), ManualClock::default()).unwrap();
    let mut a = button("a");
    a.external_id = Some("delivery-1".into());
    r.submit(a.clone(), &trust(), &fixture_snapshot()).unwrap();
    a.id = "b".into();
    assert_eq!(
        r.submit(a, &trust(), &fixture_snapshot()).unwrap_err().code,
        "DUPLICATE"
    );
    let mut c = button("c");
    c.timestamp_ms = 999;
    assert_eq!(
        r.submit(c, &trust(), &fixture_snapshot()).unwrap_err().code,
        "OUT_OF_ORDER"
    );
}
#[test]
fn strict_sequence_failure_stops_later_counter_without_rollback_claim() {
    let mut r = Runtime::new(
        base(vec![Action::Sequence {
            actions: vec![
                Action::IncrementCounter {
                    name: "before".into(),
                    amount: 1,
                },
                Action::Sound {
                    resource: "missing".into(),
                },
                Action::IncrementCounter {
                    name: "after".into(),
                    amount: 1,
                },
            ],
        }]),
        ManualClock::default(),
    )
    .unwrap();
    let mut b = Simulator {
        observed: fixture_snapshot(),
        ..Simulator::default()
    };
    r.submit(button("sequence"), &trust(), &b.snapshot())
        .unwrap();
    drain(&mut r, &mut b);
    assert_eq!(r.variables["before"], Scalar::Int(1));
    assert!(!r.variables.contains_key("after"));
    assert_eq!(r.jobs[0].state, JobState::Rejected);
}
#[test]
fn counter_overflow_fails_without_wrapping_or_changing_value() {
    let mut c = base(vec![Action::IncrementCounter {
        name: "count".into(),
        amount: 1,
    }]);
    c.variables.insert("count".into(), Scalar::Int(i64::MAX));
    let mut r = Runtime::new(c, ManualClock::default()).unwrap();
    let mut b = Simulator {
        observed: fixture_snapshot(),
        ..Simulator::default()
    };
    r.submit(button("overflow"), &trust(), &b.snapshot())
        .unwrap();
    drain(&mut r, &mut b);
    assert_eq!(r.variables["count"], Scalar::Int(i64::MAX));
    assert_eq!(
        r.jobs[0].records[0].code.as_deref(),
        Some("COUNTER_OVERFLOW")
    );
}
#[test]
fn restart_preserves_consumed_ids_counters_cooldown_and_cancels_unexecuted_jobs() {
    let clock = ManualClock::default();
    let mut c = base(vec![Action::IncrementCounter {
        name: "goals".into(),
        amount: 1,
    }]);
    c.rules[0].cooldown_ms = 1000;
    let mut r = Runtime::new(c, clock.clone()).unwrap();
    let mut b = Simulator {
        observed: fixture_snapshot(),
        ..Simulator::default()
    };
    r.submit(button("first"), &trust(), &b.snapshot()).unwrap();
    drain(&mut r, &mut b);
    clock.advance(300);
    let next = ManualClock::default();
    let mut restored = Runtime::restore(&r.checkpoint().unwrap(), next.clone()).unwrap();
    assert_eq!(restored.variables["goals"], Scalar::Int(1));
    assert_eq!(
        restored
            .submit(button("first"), &trust(), &b.snapshot())
            .unwrap_err()
            .code,
        "DUPLICATE"
    );
    assert!(
        restored
            .submit(button("second"), &trust(), &b.snapshot())
            .unwrap()
            .is_empty()
    );
    next.advance(700);
    assert_eq!(
        restored
            .submit(button("third"), &trust(), &b.snapshot())
            .unwrap()
            .len(),
        1
    );
    let mut twice =
        Runtime::restore(&restored.checkpoint().unwrap(), ManualClock::default()).unwrap();
    drain(&mut twice, &mut b);
    assert_eq!(twice.variables["goals"], Scalar::Int(1));
    assert_eq!(twice.jobs.last().unwrap().state, JobState::Cancelled);
}
#[test]
fn draft_migration_is_distinct_from_motive_project_and_validated() {
    let old = serde_json::json!({"schema_version":0,"config":base(vec![notification()]),"variables":{"goals":{"type":"int","value":2}},"consumed_event_ids":["old"]});
    let mut r = Runtime::restore(&old.to_string(), ManualClock::default()).unwrap();
    assert_eq!(r.variables["goals"], Scalar::Int(2));
    assert_eq!(
        r.submit(button("old"), &trust(), &fixture_snapshot())
            .unwrap_err()
            .code,
        "DUPLICATE"
    );
    assert!(Runtime::restore("{\"schema_version\":4}", ManualClock::default()).is_err());
    let mut malformed: serde_json::Value = serde_json::from_str(&r.checkpoint().unwrap()).unwrap();
    malformed["config"]["queue_capacity"] = serde_json::json!(0);
    assert!(Runtime::restore(&malformed.to_string(), ManualClock::default()).is_err());
}
#[test]
fn cycle_protection_preserves_one_root_budget() {
    let mut c = base(vec![Action::EmitEvent {
        name: "again".into(),
    }]);
    let mut cycle = rule(
        "cycle",
        "motive.custom_event",
        vec![Action::EmitEvent {
            name: "again".into(),
        }],
    );
    cycle.conditions = vec![Condition::Equals {
        field: "name".into(),
        value: Scalar::String("again".into()),
    }];
    c.rules.push(cycle);
    let mut r = Runtime::new(c, ManualClock::default()).unwrap();
    let mut b = Simulator {
        observed: fixture_snapshot(),
        ..Simulator::default()
    };
    r.submit(button("start"), &trust(), &b.snapshot()).unwrap();
    drain(&mut r, &mut b);
    assert_eq!(r.jobs.len(), 2);
    assert!(r.decisions.iter().any(|d| d.code == "CYCLE_BLOCKED"));
}
#[test]
fn json_event_cannot_inject_origin_trust_or_native_commands() {
    let mut e = serde_json::to_value(button("safe")).unwrap();
    e["authorized"] = serde_json::json!(true);
    assert!(Event::from_json(&e.to_string()).is_err());
    let e = event(
        "custom",
        Payload::CustomEvent {
            name: "mcp".into(),
            fields: BTreeMap::from([("command".into(), Scalar::String("rm -rf /".into()))]),
        },
    );
    let r = run_events(
        "custom",
        base(vec![notification()]),
        vec![e],
        fixture_snapshot(),
    )
    .unwrap();
    assert!(r.jobs.is_empty());
    assert!(r.planned_dispatches.is_empty());
}
