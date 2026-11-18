//! Live Show Control facade on the one Production owner. Device/media ownership
//! remains in libobs. This module schedules control work only on owner polling.
#[path = "show_control/backend.rs"]
mod backend;
#[path = "show_control/ledger.rs"]
pub(in crate::core) mod ledger;
#[path = "show_control/storage.rs"]
mod storage;

use super::Production;
use backend::{Operation, OwnerBackend};
use motive_show_control::{
    actions::{Action, Revision, Transition, TransitionKind},
    deck::{ButtonTarget, Deck, DeckRuntime, DeckTransition, LiveDeckResult},
    journal::IntentJournal,
    model::{Error, Event, Payload, Scalar, validate_id},
    runtime::{
        BusyPolicy, Condition, Config, FailurePolicy, JobState, MonotonicClock, Rule, Runtime,
        Trust,
    },
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt},
    time::Instant,
};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum ShowControlCommand {
    ShowControlStatus,
    SaveShowControl,
    LoadShowControl,
    ArmShowControl {
        pid: u32,
        revision: u64,
    },
    ConfigureShowControl {
        config: Config,
        deck: Deck,
    },
    PressShowControl {
        session: String,
        button_id: String,
        event_id: String,
    },
    CancelShowControl {
        session: String,
        job_id: u64,
    },
    ReconcileShowControl {
        session: String,
        job_id: u64,
    },
}

