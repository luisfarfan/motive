//! Regression for retaining the exact partial journal after a real model failure.
use motive_creator_runtime_lab::{model::*, planner::*, receipts::*};
use motive_show_control::{packs::CreatorPack, runtime::Config};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
fn request(instance: &str) -> InsertRequest {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf();
    let folder = root.join("element-lab/native-elements/lower-third/compiled");
    let pack =
        CreatorPack::from_json(&std::fs::read_to_string(folder.join("manifest.json")).unwrap())
            .unwrap();
    let rules =
        Config::from_json(&std::fs::read_to_string(folder.join("rules.json")).unwrap()).unwrap();
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
fn snapshot_with_collision(nonce: &str, sequence: &str) -> Snapshot {
    let mut snapshot = Snapshot::empty_fixture();
    let id = SourceId(format!("sim-{nonce}-source-{sequence}"));
    snapshot.sources.insert(
        id.clone(),
        Source {
            id,
            definition: None,
            texture_bytes: 0,
            video: false,
            installation: None,
        },
    );
    snapshot
}
fn cli(input: Value) -> (i32, Value) {
    let mut process = Command::new(env!("CARGO_BIN_EXE_motive-creator-runtime-lab"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    process
        .stdin
        .take()
        .unwrap()
        .write_all(&serde_json::to_vec(&input).unwrap())
        .unwrap();
    let result = process.wait_with_output().unwrap();
    assert!(
        result.stderr.is_empty(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    (
        result.status.code().unwrap(),
        serde_json::from_slice(&result.stdout).unwrap(),
    )
}
#[test]
fn cli_returns_partial_journal_snapshot_and_store_on_later_known_failure() {
    let snapshot = snapshot_with_collision("1", "2");
    let (exit, report) =
        cli(json!({"snapshot":snapshot,"insertions":[request("first"),request("must-not-run")]}));
    assert_eq!(exit, 1);
    assert_eq!(report["status"], "PARTIAL");
    assert_eq!(report["installations"].as_array().unwrap().len(), 1);
    let install = &report["installations"][0];
    assert_eq!(install["phase"], "partial");
    assert_eq!(install["error"], "ID_CONFLICT");
    assert_eq!(install["receipts"].as_array().unwrap().len(), 1);
    assert!(install["pending_step"].is_null());
    assert_eq!(report["snapshot"]["assets"].as_object().unwrap().len(), 1);
    assert_eq!(
        report["snapshot"]["sources"],
        serde_json::to_value(snapshot.sources).unwrap()
    );
    assert_eq!(
        report["store"]["instances"][0]["installation_phase"],
        "partial"
    );
    assert_eq!(
        report["store"]["instances"][0]["visual_bindings"]["rules"],
        json!([])
    );
    assert_eq!(report["show_control_armed"], false);
}
#[test]
fn later_review_rejection_retains_previously_completed_installation() {
    let (exit, report) = cli(
        json!({"snapshot":Snapshot::empty_fixture(),"insertions":[request("same"),request("same")]}),
    );
    assert_eq!(exit, 1);
    assert_eq!(report["status"], "PARTIAL");
    assert_eq!(report["stopped_on_error"]["code"], "INSTANCE_CONFLICT");
    assert_eq!(report["installations"].as_array().unwrap().len(), 1);
    assert_eq!(report["installations"][0]["phase"], "installed_in_model");
    assert_eq!(report["snapshot"]["sources"].as_object().unwrap().len(), 2);
    assert_eq!(report["store"]["instances"].as_array().unwrap().len(), 1);
}
#[test]
fn initial_review_failure_has_no_partial_state_claim() {
    let mut req = request("bad");
    req.target_scenes = vec![SceneId("missing".into())];
    let (exit, report) = cli(json!({"snapshot":Snapshot::empty_fixture(),"insertions":[req]}));
    assert_eq!(exit, 1);
    assert_eq!(report["status"], "FAIL");
    assert!(report.get("snapshot").is_none());
}
#[test]
fn known_step_rejection_clears_intent_and_keeps_prior_receipts() {
    // Discover this test owner's allocator prefix from its first valid receipt,
    // then use a new snapshot with the next source ID already owned by someone else.
    let mut owner = StrictOwnerModel::new(Snapshot::empty_fixture()).unwrap();
    let review = owner.review(request("probe")).unwrap();
    let mut probe = owner.begin(review).unwrap();
    owner.step(&mut probe).unwrap();
    let asset = probe.bindings.resources.values().next().unwrap().0.clone();
    let parts: Vec<_> = asset.split('-').collect();
    let id = SourceId(format!("sim-{}-source-3", parts[1]));
    // Clear the unreferenced probe asset, then arrange collision on source 3:
    // allocator 2 imports successfully; allocator 3 must reject before mutation.
    owner.snapshot.assets.clear();
    owner.snapshot.revision += 1;
    owner.snapshot.sources.insert(
        id.clone(),
        Source {
            id,
            definition: None,
            texture_bytes: 0,
            video: false,
            installation: None,
        },
    );
    let review = owner.review(request("next")).unwrap();
    let mut installation = owner.begin(review).unwrap();
    owner.step(&mut installation).unwrap();
    let before = owner.snapshot.clone();
    assert_eq!(
        owner.step(&mut installation).unwrap_err().code,
        "ID_CONFLICT"
    );
    assert_eq!(owner.snapshot, before);
    assert_eq!(installation.phase, Phase::Partial);
    assert_eq!(installation.receipts.len(), 1);
    assert!(installation.pending_step.is_none());
    assert!(installation.bound_rules().is_err());
    assert_eq!(
        prepare_removal(&installation, &owner.snapshot)
            .unwrap()
            .assets
            .len(),
        1
    );
}
