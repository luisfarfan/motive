//! Direct owner adapter. No socket, worker, synthetic clock or replacement graph.
use super::{Production, State, ledger::NativeOperation};
use crate::core::{Command, overlays};
use crate::scene::TransitionPhase;
use motive_show_control::{
    actions::{self, Action, CoreCommand, PreparedAction, ProductionSnapshot, Revision},
    journal::DispatchIntent,
    model::Error,
    runtime::{Backend, Completion, DispatchOutcome, DispatchReport, PollReport, TerminalReceipt},
};

pub(super) struct Operation {
    pub action_key: String,
    pub native: NativeOperation,
    pub terminal: Option<PollReport>,
    pub cancelled: bool,
}

pub(super) struct OwnerBackend<'a> {
    pub production: &'a mut Production,
    pub state: &'a mut State,
}
fn error(code: &str, message: &str) -> Error {
    Error::new(code, message)
}
fn rejected(error: Error) -> DispatchReport {
    DispatchReport::legacy(DispatchOutcome::Rejected(error))
}

impl OwnerBackend<'_> {
    fn version(&self) -> Revision {
        Revision {
            pid: std::process::id(),
            revision: self.production.revision,
        }
    }
    fn token(&mut self, native: NativeOperation) -> String {
        let (kind, id) = match native {
            NativeOperation::Animation(id) => ("animation", id),
            NativeOperation::Transition(id) => ("transition", id),
        };
        self.state.next_operation_token += 1;
        format!(
            "{}:{kind}:{id}:{}",
            self.state.session, self.state.next_operation_token
        )
    }
    fn observe(&self, native: NativeOperation) -> Completion {
        match native {
            NativeOperation::Animation(id) => {
                let runtime = self.production.engine.overlay_state();
                let Some(job) = runtime["animations"]["jobs"]
                    .as_array()
                    .and_then(|jobs| jobs.iter().find(|j| j["operation_id"].as_u64() == Some(id)))
                else {
                    return Completion::Unknown;
                };
                if job["pending_ack"] == true {
                    return Completion::Pending;
                }
                match job["phase"].as_str() {
                    Some("completed") => Completion::Completed,
                    Some("cancelled") => Completion::Cancelled,
                    Some("failed") => {
                        Completion::Failed(error("ANIMATION_FAILED", "Native animation failed"))
                    }
                    Some("pending" | "running" | "cancel_pending" | "cancelling" | "queued") => {
                        Completion::Pending
                    }
                    _ => Completion::Unknown,
                }
            }
            NativeOperation::Transition(id) => {
                let transition = self.production.engine.scene_state();
                if transition.operation_id != id {
                    return Completion::Unknown;
                }
                match transition.phase {
                    TransitionPhase::Preparing | TransitionPhase::Running => Completion::Pending,
                    TransitionPhase::Completed => Completion::Completed,
                    TransitionPhase::Cancelled => Completion::Cancelled,
                    TransitionPhase::Failed => Completion::Failed(error(
                        "TRANSITION_FAILED",
                        "Native transition failed; inspect production state",
                    )),
                    TransitionPhase::Idle => Completion::Unknown,
                }
            }
        }
    }
    fn run(&mut self, prepared: &PreparedAction) -> Result<Option<NativeOperation>, Error> {
        let mut native = None;
        let before = self.version();
        for core_command in &prepared.commands {
            // Configure+select is one owner turn but not a rollback transaction.
            // An unrelated lifecycle between its commands stops the second step.
            if self
                .production
                .show_control_ledger
                .receipt(
                    self.state.active_key.as_deref().unwrap(),
                    None,
                    before,
                    self.version(),
                )
                .is_none()
            {
                return Err(error(
                    "CONCURRENT_MUTATION",
                    "Another production lifecycle changed during dispatch",
                ));
            }
            let value = serde_json::to_value(core_command)
                .map_err(|_| error("INVALID_ACTION", "Cannot encode typed action"))?;
            let command: Command = crate::core::parse_command(value).map_err(|_| {
                error(
                    "UNSUPPORTED_ACTION",
                    "Core rejected the typed action contract",
                )
            })?;
            let previous_scene_id = self.production.engine.scene_state().operation_id;
            let result = self.production.apply(command, "Show Control");
            if result["ok"] != true {
                let code = result["error"]["code"].as_str().unwrap_or("CORE_REJECTED");
                return Err(error(
                    code,
                    "Production rejected the action; inspect its shared state",
                ));
            }
            // Inspect the accepted command shape, not a later arbitrary snapshot.
            match core_command {
                CoreCommand::AnimateOverlay { .. } | CoreCommand::TriggerAnimatedWidget { .. } => {
                    let id = result["result"]["operation_id"]
                        .as_u64()
                        .filter(|id| *id > 0)
                        .ok_or_else(|| {
                            error(
                                "MISSING_OPERATION",
                                "Native acceptance has no animation identity",
                            )
                        })?;
                    native = Some(NativeOperation::Animation(id));
                }
                CoreCommand::CancelOverlayAnimation { operation_id } => {
                    native = Some(NativeOperation::Animation(*operation_id))
                }
                CoreCommand::SelectScene { scene_id } => {
                    let transition = self.production.engine.scene_state();
                    let id = transition.operation_id;
                    if id == previous_scene_id && transition.current_scene == *scene_id {
                        continue; // Accepted no-op; never claim an old native ID.
                    }
                    if id == 0 || id == previous_scene_id {
                        return Err(error(
                            "MISSING_OPERATION",
                            "Native acceptance has no transition identity",
                        ));
                    }
                    native = Some(NativeOperation::Transition(id));
                }
                _ => {}
            }
        }
        Ok(native)
    }
}

