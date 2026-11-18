//! Complete CPU frames, never CEF-owned pointers; one pending + one leased frame.
use crate::{Identity, Result};
use std::sync::{Arc, Mutex};

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

#[derive(Debug, Default, Clone, Copy)]
pub struct Stats {
    pub paints: u64,
    pub coalesced: u64,
    pub acquired: u64,
    pub stale: u64,
}
struct Inner {
    identity: Identity,
    viewport: Viewport,
    latest: Option<Frame>,
    leased: bool,
    last_observed: u64,
    closed: bool,
    stats: Stats,
}
pub struct Mailbox(Arc<Mutex<Inner>>);
pub struct Lease {
    frame: Frame,
    owner: Arc<Mutex<Inner>>,
}
impl Lease {
    pub fn frame(&self) -> &Frame {
        &self.frame
    }
}
impl Drop for Lease {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.owner.lock() {
            inner.leased = false;
        }
    }
}
impl Mailbox {
    pub fn new(identity: Identity, viewport: Viewport) -> Result<Self> {
        viewport.bytes()?;
        Ok(Self(Arc::new(Mutex::new(Inner {
            identity,
            viewport,
            latest: None,
            leased: false,
            last_observed: 0,
            closed: false,
            stats: Stats::default(),
        }))))
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
        let mut inner = self.0.try_lock().map_err(|_| "FRAME_BUSY")?;
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
        // Allocate the new buffer before dropping the old: at most three buffers
        // transiently (one callback copy, pending, lease), never an unbounded queue.
        let mut owned = Vec::new();
        owned
            .try_reserve_exact(required)
            .map_err(|_| "FRAME_ALLOCATION")?;
        owned.extend_from_slice(pixels);
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
        Ok(index)
    }
    pub fn acquire(&self, now_ns: u64, max_age_ns: u64) -> Result<Option<Lease>> {
        let mut inner = self.0.try_lock().map_err(|_| "FRAME_BUSY")?;
        if inner.closed {
            return Err("FRAME_CLOSED");
        }
        if inner.leased {
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
        inner.leased = true;
        inner.stats.acquired += 1;
        Ok(Some(Lease {
            frame,
            owner: self.0.clone(),
        }))
    }
    /// Consumer must also validate its leased frame identity before drawing it.
    pub fn invalidate(&self) -> Result<()> {
        let mut inner = self.0.lock().map_err(|_| "FRAME_POISON")?;
        inner.closed = true;
        inner.latest = None;
        Ok(())
    }
    pub fn stats(&self) -> Result<Stats> {
        Ok(self.0.lock().map_err(|_| "FRAME_POISON")?.stats)
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
}
