//! Data projection only. Owner approval/binding provenance must be checked BEFORE
//! calling this function. A payload or `simulated`/`origin` field grants no trust.
use crate::{Result, ipc::SAFE_INTEGER};
use serde_json::{Value, json};
pub fn goal_message(sequence: u64, source_event: &Value) -> Result<Value> {
    if sequence == 0 || sequence > SAFE_INTEGER {
        return Err("MESSAGE_SEQUENCE");
    }
    let payload = &source_event["payload"];
    if payload["kind"] != "motive.custom_event" || payload["name"] != "goal-scored" {
        return Err("BINDING_EVENT");
    }
    let fields = payload["fields"].as_object().ok_or("BINDING_FIELDS")?;
    let mut projected = serde_json::Map::new();
    for (name, kind) in [("team", "string"), ("home", "int"), ("away", "int")] {
        let field = fields
            .get(name)
            .and_then(Value::as_object)
            .ok_or("BINDING_FIELDS")?;
        if field.len() != 2 || field.get("type") != Some(&json!(kind)) {
            return Err("BINDING_FIELD_TYPE");
        }
        let value = field.get("value").ok_or("BINDING_FIELDS")?;
        let valid = if kind == "string" {
            value.as_str().is_some_and(|s| {
                s.encode_utf16().count() <= 60 && !s.chars().any(|c| (c as u32) < 32)
            })
        } else {
            value.as_i64().is_some_and(|n| (0..=99).contains(&n))
        };
        if !valid {
            return Err("BINDING_FIELD_VALUE");
        }
        projected.insert(name.to_owned(), value.clone());
    }
    Ok(json!({"version":1,"seq":sequence,"kind":"event","name":"goal.scored","payload":projected}))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn projects_actual_show_control_fixture_and_never_forwards_extra_fields() {
        let events: Value = serde_json::from_str(include_str!(
            "../../../../element-lab/tests/fixtures/goal-events.json"
        ))
        .unwrap();
        let mut e = events[0].clone();
        e["payload"]["fields"]["token"] = json!({"type":"string","value":"discarded-sentinel"});
        let message = goal_message(1, &e).unwrap();
        assert_eq!(message["payload"].as_object().unwrap().len(), 3);
        assert!(!message.to_string().contains("discarded-sentinel"));
        e["payload"]["fields"]["home"]["value"] = json!(100);
        assert_eq!(goal_message(2, &e), Err("BINDING_FIELD_VALUE"));
    }
}
