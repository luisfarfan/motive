use motive_show_control::{actions::*, model::*};
use std::collections::BTreeMap;

fn event(payload: Payload) -> Event {
    Event {
        schema_version: 1,
        id: "event-1".into(),
        origin: "simulation".into(),
        timestamp_ms: 10,
        correlation_id: "corr-1".into(),
        external_id: None,
        simulated: true,
        payload,
    }
}
fn animation() -> Animation {
    Animation {
        kind: AnimationKind::SlideIn,
        easing: Easing::EaseOut,
        duration_ms: 500,
        distance: 120.,
        scale_from: 1.,
    }
}
fn text_definition() -> TextDefinition {
    TextDefinition {
        text: "Original".into(),
        font: Font::Helvetica,
        size: 40,
        color: 0xffffff,
        opacity: 1.,
        align: Alignment::Left,
        width: 600,
        height: 100,
        background: None,
        background_opacity: 0.,
        outline: false,
    }
}
fn snapshot() -> ProductionSnapshot {
    ProductionSnapshot {
        pid: 123,
        revision: 7,
        active_scene: "scene-live".into(),
        sources: BTreeMap::from([
            ("goal".into(), SourceReadiness::Ready),
            ("title".into(), SourceReadiness::Ready),
            ("timer".into(), SourceReadiness::Ready),
        ]),
        source_kinds: BTreeMap::from([
            ("goal".into(), SourceKind::Alert),
            ("title".into(), SourceKind::Text),
            ("timer".into(), SourceKind::Countdown),
        ]),
        text_definitions: BTreeMap::from([("title".into(), text_definition())]),
        scenes: BTreeMap::from([
            ("scene-live".into(), vec!["goal".into()]),
            ("scene-brb".into(), vec!["title".into()]),
        ]),
        layers: BTreeMap::from([(
            "layer-goal".into(),
            LayerBinding {
                scene_id: "scene-live".into(),
                source_id: "goal".into(),
            },
        )]),
        ..Default::default()
    }
}

#[test]
fn all_initial_payloads_validate_and_roundtrip() {
    let payloads = vec![
        Payload::ManualButtonPressed {
            button_id: "goal".into(),
        },
        Payload::KeyboardShortcut {
            shortcut: "Cmd+G".into(),
        },
        Payload::VoiceKeywordDetected {
            keyword: "gol".into(),
            confidence_milli: Some(900),
        },
        Payload::ChatMessage {
            user_id: "viewer".into(),
            text: "hola".into(),
        },
        Payload::ChatCommand {
            user_id: "moderator".into(),
            command: "brb".into(),
        },
        Payload::ViewerFollow {
            user_id: "viewer".into(),
        },
        Payload::ViewerSubscribe {
            user_id: "viewer".into(),
            tier: "tier-1".into(),
        },
        Payload::ViewerDonation {
            user_id: "viewer".into(),
            amount_minor: 1000,
            currency: "PEN".into(),
            message: "Gracias".into(),
        },
        Payload::ViewerRewardRedeemed {
            user_id: "viewer".into(),
            reward_id: "celebrate".into(),
            input: "hello".into(),
        },
        Payload::TimerCompleted {
            timer_id: "starting".into(),
        },
        Payload::ProductionStarted {
            output_id: "local-recording".into(),
        },
        Payload::ProductionStopped {
            output_id: "local-recording".into(),
        },
        Payload::CustomEvent {
            name: "goal".into(),
            fields: BTreeMap::from([("count".into(), Scalar::Int(1))]),
        },
    ];
    for payload in payloads {
        let expected = event(payload);
        expected.validate().unwrap();
        let actual = Event::from_json(&serde_json::to_string(&expected).unwrap()).unwrap();
        assert_eq!(actual, expected);
        assert_eq!(
            actual.field("kind"),
            Some(Scalar::String(actual.kind().into()))
        );
    }
}

