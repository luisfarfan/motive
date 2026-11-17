use motive_show_control::{model::*, providers::*};
use std::collections::BTreeSet;

fn input() -> DonationInput {
    DonationInput {
        id: "donation-1".into(),
        correlation_id: "corr-1".into(),
        external_id: Some("provider-event-1".into()),
        timestamp_ms: 10,
        semantic: ProviderSemantic::CreatorDonation,
        user_id: "viewer".into(),
        amount_decimal: "12.30".into(),
        currency: Currency::USD,
        message: "Gracias".into(),
    }
}

#[test]
fn synthetic_donation_normalizes_without_float_or_authority_claims() {
    let ingress = VerifiedIngress::simulation("simulation.donations", BTreeSet::new()).unwrap();
    let (event, trust) = normalize_donation(&ingress, input()).unwrap().into_parts();
    assert!(event.simulated);
    assert_eq!(event.origin, "simulation.donations");
    assert_eq!(event.external_id.as_deref(), Some("provider-event-1"));
    assert_eq!(event.field("amount_minor"), Some(Scalar::Int(1230)));
    assert_eq!(event.field("currency"), Some(Scalar::String("USD".into())));
    assert!(trust.authorized_origins.contains(&event.origin));
    assert!(!trust.authorized_users.contains("viewer"));
    assert!(trust.confidence_origins.is_empty());
}

#[test]
fn money_precision_boundaries_never_round() {
    for (decimal, currency, expected) in [
        ("1", Currency::USD, 100),
        ("0.01", Currency::USD, 1),
        ("12.3", Currency::PEN, 1230),
        ("123", Currency::JPY, 123),
        ("0.001", Currency::KWD, 1),
        ("10000000000", Currency::USD, 1_000_000_000_000),
    ] {
        assert_eq!(minor_units(decimal, currency).unwrap(), expected);
    }
    for decimal in [
        "",
        "0",
        "-1",
        "+1",
        "1e2",
        "1,50",
        " 1",
        "1 ",
        ".5",
        "1.",
        "0.001",
        "1.1.1",
        "NaN",
        "18446744073709551616",
        "10000000000.01",
    ] {
        assert!(minor_units(decimal, Currency::USD).is_err(), "{decimal}");
    }
    assert!(minor_units("1.0", Currency::JPY).is_err());
}

#[test]
fn monetary_property_samples_roundtrip_integer_minor_units() {
    for amount in 1..=10_000_u64 {
        let decimal = format!("{}.{:02}", amount / 100, amount % 100);
        assert_eq!(minor_units(&decimal, Currency::USD).unwrap(), amount);
    }
}

#[test]
fn provider_units_cannot_be_misreported_as_creator_donations() {
    let ingress = VerifiedIngress::simulation("simulation", BTreeSet::new()).unwrap();
    for semantic in [
        ProviderSemantic::TwitchBits,
        ProviderSemantic::TwitchCharityDonation,
        ProviderSemantic::YouTubeSuperChat,
        ProviderSemantic::YouTubeSuperSticker,
    ] {
        let mut value = input();
        value.semantic = semantic;
        let error = normalize_donation(&ingress, value).err().unwrap();
        assert_eq!(error.code, "DISTINCT_PROVIDER_SEMANTIC");
    }
}

#[test]
fn synthetic_gate_cannot_authorize_real_or_spoofed_events() {
    assert!(VerifiedIngress::simulation("twitch", BTreeSet::new()).is_err());
    let ingress =
        VerifiedIngress::simulation("simulation", BTreeSet::from(["moderator".into()])).unwrap();
    let normalized = normalize_donation(&ingress, input()).unwrap();
    let mut event = normalized.event().clone();
    event.simulated = false;
    assert_eq!(
        ingress.accept(event.clone()).err().unwrap().code,
        "INGRESS_MISMATCH"
    );
    event.simulated = true;
    event.origin = "simulation.attacker".into();
    assert!(ingress.accept(event).is_err());
    let mut payload = serde_json::to_value(input()).unwrap();
    payload["authorized"] = true.into();
    assert!(serde_json::from_value::<DonationInput>(payload).is_err());
}

#[test]
fn backoff_honors_provider_rate_limit_and_stops_at_budget() {
    let policy = BackoffPolicy {
        initial_ms: 1000,
        maximum_ms: 10000,
        maximum_attempts: 5,
    };
    assert_eq!(
        (0..5)
            .map(|n| policy.delay_ms(n, None).unwrap())
            .collect::<Vec<_>>(),
        vec![1000, 2000, 4000, 8000, 10000]
    );
    assert_eq!(policy.delay_ms(0, Some(9000)).unwrap(), 9000);
    assert_eq!(
        policy.delay_ms(0, Some(10001)).unwrap_err().code,
        "RETRY_SUSPENDED"
    );
    assert_eq!(
        policy.delay_ms(5, None).unwrap_err().code,
        "RETRY_EXHAUSTED"
    );
    assert!(
        BackoffPolicy {
            initial_ms: 0,
            ..policy
        }
        .delay_ms(0, None)
        .is_err()
    );
    assert!(
        BackoffPolicy {
            maximum_attempts: 255,
            ..policy
        }
        .delay_ms(254, None)
        .is_err()
    );
}

#[test]
fn reconnect_checkpoint_cannot_serialize_transport_urls_or_secret_fields() {
    let mut checkpoint = ReconnectCheckpoint {
        schema_version: 1,
        provider: Provider::Twitch,
        session_generation: 2,
        cursor_ref: Some("cursor-ref-session2".into()),
        last_external_event_id: Some("evt-1".into()),
    };
    checkpoint.validate().unwrap();
    checkpoint.cursor_ref = Some("wss://provider.example/reconnect?token=secret".into());
    assert!(checkpoint.validate().is_err());
    checkpoint.cursor_ref = Some("raw-provider-cursor".into());
    assert!(checkpoint.validate().is_err());
    assert!(serde_json::from_str::<ReconnectCheckpoint>(r#"{"schema_version":1,"provider":"twitch","session_generation":2,"cursor_ref":null,"last_external_event_id":null,"access_token":"secret"}"#).is_err());
}

#[test]
fn real_providers_are_contracts_only() {
    for provider in [
        Provider::Twitch,
        Provider::YouTube,
        Provider::LocalVoice,
        Provider::OfficialDonation,
    ] {
        let capability = capabilities(provider);
        assert!(!capability.adapter_implemented);
        assert!(capability.synthetic_only && capability.requires_verified_session);
    }
    assert!(capabilities(Provider::Synthetic).adapter_implemented);
}
