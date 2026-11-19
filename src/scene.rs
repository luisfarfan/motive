use crate::core::{Variant, WindowIdentity};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// Runtime controls; project v3 continues to describe compositions only.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TransitionKind {
    #[default]
    Cut,
    Fade,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TransitionConfig {
    pub kind: TransitionKind,
    pub duration_ms: u32,
}
impl TransitionConfig {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            match self.kind {
                TransitionKind::Cut => self.duration_ms == 0,
                TransitionKind::Fade => (100..=5000).contains(&self.duration_ms),
            },
            "INVALID_TRANSITION: Cut requires 0 ms; Fade requires 100–5000 ms"
        );
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TransitionPhase {
    Idle,
    Preparing,
    Running,
    Completed,
    Cancelled,
    Failed,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct TransitionState {
    pub operation_id: u64,
    pub phase: TransitionPhase,
    pub current_scene: String,
    pub from_scene: Option<String>,
    pub target_scene: Option<String>,
    pub kind: TransitionKind,
    pub duration_ms: u32,
    pub progress: f32,
    pub error: Option<String>,
    pub blocked_sources: Vec<serde_json::Value>,
    pub source_instances_created: u64,
    pub scenes_built: u64,
}
impl TransitionState {
    pub fn busy(&self) -> bool {
        matches!(
            self.phase,
            TransitionPhase::Preparing | TransitionPhase::Running
        )
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Transform {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub visible: bool,
    pub order: u32,
}
impl Transform {
    pub fn rect(x: f32, y: f32, width: f32, height: f32, order: u32) -> Self {
        Self {
            x,
            y,
            width,
            height,
            visible: true,
            order,
        }
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            [self.x, self.y, self.width, self.height]
                .iter()
                .all(|v| v.is_finite())
                && self.x.abs() <= 4096.
                && self.y.abs() <= 4096.
                && (1.0..=4096.0).contains(&self.width)
                && (1.0..=4096.0).contains(&self.height)
                && self.order < 32,
            "INVALID_TRANSFORM: bounded finite geometry required"
        );
        Ok(())
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Layouts {
    pub horizontal: Transform,
    pub vertical: Transform,
}
impl Layouts {
    pub fn get(&self, v: Variant) -> &Transform {
        match v {
            Variant::Horizontal => &self.horizontal,
            Variant::Vertical => &self.vertical,
        }
    }
    pub fn get_mut(&mut self, v: Variant) -> &mut Transform {
        match v {
            Variant::Horizontal => &mut self.horizontal,
            Variant::Vertical => &mut self.vertical,
        }
    }
    pub fn full() -> Self {
        Self {
            horizontal: Transform::rect(0., 0., 960., 540., 0),
            vertical: Transform::rect(0., 0., 540., 960., 0),
        }
    }
    pub fn overlay() -> Self {
        Self {
            horizontal: Transform::rect(32., 436., 320., 72., 1),
            vertical: Transform::rect(32., 856., 320., 72., 1),
        }
    }
    pub fn secondary() -> Self {
        Self {
            horizontal: Transform::rect(640., 32., 288., 162., 2),
            vertical: Transform::rect(268., 32., 240., 135., 2),
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SourceKind {
    Pattern,
    Overlay {
        color: u32,
    },
    Window {
        window: WindowIdentity,
    },
    Display {
        display_uuid: String,
    },
    Application {
        bundle_id: String,
        display_uuid: String,
    },
    Camera {
        device_id: String,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SourceInput {
    Pattern,
    Overlay {
        color: u32,
    },
    Window {
        window_id: u32,
    },
    Display {
        display_uuid: String,
    },
    Application {
        bundle_id: String,
        display_uuid: String,
    },
    Camera {
        device_id: String,
    },
}
impl SourceKind {
    pub fn is_screen_capture(&self) -> bool {
        matches!(
            self,
            Self::Window { .. } | Self::Display { .. } | Self::Application { .. }
        )
    }
    pub fn requires_v6(&self) -> bool {
        matches!(self, Self::Display { .. } | Self::Application { .. })
    }
}

#[cfg(test)]
mod capture_tests {
    use super::*;
    #[test]
    fn shared_layers_reuse_but_duplicate_capture_resources_are_rejected() {
        let mut graph = Graph::default();
        graph.sources[0].spec = SourceKind::Application {
            bundle_id: "local.motive.fixture".into(),
            display_uuid: "00000000-0000-0000-0000-000000000001".into(),
        };
        let mut layer = graph.scenes[0].layers[0].clone();
        layer.id = "shared-layer".into();
        graph.scenes[0].layers.push(layer);
        graph.validate().unwrap();
        let mut duplicated = graph.sources[0].clone();
        duplicated.id = "duplicate-source".into();
        graph.sources.push(duplicated);
        assert!(
            graph
                .validate()
                .unwrap_err()
                .to_string()
                .starts_with("CAPTURE_IN_USE")
        );
        graph.sources.last_mut().unwrap().spec = SourceKind::Application {
            bundle_id: "local.motive.fixture".into(),
            display_uuid: "00000000-0000-0000-0000-000000000002".into(),
        };
        graph.validate().unwrap();
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VisualSource {
    pub id: String,
    pub name: String,
    pub spec: SourceKind,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub overlay: Option<crate::core::overlays::Definition>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Layer {
    pub id: String,
    pub source_id: String,
    pub layouts: Layouts,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Scene {
    pub id: String,
    pub name: String,
    pub layers: Vec<Layer>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Graph {
    pub active_scene: String,
    pub next_id: u64,
    pub sources: Vec<VisualSource>,
    pub scenes: Vec<Scene>,
}
impl Default for Graph {
    fn default() -> Self {
        Self {
            active_scene: "scene-1".into(),
            next_id: 2,
            sources: vec![
                VisualSource {
                    id: "main".into(),
                    name: "Principal".into(),
                    spec: SourceKind::Pattern,
                    overlay: None,
                },
                VisualSource {
                    id: "overlay".into(),
                    name: "Overlay".into(),
                    spec: SourceKind::Overlay { color: 0x33e8b5 },
                    overlay: None,
                },
            ],
            scenes: vec![Scene {
                id: "scene-1".into(),
                name: "Escena principal".into(),
                layers: vec![
                    Layer {
                        id: "main-layer".into(),
                        source_id: "main".into(),
                        layouts: Layouts::full(),
                    },
                    Layer {
                        id: "overlay-layer".into(),
                        source_id: "overlay".into(),
                        layouts: Layouts::overlay(),
                    },
                ],
            }],
        }
    }
}
pub fn valid_name(name: &str) -> bool {
    !name.trim().is_empty() && name.chars().count() <= 80 && !name.chars().any(char::is_control)
}
fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 48
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}
impl Graph {
    pub fn id(&mut self, prefix: &str) -> String {
        loop {
            let id = format!("{prefix}-{}", self.next_id);
            self.next_id += 1;
            if !self.sources.iter().any(|s| s.id == id)
                && !self
                    .scenes
                    .iter()
                    .any(|s| s.id == id || s.layers.iter().any(|l| l.id == id))
            {
                return id;
            }
        }
    }
    pub fn scene(&self, id: &str) -> anyhow::Result<&Scene> {
        self.scenes
            .iter()
            .find(|s| s.id == id)
            .ok_or_else(|| anyhow::anyhow!("SCENE_UNAVAILABLE"))
    }
    pub fn scene_mut(&mut self, id: &str) -> anyhow::Result<&mut Scene> {
        self.scenes
            .iter_mut()
            .find(|s| s.id == id)
            .ok_or_else(|| anyhow::anyhow!("SCENE_UNAVAILABLE"))
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            !self.scenes.is_empty()
                && self.scenes.len() <= 8
                && self.sources.len() <= 16
                && self.scenes.iter().map(|s| s.layers.len()).sum::<usize>() <= 32
                && self.next_id < 1_000_000_000,
            "GRAPH_LIMIT"
        );
        self.scene(&self.active_scene)?;
        let mut ids = BTreeSet::new();
        let mut cameras = BTreeSet::new();
        let mut captures = BTreeSet::new();
        for source in &self.sources {
            anyhow::ensure!(
                valid_id(&source.id)
                    && !["audio", "output"].contains(&source.id.as_str())
                    && ids.insert(&source.id)
                    && valid_name(&source.name),
                "INVALID_SOURCE"
            );
            if let Some(definition) = &source.overlay {
                anyhow::ensure!(
                    matches!(source.spec, SourceKind::Overlay { .. }),
                    "INVALID_OVERLAY_SOURCE"
                );
                definition.validate()?;
            }
            match &source.spec {
                SourceKind::Overlay { color } => {
                    anyhow::ensure!(*color <= 0xffffff, "INVALID_COLOR")
                }
                SourceKind::Camera { device_id } => {
                    anyhow::ensure!(
                        !device_id.is_empty() && device_id.len() < 512 && !device_id.contains('\0'),
                        "INVALID_DEVICE"
                    );
                    anyhow::ensure!(
                        cameras.insert(device_id),
                        "DEVICE_IN_USE: reuse the existing camera source with add_layer"
                    );
                }
                SourceKind::Window { window } => anyhow::ensure!(
                    !window.bundle_id.is_empty()
                        && window.bundle_id.len() <= 256
                        && !window.title.is_empty()
                        && window.title.len() <= 512,
                    "INVALID_WINDOW_IDENTITY"
                ),
                SourceKind::Display { display_uuid } => {
                    crate::core::capture::validate_display(display_uuid)?;
                    anyhow::ensure!(
                        captures.insert(("", display_uuid.as_str())),
                        "CAPTURE_IN_USE: reuse the existing source with add_layer"
                    );
                }
                SourceKind::Application {
                    bundle_id,
                    display_uuid,
                } => {
                    crate::core::capture::validate_application(bundle_id)?;
                    crate::core::capture::validate_display(display_uuid)?;
                    anyhow::ensure!(
                        captures.insert((bundle_id.as_str(), display_uuid.as_str())),
                        "CAPTURE_IN_USE: reuse the existing source with add_layer"
                    );
                }
                _ => {}
            }
        }
        for scene in &self.scenes {
            anyhow::ensure!(
                valid_id(&scene.id) && ids.insert(&scene.id) && valid_name(&scene.name),
                "INVALID_SCENE"
            );
            for layer in &scene.layers {
                anyhow::ensure!(
                    valid_id(&layer.id)
                        && ids.insert(&layer.id)
                        && self.sources.iter().any(|s| s.id == layer.source_id),
                    "INVALID_LAYER_REFERENCE"
                );
                layer.layouts.horizontal.validate()?;
                layer.layouts.vertical.validate()?;
            }
        }
        Ok(())
    }
}

#[derive(Default, Debug)]
pub struct Recovery {
    pub pending: BTreeSet<String>,
}
impl Recovery {
    pub fn required(&self) -> bool {
        !self.pending.is_empty()
    }
    pub fn resolve(&mut self, source: &str) {
        self.pending.remove(source);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn transitions_have_bounded_official_semantics() {
        assert!(TransitionConfig::default().validate().is_ok());
        for (kind, duration_ms, valid) in [
            (TransitionKind::Cut, 1, false),
            (TransitionKind::Fade, 0, false),
            (TransitionKind::Fade, 99, false),
            (TransitionKind::Fade, 100, true),
            (TransitionKind::Fade, 5000, true),
            (TransitionKind::Fade, 5001, false),
        ] {
            assert_eq!(
                TransitionConfig { kind, duration_ms }.validate().is_ok(),
                valid
            );
        }
        for value in [
            serde_json::json!({"kind":"stinger","duration_ms":500}),
            serde_json::json!({"kind":"fade","duration_ms":-1}),
            serde_json::json!({"kind":"fade","duration_ms":500,"queue":true}),
        ] {
            assert!(serde_json::from_value::<TransitionConfig>(value).is_err());
        }
    }
    #[test]
    fn unrelated_audio_cannot_acknowledge_video_failure() {
        let mut r = Recovery::default();
        r.pending.insert("main".into());
        r.pending.insert("audio".into());
        r.resolve("audio");
        assert!(r.required());
        assert!(r.pending.contains("main"));
        r.resolve("main");
        assert!(!r.required());
    }
    #[test]
    fn graph_rejects_dangling_duplicate_and_unbounded_geometry() {
        let mut g = Graph::default();
        g.validate().unwrap();
        g.scenes[0].layers[0].source_id = "missing".into();
        assert!(g.validate().is_err());
        let mut g = Graph::default();
        g.sources[1].id = "main".into();
        assert!(g.validate().is_err());
        let mut g = Graph::default();
        g.scenes[0].layers[0].layouts.horizontal.width = f32::NAN;
        assert!(g.validate().is_err());
    }
    #[test]
    fn portrait_transform_is_independent_and_ids_survive_roundtrip() {
        let mut g = Graph::default();
        g.scenes[0].layers[0].layouts.vertical.x = 40.;
        let g: Graph = serde_json::from_slice(&serde_json::to_vec(&g).unwrap()).unwrap();
        assert_eq!(g.scenes[0].layers[0].layouts.horizontal.x, 0.);
        assert_eq!(g.scenes[0].layers[0].id, "main-layer");
    }
    #[test]
    fn one_camera_resource_per_device_reused_by_layers() {
        let mut g = Graph::default();
        g.sources[0].spec = SourceKind::Camera {
            device_id: "physical-camera".into(),
        };
        g.sources[1].spec = g.sources[0].spec.clone();
        assert!(
            g.validate()
                .unwrap_err()
                .to_string()
                .starts_with("DEVICE_IN_USE")
        );
        g.sources.pop();
        g.scenes[0].layers[1].source_id = "main".into();
        g.validate().unwrap();
    }
}