pub(super) struct State {
    runtime: Option<Runtime<MonotonicClock>>,
    original_config: Config,
    armed: bool,
    project_fingerprint: String,
    deck: DeckRuntime,
    session: String,
    journal: IntentJournal,
    operations: BTreeMap<String, Operation>,
    requests: BTreeMap<u64, Vec<u64>>,
    active_key: Option<String>,
    next_operation_token: u64,
    failure: Option<String>,
    started: Instant,
}
impl State {
    fn new(
        config: Config,
        deck: Deck,
        project_fingerprint: String,
        armed: bool,
    ) -> Result<Self, Error> {
        let compiled = bind_deck(config.clone(), &deck)?;
        let runtime = Runtime::new(compiled, MonotonicClock::default())?;
        let deck = DeckRuntime::new(deck)?;
        let directory = super::data_dir().join("show-control");
        let io = || {
            Error::new(
                "SHOW_CONTROL_STORAGE",
                "Private durable Show Control storage is unavailable",
            )
        };
        if !directory.exists() {
            fs::DirBuilder::new()
                .mode(0o700)
                .create(&directory)
                .map_err(|_| io())?;
        }
        let metadata = directory.symlink_metadata().map_err(|_| io())?;
        if !metadata.is_dir()
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.permissions().mode() & 0o777 != 0o700
        {
            return Err(io());
        }
        if fs::read_dir(&directory)
            .map_err(|_| io())?
            .take(129)
            .count()
            >= 128
        {
            return Err(Error::new(
                "SHOW_CONTROL_SESSION_LIMIT",
                "Inspect/archive retained journals before creating another session",
            ));
        }
        let mut bytes = [0u8; 16];
        if unsafe { libc::getentropy(bytes.as_mut_ptr().cast(), bytes.len()) } != 0 {
            return Err(Error::new(
                "SESSION_RANDOMNESS",
                "Cannot create a fresh owner session",
            ));
        }
        let session = bytes.iter().map(|b| format!("{b:02x}")).collect::<String>();
        let journal = IntentJournal::create(
            &directory.join(format!("session-{session}.jsonl")),
            &session,
            std::process::id(),
        )?;
        Ok(Self {
            runtime: Some(runtime),
            original_config: config,
            armed,
            project_fingerprint,
            deck,
            session,
            journal,
            operations: BTreeMap::new(),
            requests: BTreeMap::new(),
            active_key: None,
            next_operation_token: 0,
            failure: None,
            started: Instant::now(),
        })
    }
    fn now(&self) -> u64 {
        self.started.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    fn settle_deck(&mut self) {
        let runtime = self.runtime.as_ref().unwrap();
        let finished: Vec<_> = self
            .requests
            .iter()
            .filter_map(|(request, ids)| {
                let jobs: Vec<_> = ids
                    .iter()
                    .filter_map(|id| runtime.jobs.iter().find(|j| j.id == *id))
                    .collect();
                if jobs.len() != ids.len() {
                    return Some((*request, LiveDeckResult::NeedsReconciliation));
                }
                if jobs.iter().any(|j| !j.state.terminal()) {
                    return None;
                }
                let result = if jobs
                    .iter()
                    .any(|j| j.state == JobState::NeedsReconciliation)
                {
                    LiveDeckResult::NeedsReconciliation
                } else if jobs.iter().all(|j| j.state == JobState::Completed) {
                    LiveDeckResult::Completed
                } else if jobs.iter().any(|j| j.state == JobState::Cancelled) {
                    LiveDeckResult::Cancelled
                } else {
                    LiveDeckResult::Rejected(
                        jobs.iter()
                            .flat_map(|j| &j.records)
                            .find_map(|r| r.code.clone())
                            .unwrap_or_else(|| "RULE_REJECTED".into()),
                    )
                };
                Some((*request, result))
            })
            .collect();
        for (request, result) in finished {
            let _ = self.deck.finish_live(request, self.now(), result);
            self.requests.remove(&request);
        }
    }
}

/// A local UI review object. It cannot be cloned, serialized or minted by a
/// public command. Any intervening production/config/session change invalidates it.
pub struct LocalDeckConfirmation {
    session: String,
    revision: Revision,
    button_id: String,
    label: String,
    actions: Vec<Action>,
    issued_ms: u64,
}
fn binding_fingerprint(graph: &crate::scene::Graph) -> String {
    use sha2::{Digest, Sha256};
    // Bind actual scene/layer/source identities and immutable resources. Own
    // text, visibility and transform changes must not invalidate the deck that
    // produced them; current selection is not another document identity.
    let sources:Vec<_>=graph.sources.iter().map(|source| {
        let spec=match &source.spec {crate::scene::SourceKind::Overlay{..}=>json!({"kind":"overlay"}),spec=>serde_json::to_value(spec).unwrap()};
        let overlay=source.overlay.as_ref().map(|definition| {
            let value=serde_json::to_value(definition).unwrap();
            json!({"kind":value["kind"],"asset_id":definition.asset_id(),"widget_kind":value["widget"]["kind"]})
        });
        json!({"id":source.id,"spec":spec,"overlay":overlay})
    }).collect();
    let scenes:Vec<_>=graph.scenes.iter().map(|scene|json!({"id":scene.id,"layers":scene.layers.iter().map(|layer|json!({"id":layer.id,"source_id":layer.source_id})).collect::<Vec<_>>()})).collect();
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&json!({"sources":sources,"scenes":scenes})).unwrap())
    )
}
impl LocalDeckConfirmation {
    pub fn button_id(&self) -> &str {
        &self.button_id
    }
    pub fn label(&self) -> &str {
        &self.label
    }
    pub fn actions(&self) -> &[Action] {
        &self.actions
    }
}

