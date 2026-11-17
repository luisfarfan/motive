use motive_show_control::actions::*;
use serde_json::json;
use std::collections::BTreeMap;

fn animation(kind: AnimationKind) -> Animation {
    Animation {
        kind,
        easing: Easing::Linear,
        duration_ms: 500,
        distance: 120.,
        scale_from: 0.5,
    }
}

fn trigger(kind: AnimationKind) -> Action {
    Action::TriggerAnimatedWidget {
        source_id: "goal".into(),
        scene_id: "live".into(),
        layer_id: "goal-layer".into(),
        animation: animation(kind),
    }
}

fn snapshot() -> ProductionSnapshot {
    ProductionSnapshot {
        pid: 123,
        revision: 7,
        active_scene: "live".into(),
        sources: BTreeMap::from([
            ("goal".into(), SourceReadiness::Ready),
            ("other".into(), SourceReadiness::Ready),
        ]),
        source_kinds: BTreeMap::from([
            ("goal".into(), SourceKind::Alert),
            ("other".into(), SourceKind::LowerThird),
        ]),
        scenes: BTreeMap::from([
            ("live".into(), vec!["goal".into()]),
            ("brb".into(), vec!["goal".into()]),
        ]),
        layers: BTreeMap::from([
            (
                "goal-layer".into(),
                LayerBinding {
                    scene_id: "live".into(),
                    source_id: "goal".into(),
                },
            ),
            (
                "brb-goal-layer".into(),
                LayerBinding {
                    scene_id: "brb".into(),
                    source_id: "goal".into(),
                },
            ),
        ]),
        ..Default::default()
    }
}

#[test]
fn trigger_serializes_as_one_explicit_command_that_requires_completion() {
    let action = trigger(AnimationKind::SlideIn);
    let state = snapshot();
    let original = state.clone();
    let action_json = json!({
        "type": "trigger_animated_widget",
        "source_id": "goal",
        "scene_id": "live",
        "layer_id": "goal-layer",
        "animation": {
            "kind": "slide_in",
            "easing": "linear",
            "duration_ms": 500,
            "distance": 120.0,
            "scale_from": 0.5
        }
    });
    assert_eq!(serde_json::to_value(&action).unwrap(), action_json);
    assert_eq!(
        serde_json::from_value::<Action>(action_json).unwrap(),
        action
    );

    let prepared = prepare(&action, &state, Some(state.version())).unwrap();
    assert_eq!(prepared.action, action);
    assert!(!prepared.local);
    assert!(prepared.requires_completion);
    assert_eq!(prepared.commands.len(), 1);
    let command_json = json!({
        "op": "trigger_animated_widget",
        "source_id": "goal",
        "scene_id": "live",
        "layer_id": "goal-layer",
        "animation": {
            "kind": "slide_in",
            "easing": "linear",
            "duration_ms": 500,
            "distance": 120.0,
            "scale_from": 0.5
        }
    });
    assert_eq!(
        serde_json::to_value(&prepared.commands[0]).unwrap(),
        command_json
    );
    assert_eq!(
        serde_json::from_value::<CoreCommand>(command_json).unwrap(),
        prepared.commands[0]
    );
    assert_eq!(state, original);
}

#[test]
fn animated_trigger_schema_requires_explicit_targets_and_rejects_extra_fields() {
    let valid = serde_json::to_value(trigger(AnimationKind::FadeIn)).unwrap();
    for field in ["source_id", "scene_id", "layer_id", "animation"] {
        let mut malformed = valid.clone();
        malformed.as_object_mut().unwrap().remove(field);
        assert!(
            serde_json::from_value::<Action>(malformed).is_err(),
            "{field}"
        );
    }
    let mut malformed = valid.clone();
    malformed["event"] = json!("trigger");
    assert!(serde_json::from_value::<Action>(malformed).is_err());
    let mut malformed = valid;
    malformed["animation"]["start_at_ms"] = json!(10);
    assert!(serde_json::from_value::<Action>(malformed).is_err());

    let prepared = prepare(&trigger(AnimationKind::FadeIn), &snapshot(), None).unwrap();
    let mut malformed = serde_json::to_value(&prepared.commands[0]).unwrap();
    malformed["event"] = json!("trigger");
    assert!(serde_json::from_value::<CoreCommand>(malformed).is_err());
}

