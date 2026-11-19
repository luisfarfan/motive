//! Isolated, offline owner adapter. No Production authority is created here.
//! Reuses Show Control events plus H16 projection, IPC and lifecycle contracts.
#![forbid(unsafe_code)]
use motive_browser_contracts::{
    Identity, Result,
    ipc::{Gate, SAFE_INTEGER, Visual, strict_json},
    lifecycle::{Lifecycle, State},
    projection::goal_message,
};
use motive_show_control::{model::validate_id, providers::AcceptedEvent};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::BTreeMap,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT_OWNER: AtomicU64 = AtomicU64::new(1);

/// Deliberately not Deserialize: package booleans, JSON and renderer messages
/// cannot construct owner approval. This constructor exists ONLY for offline QA.
/// A future Production constructor requires the H17 handoff and local authority.
pub struct OfflineOwner {
    nonce: u64,
    session: String,
    revision: u64,
    generations: RefCell<BTreeMap<u64, u64>>,
}
impl OfflineOwner {
    pub fn new(session: &str, revision: u64) -> Result<Self> {
        validate_id(session).map_err(|_| "OWNER_SESSION")?;
        if !session.starts_with("simulation.") || revision > SAFE_INTEGER {
            return Err("OFFLINE_OWNER_REQUIRED");
        }
        Ok(Self {
            nonce: NEXT_OWNER.fetch_add(1, Ordering::Relaxed),
            session: session.into(),
            revision,
            generations: RefCell::new(BTreeMap::new()),
        })
    }
    pub fn advance_revision(&mut self) -> Result<()> {
        self.revision = self
            .revision
            .checked_add(1)
            .filter(|n| *n <= SAFE_INTEGER)
            .ok_or("REVISION_OVERFLOW")?;
        Ok(())
    }
    /// Caller has already verified bytes using Element Lab's validate_web/broker.
    /// The supplied hash identifies those bytes; it does not establish trust.
    pub fn review_goal_fixture(&self, review: FixtureReview) -> Result<Binding> {
        validate_id(&review.binding_id).map_err(|_| "BINDING_ID")?;
        validate_id(&review.origin).map_err(|_| "BINDING_ORIGIN")?;
        if !review.origin.starts_with("simulation.")
            || review.manifest["id"] != "goal-celebration-web"
            || review.manifest["version"] != "1.0.0"
            || review.definition_sha256.len() != 64
            || !review
                .definition_sha256
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            || review.identity.instance == 0
            || review.identity.generation == 0
            || review.identity.instance > SAFE_INTEGER
            || review.identity.generation > SAFE_INTEGER
        {
            return Err("BINDING_REVIEW");
        }
        {
            let generations = self.generations.borrow();
            if generations
                .get(&review.identity.instance)
                .is_some_and(|g| review.identity.generation <= *g)
            {
                return Err("GENERATION_REUSE");
            }
            if !generations.contains_key(&review.identity.instance) && generations.len() >= 16 {
                return Err("INSTANCE_LIMIT");
            }
        }
        let active_ms = review.manifest["limits"]["max_active_ms"]
            .as_u64()
            .filter(|n| (1000..=30_000).contains(n))
            .ok_or("ACTIVE_LIMIT")?;
        let mut gate = Gate::from_validated_manifest(review.identity, review.manifest.clone())?;
        // Reuse native property validation atomically before accepting review.
        let initial = envelope(
            review.identity,
            1000,
            json!({"version":1,"seq":1,
            "kind":"properties","properties":review.properties}),
        );
        gate.accept(
            &serde_json::to_vec(&initial).map_err(|_| "MESSAGE_JSON")?,
            0,
        )?;
        let properties = Value::Object(gate.properties().clone());
        let mut lifecycle = Lifecycle::new(review.identity);
        lifecycle.start(0)?;
        self.generations
            .borrow_mut()
            .insert(review.identity.instance, review.identity.generation);
        Ok(Binding {
            approval: Approval {
                owner_nonce: self.nonce,
                session: self.session.clone(),
                revision: self.revision,
                binding_id: review.binding_id,
                definition_id: "goal-celebration-web".into(),
                definition_sha256: review.definition_sha256,
                origin: review.origin,
            },
            gate: Gate::from_validated_manifest(review.identity, review.manifest)?,
            lifecycle,
            sequence: 0,
            active_ms,
            properties,
            revoked: false,
            property_sequence: None,
            properties_acknowledged: false,
            last_ack: 0,
        })
    }
}
pub struct FixtureReview {
    pub binding_id: String,
    pub definition_sha256: String,
    pub identity: Identity,
    pub origin: String,
    pub manifest: Value,
    pub properties: Value,
}
struct Approval {
    owner_nonce: u64,
    session: String,
    revision: u64,
    binding_id: String,
    definition_id: String,
    definition_sha256: String,
    origin: String,
}
/// Contains only an admitted H16 envelope. Constructed exclusively by Binding.
/// The renderer receives `message`, never an internal Show Control Event.
#[derive(Debug)]
pub struct VisualDispatch {
    envelope: Value,
}
impl VisualDispatch {
    pub fn envelope(&self) -> &Value {
        &self.envelope
    }
    pub fn message(&self) -> &Value {
        &self.envelope["message"]
    }
}
#[derive(Debug, PartialEq, Eq)]
pub enum Observation {
    /// JS readiness/receipt only. This never proves pixels or a native outcome.
    RendererReady,
    RendererAcknowledged {
        sequence: u64,
        accepted: bool,
    },
}
pub struct Binding {
    approval: Approval,
    gate: Gate,
    lifecycle: Lifecycle,
    sequence: u64,
    active_ms: u64,
    properties: Value,
    revoked: bool,
    property_sequence: Option<u64>,
    properties_acknowledged: bool,
    last_ack: u64,
}
fn envelope(identity: Identity, expires_ms: u64, message: Value) -> Value {
    json!({"protocol":1,"instance":identity.instance,"generation":identity.generation,
        "expires_ms":expires_ms,"message":message})
}
impl Binding {
    pub fn identity(&self) -> Identity {
        self.lifecycle.identity()
    }
    pub fn state(&self) -> State {
        self.lifecycle.state()
    }
    pub fn approved_properties(&self) -> &Value {
        &self.properties
    }
    pub fn review_summary(&self) -> Value {
        json!({"definition_id":self.approval.definition_id,"definition_sha256":self.approval.definition_sha256,
            "binding_id":self.approval.binding_id,"owner_session":self.approval.session,
            "owner_revision":self.approval.revision,"instance":self.identity().instance,
            "generation":self.identity().generation,"mode":"offline_owner_fixture",
            "production_connected":false,"native_terminal_outcome":false})
    }
    fn owner(&self, owner: &OfflineOwner) -> Result<()> {
        if self.revoked {
            return Err("BINDING_REVOKED");
        }
        if self.approval.owner_nonce != owner.nonce || self.approval.session != owner.session {
            return Err("OWNER_SESSION");
        }
        if owner.generations.borrow().get(&self.identity().instance)
            != Some(&self.identity().generation)
        {
            return Err("STALE_GENERATION");
        }
        if self.approval.revision != owner.revision {
            return Err("OWNER_REVISION");
        }
        Ok(())
    }
    fn next(&mut self) -> Result<u64> {
        self.sequence = self
            .sequence
            .checked_add(1)
            .filter(|n| *n <= SAFE_INTEGER)
            .ok_or("MESSAGE_SEQUENCE")?;
        Ok(self.sequence)
    }
    fn admit(&mut self, message: Value, now: u64) -> Result<VisualDispatch> {
        let expires = now
            .checked_add(1000)
            .filter(|n| *n <= SAFE_INTEGER)
            .ok_or("MESSAGE_DEADLINE")?;
        let value = envelope(self.identity(), expires, message);
        self.gate.accept(
            &serde_json::to_vec(&value).map_err(|_| "MESSAGE_JSON")?,
            now,
        )?;
        Ok(VisualDispatch { envelope: value })
    }
    pub fn ready(
        &mut self,
        owner: &OfflineOwner,
        identity: Identity,
        now: u64,
    ) -> Result<Observation> {
        self.owner(owner)?;
        self.lifecycle.ready(identity, now)?;
        Ok(Observation::RendererReady)
    }
    pub fn initial_properties(&mut self, owner: &OfflineOwner, now: u64) -> Result<VisualDispatch> {
        self.owner(owner)?;
        self.lifecycle.poll(now)?;
        if self.state() != State::Ready {
            return Err("NOT_READY");
        }
        let sequence = self.next()?;
        let dispatch = self.admit(
            json!({"version":1,"seq":sequence,"kind":"properties","properties":self.properties}),
            now,
        )?;
        self.property_sequence = Some(sequence);
        self.properties_acknowledged = false;
        Ok(dispatch)
    }
    pub fn goal(
        &mut self,
        owner: &OfflineOwner,
        event: &AcceptedEvent,
        now: u64,
    ) -> Result<VisualDispatch> {
        self.owner(owner)?;
        self.lifecycle.poll(now)?;
        if self.state() != State::Ready {
            return Err("NOT_READY");
        }
        if !self.properties_acknowledged {
            return Err("PROPERTIES_UNACKNOWLEDGED");
        }
        if event.event().origin != self.approval.origin {
            return Err("BINDING_ORIGIN");
        }
        event.event().validate().map_err(|_| "BINDING_EVENT")?;
        let sequence = self.next()?;
        let source = serde_json::to_value(event.event()).map_err(|_| "BINDING_EVENT")?;
        let message = goal_message(sequence, &source)?;
        let dispatch = self.admit(message, now)?;
        self.lifecycle.begin(sequence, now, self.active_ms)?;
        Ok(dispatch)
    }
    pub fn cancel(&mut self, owner: &OfflineOwner, now: u64) -> Result<VisualDispatch> {
        self.owner(owner)?;
        // Cancellation is admitted even if the active deadline just expired.
        self.lifecycle
            .poll(now)
            .or_else(|e| if e == "DEADLINE" { Ok(()) } else { Err(e) })?;
        if !matches!(
            self.state(),
            State::Ready | State::Active | State::Hidden | State::Failed
        ) {
            return Err("LIFECYCLE");
        }
        let sequence = self.next()?;
        let dispatch = self.admit(json!({"version":1,"seq":sequence,"kind":"cancel"}), now)?;
        if self.state() != State::Failed {
            self.lifecycle.hide_or_cancel()?;
        }
        Ok(dispatch)
    }
    pub fn resume(&mut self, owner: &OfflineOwner, now: u64) -> Result<VisualDispatch> {
        self.owner(owner)?;
        self.lifecycle.poll(now)?;
        if self.state() != State::Hidden {
            return Err("LIFECYCLE");
        }
        let sequence = self.next()?;
        let dispatch = self.admit(json!({"version":1,"seq":sequence,"kind":"resume"}), now)?;
        self.lifecycle.resume()?;
        Ok(dispatch)
    }
    /// Complete only the visual lifecycle. The caller must still await independent
    /// paint and libobs-consumption receipts for any native operation.
    pub fn visual_complete(
        &mut self,
        owner: &OfflineOwner,
        identity: Identity,
        sequence: u64,
        now: u64,
    ) -> Result<()> {
        self.owner(owner)?;
        self.lifecycle.complete(identity, sequence, now)
    }
    /// Return channel is strict and bounded. Free-form error strings are rejected.
    /// An ACK cannot advance lifecycle or Production revision.
    pub fn acknowledge(&mut self, owner: &OfflineOwner, data: &[u8]) -> Result<Observation> {
        self.owner(owner)?;
        let v = strict_json(data, 512)?;
        let obj = v.as_object().ok_or("ACK_SCHEMA")?;
        let keys = [
            "protocol",
            "instance",
            "generation",
            "kind",
            "seq",
            "accepted",
        ];
        if obj.len() != keys.len()
            || keys.iter().any(|k| !obj.contains_key(*k))
            || v["protocol"] != 1
            || v["kind"] != "visual_ack"
        {
            return Err("ACK_SCHEMA");
        }
        if v["instance"].as_u64() != Some(self.identity().instance)
            || v["generation"].as_u64() != Some(self.identity().generation)
        {
            return Err("STALE_GENERATION");
        }
        let sequence = v["seq"]
            .as_u64()
            .filter(|n| *n > self.last_ack && *n == self.sequence)
            .ok_or("STALE_ACK")?;
        let accepted = v["accepted"].as_bool().ok_or("ACK_SCHEMA")?;
        self.last_ack = sequence;
        if self.property_sequence == Some(sequence) {
            self.properties_acknowledged = accepted;
        }
        if !accepted {
            self.lifecycle.crash();
        }
        Ok(Observation::RendererAcknowledged { sequence, accepted })
    }
    pub fn dispose(&mut self, owner: &OfflineOwner, now: u64) -> Result<VisualDispatch> {
        self.owner(owner)?;
        let sequence = self.next()?;
        let dispatch = self.admit(json!({"version":1,"seq":sequence,"kind":"dispose"}), now)?;
        self.lifecycle.close(true, now)?;
        self.revoked = true;
        Ok(dispatch)
    }
    /// Native supervisor owns tree reaping. This adapter never mints a proof of
    /// reaping from JS. A restart requires a newly reviewed binding/generation.
    pub fn revoke(&mut self) {
        self.revoked = true;
        self.lifecycle.crash();
    }
    pub fn poll(&mut self, now: u64) -> Result<()> {
        self.lifecycle.poll(now)
    }
}

/// Independent receiver-side validation; no owner authority is encoded in JSON.
pub fn inspect_admitted_visual(gate: &mut Gate, data: &[u8], now: u64) -> Result<Visual> {
    gate.accept(data, now)
}
