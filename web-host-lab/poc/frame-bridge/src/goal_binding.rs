//! Owned Goal fixture adapter. No Production authority and no package constructor.
use motive_browser_contracts::{Identity, ipc::strict_json};
use motive_creator_binding::{Binding, FixtureReview, OfflineOwner};
use motive_show_control::{
    model::Event,
    providers::{AcceptedEvent, VerifiedIngress},
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, ptr, slice};

pub struct GoalBinding {
    owner: OfflineOwner,
    binding: Binding,
    event: AcceptedEvent,
    goal_sent: bool,
    last_ms: u64,
}
impl GoalBinding {
    fn create(generation: u64, definition_sha256: &str) -> Result<Self, &'static str> {
        let manifest: Value = serde_json::from_str(include_str!(
            "../../../../element-lab/web-elements/goal-celebration/web-element.json"
        ))
        .map_err(|_| "FIXTURE_MANIFEST")?;
        let owner = OfflineOwner::new("simulation.h18-cef-fixture", 1)?;
        let binding = owner.review_goal_fixture(FixtureReview {
            binding_id: "goal-fixture".into(),
            definition_sha256: definition_sha256.into(),
            identity: Identity::new(1, generation)?,
            origin: "simulation.h18-goal".into(),
            manifest,
            properties: json!({"testMode":false,"holdMs":1000}),
        })?;
        let events: Value = serde_json::from_str(include_str!(
            "../../../../element-lab/tests/fixtures/goal-events.json"
        ))
        .map_err(|_| "FIXTURE_EVENT")?;
        let mut event = Event::from_json(&events[0].to_string()).map_err(|_| "FIXTURE_EVENT")?;
        event.origin = "simulation.h18-goal".into();
        let event = VerifiedIngress::simulation("simulation.h18-goal", BTreeSet::new())
            .map_err(|_| "FIXTURE_EVENT")?
            .accept(event)
            .map_err(|_| "FIXTURE_EVENT")?;
        Ok(Self {
            owner,
            binding,
            event,
            goal_sent: false,
            last_ms: 0,
        })
    }
    fn status(&mut self, data: &[u8], now: u64) -> Result<Option<Value>, &'static str> {
        if now < self.last_ms {
            return Err("CLOCK_REGRESSION");
        };
        self.last_ms = now;
        let v = strict_json(data, 512)?;
        let obj = v.as_object().ok_or("STATUS_SCHEMA")?;
        let id = self.binding.identity();
        let identity = |value: &Value| {
            value.as_object().is_some_and(|o| o.len() == 2)
                && value["instance"].as_u64() == Some(id.instance)
                && value["generation"].as_u64() == Some(id.generation)
        };
        let output = match v["kind"].as_str() {
            Some("renderer_ready")
                if obj.len() == 3
                    && identity(&v["identity"])
                    && v["native_terminal_outcome"] == false =>
            {
                self.binding.ready(&self.owner, id, now)?;
                Some(self.binding.initial_properties(&self.owner, now)?)
            }
            Some("visual_ack") => {
                self.binding.acknowledge(&self.owner, data)?;
                if v["seq"] == 1 && v["accepted"] == true && !self.goal_sent {
                    self.goal_sent = true;
                    Some(self.binding.goal(&self.owner, &self.event, now)?)
                } else {
                    None
                }
            }
            Some("visual_state")
                if obj.len() == 5
                    && obj.contains_key("sequence")
                    && identity(&v["identity"])
                    && v["native_terminal_outcome"] == false =>
            {
                match v["state"].as_str() {
                    Some("ready") if !v["sequence"].is_null() => self.binding.visual_complete(
                        &self.owner,
                        id,
                        v["sequence"].as_u64().ok_or("STATUS_SEQUENCE")?,
                        now,
                    )?,
                    Some("active" | "ready" | "cancelled") if v["sequence"].is_null() => {}
                    Some("error" | "disposed") if v["sequence"].is_null() => self.binding.revoke(),
                    _ => return Err("STATUS_STATE"),
                }
                None
            }
            _ => return Err("STATUS_SCHEMA"),
        };
        Ok(output.map(|d| d.envelope().clone()))
    }
}