#[test]
fn all_target_identifiers_are_validated() {
    let valid = serde_json::to_value(trigger(AnimationKind::SlideIn)).unwrap();
    for field in ["source_id", "scene_id", "layer_id"] {
        for invalid in [String::new(), "../outside".into(), "x".repeat(129)] {
            let mut malformed = valid.clone();
            malformed[field] = json!(invalid);
            let action: Action = serde_json::from_value(malformed).unwrap();
            assert_eq!(action.validate().unwrap_err().code, "INVALID_ID", "{field}");
        }
    }
}

#[test]
fn only_incoming_animations_are_accepted_for_alerts_and_lower_thirds() {
    for source_kind in [SourceKind::Alert, SourceKind::LowerThird] {
        let mut state = snapshot();
        state.source_kinds.insert("goal".into(), source_kind);
        for kind in [
            AnimationKind::FadeIn,
            AnimationKind::SlideIn,
            AnimationKind::ScaleIn,
        ] {
            assert!(
                prepare(&trigger(kind), &state, None).is_ok(),
                "{source_kind:?}/{kind:?}"
            );
        }
    }
    for kind in [
        AnimationKind::FadeOut,
        AnimationKind::SlideOut,
        AnimationKind::ScaleOut,
    ] {
        let action = trigger(kind);
        assert_eq!(action.validate().unwrap_err().code, "INVALID_ANIMATION");
        assert_eq!(
            prepare(&action, &snapshot(), None).unwrap_err().code,
            "INVALID_ANIMATION"
        );
    }
}

#[test]
fn incoming_animations_retain_existing_parameter_limits() {
    let mut action = trigger(AnimationKind::SlideIn);
    if let Action::TriggerAnimatedWidget { animation, .. } = &mut action {
        animation.duration_ms = 99;
    }
    assert_eq!(action.validate().unwrap_err().code, "INVALID_ANIMATION");
    if let Action::TriggerAnimatedWidget { animation, .. } = &mut action {
        animation.duration_ms = 500;
        animation.scale_from = f32::NAN;
    }
    assert_eq!(action.validate().unwrap_err().code, "INVALID_ANIMATION");
    if let Action::TriggerAnimatedWidget { animation, .. } = &mut action {
        animation.scale_from = 0.5;
        animation.kind = AnimationKind::FadeIn;
        animation.easing = Easing::EaseOut;
    }
    assert_eq!(
        action.validate().unwrap_err().code,
        "UNSUPPORTED_FADE_EASING"
    );
}

#[test]
fn explicit_source_must_match_the_layer_in_the_active_scene() {
    let action = trigger(AnimationKind::SlideIn);
    let mut state = snapshot();
    state.layers.get_mut("goal-layer").unwrap().source_id = "other".into();
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "LAYER_MISMATCH"
    );
    state = snapshot();
    state.layers.get_mut("goal-layer").unwrap().scene_id = "brb".into();
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "LAYER_MISMATCH"
    );
    state.layers.remove("goal-layer");
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "LAYER_MISSING"
    );
    state = snapshot();
    state.active_scene = "brb".into();
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "PRODUCTION_BUSY"
    );
}

#[test]
fn trigger_requires_an_observed_ready_widget_source() {
    let action = trigger(AnimationKind::SlideIn);
    for readiness in [
        SourceReadiness::Missing,
        SourceReadiness::Recovering,
        SourceReadiness::Failed,
    ] {
        let mut state = snapshot();
        state.sources.insert("goal".into(), readiness);
        assert_eq!(
            prepare(&action, &state, None).unwrap_err().code,
            "SOURCE_NOT_READY"
        );
    }
    let mut state = snapshot();
    state.sources.remove("goal");
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "SOURCE_MISSING"
    );
    state = snapshot();
    state.source_kinds.remove("goal");
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "NOT_AN_OVERLAY"
    );
    for kind in [
        SourceKind::Text,
        SourceKind::Shape,
        SourceKind::Image,
        SourceKind::Video,
        SourceKind::Countdown,
    ] {
        state.source_kinds.insert("goal".into(), kind);
        assert_eq!(
            prepare(&action, &state, None).unwrap_err().code,
            "INVALID_OVERLAY_ACTION"
        );
    }
}

