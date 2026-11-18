//! Reviewed, bounded installation through the existing owner commands.
//! A failed step leaves visible resources and a receipt; there is no rollback or replay.
use super::{
    Command, Production, Variant,
    overlays::{Definition, OverlayCommand},
};
use crate::scene::{Graph, Layer, Layouts, Scene, SourceKind, Transform, VisualSource};
use motive_show_control::{
    actions::{Action, Animation, WidgetEvent},
    deck::{ButtonTarget, Deck},
    model::Scalar,
    packs::{Capability, CreatorPack, InstallPlan, Orientation, PlanStep},
    runtime::{BusyPolicy, Config, FailurePolicy, Rule},
};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Instant,
};

const MANIFEST: &str = include_str!("../show-control/examples/packs/matchday.json");
const DECK: &str = include_str!("../show-control/examples/decks/matchday.json");
const PREFIX: &str = "MATCHDAY · ";

/// Local capability: never serializable, clonable or accepted over CLI/MCP.
pub struct LocalPackReview {
    pid: u32,
    revision: u64,
    fingerprint: String,
    created: Instant,
    summary: Value,
    pack: CreatorPack,
    plan: InstallPlan,
}
impl LocalPackReview {
    pub fn summary(&self) -> Value {
        self.summary.clone()
    }
}

#[derive(Debug, Default, Serialize)]
struct Bindings {
    scenes: BTreeMap<String, String>,
    sources: BTreeMap<String, String>,
    layers: BTreeMap<String, String>,
}
fn bound(map: &BTreeMap<String, String>, id: &str) -> anyhow::Result<String> {
    map.get(id)
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("PACK_BINDING_MISSING: {id}"))
}
fn digest(value: &impl Serialize) -> anyhow::Result<String> {
    Ok(format!("{:x}", Sha256::digest(serde_json::to_vec(value)?)))
}
fn available(native: &Value) -> BTreeSet<Capability> {
    let has = |id: &str| native["sources"][id]["available"] == true;
    let mut result = BTreeSet::new();
    if has("motive_visual") {
        result.insert(Capability::Shape);
        result.insert(Capability::LayerAnimation);
        if has("text_ft2_source") {
            result.insert(Capability::Text);
            result.insert(Capability::Widget);
        }
    }
    if has("fade_transition") {
        result.insert(Capability::SceneTransition);
    }
    result
}
fn transform(layout: &motive_show_control::packs::Layout) -> anyhow::Result<Transform> {
    let value: Transform = serde_json::from_value(serde_json::to_value(layout)?)?;
    value.validate()?;
    Ok(value)
}

