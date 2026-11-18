use motive_browser_contracts::{Identity, ipc::*};
use serde_json::{Value, json};
use std::{
    io::Write,
    os::unix::net::UnixStream,
    time::{Duration, Instant},
};
fn manifest() -> Value {
    serde_json::from_str(include_str!(
        "../../../../element-lab/web-elements/goal-celebration/web-element.json"
    ))
    .unwrap()
}
fn gate() -> Gate {
    Gate::from_validated_manifest(Identity::new(1, 1).unwrap(), manifest()).unwrap()
}
fn envelope(message: Value) -> Vec<u8> {
    serde_json::to_vec(
        &json!({"protocol":1,"instance":1,"generation":1,"expires_ms":1000,"message":message}),
    )
    .unwrap()
}
fn event(seq: u64) -> Value {
    json!({"version":1,"seq":seq,"kind":"event","name":"goal.scored","payload":{"team":"Puerto","home":2,"away":1}})
}
#[test]
fn actual_goal_contract_projection() {
    assert!(matches!(
        gate().accept(&envelope(event(1)), 0),
        Ok(Visual::Event { .. })
    ));
}
#[test]
fn denies_studio_commands_extra_fields_and_wrong_generation() {
    let mut g = gate();
    assert_eq!(
        g.accept(
            &envelope(json!({"version":1,"seq":1,"kind":"start_recording"})),
            0
        ),
        Err("UNAUTHORIZED_MESSAGE")
    );
    let mut e = event(2);
    e["payload"]["token"] = json!("never forwarded");
    assert_eq!(g.accept(&envelope(e), 0), Err("EVENT_FIELDS"));
    let mut e: Value = serde_json::from_slice(&envelope(event(3))).unwrap();
    e["generation"] = json!(2);
    assert_eq!(
        g.accept(&serde_json::to_vec(&e).unwrap(), 0),
        Err("STALE_GENERATION")
    );
}
#[test]
fn replay_expiry_clock_and_unknown_property() {
    let mut g = gate();
    let e = envelope(event(1));
    g.accept(&e, 1).unwrap();
    assert_eq!(g.accept(&e, 1), Err("MESSAGE_SEQUENCE"));
    assert_eq!(g.accept(&envelope(event(2)), 0), Err("CLOCK_REGRESSION"));
    assert_eq!(g.accept(&envelope(event(2)), 1001), Err("MESSAGE_DEADLINE"));
    assert_eq!(
        gate().accept(
            &envelope(json!({"version":1,"seq":1,"kind":"properties","properties":{"shell":"x"}})),
            0
        ),
        Err("UNKNOWN_PROPERTY")
    );
}
#[test]
fn rate_limit_cannot_disable_cancel_or_dispose() {
    let mut g = gate();
    for n in 1..=8 {
        g.accept(&envelope(event(n)), 0).unwrap();
    }
    assert_eq!(g.accept(&envelope(event(9)), 0), Err("RATE_LIMIT"));
    assert_eq!(
        g.accept(&envelope(json!({"version":1,"seq":10,"kind":"cancel"})), 0),
        Ok(Visual::Cancel)
    );
    assert_eq!(
        g.accept(&envelope(json!({"version":1,"seq":11,"kind":"dispose"})), 0),
        Ok(Visual::Dispose)
    );
}
#[test]
fn property_patch_is_atomic_and_utf16_matches_js() {
    let mut g = gate();
    let before = g.properties().clone();
    let p = json!({"version":1,"seq":1,"kind":"properties","properties":{"home":3,"away":100}});
    assert_eq!(g.accept(&envelope(p), 0), Err("FIELD_RANGE"));
    assert_eq!(g.properties(), &before);
    let p =
        json!({"version":1,"seq":2,"kind":"properties","properties":{"title":"😀😀😀😀😀😀😀"}});
    assert_eq!(g.accept(&envelope(p), 0), Err("FIELD_RANGE"));
}
#[test]
fn duplicate_keys_nonfinite_large_and_deep_json_rejected() {
    for s in [r#"{"x":1,"x":2}"#, r#"{"x":{"y":1,"y":2}}"#, r#"{"x":NaN}"#] {
        assert_eq!(strict_json(s.as_bytes(), 4096), Err("MESSAGE_JSON"));
    }
    assert_eq!(strict_json(&vec![32; 4097], 4096), Err("MESSAGE_SIZE"));
    assert_eq!(
        strict_json(
            format!("{}0{}", "[".repeat(150), "]".repeat(150)).as_bytes(),
            4096
        ),
        Err("MESSAGE_JSON")
    );
}
#[test]
fn real_socketpair_length_guard_fragmentation_and_eof() {
    let (mut a, mut b) = UnixStream::pair().unwrap();
    let t = std::thread::spawn(move || {
        let data = envelope(event(1));
        let mut wire = (data.len() as u32).to_be_bytes().to_vec();
        wire.extend(data);
        for c in wire.chunks(3) {
            b.write_all(c).unwrap();
        }
    });
    let p = read_packet(&mut a, 4096, Duration::from_secs(1)).unwrap();
    assert!(gate().accept(&p, 0).is_ok());
    t.join().unwrap();
    assert_eq!(
        read_packet(&mut a, 4096, Duration::from_millis(20)),
        Err("TRANSPORT_EOF")
    );
    let (mut a, mut b) = UnixStream::pair().unwrap();
    b.write_all(&u32::MAX.to_be_bytes()).unwrap();
    assert_eq!(
        read_packet(&mut a, 4096, Duration::from_millis(20)),
        Err("MESSAGE_SIZE")
    );
}
#[test]
fn silent_peer_timeout_is_bounded() {
    let (mut a, _b) = UnixStream::pair().unwrap();
    let start = Instant::now();
    assert!(read_packet(&mut a, 4096, Duration::from_millis(20)).is_err());
    assert!(start.elapsed() < Duration::from_secs(1));
}
