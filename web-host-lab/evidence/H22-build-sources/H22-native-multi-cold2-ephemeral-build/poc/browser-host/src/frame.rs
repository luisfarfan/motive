//! Complete CPU frames, never CEF-owned pointers; one pending + one leased frame.
use crate::{Identity, Result};
use std::{
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    time::Instant,
};

pub const MAX_DIMENSION: u32 = 1920;
pub const MAX_BYTES: usize = 1920 * 1080 * 4;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Viewport {
    pub width: u32,
    pub height: u32,
    pub epoch: u64,
}
impl Viewport {
    pub fn bytes(self) -> Result<usize> {
        let size = (self.width as usize)
            .checked_mul(self.height as usize)
            .and_then(|v| v.checked_mul(4))
            .ok_or("FRAME_SIZE")?;
        if self.width == 0
            || self.height == 0
            || self.width > MAX_DIMENSION
            || self.height > MAX_DIMENSION
            || size > MAX_BYTES
            || self.epoch == 0
        {
            return Err("FRAME_SIZE");
        }
        Ok(size)
    }
}
#[derive(Debug, Clone, Copy)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}
impl Rect {
    fn valid(self, v: Viewport) -> bool {
        self.width > 0
            && self.height > 0
            && self.x.checked_add(self.width).is_some_and(|x| x <= v.width)
            && self
                .y
                .checked_add(self.height)
                .is_some_and(|y| y <= v.height)
    }
}
#[derive(Debug)]
pub struct Frame {
    pub identity: Identity,
    pub viewport: Viewport,
    pub index: u64,
    /// Monotonic observation nanoseconds. NEVER audiovisual PTS.
    pub observed_ns: u64,
    pub stride: u32,
    pub dirty: Vec<Rect>,
    pixels: Vec<u8>,
}
impl Frame {
    pub fn pixels(&self) -> &[u8] {
        &self.pixels
    }
}

