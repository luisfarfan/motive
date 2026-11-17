//! Synthetic evidence only. This module does not import Motive or open its socket.
use crate::actions::*;
use crate::model::{Error, Event, Payload, Scalar};
use crate::packs::{CreatorPack, VisualDefinition, WidgetKind};
use crate::runtime::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlannedDispatch {
    pub idempotency_key: String,
    pub prepared: PreparedAction,
}
#[derive(Default)]
pub struct Simulator {
    pub observed: ProductionSnapshot,
    pub dispatches: Vec<PlannedDispatch>,
}
impl Backend for Simulator {
    fn snapshot(&self) -> ProductionSnapshot {
        self.observed.clone()
    }
    fn simulated(&self) -> bool {
        true
    }
    fn dispatch(&mut self, action: &PreparedAction, key: &str) -> DispatchOutcome {
        self.dispatches.push(PlannedDispatch {
            idempotency_key: key.into(),
            prepared: action.clone(),
        });
        DispatchOutcome::Simulated
    }
    fn poll(&mut self, _: &str) -> Completion {
        Completion::Unknown
    }
    fn request_cancel(&mut self, _: &str) -> Result<(), Error> {
        Err(Error::new("SIMULATION_ONLY", "no live operation exists"))
    }
}
pub fn pack_snapshot(pack: &CreatorPack) -> Result<ProductionSnapshot, Error> {
    pack.validate()?;
    let mut snapshot = ProductionSnapshot {
        pid: 0,
        revision: 1,
        active_scene: pack
            .scenes
            .first()
            .map(|s| s.id.clone())
            .unwrap_or_default(),
        ..ProductionSnapshot::default()
    };
    for source in &pack.overlays {
        snapshot
            .sources
            .insert(source.id.clone(), SourceReadiness::Ready);
        let kind = match &source.definition {
            VisualDefinition::Text { .. } => SourceKind::Text,
            VisualDefinition::Shape { .. } => SourceKind::Shape,
            VisualDefinition::Image { .. } => SourceKind::Image,
            VisualDefinition::Video { .. } => SourceKind::Video,
            VisualDefinition::Widget { widget } => match widget.kind {
                WidgetKind::Countdown => SourceKind::Countdown,
                WidgetKind::Alert => SourceKind::Alert,
                WidgetKind::LowerThird => SourceKind::LowerThird,
            },
        };
        snapshot.source_kinds.insert(source.id.clone(), kind);
        if let VisualDefinition::Text { .. } = &source.definition {
            let mut value = serde_json::to_value(&source.definition)
                .map_err(|_| Error::new("FIXTURE", "text fixture failed"))?;
            value.as_object_mut().unwrap().remove("kind");
            snapshot.text_definitions.insert(
                source.id.clone(),
                serde_json::from_value(value)
                    .map_err(|_| Error::new("FIXTURE", "text fixture incompatible with H12"))?,
            );
        }
    }
    for scene in &pack.scenes {
        snapshot.scenes.insert(
            scene.id.clone(),
            scene.layers.iter().map(|l| l.overlay_id.clone()).collect(),
        );
        for layer in &scene.layers {
            snapshot.layers.insert(
                layer.id.clone(),
                LayerBinding {
                    scene_id: scene.id.clone(),
                    source_id: layer.overlay_id.clone(),
                },
            );
        }
    }
    Ok(snapshot)
}
/// Resolve declarative rule references offline; never binds symbolic IDs to a real core.
pub fn validate_pack_rules(pack: &CreatorPack, config: &Config) -> Result<(), Error> {
    pack.validate()?;
    config.validate()?;
    let snapshot = pack_snapshot(pack)?;
    for id in &pack.rule_ids {
        let rule = config.rules.iter().find(|r| r.id == *id).ok_or_else(|| {
            Error::new(
                "PACK_RULE_MISSING",
                "declared rule is not in the loaded configuration",
            )
        })?;
        if !pack.events.contains(&rule.event_kind) {
            return Err(Error::new(
                "PACK_EVENT_MISSING",
                "rule uses an undeclared event kind",
            ));
        }
        for action in &rule.actions {
            for leaf in action.flattened()? {
                match leaf {
                    Action::ShowOverlay { source_id }
                    | Action::HideOverlay { source_id }
                    | Action::Widget { source_id, .. }
                    | Action::CountdownStart { source_id }
                    | Action::CountdownReset { source_id }
                    | Action::UpdateText { source_id, .. }
                        if !snapshot.sources.contains_key(&source_id) =>
                    {
                        return Err(Error::new(
                            "PACK_SOURCE_MISSING",
                            "rule target is absent from the pack",
                        ));
                    }
                    Action::SelectScene { scene_id, .. }
                        if !snapshot.scenes.contains_key(&scene_id) =>
                    {
                        return Err(Error::new(
                            "PACK_SCENE_MISSING",
                            "rule target scene is absent from the pack",
                        ));
                    }
                    Action::Animate {
                        scene_id, layer_id, ..
                    } if snapshot
                        .layers
                        .get(&layer_id)
                        .is_none_or(|layer| layer.scene_id != scene_id) =>
                    {
                        return Err(Error::new(
                            "PACK_LAYER_MISSING",
                            "rule target layer is absent from the pack scene",
                        ));
                    }
                    _ => {}
                }
            }
        }
    }
    Ok(())
}
pub fn fixture_snapshot() -> ProductionSnapshot {
    let mut s = ProductionSnapshot {
        pid: 0,
        revision: 1,
        active_scene: "match-live".into(),
        ..ProductionSnapshot::default()
    };
    for (id, kind) in [
        ("goal-celebration", SourceKind::Alert),
        ("community-alert", SourceKind::Alert),
        ("match-clock", SourceKind::Countdown),
    ] {
        s.sources.insert(id.into(), SourceReadiness::Ready);
        s.source_kinds.insert(id.into(), kind);
    }
    s.scenes
        .insert("match-live".into(), vec!["goal-celebration".into()]);
    s.scenes
        .insert("match-brb".into(), vec!["match-clock".into()]);
    s
}
pub fn trust() -> Trust {
    Trust {
        authorized_origins: BTreeSet::from([
            "simulator".into(),
            "deck".into(),
            "simulation.donations".into(),
        ]),
        authorized_users: BTreeSet::from(["creator".into()]),
        confidence_origins: BTreeSet::from(["simulator".into()]),
    }
}
pub fn event(id: &str, payload: Payload) -> Event {
    Event {
        schema_version: 1,
        id: id.into(),
        origin: "simulator".into(),
        timestamp_ms: 1000,
        correlation_id: id.into(),
        external_id: None,
        simulated: true,
        payload,
    }
}
pub fn rule(id: &str, kind: &str, actions: Vec<Action>) -> Rule {
    Rule {
        id: id.into(),
        enabled: true,
        event_kind: kind.into(),
        priority: 5,
        conditions: Vec::new(),
        actions,
        cooldown_ms: 0,
        debounce_ms: 0,
        timeout_ms: 5000,
        busy_policy: BusyPolicy::Reject,
        failure_policy: FailurePolicy::Stop,
    }
}
pub fn demo_config() -> Config {
    let mut goal = rule(
        "goal-celebration",
        "voice.keyword_detected",
        vec![
            Action::Widget {
                source_id: "goal-celebration".into(),
                event: WidgetEvent::Trigger,
            },
            Action::Sound {
                resource: "stadium-cheer".into(),
            },
            Action::IncrementCounter {
                name: "goals".into(),
                amount: 1,
            },
        ],
    );
    goal.conditions = vec![
        Condition::Contains {
            field: "keyword".into(),
            phrase: "gol".into(),
            whole_word: true,
        },
        Condition::ConfidenceAtLeast { milli: 800 },
    ];
    goal.cooldown_ms = 3000;
    goal.failure_policy = FailurePolicy::ContinueUnavailable;
    let mut donation = rule(
        "donation-alert",
        "viewer.donation",
        vec![
            Action::Widget {
                source_id: "community-alert".into(),
                event: WidgetEvent::Trigger,
            },
            Action::PrepareSpeech {
                text: "Thank you for supporting this local demo. Speech is not synthesized.".into(),
            },
        ],
    );
    donation.conditions = vec![Condition::Numeric {
        field: "amount_minor".into(),
        comparison: Comparison::GreaterEqual,
        value: 100,
    }];
    let mut chat = rule(
        "brb-authorized",
        "chat.command",
        vec![Action::SelectScene {
            scene_id: "match-brb".into(),
            transition: Transition {
                kind: TransitionKind::Fade,
                duration_ms: 400,
            },
        }],
    );
    chat.conditions = vec![
        Condition::Equals {
            field: "command".into(),
            value: Scalar::String("brb".into()),
        },
        Condition::AuthorizedUser,
    ];
    chat.cooldown_ms = 3000;
    let mut button = rule(
        "deck-goal",
        "manual.button_pressed",
        vec![
            Action::Widget {
                source_id: "goal-celebration".into(),
                event: WidgetEvent::Trigger,
            },
            Action::IncrementCounter {
                name: "goals".into(),
                amount: 1,
            },
        ],
    );
    button.conditions = vec![Condition::Equals {
        field: "button_id".into(),
        value: Scalar::String("goal".into()),
    }];
    button.cooldown_ms = 3000;
    let mut community = rule(
        "deck-community",
        "manual.button_pressed",
        vec![Action::Widget {
            source_id: "community-alert".into(),
            event: WidgetEvent::Trigger,
        }],
    );
    community.conditions = vec![Condition::Equals {
        field: "button_id".into(),
        value: Scalar::String("community".into()),
    }];
    let mut celebrate = button.clone();
    celebrate.id = "deck-celebrate".into();
    celebrate.conditions = vec![Condition::Equals {
        field: "button_id".into(),
        value: Scalar::String("celebrate".into()),
    }];
    celebrate.actions = vec![Action::Sequence {
        actions: vec![
            Action::Widget {
                source_id: "goal-celebration".into(),
                event: WidgetEvent::Trigger,
            },
            Action::Sound {
                resource: "stadium-cheer".into(),
            },
            Action::IncrementCounter {
                name: "goals".into(),
                amount: 1,
            },
        ],
    }];
    celebrate.failure_policy = FailurePolicy::ContinueUnavailable;
    Config {
        schema_version: 1,
        rules: vec![goal, donation, chat, button, community, celebrate],
        variables: BTreeMap::from([("goals".into(), Scalar::Int(0))]),
        queue_capacity: 16,
        rate_limit: 100,
        rate_window_ms: 1000,
        max_actions_per_event: 32,
    }
}

