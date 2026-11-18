use crate::{Error, check, label};
use motive_show_control::{
    actions::{LayerBinding, ProductionSnapshot, SourceKind, SourceReadiness},
    packs::{
        Capability, CreatorPack, Layout, PackLayer, PackOverlay, PackScene, Resource,
        ResourceBudget, ResourceKind, VisualDefinition, WidgetKind,
    },
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

// These are adapter identities, not new Show Control enums or a project schema.
macro_rules! identity {
    ($name:ident) => {
        #[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
        #[serde(transparent)]
        pub struct $name(pub String);
    };
}
identity!(SceneId);
identity!(SourceId);
identity!(LayerId);
identity!(ResourceId);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub id: SourceId,
    /// None means an existing camera/capture/pattern whose reservation is owner supplied.
    pub definition: Option<VisualDefinition>,
    pub texture_bytes: u64,
    pub video: bool,
    pub installation: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Layer {
    pub id: LayerId,
    pub source: SourceId,
    pub scene: SceneId,
    pub horizontal: Layout,
    pub vertical: Layout,
    pub installation: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Asset {
    pub id: ResourceId,
    pub descriptor: Resource,
    pub license: String,
    pub installation: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub session: String,
    pub revision: u64,
    pub busy: bool,
    pub capabilities: BTreeSet<Capability>,
    pub scenes: BTreeSet<SceneId>,
    pub sources: BTreeMap<SourceId, Source>,
    pub layers: BTreeMap<LayerId, Layer>,
    pub assets: BTreeMap<ResourceId, Asset>,
}
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    pub scenes: usize,
    pub sources: usize,
    pub layers: usize,
    pub video_sources: usize,
    pub texture_bytes: u64,
    pub resource_bytes: u64,
    pub resource_count: usize,
}
impl Budget {
    pub fn validate(&self) -> Result<(), Error> {
        check(
            self.scenes <= 8
                && self.sources <= 16
                && self.layers <= 32
                && self.video_sources <= 4
                && self.texture_bytes <= 256 * 1024 * 1024
                && self.resource_bytes <= 512 * 1024 * 1024
                && self.resource_count <= 128,
            "GLOBAL_BUDGET",
            "Existing graph/texture or 128 assets/512 MiB inventory limits exceeded",
        )
    }
}
impl Snapshot {
    pub fn empty_fixture() -> Self {
        Self {
            session: "offline-owner-session".into(),
            revision: 1,
            busy: false,
            capabilities: Capability::h12_contracts(),
            scenes: BTreeSet::from([SceneId("fixture-scene".into())]),
            sources: BTreeMap::new(),
            layers: BTreeMap::new(),
            assets: BTreeMap::new(),
        }
    }
    pub fn budget(&self) -> Budget {
        Budget {
            scenes: self.scenes.len(),
            sources: self.sources.len(),
            layers: self.layers.len(),
            video_sources: self.sources.values().filter(|s| s.video).count(),
            texture_bytes: self
                .sources
                .values()
                .fold(0u64, |n, s| n.saturating_add(s.texture_bytes)),
            resource_bytes: self
                .assets
                .values()
                .fold(0u64, |n, a| n.saturating_add(a.descriptor.bytes)),
            resource_count: self.assets.len(),
        }
    }
    pub fn validate(&self) -> Result<(), Error> {
        label(&self.session)?;
        self.budget().validate()?;
        for id in &self.scenes {
            label(&id.0)?;
        }
        for (id, source) in &self.sources {
            label(&id.0)?;
            check(id == &source.id, "IDENTITY", "Source key differs from ID")?;
            if let Some(d) = &source.definition {
                // Upstream CreatorPack uses symbolic resource refs (<=64 bytes).
                // An owner receipt may instead use a 70-byte native asset hash ID.
                let mut symbolic = d.clone();
                if let VisualDefinition::Image { resource_id, .. }
                | VisualDefinition::Video { resource_id, .. } = &mut symbolic
                {
                    *resource_id = "resource-validation".into();
                }
                symbolic.validate()?;
                check(
                    source.video == matches!(d, VisualDefinition::Video { .. }),
                    "BUDGET_UNDERSTATED",
                    "Video reservation must match native definition",
                )?;
            }
        }
        for (id, a) in &self.assets {
            resource_id(&id.0)?;
            crate::hash(&a.descriptor.sha256)?;
            validate_resource(&a.descriptor, &a.license)?;
            if id.0.len() == 70 && id.0.starts_with("asset-") {
                check(
                    id.0[6..] == a.descriptor.sha256,
                    "ASSET_IDENTITY",
                    "Native hash ID differs from descriptor",
                )?;
            }
            check(
                id == &a.id && a.descriptor.bytes > 0 && a.descriptor.bytes <= 64 * 1024 * 1024,
                "ASSET_IDENTITY",
                "Invalid asset record",
            )?;
        }
        for (id, layer) in &self.layers {
            label(&id.0)?;
            check(
                id == &layer.id
                    && self.scenes.contains(&layer.scene)
                    && self.sources.contains_key(&layer.source),
                "ORPHAN_REFERENCE",
                "Layer references missing scene/source",
            )?;
            layer.horizontal.validate()?;
            layer.vertical.validate()?;
        }
        // A lower estimate supplied for a native source is never accepted.
        for s in self.sources.values() {
            if let Some(d) = &s.definition {
                let resources: BTreeMap<_, _> = self
                    .assets
                    .values()
                    .map(|a| (a.id.0.clone(), a.descriptor.clone()))
                    .collect();
                check(
                    s.texture_bytes >= texture_bytes(d, &resources)?,
                    "BUDGET_UNDERSTATED",
                    "Native texture reservation too small",
                )?;
            }
        }
        Ok(())
    }
}

pub fn resource_id(value: &str) -> Result<(), Error> {
    if let Some(hash) = value.strip_prefix("asset-")
        && hash.len() == 64
    {
        return crate::hash(hash);
    }
    label(value)
}

/// Resource has no public standalone validator upstream. Validate a minimal
/// typed CreatorPack through that existing implementation instead of copying its
/// format, extension and dimension rules into another schema.
pub fn validate_resource(resource: &Resource, license: &str) -> Result<(), Error> {
    let definition = match resource.kind {
        ResourceKind::Image => VisualDefinition::Image {
            resource_id: resource.id.clone(),
            opacity: 1.,
        },
        ResourceKind::Video => VisualDefinition::Video {
            resource_id: resource.id.clone(),
            opacity: 1.,
            looping: false,
        },
    };
    let layout = Layout {
        x: 0.,
        y: 0.,
        width: 1.,
        height: 1.,
        visible: false,
        order: 0,
    };
    CreatorPack {
        schema_version: 1,
        id: "resource-validation".into(),
        version: "1.0.0".into(),
        name: "Resource validation".into(),
        author: "Motive validator".into(),
        license: license.into(),
        resources: vec![resource.clone()],
        scenes: vec![PackScene {
            id: "scene".into(),
            name: "Validation".into(),
            layers: vec![PackLayer {
                id: "layer".into(),
                overlay_id: "source".into(),
                horizontal: layout.clone(),
                vertical: layout,
            }],
        }],
        overlays: vec![PackOverlay {
            id: "source".into(),
            name: "Validation".into(),
            definition,
        }],
        animations: vec![],
        properties: vec![],
        events: vec![],
        rule_ids: vec![],
        requires: BTreeSet::from([if resource.kind == ResourceKind::Image {
            Capability::ImageAsset
        } else {
            Capability::VideoAsset
        }]),
        budget: ResourceBudget {
            max_resource_bytes: 64 * 1024 * 1024,
            max_estimated_texture_bytes: 256 * 1024 * 1024,
            max_simultaneous_animations: 0,
        },
    }
    .validate()
}

impl Snapshot {
    /// Semantic projection only: readiness is hypothetical and never native evidence.
    pub fn action_snapshot(&self) -> Result<ProductionSnapshot, Error> {
        self.validate()?;
        let mut out = ProductionSnapshot {
            pid: 1,
            ..ProductionSnapshot::default()
        };
        out.revision = self.revision;
        out.structural_busy = self.busy;
        for s in self.sources.values() {
            out.sources.insert(s.id.0.clone(), SourceReadiness::Ready);
            let Some(d) = &s.definition else {
                continue;
            };
            let kind = match d {
                VisualDefinition::Text { .. } => SourceKind::Text,
                VisualDefinition::Shape { .. } => SourceKind::Shape,
                VisualDefinition::Image { .. } => SourceKind::Image,
                VisualDefinition::Video { .. } => SourceKind::Video,
                VisualDefinition::Widget { widget } => match widget.kind {
                    WidgetKind::LowerThird => SourceKind::LowerThird,
                    WidgetKind::Alert => SourceKind::Alert,
                    WidgetKind::Countdown => SourceKind::Countdown,
                },
            };
            out.source_kinds.insert(s.id.0.clone(), kind);
            if matches!(d, VisualDefinition::Text { .. }) {
                let mut value = serde_json::to_value(d)
                    .map_err(|_| Error::new("ACTION_DEFINITION", "Invalid text"))?;
                value
                    .as_object_mut()
                    .expect("tagged definition")
                    .remove("kind");
                out.text_definitions.insert(
                    s.id.0.clone(),
                    serde_json::from_value(value)
                        .map_err(|_| Error::new("ACTION_DEFINITION", "Invalid text definition"))?,
                );
            }
        }
        for scene in &self.scenes {
            out.scenes.insert(
                scene.0.clone(),
                self.layers
                    .values()
                    .filter(|l| &l.scene == scene)
                    .map(|l| l.source.0.clone())
                    .collect(),
            );
        }
        for layer in self.layers.values() {
            out.layers.insert(
                layer.id.0.clone(),
                LayerBinding {
                    scene_id: layer.scene.0.clone(),
                    source_id: layer.source.0.clone(),
                },
            );
        }
        Ok(out)
    }
}

/// Same documented conservative H11 estimate used by Element Lab; not measured RSS.
pub fn texture_bytes(
    definition: &VisualDefinition,
    resources: &BTreeMap<String, Resource>,
) -> Result<u64, Error> {
    let (w, h, extra) = match definition {
        VisualDefinition::Text { width, height, .. } => (*width, *height, 8 * 1024 * 1024),
        VisualDefinition::Shape { width, height, .. } => (*width, *height, 0),
        VisualDefinition::Widget { widget } => (widget.width, widget.height, 16 * 1024 * 1024),
        VisualDefinition::Image { resource_id, .. }
        | VisualDefinition::Video { resource_id, .. } => {
            let r = resources.get(resource_id).ok_or_else(|| {
                Error::new("RESOURCE_MISSING", "Missing authorized resource receipt")
            })?;
            check(
                matches!(
                    (definition, r.kind),
                    (VisualDefinition::Image { .. }, ResourceKind::Image)
                        | (VisualDefinition::Video { .. }, ResourceKind::Video)
                ),
                "RESOURCE_KIND",
                "Source and resource kind mismatch",
            )?;
            (r.width, r.height, 0)
        }
    };
    u64::from(w)
        .checked_mul(u64::from(h))
        .and_then(|n| n.checked_mul(8))
        .and_then(|n| n.checked_add(extra))
        .ok_or_else(|| Error::new("BUDGET_OVERFLOW", "Invalid resource dimensions"))
}
