use motive_creator_runtime_lab::{digest, model::*, persistence::*, planner::*, receipts::*};
use motive_show_control::{
    packs::{CreatorPack, Layout, PlanStep, PropertyValue, VisualDefinition},
    runtime::Config,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::PathBuf,
};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}
fn request(name: &str, instance: &str) -> InsertRequest {
    let dir = if name.ends_with("minimal") {
        root().join("element-lab/packs").join(name)
    } else {
        root()
            .join("element-lab/native-elements")
            .join(name)
            .join("compiled")
    };
    let pack = CreatorPack::from_json(&std::fs::read_to_string(dir.join("manifest.json")).unwrap())
        .unwrap();
    let rules =
        Config::from_json(&std::fs::read_to_string(dir.join("rules.json")).unwrap()).unwrap();
    InsertRequest {
        instance_id: instance.into(),
        definition: DefinitionId {
            package_id: pack.id.clone(),
            version: pack.version.clone(),
            package_sha256: "a".repeat(64),
        },
        pack,
        rules,
        properties: BTreeMap::new(),
        target_scenes: vec![SceneId("fixture-scene".into())],
        layouts: BTreeMap::new(),
    }
}
fn install(owner: &mut StrictOwnerModel, request: InsertRequest) -> Installation {
    let review = owner.review(request).unwrap();
    owner.install(review).unwrap()
}
fn owner() -> StrictOwnerModel {
    StrictOwnerModel::new(Snapshot::empty_fixture()).unwrap()
}
fn layout() -> Layout {
    Layout {
        x: 10.,
        y: 20.,
        width: 200.,
        height: 100.,
        visible: true,
        order: 0,
    }
}

