//! Offline contract validation only. Never links Motive, libobs or a device adapter.
use motive_show_control::{
    actions::{self, Action},
    deck::{ButtonTarget, Deck, DeckPress, DeckRuntime},
    model::{Error, Event, Payload},
    packs::{Capability, CreatorPack, PropertyValue},
    runtime::{Config, JobState},
    simulation,
};
use serde_json::{Value, json};
use std::{fs, path::Path};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn ensure(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}

fn read(path: &Path) -> Result<String> {
    // Explicit local authoring inputs; no symlink following at this boundary.
    let meta = fs::symlink_metadata(path)?;
    ensure(
        meta.is_file() && meta.len() <= 1_048_576,
        "INPUT_FILE_BOUNDARY",
    )?;
    Ok(fs::read_to_string(path)?)
}

fn expect_reject(name: &str, candidate: Value, code: &str) -> Result<Value> {
    match CreatorPack::from_json(&candidate.to_string()) {
        Err(e) => {
            ensure(
                e.code == code,
                &format!("{name}: expected {code}, got {}", e.code),
            )?;
            Ok(json!({"case":name,"status":"PASS","rejected_with":e.code}))
        }
        Ok(_) => Err(format!("{name}: unexpectedly accepted").into()),
    }
}

fn adversarial(
    pack: &CreatorPack,
    raw: &Value,
    deck: &Deck,
    config: &Config,
) -> Result<Vec<Value>> {
    let mut cases = Vec::new();
    for (name, key, value, code) in [
        (
            "unknown_executable_field",
            "shell",
            json!("do-not-execute"),
            "PACK_SCHEMA",
        ),
        ("future_schema", "schema_version", json!(99), "PACK_VERSION"),
        (
            "undeclared_capability",
            "requires",
            json!([]),
            "PACK_CAPABILITY",
        ),
    ] {
        let mut changed = raw.clone();
        changed[key] = value;
        cases.push(expect_reject(name, changed, code)?);
    }
    let mut changed = raw.clone();
    changed["scenes"][0]["layers"][0]["overlay_id"] = json!("missing-source");
    cases.push(expect_reject("missing_source", changed, "PACK_REFERENCE")?);
    let mut changed = raw.clone();
    changed["budget"]["max_estimated_texture_bytes"] = json!(1);
    cases.push(expect_reject(
        "underbudget_texture",
        changed,
        "PACK_BUDGET",
    )?);
    let mut changed = raw.clone();
    changed["scenes"][0]["layers"][0]["vertical"]["width"] = json!(0);
    cases.push(expect_reject(
        "zero_vertical_width",
        changed,
        "PACK_LAYOUT",
    )?);
    let mut changed = raw.clone();
    let base = changed["scenes"][0]["layers"][0].clone();
    changed["scenes"][0]["layers"] = Value::Array(vec![base; 33]);
    cases.push(expect_reject(
        "global_layer_overflow",
        changed,
        "PACK_LIMIT",
    )?);
    if !pack.resources.is_empty() {
        let mut changed = raw.clone();
        changed["resources"][0]["file_name"] = json!("../secret.png");
        cases.push(expect_reject(
            "resource_path_traversal",
            changed,
            "PACK_RESOURCE",
        )?);
    }
    if !pack.animations.is_empty() {
        let mut changed = raw.clone();
        changed["animations"][0]["kind"] = json!("fade_in");
        changed["animations"][0]["easing"] = json!("ease_out");
        cases.push(expect_reject(
            "unsupported_fade_easing",
            changed,
            "PACK_ANIMATION",
        )?);
    }
    if let Some(property) = pack.properties.first() {
        let mut copy = pack.clone();
        let wrong = match property.value {
            PropertyValue::Text(_) => PropertyValue::Color(0),
            PropertyValue::Color(_) => PropertyValue::Text("wrong type".into()),
        };
        ensure(
            copy.set_property(&property.id, wrong).is_err(),
            "PROPERTY_TYPE_ACCEPTED",
        )?;
        ensure(copy == *pack, "FAILED_PROPERTY_MUTATED_PACK")?;
        copy.set_property(&property.id, property.value.clone())?;
        cases.push(json!({"case":"typed_property_transaction","status":"PASS"}));
    }
    if let Some(button) = deck.buttons.iter().find(|b| b.enabled) {
        let mut copy = deck.clone();
        let selected = copy.buttons.iter_mut().find(|b| b.id == button.id).unwrap();
        selected.sensitive = true;
        selected.cooldown_ms = 1000;
        let mut runtime = DeckRuntime::new(copy)?;
        let error = runtime.press(&button.id, 0, false).unwrap_err();
        ensure(
            error.code == "DECK_CONFIRMATION",
            "MISSING_LOCAL_CONFIRMATION",
        )?;
        let press = runtime.press(&button.id, 0, true)?;
        ensure(press.simulated, "NON_SIMULATED_PRESS")?;
        ensure(
            runtime.press(&button.id, 1, true).unwrap_err().code == "DECK_PENDING",
            "MISSING_PENDING_GUARD",
        )?;
        runtime.finish_simulation(press.request_id, 1, None)?;
        ensure(
            runtime.press(&button.id, 2, true).unwrap_err().code == "DECK_COOLDOWN",
            "MISSING_COOLDOWN",
        )?;
        runtime.press(&button.id, 1000, true)?;
        ensure(
            runtime.press(&button.id, 999, true).unwrap_err().code == "CLOCK_REGRESSION",
            "CLOCK_REGRESSION_ACCEPTED",
        )?;
        cases.push(json!({"case":"deck_confirmation_pending_cooldown_monotonic_clock","status":"PASS","mode":"simulation_only"}));
    }
    if let Some(rule) = config.rules.first() {
        let mut broken = config.clone();
        broken.rules[0].actions = vec![Action::ShowOverlay {
            source_id: "absent-source".into(),
        }];
        ensure(pack.rule_ids.contains(&rule.id), "UNDECLARED_TEST_RULE")?;
        ensure(
            simulation::validate_pack_rules(pack, &broken)
                .unwrap_err()
                .code
                == "PACK_SOURCE_MISSING",
            "MISSING_RULE_TARGET_ACCEPTED",
        )?;
        cases.push(json!({"case":"rule_cross_reference_missing","status":"PASS","rejected_with":"PACK_SOURCE_MISSING"}));
    }
    if let Some(source) = pack.overlays.iter().find(|source| {
        matches!(
            source.definition,
            motive_show_control::packs::VisualDefinition::Shape { .. }
        )
    }) {
        let invalid = Action::CountdownStart {
            source_id: source.id.clone(),
        };
        let snapshot = simulation::pack_snapshot(pack)?;
        ensure(
            actions::prepare(&invalid, &snapshot, None)
                .unwrap_err()
                .code
                == "INVALID_OVERLAY_ACTION",
            "WRONG_WIDGET_TARGET_ACCEPTED",
        )?;
        cases.push(json!({"case":"countdown_cannot_target_shape","status":"PASS","rejected_with":"INVALID_OVERLAY_ACTION"}));
    }
    Ok(cases)
}

