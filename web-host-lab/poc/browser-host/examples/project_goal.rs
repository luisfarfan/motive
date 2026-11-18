use motive_browser_contracts::{Identity, ipc::Gate, projection::goal_message};
use serde_json::{Value, json};
fn main() {
    let events: Value = serde_json::from_str(include_str!(
        "../../../../element-lab/tests/fixtures/goal-events.json"
    ))
    .unwrap();
    let manifest: Value = serde_json::from_str(include_str!(
        "../../../../element-lab/web-elements/goal-celebration/web-element.json"
    ))
    .unwrap();
    let message = goal_message(1, &events[0]).unwrap();
    let envelope =
        json!({"protocol":1,"instance":1,"generation":1,"expires_ms":1000,"message":message});
    let mut gate = Gate::from_validated_manifest(Identity::new(1, 1).unwrap(), manifest).unwrap();
    gate.accept(&serde_json::to_vec(&envelope).unwrap(), 0)
        .unwrap();
    println!("{}", serde_json::to_string_pretty(&message).unwrap());
}