#[test]
fn mixed_creator_tech_lower_alert_goal_insert_into_one_existing_scene() {
    let mut o = owner();
    let original_scenes = o.snapshot.scenes.clone();
    let mut states = vec![];
    for (name, id) in [
        ("creator-tech-minimal", "tech"),
        ("lower-third", "lower"),
        ("community-alert", "alert"),
        ("goal-celebration", "goal"),
    ] {
        states.push(install(&mut o, request(name, id)));
    }
    assert_eq!(o.snapshot.scenes, original_scenes);
    assert_eq!(o.snapshot.budget().sources, 12);
    assert_eq!(o.snapshot.budget().layers, 12);
    assert_eq!(o.snapshot.budget().scenes, 1);
    o.snapshot.validate().unwrap();
    for s in &states {
        assert_eq!(s.phase, Phase::InstalledInModel);
        assert!(
            s.plan
                .steps
                .iter()
                .all(|s| !matches!(s, PlanStep::CreateScene { .. }))
        );
        assert!(s.bound_rules().unwrap().rules.iter().all(|r| !r.enabled));
    }
    let h: BTreeSet<_> = o
        .snapshot
        .layers
        .values()
        .map(|l| l.horizontal.order)
        .collect();
    let v: BTreeSet<_> = o
        .snapshot
        .layers
        .values()
        .map(|l| l.vertical.order)
        .collect();
    assert_eq!(h.len(), 12);
    assert_eq!(v.len(), 12);
}
#[test]
fn one_definition_two_instances_independent_properties_shared_asset_bytes() {
    let mut o = owner();
    let mut a = request("lower-third", "alice");
    a.properties.insert(
        "lower-third-title".into(),
        PropertyValue::Text("Alice".into()),
    );
    let a = install(&mut o, a);
    let mut b = request("lower-third", "bob");
    b.properties.insert(
        "lower-third-title".into(),
        PropertyValue::Text("Bob".into()),
    );
    let b = install(&mut o, b);
    assert_eq!(a.plan.definition, b.plan.definition);
    assert_ne!(a.bindings.sources, b.bindings.sources);
    assert_eq!(o.snapshot.assets.len(), 1);
    assert!(
        !b.plan
            .steps
            .iter()
            .any(|s| matches!(s, PlanStep::ImportAssetAfterLocalAuthorization { .. }))
    );
    let titles: BTreeSet<_> = o
        .snapshot
        .sources
        .values()
        .filter_map(|s| match &s.definition {
            Some(VisualDefinition::Widget { widget }) => Some(widget.title.clone()),
            _ => None,
        })
        .collect();
    assert_eq!(titles, BTreeSet::from(["Alice".into(), "Bob".into()]));
}
#[test]
fn same_instance_shares_sources_in_two_scenes_preserves_independent_layouts() {
    let mut o = owner();
    o.snapshot.scenes.insert(SceneId("second-scene".into()));
    let mut req = request("lower-third", "shared");
    req.target_scenes.push(SceneId("second-scene".into()));
    let mut vertical = layout();
    vertical.x = 60.;
    vertical.visible = false;
    req.layouts.insert(
        "lower-third-content-layer".into(),
        LayoutPair {
            horizontal: layout(),
            vertical,
        },
    );
    let state = install(&mut o, req);
    assert_eq!(o.snapshot.sources.len(), 2);
    assert_eq!(o.snapshot.layers.len(), 4);
    assert_eq!(o.snapshot.assets.len(), 1);
    assert_eq!(state.plan.layer_symbols.len(), 2);
    assert_eq!(
        state
            .plan
            .steps
            .iter()
            .filter(|s| matches!(s, PlanStep::AddLayer { .. }))
            .count(),
        2
    );
    for l in o.snapshot.layers.values().filter(|l| l.horizontal.x == 10.) {
        assert_eq!(l.vertical.x, 60.);
        assert!(!l.vertical.visible);
    }
}
#[test]
fn preserving_camera_and_gameplay_reservations_and_layers() {
    let mut snapshot = Snapshot::empty_fixture();
    for id in ["camera", "gameplay"] {
        let source = SourceId(id.into());
        let layer = LayerId(format!("{id}-layer"));
        snapshot.sources.insert(
            source.clone(),
            Source {
                id: source.clone(),
                definition: None,
                texture_bytes: 4 * 1920 * 1080,
                video: false,
                installation: None,
            },
        );
        snapshot.layers.insert(
            layer.clone(),
            Layer {
                id: layer,
                source,
                scene: SceneId("fixture-scene".into()),
                horizontal: layout(),
                vertical: layout(),
                installation: None,
            },
        );
    }
    let mut o = StrictOwnerModel::new(snapshot.clone()).unwrap();
    install(&mut o, request("lower-third", "lower"));
    for (id, source) in snapshot.sources {
        assert_eq!(o.snapshot.sources[&id], source);
    }
    for (id, layer) in snapshot.layers {
        assert_eq!(o.snapshot.layers[&id], layer);
    }
}
#[test]
fn no_new_scene_quota_even_when_eight_scenes_already_exist() {
    let mut s = Snapshot::empty_fixture();
    for n in 1..8 {
        s.scenes.insert(SceneId(format!("scene-{n}")));
    }
    let p = prepare(request("lower-third", "lower"), &s).unwrap();
    assert_eq!(p.budget.scenes, 8);
}
#[test]
fn global_source_layer_texture_and_order_limits_remain_enforced() {
    let mut s = Snapshot::empty_fixture();
    for n in 0..15 {
        let id = SourceId(format!("source-{n}"));
        s.sources.insert(
            id.clone(),
            Source {
                id,
                definition: None,
                texture_bytes: 0,
                video: false,
                installation: None,
            },
        );
    }
    assert_eq!(
        prepare(request("lower-third", "lower"), &s)
            .unwrap_err()
            .code,
        "GLOBAL_BUDGET"
    );
    s.sources.clear();
    let id = SourceId("reserved".into());
    s.sources.insert(
        id.clone(),
        Source {
            id: id.clone(),
            definition: None,
            texture_bytes: 255 * 1024 * 1024,
            video: false,
            installation: None,
        },
    );
    assert_eq!(
        prepare(request("lower-third", "lower"), &s)
            .unwrap_err()
            .code,
        "GLOBAL_BUDGET"
    );
    s.sources.get_mut(&id).unwrap().texture_bytes = 0;
    for n in 0..31 {
        let layer = LayerId(format!("layer-{n}"));
        s.layers.insert(
            layer.clone(),
            Layer {
                id: layer,
                source: id.clone(),
                scene: SceneId("fixture-scene".into()),
                horizontal: layout(),
                vertical: layout(),
                installation: None,
            },
        );
    }
    assert_eq!(
        prepare(request("lower-third", "lower"), &s)
            .unwrap_err()
            .code,
        "GLOBAL_BUDGET"
    );
    s.layers.retain(|k, _| k.0 == "layer-0");
    s.layers.values_mut().next().unwrap().horizontal.order = 31;
    assert_eq!(
        prepare(request("lower-third", "lower"), &s)
            .unwrap_err()
            .code,
        "PACK_LAYOUT"
    );
}
#[test]
fn malformed_missing_incompatible_and_busy_inputs_fail_closed() {
    let s = Snapshot::empty_fixture();
    let mut r = request("lower-third", "x");
    r.definition.version = "2.0.0".into();
    assert_eq!(prepare(r, &s).unwrap_err().code, "PACKAGE_IDENTITY");
    let mut r = request("lower-third", "x");
    r.definition.package_sha256 = "bad".into();
    assert_eq!(prepare(r, &s).unwrap_err().code, "HASH");
    let mut r = request("lower-third", "x");
    r.target_scenes = vec![SceneId("missing".into())];
    assert_eq!(prepare(r, &s).unwrap_err().code, "SCENE_MISSING");
    let mut r = request("lower-third", "x");
    r.properties
        .insert("not-exported".into(), PropertyValue::Color(123));
    assert_eq!(prepare(r, &s).unwrap_err().code, "PACK_REFERENCE");
    let mut r = request("lower-third", "x");
    r.properties
        .insert("lower-third-title".into(), PropertyValue::Color(123));
    assert_eq!(prepare(r, &s).unwrap_err().code, "PACK_PROPERTY_TYPE");
    let mut s = s;
    s.capabilities.clear();
    assert_eq!(
        prepare(request("lower-third", "x"), &s).unwrap_err().code,
        "CAPABILITY_UNAVAILABLE"
    );
    s.busy = true;
    assert_eq!(
        prepare(request("lower-third", "x"), &s).unwrap_err().code,
        "OWNER_BUSY"
    );
}
#[test]
fn unknown_fields_confirmation_and_payload_commands_are_rejected() {
    let mut value = serde_json::to_value(request("lower-third", "x")).unwrap();
    value["confirmed"] = true.into();
    assert!(serde_json::from_value::<InsertRequest>(value).is_err());
    let mut r = request("lower-third", "x");
    r.rules.rules[0].actions = vec![motive_show_control::actions::Action::EmitEvent {
        name: "private-command".into(),
    }];
    assert!(prepare(r, &Snapshot::empty_fixture()).is_err());
}
#[test]
fn local_review_is_owner_and_snapshot_bound() {
    let a = owner();
    let b = owner();
    let review = a.review(request("lower-third", "x")).unwrap();
    assert_eq!(b.begin(review).unwrap_err().code, "REVIEW_STALE");
    let mut a = a;
    let review = a.review(request("lower-third", "x")).unwrap();
    a.snapshot.revision += 1;
    assert_eq!(a.begin(review).unwrap_err().code, "REVIEW_STALE");
}
#[test]
fn stale_revision_between_steps_requires_reconciliation_no_replay() {
    let mut o = owner();
    let review = o.review(request("lower-third", "x")).unwrap();
    let mut i = o.begin(review).unwrap();
    o.step(&mut i).unwrap();
    o.snapshot.revision += 1;
    assert_eq!(o.step(&mut i).unwrap_err().code, "REVIEW_STALE");
    assert_eq!(i.phase, Phase::NeedsReconciliation);
    let before = o.snapshot.clone();
    assert!(o.step(&mut i).is_err());
    assert_eq!(before, o.snapshot);
}
#[test]
fn changed_graph_even_with_same_revision_is_not_adopted() {
    let mut o = owner();
    let review = o.review(request("lower-third", "x")).unwrap();
    let mut i = o.begin(review).unwrap();
    o.snapshot.scenes.insert(SceneId("foreign".into()));
    assert_eq!(o.step(&mut i).unwrap_err().code, "REVIEW_STALE");
}
fn pending() -> (StrictOwnerModel, Installation, Receipt, Snapshot, Snapshot) {
    let o = owner();
    let review = o.review(request("lower-third", "x")).unwrap();
    let mut i = o.begin(review).unwrap();
    let index = i.begin_step(&o.snapshot).unwrap();
    let result = StepResult::Asset {
        id: ResourceId("sim-asset".into()),
    };
    let before = o.snapshot.clone();
    let after = apply_model_step(&before, &i.plan, &i.bindings, index, &result).unwrap();
    let receipt = Receipt {
        instance_id: "x".into(),
        session: before.session.clone(),
        step: index,
        operation_sha256: digest(&i.plan.steps[index]).unwrap(),
        before: before.revision,
        after: after.revision,
        result,
    };
    (o, i, receipt, before, after)
}
#[test]
fn receipt_rejects_wrong_session_revision_step_fingerprint_and_identity() {
    for field in 0..6 {
        let (_, mut i, mut r, b, a) = pending();
        match field {
            0 => r.session = "alien".into(),
            1 => r.after += 1,
            2 => r.step += 1,
            3 => r.operation_sha256 = "b".repeat(64),
            4 => r.instance_id = "alien".into(),
            _ => i.plan.steps.clear(), // Malformed journal must reject, not index/panic.
        }
        assert!(i.accept(r, &b, &a).is_err());
        assert_eq!(i.phase, Phase::NeedsReconciliation);
        assert!(i.bindings.resources.is_empty());
    }
}
#[test]
fn receipt_rejects_unrelated_mutations_and_duplicate_result() {
    let (_, mut i, r, b, mut a) = pending();
    a.scenes.insert(SceneId("foreign".into()));
    assert_eq!(i.accept(r, &b, &a).unwrap_err().code, "RECEIPT_GRAPH");
    let (_, mut i, r, b, a) = pending();
    i.accept(r.clone(), &b, &a).unwrap();
    assert_eq!(i.accept(r, &b, &a).unwrap_err().code, "RECEIPT_ORDER");
}
#[test]
fn timeout_partial_installation_is_retained_and_cannot_activate_rules_or_rollback() {
    let mut o = owner();
    let review = o.review(request("lower-third", "x")).unwrap();
    let mut i = o.begin(review).unwrap();
    o.step(&mut i).unwrap();
    i.begin_step(&o.snapshot).unwrap();
    i.uncertain("DEADLINE");
    assert_eq!(o.snapshot.assets.len(), 1);
    assert!(i.bound_rules().is_err());
    assert!(prepare_removal(&i, &o.snapshot).is_err());
    assert!(o.step(&mut i).is_err());
    let store = Store::capture(&[i], &o.snapshot).unwrap();
    let report = store.assess_restore(&BTreeMap::new(), &o.snapshot).unwrap();
    assert!(
        report
            .issues
            .iter()
            .any(|x| x.code == "RECONCILIATION_REQUIRED")
    );
}
#[test]
fn explicit_rejection_retains_partial_receipts_and_safe_removal_proposal() {
    let mut o = owner();
    let review = o.review(request("lower-third", "x")).unwrap();
    let mut i = o.begin(review).unwrap();
    o.step(&mut i).unwrap();
    i.rejected("SOURCE_CREATE_FAILED");
    let removal = prepare_removal(&i, &o.snapshot).unwrap();
    assert_eq!(removal.assets.len(), 1);
    assert!(!removal.atomic);
    assert!(removal.sources.is_empty());
}
#[test]
fn cleanup_preserves_foreign_layers_and_assets_reused_by_other_instances() {
    let mut o = owner();
    let a = install(&mut o, request("lower-third", "a"));
    let b = install(&mut o, request("lower-third", "b"));
    let r = prepare_removal(&a, &o.snapshot).unwrap();
    assert_eq!(r.layers.len(), 2);
    assert_eq!(r.sources.len(), 2);
    assert!(r.assets.is_empty());
    assert_eq!(r.retained_shared_assets.len(), 1);
    let source = a.bindings.sources.values().next().unwrap().clone();
    let id = LayerId("foreign-layer".into());
    o.snapshot.layers.insert(
        id.clone(),
        Layer {
            id: id.clone(),
            source: source.clone(),
            scene: SceneId("fixture-scene".into()),
            horizontal: layout(),
            vertical: layout(),
            installation: None,
        },
    );
    let r = prepare_removal(&a, &o.snapshot).unwrap();
    assert!(!r.layers.contains(&id));
    assert!(r.retained_shared_sources.contains(&source));
    assert!(b.bindings.sources.values().all(|s| !r.sources.contains(s)));
}
#[test]
fn restore_requires_reverified_bytes_preserves_properties_layouts_and_disarms() {
    let mut o = owner();
    let req = request("lower-third", "a");
    let pack = req.pack.clone();
    let a = install(&mut o, req);
    let store = Store::capture(&[a], &o.snapshot).unwrap();
    let bytes = serde_json::to_vec(&store).unwrap();
    let read = Store::parse(&bytes).unwrap();
    let no_bytes = read.assess_restore(&BTreeMap::new(), &o.snapshot).unwrap();
    assert_eq!(no_bytes.issues[0].code, "PACKAGE_REVERIFY_REQUIRED");
    let valid = read
        .assess_restore(&BTreeMap::from([("a".repeat(64), pack)]), &o.snapshot)
        .unwrap();
    assert_eq!(valid.compatible, vec!["a"]);
    assert!(valid.requires_local_review);
    assert!(!valid.show_control_armed);
    assert_eq!(valid.historical_events_replayed, 0);
    assert_eq!(valid.scripts_started, 0);
    assert!(
        !String::from_utf8(bytes)
            .unwrap()
            .contains("offline-owner-session")
    );
}
#[test]
fn restore_detects_orphans_incompatible_versions_and_capabilities() {
    let mut o = owner();
    let req = request("lower-third", "a");
    let mut pack = req.pack.clone();
    let a = install(&mut o, req);
    let store = Store::capture(&[a], &o.snapshot).unwrap();
    o.snapshot.layers.clear();
    o.snapshot.capabilities.clear();
    pack.version = "9.0.0".into();
    let report = store
        .assess_restore(&BTreeMap::from([("a".repeat(64), pack)]), &o.snapshot)
        .unwrap();
    for code in [
        "LAYER_MISSING_OR_CHANGED",
        "PACKAGE_IDENTITY",
        "CAPABILITY_UNAVAILABLE",
    ] {
        assert!(report.issues.iter().any(|x| x.code == code));
    }
}
#[test]
fn store_rejects_new_version_unknown_fields_or_self_authorized_trust() {
    let mut o = owner();
    let a = install(&mut o, request("lower-third", "a"));
    let store = serde_json::to_value(Store::capture(&[a], &o.snapshot).unwrap()).unwrap();
    for field in 0..4 {
        let mut bad = store.clone();
        match field {
            0 => bad["version"] = 2.into(),
            1 => bad["process_handle"] = 42.into(),
            2 => bad["instances"][0]["trust_policy"] = "trusted".into(),
            _ => bad["instances"][0]["visual_bindings"]["rules"][0]["enabled"] = true.into(),
        };
        assert!(Store::parse(&serde_json::to_vec(&bad).unwrap()).is_err());
    }
}
#[test]
fn legacy_project_fixtures_remain_byte_identical_without_mandatory_sidecar() {
    // Independently computed SHA-256 of the actual fixture bytes, not a JSON
    // serialization of a byte array. Keeps this evidence usable by native tools.
    let expected = [
        "008ab93d716f08d0f6d86035cc991fb201c4dde5d99b5307a31c7ea8b6217589",
        "f31b4452f4484daccb0dde8ac4d57320c5ad6a6e07b703b26f715b6d4fff03fd",
        "d49464b89ca2961a3cf627c41af17e51e3bec8f70c13ca03f04a446f560d9df3",
        "9729b321ea2546dce64e68ec3bb244d3bcad58ff60e57d5b6ae89b7bb119247c",
        "5a9840cb9ed0a6aa2c97dd382f19285d9b2e3bbbcac32a38ae9a8b24905e95cf",
    ];
    for version in 1..=5 {
        let bytes =
            format!("{{\"version\":{version},\"fixture\":\"opaque-preserved\"}}").into_bytes();
        let before = bytes.clone();
        let report = preserve_legacy_project(&bytes, None).unwrap();
        assert_eq!(report["input_bytes_sha256"], expected[version - 1]);
        assert_eq!(bytes, before);
        assert_eq!(report["project_rewritten"], false);
        assert_eq!(report["production_parser_executed"], false);
    }
}
#[test]
fn installation_rejects_duplicate_instance_and_has_no_rss_or_native_pass_claim() {
    let mut o = owner();
    let a = install(&mut o, request("lower-third", "a"));
    assert_eq!(
        prepare(request("lower-third", "a"), &o.snapshot)
            .unwrap_err()
            .code,
        "INSTANCE_CONFLICT"
    );
    assert!(!a.plan.executable_in_production);
}
#[test]
fn neon_arena_fits_existing_scene_offline() {
    let mut o = owner();
    let i = install(&mut o, request("neon-arena-minimal", "neon"));
    assert_eq!(i.plan.budget.scenes, 1);
    assert_eq!(i.plan.budget.sources, 5);
    assert_eq!(i.plan.budget.layers, 5);
}

