//! Strict test owner and receipt verifier. It never calls Production or executes rules.
use crate::{Error, check, digest, label, model::*, planner::*};
use motive_show_control::packs::{Layout, Orientation, PlanStep, VisualDefinition};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum StepResult {
    Asset { id: ResourceId },
    Overlay { source: SourceId, layer: LayerId },
    Layer { id: LayerId },
    Transform,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub instance_id: String,
    pub session: String,
    pub step: usize,
    pub operation_sha256: String,
    pub before: u64,
    pub after: u64,
    pub result: StepResult,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Installing,
    InstalledInModel,
    Partial,
    NeedsReconciliation,
    RemovedInModel,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Installation {
    // Process-local execution capability. Persisted journals are evidence only;
    // deserialization must never recreate authority to mutate an owner.
    #[serde(skip)]
    owner_nonce: Option<u64>,
    pub plan: InstancePlan,
    pub plan_sha256: String,
    pub phase: Phase,
    pub bindings: Bindings,
    pub receipts: Vec<Receipt>,
    pub pending_step: Option<usize>,
    pub last_revision: u64,
    pub last_snapshot_sha256: String,
    pub error: Option<String>,
}
impl Installation {
    fn new(plan: InstancePlan) -> Result<Self, Error> {
        Ok(Self {
            owner_nonce: None,
            plan_sha256: digest(&plan)?,
            last_revision: plan.revision,
            last_snapshot_sha256: plan.snapshot_sha256.clone(),
            bindings: plan.initial_bindings.clone(),
            plan,
            phase: Phase::Installing,
            receipts: vec![],
            pending_step: None,
            error: None,
        })
    }
    pub fn begin_step(&mut self, current: &Snapshot) -> Result<usize, Error> {
        check(
            self.phase == Phase::Installing && self.pending_step.is_none(),
            "RECONCILIATION_REQUIRED",
            "Installation is not dispatchable; never replay partial work",
        )?;
        check(
            self.plan_sha256 == digest(&self.plan)?,
            "PLAN_CHANGED",
            "Plan changed after local review",
        )?;
        if current.busy
            || current.session != self.plan.session
            || current.revision != self.last_revision
            || digest(current)? != self.last_snapshot_sha256
        {
            self.uncertain("REVIEW_STALE");
            return Err(Error::new(
                "REVIEW_STALE",
                "Owner revision/session/graph changed",
            ));
        }
        let i = self.receipts.len();
        check(
            i < self.plan.steps.len(),
            "INSTALL_COMPLETE",
            "No further operation",
        )?;
        self.pending_step = Some(i); // Persist this intent before owner dispatch in the real adapter.
        Ok(i)
    }
    pub fn accept(
        &mut self,
        receipt: Receipt,
        before: &Snapshot,
        after: &Snapshot,
    ) -> Result<(), Error> {
        let result = self.verify(&receipt, before, after);
        if let Err(e) = result {
            self.phase = Phase::NeedsReconciliation;
            self.error = Some(e.code.clone());
            return Err(e);
        }
        update_bindings(
            &mut self.bindings,
            &self.plan.steps[receipt.step],
            &receipt.result,
        )?;
        self.pending_step = None;
        self.last_revision = receipt.after;
        self.last_snapshot_sha256 = digest(after)?;
        self.receipts.push(receipt);
        if self.receipts.len() == self.plan.steps.len() {
            self.phase = Phase::InstalledInModel;
        }
        Ok(())
    }
    fn verify(&self, receipt: &Receipt, before: &Snapshot, after: &Snapshot) -> Result<(), Error> {
        check(
            self.phase == Phase::Installing
                && self.pending_step == Some(self.receipts.len())
                && receipt.step == self.receipts.len(),
            "RECEIPT_ORDER",
            "Receipt does not acknowledge the pending operation",
        )?;
        check(
            receipt.instance_id == self.plan.instance_id
                && receipt.session == self.plan.session
                && before.session == receipt.session
                && after.session == receipt.session,
            "RECEIPT_IDENTITY",
            "Receipt owner/instance mismatch",
        )?;
        check(
            before.revision == self.last_revision
                && receipt.before == before.revision
                && receipt.after == after.revision
                && receipt.after
                    == receipt
                        .before
                        .checked_add(1)
                        .ok_or_else(|| Error::new("REVISION_OVERFLOW", "Revision exhausted"))?,
            "RECEIPT_REVISION",
            "Exactly one modeled owned revision required",
        )?;
        check(
            receipt.operation_sha256 == digest(&self.plan.steps[receipt.step])?
                && self.plan_sha256 == digest(&self.plan)?,
            "RECEIPT_OPERATION",
            "Receipt operation fingerprint mismatch",
        )?;
        check(
            digest(before)? == self.last_snapshot_sha256,
            "RECEIPT_GRAPH",
            "Pre-operation snapshot changed",
        )?;
        let expected = apply_model_step(
            before,
            &self.plan,
            &self.bindings,
            receipt.step,
            &receipt.result,
        )?;
        check(
            &expected == after,
            "RECEIPT_GRAPH",
            "Owner result differs from exact expected mutation; reconcile",
        )
    }
    pub fn uncertain(&mut self, code: &str) {
        self.phase = Phase::NeedsReconciliation;
        self.error = Some(code.into());
    }
    pub fn rejected(&mut self, code: &str) {
        self.phase = Phase::Partial;
        self.pending_step = None;
        self.error = Some(code.into());
    }
    pub fn bound_rules(&self) -> Result<motive_show_control::runtime::Config, Error> {
        check(
            self.phase == Phase::InstalledInModel,
            "INSTALL_INCOMPLETE",
            "Rules require complete verified bindings",
        )?;
        let mut rules = self.plan.rules.clone();
        let sources = self
            .bindings
            .sources
            .iter()
            .map(|(k, v)| (k.clone(), v.0.clone()))
            .collect();
        let layers = self
            .bindings
            .layers
            .iter()
            .map(|(k, v)| (k.clone(), v.0.clone()))
            .collect();
        let scenes = self
            .bindings
            .scenes
            .iter()
            .map(|(k, v)| (k.clone(), v.0.clone()))
            .collect();
        for rule in &mut rules.rules {
            rule.enabled = false;
            for action in &mut rule.actions {
                remap_action(action, &sources, &layers, &scenes)?;
            }
        }
        Ok(rules)
    }
}
fn bound<T: Clone>(map: &BTreeMap<String, T>, key: &str) -> Result<T, Error> {
    map.get(key)
        .cloned()
        .ok_or_else(|| Error::new("BINDING_MISSING", "A required typed receipt is absent"))
}
fn update_bindings(
    bindings: &mut Bindings,
    step: &PlanStep,
    result: &StepResult,
) -> Result<(), Error> {
    match (step, result) {
        (
            PlanStep::ImportAssetAfterLocalAuthorization { resource_ref, .. },
            StepResult::Asset { id },
        ) => {
            check(
                !bindings.resources.contains_key(resource_ref),
                "ID_CONFLICT",
                "Resource already bound",
            )?;
            bindings.resources.insert(resource_ref.clone(), id.clone());
        }
        (
            PlanStep::CreateOverlay {
                source_ref,
                first_layer_ref,
                ..
            },
            StepResult::Overlay { source, layer },
        ) => {
            check(
                !bindings.sources.contains_key(source_ref)
                    && !bindings.layers.contains_key(first_layer_ref),
                "ID_CONFLICT",
                "Identity already bound",
            )?;
            bindings.sources.insert(source_ref.clone(), source.clone());
            bindings
                .layers
                .insert(first_layer_ref.clone(), layer.clone());
        }
        (PlanStep::AddLayer { layer_ref, .. }, StepResult::Layer { id }) => {
            check(
                !bindings.layers.contains_key(layer_ref),
                "ID_CONFLICT",
                "Layer already bound",
            )?;
            bindings.layers.insert(layer_ref.clone(), id.clone());
        }
        (PlanStep::SetTransform { .. }, StepResult::Transform) => (),
        _ => {
            return Err(Error::new(
                "RECEIPT_TYPE",
                "Unexpected receipt type for operation",
            ));
        }
    }
    Ok(())
}
fn initial_layout() -> Layout {
    Layout {
        x: 0.,
        y: 0.,
        width: 1.,
        height: 1.,
        visible: false,
        order: 0,
    }
}
pub fn apply_model_step(
    before: &Snapshot,
    plan: &InstancePlan,
    bindings: &Bindings,
    index: usize,
    result: &StepResult,
) -> Result<Snapshot, Error> {
    before.validate()?;
    check(!before.busy, "OWNER_BUSY", "Owner became busy")?;
    let step = plan
        .steps
        .get(index)
        .ok_or_else(|| Error::new("STEP", "Unknown operation"))?;
    let mut out = before.clone();
    let tag = Some(plan.instance_id.clone());
    let make_layer = |id: LayerId, scene: SceneId, source: SourceId| -> Result<Layer, Error> {
        label(&id.0)?;
        check(
            !before.layers.contains_key(&id) && before.scenes.contains(&scene),
            "ID_CONFLICT",
            "Layer already exists or scene disappeared",
        )?;
        Ok(Layer {
            id,
            source,
            scene,
            horizontal: initial_layout(),
            vertical: initial_layout(),
            installation: tag.clone(),
        })
    };
    match (step, result) {
        (
            PlanStep::ImportAssetAfterLocalAuthorization { resource_ref, .. },
            StepResult::Asset { id },
        ) => {
            resource_id(&id.0)?;
            check(
                !out.assets.contains_key(id),
                "ID_CONFLICT",
                "Import must return a new asset or be planned as reuse",
            )?;
            let descriptor = plan
                .resources
                .get(resource_ref)
                .ok_or_else(|| {
                    Error::new("RESOURCE_MISSING", "Resource outside reviewed inventory")
                })?
                .clone();
            out.assets.insert(
                id.clone(),
                Asset {
                    id: id.clone(),
                    descriptor,
                    license: plan.license.clone(),
                    installation: tag,
                },
            );
        }
        (
            PlanStep::CreateOverlay {
                scene_ref,
                source_ref,
                definition,
                ..
            },
            StepResult::Overlay { source, layer },
        ) => {
            label(&source.0)?;
            check(
                !out.sources.contains_key(source),
                "ID_CONFLICT",
                "Source already exists",
            )?;
            let mut definition = definition.clone();
            if let VisualDefinition::Image { resource_id, .. }
            | VisualDefinition::Video { resource_id, .. } = &mut definition
            {
                *resource_id = bound(&bindings.resources, resource_id)?.0;
            }
            let l = make_layer(
                layer.clone(),
                bound(&bindings.scenes, scene_ref)?,
                source.clone(),
            )?;
            let texture = *plan
                .source_texture_bytes
                .get(source_ref)
                .ok_or_else(|| Error::new("BUDGET", "Missing source reservation"))?;
            out.sources.insert(
                source.clone(),
                Source {
                    id: source.clone(),
                    video: matches!(definition, VisualDefinition::Video { .. }),
                    definition: Some(definition),
                    texture_bytes: texture,
                    installation: tag,
                },
            );
            out.layers.insert(layer.clone(), l);
        }
        (
            PlanStep::AddLayer {
                scene_ref,
                source_ref,
                ..
            },
            StepResult::Layer { id },
        ) => {
            let source = bound(&bindings.sources, source_ref)?;
            check(
                out.sources.contains_key(&source),
                "SOURCE_MISSING",
                "Shared source disappeared",
            )?;
            out.layers.insert(
                id.clone(),
                make_layer(id.clone(), bound(&bindings.scenes, scene_ref)?, source)?,
            );
        }
        (
            PlanStep::SetTransform {
                scene_ref,
                layer_ref,
                variant,
                transform,
            },
            StepResult::Transform,
        ) => {
            transform.validate()?;
            let l = out
                .layers
                .get_mut(&bound(&bindings.layers, layer_ref)?)
                .ok_or_else(|| Error::new("LAYER_MISSING", "Layer disappeared"))?;
            check(
                l.scene == bound(&bindings.scenes, scene_ref)? && l.installation == tag,
                "LAYER_OWNERSHIP",
                "Layer belongs to another installation/scene",
            )?;
            match variant {
                Orientation::Horizontal => l.horizontal = transform.clone(),
                Orientation::Vertical => l.vertical = transform.clone(),
            }
        }
        _ => {
            return Err(Error::new(
                "RECEIPT_TYPE",
                "Unexpected receipt; CreateScene is forbidden here",
            ));
        }
    }
    out.revision = out
        .revision
        .checked_add(1)
        .ok_or_else(|| Error::new("REVISION_OVERFLOW", "Revision exhausted"))?;
    out.validate()?;
    Ok(out)
}

/// Nonserializable, one-use capability; produced only by this *offline* owner.
pub struct LocalModelReview {
    plan: InstancePlan,
    owner_nonce: u64,
}
pub struct StrictOwnerModel {
    pub snapshot: Snapshot,
    nonce: u64,
    sequence: u64,
}
static OWNERS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
impl StrictOwnerModel {
    pub fn new(snapshot: Snapshot) -> Result<Self, Error> {
        snapshot.validate()?;
        Ok(Self {
            snapshot,
            nonce: OWNERS.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
            sequence: 0,
        })
    }
    pub fn review(&self, request: InsertRequest) -> Result<LocalModelReview, Error> {
        Ok(LocalModelReview {
            plan: prepare(request, &self.snapshot)?,
            owner_nonce: self.nonce,
        })
    }
    pub fn begin(&self, review: LocalModelReview) -> Result<Installation, Error> {
        check(
            review.owner_nonce == self.nonce
                && review.plan.snapshot_sha256 == digest(&self.snapshot)?
                && !self.snapshot.busy,
            "REVIEW_STALE",
            "Local review belongs to another owner or state",
        )?;
        let mut installation = Installation::new(review.plan)?;
        installation.owner_nonce = Some(self.nonce);
        Ok(installation)
    }
    pub fn step(&mut self, installation: &mut Installation) -> Result<(), Error> {
        if installation.owner_nonce != Some(self.nonce) {
            installation.uncertain("OWNER_SCOPE");
            return Err(Error::new(
                "OWNER_SCOPE",
                "Journal has no execution capability for this owner; local review/reconciliation required",
            ));
        }
        let index = installation.begin_step(&self.snapshot)?;
        let result = match self.dispatch(installation, index) {
            Ok(result) => result,
            Err(error) => {
                // The strict model has not mutated the graph. This is a known
                // rejection, distinct from an uncertain native dispatch outcome.
                installation.rejected(&error.code);
                return Err(error);
            }
        };
        let before = self.snapshot.clone();
        let after = match apply_model_step(
            &before,
            &installation.plan,
            &installation.bindings,
            index,
            &result,
        ) {
            Ok(after) => after,
            Err(error) => {
                installation.rejected(&error.code);
                return Err(error);
            }
        };
        let receipt = Receipt {
            instance_id: installation.plan.instance_id.clone(),
            session: before.session.clone(),
            step: index,
            operation_sha256: digest(&installation.plan.steps[index])?,
            before: before.revision,
            after: after.revision,
            result,
        };
        self.snapshot = after.clone();
        installation.accept(receipt, &before, &after)
    }
    fn dispatch(&mut self, installation: &Installation, index: usize) -> Result<StepResult, Error> {
        self.sequence += 1;
        let id = |kind| format!("sim-{}-{kind}-{}", self.nonce, self.sequence);
        Ok(match &installation.plan.steps[index] {
            PlanStep::ImportAssetAfterLocalAuthorization { .. } => StepResult::Asset {
                id: ResourceId(id("asset")),
            },
            PlanStep::CreateOverlay { .. } => StepResult::Overlay {
                source: SourceId(id("source")),
                layer: LayerId(id("layer")),
            },
            PlanStep::AddLayer { .. } => StepResult::Layer {
                id: LayerId(id("layer")),
            },
            PlanStep::SetTransform { .. } => StepResult::Transform,
            PlanStep::CreateScene { .. } => {
                return Err(Error::new(
                    "CREATE_SCENE_FORBIDDEN",
                    "Insertion must preserve existing scenes",
                ));
            }
        })
    }
    /// Once review is accepted, always return the installation journal, including
    /// partial/uncertain outcomes. Ok means a report exists, not that installation
    /// succeeded; callers must inspect Phase::InstalledInModel before using it.
    /// Only a rejected begin returns Err because it made no modeled mutation.
    pub fn install(&mut self, review: LocalModelReview) -> Result<Installation, Error> {
        let mut installation = self.begin(review)?;
        while installation.phase == Phase::Installing {
            if let Err(error) = self.step(&mut installation) {
                if installation.phase == Phase::Installing {
                    installation.uncertain(&error.code);
                }
                break;
            }
        }
        if installation.phase == Phase::InstalledInModel
            && let Err(error) = installation.bound_rules()
        {
            installation.uncertain(&error.code);
        }
        Ok(installation)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RemovalPlan {
    pub instance_id: String,
    pub snapshot_sha256: String,
    pub layers: Vec<LayerId>,
    pub sources: Vec<SourceId>,
    pub assets: Vec<ResourceId>,
    pub retained_shared_sources: Vec<SourceId>,
    pub retained_shared_assets: Vec<ResourceId>,
    pub atomic: bool,
}
pub fn prepare_removal(
    installation: &Installation,
    current: &Snapshot,
) -> Result<RemovalPlan, Error> {
    current.validate()?;
    check(!current.busy, "OWNER_BUSY", "Removal requires idle owner")?;
    check(
        installation.pending_step.is_none()
            && matches!(installation.phase, Phase::InstalledInModel | Phase::Partial),
        "RECONCILIATION_REQUIRED",
        "Resolve uncertain operation before cleanup",
    )?;
    let owned = &Some(installation.plan.instance_id.clone());
    let layers: Vec<_> = installation
        .bindings
        .layers
        .values()
        .filter(|id| {
            current
                .layers
                .get(*id)
                .is_some_and(|l| &l.installation == owned)
        })
        .cloned()
        .collect();
    let mut sources = vec![];
    let mut retained_shared_sources = vec![];
    for id in installation.bindings.sources.values() {
        if !current
            .sources
            .get(id)
            .is_some_and(|s| &s.installation == owned)
        {
            continue;
        }
        if current
            .layers
            .values()
            .any(|l| &l.source == id && !layers.contains(&l.id))
        {
            retained_shared_sources.push(id.clone());
        } else {
            sources.push(id.clone());
        }
    }
    let mut assets = vec![];
    let mut retained_shared_assets = vec![];
    for id in installation.bindings.resources.values() {
        if !current
            .assets
            .get(id)
            .is_some_and(|a| &a.installation == owned)
        {
            continue;
        }
        let referenced = current.sources.values().filter(|s| !sources.contains(&s.id)).any(|s| matches!(&s.definition, Some(VisualDefinition::Image { resource_id, .. } | VisualDefinition::Video { resource_id, .. }) if resource_id == &id.0));
        if referenced {
            retained_shared_assets.push(id.clone());
        } else {
            assets.push(id.clone());
        }
    }
    Ok(RemovalPlan {
        instance_id: installation.plan.instance_id.clone(),
        snapshot_sha256: digest(current)?,
        layers,
        sources,
        assets,
        retained_shared_sources,
        retained_shared_assets,
        atomic: false,
    })
}
