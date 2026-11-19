//! Owned fixture process for the loopback QA harness, never a production host.
use motive_browser_contracts::{Identity, ipc::strict_json};
use motive_creator_binding::{FixtureReview, OfflineOwner};
use motive_show_control::{model::Event, providers::VerifiedIngress};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    io::{self, BufRead, Write},
    time::Instant,
};
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        std::process::exit(2);
    }
    let generation: u64 = args[2].parse().expect("fixture generation");
    let manifest: Value = serde_json::from_str(include_str!(
        "../../../element-lab/web-elements/goal-celebration/web-element.json"
    ))
    .unwrap();
    let owner = OfflineOwner::new("simulation.h18-fixture", 1).unwrap();
    let mut binding = owner
        .review_goal_fixture(FixtureReview {
            binding_id: "goal-fixture".into(),
            definition_sha256: args[1].clone(),
            identity: Identity::new(1, generation).unwrap(),
            origin: "simulation.h18-goal".into(),
            manifest,
            properties: json!({"testMode":false,"holdMs":1000}),
        })
        .unwrap();
    let events: Value = serde_json::from_str(include_str!(
        "../../../element-lab/tests/fixtures/goal-events.json"
    ))
    .unwrap();
    let mut event = Event::from_json(&events[0].to_string()).unwrap();
    event.origin = "simulation.h18-goal".into();
    let ingress = VerifiedIngress::simulation("simulation.h18-goal", BTreeSet::new()).unwrap();
    let accepted = ingress.accept(event).unwrap();
    let start = Instant::now();
    for line in io::stdin().lock().lines() {
        let Ok(line) = line else { break };
        let now = start.elapsed().as_millis() as u64;
        let result = (|| -> Result<Value, &'static str> {
            let request = strict_json(line.as_bytes(), 1024)?;
            let command = request["command"].as_str().ok_or("FIXTURE_COMMAND")?;
            let keys = if matches!(command, "ack" | "complete") {
                2
            } else {
                1
            };
            if request.as_object().ok_or("FIXTURE_COMMAND")?.len() != keys {
                return Err("FIXTURE_COMMAND");
            }
            let dispatch = match command {
                "ready" => {
                    binding.ready(&owner, binding.identity(), now)?;
                    None
                }
                "properties" => Some(binding.initial_properties(&owner, now)?),
                "goal" => Some(binding.goal(&owner, &accepted, now)?),
                "cancel" => Some(binding.cancel(&owner, now)?),
                "resume" => Some(binding.resume(&owner, now)?),
                "dispose" => Some(binding.dispose(&owner, now)?),
                "ack" => {
                    binding.acknowledge(
                        &owner,
                        &serde_json::to_vec(&request["ack"]).map_err(|_| "ACK_SCHEMA")?,
                    )?;
                    None
                }
                "complete" => {
                    binding.visual_complete(
                        &owner,
                        binding.identity(),
                        request["sequence"].as_u64().ok_or("MESSAGE_SEQUENCE")?,
                        now,
                    )?;
                    None
                }
                "revoke" => {
                    binding.revoke();
                    None
                }
                _ => return Err("FIXTURE_COMMAND"),
            };
            Ok(
                json!({"ok":true,"dispatch":dispatch.map(|d|d.envelope().clone()),"now_ms":now,
                "scope":binding.review_summary(),"state":format!("{:?}",binding.state()),"native_terminal_outcome":false}),
            )
        })();
        let output = match result {
            Ok(v) => v,
            Err(code) => json!({"ok":false,"code":code,"native_terminal_outcome":false}),
        };
        println!("{output}");
        io::stdout().flush().unwrap();
    }
}