#[test]
fn malformed_unknown_schema_and_extra_fields_are_rejected() {
    assert_eq!(Event::from_json("{}").unwrap_err().code, "INVALID_JSON");
    let mut value = event(Payload::ViewerFollow {
        user_id: "viewer".into(),
    });
    value.schema_version = 2;
    assert_eq!(value.validate().unwrap_err().code, "UNSUPPORTED_SCHEMA");
    value.schema_version = 1;
    let mut json = serde_json::to_value(&value).unwrap();
    json["payload"]["trusted"] = true.into();
    assert!(Event::from_json(&json.to_string()).is_err());
    json["payload"].as_object_mut().unwrap().remove("trusted");
    json["trusted"] = true.into();
    assert!(Event::from_json(&json.to_string()).is_err());
    assert_eq!(
        Event::from_json(&" ".repeat(MAX_JSON_BYTES + 1))
            .unwrap_err()
            .code,
        "INPUT_TOO_LARGE"
    );
}

#[test]
fn event_bounds_are_utf8_and_integer_based() {
    for amount in [0, 1_000_000_000_001, u64::MAX] {
        assert!(
            event(Payload::ViewerDonation {
                user_id: "viewer".into(),
                amount_minor: amount,
                currency: "USD".into(),
                message: String::new()
            })
            .validate()
            .is_err()
        );
    }
    assert!(
        event(Payload::VoiceKeywordDetected {
            keyword: "gol".into(),
            confidence_milli: Some(1001)
        })
        .validate()
        .is_err()
    );
    assert!(
        event(Payload::VoiceKeywordDetected {
            keyword: " ".into(),
            confidence_milli: None
        })
        .validate()
        .is_err()
    );
    assert!(
        event(Payload::ChatMessage {
            user_id: "viewer".into(),
            text: "é".repeat(2049)
        })
        .validate()
        .is_err()
    );
    assert!(
        event(Payload::ChatMessage {
            user_id: "viewer".into(),
            text: "inject\u{001b}[0m".into()
        })
        .validate()
        .is_err()
    );
    let mut fields = BTreeMap::new();
    fields.insert("origin".into(), Scalar::String("owner".into()));
    assert_eq!(
        event(Payload::CustomEvent {
            name: "test".into(),
            fields
        })
        .validate()
        .unwrap_err()
        .code,
        "RESERVED_FIELD"
    );
}

#[test]
fn field_lookup_is_typed_and_closed() {
    let event = event(Payload::ViewerDonation {
        user_id: "viewer".into(),
        amount_minor: 123,
        currency: "USD".into(),
        message: "test".into(),
    });
    assert_eq!(event.field("amount_minor"), Some(Scalar::Int(123)));
    assert_eq!(event.field("payload.amount_minor"), None);
    assert_eq!(
        event.field("user_id"),
        Some(Scalar::String("viewer".into()))
    );
}