#[test]
fn global_asset_inventory_quotas_do_not_expand_silently() {
    let mut o = owner();
    let a = install(&mut o, request("lower-third", "a"));
    let template = o.snapshot.assets.values().next().unwrap().clone();
    for n in 1..128 {
        let mut asset = template.clone();
        asset.id = ResourceId(format!("asset-{n}"));
        asset.descriptor.sha256 = format!("{n:064x}");
        o.snapshot.assets.insert(asset.id.clone(), asset);
    }
    // Same bytes fit as reuse despite full inventory.
    assert_eq!(
        prepare(request("lower-third", "b"), &o.snapshot)
            .unwrap()
            .budget
            .resource_count,
        128
    );
    assert_eq!(
        prepare(request("goal-celebration", "g"), &o.snapshot)
            .unwrap_err()
            .code,
        "GLOBAL_BUDGET"
    );
    let _ = a;
    o.snapshot
        .assets
        .values_mut()
        .for_each(|r| r.descriptor.bytes = 64 * 1024 * 1024);
    assert_eq!(o.snapshot.validate().unwrap_err().code, "GLOBAL_BUDGET");
}

#[test]
fn restore_rejects_definition_changed_even_if_live_and_saved_copies_agree() {
    let mut o = owner();
    let req = request("lower-third", "a");
    let pack = req.pack.clone();
    let a = install(&mut o, req);
    let mut store = Store::capture(&[a], &o.snapshot).unwrap();
    for (id, source) in &mut store.instances[0].sources {
        if let Some(VisualDefinition::Widget { widget }) = &mut source.definition {
            widget.title = "Unreviewed title".into();
            o.snapshot.sources.insert(id.clone(), source.clone());
        }
    }
    let report = store
        .assess_restore(&BTreeMap::from([("a".repeat(64), pack)]), &o.snapshot)
        .unwrap();
    assert!(
        report
            .issues
            .iter()
            .any(|i| i.code == "DEFINITION_INCOMPATIBLE")
    );
    assert!(report.compatible.is_empty());
}

