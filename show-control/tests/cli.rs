use serde_json::Value;
use std::path::Path;
use std::process::{Command, Output};
fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_motive-show"))
        .args(args)
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .unwrap()
}
fn decoded(output: Output) -> Value {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).unwrap()
}
#[test]
fn all_scenarios_execute_independently_and_disclose_zero_live_commands() {
    for scenario in ["goal", "donation", "chat", "burst"] {
        let result = decoded(run(&["simulate", scenario]));
        assert_eq!(result["mode"], "simulation_only");
        assert_eq!(result["live_commands_sent"], 0);
    }
}
#[test]
fn definition_and_event_files_load_into_shared_runtime() {
    let result = decoded(run(&[
        "run",
        "examples/rules/matchday.json",
        "examples/events/goal.jsonl",
    ]));
    assert_eq!(result["variables"]["goals"]["value"], 1);
    assert_eq!(result["jobs"][0]["rule_id"], "goal-celebration");
    let from_pack = decoded(run(&[
        "run",
        "examples/rules/matchday.json",
        "examples/events/goal.jsonl",
        "examples/packs/matchday.json",
    ]));
    assert_eq!(from_pack["jobs"][0]["state"], "simulated");
}
#[test]
fn matchday_pack_plans_and_events_reference_actual_declared_sources() {
    let plan = decoded(run(&["plan-pack", "examples/packs/matchday.json"]));
    assert_eq!(plan["executable"], false);
    let result = decoded(run(&["simulate", "goal", "examples/packs/matchday.json"]));
    assert_eq!(
        result["planned_dispatches"][0]["prepared"]["commands"][0]["source_id"],
        "goal-celebration"
    );
}
#[test]
fn deck_confirmation_and_every_sample_button_reach_simulator() {
    for button in [
        "goal",
        "countdown",
        "lower-third",
        "lower-entry",
        "brb",
        "live",
        "community",
        "celebrate",
    ] {
        let result = decoded(run(&[
            "deck-press",
            "examples/decks/matchday.json",
            "examples/packs/matchday.json",
            button,
            "--confirm",
        ]));
        assert_eq!(result["simulation"]["live_commands_sent"], 0);
        assert!(!result["simulation"]["jobs"].as_array().unwrap().is_empty());
        assert_eq!(
            result["simulation"]["jobs"][0]["state"], "simulated",
            "{button}: {result}"
        );
    }
    let denied = run(&[
        "deck-press",
        "examples/decks/matchday.json",
        "examples/packs/matchday.json",
        "brb",
    ]);
    assert!(!denied.status.success());
    let error: Value = serde_json::from_slice(&denied.stderr).unwrap();
    assert_eq!(error["error"]["code"], "DECK_CONFIRMATION");
}
#[test]
fn schemas_and_checked_in_rule_example_remain_valid() {
    for entry in
        std::fs::read_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/packs")).unwrap()
    {
        let path = entry.unwrap().path();
        decoded(run(&["validate-pack", path.to_str().unwrap()]));
    }
    let generated = decoded(run(&["example-config"]));
    let checked: Value =
        serde_json::from_str(include_str!("../examples/rules/matchday.json")).unwrap();
    assert_eq!(generated, checked);
    decoded(run(&["validate-config", "examples/rules/matchday.json"]));
    for kind in ["goal", "chat", "donation"] {
        decoded(run(&[
            "validate-event",
            &format!("examples/events/{kind}.jsonl"),
        ]));
    }
}