/// Counters are cumulative for one immutable identity/viewport mailbox.
/// `paints` counts accepted complete copies, not rejected callback attempts.
/// `acquired` counts a transition, not a terminal outcome. `coalesced` means
/// replacement of one pending paint by a later complete paint (one category).
/// Exact conservation at every snapshot:
/// paints = pending + leased + coalesced + stale + consumed +
///          released_unconsumed + invalidated_close + revoked_generation.
/// `retained_leases` includes invalidated/completed leases whose bytes must remain
/// alive until release; it is intentionally distinct from unclassified `leased`.
#[derive(Debug, Default, Clone, Copy)]
pub struct Stats {
    pub paints: u64,
    pub coalesced: u64,
    pub acquired: u64,
    pub stale: u64,
    pub pending: u64,
    pub leased: u64,
    pub consumed: u64,
    pub released_unconsumed: u64,
    pub invalidated_close: u64,
    pub revoked_generation: u64,
    pub retained_leases: u64,
    pub retained_bytes: u64,
    pub copied_bytes: u64,
    /// Wall duration of extend_from_slice into already reserved capacity. Includes
    /// timing overhead and memory faults; not an isolated libc memcpy benchmark.
    pub copy_ns: u64,
    pub publish_busy: u64,
    pub acquire_busy: u64,
    pub consumer_busy: u64,
}
impl Stats {
    pub fn is_conserved(self) -> bool {
        self.paints
            == self.pending
                + self.leased
                + self.coalesced
                + self.stale
                + self.consumed
                + self.released_unconsumed
                + self.invalidated_close
                + self.revoked_generation
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Revocation {
    Close,
    Generation,
}
#[derive(Clone, Copy)]
enum Outcome {
    Consumed,
    Revoked,
}
struct LeaseRecord {
    index: u64,
    bytes: u64,
    outcome: Option<Outcome>,
}
struct Inner {
    identity: Identity,
    viewport: Viewport,
    latest: Option<Frame>,
    leased: Option<LeaseRecord>,
    last_observed: u64,
    closed: bool,
    stats: Stats,
}
struct Shared {
    inner: Mutex<Inner>,
    publish_busy: AtomicU64,
    acquire_busy: AtomicU64,
}
pub struct Mailbox(Arc<Shared>);
pub struct Lease {
    frame: Frame,
    owner: Arc<Shared>,
}
impl Lease {
    pub fn frame(&self) -> &Frame {
        &self.frame
    }
    /// Revocation is independent of byte lifetime. An old lease must never be
    /// uploaded after its generation/viewport has been revoked.
    pub fn is_valid(&self) -> bool {
        self.owner.inner.lock().is_ok_and(|inner| {
            !inner.closed
                && inner.leased.as_ref().is_some_and(|record| {
                    record.index == self.frame.index
                        && !matches!(record.outcome, Some(Outcome::Revoked))
                })
        })
    }
    /// Called by the sink only after successful use. Acquisition or release alone
    /// does not prove consumption. Returns false on duplicate completion/revocation.
    pub fn mark_consumed(&self) -> bool {
        let Ok(mut inner) = self.owner.inner.lock() else {
            return false;
        };
        if inner.closed {
            return false;
        }
        let Some(record) = inner.leased.as_mut() else {
            return false;
        };
        if record.index != self.frame.index || record.outcome.is_some() {
            return false;
        }
        record.outcome = Some(Outcome::Consumed);
        inner.stats.consumed += 1;
        true
    }
}
impl Drop for Lease {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.owner.inner.lock()
            && inner
                .leased
                .as_ref()
                .is_some_and(|record| record.index == self.frame.index)
            && let Some(record) = inner.leased.take()
            && record.outcome.is_none()
        {
            inner.stats.released_unconsumed += 1;
        }
    }
}
impl Mailbox {
    pub fn new(identity: Identity, viewport: Viewport) -> Result<Self> {
        Identity::new(identity.instance, identity.generation)?;
        viewport.bytes()?;
        Ok(Self(Arc::new(Shared {
            inner: Mutex::new(Inner {
                identity,
                viewport,
                latest: None,
                leased: None,
                last_observed: 0,
                closed: false,
                stats: Stats::default(),
            }),
            publish_busy: AtomicU64::new(0),
            acquire_busy: AtomicU64::new(0),
        })))
    }
    /// Call within OnPaint with a slice of the documented complete image.
    /// Never waits for the consumer: if the metadata mutex is busy, drop the paint.
    pub fn publish(
        &self,
        identity: Identity,
        viewport: Viewport,
        observed_ns: u64,
        pixels: &[u8],
        dirty: &[Rect],
    ) -> Result<u64> {
        let required = viewport.bytes()?;
        if pixels.len() != required || dirty.len() > 128 || dirty.iter().any(|r| !r.valid(viewport))
        {
            return Err("FRAME_LAYOUT");
        }
        let mut inner = self.0.inner.try_lock().map_err(|_| {
            self.0.publish_busy.fetch_add(1, Ordering::Relaxed);
            "FRAME_BUSY"
        })?;
        if inner.closed {
            return Err("FRAME_CLOSED");
        }
        if identity != inner.identity || viewport != inner.viewport {
            return Err("STALE_FRAME");
        }
        if observed_ns < inner.last_observed {
            return Err("CLOCK_REGRESSION");
        }
        let index = inner
            .stats
            .paints
            .checked_add(1)
            .ok_or("FRAME_INDEX_OVERFLOW")?;
        // One owned callback copy plus pending and lease: at most three complete
        // frames transiently. Never retain callback memory or coalesce deltas.
        let mut owned = Vec::new();
        owned
            .try_reserve_exact(required)
            .map_err(|_| "FRAME_ALLOCATION")?;
        let start = Instant::now();
        owned.extend_from_slice(pixels);
        let copy_ns = start.elapsed().as_nanos().min(u128::from(u64::MAX)) as u64;
        let frame = Frame {
            identity,
            viewport,
            index,
            observed_ns,
            stride: viewport.width * 4,
            dirty: dirty.to_vec(),
            pixels: owned,
        };
        if inner.latest.replace(frame).is_some() {
            inner.stats.coalesced += 1;
        }
        inner.last_observed = observed_ns;
        inner.stats.paints = index;
        inner.stats.copied_bytes = inner.stats.copied_bytes.saturating_add(required as u64);
        inner.stats.copy_ns = inner.stats.copy_ns.saturating_add(copy_ns);
        Ok(index)
    }
    pub fn acquire(&self, now_ns: u64, max_age_ns: u64) -> Result<Option<Lease>> {
        let mut inner = self.0.inner.try_lock().map_err(|_| {
            self.0.acquire_busy.fetch_add(1, Ordering::Relaxed);
            "FRAME_BUSY"
        })?;
        if inner.closed {
            return Err("FRAME_CLOSED");
        }
        if inner.leased.is_some() {
            inner.stats.consumer_busy += 1;
            return Err("CONSUMER_BUSY");
        }
        if now_ns < inner.last_observed {
            return Err("CLOCK_REGRESSION");
        }
        let Some(frame) = inner.latest.take() else {
            return Ok(None);
        };
        if now_ns - frame.observed_ns > max_age_ns {
            inner.stats.stale += 1;
            return Ok(None);
        }
        inner.leased = Some(LeaseRecord {
            index: frame.index,
            bytes: frame.pixels.len() as u64,
            outcome: None,
        });
        inner.stats.acquired += 1;
        Ok(Some(Lease {
            frame,
            owner: self.0.clone(),
        }))
    }
    /// Legacy close invalidation. Use Generation for epoch/restart replacement.
    pub fn invalidate(&self) -> Result<()> {
        self.invalidate_reason(Revocation::Close)
    }
    /// Idempotently classify every still-pending/unclassified lease. Retained
    /// lease bytes survive until release, but no longer have visual authority.
    pub fn invalidate_reason(&self, reason: Revocation) -> Result<()> {
        let mut inner = self.0.inner.lock().map_err(|_| "FRAME_POISON")?;
        if inner.closed {
            return Ok(());
        }
        inner.closed = true;
        let mut revoked = u64::from(inner.latest.take().is_some());
        if let Some(record) = inner.leased.as_mut()
            && record.outcome.is_none()
        {
            record.outcome = Some(Outcome::Revoked);
            revoked += 1;
        }
        match reason {
            Revocation::Close => inner.stats.invalidated_close += revoked,
            Revocation::Generation => inner.stats.revoked_generation += revoked,
        }
        Ok(())
    }
    pub fn stats(&self) -> Result<Stats> {
        let inner = self.0.inner.lock().map_err(|_| "FRAME_POISON")?;
        let mut stats = inner.stats;
        stats.pending = u64::from(inner.latest.is_some());
        stats.leased = u64::from(inner.leased.as_ref().is_some_and(|l| l.outcome.is_none()));
        stats.retained_leases = u64::from(inner.leased.is_some());
        stats.retained_bytes = inner.latest.as_ref().map_or(0, |f| f.pixels.len() as u64)
            + inner.leased.as_ref().map_or(0, |l| l.bytes);
        stats.publish_busy = self.0.publish_busy.load(Ordering::Relaxed);
        stats.acquire_busy = self.0.acquire_busy.load(Ordering::Relaxed);
        Ok(stats)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn setup() -> (Identity, Viewport, Mailbox) {
        let id = Identity::new(1, 1).unwrap();
        let v = Viewport {
            width: 2,
            height: 1,
            epoch: 1,
        };
        (id, v, Mailbox::new(id, v).unwrap())
    }
    #[test]
    fn owned_bytes_coalesce_and_consumer_cannot_hoard() {
        let (id, v, m) = setup();
        let mut data = vec![0, 0, 128, 128, 0, 0, 0, 0];
        m.publish(id, v, 1, &data, &[]).unwrap();
        data.fill(255);
        let lease = m.acquire(1, 100).unwrap().unwrap();
        assert_eq!(lease.frame().pixels(), &[0, 0, 128, 128, 0, 0, 0, 0]);
        for now in 2..100 {
            m.publish(id, v, now, &data, &[]).unwrap();
        }
        assert!(matches!(m.acquire(100, 100), Err("CONSUMER_BUSY")));
        drop(lease);
        let next = m.acquire(100, 100).unwrap().unwrap();
        assert_eq!(next.frame().index, 99);
        assert_eq!(m.stats().unwrap().coalesced, 97);
    }
    #[test]
    fn stale_resize_generation_and_future_timestamp_rejected() {
        let (id, v, m) = setup();
        let data = [0; 8];
        assert_eq!(
            m.publish(Identity::new(1, 2).unwrap(), v, 1, &data, &[]),
            Err("STALE_FRAME")
        );
        let resized = Viewport { epoch: 2, ..v };
        assert_eq!(m.publish(id, resized, 1, &data, &[]), Err("STALE_FRAME"));
        m.publish(id, v, 10, &data, &[]).unwrap();
        assert!(matches!(m.acquire(9, 1), Err("CLOCK_REGRESSION")));
        assert!(m.acquire(20, 9).unwrap().is_none());
        assert_eq!(m.stats().unwrap().stale, 1);
        m.invalidate().unwrap();
        assert_eq!(m.publish(id, v, 21, &data, &[]), Err("FRAME_CLOSED"));
    }
    #[test]
    fn validates_bounds_without_allocating_from_untrusted_dimensions() {
        let (id, v, m) = setup();
        assert_eq!(
            Viewport {
                width: u32::MAX,
                ..v
            }
            .bytes(),
            Err("FRAME_SIZE")
        );
        assert_eq!(m.publish(id, v, 1, &[0; 7], &[]), Err("FRAME_LAYOUT"));
        let bad = Rect {
            x: u32::MAX,
            y: 0,
            width: 2,
            height: 1,
        };
        assert_eq!(m.publish(id, v, 1, &[0; 8], &[bad]), Err("FRAME_LAYOUT"));
        assert_eq!(
            m.publish(
                id,
                v,
                1,
                &[0; 8],
                &[Rect {
                    x: 0,
                    y: 0,
                    width: 1,
                    height: 1
                }; 129]
            ),
            Err("FRAME_LAYOUT")
        );
    }
    #[test]
    fn coalescing_retains_full_image_even_when_dirty_is_small() {
        let (id, v, m) = setup();
        m.publish(id, v, 1, &[10; 8], &[]).unwrap();
        m.publish(
            id,
            v,
            2,
            &[20, 20, 20, 255, 10, 10, 10, 255],
            &[Rect {
                x: 0,
                y: 0,
                width: 1,
                height: 1,
            }],
        )
        .unwrap();
        assert_eq!(
            m.acquire(2, 0).unwrap().unwrap().frame().pixels(),
            &[20, 20, 20, 255, 10, 10, 10, 255]
        );
    }
    #[test]
    fn exact_terminal_accounting_tracks_consumption_release_and_stale() {
        let (id, v, m) = setup();
        for t in 1..=3 {
            m.publish(id, v, t, &[0; 8], &[]).unwrap();
        }
        let lease = m.acquire(3, 0).unwrap().unwrap();
        let s = m.stats().unwrap();
        assert_eq!((s.paints, s.coalesced, s.acquired, s.leased), (3, 2, 1, 1));
        assert_eq!(s.retained_bytes, 8);
        assert!(s.is_conserved());
        assert!(lease.mark_consumed());
        assert!(!lease.mark_consumed());
        assert!(m.stats().unwrap().is_conserved());
        drop(lease);
        m.publish(id, v, 4, &[0; 8], &[]).unwrap();
        drop(m.acquire(4, 0).unwrap().unwrap());
        m.publish(id, v, 5, &[0; 8], &[]).unwrap();
        assert!(m.acquire(6, 0).unwrap().is_none());
        let s = m.stats().unwrap();
        assert_eq!((s.consumed, s.released_unconsumed, s.stale), (1, 1, 1));
        assert_eq!(
            (s.pending, s.leased, s.retained_leases, s.retained_bytes),
            (0, 0, 0, 0)
        );
        assert_eq!(s.copied_bytes, 5 * 8);
        assert!(s.is_conserved());
    }
    #[test]
    fn revocation_classifies_pending_and_leased_once_without_freeing_borrowed_bytes() {
        for reason in [Revocation::Close, Revocation::Generation] {
            let (id, v, m) = setup();
            m.publish(id, v, 1, &[128; 8], &[]).unwrap();
            let lease = m.acquire(1, 0).unwrap().unwrap();
            m.publish(id, v, 2, &[255; 8], &[]).unwrap();
            m.invalidate_reason(reason).unwrap();
            m.invalidate().unwrap();
            let s = m.stats().unwrap();
            assert_eq!(
                s.invalidated_close,
                if reason == Revocation::Close { 2 } else { 0 }
            );
            assert_eq!(
                s.revoked_generation,
                if reason == Revocation::Generation {
                    2
                } else {
                    0
                }
            );
            assert_eq!((s.leased, s.retained_leases, s.retained_bytes), (0, 1, 8));
            assert!(s.is_conserved());
            assert!(!lease.is_valid());
            assert!(!lease.mark_consumed());
            assert_eq!(lease.frame().pixels(), &[128; 8]);
            drop(lease);
            let s = m.stats().unwrap();
            assert_eq!(
                (s.retained_bytes, s.retained_leases, s.released_unconsumed),
                (0, 0, 0)
            );
            assert!(s.is_conserved());
        }
    }
    #[test]
    fn completed_lease_is_not_reclassified_by_close() {
        let (id, v, m) = setup();
        m.publish(id, v, 1, &[0; 8], &[]).unwrap();
        let lease = m.acquire(1, 0).unwrap().unwrap();
        assert!(lease.mark_consumed());
        m.invalidate().unwrap();
        assert!(!lease.is_valid());
        drop(lease);
        let s = m.stats().unwrap();
        assert_eq!((s.consumed, s.invalidated_close), (1, 0));
        assert!(s.is_conserved());
    }
    #[test]
    fn independent_instance_and_resize_mailboxes_reject_cross_routing() {
        let (id, v, old) = setup();
        old.publish(id, v, 1, &[42; 8], &[]).unwrap();
        let lease = old.acquire(1, 0).unwrap().unwrap();
        old.invalidate_reason(Revocation::Generation).unwrap();
        let resized = Viewport {
            width: 1,
            height: 2,
            epoch: 2,
        };
        let new = Mailbox::new(id, resized).unwrap();
        let other = Identity::new(2, 1).unwrap();
        assert_eq!(
            new.publish(other, resized, 2, &[0; 8], &[]),
            Err("STALE_FRAME")
        );
        assert_eq!(new.publish(id, v, 2, &[0; 8], &[]), Err("STALE_FRAME"));
        assert_eq!(old.publish(id, v, 2, &[0; 8], &[]), Err("FRAME_CLOSED"));
        new.publish(id, resized, 2, &[7; 8], &[]).unwrap();
        assert_eq!(
            new.acquire(2, 0).unwrap().unwrap().frame().pixels(),
            &[7; 8]
        );
        assert_eq!(lease.frame().pixels(), &[42; 8]);
        assert!(!lease.is_valid());
    }
    #[test]
    fn contention_counters_never_manufacture_accepted_paints() {
        let (id, v, m) = setup();
        let guard = m.0.inner.lock().unwrap();
        assert_eq!(m.publish(id, v, 1, &[0; 8], &[]), Err("FRAME_BUSY"));
        assert!(matches!(m.acquire(1, 1), Err("FRAME_BUSY")));
        drop(guard);
        let s = m.stats().unwrap();
        assert_eq!((s.paints, s.publish_busy, s.acquire_busy), (0, 1, 1));
        assert!(s.is_conserved());
    }
}