#[test]
fn action_schema_does_not_accept_arbitrary_commands() {
    assert!(serde_json::from_str::<Action>(r#"{"type":"shell","command":"anything"}"#).is_err());
    assert!(
        serde_json::from_str::<Action>(
            r#"{"type":"show_overlay","source_id":"goal","url":"https://example.org"}"#
        )
        .is_err()
    );
    assert!(
        Action::ShowOverlay {
            source_id: "../../secret".into()
        }
        .validate()
        .is_err()
    );
    assert!(
        Action::Sound {
            resource: "https://example.org/audio.wav".into()
        }
        .validate()
        .is_err()
    );
}

#[test]
fn sequence_leaf_count_and_depth_are_bounded() {
    let notify = Action::Notify {
        message: "test".into(),
    };
    assert_eq!(
        Action::Sequence {
            actions: vec![notify.clone(); 32]
        }
        .flattened()
        .unwrap()
        .len(),
        32
    );
    assert!(
        Action::Sequence {
            actions: vec![notify.clone(); 33]
        }
        .validate()
        .is_err()
    );
    let mut deep = notify;
    for _ in 0..5 {
        deep = Action::Sequence {
            actions: vec![deep],
        };
    }
    assert_eq!(deep.validate().unwrap_err().code, "SEQUENCE_DEPTH");
    assert!(Action::Sequence { actions: vec![] }.validate().is_err());
}

#[test]
fn exhaustive_animation_boundary_samples() {
    for duration in [0, 99, 100, 500, 10000, 10001, u32::MAX] {
        let mut value = animation();
        value.duration_ms = duration;
        assert_eq!(value.validate().is_ok(), (100..=10000).contains(&duration));
    }
    for distance in [f32::NAN, f32::INFINITY, -1921., -1920., 0., 1920., 1921.] {
        let mut value = animation();
        value.distance = distance;
        assert_eq!(
            value.validate().is_ok(),
            distance.is_finite() && distance.abs() <= 1920.
        );
    }
    let mut value = animation();
    value.kind = AnimationKind::FadeIn;
    assert_eq!(
        value.validate().unwrap_err().code,
        "UNSUPPORTED_FADE_EASING"
    );
    value.easing = Easing::Linear;
    assert!(value.validate().is_ok());
}

#[test]
fn stale_process_and_revision_reject_media_but_not_local_counter() {
    let state = snapshot();
    let action = Action::ShowOverlay {
        source_id: "goal".into(),
    };
    for version in [
        Revision {
            pid: 123,
            revision: 6,
        },
        Revision {
            pid: 999,
            revision: 7,
        },
    ] {
        assert_eq!(
            prepare(&action, &state, Some(version)).unwrap_err().code,
            "STALE_REVISION"
        );
        assert!(
            prepare(
                &Action::IncrementCounter {
                    name: "goals".into(),
                    amount: 1
                },
                &state,
                Some(version)
            )
            .unwrap()
            .local
        );
    }
}

#[test]
fn source_reconnection_requires_a_new_observed_snapshot() {
    let action = Action::ShowOverlay {
        source_id: "goal".into(),
    };
    let mut state = snapshot();
    state
        .sources
        .insert("goal".into(), SourceReadiness::Missing);
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "SOURCE_NOT_READY"
    );
    state
        .sources
        .insert("goal".into(), SourceReadiness::Recovering);
    assert!(prepare(&action, &state, None).is_err());
    state.sources.insert("goal".into(), SourceReadiness::Ready);
    state.revision += 1;
    let prepared = prepare(&action, &state, Some(state.version())).unwrap();
    assert!(prepared.requires_completion);
    assert!(!prepared.local);
}

#[test]
fn widget_compatibility_and_source_visibility_are_explicit() {
    let state = snapshot();
    assert!(
        prepare(
            &Action::CountdownStart {
                source_id: "goal".into()
            },
            &state,
            None
        )
        .is_err()
    );
    assert!(
        prepare(
            &Action::Widget {
                source_id: "title".into(),
                event: WidgetEvent::Trigger
            },
            &state,
            None
        )
        .is_err()
    );
    let prepared = prepare(
        &Action::ShowOverlay {
            source_id: "goal".into(),
        },
        &state,
        None,
    )
    .unwrap();
    assert_eq!(
        serde_json::to_value(&prepared.commands[0]).unwrap(),
        serde_json::json!({"op":"overlay_event","source_id":"goal","event":"show"})
    );
    assert!(
        prepare(
            &Action::CountdownStart {
                source_id: "timer".into()
            },
            &state,
            None
        )
        .is_ok()
    );
}

#[test]
fn scene_transition_uses_existing_two_step_contract() {
    let action = Action::SelectScene {
        scene_id: "scene-brb".into(),
        transition: Transition {
            kind: TransitionKind::Fade,
            duration_ms: 350,
        },
    };
    let mut state = snapshot();
    let prepared = prepare(&action, &state, None).unwrap();
    assert_eq!(
        serde_json::to_value(&prepared.commands).unwrap(),
        serde_json::json!([
            {"op":"configure_transition","transition":{"kind":"fade","duration_ms":350}},
            {"op":"select_scene","scene_id":"scene-brb"}
        ])
    );
    state.animation_active = true;
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "PRODUCTION_BUSY"
    );
    state.animation_active = false;
    state
        .sources
        .insert("title".into(), SourceReadiness::Failed);
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "SOURCE_NOT_READY"
    );
    assert_eq!(state.active_scene, "scene-live"); // preparation never mutates production
}

