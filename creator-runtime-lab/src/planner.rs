use crate::{Error, check, digest, hash, label, model::*};
use motive_show_control::{
    actions::Action,
    packs::{
        CreatorPack, Layout, Orientation, PlanStep, PropertyValue, Resource, VisualDefinition,
    },
    runtime::Config,
    simulation,
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DefinitionId {
    pub package_id: String,
    pub version: String,
    pub package_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LayoutPair {
    pub horizontal: Layout,
    pub vertical: Layout,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InsertRequest {
    pub instance_id: String,
    pub definition: DefinitionId,
    pub pack: CreatorPack,
    pub rules: Config,
    pub properties: BTreeMap<String, PropertyValue>,
    /// Deliberate shared-source placements. Properties apply to every placement.
    pub target_scenes: Vec<SceneId>,
    pub layouts: BTreeMap<String, LayoutPair>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Bindings {
    pub scenes: BTreeMap<String, SceneId>,
    pub sources: BTreeMap<String, SourceId>,
    pub layers: BTreeMap<String, LayerId>,
    pub resources: BTreeMap<String, ResourceId>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InstancePlan {
    pub definition: DefinitionId,
    pub instance_id: String,
    pub session: String,
    pub revision: u64,
    pub snapshot_sha256: String,
    pub properties: BTreeMap<String, PropertyValue>,
    pub resources: BTreeMap<String, Resource>,
    pub license: String,
    pub initial_bindings: Bindings,
    pub steps: Vec<PlanStep>,
    pub rules: Config,
    pub budget: Budget,
    pub source_texture_bytes: BTreeMap<String, u64>,
    pub source_symbols: BTreeMap<String, String>,
    pub layer_symbols: Vec<BTreeMap<String, String>>,
    pub executable_in_production: bool,
}
pub fn symbol(instance: &str, original: &str) -> String {
    let raw = format!("{instance}-{original}");
    if raw.len() <= 64 {
        raw
    } else {
        format!(
            "{}-{}",
            &raw[..43],
            &digest(&raw).expect("string serialization")[..20]
        )
    }
}
fn resource_equivalent(a: &Resource, b: &Resource) -> bool {
    a.sha256 == b.sha256
        && a.bytes == b.bytes
        && a.kind == b.kind
        && a.width == b.width
        && a.height == b.height
        && a.duration_ms == b.duration_ms
}

pub fn prepare(request: InsertRequest, snapshot: &Snapshot) -> Result<InstancePlan, Error> {
    snapshot.validate()?;
    check(
        !snapshot.busy,
        "OWNER_BUSY",
        "Owner must be idle for installation review",
    )?;
    label(&request.instance_id)?;
    hash(&request.definition.package_sha256)?;
    request.pack.validate()?;
    check(
        request.pack.id == request.definition.package_id
            && request.pack.version == request.definition.version,
        "PACKAGE_IDENTITY",
        "Reviewed bytes must identify this definition and version",
    )?;
    check(
        !snapshot
            .sources
            .values()
            .any(|s| s.installation.as_ref() == Some(&request.instance_id)),
        "INSTANCE_CONFLICT",
        "Instance already exists; inspect its receipts",
    )?;
    check(
        request.pack.scenes.len() == 1,
        "SELECTION_REQUIRED",
        "Select one authored scene with the existing SDK before insertion",
    )?;
    check(
        !request.target_scenes.is_empty()
            && request.target_scenes.len() <= 8
            && request.target_scenes.iter().collect::<BTreeSet<_>>().len()
                == request.target_scenes.len(),
        "SCENE_SELECTION",
        "Unique existing target scenes required",
    )?;
    check(
        request
            .target_scenes
            .iter()
            .all(|s| snapshot.scenes.contains(s)),
        "SCENE_MISSING",
        "Target scene no longer exists",
    )?;
    let mut pack = request.pack;
    for (id, value) in request.properties {
        pack.set_property(&id, value)?;
    }
    let upstream = pack.plan(&snapshot.capabilities)?;
    check(
        upstream.unavailable.is_empty(),
        "CAPABILITY_UNAVAILABLE",
        "Required native capability unavailable",
    )?;
    simulation::validate_pack_rules(&pack, &request.rules)?;
    check(
        request.rules.variables.is_empty()
            && request
                .rules
                .rules
                .iter()
                .all(|r| pack.rule_ids.contains(&r.id)),
        "RULE_REVIEW_REQUIRED",
        "No hidden rules or implicit variable migration",
    )?;
    let authored = &pack.scenes[0];
    check(
        request
            .layouts
            .keys()
            .all(|k| authored.layers.iter().any(|l| &l.id == k)),
        "LAYOUT_UNKNOWN",
        "Layout override references unknown layer",
    )?;
    let mut candidate_layers = authored.layers.clone();
    for l in &mut candidate_layers {
        if let Some(v) = request.layouts.get(&l.id) {
            v.horizontal.validate()?;
            v.vertical.validate()?;
            l.horizontal = v.horizontal.clone();
            l.vertical = v.vertical.clone();
        }
    }
    let mut initial = Bindings::default();
    let mut steps = Vec::new();
    let mut resources: BTreeMap<String, Resource> = BTreeMap::new();
    let mut resource_symbols = BTreeMap::new();
    for r in &pack.resources {
        // Reuse only exact content/encoding/dimension/license matches; never paths.
        let prior: Option<String> = resources
            .iter()
            .find(|(_, x)| resource_equivalent(x, r))
            .map(|(k, _)| k.clone());
        if let Some(existing) = prior {
            resource_symbols.insert(r.id.clone(), existing);
            continue;
        }
        let key = symbol(&request.instance_id, &r.id);
        resources.insert(key.clone(), r.clone());
        resource_symbols.insert(r.id.clone(), key.clone());
        if let Some(asset) = snapshot
            .assets
            .values()
            .find(|a| a.license == pack.license && resource_equivalent(&a.descriptor, r))
        {
            initial.resources.insert(key, asset.id.clone());
        } else {
            steps.push(PlanStep::ImportAssetAfterLocalAuthorization {
                resource_ref: key,
                file_name: r.file_name.clone(),
            });
        }
    }
    let source_symbols: BTreeMap<_, _> = pack
        .overlays
        .iter()
        .map(|s| (s.id.clone(), symbol(&request.instance_id, &s.id)))
        .collect();
    let resource_table = pack
        .resources
        .iter()
        .map(|r| (r.id.clone(), r.clone()))
        .collect();
    let source_texture_bytes: BTreeMap<_, _> = pack
        .overlays
        .iter()
        .map(|s| {
            Ok((
                source_symbols[&s.id].clone(),
                texture_bytes(&s.definition, &resource_table)?,
            ))
        })
        .collect::<Result<_, Error>>()?;
    let mut budget = snapshot.budget();
    budget.sources += pack.overlays.len();
    budget.layers += candidate_layers.len() * request.target_scenes.len();
    budget.video_sources += pack
        .overlays
        .iter()
        .filter(|s| matches!(s.definition, VisualDefinition::Video { .. }))
        .count();
    budget.texture_bytes = budget
        .texture_bytes
        .saturating_add(source_texture_bytes.values().sum::<u64>());
    budget.resource_bytes = budget.resource_bytes.saturating_add(
        resources
            .iter()
            .filter(|(k, _)| !initial.resources.contains_key(*k))
            .map(|(_, r)| r.bytes)
            .sum::<u64>(),
    );
    budget.resource_count += resources
        .keys()
        .filter(|k| !initial.resources.contains_key(*k))
        .count();
    budget.validate()?;
    let mut created = BTreeSet::new();
    let mut layer_symbols = Vec::new();
    let mut rules = request.rules.clone();
    rules.rules.clear();
    for (place, scene) in request.target_scenes.iter().enumerate() {
        let scene_ref = symbol(&request.instance_id, &format!("placement-{place}"));
        initial.scenes.insert(scene_ref.clone(), scene.clone());
        let layer_table: BTreeMap<_, _> = candidate_layers
            .iter()
            .map(|l| {
                (
                    l.id.clone(),
                    symbol(&request.instance_id, &format!("p{place}-{}", l.id)),
                )
            })
            .collect();
        let mut placements = candidate_layers.clone();
        for vertical in [false, true] {
            let base = snapshot
                .layers
                .values()
                .filter(|l| &l.scene == scene)
                .map(|l| {
                    if vertical {
                        l.vertical.order
                    } else {
                        l.horizontal.order
                    }
                })
                .max()
                .map_or(0, |n| n + 1);
            let mut sorted: Vec<_> = placements.iter_mut().collect();
            sorted.sort_by_key(|l| {
                if vertical {
                    l.vertical.order
                } else {
                    l.horizontal.order
                }
            });
            for (rank, layer) in sorted.into_iter().enumerate() {
                let target = if vertical {
                    &mut layer.vertical
                } else {
                    &mut layer.horizontal
                };
                target.order = base + rank as u32;
                target.validate()?;
            }
        }
        for l in placements {
            let source_ref = source_symbols[&l.overlay_id].clone();
            let layer_ref = layer_table[&l.id].clone();
            if created.insert(source_ref.clone()) {
                let source = pack
                    .overlays
                    .iter()
                    .find(|s| s.id == l.overlay_id)
                    .expect("pack validated");
                let mut definition = source.definition.clone();
                if let VisualDefinition::Image { resource_id, .. }
                | VisualDefinition::Video { resource_id, .. } = &mut definition
                {
                    *resource_id = resource_symbols[resource_id].clone();
                }
                steps.push(PlanStep::CreateOverlay {
                    scene_ref: scene_ref.clone(),
                    source_ref,
                    first_layer_ref: layer_ref.clone(),
                    name: source.name.clone(),
                    definition,
                });
            } else {
                steps.push(PlanStep::AddLayer {
                    scene_ref: scene_ref.clone(),
                    source_ref,
                    layer_ref: layer_ref.clone(),
                });
            }
            steps.push(PlanStep::SetTransform {
                scene_ref: scene_ref.clone(),
                layer_ref: layer_ref.clone(),
                variant: Orientation::Horizontal,
                transform: l.horizontal,
            });
            steps.push(PlanStep::SetTransform {
                scene_ref: scene_ref.clone(),
                layer_ref,
                variant: Orientation::Vertical,
                transform: l.vertical,
            });
        }
        let scene_symbols = BTreeMap::from([(authored.id.clone(), scene_ref)]);
        for rule in &request.rules.rules {
            let mut rule = rule.clone();
            rule.id = symbol(&request.instance_id, &format!("p{place}-{}", rule.id));
            rule.enabled = false;
            for a in &mut rule.actions {
                remap_action(a, &source_symbols, &layer_table, &scene_symbols)?;
            }
            rules.rules.push(rule);
        }
        layer_symbols.push(layer_table);
    }
    Config::from_json(
        &serde_json::to_string(&rules).map_err(|_| Error::new("RULE_SCHEMA", "Invalid rules"))?,
    )?;
    Ok(InstancePlan {
        definition: request.definition,
        instance_id: request.instance_id,
        session: snapshot.session.clone(),
        revision: snapshot.revision,
        snapshot_sha256: digest(snapshot)?,
        properties: pack
            .properties
            .into_iter()
            .map(|p| (p.id, p.value))
            .collect(),
        resources,
        license: pack.license,
        initial_bindings: initial,
        steps,
        rules,
        budget,
        source_texture_bytes,
        source_symbols,
        layer_symbols,
        executable_in_production: false,
    })
}

fn remap(value: &mut String, table: &BTreeMap<String, String>) -> Result<(), Error> {
    *value = table
        .get(value)
        .ok_or_else(|| Error::new("BINDING_MISSING", "Action references missing identity"))?
        .clone();
    Ok(())
}
pub fn remap_action(
    action: &mut Action,
    sources: &BTreeMap<String, String>,
    layers: &BTreeMap<String, String>,
    scenes: &BTreeMap<String, String>,
) -> Result<(), Error> {
    match action {
        Action::ShowOverlay { source_id }
        | Action::HideOverlay { source_id }
        | Action::Widget { source_id, .. }
        | Action::CountdownStart { source_id }
        | Action::CountdownReset { source_id }
        | Action::UpdateText { source_id, .. } => remap(source_id, sources)?,
        Action::TriggerAnimatedWidget {
            source_id,
            scene_id,
            layer_id,
            ..
        } => {
            remap(source_id, sources)?;
            remap(scene_id, scenes)?;
            remap(layer_id, layers)?;
        }
        Action::Animate {
            scene_id, layer_id, ..
        } => {
            remap(scene_id, scenes)?;
            remap(layer_id, layers)?;
        }
        Action::SelectScene { scene_id, .. } => remap(scene_id, scenes)?,
        Action::Sequence { actions } => {
            for a in actions {
                remap_action(a, sources, layers, scenes)?;
            }
        }
        _ => {
            return Err(Error::new(
                "ACTION_UNSUPPORTED",
                "Runtime import admits existing visual actions only",
            ));
        }
    }
    action.validate()
}