pub(in crate::core) fn validate_bindings(config: Config, deck: &Deck) -> Result<(), Error> {
    bind_deck(config, deck).map(|_| ())
}
fn bind_deck(mut config: Config, deck: &Deck) -> Result<Config, Error> {
    config.validate()?;
    deck.validate()?;
    let mut bound = BTreeSet::new();
    for button in &deck.buttons {
        let actions = match &button.target {
            ButtonTarget::Rule { rule_id }
            | ButtonTarget::Composite { rule_id }
            | ButtonTarget::Animation {
                animation_id: rule_id,
            } => {
                if !bound.insert(rule_id.clone()) {
                    return Err(Error::new(
                        "DECK_RULE_BINDING",
                        "Each live rule requires one unambiguous deck button",
                    ));
                }
                let rule = config
                    .rules
                    .iter_mut()
                    .find(|r| r.id == *rule_id)
                    .ok_or_else(|| {
                        Error::new("DECK_RULE_MISSING", "Button refers to a missing rule")
                    })?;
                if rule.event_kind != "manual.button_pressed" {
                    return Err(Error::new(
                        "DECK_RULE_KIND",
                        "Live deck binds only manual rules",
                    ));
                }
                if matches!(&button.target, ButtonTarget::Animation { .. })
                    && !rule.actions.iter().any(|a| {
                        matches!(
                            a,
                            Action::Animate { .. } | Action::TriggerAnimatedWidget { .. }
                        )
                    })
                {
                    return Err(Error::new(
                        "DECK_ANIMATION_BINDING",
                        "Animation button requires an animation rule",
                    ));
                }
                rule.conditions.push(Condition::Equals {
                    field: "button_id".into(),
                    value: Scalar::String(button.id.clone()),
                });
                None
            }
            ButtonTarget::Overlay { source_ref, show } => Some(vec![if *show {
                Action::ShowOverlay {
                    source_id: source_ref.clone(),
                }
            } else {
                Action::HideOverlay {
                    source_id: source_ref.clone(),
                }
            }]),
            ButtonTarget::Countdown { source_ref, reset } => Some(vec![if *reset {
                Action::CountdownReset {
                    source_id: source_ref.clone(),
                }
            } else {
                Action::CountdownStart {
                    source_id: source_ref.clone(),
                }
            }]),
            ButtonTarget::Scene {
                scene_ref,
                transition,
            } => Some(vec![Action::SelectScene {
                scene_id: scene_ref.clone(),
                transition: match transition {
                    DeckTransition::Cut => Transition {
                        kind: TransitionKind::Cut,
                        duration_ms: 0,
                    },
                    DeckTransition::Fade { duration_ms } => Transition {
                        kind: TransitionKind::Fade,
                        duration_ms: *duration_ms,
                    },
                },
            }]),
        };
        if let Some(actions) = actions {
            let id = format!("deck-{}", button.id);
            bound.insert(id.clone());
            config.rules.push(Rule {
                id,
                enabled: true,
                event_kind: "manual.button_pressed".into(),
                priority: 5,
                conditions: vec![Condition::Equals {
                    field: "button_id".into(),
                    value: Scalar::String(button.id.clone()),
                }],
                actions,
                cooldown_ms: 0,
                debounce_ms: 0,
                timeout_ms: 20000,
                busy_policy: BusyPolicy::Reject,
                failure_policy: FailurePolicy::Stop,
            });
        }
    }
    // An event can never invoke hidden extra manual rules outside the reviewed deck.
    if config
        .rules
        .iter()
        .any(|r| r.event_kind == "manual.button_pressed" && !bound.contains(&r.id))
    {
        return Err(Error::new(
            "UNBOUND_MANUAL_RULE",
            "All manual rules must be bound to a reviewed deck button",
        ));
    }
    config.validate()?;
    Ok(config)
}

