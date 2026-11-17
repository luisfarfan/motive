use motive_show_control::deck::*;
fn deck() -> Deck {
    Deck::from_json(include_str!("../examples/decks/matchday.json")).unwrap()
}
#[test]
fn real_owner_result_is_distinct_from_simulation_and_retains_cooldown() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    let permit = runtime.authorize_live("goal", 0).unwrap();
    let press = runtime.press_live(permit, 0).unwrap();
    assert!(!press.simulated);
    assert!(
        runtime
            .finish_simulation(press.request_id, 1, None)
            .is_err()
    );
    runtime
        .finish_live(press.request_id, 1, LiveDeckResult::Completed)
        .unwrap();
    assert_eq!(
        runtime.history().back().unwrap().state,
        ButtonState::Completed
    );
    assert_eq!(
        runtime.state("goal", 2).unwrap(),
        ButtonState::CoolingDown { remaining_ms: 9998 }
    );
    assert!(
        runtime
            .finish_live(press.request_id, 2, LiveDeckResult::Completed)
            .is_err()
    );
}
#[test]
fn simulation_cannot_be_reported_as_a_live_completion() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    let press = runtime.press("goal", 0, false).unwrap();
    assert!(
        runtime
            .finish_live(press.request_id, 1, LiveDeckResult::Completed)
            .is_err()
    );
    runtime
        .finish_simulation(press.request_id, 1, None)
        .unwrap();
}
#[test]
fn owner_permit_is_consumed_against_exact_deck_and_request_sequence() {
    let mut runtime = DeckRuntime::new(deck()).unwrap();
    let stale = runtime.authorize_live("goal", 0).unwrap();
    let current = runtime.authorize_live("goal", 0).unwrap();
    let press = runtime.press_live(current, 0).unwrap();
    runtime
        .finish_live(press.request_id, 1, LiveDeckResult::NeedsReconciliation)
        .unwrap();
    assert!(runtime.press_live(stale, 10000).is_err());
    assert_eq!(
        runtime.history().back().unwrap().state,
        ButtonState::NeedsReconciliation
    );
    let fresh = runtime.authorize_live("goal", 10000).unwrap();
    let press = runtime.press_live(fresh, 10000).unwrap();
    runtime
        .finish_live(press.request_id, 10001, LiveDeckResult::Cancelled)
        .unwrap();
    assert_eq!(
        runtime.history().back().unwrap().state,
        ButtonState::Cancelled
    );
}
