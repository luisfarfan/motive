use crate::{Error, check, label};
use motive_show_control::packs::{Capability, Layout, Resource, VisualDefinition};
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
                d.validate()?;
                check(
                    source.video == matches!(d, VisualDefinition::Video { .. }),
                    "BUDGET_UNDERSTATED",
                    "Video reservation must match native definition",
                )?;
            }
        }
        for (id, a) in &self.assets {
            label(&id.0)?;
            crate::hash(&a.descriptor.sha256)?;
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
            (r.width, r.height, 0)
        }
    };
    Ok(u64::from(w) * u64::from(h) * 8 + extra)
}
