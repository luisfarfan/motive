use motive_browser_contracts::{Identity, lifecycle::State};
use motive_creator_binding::{Binding, FixtureReview, Observation, OfflineOwner};
use motive_show_control::{
    model::Event,
    providers::{AcceptedEvent, VerifiedIngress},
};
use serde_json::{Value, json};
use std::collections::BTreeSet;
fn manifest() -> Value {
    serde_json::from_str(include_str!(
        "../../../element-lab/web-elements/goal-celebration/web-element.json"
    ))
    .unwrap()
}
fn event(origin: &str) -> AcceptedEvent {
    let v: Value = serde_json::from_str(include_str!(
        "../../../element-lab/tests/fixtures/goal-events.json"
    ))
    .unwrap();
    let mut event = Event::from_json(&v[0].to_string()).unwrap();
    event.origin = origin.into();
    VerifiedIngress::simulation(origin, BTreeSet::new())
        .unwrap()
        .accept(event)
        .unwrap()
}
fn fixture() -> (OfflineOwner, Binding) {
    let owner = OfflineOwner::new("simulation.owner", 42).unwrap();
    let binding = owner
        .review_goal_fixture(FixtureReview {
            binding_id: "goal-binding".into(),
            definition_sha256: "a".repeat(64),
            identity: Identity::new(5, 7).unwrap(),
            origin: "simulation.goal".into(),
            manifest: manifest(),
            properties: json!({"testMode":false,"team":"Reviewed team"}),
        })
        .unwrap();
    (owner, binding)
}
fn ack(binding: &Binding, seq: u64, accepted: bool) -> Vec<u8> {
    serde_json::to_vec(&json!({"protocol":1,"instance":binding.identity().instance,"generation":binding.identity().generation,
        "kind":"visual_ack","seq":seq,"accepted":accepted})).unwrap()
}
fn ready(owner: &OfflineOwner, binding: &mut Binding) {
    binding.ready(owner, binding.identity(), 0).unwrap();
    let p = binding.initial_properties(owner, 0).unwrap();
    binding
        .acknowledge(
            owner,
            &ack(binding, p.message()["seq"].as_u64().unwrap(), true),
        )
        .unwrap();
}
#[test]
fn binds_owner_session_revision_and_rejects_package_authority() {
    assert!(OfflineOwner::new("production", 1).is_err());
    let (mut owner, mut binding) = fixture();
    let impostor = OfflineOwner::new("simulation.owner", 42).unwrap();
    assert_eq!(
        binding.ready(&impostor, binding.identity(), 0),
        Err("OWNER_SESSION")
    );
    owner.advance_revision().unwrap();
    assert_eq!(
        binding.ready(&owner, binding.identity(), 0),
        Err("OWNER_REVISION")
    );
}
#[test]
fn validates_identity_and_approved_properties_before_dispatch() {
    let (owner, mut binding) = fixture();
    assert_eq!(
        binding.ready(&owner, Identity::new(5, 6).unwrap(), 0),
        Err("STALE_GENERATION")
    );
    binding.ready(&owner, binding.identity(), 0).unwrap();
    assert_eq!(
        binding.goal(&owner, &event("simulation.goal"), 0).err(),
        Some("PROPERTIES_UNACKNOWLEDGED")
    );
    let p = binding.initial_properties(&owner, 0).unwrap();
    assert_eq!(p.message()["properties"]["team"], "Reviewed team");
    assert_eq!(p.message()["properties"]["testMode"], false);
    binding
        .acknowledge(&owner, &ack(&binding, 1, true))
        .unwrap();
    assert!(binding.goal(&owner, &event("simulation.goal"), 1).is_ok());
}
#[test]
fn projects_real_event_contract_and_never_uses_event_flags_as_trust() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    assert_eq!(
        binding.goal(&owner, &event("simulation.other"), 1).err(),
        Some("BINDING_ORIGIN")
    );
    let d = binding.goal(&owner, &event("simulation.goal"), 2).unwrap();
    assert_eq!(d.message()["name"], "goal.scored");
    assert_eq!(
        d.message()["payload"],
        json!({"team":"Club del Puerto","home":2,"away":1})
    );
    for forbidden in [
        "origin",
        "correlation_id",
        "external_id",
        "simulated",
        "timestamp_ms",
    ] {
        assert!(!d.envelope().to_string().contains(forbidden));
    }
    assert_eq!(binding.state(), State::Active);
}
#[test]
fn ack_is_not_a_native_or_lifecycle_completion_and_replay_is_rejected() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    binding.goal(&owner, &event("simulation.goal"), 1).unwrap();
    let a = ack(&binding, 2, true);
    assert_eq!(
        binding.acknowledge(&owner, &a),
        Ok(Observation::RendererAcknowledged {
            sequence: 2,
            accepted: true
        })
    );
    assert_eq!(binding.state(), State::Active);
    assert_eq!(binding.acknowledge(&owner, &a), Err("STALE_ACK"));
    assert_eq!(
        binding.visual_complete(&owner, binding.identity(), 1, 2),
        Err("STALE_COMPLETION")
    );
    binding
        .visual_complete(&owner, binding.identity(), 2, 3)
        .unwrap();
    assert_eq!(binding.state(), State::Ready);
}
#[test]
fn cancellation_disposal_revoke_stale_completions_and_fail_closed() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    binding.goal(&owner, &event("simulation.goal"), 1).unwrap();
    binding.cancel(&owner, 2).unwrap();
    assert_eq!(
        binding.visual_complete(&owner, binding.identity(), 2, 3),
        Err("STALE_COMPLETION")
    );
    binding.resume(&owner, 4).unwrap();
    binding.dispose(&owner, 5).unwrap();
    assert_eq!(
        binding.goal(&owner, &event("simulation.goal"), 6).err(),
        Some("BINDING_REVOKED")
    );
    assert_eq!(
        binding.acknowledge(&owner, &ack(&binding, 5, true)),
        Err("BINDING_REVOKED")
    );
}
#[test]
fn watchdog_timeout_never_auto_replays_or_restarts() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    binding.goal(&owner, &event("simulation.goal"), 1).unwrap();
    assert_eq!(binding.poll(15001), Err("DEADLINE"));
    assert_eq!(binding.state(), State::Failed);
    assert_eq!(binding.resume(&owner, 15002).err(), Some("LIFECYCLE"));
    assert!(binding.cancel(&owner, 15003).is_ok());
}
#[test]
fn receiver_rejects_unknown_diagnostic_text_duplicate_keys_and_old_generation() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    binding.goal(&owner, &event("simulation.goal"), 1).unwrap();
    let mut v: Value = serde_json::from_slice(&ack(&binding, 2, true)).unwrap();
    v["error"] = json!("private path sentinel");
    assert_eq!(
        binding.acknowledge(&owner, &serde_json::to_vec(&v).unwrap()),
        Err("ACK_SCHEMA")
    );
    assert_eq!(
        binding.acknowledge(&owner, br#"{"protocol":1,"protocol":1}"#),
        Err("MESSAGE_JSON")
    );
    v.as_object_mut().unwrap().remove("error");
    v["generation"] = json!(6);
    assert_eq!(
        binding.acknowledge(&owner, &serde_json::to_vec(&v).unwrap()),
        Err("STALE_GENERATION")
    );
}
#[test]
fn rejected_properties_cannot_start_a_visual() {
    let (owner, mut binding) = fixture();
    binding.ready(&owner, binding.identity(), 0).unwrap();
    binding.initial_properties(&owner, 0).unwrap();
    binding
        .acknowledge(&owner, &ack(&binding, 1, false))
        .unwrap();
    assert_eq!(binding.state(), State::Failed);
    assert_eq!(
        binding.goal(&owner, &event("simulation.goal"), 1).err(),
        Some("NOT_READY")
    );
}
#[test]
fn invalid_review_cannot_return_a_binding() {
    let owner = OfflineOwner::new("simulation.owner", 42).unwrap();
    for properties in [
        json!({"home":100}),
        json!({"token":"private"}),
        json!({"team":"a\n"}),
    ] {
        assert!(
            owner
                .review_goal_fixture(FixtureReview {
                    binding_id: "binding".into(),
                    definition_sha256: "a".repeat(64),
                    identity: Identity::new(1, 1).unwrap(),
                    origin: "simulation.goal".into(),
                    manifest: manifest(),
                    properties
                })
                .is_err()
        );
    }
}

