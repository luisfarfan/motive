//! Owner-thread integration and a single bounded import worker; no media clock.
use super::{
    assets::{Asset, AssetCatalog, AssetKind},
    *,
};
use crate::{
    core::{Production, Variant, command_error, data_dir},
    scene::{Graph, Layer, Layouts, SourceKind, VisualSource, valid_name},
};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    path::PathBuf,
    sync::mpsc,
    thread,
};

struct AnimationTarget {
    generation: u64,
    variant: Variant,
    scene_id: String,
    layer_id: String,
    source_id: String,
    visible: bool,
}
#[derive(Default)]
struct AnimationTracker {
    generation: u64,
    pending: BTreeMap<u64, AnimationTarget>,
}
impl AnimationTracker {
    fn record(
        &mut self,
        id: u64,
        variant: Variant,
        scene_id: String,
        layer: &Layer,
        kind: AnimationKind,
    ) {
        self.pending.insert(
            id,
            AnimationTarget {
                generation: self.generation,
                variant,
                scene_id,
                layer_id: layer.id.clone(),
                source_id: layer.source_id.clone(),
                visible: matches!(
                    kind,
                    AnimationKind::FadeIn | AnimationKind::SlideIn | AnimationKind::ScaleIn
                ),
            },
        );
    }
    fn graph_replaced(&mut self) {
        self.generation = self
            .generation
            .checked_add(1)
            .expect("graph generation exhausted");
    }
    // A native terminal receipt is retained until this effect has been applied
    // and its exact ID acknowledged. Repeated delivery is idempotent, including
    // an acknowledgment failure. A prior graph's receipt never edits its successor.
    fn reconcile(&self, id: u64, job: &Value, graph: &mut Graph) -> anyhow::Result<bool> {
        let target = self
            .pending
            .get(&id)
            .ok_or_else(|| anyhow::anyhow!("ANIMATION_COMPLETION_UNKNOWN"))?;
        anyhow::ensure!(
            job["scene_id"] == target.scene_id
                && job["layer_id"] == target.layer_id
                && job["target_visible"] == target.visible
                && job["pending_ack"] == true
                && matches!(
                    job["phase"].as_str(),
                    Some("completed" | "cancelled" | "failed")
                ),
            "ANIMATION_COMPLETION_MISMATCH"
        );
        if target.generation != self.generation || job["phase"] != "completed" {
            return Ok(false);
        }
        let layer = graph
            .scenes
            .iter_mut()
            .find(|s| s.id == target.scene_id)
            .and_then(|s| {
                s.layers
                    .iter_mut()
                    .find(|l| l.id == target.layer_id && l.source_id == target.source_id)
            })
            .ok_or_else(|| anyhow::anyhow!("ANIMATION_COMPLETION_LAYER_CHANGED"))?;
        let visible = &mut layer.layouts.get_mut(target.variant).visible;
        let changed = *visible != target.visible;
        *visible = target.visible;
        Ok(changed)
    }
}