/// A deck press only emits a synthetic manual event; voice/chat trust cannot be bypassed.
pub fn deck_actions(
    press: &crate::deck::DeckPress,
    pack: &CreatorPack,
    config: &Config,
) -> Result<Config, Error> {
    use crate::deck::{ButtonTarget, DeckTransition};
    let actions = match &press.target {
        ButtonTarget::Rule { rule_id } | ButtonTarget::Composite { rule_id } => {
            let selected = config
                .rules
                .iter()
                .find(|r| r.id == *rule_id)
                .ok_or_else(|| Error::new("RULE_MISSING", "deck rule is not loaded"))?;
            if selected.event_kind != "manual.button_pressed" {
                return Err(Error::new(
                    "RULE_TRIGGER_MISMATCH",
                    "deck cannot bypass a provider or voice rule trigger",
                ));
            }
            let mut config = config.clone();
            config.rules = vec![selected.clone()];
            return Ok(config);
        }
        ButtonTarget::Overlay { source_ref, show } => vec![if *show {
            Action::ShowOverlay {
                source_id: source_ref.clone(),
            }
        } else {
            Action::HideOverlay {
                source_id: source_ref.clone(),
            }
        }],
        ButtonTarget::Countdown { source_ref, reset } => vec![if *reset {
            Action::CountdownReset {
                source_id: source_ref.clone(),
            }
        } else {
            Action::CountdownStart {
                source_id: source_ref.clone(),
            }
        }],
        ButtonTarget::Scene {
            scene_ref,
            transition,
        } => vec![Action::SelectScene {
            scene_id: scene_ref.clone(),
            transition: match transition {
                DeckTransition::Cut => Transition {
                    kind: TransitionKind::Cut,
                    duration_ms: 0,
                },
                DeckTransition::Fade { duration_ms } => Transition {
                    kind: TransitionKind::Fade,
                    duration_ms: *duration_ms,
                },
            },
        }],
        ButtonTarget::Animation { animation_id } => {
            let animation = pack
                .animations
                .iter()
                .find(|a| a.id == *animation_id)
                .ok_or_else(|| {
                    Error::new("ANIMATION_MISSING", "deck animation is not in this pack")
                })?;
            let value = serde_json::json!({"kind":animation.kind,"easing":animation.easing,"duration_ms":animation.duration_ms,"distance":animation.distance,"scale_from":animation.scale_from});
            vec![Action::Animate {
                scene_id: animation.scene_id.clone(),
                layer_id: animation.layer_id.clone(),
                animation: serde_json::from_value(value).map_err(|_| {
                    Error::new("ANIMATION_SCHEMA", "incompatible animation contract")
                })?,
            }]
        }
    };
    let mut r = rule("deck-direct", "manual.button_pressed", actions);
    r.conditions = vec![Condition::Equals {
        field: "button_id".into(),
        value: Scalar::String(press.button_id.clone()),
    }];
    let mut config = config.clone();
    config.rules = vec![r];
    config.validate()?;
    Ok(config)
}
#[derive(Serialize)]
pub struct Report {
    pub mode: &'static str,
    pub scenario: String,
    pub live_commands_sent: usize,
    pub admissions: Vec<Admission>,
    pub jobs: Vec<Job>,
    pub decisions: Vec<Decision>,
    pub variables: BTreeMap<String, Scalar>,
    pub planned_dispatches: Vec<PlannedDispatch>,
}
#[derive(Serialize)]
pub struct Admission {
    pub event_id: String,
    pub jobs: Vec<u64>,
    pub error: Option<Error>,
}
pub fn run_events(
    name: &str,
    config: Config,
    events: Vec<Event>,
    snapshot: ProductionSnapshot,
) -> Result<Report, Error> {
    let clock = ManualClock::default();
    let mut runtime = Runtime::new(config, clock)?;
    let mut backend = Simulator {
        observed: snapshot,
        ..Simulator::default()
    };
    let mut admissions = Vec::new();
    for event in events {
        if !event.simulated {
            return Err(Error::new(
                "SIMULATION_ONLY",
                "CLI only accepts explicitly simulated events",
            ));
        }
        let id = event.id.clone();
        match runtime.submit(event, &trust(), &backend.snapshot()) {
            Ok(jobs) => admissions.push(Admission {
                event_id: id,
                jobs,
                error: None,
            }),
            Err(error) => admissions.push(Admission {
                event_id: id,
                jobs: vec![],
                error: Some(error),
            }),
        }
    }
    for _ in 0..40 {
        runtime.tick(&mut backend);
    }
    Ok(report(name, runtime, backend, admissions))
}
fn report(
    name: &str,
    runtime: Runtime<ManualClock>,
    backend: Simulator,
    admissions: Vec<Admission>,
) -> Report {
    Report {
        mode: "simulation_only",
        scenario: name.into(),
        live_commands_sent: 0,
        admissions,
        jobs: runtime.jobs,
        decisions: runtime.decisions.into_iter().collect(),
        variables: runtime.variables,
        planned_dispatches: backend.dispatches,
    }
}
pub fn scenario(name: &str) -> Result<Report, Error> {
    scenario_with_snapshot(name, fixture_snapshot())
}
pub fn scenario_with_snapshot(name: &str, snapshot: ProductionSnapshot) -> Result<Report, Error> {
    let config = demo_config();
    match name {
        "goal" => {
            let e = event(
                "goal-1",
                Payload::VoiceKeywordDetected {
                    keyword: "gol".into(),
                    confidence_milli: Some(950),
                },
            );
            run_events(
                name,
                config,
                vec![
                    e.clone(),
                    e,
                    event(
                        "goal-2",
                        Payload::VoiceKeywordDetected {
                            keyword: "gol".into(),
                            confidence_milli: Some(950),
                        },
                    ),
                ],
                snapshot,
            )
        }
        "donation" => {
            use crate::providers::*;
            let ingress = VerifiedIngress::simulation("simulation.donations", BTreeSet::new())?;
            let normalized = normalize_donation(
                &ingress,
                DonationInput {
                    id: "donation-1".into(),
                    correlation_id: "donation-1".into(),
                    external_id: Some("fixture-payment-1".into()),
                    timestamp_ms: 1000,
                    semantic: ProviderSemantic::CreatorDonation,
                    user_id: "fixture-viewer".into(),
                    amount_decimal: "5.00".into(),
                    currency: Currency::USD,
                    message: "Synthetic support, no payment occurred".into(),
                },
            )?;
            run_events(name, config, vec![normalized.into_parts().0], snapshot)
        }
        "chat" => run_events(
            name,
            config,
            vec![
                event(
                    "chat-1",
                    Payload::ChatCommand {
                        user_id: "viewer".into(),
                        command: "brb".into(),
                    },
                ),
                event(
                    "chat-2",
                    Payload::ChatCommand {
                        user_id: "creator".into(),
                        command: "brb".into(),
                    },
                ),
                event(
                    "chat-3",
                    Payload::ChatCommand {
                        user_id: "creator".into(),
                        command: "brb".into(),
                    },
                ),
            ],
            snapshot,
        ),
        "burst" => {
            let mut config = config;
            config.rules.clear();
            config.queue_capacity = 4;
            for (id, p) in [("normal", 2), ("urgent", 9)] {
                let mut r = rule(
                    id,
                    "manual.button_pressed",
                    vec![Action::Widget {
                        source_id: if id == "urgent" {
                            "goal-celebration"
                        } else {
                            "community-alert"
                        }
                        .into(),
                        event: WidgetEvent::Trigger,
                    }],
                );
                r.priority = p;
                r.conditions = vec![Condition::Equals {
                    field: "button_id".into(),
                    value: Scalar::String(id.into()),
                }];
                config.rules.push(r);
            }
            let mut runtime = Runtime::new(config, ManualClock::default())?;
            let mut backend = Simulator {
                observed: snapshot,
                ..Simulator::default()
            };
            let mut admissions = Vec::new();
            for i in 0..8 {
                let e = event(
                    &format!("burst-{i}"),
                    Payload::ManualButtonPressed {
                        button_id: if i % 2 == 0 { "normal" } else { "urgent" }.into(),
                    },
                );
                let event_id = e.id.clone();
                match runtime.submit(e, &trust(), &backend.snapshot()) {
                    Ok(jobs) => admissions.push(Admission {
                        event_id,
                        jobs,
                        error: None,
                    }),
                    Err(error) => admissions.push(Admission {
                        event_id,
                        jobs: vec![],
                        error: Some(error),
                    }),
                }
            }
            let duplicate = event(
                "burst-1",
                Payload::ManualButtonPressed {
                    button_id: "urgent".into(),
                },
            );
            let error = runtime
                .submit(duplicate, &trust(), &backend.snapshot())
                .err();
            admissions.push(Admission {
                event_id: "burst-1".into(),
                jobs: vec![],
                error,
            });
            runtime.cancel(1, &mut backend)?;
            for _ in 0..4 {
                runtime.tick(&mut backend);
            }
            Ok(report(name, runtime, backend, admissions))
        }
        _ => Err(Error::new(
            "UNKNOWN_SCENARIO",
            "use goal, donation, chat or burst",
        )),
    }
}