/// Validation-only candidate; its allocated IDs are never used for real dispatch.
fn candidate(existing: &Graph, pack: &CreatorPack) -> anyhow::Result<(Graph, Bindings)> {
    anyhow::ensure!(pack.resources.is_empty(), "PACK_RESOURCES_UNSUPPORTED");
    anyhow::ensure!(
        !existing.scenes.iter().any(|s| s.name.starts_with(PREFIX))
            && !existing.sources.iter().any(|s| s.name.starts_with(PREFIX)),
        "PACK_ALREADY_PRESENT: inspect existing or partially installed MATCHDAY resources"
    );
    let mut graph = existing.clone();
    let mut bindings = Bindings::default();
    for source in &pack.overlays {
        let definition: Definition =
            serde_json::from_value(serde_json::to_value(&source.definition)?)?;
        definition.validate()?;
        let id = graph.id("source");
        bindings.sources.insert(source.id.clone(), id.clone());
        graph.sources.push(VisualSource {
            id,
            name: format!("{PREFIX}{}", source.name),
            spec: SourceKind::Overlay { color: 0x33e8b5 },
            overlay: Some(definition),
        });
    }
    for scene in &pack.scenes {
        let id = graph.id("scene");
        bindings.scenes.insert(scene.id.clone(), id.clone());
        let mut layers = Vec::new();
        for layer in &scene.layers {
            let id = graph.id("layer");
            bindings.layers.insert(layer.id.clone(), id.clone());
            layers.push(Layer {
                id,
                source_id: bound(&bindings.sources, &layer.overlay_id)?,
                layouts: Layouts {
                    horizontal: transform(&layer.horizontal)?,
                    vertical: transform(&layer.vertical)?,
                },
            });
        }
        graph.scenes.push(Scene {
            id,
            name: format!("{PREFIX}{}", scene.name),
            layers,
        });
    }
    graph.validate()?;
    Ok((graph, bindings))
}
fn animation(pack: &CreatorPack, bindings: &Bindings, name: &str) -> anyhow::Result<Action> {
    let a = pack
        .animations
        .iter()
        .find(|a| a.id == name)
        .ok_or_else(|| anyhow::anyhow!("PACK_ANIMATION_MISSING"))?;
    let animation: Animation = serde_json::from_value(json!({"kind":a.kind,"easing":a.easing,
        "duration_ms":a.duration_ms,"distance":a.distance,"scale_from":a.scale_from}))?;
    animation.validate()?;
    Ok(Action::Animate {
        scene_id: bound(&bindings.scenes, &a.scene_id)?,
        layer_id: bound(&bindings.layers, &a.layer_id)?,
        animation,
    })
}
fn live_configuration(pack: &CreatorPack, bindings: &Bindings) -> anyhow::Result<(Config, Deck)> {
    // This explicit manual subset deliberately contains no voice/network/sound actions.
    let trigger = |id: &str| -> anyhow::Result<Action> {
        Ok(Action::Widget {
            source_id: bound(&bindings.sources, id)?,
            event: WidgetEvent::Trigger,
        })
    };
    let Action::Animate {
        scene_id,
        layer_id,
        animation: goal_animation,
    } = animation(pack, bindings, "goal-enter")?
    else {
        anyhow::bail!("PACK_ANIMATION_MISSING");
    };
    let goal = vec![
        Action::TriggerAnimatedWidget {
            source_id: bound(&bindings.sources, "goal-celebration")?,
            scene_id,
            layer_id,
            animation: goal_animation,
        },
        Action::IncrementCounter {
            name: "goals".into(),
            amount: 1,
        },
    ];
    let rules = [
        ("deck-goal", goal.clone(), 10_000),
        ("deck-celebrate", goal, 10_000),
        ("deck-community", vec![trigger("community-alert")?], 3_000),
        (
            "lower-enter",
            vec![
                Action::ShowOverlay {
                    source_id: bound(&bindings.sources, "match-lower-third")?,
                },
                animation(pack, bindings, "lower-enter")?,
            ],
            0,
        ),
    ]
    .into_iter()
    .map(|(id, actions, cooldown_ms)| Rule {
        id: id.into(),
        enabled: true,
        event_kind: "manual.button_pressed".into(),
        priority: 5,
        conditions: vec![],
        actions,
        cooldown_ms,
        debounce_ms: 0,
        timeout_ms: 10_000,
        busy_policy: BusyPolicy::Reject,
        failure_policy: FailurePolicy::Stop,
    })
    .collect();
    let config = Config {
        schema_version: 1,
        rules,
        variables: BTreeMap::from([("goals".into(), Scalar::Int(0))]),
        queue_capacity: 16,
        rate_limit: 20,
        rate_window_ms: 1000,
        max_actions_per_event: 32,
    };
    let mut deck: Deck = serde_json::from_str(DECK)?;
    deck.name = "MATCHDAY Live Deck".into();
    for button in &mut deck.buttons {
        if button.id == "goal" {
            button.label = "Celebración de gol".into();
        }
        match &mut button.target {
            ButtonTarget::Overlay { source_ref, .. }
            | ButtonTarget::Countdown { source_ref, .. } => {
                *source_ref = bound(&bindings.sources, source_ref)?
            }
            ButtonTarget::Scene { scene_ref, .. } => {
                *scene_ref = bound(&bindings.scenes, scene_ref)?
            }
            _ => {}
        }
    }
    super::show_control::validate_bindings(config.clone(), &deck)?;
    Ok((config, deck))
}
fn unique_new(
    before: impl Iterator<Item = String>,
    after: impl Iterator<Item = String>,
) -> anyhow::Result<String> {
    let old: BTreeSet<_> = before.collect();
    let mut created = after.filter(|id| !old.contains(id));
    let id = created
        .next()
        .ok_or_else(|| anyhow::anyhow!("PACK_BINDING_MISSING"))?;
    anyhow::ensure!(created.next().is_none(), "PACK_BINDING_AMBIGUOUS");
    Ok(id)
}