impl Backend for OwnerBackend<'_> {
    fn snapshot(&self) -> ProductionSnapshot {
        self.production.show_control_production_snapshot()
    }
    fn simulated(&self) -> bool {
        false
    }
    fn dispatch(&mut self, action: &PreparedAction, key: &str) -> DispatchOutcome {
        self.dispatch_checked(action, key, self.version()).outcome
    }
    fn poll(&mut self, operation: &str) -> Completion {
        self.state
            .operations
            .get(operation)
            .map_or(Completion::Unknown, |op| {
                op.terminal
                    .as_ref()
                    .map_or_else(|| self.observe(op.native), |r| r.completion.clone())
            })
    }
    fn dispatch_checked(
        &mut self,
        prepared: &PreparedAction,
        key: &str,
        expected: Revision,
    ) -> DispatchReport {
        self.production.poll_health();
        if self.state.failure.is_some() {
            return rejected(error(
                "SHOW_CONTROL_RECOVERY_REQUIRED",
                "Durability failure requires explicit reconciliation",
            ));
        }
        let snapshot = self.snapshot();
        let prepared = match actions::prepare(&prepared.action, &snapshot, Some(expected)) {
            Ok(p) if !p.local => p,
            Ok(_) => {
                return rejected(error(
                    "LOCAL_ACTION",
                    "Local runtime action cannot enter native backend",
                ));
            }
            Err(e) => return rejected(e),
        };
        if self.state.operations.len() >= 512 {
            return rejected(error(
                "OPERATION_LIMIT",
                "New owner session required; no silent operation eviction",
            ));
        }
        if let Err(e) = self.state.journal.begin(DispatchIntent {
            action_key: key.into(),
            expected,
            prepared: prepared.clone(),
        }) {
            return rejected(e);
        }
        let source = match &prepared.action {
            Action::ShowOverlay { source_id }
            | Action::HideOverlay { source_id }
            | Action::Widget { source_id, .. }
            | Action::CountdownStart { source_id }
            | Action::CountdownReset { source_id }
            | Action::UpdateText { source_id, .. } => Some(source_id.clone()),
            _ => None,
        };
        if !self.production.show_control_ledger.begin(key, source) {
            return rejected(error(
                "PRODUCTION_BUSY",
                "Owner dispatch is already scoped or exhausted",
            ));
        }
        self.state.active_key = Some(key.into());
        let result = self.run(&prepared);
        self.state.active_key = None;
        self.production.show_control_ledger.end();
        let after = self.version();
        let report = match result {
            Ok(native) => {
                let token = native.map(|n| self.token(n));
                if let (Some(native), Some(token)) = (native, &token) {
                    self.state.operations.insert(
                        token.clone(),
                        Operation {
                            action_key: key.into(),
                            native,
                            terminal: None,
                            cancelled: false,
                        },
                    );
                }
                DispatchReport {
                    receipt: self.production.show_control_ledger.receipt(
                        key,
                        token.as_deref(),
                        expected,
                        after,
                    ),
                    outcome: token.map_or(DispatchOutcome::Completed, |operation_id| {
                        DispatchOutcome::Accepted { operation_id }
                    }),
                }
            }
            Err(e) if after == expected => rejected(e),
            Err(_) => DispatchReport::legacy(DispatchOutcome::Uncertain),
        };
        if let Err(e) = self.state.journal.record_dispatch(key, report.clone()) {
            self.state.failure = Some(e.code);
            // A known native token remains in owner status even if the runtime
            // cannot accept the unpersisted dispatch receipt.
            return DispatchReport::legacy(DispatchOutcome::Uncertain);
        }
        report
    }
    fn poll_checked(&mut self, token: &str, key: &str, expected: Revision) -> PollReport {
        if !token.starts_with(&format!("{}:", self.state.session)) {
            return PollReport::legacy(Completion::Unknown);
        }
        self.production.poll_health();
        let Some(operation) = self.state.operations.get(token) else {
            return PollReport::legacy(Completion::Unknown);
        };
        if operation.action_key != key {
            return PollReport::legacy(Completion::Unknown);
        }
        if let Some(report) = &operation.terminal {
            return report.clone();
        }
        let native = operation.native;
        let completion = self.observe(native);
        if matches!(completion, Completion::Pending | Completion::Unknown) {
            // Unknown observation is not a native terminal barrier. Preserve
            // the durable accepted token so explicit reconciliation may inspect
            // it again; never dispatch it again or cache an invented terminal.
            return PollReport::legacy(completion);
        }
        let receipt = matches!(completion, Completion::Completed)
            .then(|| {
                self.production.show_control_ledger.receipt(
                    key,
                    Some(token),
                    expected,
                    self.version(),
                )
            })
            .flatten();
        let report = PollReport {
            completion,
            receipt,
            terminal_receipt: Some(TerminalReceipt {
                action_key: key.into(),
                operation_id: token.into(),
                pid: std::process::id(),
            }),
        };
        if let Err(e) = self
            .state
            .journal
            .record_completion(key, token, report.clone())
        {
            self.state.failure = Some(e.code);
            return PollReport::legacy(Completion::Unknown);
        }
        self.state.operations.get_mut(token).unwrap().terminal = Some(report.clone());
        self.production.show_control_ledger.forget(native);
        report
    }
    fn request_cancel(&mut self, token: &str) -> Result<(), Error> {
        let operation = self.state.operations.get(token).ok_or_else(|| {
            error(
                "UNKNOWN_OPERATION",
                "Operation does not belong to this owner session",
            )
        })?;
        if operation.terminal.is_some() || operation.cancelled {
            return Err(error(
                "OPERATION_TERMINAL",
                "Cancellation was already requested or observed",
            ));
        }
        self.state
            .journal
            .begin_cancel(&operation.action_key, token)?;
        let native = operation.native;
        self.state.operations.get_mut(token).unwrap().cancelled = true;
        let result = match native {
            NativeOperation::Animation(operation_id) => self.production.apply(
                Command::Overlay(overlays::OverlayCommand::CancelOverlayAnimation { operation_id }),
                "Show Control cancellation",
            ),
            NativeOperation::Transition(operation_id) => self.production.apply(
                Command::CancelTransition { operation_id },
                "Show Control cancellation",
            ),
        };
        if result["ok"] != true {
            self.state.failure = Some("CANCEL_UNCERTAIN".into());
        }
        // The durable request is acknowledged, not native completion. Runtime
        // must enter NeedsReconciliation even if the native cancel reply failed.
        Ok(())
    }
}

