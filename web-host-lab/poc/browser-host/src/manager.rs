//! H19 owner-side integration contract. Compiles without CEF or libobs.
//!
//! This is a bounded registry for already-reviewed, owned laboratory fixtures;
//! it is not an importer, OS supervisor, trust grant or Production API. H20 must
//! bind observations to its authenticated native channel and execute lifecycle
//! actions asynchronously. Existing IPC Gate/creator Binding retain properties,
//! events and owner authority; this module does not duplicate their schemas.
use std::collections::{BTreeMap, BTreeSet};

use crate::{
    Identity, Result,
    adapter::{Admission, Decision, Health},
    frame::{Frame, Mailbox, Revocation, Stats, Viewport},
    lifecycle::{Lifecycle, State},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProcessIdentity {
    pub pid: u32,
    /// Supervisor-observed process start identity, never a timestamp from JS.
    pub start_token: u64,
}
impl ProcessIdentity {
    fn validate(self) -> Result<()> {
        if self.pid == 0 || self.start_token == 0 {
            return Err("PROCESS_IDENTITY");
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BrowserIdentity {
    pub host: ProcessIdentity,
    pub browser_id: u32,
    /// None means process assignment is unobserved, not independent isolation.
    pub renderer: Option<ProcessIdentity>,
}
#[derive(Clone, Debug)]
pub struct OwnedFixtureDescriptor {
    pub identity: Identity,
    pub viewport: Viewport,
    pub package_sha256: [u8; 32],
    pub inventory_sha256: [u8; 32],
    /// Native-created fresh context token; distinct contexts are not OS sandboxes.
    pub request_context: u64,
    pub max_age_ns: u64,
    pub static_hold: bool,
}
impl OwnedFixtureDescriptor {
    fn validate(&self) -> Result<()> {
        Identity::new(self.identity.instance, self.identity.generation)?;
        self.viewport.bytes()?;
        if self.request_context == 0
            || self.max_age_ns == 0
            || self.package_sha256 == [0; 32]
            || self.inventory_sha256 == [0; 32]
        {
            return Err("INSTANCE_DESCRIPTOR");
        }
        Ok(())
    }
    pub fn origin(&self) -> String {
        format!(
            "motive-asset://i{}-g{}",
            self.identity.instance, self.identity.generation
        )
    }
}
pub struct Instance {
    descriptor: OwnedFixtureDescriptor,
    lifecycle: Lifecycle,
    browser: Option<BrowserIdentity>,
    mailbox: Mailbox,
    admission: Admission,
    visible_references: usize,
    host_reaped: bool,
    dispose_requested: bool,
}
impl Instance {
    pub fn descriptor(&self) -> &OwnedFixtureDescriptor {
        &self.descriptor
    }
    pub fn state(&self) -> State {
        self.lifecycle.state()
    }
    pub fn browser(&self) -> Option<BrowserIdentity> {
        self.browser
    }
    pub fn mailbox(&self) -> &Mailbox {
        &self.mailbox
    }
    pub fn frame_stats(&self) -> Result<Stats> {
        self.mailbox.stats()
    }
}
pub struct BrowserHostManager {
    instances: BTreeMap<u64, Instance>,
    /// A caller-supplied admission bound, not a benchmark-backed capacity claim.
    limit: usize,
    generations: BTreeMap<u64, u64>,
    context_history: BTreeSet<u64>,
}
impl BrowserHostManager {
    pub fn new(limit: usize) -> Result<Self> {
        if !(1..=16).contains(&limit) {
            return Err("INSTANCE_LIMIT");
        }
        Ok(Self {
            instances: BTreeMap::new(),
            limit,
            generations: BTreeMap::new(),
            context_history: BTreeSet::new(),
        })
    }
    pub fn get(&self, identity: Identity) -> Result<&Instance> {
        let instance = self
            .instances
            .get(&identity.instance)
            .ok_or("INSTANCE_MISSING")?;
        instance.lifecycle.check_identity(identity)?;
        Ok(instance)
    }
    fn get_mut(&mut self, identity: Identity) -> Result<&mut Instance> {
        let instance = self
            .instances
            .get_mut(&identity.instance)
            .ok_or("INSTANCE_MISSING")?;
        instance.lifecycle.check_identity(identity)?;
        Ok(instance)
    }
    pub fn register_owned_fixture(
        &mut self,
        descriptor: OwnedFixtureDescriptor,
        now_ms: u64,
    ) -> Result<()> {
        descriptor.validate()?;
        if self.instances.len() >= self.limit {
            return Err("INSTANCE_LIMIT");
        }
        if self.instances.contains_key(&descriptor.identity.instance) {
            return Err("INSTANCE_EXISTS");
        }
        if self
            .generations
            .get(&descriptor.identity.instance)
            .is_some_and(|last| descriptor.identity.generation <= *last)
        {
            return Err("GENERATION_REUSED");
        }
        if self.generations.len() >= 1024
            && !self.generations.contains_key(&descriptor.identity.instance)
        {
            return Err("IDENTITY_LEDGER_LIMIT");
        }
        if self.context_history.contains(&descriptor.request_context) {
            return Err("CONTEXT_REUSED");
        }
        if self.context_history.len() >= 1024 {
            return Err("CONTEXT_LEDGER_LIMIT");
        }
        let mailbox = Mailbox::new(descriptor.identity, descriptor.viewport)?;
        let admission = Admission::new(
            descriptor.identity,
            descriptor.viewport,
            descriptor.max_age_ns,
            descriptor.static_hold,
        )?;
        let mut lifecycle = Lifecycle::new(descriptor.identity);
        lifecycle.start(now_ms)?;
        self.context_history.insert(descriptor.request_context);
        self.generations
            .insert(descriptor.identity.instance, descriptor.identity.generation);
        self.instances.insert(
            descriptor.identity.instance,
            Instance {
                descriptor,
                lifecycle,
                browser: None,
                mailbox,
                admission,
                visible_references: 0,
                host_reaped: false,
                dispose_requested: false,
            },
        );
        Ok(())
    }
    /// Observe OnAfterCreated through the trusted channel; never infer renderer
    /// independence merely because browser_id/request_context are different.
    pub fn browser_created(
        &mut self,
        identity: Identity,
        browser: BrowserIdentity,
        now_ms: u64,
    ) -> Result<()> {
        browser.host.validate()?;
        if let Some(renderer) = browser.renderer {
            renderer.validate()?;
        }
        if browser.browser_id == 0 {
            return Err("BROWSER_IDENTITY");
        }
        if self.instances.values().any(|i| {
            i.browser
                .is_some_and(|b| b.host == browser.host && b.browser_id == browser.browser_id)
        }) {
            return Err("BROWSER_REUSED");
        }
        let instance = self.get_mut(identity)?;
        instance.lifecycle.ready(identity, now_ms)?;
        instance.browser = Some(browser);
        Ok(())
    }
    /// Aggregate references across existing scene layers. A hidden layer cannot
    /// suppress a source still visible in another layer.
    pub fn set_visible_references(&mut self, identity: Identity, count: usize) -> Result<()> {
        if count > 32 {
            return Err("LAYER_LIMIT");
        }
        let instance = self.get_mut(identity)?;
        if count == 0 && matches!(instance.lifecycle.state(), State::Ready | State::Active) {
            instance.lifecycle.hide_or_cancel()?;
        } else if count != 0 && instance.lifecycle.state() == State::Hidden {
            instance.lifecycle.resume()?;
        }
        instance.visible_references = count;
        Ok(())
    }
    /// The caller supplies a lease from binary frame transport and performs any
    /// returned upload on OBS's graphics context under OBS's audiovisual clock.
    /// This function creates no texture and treats observation time only as age.
    pub fn frame_decision(
        &mut self,
        identity: Identity,
        frame: Option<&Frame>,
        now_ns: u64,
    ) -> Result<Decision> {
        let instance = self.get_mut(identity)?;
        let health = match instance.lifecycle.state() {
            State::Ready | State::Hidden => Health::Ready,
            State::Active => Health::Active,
            State::Failed => Health::Failed,
            State::Closing | State::Suspended | State::Disposed => Health::Revoked,
            State::Created | State::Starting => return Ok(Decision::Blank),
        };
        instance
            .admission
            .decide(health, instance.visible_references, frame, now_ns)
    }
    pub fn close(&mut self, identity: Identity, dispose: bool, now_ms: u64) -> Result<()> {
        let instance = self.get_mut(identity)?;
        instance.lifecycle.close(dispose, now_ms)?;
        instance.dispose_requested |= dispose;
        instance.admission.revoke();
        instance.mailbox.invalidate()?;
        Ok(())
    }
    /// External owner timer enforces the existing lifecycle deadlines. A timeout
    /// revokes admission immediately, but does not claim that native resources
    /// were released; the supervisor must still close or reap the owned host.
    pub fn poll(&mut self, now_ms: u64) -> Result<Vec<Identity>> {
        let mut failed = Vec::new();
        for instance in self.instances.values_mut() {
            match instance.lifecycle.poll(now_ms) {
                Ok(()) => {}
                Err("DEADLINE") => {
                    instance.admission.revoke();
                    instance.mailbox.invalidate_reason(Revocation::Generation)?;
                    failed.push(instance.descriptor.identity);
                }
                Err(error) => return Err(error),
            }
        }
        Ok(failed)
    }
    /// Native OnBeforeClose for this browser, not a JS ack or host-tree reap.
    pub fn browser_closed(
        &mut self,
        identity: Identity,
        browser: BrowserIdentity,
        now_ms: u64,
    ) -> Result<()> {
        let instance = self.get_mut(identity)?;
        if instance.browser != Some(browser) {
            return Err("BROWSER_IDENTITY");
        }
        instance.lifecycle.closed(identity, now_ms)?;
        instance.browser = None;
        Ok(())
    }
    /// All known members of a shared renderer fail together. Unknown assignment
    /// is conservatively affected by a failure in the same host. This does not
    /// assert that OS processes were killed or reaped.
    pub fn renderer_failed(
        &mut self,
        host: ProcessIdentity,
        renderer: Option<ProcessIdentity>,
    ) -> Result<Vec<Identity>> {
        host.validate()?;
        if let Some(renderer) = renderer {
            renderer.validate()?;
        }
        let mut affected = Vec::new();
        for instance in self.instances.values_mut() {
            if instance.browser.is_some_and(|b| {
                b.host == host
                    && (renderer.is_none() || b.renderer.is_none() || b.renderer == renderer)
            }) {
                instance.lifecycle.crash();
                instance.admission.revoke();
                instance.mailbox.invalidate_reason(Revocation::Generation)?;
                affected.push(instance.descriptor.identity);
            }
        }
        Ok(affected)
    }
    pub fn host_failed(&mut self, host: ProcessIdentity) -> Result<Vec<Identity>> {
        self.renderer_failed(host, None)
    }
    /// Called only after the external supervisor observes the exact launched
    /// host tree gone. This is a trusted owner observation, never renderer input.
    pub fn observe_host_reaped(&mut self, host: ProcessIdentity) -> Result<Vec<Identity>> {
        let affected = self.host_failed(host)?;
        for identity in &affected {
            let instance = self.get_mut(*identity)?;
            instance.browser = None;
            instance.host_reaped = true;
        }
        Ok(affected)
    }
    /// A dynamic native resize needs a proven ordering barrier. Until the caller
    /// can supply one, the compiled contract requires final browser close and a
    /// fresh generation/context. Old leases retain bytes but stay revoked.
    pub fn replace_closed(
        &mut self,
        old: Identity,
        replacement: OwnedFixtureDescriptor,
        now_ms: u64,
    ) -> Result<()> {
        replacement.validate()?;
        let previous = self.get(old)?;
        if previous.dispose_requested {
            return Err("DISPOSE_IS_TERMINAL");
        }
        if !(previous.state() == State::Suspended
            || (previous.state() == State::Failed && previous.host_reaped))
            || previous.browser.is_some()
        {
            return Err("NATIVE_CLOSE_REQUIRED");
        }
        if replacement.identity.instance != old.instance
            || replacement.identity.generation
                != old.generation.checked_add(1).ok_or("GENERATION_OVERFLOW")?
            || replacement.request_context == previous.descriptor.request_context
        {
            return Err("REPLACEMENT_IDENTITY");
        }
        if previous.mailbox.stats()?.retained_leases != 0 {
            return Err("LEASES_RETAINED");
        }
        if self.context_history.contains(&replacement.request_context) {
            return Err("CONTEXT_REUSED");
        }
        if self.context_history.len() >= 1024 {
            return Err("CONTEXT_LEDGER_LIMIT");
        }
        // Preflight construction before retiring the previous state.
        let mailbox = Mailbox::new(replacement.identity, replacement.viewport)?;
        let admission = Admission::new(
            replacement.identity,
            replacement.viewport,
            replacement.max_age_ns,
            replacement.static_hold,
        )?;
        let mut lifecycle = Lifecycle::new(replacement.identity);
        lifecycle.start(now_ms)?;
        self.context_history.insert(replacement.request_context);
        self.generations
            .insert(old.instance, replacement.identity.generation);
        self.instances.insert(
            old.instance,
            Instance {
                descriptor: replacement,
                lifecycle,
                browser: None,
                mailbox,
                admission,
                visible_references: 0,
                host_reaped: false,
                dispose_requested: false,
            },
        );
        Ok(())
    }
    pub fn remove_disposed(&mut self, identity: Identity) -> Result<Stats> {
        let instance = self.get(identity)?;
        if !(instance.state() == State::Disposed
            || (instance.state() == State::Failed
                && instance.host_reaped
                && instance.dispose_requested))
            || instance.browser.is_some()
        {
            return Err("NATIVE_CLOSE_REQUIRED");
        }
        let stats = instance.mailbox.stats()?;
        if stats.retained_leases != 0 {
            return Err("LEASES_RETAINED");
        }
        self.instances.remove(&identity.instance);
        Ok(stats)
    }
}
