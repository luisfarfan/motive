//! State machine only. The native adapter must execute actions and acknowledge close.
use crate::{Identity, Result};

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum State {
    Created,
    Starting,
    Ready,
    Active,
    Hidden,
    Closing,
    Suspended,
    Disposed,
    Failed,
}

#[derive(Debug)]
pub struct Lifecycle {
    identity: Identity,
    state: State,
    last_now: u64,
    deadline: Option<u64>,
    active_sequence: Option<u64>,
    dispose_on_close: bool,
}

impl Lifecycle {
    pub fn new(identity: Identity) -> Self {
        Self {
            identity,
            state: State::Created,
            last_now: 0,
            deadline: None,
            active_sequence: None,
            dispose_on_close: false,
        }
    }
    pub fn identity(&self) -> Identity {
        self.identity
    }
    pub fn state(&self) -> State {
        self.state
    }
    fn clock(&mut self, now: u64) -> Result<()> {
        if now < self.last_now {
            return Err("CLOCK_REGRESSION");
        }
        self.last_now = now;
        Ok(())
    }
    fn timed(&mut self, now: u64, duration: u64, next: State) -> Result<()> {
        if duration == 0 || duration > 30_000 {
            return Err("TIMEOUT_RANGE");
        }
        let deadline = now.checked_add(duration).ok_or("TIME_OVERFLOW")?;
        self.clock(now)?;
        self.deadline = Some(deadline);
        self.state = next;
        Ok(())
    }
    pub fn check_identity(&self, identity: Identity) -> Result<()> {
        if identity != self.identity {
            return Err("STALE_GENERATION");
        }
        Ok(())
    }
    pub fn start(&mut self, now: u64) -> Result<()> {
        if self.state != State::Created {
            return Err("LIFECYCLE");
        }
        self.timed(now, 5_000, State::Starting)
    }
    pub fn ready(&mut self, identity: Identity, now: u64) -> Result<()> {
        self.check_identity(identity)?;
        self.poll(now)?;
        if self.state != State::Starting {
            return Err("LIFECYCLE");
        }
        self.state = State::Ready;
        self.deadline = None;
        Ok(())
    }
    pub fn begin(&mut self, sequence: u64, now: u64, max_active_ms: u64) -> Result<()> {
        self.poll(now)?;
        if self.state != State::Ready || sequence == 0 {
            return Err("NOT_READY");
        }
        self.timed(now, max_active_ms, State::Active)?;
        self.active_sequence = Some(sequence);
        Ok(())
    }
    pub fn complete(&mut self, identity: Identity, sequence: u64, now: u64) -> Result<()> {
        self.check_identity(identity)?;
        self.poll(now)?;
        if self.state != State::Active || self.active_sequence != Some(sequence) {
            return Err("STALE_COMPLETION");
        }
        self.state = State::Ready;
        self.deadline = None;
        self.active_sequence = None;
        Ok(())
    }
    pub fn hide_or_cancel(&mut self) -> Result<()> {
        if !matches!(self.state, State::Ready | State::Active | State::Hidden) {
            return Err("LIFECYCLE");
        }
        self.state = State::Hidden;
        self.deadline = None;
        self.active_sequence = None;
        Ok(())
    }
    pub fn resume(&mut self) -> Result<()> {
        if self.state != State::Hidden {
            return Err("LIFECYCLE");
        }
        self.state = State::Ready;
        Ok(())
    }
    /// Caller revokes channels and frames immediately; final callback is separate.
    pub fn close(&mut self, dispose: bool, now: u64) -> Result<()> {
        if matches!(
            self.state,
            State::Closing | State::Disposed | State::Suspended
        ) {
            return Err("LIFECYCLE");
        }
        self.timed(now, 5_000, State::Closing)?;
        self.active_sequence = None;
        // A retry after a close timeout cannot downgrade terminal disposal.
        self.dispose_on_close |= dispose;
        Ok(())
    }
    pub fn closed(&mut self, identity: Identity, now: u64) -> Result<()> {
        self.check_identity(identity)?;
        self.poll(now)?;
        if self.state != State::Closing {
            return Err("LIFECYCLE");
        }
        self.state = if self.dispose_on_close {
            State::Disposed
        } else {
            State::Suspended
        };
        self.deadline = None;
        Ok(())
    }
    pub fn crash(&mut self) {
        if self.state != State::Disposed {
            self.state = State::Failed;
            self.deadline = None;
            self.active_sequence = None;
        }
    }
    /// The external supervisor must reap the previous tree before this operation.
    /// A boolean supplied by a renderer is never sufficient proof of cleanup.
    pub fn restart_after_reap(&mut self) -> Result<Identity> {
        if !matches!(self.state, State::Failed | State::Suspended) || self.dispose_on_close {
            return Err("LIFECYCLE");
        }
        self.identity.generation = self
            .identity
            .generation
            .checked_add(1)
            .ok_or("GENERATION_OVERFLOW")?;
        self.state = State::Created;
        self.deadline = None;
        self.active_sequence = None;
        Ok(self.identity)
    }
    pub fn poll(&mut self, now: u64) -> Result<()> {
        self.clock(now)?;
        if self.deadline.is_some_and(|deadline| now >= deadline) {
            self.crash();
            return Err("DEADLINE");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ready() -> Lifecycle {
        let mut l = Lifecycle::new(Identity::new(1, 1).unwrap());
        l.start(0).unwrap();
        l.ready(l.identity(), 1).unwrap();
        l
    }
    #[test]
    fn completion_cannot_revive_cancelled_event() {
        let mut l = ready();
        l.begin(1, 2, 1000).unwrap();
        l.hide_or_cancel().unwrap();
        assert_eq!(l.complete(l.identity(), 1, 3), Err("STALE_COMPLETION"));
        l.resume().unwrap();
        l.begin(2, 4, 1000).unwrap();
        assert_eq!(l.complete(l.identity(), 1, 5), Err("STALE_COMPLETION"));
        l.complete(l.identity(), 2, 6).unwrap();
        assert_eq!(l.state(), State::Ready);
    }
    #[test]
    fn close_ack_and_restart_generation() {
        let mut l = ready();
        let old = l.identity();
        l.close(false, 2).unwrap();
        assert_eq!(l.restart_after_reap(), Err("LIFECYCLE"));
        l.closed(old, 3).unwrap();
        let new = l.restart_after_reap().unwrap();
        assert_eq!(new.generation, 2);
        l.start(4).unwrap();
        assert_eq!(l.ready(old, 5), Err("STALE_GENERATION"));
        l.ready(new, 5).unwrap();
    }
    #[test]
    fn timeouts_fail_closed_and_dispose_is_terminal() {
        let mut l = ready();
        l.begin(1, 2, 1000).unwrap();
        assert_eq!(l.poll(1002), Err("DEADLINE"));
        assert_eq!(l.state(), State::Failed);
        assert_eq!(l.resume(), Err("LIFECYCLE"));
        l.close(true, 1003).unwrap();
        l.closed(l.identity(), 1004).unwrap();
        l.crash();
        assert_eq!(l.state(), State::Disposed);
        assert_eq!(l.restart_after_reap(), Err("LIFECYCLE"));
    }
    #[test]
    fn failed_disposal_must_not_restart_and_time_never_rewinds() {
        let mut l = ready();
        assert_eq!(l.poll(0), Err("CLOCK_REGRESSION"));
        l.close(true, 2).unwrap();
        assert_eq!(l.poll(5002), Err("DEADLINE"));
        assert_eq!(l.restart_after_reap(), Err("LIFECYCLE"));
        l.close(false, 5003).unwrap();
        l.closed(l.identity(), 5004).unwrap();
        assert_eq!(l.state(), State::Disposed);
        assert_eq!(l.restart_after_reap(), Err("LIFECYCLE"));
    }
}
