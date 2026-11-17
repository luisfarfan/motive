//! Offline, declarative Creator Packs. A plan is a proposal, never a live import.
use crate::model::Error;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_MANIFEST_BYTES: usize = 256 * 1024;
fn err(code: &str, message: &str) -> Error {
    Error::new(code, message)
}
fn check(ok: bool, code: &str, message: &str) -> Result<(), Error> {
    if ok { Ok(()) } else { Err(err(code, message)) }
}
fn id(value: &str) -> Result<(), Error> {
    check(
        !value.is_empty()
            && value.len() <= 64
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_')),
        "PACK_ID",
        "Identifiers must be bounded ASCII labels, not paths or URLs",
    )
}
fn text(value: &str, max: usize) -> Result<(), Error> {
    check(
        value.len() <= max
            && !value
                .chars()
                .any(|c| c.is_control() && c != '\n' && c != '\t'),
        "PACK_TEXT",
        "Text exceeds its limit or contains control characters",
    )
}
fn native_name(value: &str) -> Result<(), Error> {
    check(
        !value.trim().is_empty()
            && value.chars().count() <= 80
            && !value.chars().any(char::is_control),
        "PACK_NAME",
        "Native scene/source names require 1..80 characters without controls",
    )
}
fn color(value: u32) -> Result<(), Error> {
    check(value <= 0xffffff, "PACK_COLOR", "RGB24 required")
}
fn opacity(value: f32) -> Result<(), Error> {
    check(
        value.is_finite() && (0.0..=1.0).contains(&value),
        "PACK_OPACITY",
        "Finite opacity in 0..1 required",
    )
}
fn dimensions(width: u32, height: u32) -> Result<(), Error> {
    check(
        (1..=1920).contains(&width) && (1..=1080).contains(&height),
        "PACK_DIMENSIONS",
        "H11 source dimensions exceeded",
    )
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum Capability {
    Text,
    Shape,
    Widget,
    LayerAnimation,
    SceneTransition,
    ImageAsset,
    VideoAsset,
    Soundboard,
    Tts,
    BrowserSource,
    VoiceRecognition,
}
impl Capability {
    pub fn h12_contracts() -> BTreeSet<Self> {
        [
            Self::Text,
            Self::Shape,
            Self::Widget,
            Self::LayerAnimation,
            Self::SceneTransition,
            Self::ImageAsset,
            Self::VideoAsset,
        ]
        .into_iter()
        .collect()
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CreatorPack {
    pub schema_version: u32,
    pub id: String,
    pub version: String,
    pub name: String,
    pub author: String,
    pub license: String,
    pub resources: Vec<Resource>,
    pub scenes: Vec<PackScene>,
    pub overlays: Vec<PackOverlay>,
    pub animations: Vec<PackAnimation>,
    pub properties: Vec<Property>,
    pub events: Vec<String>,
    pub rule_ids: Vec<String>,
    pub requires: BTreeSet<Capability>,
    pub budget: ResourceBudget,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Resource {
    pub id: String,
    pub file_name: String,
    pub kind: ResourceKind,
    pub sha256: String,
    pub bytes: u64,
    pub width: u32,
    pub height: u32,
    pub duration_ms: Option<u32>,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceKind {
    Image,
    Video,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ResourceBudget {
    pub max_resource_bytes: u64,
    pub max_estimated_texture_bytes: u64,
    pub max_simultaneous_animations: u8,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PackScene {
    pub id: String,
    pub name: String,
    pub layers: Vec<PackLayer>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PackLayer {
    pub id: String,
    pub overlay_id: String,
    pub horizontal: Layout,
    pub vertical: Layout,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Layout {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub visible: bool,
    pub order: u32,
}
impl Layout {
    pub fn validate(&self) -> Result<(), Error> {
        check(
            [self.x, self.y, self.width, self.height]
                .iter()
                .all(|x| x.is_finite())
                && self.x.abs() <= 4096.0
                && self.y.abs() <= 4096.0
                && (1.0..=4096.0).contains(&self.width)
                && (1.0..=4096.0).contains(&self.height)
                && self.order < 32,
            "PACK_LAYOUT",
            "H12 finite geometry and order bounds required",
        )
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PackOverlay {
    pub id: String,
    pub name: String,
    pub definition: VisualDefinition,
}
/// Narrow data-only subset matching H11 definitions. Resource references are symbolic.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum VisualDefinition {
    Text {
        text: String,
        font: Font,
        size: u32,
        color: u32,
        opacity: f32,
        align: Alignment,
        width: u32,
        height: u32,
        background: Option<u32>,
        background_opacity: f32,
        outline: bool,
    },
    Shape {
        shape: Shape,
        width: u32,
        height: u32,
        color: u32,
        opacity: f32,
        border_color: Option<u32>,
        border_width: u32,
    },
    Widget {
        widget: Widget,
    },
    Image {
        resource_id: String,
        opacity: f32,
    },
    Video {
        resource_id: String,
        opacity: f32,
        looping: bool,
    },
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
pub enum Font {
    Helvetica,
    Arial,
    Menlo,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    Left,
    Center,
    Right,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    Rectangle,
    Circle,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum WidgetKind {
    LowerThird,
    Countdown,
    Alert,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Widget {
    pub kind: WidgetKind,
    pub title: String,
    pub subtitle: String,
    pub width: u32,
    pub height: u32,
    pub background: u32,
    pub accent: u32,
    pub color: u32,
    pub opacity: f32,
    pub duration_ms: u32,
}
impl VisualDefinition {
    fn capability(&self) -> Capability {
        match self {
            Self::Text { .. } => Capability::Text,
            Self::Shape { .. } => Capability::Shape,
            Self::Widget { .. } => Capability::Widget,
            Self::Image { .. } => Capability::ImageAsset,
            Self::Video { .. } => Capability::VideoAsset,
        }
    }
    pub fn validate(&self) -> Result<(), Error> {
        match self {
            Self::Text {
                text: t,
                size,
                color: c,
                opacity: o,
                width,
                height,
                background,
                background_opacity,
                ..
            } => {
                text(t, 4096)?;
                dimensions(*width, *height)?;
                color(*c)?;
                opacity(*o)?;
                opacity(*background_opacity)?;
                if let Some(c) = background {
                    color(*c)?;
                }
                check(
                    (8..=192).contains(size)
                        && t.lines().count() <= 16
                        && t.chars().count().saturating_mul(*size as usize) <= 24576,
                    "PACK_TEXT_RENDER",
                    "H11 text render budget exceeded",
                )?;
            }
            Self::Shape {
                width,
                height,
                color: c,
                opacity: o,
                border_color,
                border_width,
                ..
            } => {
                dimensions(*width, *height)?;
                color(*c)?;
                opacity(*o)?;
                if let Some(c) = border_color {
                    color(*c)?;
                }
                check(
                    *border_width <= 32 && *border_width <= (*width).min(*height) / 2,
                    "PACK_BORDER",
                    "Border exceeds H11 limits",
                )?;
            }
            Self::Widget { widget: w } => {
                text(&w.title, 4096)?;
                text(&w.subtitle, 4096)?;
                dimensions(w.width, w.height)?;
                check(
                    w.width >= 240
                        && w.height >= 100
                        && w.title.chars().count() <= 160
                        && w.subtitle.chars().count() <= 256
                        && w.title.lines().count() <= 3
                        && w.subtitle.lines().count() <= 4,
                    "PACK_WIDGET",
                    "Widget size/text exceeds H11 limits",
                )?;
                for c in [w.background, w.accent, w.color] {
                    color(c)?;
                }
                opacity(w.opacity)?;
                check(
                    match w.kind {
                        WidgetKind::LowerThird => w.duration_ms == 0,
                        WidgetKind::Countdown => (1000..=3600000).contains(&w.duration_ms),
                        WidgetKind::Alert => (100..=60000).contains(&w.duration_ms),
                    },
                    "PACK_WIDGET_DURATION",
                    "Unsupported widget duration",
                )?;
            }
            Self::Image {
                resource_id,
                opacity: o,
            }
            | Self::Video {
                resource_id,
                opacity: o,
                ..
            } => {
                id(resource_id)?;
                opacity(*o)?;
            }
        }
        Ok(())
    }
    fn texture_bytes(&self) -> u64 {
        let (w, h, factor) = match self {
            Self::Text { width, height, .. } => (*width, *height, 3),
            Self::Shape { width, height, .. } => (*width, *height, 1),
            Self::Widget { widget } => (widget.width, widget.height, 4),
            Self::Image { .. } => (2048, 2048, 1),
            Self::Video { .. } => (1920, 1080, 4),
        };
        u64::from(w) * u64::from(h) * 4 * factor
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PackAnimation {
    pub id: String,
    pub scene_id: String,
    pub layer_id: String,
    pub kind: AnimationKind,
    pub easing: Easing,
    pub duration_ms: u32,
    pub distance: f32,
    pub scale_from: f32,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AnimationKind {
    FadeIn,
    FadeOut,
    SlideIn,
    SlideOut,
    ScaleIn,
    ScaleOut,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Easing {
    Linear,
    EaseIn,
    EaseOut,
    EaseInOut,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Property {
    pub id: String,
    pub label: String,
    pub overlay_id: String,
    pub target: PropertyTarget,
    pub value: PropertyValue,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum PropertyTarget {
    TextContent,
    WidgetTitle,
    WidgetSubtitle,
    ShapeColor,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(
    tag = "type",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum PropertyValue {
    Text(String),
    Color(u32),
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallPlan {
    pub pack_id: String,
    pub pack_version: String,
    pub schema_version: u32,
    pub executable: bool,
    pub requires_idle: bool,
    pub unavailable: Vec<Capability>,
    pub estimated_texture_bytes: u64,
    pub steps: Vec<PlanStep>,
    pub limitations: Vec<String>,
}
/// An adapter must resolve symbolic references from actual replies. These are not wire commands.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub enum PlanStep {
    ImportAssetAfterLocalAuthorization {
        resource_ref: String,
        file_name: String,
    },
    CreateScene {
        scene_ref: String,
        name: String,
    },
    CreateOverlay {
        scene_ref: String,
        source_ref: String,
        first_layer_ref: String,
        name: String,
        definition: VisualDefinition,
    },
    AddLayer {
        scene_ref: String,
        source_ref: String,
        layer_ref: String,
    },
    SetTransform {
        scene_ref: String,
        layer_ref: String,
        variant: Orientation,
        transform: Layout,
    },
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    Horizontal,
    Vertical,
}

impl CreatorPack {
    pub fn from_json(input: &str) -> Result<Self, Error> {
        check(
            input.len() <= MAX_MANIFEST_BYTES,
            "PACK_SIZE",
            "Manifest exceeds 256 KiB",
        )?;
        let pack: Self = serde_json::from_str(input).map_err(|_| {
            err(
                "PACK_SCHEMA",
                "Malformed manifest, missing field or unknown schema member",
            )
        })?;
        pack.validate()?;
        Ok(pack)
    }
    pub fn validate(&self) -> Result<(), Error> {
        check(
            self.schema_version == 1,
            "PACK_VERSION",
            "Only Creator Pack schema 1 is supported",
        )?;
        id(&self.id)?;
        text(&self.name, 128)?;
        text(&self.author, 128)?;
        check(
            !self.name.trim().is_empty() && !self.author.trim().is_empty(),
            "PACK_METADATA",
            "Name and author required",
        )?;
        let parts: Vec<_> = self.version.split('.').collect();
        check(
            parts.len() == 3
                && parts.iter().all(|p| {
                    !p.is_empty() && p.len() <= 6 && p.bytes().all(|b| b.is_ascii_digit())
                }),
            "PACK_VERSION",
            "Bounded numeric major.minor.patch version required",
        )?;
        check(
            matches!(
                self.license.as_str(),
                "GPL-3.0-or-later" | "CC0-1.0" | "MIT" | "CC-BY-4.0"
            ),
            "PACK_LICENSE",
            "Explicit supported open license required",
        )?;
        check(
            !self.scenes.is_empty()
                && self.scenes.len() <= 8
                && !self.overlays.is_empty()
                && self.overlays.len() <= 16
                && self.scenes.iter().map(|s| s.layers.len()).sum::<usize>() <= 32
                && self.animations.len() <= 64
                && self.properties.len() <= 64
                && self.resources.len() <= 16
                && self.events.len() <= 32
                && self.rule_ids.len() <= 64,
            "PACK_LIMIT",
            "Pack exceeds graph or manifest limits",
        )?;
        check(
            self.budget.max_resource_bytes <= 512 * 1024 * 1024
                && self.budget.max_estimated_texture_bytes <= 256 * 1024 * 1024
                && self.budget.max_simultaneous_animations <= 8,
            "PACK_BUDGET",
            "Resource budget exceeds H12 limits",
        )?;
        let mut resources = BTreeMap::new();
        let mut resource_bytes = 0_u64;
        for resource in &self.resources {
            id(&resource.id)?;
            check(
                resources.insert(resource.id.as_str(), resource).is_none(),
                "PACK_DUPLICATE",
                "Duplicate resource identifier",
            )?;
            let f = &resource.file_name;
            check(
                !f.is_empty()
                    && f.len() <= 120
                    && f.as_bytes()[0].is_ascii_alphanumeric()
                    && f.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_'))
                    && !f.contains(".."),
                "PACK_RESOURCE",
                "Only authorized inbox basenames may be proposed; paths and URLs are forbidden",
            )?;
            check(
                resource.sha256.len() == 64
                    && resource
                        .sha256
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
                "PACK_RESOURCE",
                "SHA-256 metadata required",
            )?;
            check(
                resource.bytes > 0 && resource.bytes <= 64 * 1024 * 1024,
                "PACK_RESOURCE",
                "Resource byte limit exceeded",
            )?;
            let ext = f.rsplit('.').next().unwrap_or("").to_ascii_lowercase();
            check(
                match resource.kind {
                    ResourceKind::Image => {
                        ["png", "jpg", "jpeg", "webp"].contains(&ext.as_str())
                            && resource.width > 0
                            && resource.height > 0
                            && resource.width <= 2048
                            && resource.height <= 2048
                            && resource.duration_ms.is_none()
                    }
                    ResourceKind::Video => {
                        ["mp4", "mov", "webm"].contains(&ext.as_str())
                            && resource.width > 0
                            && resource.height > 0
                            && resource.width <= 1920
                            && resource.height <= 1080
                            && resource.duration_ms.is_some_and(|d| d > 0 && d <= 60000)
                    }
                },
                "PACK_RESOURCE",
                "Unsupported declared media type or dimensions",
            )?;
            resource_bytes += resource.bytes;
        }
        check(
            resource_bytes <= self.budget.max_resource_bytes,
            "PACK_BUDGET",
            "Declared resources exceed pack byte budget",
        )?;
        let mut overlays = BTreeMap::new();
        let mut estimate = 0_u64;
        for overlay in &self.overlays {
            id(&overlay.id)?;
            native_name(&overlay.name)?;
            overlay.definition.validate()?;
            check(
                overlays.insert(overlay.id.as_str(), overlay).is_none(),
                "PACK_DUPLICATE",
                "Duplicate source identifier",
            )?;
            check(
                self.requires.contains(&overlay.definition.capability()),
                "PACK_CAPABILITY",
                "Overlay capability must be declared",
            )?;
            match &overlay.definition {
                VisualDefinition::Image { resource_id, .. }
                | VisualDefinition::Video { resource_id, .. } => {
                    let resource = resources
                        .get(resource_id.as_str())
                        .ok_or_else(|| err("PACK_REFERENCE", "Missing resource"))?;
                    check(
                        matches!(
                            (&overlay.definition, resource.kind),
                            (VisualDefinition::Image { .. }, ResourceKind::Image)
                                | (VisualDefinition::Video { .. }, ResourceKind::Video)
                        ),
                        "PACK_RESOURCE",
                        "Resource type mismatch",
                    )?;
                }
                _ => {}
            }
            estimate += overlay.definition.texture_bytes();
        }
        check(
            estimate <= self.budget.max_estimated_texture_bytes,
            "PACK_BUDGET",
            "Planning texture estimate exceeds budget (not a native RSS measurement)",
        )?;
        let mut scenes = BTreeSet::new();
        let mut layers = BTreeSet::new();
        let mut layer_ids = BTreeSet::new();
        let mut used = BTreeSet::new();
        for scene in &self.scenes {
            id(&scene.id)?;
            native_name(&scene.name)?;
            check(
                scenes.insert(scene.id.as_str()) && !scene.layers.is_empty(),
                "PACK_SCENE",
                "Duplicate or empty scene",
            )?;
            for layer in &scene.layers {
                id(&layer.id)?;
                check(
                    layers.insert((scene.id.as_str(), layer.id.as_str()))
                        && layer_ids.insert(layer.id.as_str())
                        && overlays.contains_key(layer.overlay_id.as_str()),
                    "PACK_REFERENCE",
                    "Duplicate layer or unknown overlay reference",
                )?;
                layer.horizontal.validate()?;
                layer.vertical.validate()?;
                used.insert(layer.overlay_id.as_str());
            }
        }
        check(
            used.len() == overlays.len(),
            "PACK_UNUSED_SOURCE",
            "Every proposed source must have at least one layer",
        )?;
        let mut animation_ids = BTreeSet::new();
        for a in &self.animations {
            id(&a.id)?;
            check(
                animation_ids.insert(a.id.as_str())
                    && layers.contains(&(a.scene_id.as_str(), a.layer_id.as_str())),
                "PACK_REFERENCE",
                "Duplicate animation or missing layer",
            )?;
            check(
                (100..=10000).contains(&a.duration_ms)
                    && a.distance.is_finite()
                    && (-1920.0..=1920.0).contains(&a.distance)
                    && a.scale_from.is_finite()
                    && (0.1..=2.0).contains(&a.scale_from)
                    && (!matches!(a.kind, AnimationKind::FadeIn | AnimationKind::FadeOut)
                        || a.easing == Easing::Linear),
                "PACK_ANIMATION",
                "Animation exceeds official H11 contract",
            )?;
        }
        check(
            self.animations.is_empty()
                || (self.requires.contains(&Capability::LayerAnimation)
                    && self.budget.max_simultaneous_animations > 0),
            "PACK_CAPABILITY",
            "Animations require a declared capability and nonzero budget",
        )?;
        let mut properties = BTreeSet::new();
        for property in &self.properties {
            id(&property.id)?;
            text(&property.label, 128)?;
            check(
                properties.insert(property.id.as_str()),
                "PACK_DUPLICATE",
                "Duplicate property",
            )?;
            let mut definition = overlays
                .get(property.overlay_id.as_str())
                .ok_or_else(|| err("PACK_REFERENCE", "Property source missing"))?
                .definition
                .clone();
            apply_property(&mut definition, property.target, &property.value)?;
            definition.validate()?;
        }
        let mut events = BTreeSet::new();
        for event in &self.events {
            check(
                events.insert(event)
                    && [
                        "manual.button_pressed",
                        "keyboard.shortcut",
                        "voice.keyword_detected",
                        "chat.message",
                        "chat.command",
                        "viewer.follow",
                        "viewer.subscribe",
                        "viewer.donation",
                        "viewer.reward_redeemed",
                        "timer.completed",
                        "production.started",
                        "production.stopped",
                        "motive.custom_event",
                    ]
                    .contains(&event.as_str()),
                "PACK_EVENT",
                "Unknown or duplicate event kind",
            )?;
        }
        let mut rules = BTreeSet::new();
        for rule in &self.rule_ids {
            id(rule)?;
            check(
                rules.insert(rule),
                "PACK_DUPLICATE",
                "Duplicate rule binding",
            )?;
        }
        Ok(())
    }
    /// Apply a typed property to an offline copy. It never sends update_overlay.
    pub fn set_property(&mut self, property_id: &str, value: PropertyValue) -> Result<(), Error> {
        let mut candidate = self.clone();
        let property = candidate
            .properties
            .iter_mut()
            .find(|p| p.id == property_id)
            .ok_or_else(|| err("PACK_REFERENCE", "Unknown property"))?;
        let overlay = candidate
            .overlays
            .iter_mut()
            .find(|o| o.id == property.overlay_id)
            .ok_or_else(|| err("PACK_REFERENCE", "Property source missing"))?;
        apply_property(&mut overlay.definition, property.target, &value)?;
        property.value = value;
        candidate.validate()?;
        *self = candidate;
        Ok(())
    }
    pub fn plan(&self, available: &BTreeSet<Capability>) -> Result<InstallPlan, Error> {
        self.validate()?;
        let mut steps = Vec::new();
        for resource in &self.resources {
            steps.push(PlanStep::ImportAssetAfterLocalAuthorization {
                resource_ref: resource.id.clone(),
                file_name: resource.file_name.clone(),
            });
        }
        let mut created = BTreeSet::new();
        for scene in &self.scenes {
            steps.push(PlanStep::CreateScene {
                scene_ref: scene.id.clone(),
                name: scene.name.clone(),
            });
            for layer in &scene.layers {
                if created.insert(&layer.overlay_id) {
                    let overlay = self
                        .overlays
                        .iter()
                        .find(|o| o.id == layer.overlay_id)
                        .expect("validated reference");
                    steps.push(PlanStep::CreateOverlay {
                        scene_ref: scene.id.clone(),
                        source_ref: overlay.id.clone(),
                        first_layer_ref: layer.id.clone(),
                        name: overlay.name.clone(),
                        definition: overlay.definition.clone(),
                    });
                } else {
                    steps.push(PlanStep::AddLayer {
                        scene_ref: scene.id.clone(),
                        source_ref: layer.overlay_id.clone(),
                        layer_ref: layer.id.clone(),
                    });
                }
                steps.push(PlanStep::SetTransform {
                    scene_ref: scene.id.clone(),
                    layer_ref: layer.id.clone(),
                    variant: Orientation::Horizontal,
                    transform: layer.horizontal.clone(),
                });
                steps.push(PlanStep::SetTransform {
                    scene_ref: scene.id.clone(),
                    layer_ref: layer.id.clone(),
                    variant: Orientation::Vertical,
                    transform: layer.vertical.clone(),
                });
            }
        }
        Ok(InstallPlan {pack_id:self.id.clone(),pack_version:self.version.clone(),schema_version:1,executable:false,requires_idle:true,unavailable:self.requires.difference(available).copied().collect(),estimated_texture_bytes:self.overlays.iter().map(|o|o.definition.texture_bytes()).sum(),steps,limitations:vec!["Offline proposal only; no Production importer or live acceptance has been implemented.".into(),"Resolve scene/source/layer IDs from real replies; verify existing graph plus pack fits global budgets on the owner before applying.".into(),"Resource metadata is untrusted until authorized staging and the existing importer verify actual bytes; no file is read by this validator.".into(),"Properties and rules need explicit binding; no actions, animations, timers or outputs start on import.".into(),"Texture estimate is a planning heuristic, not a verified bound on native memory or decoded asset validation.".into()]})
    }
}
fn apply_property(
    definition: &mut VisualDefinition,
    target: PropertyTarget,
    value: &PropertyValue,
) -> Result<(), Error> {
    match (definition, target, value) {
        (
            VisualDefinition::Text { text, .. },
            PropertyTarget::TextContent,
            PropertyValue::Text(value),
        ) => *text = value.clone(),
        (
            VisualDefinition::Widget { widget },
            PropertyTarget::WidgetTitle,
            PropertyValue::Text(value),
        ) => widget.title = value.clone(),
        (
            VisualDefinition::Widget { widget },
            PropertyTarget::WidgetSubtitle,
            PropertyValue::Text(value),
        ) => widget.subtitle = value.clone(),
        (
            VisualDefinition::Shape { color, .. },
            PropertyTarget::ShapeColor,
            PropertyValue::Color(value),
        ) => *color = *value,
        _ => {
            return Err(err(
                "PACK_PROPERTY_TYPE",
                "Property target/type does not match the overlay",
            ));
        }
    }
    Ok(())
}