impl Production {
    fn show_control_binding_fingerprint(&self) -> String {
        binding_fingerprint(self.graph())
    }
    pub(in crate::core) fn bump_revision(&mut self, cause: ledger::Cause<'_>) {
        let before = self.revision;
        self.revision = self
            .revision
            .checked_add(1)
            .expect("production revision exhausted");
        self.show_control_ledger
            .record(before, self.revision, cause);
    }
    pub(super) fn bump_external_revision(&mut self) {
        self.bump_revision(ledger::Cause::External);
    }
    pub fn show_control_status(&self) -> Value {
        let Some(state) = &self.show_control else {
            return json!({"available":true,"configured":false,"live":true});
        };
        let runtime = state.runtime.as_ref().unwrap();
        json!({"available":true,"configured":true,"live":true,"armed":state.armed,"project_fingerprint":state.project_fingerprint,"bindings_current":state.project_fingerprint==self.show_control_binding_fingerprint(),"session":state.session,"failure":state.failure,
            "rules":runtime.config.rules.iter().map(|r|json!({"id":r.id,"enabled":r.enabled,"event_kind":r.event_kind,"cooldown_ms":r.cooldown_ms,"actions":r.actions.len()})).collect::<Vec<_>>(),"deck":state.deck.deck(),"buttons":state.deck.deck().buttons.iter().map(|b|json!({"id":b.id,"state":state.deck.state(&b.id,state.now()).ok()})).collect::<Vec<_>>(),
            "jobs":runtime.jobs.iter().rev().take(16).map(|j|json!({"id":j.id,"rule_id":j.rule_id,"event_id":j.event_id,"state":j.state,"expected":j.expected,"cursor":j.cursor,"records":j.records.iter().rev().take(4).map(|r|json!({"index":r.index,"stage":r.stage,"operation_id":r.operation_id,"code":r.code,"revision_receipts":r.revision_receipts})).collect::<Vec<_>>()})).collect::<Vec<_>>(),
            "decisions":runtime.decisions.iter().rev().take(64).collect::<Vec<_>>(),"counters":runtime.variables.iter().filter(|(_,v)|matches!(v,Scalar::Int(_))).collect::<BTreeMap<_,_>>(),"history":state.deck.history(),
            "operations":state.operations.iter().rev().take(32).map(|(id,op)|json!({"id":id,"action_key":op.action_key,"cancel_requested":op.cancelled,"terminal":op.terminal})).collect::<Vec<_>>(),
            "status_limits":{"jobs":16,"records_per_job":4,"decisions":64,"operations":32},"jobs_total":runtime.jobs.len(),"operations_total":state.operations.len(),
            "presentation_verified":false})
    }
    pub fn configure_show_control(&mut self, config: Config, deck: Deck) -> Result<(), Error> {
        if self.shutdown_pending || self.shutdown_requested {
            return Err(Error::new(
                "SHUTDOWN_PENDING",
                "Cannot configure during shutdown",
            ));
        }
        if self.show_control.as_ref().is_some_and(|s| {
            s.runtime
                .as_ref()
                .unwrap()
                .jobs
                .iter()
                .any(|j| !j.state.terminal() || j.state == JobState::NeedsReconciliation)
        }) {
            return Err(Error::new(
                "SHOW_CONTROL_BUSY",
                "Complete or reconcile the current session before reconfiguration",
            ));
        }
        let state = State::new(config, deck, self.show_control_binding_fingerprint(), true)?;
        self.show_control = Some(state);
        self.bump_external_revision();
        Ok(())
    }
    pub fn save_show_control(&self) -> Result<(), Error> {
        let state = self
            .show_control
            .as_ref()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "No configuration to save"))?;
        if state.project_fingerprint != self.show_control_binding_fingerprint() {
            return Err(Error::new(
                "SHOW_CONTROL_BINDINGS_CHANGED",
                "Review the configuration against the changed production before saving",
            ));
        }
        storage::SavedConfiguration {
            version: 1,
            project_fingerprint: state.project_fingerprint.clone(),
            config: state.original_config.clone(),
            deck: state.deck.deck().clone(),
        }
        .save(
            &super::data_dir().join("show-control/configuration.json"),
            &state.session,
        )
    }
    pub fn load_show_control(&mut self) -> Result<(), Error> {
        if self.shutdown_pending || self.shutdown_requested {
            return Err(Error::new(
                "SHUTDOWN_PENDING",
                "Cannot load during shutdown",
            ));
        }
        if self.show_control.as_ref().is_some_and(|s| {
            s.runtime
                .as_ref()
                .unwrap()
                .jobs
                .iter()
                .any(|j| !j.state.terminal() || j.state == JobState::NeedsReconciliation)
        }) {
            return Err(Error::new(
                "SHOW_CONTROL_BUSY",
                "Reconcile the current session before loading",
            ));
        }
        let saved = storage::SavedConfiguration::read(
            &super::data_dir().join("show-control/configuration.json"),
        )?;
        let state = State::new(saved.config, saved.deck, saved.project_fingerprint, false)?;
        self.show_control = Some(state);
        self.bump_external_revision();
        Ok(())
    }
    pub fn arm_show_control(&mut self, pid: u32, revision: u64) -> Result<(), Error> {
        self.poll_health();
        if pid != std::process::id() || revision != self.revision {
            return Err(Error::new(
                "STALE_REVISION",
                "Refresh the actual production before arming",
            ));
        }
        if self.shutdown_pending || self.shutdown_requested {
            return Err(Error::new("SHUTDOWN_PENDING", "Cannot arm during shutdown"));
        }
        let fingerprint = self.show_control_binding_fingerprint();
        let state = self
            .show_control
            .as_mut()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "No loaded configuration"))?;
        if state.project_fingerprint != fingerprint {
            return Err(Error::new(
                "SHOW_CONTROL_BINDINGS_CHANGED",
                "Stored IDs/definitions do not match the current production",
            ));
        }
        state.armed = true;
        self.bump_external_revision();
        Ok(())
    }
    pub fn prepare_show_control_confirmation(
        &mut self,
        button_id: &str,
    ) -> Result<LocalDeckConfirmation, Error> {
        self.poll_health();
        let state = self
            .show_control
            .as_ref()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "Install a bound deck first"))?;
        if !state.armed {
            return Err(Error::new(
                "SHOW_CONTROL_DISARMED",
                "Explicitly arm the restored configuration first",
            ));
        }
        state.deck.authorize_live(button_id, state.now())?;
        let button = state
            .deck
            .deck()
            .buttons
            .iter()
            .find(|button| button.id == button_id)
            .expect("validated button");
        let rule_id = match &button.target {
            ButtonTarget::Rule { rule_id }
            | ButtonTarget::Composite { rule_id }
            | ButtonTarget::Animation {
                animation_id: rule_id,
            } => rule_id.clone(),
            _ => format!("deck-{button_id}"),
        };
        let actions = state
            .runtime
            .as_ref()
            .unwrap()
            .config
            .rules
            .iter()
            .find(|rule| rule.id == rule_id)
            .ok_or_else(|| Error::new("DECK_RULE_MISSING", "Bound actions are unavailable"))?
            .actions
            .clone();
        Ok(LocalDeckConfirmation {
            session: state.session.clone(),
            revision: Revision {
                pid: std::process::id(),
                revision: self.revision,
            },
            button_id: button_id.into(),
            label: button.label.clone(),
            actions,
            issued_ms: state.now(),
        })
    }
    pub fn confirm_show_control_local(
        &mut self,
        confirmation: LocalDeckConfirmation,
        event_id: &str,
    ) -> Result<Vec<u64>, Error> {
        self.poll_health();
        let state = self
            .show_control
            .as_ref()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "Install a bound deck first"))?;
        if confirmation.session != state.session
            || confirmation.revision
                != (Revision {
                    pid: std::process::id(),
                    revision: self.revision,
                })
            || state.now() < confirmation.issued_ms
            || state.now() - confirmation.issued_ms > 60000
        {
            return Err(Error::new(
                "STALE_DECK_CONFIRMATION",
                "Production or session changed since local review",
            ));
        }
        self.press_show_control_inner(&confirmation.button_id, event_id, true)
    }
    pub fn press_show_control(
        &mut self,
        button_id: &str,
        event_id: &str,
    ) -> Result<Vec<u64>, Error> {
        self.poll_health();
        self.press_show_control_inner(button_id, event_id, false)
    }
    fn press_show_control_inner(
        &mut self,
        button_id: &str,
        event_id: &str,
        local_review: bool,
    ) -> Result<Vec<u64>, Error> {
        validate_id(event_id)?;
        if self.shutdown_pending || self.shutdown_requested {
            return Err(Error::new(
                "SHUTDOWN_PENDING",
                "No new show work during shutdown",
            ));
        }
        let snapshot = self.show_control_production_snapshot();
        let fingerprint = self.show_control_binding_fingerprint();
        let state = self
            .show_control
            .as_mut()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "Install a bound deck first"))?;
        if !state.armed {
            return Err(Error::new(
                "SHOW_CONTROL_DISARMED",
                "Explicitly arm the restored configuration first",
            ));
        }
        if state.project_fingerprint != fingerprint {
            return Err(Error::new(
                "SHOW_CONTROL_BINDINGS_CHANGED",
                "Review the deck after production identities or resource bindings change",
            ));
        }
        if state.failure.is_some() {
            return Err(Error::new(
                "SHOW_CONTROL_RECOVERY_REQUIRED",
                "Durability failure requires reconciliation",
            ));
        }
        let button = state
            .deck
            .deck()
            .buttons
            .iter()
            .find(|b| b.id == button_id)
            .ok_or_else(|| Error::new("DECK_NOT_FOUND", "Unknown deck button"))?;
        if button.sensitive && !local_review {
            return Err(Error::new(
                "LOCAL_DECK_CONFIRMATION_REQUIRED",
                "Sensitive button requires an exact local owner confirmation",
            ));
        }
        let permit = state.deck.authorize_live(button_id, state.now())?;
        let press = state.deck.press_live(permit, state.now())?;
        let now = state.now();
        let event = Event {
            schema_version: 1,
            id: event_id.into(),
            origin: "owner.manual".into(),
            timestamp_ms: now,
            correlation_id: event_id.into(),
            external_id: None,
            simulated: false,
            payload: Payload::ManualButtonPressed {
                button_id: button_id.into(),
            },
        };
        let trust = Trust {
            authorized_origins: BTreeSet::from(["owner.manual".into()]),
            ..Trust::default()
        };
        match state
            .runtime
            .as_mut()
            .unwrap()
            .submit(event, &trust, &snapshot)
        {
            Ok(ids) if !ids.is_empty() => {
                state.requests.insert(press.request_id, ids.clone());
                Ok(ids)
            }
            result => {
                let error = result.err().unwrap_or_else(|| {
                    Error::new("NO_RULE_SELECTED", "No enabled rule admitted this button")
                });
                let _ = state.deck.finish_live(
                    press.request_id,
                    now,
                    LiveDeckResult::Rejected(error.code.clone()),
                );
                Err(error)
            }
        }
    }
    /// Call once from the outer owner heartbeat, after `poll_health` and outside
    /// command application. Inner post-command health polls must never run rules.
    pub fn poll_show_control(&mut self) {
        let Some(mut state) = self.show_control.take() else {
            return;
        };
        let mut runtime = state.runtime.take().unwrap();
        if !self.shutdown_pending
            && !self.shutdown_requested
            && state.failure.is_none()
            && state.armed
        {
            runtime.tick(&mut OwnerBackend {
                production: self,
                state: &mut state,
            });
        }
        state.runtime = Some(runtime);
        state.settle_deck();
        self.show_control = Some(state);
    }
    pub fn cancel_show_control(&mut self, job_id: u64) -> Result<(), Error> {
        let mut state = self
            .show_control
            .take()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "No Show Control session"))?;
        let mut runtime = state.runtime.take().unwrap();
        let result = runtime.cancel(
            job_id,
            &mut OwnerBackend {
                production: self,
                state: &mut state,
            },
        );
        state.runtime = Some(runtime);
        state.settle_deck();
        self.show_control = Some(state);
        result
    }
    pub fn reconcile_show_control(&mut self, job_id: u64) -> Result<JobState, Error> {
        let mut state = self
            .show_control
            .take()
            .ok_or_else(|| Error::new("SHOW_CONTROL_UNCONFIGURED", "No Show Control session"))?;
        let mut runtime = state.runtime.take().unwrap();
        let result = runtime.reconcile(
            job_id,
            &mut OwnerBackend {
                production: self,
                state: &mut state,
            },
        );
        state.runtime = Some(runtime);
        state.settle_deck();
        self.show_control = Some(state);
        result
    }
    pub(super) fn apply_show_control(&mut self, command: ShowControlCommand) -> Value {
        let result = match command {
            ShowControlCommand::ShowControlStatus => {
                return json!({"ok":true,"show_control":self.show_control_status()});
            }
            ShowControlCommand::SaveShowControl => self.save_show_control().map(|()| Value::Null),
            ShowControlCommand::LoadShowControl => self.load_show_control().map(|()| Value::Null),
            ShowControlCommand::ArmShowControl { pid, revision } => {
                self.arm_show_control(pid, revision).map(|()| Value::Null)
            }
            ShowControlCommand::ConfigureShowControl { config, deck } => self
                .configure_show_control(config, deck)
                .map(|()| Value::Null),
            ShowControlCommand::PressShowControl {
                session,
                button_id,
                event_id,
            } => {
                if self
                    .show_control
                    .as_ref()
                    .is_none_or(|state| state.session != session)
                {
                    Err(Error::new(
                        "CORE_SESSION_CHANGED",
                        "Refresh the actual owner session before a manual event",
                    ))
                } else {
                    self.press_show_control(&button_id, &event_id)
                        .map(|ids| json!({"job_ids":ids}))
                }
            }
            ShowControlCommand::CancelShowControl { session, job_id } => {
                if self
                    .show_control
                    .as_ref()
                    .is_none_or(|state| state.session != session)
                {
                    Err(Error::new(
                        "CORE_SESSION_CHANGED",
                        "Job belongs to another owner session",
                    ))
                } else {
                    self.cancel_show_control(job_id).map(|()| Value::Null)
                }
            }
            ShowControlCommand::ReconcileShowControl { session, job_id } => {
                if self
                    .show_control
                    .as_ref()
                    .is_none_or(|state| state.session != session)
                {
                    Err(Error::new(
                        "CORE_SESSION_CHANGED",
                        "Job belongs to another owner session",
                    ))
                } else {
                    self.reconcile_show_control(job_id)
                        .map(|state| json!({"state":state}))
                }
            }
        };
        match result {
            Ok(result) => {
                json!({"ok":true,"pid":std::process::id(),"revision":self.revision,"result":result,"show_control":self.show_control_status()})
            }
            Err(e) => super::error(&e.code, e.message),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use motive_show_control::deck::{DeckButton, DeckGroup, DeckIcon};
    pub(super) fn inputs() -> (Config, Deck) {
        let config = Config {
            schema_version: 1,
            rules: vec![Rule {
                id: "celebrate".into(),
                enabled: true,
                event_kind: "manual.button_pressed".into(),
                priority: 5,
                conditions: vec![],
                actions: vec![Action::ShowOverlay {
                    source_id: "score".into(),
                }],
                cooldown_ms: 1000,
                debounce_ms: 0,
                timeout_ms: 5000,
                busy_policy: BusyPolicy::Reject,
                failure_policy: FailurePolicy::Stop,
            }],
            variables: BTreeMap::new(),
            queue_capacity: 8,
            rate_limit: 10,
            rate_window_ms: 1000,
            max_actions_per_event: 32,
        };
        let deck = Deck {
            schema_version: 1,
            id: "matchday".into(),
            name: "Matchday".into(),
            groups: vec![DeckGroup {
                id: "live".into(),
                label: "Live".into(),
                order: 0,
            }],
            buttons: vec![DeckButton {
                id: "goal".into(),
                group_id: "live".into(),
                label: "Goal".into(),
                icon: DeckIcon::Goal,
                order: 0,
                enabled: true,
                shortcut: None,
                cooldown_ms: 1000,
                sensitive: false,
                target: ButtonTarget::Rule {
                    rule_id: "celebrate".into(),
                },
            }],
        };
        (config, deck)
    }
    #[test]
    fn deck_binding_narrows_manual_rule_and_rejects_hidden_targets() {
        let (config, deck) = inputs();
        let bound = bind_deck(config.clone(), &deck).unwrap();
        assert!(
            matches!(&bound.rules[0].conditions[0],Condition::Equals{field,value:Scalar::String(id)} if field=="button_id"&&id=="goal")
        );
        let mut hidden = config.clone();
        let mut rule = hidden.rules[0].clone();
        rule.id = "hidden".into();
        hidden.rules.push(rule);
        assert_eq!(
            bind_deck(hidden, &deck).unwrap_err().code,
            "UNBOUND_MANUAL_RULE"
        );
        let mut missing = deck.clone();
        missing.buttons[0].target = ButtonTarget::Rule {
            rule_id: "missing".into(),
        };
        assert_eq!(
            bind_deck(config, &missing).unwrap_err().code,
            "DECK_RULE_MISSING"
        );
    }
    #[test]
    fn core_typed_commands_have_exact_compatible_shapes() {
        let command = actions_for_test();
        for command in command {
            let value = serde_json::to_value(command).unwrap();
            assert!(super::super::parse_command(value).is_ok());
        }
    }
    fn actions_for_test() -> Vec<motive_show_control::actions::CoreCommand> {
        use motive_show_control::actions::*;
        vec![
            CoreCommand::OverlayEvent {
                source_id: "score".into(),
                event: WidgetEvent::Trigger,
            },
            CoreCommand::ConfigureTransition {
                transition: Transition {
                    kind: TransitionKind::Fade,
                    duration_ms: 300,
                },
            },
            CoreCommand::SelectScene {
                scene_id: "scene-1".into(),
            },
            CoreCommand::AnimateOverlay {
                scene_id: "scene-1".into(),
                layer_id: "layer-1".into(),
                animation: Animation {
                    kind: AnimationKind::ScaleIn,
                    easing: Easing::EaseOut,
                    duration_ms: 400,
                    distance: 0.,
                    scale_from: 0.5,
                },
            },
            CoreCommand::CancelOverlayAnimation { operation_id: 1 },
            CoreCommand::TriggerAnimatedWidget {
                source_id: "score".into(),
                scene_id: "scene-1".into(),
                layer_id: "layer-1".into(),
                animation: Animation {
                    kind: AnimationKind::ScaleIn,
                    easing: Easing::EaseOut,
                    duration_ms: 450,
                    distance: 0.,
                    scale_from: 0.8,
                },
            },
        ]
    }
    #[test]
    fn remote_commands_cannot_carry_local_confirmation_or_trust() {
        let valid = json!({"op":"press_show_control","session":"owner-session","button_id":"goal","event_id":"evt-1"});
        assert!(super::super::parse_command(valid.clone()).is_ok());
        let mut invalid = valid;
        invalid["confirmed"] = json!(true);
        assert!(super::super::parse_command(invalid).is_err());
        assert!(
            super::super::parse_command(
                json!({"op":"confirm_show_control_local","button_id":"goal","revision":0})
            )
            .is_err()
        );
    }
    #[test]
    fn binding_fingerprint_tracks_identities_not_live_visibility() {
        let mut graph = crate::scene::Graph::default();
        let original = binding_fingerprint(&graph);
        graph.active_scene = "another-program-scene".into();
        graph.scenes[0].layers[0].layouts.horizontal.visible = false;
        graph.scenes[0].layers[0].layouts.vertical.x += 10.;
        assert_eq!(binding_fingerprint(&graph), original);
        graph.scenes[0].layers[0].source_id = "different-source".into();
        assert_ne!(binding_fingerprint(&graph), original);
    }
}
