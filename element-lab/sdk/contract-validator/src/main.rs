//! Read-only contract adapter. No Motive, libobs, socket or backend dependency.
use motive_show_control::{
    actions::{self, Action},
    model::{Error, Event},
    packs::{Capability, CreatorPack},
    runtime::Config,
    simulation,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{self, Read};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    pack: Value,
    rules: Value,
    #[serde(default)]
    events: Vec<Value>,
}

fn validate(input: &str) -> Result<Value, Error> {
    let request: Request =
        serde_json::from_str(input).map_err(|e| Error::new("ADAPTER_SCHEMA", &e.to_string()))?;
    let pack = CreatorPack::from_json(&request.pack.to_string())?;
    let rules = Config::from_json(&request.rules.to_string())?;
    simulation::validate_pack_rules(&pack, &rules)?;
    if rules.rules.iter().any(|r| !pack.rule_ids.contains(&r.id)) {
        return Err(Error::new(
            "UNDECLARED_RULE",
            "Every rule must be declared by the pack",
        ));
    }
    let mut snapshot = simulation::pack_snapshot(&pack)?;
    let mut prepared = 0;
    for rule in &rules.rules {
        for action in &rule.actions {
            for leaf in action.flattened()? {
                // A hypothetical active scene for static preparation, not an observed runtime.
                if let Action::Animate { scene_id, .. }
                | Action::TriggerAnimatedWidget { scene_id, .. } = &leaf
                {
                    snapshot.active_scene = scene_id.clone();
                }
                actions::prepare(&leaf, &snapshot, None)?;
                prepared += 1;
            }
        }
    }
    let plan = pack.plan(&Capability::h12_contracts())?;
    let events = request
        .events
        .iter()
        .map(|e| Event::from_json(&e.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    let rehearsal = if events.is_empty() {
        None
    } else {
        Some(simulation::run_events(
            "element-lab-explicit-fixture",
            rules,
            events,
            simulation::pack_snapshot(&pack)?,
        )?)
    };
    Ok(
        json!({"status":"PASS", "mode":"real_show_control_contract_offline", "pack_id":pack.id,
        "prepared_actions":prepared,"plan":plan,"rehearsal":rehearsal,"production_connected":false,"native_render_verified":false}),
    )
}
fn main() {
    let mut input = String::new();
    let result = match io::stdin().take(1_048_577).read_to_string(&mut input) {
        Ok(_) if input.len() <= 1_048_576 => validate(&input),
        _ => Err(Error::new("ADAPTER_SIZE", "UTF-8 input <= 1 MiB required")),
    };
    match result {
        Ok(value) => println!("{value}"),
        Err(error) => {
            println!("{}", json!({"status":"FAIL","error":error}));
            std::process::exit(1);
        }
    }
}
