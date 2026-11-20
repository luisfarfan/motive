//! Prepared libobs admission policy only. No texture creation, OBS calls or PTS.
//! The owner supplies aggregate visibility and health; render cannot revive a host.
use crate::{
    Identity, Result,
    frame::{Frame, Viewport},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Health {
    Ready,
    Active,
    Suspended,
    Failed,
    Revoked,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Decision {
    Upload { index: u64 },
    Repeat { index: u64 },
    Blank,
}

pub struct Admission {
    identity: Identity,
    viewport: Viewport,
    last_index: u64,
    last_observed: u64,
    max_age_ns: u64,
    static_hold: bool,
    revoked: bool,
}
impl Admission {
    pub fn new(
        identity: Identity,
        viewport: Viewport,
        max_age_ns: u64,
        static_hold: bool,
    ) -> Result<Self> {
        viewport.bytes()?;
        if max_age_ns == 0 {
            return Err("FRAME_AGE_POLICY");
        }
        Ok(Self {
            identity,
            viewport,
            max_age_ns,
            static_hold,
            last_index: 0,
            last_observed: 0,
            revoked: false,
        })
    }
    /// Source removal/restart permanently revokes this admission generation.
    pub fn revoke(&mut self) {
        self.revoked = true;
        self.last_index = 0;
    }
    /// A returned Upload borrows the caller's lease; release it only after texture
    /// upload on OBS's graphics context. Never treat observed_ns as output PTS.
    pub fn decide(
        &mut self,
        health: Health,
        visible_layer_references: usize,
        frame: Option<&Frame>,
        now_ns: u64,
    ) -> Result<Decision> {
        if self.revoked {
            return Ok(Decision::Blank);
        }
        if matches!(health, Health::Failed | Health::Revoked | Health::Suspended) {
            self.revoke();
            return Ok(Decision::Blank);
        }
        if visible_layer_references == 0 {
            return Ok(Decision::Blank);
        }
        if let Some(f) = frame {
            if f.identity != self.identity || f.viewport != self.viewport {
                return Err("STALE_FRAME");
            }
            if f.index <= self.last_index {
                return Err("FRAME_SEQUENCE");
            }
            if f.observed_ns > now_ns || f.observed_ns < self.last_observed {
                return Err("CLOCK_REGRESSION");
            }
            if now_ns - f.observed_ns > self.max_age_ns {
                return Ok(Decision::Blank);
            }
            self.last_index = f.index;
            self.last_observed = f.observed_ns;
            return Ok(Decision::Upload { index: f.index });
        }
        if now_ns < self.last_observed {
            return Err("CLOCK_REGRESSION");
        }
        if self.last_index != 0
            && (self.static_hold || now_ns - self.last_observed <= self.max_age_ns)
        {
            Ok(Decision::Repeat {
                index: self.last_index,
            })
        } else {
            Ok(Decision::Blank)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::frame::Mailbox;
    #[test]
    fn aggregate_visibility_age_and_revocation_do_not_create_a_clock() {
        let id = Identity::new(1, 1).unwrap();
        let v = Viewport {
            width: 1,
            height: 1,
            epoch: 1,
        };
        let m = Mailbox::new(id, v).unwrap();
        m.publish(id, v, 10, &[0; 4], &[]).unwrap();
        let lease = m.acquire(10, 10).unwrap().unwrap();
        let mut a = Admission::new(id, v, 10, false).unwrap();
        assert_eq!(
            a.decide(Health::Active, 2, Some(lease.frame()), 10),
            Ok(Decision::Upload { index: 1 })
        );
        assert_eq!(
            a.decide(Health::Active, 1, None, 11),
            Ok(Decision::Repeat { index: 1 })
        );
        assert_eq!(a.decide(Health::Active, 0, None, 12), Ok(Decision::Blank));
        assert_eq!(a.decide(Health::Active, 1, None, 21), Ok(Decision::Blank));
        assert_eq!(a.decide(Health::Failed, 1, None, 22), Ok(Decision::Blank));
        assert_eq!(
            a.decide(Health::Active, 1, Some(lease.frame()), 23),
            Ok(Decision::Blank)
        );
    }
    #[test]
    fn wrong_generation_epoch_repeated_index_and_future_frame_rejected() {
        let id = Identity::new(1, 1).unwrap();
        let v = Viewport {
            width: 1,
            height: 1,
            epoch: 1,
        };
        let m = Mailbox::new(id, v).unwrap();
        m.publish(id, v, 10, &[0; 4], &[]).unwrap();
        let lease = m.acquire(10, 10).unwrap().unwrap();
        let mut a = Admission::new(Identity::new(1, 2).unwrap(), v, 10, true).unwrap();
        assert_eq!(
            a.decide(Health::Active, 1, Some(lease.frame()), 10),
            Err("STALE_FRAME")
        );
        let mut a = Admission::new(id, Viewport { epoch: 2, ..v }, 10, true).unwrap();
        assert_eq!(
            a.decide(Health::Active, 1, Some(lease.frame()), 10),
            Err("STALE_FRAME")
        );
        let mut a = Admission::new(id, v, 10, true).unwrap();
        assert_eq!(
            a.decide(Health::Active, 1, Some(lease.frame()), 9),
            Err("CLOCK_REGRESSION")
        );
        a.decide(Health::Active, 1, Some(lease.frame()), 10)
            .unwrap();
        assert_eq!(
            a.decide(Health::Active, 1, Some(lease.frame()), 10),
            Err("FRAME_SEQUENCE")
        );
        assert_eq!(
            a.decide(Health::Ready, 1, None, 10000),
            Ok(Decision::Repeat { index: 1 })
        );
    }
}