/// # Safety
/// `hash` spans `length` immutable bytes belonging to the trusted build inventory.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_goal_create(
    generation: u64,
    hash: *const u8,
    length: usize,
) -> *mut GoalBinding {
    if hash.is_null() || length != 64 {
        return ptr::null_mut();
    };
    let Ok(hash) = std::str::from_utf8(unsafe { slice::from_raw_parts(hash, length) }) else {
        return ptr::null_mut();
    };
    match GoalBinding::create(generation, hash) {
        Ok(s) => Box::into_raw(Box::new(s)),
        Err(_) => ptr::null_mut(),
    }
}
/// # Safety
/// Handle is live and exclusively held on CEF UI thread. Data/output span their
/// declared lengths. Returns 0 for observation only, positive JSON byte count,
/// or negative failure. A renderer reply can never create owner authority.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_goal_status(
    handle: *mut GoalBinding,
    data: *const u8,
    length: usize,
    now_ms: u64,
    output: *mut u8,
    capacity: usize,
) -> isize {
    if handle.is_null() || data.is_null() || output.is_null() || length > 512 || capacity < 16384 {
        return -1;
    };
    let state = unsafe { &mut *handle };
    match state.status(unsafe { slice::from_raw_parts(data, length) }, now_ms) {
        Ok(Some(value)) => {
            let Ok(bytes) = serde_json::to_vec(&value) else {
                return -2;
            };
            if bytes.len() > capacity {
                return -3;
            };
            unsafe { ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len()) };
            bytes.len() as isize
        }
        Ok(None) => 0,
        Err(_) => -4,
    }
}
/// # Safety
/// Handle is live, exclusive, and destroyed once after native callbacks stop.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_goal_destroy(handle: *mut GoalBinding) {
    if !handle.is_null() {
        let mut state = unsafe { Box::from_raw(handle) };
        state.binding.revoke();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn status(value: Value) -> Vec<u8> {
        serde_json::to_vec(&value).unwrap()
    }
    #[test]
    fn native_fixture_uses_existing_owner_grant_properties_and_event_projection() {
        let mut s = GoalBinding::create(7, &"a".repeat(64)).unwrap();
        let properties=s.status(&status(json!({"kind":"renderer_ready","identity":{"instance":1,"generation":7},"native_terminal_outcome":false})),10).unwrap().unwrap();
        assert_eq!(properties["message"]["kind"], "properties");
        let goal=s.status(&status(json!({"kind":"visual_ack","protocol":1,"instance":1,"generation":7,"seq":1,"accepted":true})),11).unwrap().unwrap();
        assert_eq!(goal["message"]["name"], "goal.scored");
        assert_eq!(
            goal["message"]["payload"],
            json!({"team":"Club del Puerto","home":2,"away":1})
        );
        assert_eq!(goal["message"]["payload"].as_object().unwrap().len(), 3);
        assert!(s.status(&status(json!({"kind":"visual_ack","protocol":1,"instance":1,"generation":7,"seq":1,"accepted":true})),12).is_err());
    }
    #[test]
    fn forged_stale_secret_and_replayed_statuses_do_not_mint_commands() {
        let mut s = GoalBinding::create(7, &"a".repeat(64)).unwrap();
        for value in [
            json!({"kind":"start_recording"}),
            json!({"kind":"renderer_ready","identity":{"instance":1,"generation":6},"native_terminal_outcome":false}),
            json!({"kind":"renderer_ready","identity":{"instance":1,"generation":7},"native_terminal_outcome":true}),
            json!({"kind":"renderer_ready","identity":{"instance":1,"generation":7},"native_terminal_outcome":false,"secret":"not forwarded"}),
        ] {
            assert!(s.status(&status(value), 1).is_err());
        }
        assert!(
            s.status(b"{\"kind\":\"visual_ack\",\"kind\":\"renderer_ready\"}", 2)
                .is_err()
        );
        assert!(s.status(&vec![b' '; 513], 3).is_err());
        assert!(s.status(b"{}", 2).is_err());
    }
}