#[test]
fn native_gate_rate_limit_preserves_cancel_lane() {
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    for _ in 0..7 {
        let dispatch = binding.goal(&owner, &event("simulation.goal"), 1).unwrap();
        binding
            .visual_complete(
                &owner,
                binding.identity(),
                dispatch.message()["seq"].as_u64().unwrap(),
                1,
            )
            .unwrap();
    }
    assert_eq!(
        binding.goal(&owner, &event("simulation.goal"), 1).err(),
        Some("RATE_LIMIT")
    );
    assert!(binding.cancel(&owner, 1).is_ok());
    assert_eq!(binding.state(), State::Hidden);
}

#[test]
fn internal_metadata_and_extra_fields_never_reach_visual_payload() {
    use motive_show_control::model::{Payload, Scalar};
    let (owner, mut binding) = fixture();
    ready(&owner, &mut binding);
    let mut source = event("simulation.goal").event().clone();
    source.external_id = Some("private-provider-id".into());
    if let Payload::CustomEvent { fields, .. } = &mut source.payload {
        fields.insert("token".into(), Scalar::String("private-sentinel".into()));
    }
    let accepted = VerifiedIngress::simulation("simulation.goal", BTreeSet::new())
        .unwrap()
        .accept(source)
        .unwrap();
    let dispatch = binding.goal(&owner, &accepted, 1).unwrap();
    assert!(!dispatch.envelope().to_string().contains("private"));
    assert_eq!(dispatch.message()["payload"].as_object().unwrap().len(), 3);
}