impl Production {
    pub fn creator_packs_status(&self) -> Value {
        self.creator_packs.clone()
    }
    fn pack_admission(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            !self.shutdown_pending && !self.shutdown_requested,
            "SHUTDOWN_PENDING"
        );
        self.idle()?;
        anyhow::ensure!(
            !self.destination_credential_busy(),
            "CREDENTIAL_ENROLLMENT_BUSY"
        );
        anyhow::ensure!(
            self.show_control.is_none(),
            "PACK_DECK_EXISTS: preserve the existing Show Control configuration"
        );
        anyhow::ensure!(
            self.creator_packs["phase"] == "not_installed",
            "PACK_ALREADY_ATTEMPTED"
        );
        Ok(())
    }
    pub fn prepare_matchday_install(&mut self) -> anyhow::Result<LocalPackReview> {
        self.poll_health();
        self.pack_admission()?;
        let pack = CreatorPack::from_json(MANIFEST)?;
        let plan = pack.plan(&available(&self.engine.overlay_capabilities()))?;
        anyhow::ensure!(plan.unavailable.is_empty(), "PACK_CAPABILITY_UNAVAILABLE");
        let (proposed, bindings) = candidate(self.graph(), &pack)?;
        let mut value = serde_json::to_value(&proposed)?;
        self.overlay_native_graph(&proposed, &mut value)?;
        live_configuration(&pack, &bindings)?;
        let summary = json!({"pack_id":pack.id,"pack_version":pack.version,"pid":std::process::id(),
            "revision":self.revision,"manifest_sha256":format!("{:x}",Sha256::digest(MANIFEST.as_bytes())),
            "scenes":pack.scenes.len(),"sources":pack.overlays.len(),
            "layers":pack.scenes.iter().map(|s|s.layers.len()).sum::<usize>(),
            "steps":plan.steps.len(),"estimated_texture_bytes":plan.estimated_texture_bytes,
            "previous_scene":self.graph().active_scene,"atomic":false,"requires_idle":true,
            "limitations":["Conserva las fuentes existentes. Crear escenas cambia temporalmente el preview.",
                "Un fallo conserva los recursos creados; no hay rollback ni reintento automático.",
                "Incluye ambas orientaciones y un Live Deck manual. Sin sonido, voz ni descargas.",
                "No guarda el proyecto ni inicia salidas. Guarda proyecto y Show Control al finalizar."]});
        Ok(LocalPackReview {
            pid: std::process::id(),
            revision: self.revision,
            fingerprint: digest(self.graph())?,
            created: Instant::now(),
            summary,
            pack,
            plan,
        })
    }
    pub fn install_matchday_local(&mut self, review: LocalPackReview) -> anyhow::Result<Value> {
        self.poll_health();
        self.pack_admission()?;
        anyhow::ensure!(
            review.pid == std::process::id()
                && review.revision == self.revision
                && review.fingerprint == digest(self.graph())?
                && review.created.elapsed().as_secs() < 120,
            "PACK_REVIEW_STALE: review the current production again"
        );
        let previous_scene = self.graph().active_scene.clone();
        let initial_graph = self.graph().clone();
        let mut bindings = Bindings::default();
        let mut completed = 0;
        self.creator_packs =
            json!({"phase":"installing","pack_id":"matchday","review":review.summary});
        let result = (|| -> anyhow::Result<()> {
            for step in &review.plan.steps {
                self.install_pack_step(step, &mut bindings)?;
                completed += 1;
                self.creator_packs["steps_completed"] = json!(completed);
                self.creator_packs["bindings"] = serde_json::to_value(&bindings)?;
            }
            // Never arm any rules with a partial binding table.
            let (config, deck) = live_configuration(&review.pack, &bindings)?;
            self.configure_show_control(config, deck)?;
            Ok(())
        })();
        let restore = self.apply(
            Command::SelectScene {
                scene_id: previous_scene.clone(),
            },
            "Creator Pack",
        );
        self.creator_packs = json!({"phase":if result.is_ok(){"completed"}else{"partial"},
            "pack_id":"matchday","pack_version":review.pack.version,
            "steps_completed":completed,"steps_total":review.plan.steps.len(),"bindings":bindings,
            "error":result.err().map(|e|e.to_string()),"atomic":false,"replay_allowed":false,
            "retained_new_scene_ids":self.graph().scenes.iter().filter(|s|!initial_graph.scenes.iter().any(|old|old.id==s.id)).map(|s|&s.id).collect::<Vec<_>>(),
            "retained_new_source_ids":self.graph().sources.iter().filter(|s|!initial_graph.sources.iter().any(|old|old.id==s.id)).map(|s|&s.id).collect::<Vec<_>>(),
            "retained_new_layer_ids":self.graph().scenes.iter().flat_map(|s|&s.layers).filter(|l|!initial_graph.scenes.iter().flat_map(|s|&s.layers).any(|old|old.id==l.id)).map(|l|&l.id).collect::<Vec<_>>(),
            "previous_scene":previous_scene,"restore_accepted":restore["ok"] == true,
            "restore_error":if restore["ok"]==true {None}else{Some(restore["error"].to_string())},"project_saved":false,"show_control_saved":false,
            "presentation_verified":false});
        self.bump_external_revision();
        Ok(self.creator_packs_status())
    }
    fn install_pack_step(
        &mut self,
        step: &PlanStep,
        bindings: &mut Bindings,
    ) -> anyhow::Result<()> {
        let before = self.graph().clone();
        let command = match step {
            PlanStep::CreateScene { name, .. } => Command::CreateScene {
                name: format!("{PREFIX}{name}"),
            },
            PlanStep::CreateOverlay {
                scene_ref,
                name,
                definition,
                ..
            } => Command::Overlay(OverlayCommand::CreateOverlay {
                scene_id: bound(&bindings.scenes, scene_ref)?,
                name: format!("{PREFIX}{name}"),
                definition: serde_json::from_value(serde_json::to_value(definition)?)?,
            }),
            PlanStep::AddLayer {
                scene_ref,
                source_ref,
                ..
            } => Command::AddLayer {
                scene_id: bound(&bindings.scenes, scene_ref)?,
                source_id: bound(&bindings.sources, source_ref)?,
            },
            PlanStep::SetTransform {
                scene_ref,
                layer_ref,
                variant,
                transform: layout,
            } => Command::SetTransform {
                scene_id: bound(&bindings.scenes, scene_ref)?,
                layer_id: bound(&bindings.layers, layer_ref)?,
                variant: match variant {
                    Orientation::Horizontal => Variant::Horizontal,
                    Orientation::Vertical => Variant::Vertical,
                },
                transform: transform(layout)?,
            },
            PlanStep::ImportAssetAfterLocalAuthorization { .. } => {
                anyhow::bail!("PACK_RESOURCES_UNSUPPORTED")
            }
        };
        let response = self.apply(command, "Creator Pack");
        // Bind only successful replies. The final receipt also records graph differences
        // from before installation, including any resources retained by a failed step.
        anyhow::ensure!(
            response["ok"] == true,
            "PACK_STEP_REJECTED: {}",
            response["error"]
        );
        let after = self.graph();
        match step {
            PlanStep::CreateScene { scene_ref, .. } => {
                bindings.scenes.insert(
                    scene_ref.clone(),
                    unique_new(
                        before.scenes.iter().map(|s| s.id.clone()),
                        after.scenes.iter().map(|s| s.id.clone()),
                    )?,
                );
            }
            PlanStep::CreateOverlay {
                source_ref,
                first_layer_ref,
                ..
            } => {
                bindings.sources.insert(
                    source_ref.clone(),
                    unique_new(
                        before.sources.iter().map(|s| s.id.clone()),
                        after.sources.iter().map(|s| s.id.clone()),
                    )?,
                );
                bindings.layers.insert(
                    first_layer_ref.clone(),
                    unique_new(
                        before
                            .scenes
                            .iter()
                            .flat_map(|s| s.layers.iter().map(|l| l.id.clone())),
                        after
                            .scenes
                            .iter()
                            .flat_map(|s| s.layers.iter().map(|l| l.id.clone())),
                    )?,
                );
            }
            PlanStep::AddLayer { layer_ref, .. } => {
                bindings.layers.insert(
                    layer_ref.clone(),
                    unique_new(
                        before
                            .scenes
                            .iter()
                            .flat_map(|s| s.layers.iter().map(|l| l.id.clone())),
                        after
                            .scenes
                            .iter()
                            .flat_map(|s| s.layers.iter().map(|l| l.id.clone())),
                    )?,
                );
            }
            _ => {}
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn builtin_fits_both_layouts_preserving_existing_resources_and_manual_bindings() {
        let pack = CreatorPack::from_json(MANIFEST).unwrap();
        let old = Graph::default();
        let (new, bindings) = candidate(&old, &pack).unwrap();
        assert_eq!(
            (
                new.scenes.len(),
                new.sources.len(),
                new.scenes.iter().map(|s| s.layers.len()).sum::<usize>()
            ),
            (5, 14, 25)
        );
        for source in &old.sources {
            assert_eq!(
                serde_json::to_value(source).unwrap(),
                serde_json::to_value(new.sources.iter().find(|s| s.id == source.id).unwrap())
                    .unwrap()
            );
        }
        assert_eq!(
            serde_json::to_value(&old.scenes[0]).unwrap(),
            serde_json::to_value(&new.scenes[0]).unwrap()
        );
        let (config, deck) = live_configuration(&pack, &bindings).unwrap();
        assert!(
            config
                .rules
                .iter()
                .all(|r| r.event_kind == "manual.button_pressed")
        );
        assert!(
            config
                .rules
                .iter()
                .flat_map(|r| &r.actions)
                .any(|a| matches!(a, Action::Animate { .. }))
        );
        assert!(
            deck.buttons
                .iter()
                .filter(|b| matches!(b.target, ButtonTarget::Scene { .. }))
                .all(|b| b.sensitive)
        );
        assert!(candidate(&new, &pack).is_err());
    }
    #[test]
    fn goal_and_celebration_bind_one_atomic_entry_before_the_counter() {
        let pack = CreatorPack::from_json(MANIFEST).unwrap();
        let (_, bindings) = candidate(&Graph::default(), &pack).unwrap();
        let (config, _) = live_configuration(&pack, &bindings).unwrap();
        for id in ["deck-goal", "deck-celebrate"] {
            let rule = config.rules.iter().find(|r| r.id == id).unwrap();
            assert_eq!(rule.actions.len(), 2);
            assert!(matches!(&rule.actions[0], Action::TriggerAnimatedWidget {
                source_id, scene_id, layer_id, animation,
            } if source_id == &bindings.sources["goal-celebration"]
                && scene_id == &bindings.scenes["match-live"]
                && layer_id == &bindings.layers["live-goal"]
                && animation.duration_ms == 450));
            assert!(
                matches!(&rule.actions[1], Action::IncrementCounter { name, amount: 1 } if name == "goals")
            );
        }
    }
    #[test]
    fn graph_budget_and_missing_bindings_fail_before_dispatch() {
        let pack = CreatorPack::from_json(MANIFEST).unwrap();
        let mut graph = Graph::default();
        for n in 0..3 {
            graph.sources.push(VisualSource {
                id: format!("extra-{n}"),
                name: "Existing".into(),
                spec: SourceKind::Pattern,
                overlay: None,
            });
        }
        assert!(
            candidate(&graph, &pack)
                .unwrap_err()
                .to_string()
                .contains("GRAPH_LIMIT")
        );
        assert!(live_configuration(&pack, &Bindings::default()).is_err());
        assert!(available(&json!({})).is_empty());
        assert!(
            unique_new(
                ["a".into()].into_iter(),
                ["a".into(), "b".into(), "c".into()].into_iter()
            )
            .is_err()
        );
    }
}
