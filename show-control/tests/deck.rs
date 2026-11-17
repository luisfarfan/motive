use motive_show_control::deck::*;
fn deck() -> Deck {
    Deck::from_json(include_str!("../examples/decks/matchday.json")).unwrap()
}
#[test]
fn sample_deck_has_each_typed_target_and_only_simulated_events() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    let press = runtime.press("goal", 100, false).unwrap();
    assert!(press.simulated);
    assert_eq!(press.event_kind, "manual.button_pressed");
    assert_eq!(
        press.target,
        ButtonTarget::Rule {
            rule_id: "deck-goal".into()
        }
    );
    assert!(matches!(
        runtime.state("goal", 100).unwrap(),
        ButtonState::Pending { .. }
    ));
    runtime
        .finish_simulation(press.request_id, 101, None)
        .unwrap();
    assert!(matches!(
        runtime.history().back().unwrap().state,
        ButtonState::Simulated
    ));
}
#[test]
fn cooldown_and_pending_are_explicit_and_cannot_duplicate_dispatch() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    let press = runtime.press("goal", 0, false).unwrap();
    assert!(runtime.press("goal", 0, false).is_err());
    runtime
        .finish_simulation(press.request_id, 1, None)
        .unwrap();
    assert!(runtime.press("goal", 9999, false).is_err());
    assert_eq!(
        runtime.state("goal", 9999).unwrap(),
        ButtonState::CoolingDown { remaining_ms: 1 }
    );
    assert!(runtime.press("goal", 10000, false).is_ok());
    assert!(
        runtime
            .finish_simulation(press.request_id, 10001, None)
            .is_err()
    );
}
#[test]
fn sensitive_confirmation_is_local_prototype_only() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    assert!(runtime.press("brb", 0, false).is_err());
    assert_eq!(
        runtime.state("brb", 0).unwrap(),
        ButtonState::AwaitingConfirmation
    );
    let press = runtime.press("brb", 1, true).unwrap();
    assert!(press.simulated);
    runtime.cancel_pending(press.request_id, 2).unwrap();
    assert!(matches!(
        runtime.history().back().unwrap().state,
        ButtonState::Cancelled
    ));
}
#[test]
fn disabled_and_duplicate_shortcuts_and_unknown_fields_fail() {
    let mut d = deck();
    d.buttons[0].enabled = false;
    let mut runtime = DeckRuntime::new(d).unwrap();
    assert!(runtime.press("goal", 0, false).is_err());
    let mut d = deck();
    d.buttons[1].shortcut = d.buttons[0].shortcut.clone();
    assert!(d.validate().is_err());
    let mut value = serde_json::to_value(deck()).unwrap();
    value["buttons"][0]["target"]["command"] = "shell".into();
    assert!(Deck::from_json(&value.to_string()).is_err());
    assert!(Deck::from_json("{}").is_err());
}
#[test]
fn history_is_bounded_rejected_requests_are_observable_and_time_is_monotonic() {
    let mut d = deck();
    d.buttons[0].cooldown_ms = 0;
    let mut runtime = DeckRuntime::new(d).unwrap();
    for now in 0..100 {
        let press = runtime.press("goal", now, false).unwrap();
        runtime
            .finish_simulation(press.request_id, now, Some("SOURCE_UNAVAILABLE"))
            .unwrap();
    }
    assert_eq!(runtime.history().len(), 64);
    assert!(matches!(
        runtime.history().back().unwrap().state,
        ButtonState::Rejected { .. }
    ));
    assert!(runtime.press("goal", 98, false).is_err());
    assert!(runtime.state("goal", 98).is_err());
}
#[test]
fn exhausted_clock_does_not_dispatch() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    assert!(runtime.press("goal", u64::MAX, false).is_err());
    assert!(runtime.history().is_empty());
}

#[test]
fn scene_fade_uses_h9_limit_not_layer_animation_limit() {
    let mut d = deck();
    d.buttons[0].target = ButtonTarget::Scene {
        scene_ref: "match-brb".into(),
        transition: DeckTransition::Fade { duration_ms: 5000 },
    };
    assert!(d.validate().is_ok());
    d.buttons[0].target = ButtonTarget::Scene {
        scene_ref: "match-brb".into(),
        transition: DeckTransition::Fade { duration_ms: 5001 },
    };
    assert!(d.validate().is_err());
}
