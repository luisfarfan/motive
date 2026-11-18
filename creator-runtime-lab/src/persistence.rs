//! Experimental sidecar only. Production project versions 1–5 are untouched.
use crate::{Error, check, hash, label, model::*, planner::*, receipts::*};
use motive_show_control::packs::{CreatorPack, PropertyValue, Resource, VisualDefinition};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const FORMAT: &str = "motive-creator-runtime-lab-state";
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StoredInstance {
    pub instance_id: String,
    pub definition: DefinitionId,
    pub properties: BTreeMap<String, PropertyValue>,
    pub sources: BTreeMap<SourceId, Source>,
    pub layers: BTreeMap<LayerId, Layer>,
    pub assets: BTreeMap<ResourceId, Asset>,
    pub symbolic_bindings: Bindings,
    pub visual_bindings: motive_show_control::runtime::Config,
    pub trust_policy: String,
    pub installation_phase: Phase,
    pub pending_step: Option<usize>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Store {
    pub format: String,
    pub version: u32,
    pub evidence_scope: String,
    pub instances: Vec<StoredInstance>,
}
#[derive(Clone, Debug, Serialize)]
pub struct RestoreReport {
    pub compatible: Vec<String>,
    pub issues: Vec<RestoreIssue>,
    pub requires_local_review: bool,
    pub show_control_armed: bool,
    pub scripts_started: usize,
    pub historical_events_replayed: usize,
    pub production_project_changed: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct RestoreIssue {
    pub instance: String,
    pub code: String,
}

impl Store {
    pub fn capture(installations: &[Installation], snapshot: &Snapshot) -> Result<Self, Error> {
        snapshot.validate()?;
        let mut instances = vec![];
        for i in installations {
            let sources = i
                .bindings
                .sources
                .values()
                .filter_map(|id| snapshot.sources.get(id).map(|s| (id.clone(), s.clone())))
                .collect();
            let layers = i
                .bindings
                .layers
                .values()
                .filter_map(|id| snapshot.layers.get(id).map(|l| (id.clone(), l.clone())))
                .collect();
            let assets = i
                .bindings
                .resources
                .values()
                .filter_map(|id| snapshot.assets.get(id).map(|a| (id.clone(), a.clone())))
                .collect();
            let mut rules = if i.phase == Phase::InstalledInModel {
                i.bound_rules()?
            } else {
                let mut r = i.plan.rules.clone();
                r.rules.clear();
                r
            };
            for r in &mut rules.rules {
                r.enabled = false;
            }
            instances.push(StoredInstance {
                instance_id: i.plan.instance_id.clone(),
                definition: i.plan.definition.clone(),
                properties: i.plan.properties.clone(),
                sources,
                layers,
                assets,
                symbolic_bindings: i.bindings.clone(),
                visual_bindings: rules,
                trust_policy: "local-review-required-on-restore".into(),
                installation_phase: i.phase.clone(),
                pending_step: i.pending_step,
            });
        }
        let store = Self {
            format: FORMAT.into(),
            version: 1,
            evidence_scope: "offline-model-only".into(),
            instances,
        };
        Self::parse(
            &serde_json::to_vec(&store).map_err(|_| Error::new("STORE_SCHEMA", "Invalid state"))?,
        )
    }
    pub fn parse(bytes: &[u8]) -> Result<Self, Error> {
        check(
            bytes.len() <= 1_048_576,
            "STORE_SIZE",
            "Sidecar exceeds 1 MiB",
        )?;
        let store: Self = serde_json::from_slice(bytes)
            .map_err(|_| Error::new("STORE_SCHEMA", "Malformed or unknown state fields"))?;
        check(
            store.format == FORMAT
                && store.version == 1
                && store.evidence_scope == "offline-model-only",
            "STORE_VERSION",
            "Unsupported sidecar or native trust claim",
        )?;
        check(
            store.instances.len() <= 16,
            "STORE_LIMIT",
            "Too many instances",
        )?;
        let mut ids = BTreeSet::new();
        for i in &store.instances {
            label(&i.instance_id)?;
            label(&i.definition.package_id)?;
            hash(&i.definition.package_sha256)?;
            check(
                ids.insert(&i.instance_id),
                "INSTANCE_CONFLICT",
                "Duplicate persisted instance",
            )?;
            check(
                i.trust_policy == "local-review-required-on-restore"
                    && i.visual_bindings.rules.iter().all(|r| !r.enabled),
                "STORE_AUTHORITY",
                "Store cannot grant execution or activate rules",
            )?;
            motive_show_control::runtime::Config::from_json(
                &serde_json::to_string(&i.visual_bindings)
                    .map_err(|_| Error::new("STORE_SCHEMA", "Invalid rules"))?,
            )?;
            check(
                i.visual_bindings.variables.is_empty(),
                "STORE_AUTHORITY",
                "No implicit Show Control variable restoration",
            )?;
            let source_ids: BTreeMap<_, _> = i
                .sources
                .keys()
                .map(|id| (id.0.clone(), id.0.clone()))
                .collect();
            let layer_ids: BTreeMap<_, _> = i
                .layers
                .keys()
                .map(|id| (id.0.clone(), id.0.clone()))
                .collect();
            let scene_ids: BTreeMap<_, _> = i
                .symbolic_bindings
                .scenes
                .values()
                .map(|id| (id.0.clone(), id.0.clone()))
                .collect();
            for rule in &i.visual_bindings.rules {
                for action in &rule.actions {
                    remap_action(&mut action.clone(), &source_ids, &layer_ids, &scene_ids)?;
                }
            }
            check(
                i.sources
                    .values()
                    .all(|s| s.installation.as_ref() == Some(&i.instance_id))
                    && i.layers
                        .values()
                        .all(|l| l.installation.as_ref() == Some(&i.instance_id)),
                "STORE_OWNERSHIP",
                "Source/layer belongs to another installation",
            )?;
            check(
                i.symbolic_bindings
                    .sources
                    .values()
                    .all(|id| i.sources.contains_key(id))
                    && i.symbolic_bindings
                        .layers
                        .values()
                        .all(|id| i.layers.contains_key(id))
                    && i.symbolic_bindings
                        .resources
                        .values()
                        .all(|id| i.assets.contains_key(id)),
                "ORPHAN_REFERENCE",
                "Stored bindings are missing objects",
            )?;
            let scenes = i.symbolic_bindings.scenes.values().cloned().collect();
            let snapshot = Snapshot {
                session: "store-validation".into(),
                revision: 0,
                busy: false,
                capabilities: BTreeSet::new(),
                scenes,
                sources: i.sources.clone(),
                layers: i.layers.clone(),
                assets: i.assets.clone(),
            };
            snapshot.validate()?;
            validate_actions(&i.visual_bindings, snapshot.action_snapshot()?)?;
        }
        Ok(store)
    }
    /// `verified` comes from the importer rechecking archive bytes; a hash in the
    /// sidecar alone is not verification. This method only reports, never dispatches.
    pub fn assess_restore(
        &self,
        verified: &BTreeMap<String, CreatorPack>,
        snapshot: &Snapshot,
    ) -> Result<RestoreReport, Error> {
        snapshot.validate()?;
        let mut report = RestoreReport {
            compatible: vec![],
            issues: vec![],
            requires_local_review: true,
            show_control_armed: false,
            scripts_started: 0,
            historical_events_replayed: 0,
            production_project_changed: false,
        };
        for i in &self.instances {
            let mut codes = BTreeSet::new();
            if let Some(pack) = verified.get(&i.definition.package_sha256) {
                pack.validate()?;
                if pack.id != i.definition.package_id || pack.version != i.definition.version {
                    codes.insert("PACKAGE_IDENTITY");
                }
                if !pack.requires.is_subset(&snapshot.capabilities) {
                    codes.insert("CAPABILITY_UNAVAILABLE");
                }
                let mut applied = pack.clone();
                for (id, v) in &i.properties {
                    if applied.set_property(id, v.clone()).is_err() {
                        codes.insert("PROPERTY_INCOMPATIBLE");
                    }
                }
                if i.properties.len() != pack.properties.len() {
                    codes.insert("PROPERTY_INCOMPATIBLE");
                }
                if i.sources.len() != applied.overlays.len() {
                    codes.insert("DEFINITION_INCOMPATIBLE");
                }
                for overlay in &applied.overlays {
                    let key = symbol(&i.instance_id, &overlay.id);
                    let source = i
                        .symbolic_bindings
                        .sources
                        .get(&key)
                        .and_then(|id| i.sources.get(id));
                    let Some(source) = source else {
                        codes.insert("DEFINITION_INCOMPATIBLE");
                        continue;
                    };
                    let mut expected = overlay.definition.clone();
                    if let VisualDefinition::Image { resource_id, .. }
                    | VisualDefinition::Video { resource_id, .. } = &mut expected
                    {
                        let descriptor = applied.resources.iter().find(|r| &r.id == resource_id);
                        let actual_id = match &source.definition {
                            Some(
                                VisualDefinition::Image { resource_id, .. }
                                | VisualDefinition::Video { resource_id, .. },
                            ) => Some(resource_id),
                            _ => None,
                        };
                        if let (Some(descriptor), Some(actual_id)) = (descriptor, actual_id) {
                            if i.assets
                                .get(&ResourceId(actual_id.clone()))
                                .is_some_and(|a| {
                                    a.license == pack.license
                                        && same_resource(&a.descriptor, descriptor)
                                })
                            {
                                *resource_id = actual_id.clone();
                            } else {
                                codes.insert("ASSET_INCOMPATIBLE");
                            }
                        } else {
                            codes.insert("ASSET_INCOMPATIBLE");
                        }
                    }
                    if source.definition.as_ref() != Some(&expected) {
                        codes.insert("DEFINITION_INCOMPATIBLE");
                    }
                }
                // A source that changed after the stored installation cannot be
                // reclaimed or silently replaced during restore.
                for (id, source) in &i.sources {
                    if snapshot.sources.get(id) != Some(source) {
                        codes.insert("SOURCE_MISSING_OR_CHANGED");
                    }
                }
                for (id, layer) in &i.layers {
                    if snapshot.layers.get(id) != Some(layer) {
                        codes.insert("LAYER_MISSING_OR_CHANGED");
                    }
                }
                for (id, asset) in &i.assets {
                    if snapshot.assets.get(id) != Some(asset) {
                        codes.insert("ASSET_MISSING_OR_CHANGED");
                    }
                }
                for scene in i.symbolic_bindings.scenes.values() {
                    if !snapshot.scenes.contains(scene) {
                        codes.insert("SCENE_MISSING");
                    }
                }
            } else {
                codes.insert("PACKAGE_REVERIFY_REQUIRED");
            }
            if i.pending_step.is_some() || i.installation_phase != Phase::InstalledInModel {
                codes.insert("RECONCILIATION_REQUIRED");
            }
            if codes.is_empty() {
                report.compatible.push(i.instance_id.clone());
            }
            for code in codes {
                report.issues.push(RestoreIssue {
                    instance: i.instance_id.clone(),
                    code: code.into(),
                });
            }
        }
        Ok(report)
    }
}

fn same_resource(a: &Resource, b: &Resource) -> bool {
    a.sha256 == b.sha256
        && a.bytes == b.bytes
        && a.width == b.width
        && a.height == b.height
        && a.kind == b.kind
        && a.duration_ms == b.duration_ms
}

/// Compatibility fixture adapter: preserve opaque legacy project bytes exactly.
/// This does not claim to be Production's legacy parser or perform a migration.
pub fn preserve_legacy_project(
    project: &[u8],
    sidecar: Option<&[u8]>,
) -> Result<serde_json::Value, Error> {
    check(
        project.len() <= 4 * 1024 * 1024,
        "PROJECT_SIZE",
        "Fixture too large",
    )?;
    let value: serde_json::Value = serde_json::from_slice(project)
        .map_err(|_| Error::new("PROJECT_SCHEMA", "Fixture JSON invalid"))?;
    let version = value
        .get("version")
        .or_else(|| value.get("schema_version"))
        .and_then(|v| v.as_u64());
    check(
        version.is_some_and(|v| (1..=5).contains(&v)),
        "PROJECT_VERSION",
        "Expected a legacy v1–v5 fixture",
    )?;
    if let Some(bytes) = sidecar {
        Store::parse(bytes)?;
    }
    Ok(
        serde_json::json!({"version":version,"input_bytes_sha256":format!("{:x}", Sha256::digest(project)),"project_rewritten":false,
        "production_parser_executed":false,"sidecar_present":sidecar.is_some(),"requires_project_format_bump":false,"scripts_started":0,"show_control_armed":false}),
    )
}