#[test]
fn store_rejects_foreign_rule_references_and_nonvisual_commands() {
    let mut o = owner();
    let a = install(&mut o, request("lower-third", "a"));
    let store = Store::capture(&[a], &o.snapshot).unwrap();
    for action in [
        motive_show_control::actions::Action::ShowOverlay {
            source_id: "foreign".into(),
        },
        motive_show_control::actions::Action::EmitEvent {
            name: "private-command".into(),
        },
    ] {
        let mut changed = store.clone();
        changed.instances[0].visual_bindings.rules[0].actions = vec![action];
        assert!(Store::parse(&serde_json::to_vec(&changed).unwrap()).is_err());
    }
}

#[test]
fn hostile_resource_metadata_returns_errors_without_arithmetic_panic() {
    let mut o = owner();
    install(&mut o, request("lower-third", "a"));
    for case in 0..5 {
        let mut bad = o.snapshot.clone();
        let asset = bad.assets.values_mut().next().unwrap();
        match case {
            0 => {
                asset.descriptor.width = u32::MAX;
                asset.descriptor.height = u32::MAX;
            }
            1 => asset.descriptor.file_name = "../escape.png".into(),
            2 => asset.descriptor.duration_ms = Some(1000),
            3 => asset.descriptor.height = 0,
            _ => asset.license = "unreviewed-license".into(),
        }
        assert!(bad.validate().is_err());
    }
    let mut resource = request("lower-third", "a").pack.resources[0].clone();
    resource.width = u32::MAX;
    resource.height = u32::MAX;
    let source = VisualDefinition::Image {
        resource_id: resource.id.clone(),
        opacity: 1.,
    };
    assert_eq!(
        texture_bytes(&source, &BTreeMap::from([(resource.id.clone(), resource)]))
            .unwrap_err()
            .code,
        "BUDGET_OVERFLOW"
    );
}