// Scalar snapshot projection only: the scene graph remains owned by Production.
impl Production {
    pub(in crate::core) fn show_control_production_snapshot(&self) -> ProductionSnapshot {
        let mut snapshot = ProductionSnapshot {
            pid: std::process::id(),
            revision: self.revision,
            active_scene: self.graph().active_scene.clone(),
            output_active: self.outputs.busy(),
            structural_busy: self.shutdown_pending
                || self.shutdown_requested
                || self.overlays.busy(),
            transition_active: self.engine.scene_state().busy(),
            animation_active: self.engine.overlay_animation_busy(),
            ..ProductionSnapshot::default()
        };
        let health = self.engine.graph_health();
        for source in &self.graph().sources {
            let state = health
                .as_array()
                .and_then(|values| values.iter().find(|s| s["id"] == source.id));
            let ready = state.is_some_and(|s| s["issue"].as_str().is_none_or(str::is_empty));
            snapshot.sources.insert(
                source.id.clone(),
                if self.awaiting_recovery.contains(&source.id) {
                    actions::SourceReadiness::Recovering
                } else if ready {
                    actions::SourceReadiness::Ready
                } else {
                    actions::SourceReadiness::Failed
                },
            );
            if let Some(definition) = &source.overlay {
                let kind = match definition {
                    overlays::Definition::Text { .. } => actions::SourceKind::Text,
                    overlays::Definition::Shape { .. } => actions::SourceKind::Shape,
                    overlays::Definition::Image { .. } => actions::SourceKind::Image,
                    overlays::Definition::Video { .. } => actions::SourceKind::Video,
                    overlays::Definition::Widget { widget } => match widget.kind {
                        overlays::WidgetKind::Alert => actions::SourceKind::Alert,
                        overlays::WidgetKind::Countdown => actions::SourceKind::Countdown,
                        overlays::WidgetKind::LowerThird => actions::SourceKind::LowerThird,
                    },
                };
                snapshot.source_kinds.insert(source.id.clone(), kind);
                if kind == actions::SourceKind::Text {
                    let mut definition = serde_json::to_value(definition).unwrap();
                    definition.as_object_mut().unwrap().remove("kind");
                    if let Ok(text) = serde_json::from_value(definition) {
                        snapshot.text_definitions.insert(source.id.clone(), text);
                    }
                }
            }
        }
        for scene in &self.graph().scenes {
            snapshot.scenes.insert(
                scene.id.clone(),
                scene
                    .layers
                    .iter()
                    .filter(|l| l.layouts.get(self.project.variant).visible)
                    .map(|l| l.source_id.clone())
                    .collect(),
            );
            for layer in &scene.layers {
                snapshot.layers.insert(
                    layer.id.clone(),
                    actions::LayerBinding {
                        scene_id: scene.id.clone(),
                        source_id: layer.source_id.clone(),
                    },
                );
            }
        }
        let native = self.engine.overlay_state();
        for job in native["animations"]["jobs"]
            .as_array()
            .into_iter()
            .flatten()
        {
            let busy = job["pending_ack"] == true
                || matches!(
                    job["phase"].as_str(),
                    Some("pending" | "running" | "cancel_pending" | "cancelling" | "queued")
                );
            if busy {
                if let Some(layer) = job["layer_id"].as_str() {
                    snapshot.busy_layers.insert(layer.into());
                }
                if let Some(id) = job["operation_id"].as_u64() {
                    snapshot.animation_operations.insert(id);
                }
            }
        }
        snapshot
    }
}