#[test]
fn duplicate_source_layers_are_rejected_only_in_the_active_scene() {
    let action = trigger(AnimationKind::SlideIn);
    let mut state = snapshot();
    assert!(prepare(&action, &state, None).is_ok()); // The source is also used in BRB.
    state.layers.insert(
        "duplicate".into(),
        LayerBinding {
            scene_id: "live".into(),
            source_id: "goal".into(),
        },
    );
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "SHARED_WIDGET_SOURCE"
    );
    state.layers.get_mut("duplicate").unwrap().source_id = "other".into();
    assert!(prepare(&action, &state, None).is_ok());
}

#[test]
fn structural_work_transition_and_animation_capacity_block_the_trigger() {
    let action = trigger(AnimationKind::SlideIn);
    let mut state = snapshot();
    state.structural_busy = true;
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "PRODUCTION_BUSY"
    );
    state.structural_busy = false;
    state.transition_active = true;
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "PRODUCTION_BUSY"
    );
    state.transition_active = false;
    state.animation_active = true;
    state.output_active = true;
    state.busy_layers = (0..7).map(|index| format!("other-{index}")).collect();
    assert!(prepare(&action, &state, None).is_ok());
    state.busy_layers.insert("other-7".into());
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "ANIMATION_BUSY"
    );
    state.busy_layers.clear();
    state.busy_layers.insert("goal-layer".into());
    assert_eq!(
        prepare(&action, &state, None).unwrap_err().code,
        "ANIMATION_BUSY"
    );
}

#[test]
fn stale_process_or_revision_cannot_prepare_a_composite_trigger() {
    let state = snapshot();
    for expected in [
        Revision {
            pid: 124,
            revision: 7,
        },
        Revision {
            pid: 123,
            revision: 6,
        },
    ] {
        assert_eq!(
            prepare(&trigger(AnimationKind::SlideIn), &state, Some(expected))
                .unwrap_err()
                .code,
            "STALE_REVISION"
        );
    }
}

#[test]
fn existing_widget_and_animation_actions_keep_their_original_contracts() {
    let mut state = snapshot();
    state.layers.insert(
        "duplicate".into(),
        LayerBinding {
            scene_id: "live".into(),
            source_id: "goal".into(),
        },
    );
    let widget_json = json!({"type": "widget", "source_id": "goal", "event": "trigger"});
    let widget: Action = serde_json::from_value(widget_json.clone()).unwrap();
    assert_eq!(serde_json::to_value(&widget).unwrap(), widget_json);
    let prepared = prepare(&widget, &state, None).unwrap();
    assert!(prepared.requires_completion);
    assert_eq!(
        serde_json::to_value(prepared.commands).unwrap(),
        json!([
            {"op": "overlay_event", "source_id": "goal", "event": "trigger"}
        ])
    );

    let animate = Action::Animate {
        scene_id: "live".into(),
        layer_id: "goal-layer".into(),
        animation: animation(AnimationKind::SlideOut),
    };
    let prepared = prepare(&animate, &state, None).unwrap();
    assert!(prepared.requires_completion);
    assert_eq!(
        prepared.commands,
        vec![CoreCommand::AnimateOverlay {
            scene_id: "live".into(),
            layer_id: "goal-layer".into(),
            animation: animation(AnimationKind::SlideOut),
        }]
    );
    assert_eq!(serde_json::to_value(&animate).unwrap()["type"], "animate");
    assert_eq!(
        serde_json::to_value(&prepared.commands[0]).unwrap()["op"],
        "animate_overlay"
    );
    state.busy_layers.insert("goal-layer".into());
    assert_eq!(
        prepare(&animate, &state, None).unwrap_err().code,
        "ANIMATION_BUSY"
    );
    assert!(prepare(&widget, &state, None).is_ok());
}