#[test]
fn real_native_asset_receipt_identity_is_supported_separately_from_symbols() {
    let (mut o, mut i, mut receipt, before, _) = pending();
    receipt.result = StepResult::Asset {
        id: ResourceId(format!(
            "asset-{}",
            i.plan.resources.values().next().unwrap().sha256
        )),
    };
    let after = apply_model_step(&before, &i.plan, &i.bindings, 0, &receipt.result).unwrap();
    i.accept(receipt, &before, &after).unwrap();
    o.snapshot = after;
    while i.phase == Phase::Installing {
        o.step(&mut i).unwrap();
    }
    o.snapshot.validate().unwrap();
    assert!(o.snapshot.assets.keys().all(|r| r.0.len() == 70));
}

#[test]
fn existing_event_names_do_not_make_actions_compatible_with_source_kinds() {
    let mut req = request("lower-third", "a");
    req.rules.rules[0].actions = vec![motive_show_control::actions::Action::CountdownStart {
        source_id: "lower-third-motif".into(),
    }];
    assert!(prepare(req, &Snapshot::empty_fixture()).is_err());
    let mut o = owner();
    let i = install(&mut o, request("lower-third", "a"));
    let mut store = Store::capture(&[i], &o.snapshot).unwrap();
    let image = store.instances[0]
        .sources
        .values()
        .find(|s| matches!(s.definition, Some(VisualDefinition::Image { .. })))
        .unwrap()
        .id
        .0
        .clone();
    store.instances[0].visual_bindings.rules[0].actions =
        vec![motive_show_control::actions::Action::CountdownStart { source_id: image }];
    assert!(Store::parse(&serde_json::to_vec(&store).unwrap()).is_err());
}