pub struct State {
    pub assets: AssetCatalog,
    pending: Option<(
        mpsc::Receiver<anyhow::Result<Asset>>,
        thread::JoinHandle<()>,
    )>,
    next_import: u64,
    import: Value,
    observed: Value,
    resolved: RefCell<BTreeMap<String, (PathBuf, Asset)>>,
    animations: AnimationTracker,
    completion_error: Option<String>,
}
impl State {
    pub fn new(root: PathBuf) -> anyhow::Result<Self> {
        Ok(Self {
            assets: AssetCatalog::new(root)?,
            pending: None,
            next_import: 1,
            import: Value::Null,
            observed: Value::Null,
            animations: AnimationTracker::default(),
            completion_error: None,
            resolved: RefCell::new(BTreeMap::new()),
        })
    }
    pub fn busy(&self) -> bool {
        self.pending.is_some()
    }
    pub fn invalidate(&self) {
        self.resolved.borrow_mut().clear();
    }
    pub(in crate::core) fn graph_replaced(&mut self) {
        self.animations.graph_replaced();
    }
    pub fn resolve(&self, id: &str) -> anyhow::Result<(PathBuf, Asset)> {
        if let Some(entry) = self.resolved.borrow().get(id) {
            return Ok(entry.clone());
        }
        let asset = self.assets.get(id)?;
        let path = self.assets.resolve(id)?;
        self.resolved
            .borrow_mut()
            .insert(id.into(), (path.clone(), asset.clone()));
        Ok((path, asset))
    }
    fn start_import(&mut self, name: String) -> anyhow::Result<()> {
        anyhow::ensure!(!self.busy(), "ASSET_IMPORT_BUSY");
        // Validate the narrow inbox capability before enqueueing expensive work.
        anyhow::ensure!(
            !name.is_empty()
                && name.len() <= 120
                && !name.starts_with('.')
                && name
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_')),
            "INVALID_IMPORT_NAME"
        );
        let id = self.next_import;
        self.next_import += 1;
        let (tx, rx) = mpsc::channel();
        let handle = thread::spawn(move || {
            let result = AssetCatalog::new(data_dir()).and_then(|c| c.import(&name));
            let _ = tx.send(result);
        });
        self.pending = Some((rx, handle));
        self.import = json!({"operation_id":id,"phase":"running"});
        Ok(())
    }
    fn poll(&mut self) -> bool {
        let Some((rx, _)) = &self.pending else {
            return false;
        };
        let result = match rx.try_recv() {
            Ok(r) => r,
            Err(mpsc::TryRecvError::Empty) => return false,
            Err(_) => Err(anyhow::anyhow!("ASSET_IMPORT_FAILED")),
        };
        if let Some((_, handle)) = self.pending.take() {
            let _ = handle.join();
        }
        match result {
            Ok(asset) => {
                self.import["phase"] = json!("completed");
                self.import["asset"] = json!(asset);
            }
            Err(e) => {
                self.import["phase"] = json!("failed");
                self.import["error"] = command_error(e)["error"].clone();
            }
        }
        true
    }
}
impl Drop for State {
    fn drop(&mut self) {
        if let Some((_, handle)) = self.pending.take() {
            let _ = handle.join();
        }
    }
}
impl Production {
    pub(in crate::core) fn poll_overlays(&mut self) {
        if self.overlays.poll() {
            self.revision += 1;
        }
        self.engine.poll_overlays();
        let runtime = self.engine.overlay_state();
        if let Some(jobs) = runtime["animations"]["jobs"].as_array() {
            for job in jobs {
                if job["pending_ack"] != true {
                    continue;
                }
                let Some(id) = job["operation_id"].as_u64() else {
                    continue;
                };
                let outcome = self.overlays.animations.reconcile(
                    id,
                    job,
                    self.project.graph.as_mut().unwrap(),
                );
                match outcome {
                    Ok(changed) => {
                        if changed {
                            self.update_legacy();
                        }
                        match self.engine.ack_overlay_animation(id) {
                            Ok(()) => {
                                self.overlays.animations.pending.remove(&id);
                                self.overlays.completion_error = None;
                            }
                            Err(e) => self.overlays.completion_error = Some(e.to_string()),
                        }
                    }
                    Err(e) => self.overlays.completion_error = Some(e.to_string()),
                }
            }
        }
        let lifecycle = json!({"animations":runtime["animations"]["jobs"].as_array().map(|a|a.iter().map(|v|json!([v["operation_id"],v["phase"]])).collect::<Vec<_>>()),"sources":runtime["sources"].as_array().map(|a|a.iter().map(|v|json!([v["id"],v["phase"],v["visible"]])).collect::<Vec<_>>())});
        if lifecycle != self.overlays.observed {
            self.overlays.observed = lifecycle;
            self.revision += 1;
        }
    }
    pub fn overlay_status(&self) -> Value {
        json!({"definition_version":1,"runtime":self.engine.overlay_state(),"import":self.overlays.import,"completion_error":self.overlays.completion_error,"definitions":self.graph().sources.iter().filter(|s|s.overlay.is_some()).collect::<Vec<_>>()})
    }
    pub(in crate::core) fn overlay_native_graph(
        &self,
        graph: &Graph,
        value: &mut Value,
    ) -> anyhow::Result<()> {
        anyhow::ensure!(!self.overlays.busy(), "ASSET_IMPORT_BUSY");
        let mut estimate = 0u64;
        let mut videos = 0;
        for source in &graph.sources {
            if let Some(definition) = &source.overlay {
                estimate += match definition {
                    Definition::Text { .. } => 8 * 1024 * 1024,
                    Definition::Widget { .. } => 16 * 1024 * 1024,
                    _ => 0,
                };
                videos += usize::from(matches!(definition, Definition::Video { .. }));
                estimate += match definition {
                    Definition::Text { width, height, .. }
                    | Definition::Shape { width, height, .. } => {
                        (*width as u64) * (*height as u64) * 8
                    }
                    Definition::Widget { widget } => widget.width as u64 * widget.height as u64 * 8,
                    _ => 0,
                };
                let v = value["sources"]
                    .as_array_mut()
                    .unwrap()
                    .iter_mut()
                    .find(|v| v["id"] == source.id)
                    .unwrap();
                if let Some(id) = definition.asset_id() {
                    let (path, asset) = self.overlays.resolve(id)?;
                    anyhow::ensure!(
                        match definition {
                            Definition::Image { .. } => asset.kind == AssetKind::Image,
                            Definition::Video { .. } => asset.kind == AssetKind::Video,
                            _ => false,
                        },
                        "ASSET_TYPE_MISMATCH"
                    );
                    estimate += asset.width as u64 * asset.height as u64 * 8;
                    v["asset_path"] = json!(path);
                    v["asset_width"] = json!(asset.width);
                    v["asset_height"] = json!(asset.height);
                }
            }
        }
        anyhow::ensure!(
            estimate <= 256 * 1024 * 1024 && videos <= 4,
            "OVERLAY_MEMORY_LIMIT"
        );
        Ok(())
    }
    fn add_overlay_definition(
        graph: &mut Graph,
        scene_id: &str,
        name: String,
        definition: Definition,
        layouts: Layouts,
    ) -> anyhow::Result<String> {
        anyhow::ensure!(valid_name(&name), "INVALID_NAME");
        definition.validate()?;
        graph.scene(scene_id)?;
        let id = graph.id("source");
        graph.sources.push(VisualSource {
            id: id.clone(),
            name,
            spec: SourceKind::Overlay { color: 0x33e8b5 },
            overlay: Some(definition),
        });
        let layer = graph.id("layer");
        graph.scene_mut(scene_id)?.layers.push(Layer {
            id: layer,
            source_id: id.clone(),
            layouts,
        });
        Ok(id)
    }
    pub(in crate::core) fn apply_overlay(
        &mut self,
        command: OverlayCommand,
        origin: &str,
    ) -> Value {
        let query = command.query();
        let label = serde_json::to_value(&command).unwrap()["op"]
            .as_str()
            .unwrap()
            .to_owned();
        let result = (|| -> anyhow::Result<Value> {
            if !query {
                anyhow::ensure!(!self.shutdown_pending, "SHUTDOWN_PENDING");
            }
            match command {
                OverlayCommand::OverlayCapabilities => Ok(
                    json!({"definitions":protocol::definition_schema(),"presets":presets::catalogue(),"limits":{"sources":16,"layers":32,"scenes":8,"active_animations":8,"image_dimensions":2048,"managed_bytes":536870912,"estimated_visual_bytes":268435456,"max_video_sources":4},"native":self.engine.overlay_capabilities(),"assets":{"import":"explicit file copy into var/imports, then basename only","async":true,"formats":["png","jpeg","webp","mp4","mov","webm"],"canonical":["png","mkv"]},"browser":{"available":false,"code":"BROWSER_ISOLATION_UNAVAILABLE"},"text_layout":"natural_block_explicit_newlines_contain","media_audio":"disabled_mixers_0_monitoring_off","project_schema":{"legacy":3,"overlays":4},"animation_easing":{"fade":["linear"],"slide_scale":["linear","ease_in","ease_out","ease_in_out"]}}),
                ),
                OverlayCommand::OverlayState => Ok(self.overlay_status()),
                OverlayCommand::OverlayPresets => Ok(presets::catalogue()),
                OverlayCommand::ListAssets => {
                    anyhow::ensure!(!self.overlays.busy(), "ASSET_IMPORT_BUSY");
                    Ok(json!({"assets":self.overlays.assets.list()?}))
                }
                OverlayCommand::ImportAsset { file_name } => {
                    self.idle()?;
                    self.overlays.start_import(file_name)?;
                    Ok(json!({"import":self.overlays.import}))
                }
                OverlayCommand::RemoveAsset { asset_id } => {
                    self.idle()?;
                    let refs: BTreeSet<String> = self
                        .graph()
                        .sources
                        .iter()
                        .filter_map(|s| s.overlay.as_ref()?.asset_id().map(str::to_owned))
                        .collect();
                    self.overlays.assets.remove(&asset_id, &refs)?;
                    self.overlays.invalidate();
                    Ok(Value::Null)
                }
                OverlayCommand::CreateOverlay {
                    scene_id,
                    name,
                    definition,
                } => {
                    self.idle()?;
                    let mut graph = self.graph().clone();
                    let id = Self::add_overlay_definition(
                        &mut graph,
                        &scene_id,
                        name,
                        definition,
                        Layouts::secondary(),
                    )?;
                    self.sync(graph, self.bindings.clone(), "")?;
                    Ok(json!({"source_id":id}))
                }
                OverlayCommand::UpdateOverlay {
                    source_id,
                    definition,
                } => {
                    self.scene_quiescent()?;
                    definition.validate()?;
                    let source = self
                        .graph()
                        .sources
                        .iter()
                        .find(|s| s.id == source_id)
                        .ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE"))?;
                    let previous = source
                        .overlay
                        .as_ref()
                        .ok_or_else(|| anyhow::anyhow!("NOT_AN_OVERLAY"))?;
                    anyhow::ensure!(
                        previous.compatible_update(&definition),
                        "OVERLAY_RESOURCE_IMMUTABLE: create another source for a different kind or asset"
                    );
                    if matches!(definition, Definition::Video { .. }) {
                        self.idle()?;
                    }
                    let mut proposed = self.graph().clone();
                    proposed
                        .sources
                        .iter_mut()
                        .find(|s| s.id == source_id)
                        .unwrap()
                        .overlay = Some(definition.clone());
                    self.overlay_native_graph(&proposed, &mut serde_json::to_value(&proposed)?)?;
                    self.engine.update_overlay(&source_id, &definition)?;
                    self.project
                        .graph
                        .as_mut()
                        .unwrap()
                        .sources
                        .iter_mut()
                        .find(|s| s.id == source_id)
                        .unwrap()
                        .overlay = Some(definition);
                    Ok(Value::Null)
                }
                OverlayCommand::OverlayEvent { source_id, event } => {
                    self.engine.overlay_event(&source_id, event.native())?;
                    Ok(Value::Null)
                }
                OverlayCommand::AnimateOverlay {
                    scene_id,
                    layer_id,
                    animation,
                } => {
                    anyhow::ensure!(!self.engine.scene_state().busy(), "TRANSITION_BUSY");
                    animation.validate()?;
                    anyhow::ensure!(
                        scene_id == self.graph().active_scene,
                        "ANIMATION_SCENE_NOT_ACTIVE"
                    );
                    let layer = self
                        .graph()
                        .scene(&scene_id)?
                        .layers
                        .iter()
                        .find(|l| l.id == layer_id)
                        .ok_or_else(|| anyhow::anyhow!("LAYER_UNAVAILABLE"))?;
                    anyhow::ensure!(
                        self.graph()
                            .sources
                            .iter()
                            .any(|s| s.id == layer.source_id && s.overlay.is_some()),
                        "NOT_AN_OVERLAY"
                    );
                    let layer = layer.clone();
                    let operation_id = self
                        .engine
                        .animate_overlay(&scene_id, &layer_id, &animation)?;
                    self.overlays.animations.record(
                        operation_id,
                        self.project.variant,
                        scene_id,
                        &layer,
                        animation.kind,
                    );
                    Ok(json!({"operation_id":operation_id}))
                }
                OverlayCommand::CancelOverlayAnimation { operation_id } => {
                    self.engine.cancel_overlay_animation(operation_id)?;
                    Ok(Value::Null)
                }
                OverlayCommand::InstantiateOverlayPreset {
                    scene_id,
                    preset,
                    parameters,
                } => {
                    self.idle()?;
                    let mut graph = self.graph().clone();
                    let mut ids = vec![];
                    for (name, definition, layouts) in presets::instantiate(preset, parameters)? {
                        ids.push(Self::add_overlay_definition(
                            &mut graph, &scene_id, name, definition, layouts,
                        )?);
                    }
                    self.sync(graph, self.bindings.clone(), "")?;
                    Ok(json!({"preset_version":1,"source_ids":ids}))
                }
            }
        })();
        match result {
            Ok(result) => {
                if !query {
                    self.poll_health();
                    self.revision += 1;
                    self.last_action = format!("{origin} · {label} · revisión {}", self.revision);
                }
                let mut value = json!({"ok":true,"pid":std::process::id(),"revision":self.revision,"result":result});
                if !query {
                    value["state"] = self.status();
                }
                value
            }
            Err(e) => {
                let mut value = command_error(e);
                value["revision"] = json!(self.revision);
                value["overlays"] = self.overlay_status();
                value
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn receipt(id: u64, layer: &Layer, phase: &str) -> Value {
        json!({"operation_id":id,"scene_id":"scene-1","layer_id":layer.id,
            "phase":phase,"target_visible":false,"pending_ack":true})
    }

    #[test]
    fn completion_uses_accepted_variant_and_retries_idempotently_until_ack() {
        let mut graph = Graph::default();
        let layer = graph.scenes[0].layers[0].clone();
        let mut tracker = AnimationTracker::default();
        tracker.record(
            1,
            Variant::Horizontal,
            "scene-1".into(),
            &layer,
            AnimationKind::SlideOut,
        );
        let job = receipt(1, &layer, "completed");
        assert!(tracker.reconcile(1, &job, &mut graph).unwrap());
        assert!(!graph.scenes[0].layers[0].layouts.horizontal.visible);
        assert!(graph.scenes[0].layers[0].layouts.vertical.visible);
        // A failed native ack must leave the receipt safe to deliver again.
        assert!(!tracker.reconcile(1, &job, &mut graph).unwrap());
        assert!(tracker.pending.contains_key(&1));
        tracker.pending.remove(&1); // successful native acknowledgment
        assert!(tracker.reconcile(1, &job, &mut graph).is_err());
    }

    #[test]
    fn stale_generation_and_cancelled_or_failed_receipts_never_edit_new_document() {
        for phase in ["completed", "cancelled", "failed"] {
            let mut graph = Graph::default();
            let layer = graph.scenes[0].layers[0].clone();
            let mut tracker = AnimationTracker::default();
            tracker.record(
                1,
                Variant::Horizontal,
                "scene-1".into(),
                &layer,
                AnimationKind::FadeOut,
            );
            if phase == "completed" {
                tracker.graph_replaced();
            }
            assert!(
                !tracker
                    .reconcile(1, &receipt(1, &layer, phase), &mut graph)
                    .unwrap()
            );
            assert!(graph.scenes[0].layers[0].layouts.horizontal.visible);
        }
    }

    #[test]
    fn completion_requires_exact_layer_source_and_terminal_receipt() {
        let mut graph = Graph::default();
        let layer = graph.scenes[0].layers[0].clone();
        let mut tracker = AnimationTracker::default();
        tracker.record(
            1,
            Variant::Horizontal,
            "scene-1".into(),
            &layer,
            AnimationKind::ScaleOut,
        );
        assert!(
            tracker
                .reconcile(1, &receipt(1, &layer, "running"), &mut graph)
                .is_err()
        );
        let mut job = receipt(1, &layer, "completed");
        job["layer_id"] = json!("other-layer");
        assert!(tracker.reconcile(1, &job, &mut graph).is_err());
        graph.scenes[0].layers[0].source_id = "replacement".into();
        assert!(
            tracker
                .reconcile(1, &receipt(1, &layer, "completed"), &mut graph)
                .is_err()
        );
        assert!(graph.scenes[0].layers[0].layouts.horizontal.visible);
    }

    #[test]
    fn multiple_receipts_apply_out_of_order_without_losing_independent_layers() {
        let mut graph = Graph::default();
        let layers = graph.scenes[0].layers.clone();
        let mut tracker = AnimationTracker::default();
        for (n, layer) in layers.iter().enumerate() {
            tracker.record(
                n as u64 + 1,
                Variant::Horizontal,
                "scene-1".into(),
                layer,
                AnimationKind::FadeOut,
            );
        }
        for (n, layer) in layers.iter().enumerate().rev() {
            let id = n as u64 + 1;
            tracker
                .reconcile(id, &receipt(id, layer, "completed"), &mut graph)
                .unwrap();
            tracker.pending.remove(&id);
        }
        assert!(tracker.pending.is_empty());
        assert!(
            graph.scenes[0]
                .layers
                .iter()
                .all(|l| !l.layouts.horizontal.visible)
        );
    }
}