fn inspect_actions(config: &Config, pack: &CreatorPack) -> Result<Vec<Value>> {
    let mut snapshot = simulation::pack_snapshot(pack)?;
    let mut results = Vec::new();
    for rule in &config.rules {
        ensure(
            pack.rule_ids.contains(&rule.id) || rule.id == "deck-direct",
            "UNDECLARED_RULE",
        )?;
        for action in &rule.actions {
            for leaf in action.flattened()? {
                // Inspect the target scene without inventing an on-air scene.
                if let Action::Animate { scene_id, .. } = &leaf {
                    snapshot.active_scene = scene_id.clone();
                }
                let result = actions::prepare(&leaf, &snapshot, None);
                match result {
                    Ok(_) => results.push(
                        json!({"rule":rule.id,"action":leaf,"status":"VALID_TYPED_INTENTION"}),
                    ),
                    Err(Error { code, .. })
                        if code == "CAPABILITY_UNAVAILABLE" && !rule.enabled =>
                    {
                        results.push(json!({"rule":rule.id,"action":leaf,"status":"DISABLED_UNAVAILABLE","code":code}));
                    }
                    Err(e) => return Err(e.into()),
                }
            }
        }
    }
    Ok(results)
}

fn validate(directory: &Path) -> Result<Value> {
    let input = read(&directory.join("manifest.json"))?;
    let pack = CreatorPack::from_json(&input)?;
    let raw: Value = serde_json::from_str(&input)?;
    let config = Config::from_json(&read(&directory.join("rules.json"))?)?;
    let deck = Deck::from_json(&read(&directory.join("deck.json"))?)?;
    simulation::validate_pack_rules(&pack, &config)?;
    let actions = inspect_actions(&config, &pack)?;
    let mut buttons = Vec::new();
    for button in &deck.buttons {
        let press = DeckPress {
            request_id: 1,
            button_id: button.id.clone(),
            event_kind: "manual.button_pressed".into(),
            target: button.target.clone(),
            simulated: true,
        };
        let selected = match simulation::deck_actions(&press, &pack, &config) {
            Ok(selected) => selected,
            Err(error) if !button.enabled && error.code == "RULE_TRIGGER_MISMATCH" => {
                buttons.push(json!({"id":button.id,"enabled":false,"status":"DISABLED_PROVIDER_RULE","press_would_reject":"DECK_DISABLED","manual_binding_would_reject":error.code}));
                continue;
            }
            Err(error) => return Err(error.into()),
        };
        let prepared = inspect_actions(&selected, &pack)?;
        if let ButtonTarget::Rule { rule_id } | ButtonTarget::Composite { rule_id } = &button.target
        {
            ensure(pack.rule_ids.contains(rule_id), "DECK_RULE_NOT_DECLARED")?;
        }
        let mut snapshot = simulation::pack_snapshot(&pack)?;
        for rule in &selected.rules {
            for action in &rule.actions {
                for leaf in action.flattened()? {
                    if let Action::Animate { scene_id, .. } = leaf {
                        snapshot.active_scene = scene_id;
                    }
                }
            }
        }
        let event = simulation::event(
            &format!("check-{}", button.id),
            Payload::ManualButtonPressed {
                button_id: button.id.clone(),
            },
        );
        let rehearsal = simulation::run_events(&button.id, selected, vec![event], snapshot)?;
        if button.enabled {
            ensure(
                !rehearsal.jobs.is_empty(),
                &format!("BUTTON_CONDITIONS_NEVER_MATCH: {}", button.id),
            )?;
            ensure(
                rehearsal.jobs.iter().all(|job| {
                    job.state == JobState::Simulated || job.state == JobState::Completed
                }),
                &format!("BUTTON_REHEARSAL_REJECTED: {}", button.id),
            )?;
        }
        ensure(rehearsal.live_commands_sent == 0, "LIVE_COMMAND_FORBIDDEN")?;
        buttons.push(json!({"id":button.id,"enabled":button.enabled,"actions":prepared,"rehearsal":rehearsal}));
    }
    let events_path = directory.join("events.jsonl");
    let mut events = Vec::new();
    if events_path.exists() {
        for line in read(&events_path)?
            .lines()
            .filter(|line| !line.trim().is_empty())
        {
            let event = Event::from_json(line)?;
            ensure(event.simulated, "AUTHORING_EVENT_MUST_BE_SIMULATED")?;
            ensure(
                pack.events.iter().any(|kind| kind == event.kind()),
                "UNDECLARED_EVENT",
            )?;
            events.push(json!({"id":event.id,"kind":event.kind(),"simulated":true}));
        }
    }
    let plan = pack.plan(&Capability::h12_contracts())?;
    ensure(
        !plan.executable && plan.unavailable.is_empty(),
        "INVALID_BASELINE_PLAN",
    )?;
    let missing = pack.plan(&Default::default())?;
    ensure(
        missing.unavailable.len() == pack.requires.len(),
        "MISSING_CAPABILITY_NOT_REPORTED",
    )?;
    Ok(json!({
        "pack_id":pack.id,"version":pack.version,"status":"PASS",
        "counts":{"scenes":pack.scenes.len(),"sources":pack.overlays.len(),"layers":pack.scenes.iter().map(|s|s.layers.len()).sum::<usize>(),"animations":pack.animations.len(),"properties":pack.properties.len(),"resources":pack.resources.len(),"rules":config.rules.len(),"buttons":deck.buttons.len()},
        "plan":plan,"rules":actions,"deck":buttons,"events":events,
        "adversarial_checks":adversarial(&pack,&raw,&deck,&config)?,
        "native_execution":false,"live_commands_sent":0
    }))
}

fn main() {
    let arguments: Vec<_> = std::env::args().skip(1).collect();
    let directories = if arguments.is_empty() {
        vec![
            "creator-experience/packs/creator-tech".into(),
            "creator-experience/packs/neon-arena".into(),
        ]
    } else {
        arguments
    };
    let mut failed = false;
    let reports: Vec<_> = directories
        .iter()
        .map(|directory| match validate(Path::new(directory)) {
            Ok(report) => report,
            Err(error) => {
                failed = true;
                json!({"directory":directory,"status":"FAIL","error":error.to_string()})
            }
        })
        .collect();
    println!("{}", serde_json::to_string_pretty(&json!({"mode":"offline_contract_validation","status":if failed {"FAIL"} else {"PASS"},"production_connection":false,"reports":reports})).unwrap());
    if failed {
        std::process::exit(1);
    }
}