#[test]
fn animation_pending_ack_and_global_limit_remain_busy() {
    let action = Action::Animate {
        scene_id: "scene-live".into(),
        layer_id: "layer-goal".into(),
        animation: animation(),
    };
    let mut state = snapshot();
    assert!(prepare(&action, &state, None).is_ok());
    state.busy_layers.insert("layer-goal".into());
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "ANIMATION_BUSY"
    );
    state.busy_layers = (0..8).map(|i| format!("other-{i}")).collect();
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "ANIMATION_BUSY"
    );
    state.busy_layers.clear();
    state.transition_active = true;
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "PRODUCTION_BUSY"
    );
}

#[test]
fn empty_target_rejects_fade_and_live_cut() {
    let mut state = snapshot();
    state.scenes.insert("empty".into(), Vec::new());
    let cut = Action::SelectScene {
        scene_id: "empty".into(),
        transition: Transition {
            kind: TransitionKind::Cut,
            duration_ms: 0,
        },
    };
    let fade = Action::SelectScene {
        scene_id: "empty".into(),
        transition: Transition {
            kind: TransitionKind::Fade,
            duration_ms: 250,
        },
    };
    assert!(prepare(&cut, &state, None).is_ok());
    assert_eq!(
        prepare(&fade, &state, None).unwrap_err().code,
        "EMPTY_SCENE"
    );
    state.output_active = true;
    assert_eq!(prepare(&cut, &state, None).unwrap_err().code, "EMPTY_SCENE");
    assert_eq!(
        prepare(&fade, &state, None).unwrap_err().code,
        "EMPTY_SCENE"
    );
}

#[test]
fn cancellation_uses_only_known_animation_operation_ids() {
    let mut state = snapshot();
    assert_eq!(
        prepare(&Action::CancelAnimation { operation_id: 3 }, &state, None)
            .unwrap_err()
            .code,
        "OPERATION_MISSING"
    );
    state.animation_operations.insert(3);
    let result = prepare(&Action::CancelAnimation { operation_id: 3 }, &state, None).unwrap();
    assert!(result.requires_completion);
}

#[test]
fn text_update_copies_full_definition_without_mutating_snapshot() {
    let state = snapshot();
    let result = prepare(
        &Action::UpdateText {
            source_id: "title".into(),
            text: "New title".into(),
        },
        &state,
        None,
    )
    .unwrap();
    let json = serde_json::to_value(&result.commands[0]).unwrap();
    assert_eq!(json["op"], "update_overlay");
    assert_eq!(json["definition"]["kind"], "text");
    assert_eq!(json["definition"]["text"], "New title");
    assert_eq!(json["definition"]["size"], 40);
    assert!(json["definition"]["background"].is_null());
    assert_eq!(state.text_definitions["title"].text, "Original");
}

#[test]
fn unavailable_audio_never_produces_commands() {
    let state = snapshot();
    assert_eq!(
        prepare(
            &Action::Sound {
                resource: "stadium-cheer".into()
            },
            &state,
            None
        )
        .unwrap_err()
        .code,
        "CAPABILITY_UNAVAILABLE"
    );
    let speech = prepare(
        &Action::PrepareSpeech {
            text: "Thank you".into(),
        },
        &state,
        None,
    )
    .unwrap();
    assert!(speech.local && speech.commands.is_empty());
    assert!(!speech.requires_completion);
}

#[test]
fn receipt_does_not_confuse_accepted_with_completed() {
    let mut receipt = ActionReceipt {
        action_id: "action-1".into(),
        status: ActionStatus::Validated,
        operation_id: None,
        error: None,
        simulated: true,
    };
    assert!(receipt.transition(ActionStatus::Completed).is_err());
    receipt.transition(ActionStatus::Prepared).unwrap();
    receipt.transition(ActionStatus::Sent).unwrap();
    receipt.transition(ActionStatus::Accepted).unwrap();
    receipt.operation_id = Some(45);
    assert_eq!(receipt.status, ActionStatus::Accepted);
    receipt.transition(ActionStatus::Uncertain).unwrap();
    assert!(receipt.transition(ActionStatus::Sent).is_err()); // never resend uncertain mutation
    receipt.transition(ActionStatus::Completed).unwrap();
    assert!(receipt.transition(ActionStatus::Sent).is_err());
}
