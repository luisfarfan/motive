//! Trusted in-process C ABI for the existing H16 owned mailbox. Never an IPC parser.
//! Callers supply live handles and readable callback buffers; CEF pointers are
//! copied before publish returns. At most one lease, one pending and one copy.
use motive_browser_contracts::{
    Identity,
    frame::{Lease, Mailbox, Rect, Revocation, Viewport},
};
use std::{
    ptr, slice,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
};

pub struct Bridge {
    mailbox: Mailbox,
    identity: Identity,
    viewport: Viewport,
    live: Arc<AtomicBool>,
}
pub struct FrameLease {
    lease: Lease,
    live: Arc<AtomicBool>,
}
#[repr(C)]
#[derive(Default, Debug, Copy, Clone)]
pub struct Metadata {
    pub instance: u64,
    pub generation: u64,
    pub epoch: u64,
    pub index: u64,
    pub observed_ns: u64,
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub bgra8: u32,
    pub alpha_mode: u32,
    pub reserved: u32,
    pub length: u64,
}
#[repr(C)]
#[derive(Default, Debug, Copy, Clone)]
pub struct Statistics {
    pub paints: u64,
    pub coalesced: u64,
    pub acquired: u64,
    pub stale: u64,
}

/// Versioned exact terminal accounting. All fields are 64-bit host ABI integers.
/// Acquired overlaps transitions; coalesced is replacement, not a second count.
#[repr(C)]
#[derive(Default, Debug, Copy, Clone)]
pub struct StatisticsV2 {
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
    pub copy_ns: u64,
    pub publish_busy: u64,
    pub acquire_busy: u64,
    pub consumer_busy: u64,
}

#[unsafe(no_mangle)]
pub extern "C" fn motive_frames_create(
    instance: u64,
    generation: u64,
    epoch: u64,
    width: u32,
    height: u32,
) -> *mut Bridge {
    let Ok(identity) = Identity::new(instance, generation) else {
        return ptr::null_mut();
    };
    let viewport = Viewport {
        width,
        height,
        epoch,
    };
    let Ok(mailbox) = Mailbox::new(identity, viewport) else {
        return ptr::null_mut();
    };
    Box::into_raw(Box::new(Bridge {
        mailbox,
        identity,
        viewport,
        live: Arc::new(AtomicBool::new(true)),
    }))
}
/// # Safety
/// `bridge` is a live handle for this read, or null. No owner authority is granted.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_live(bridge: *const Bridge) -> bool {
    unsafe { bridge.as_ref() }.is_some_and(|b| b.live.load(Ordering::Acquire))
}
/// # Safety
/// `bridge` is live until all concurrent calls finish; `bytes` spans `length` bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_publish(
    bridge: *const Bridge,
    generation: u64,
    epoch: u64,
    observed_ns: u64,
    bytes: *const u8,
    length: usize,
) -> i32 {
    let Some(b) = (unsafe { bridge.as_ref() }) else {
        return -1;
    };
    if bytes.is_null() || !b.live.load(Ordering::Acquire) {
        return -1;
    }
    if generation != b.identity.generation || epoch != b.viewport.epoch {
        return -2;
    }
    if b.viewport.bytes().ok() != Some(length) {
        return -3;
    }
    let data = unsafe { slice::from_raw_parts(bytes, length) };
    match b
        .mailbox
        .publish(b.identity, b.viewport, observed_ns, data, &[] as &[Rect])
    {
        Ok(_) => 0,
        Err("FRAME_BUSY") => 1,
        Err(_) => -4,
    }
}
/// # Safety
/// `bridge` is a live handle, and `metadata` and `pixels` are writable output pointers.
/// Returned pixels are immutable, valid only until release, and must not be retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_acquire(
    bridge: *const Bridge,
    now_ns: u64,
    max_age_ns: u64,
    metadata: *mut Metadata,
    pixels: *mut *const u8,
) -> *mut FrameLease {
    let Some(b) = (unsafe { bridge.as_ref() }) else {
        return ptr::null_mut();
    };
    if metadata.is_null() || pixels.is_null() || !b.live.load(Ordering::Acquire) {
        return ptr::null_mut();
    }
    let Ok(Some(lease)) = b.mailbox.acquire(now_ns, max_age_ns) else {
        return ptr::null_mut();
    };
    let f = lease.frame();
    unsafe {
        *metadata = Metadata {
            instance: f.identity.instance,
            generation: f.identity.generation,
            epoch: f.viewport.epoch,
            index: f.index,
            observed_ns: f.observed_ns,
            width: f.viewport.width,
            height: f.viewport.height,
            stride: f.stride,
            bgra8: 1,
            alpha_mode: 0,
            reserved: 0,
            length: f.pixels().len() as u64,
        };
        // alpha_mode=0 means unverified. A declaration is not a measured alpha result.
        *pixels = f.pixels().as_ptr();
    }
    Box::into_raw(Box::new(FrameLease {
        lease,
        live: b.live.clone(),
    }))
}
/// # Safety
/// `lease` must be a live, unreleased lease returned by acquire.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_lease_valid(lease: *const FrameLease) -> bool {
    unsafe { lease.as_ref() }.is_some_and(|l| l.live.load(Ordering::Acquire) && l.lease.is_valid())
}
/// # Safety
/// `lease` is live and exclusively held by its sink. Call only after successful
/// sink use; this records an observation, never audiovisual time or OS cleanup.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_complete(lease: *mut FrameLease) -> bool {
    unsafe { lease.as_ref() }
        .is_some_and(|l| l.live.load(Ordering::Acquire) && l.lease.mark_consumed())
}
/// # Safety
/// `lease` must be null or one live lease, released exactly once without concurrent use.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_release(lease: *mut FrameLease) {
    if !lease.is_null() {
        drop(unsafe { Box::from_raw(lease) });
    }
}
/// # Safety
/// `bridge` must be live and `stats` writable. This operation is for telemetry,
/// not a real-time graphics callback.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_stats(
    bridge: *const Bridge,
    stats: *mut Statistics,
) -> bool {
    let Some(b) = (unsafe { bridge.as_ref() }) else {
        return false;
    };
    if stats.is_null() {
        return false;
    }
    let Ok(s) = b.mailbox.stats() else {
        return false;
    };
    unsafe {
        *stats = Statistics {
            paints: s.paints,
            coalesced: s.coalesced,
            acquired: s.acquired,
            stale: s.stale,
        };
    }
    true
}
/// # Safety
/// `bridge` must be live and `stats` writable for StatisticsV2. Telemetry only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_stats_v2(
    bridge: *const Bridge,
    stats: *mut StatisticsV2,
) -> bool {
    let Some(b) = (unsafe { bridge.as_ref() }) else {
        return false;
    };
    if stats.is_null() {
        return false;
    }
    let Ok(s) = b.mailbox.stats() else {
        return false;
    };
    unsafe {
        *stats = StatisticsV2 {
            paints: s.paints,
            coalesced: s.coalesced,
            acquired: s.acquired,
            stale: s.stale,
            pending: s.pending,
            leased: s.leased,
            consumed: s.consumed,
            released_unconsumed: s.released_unconsumed,
            invalidated_close: s.invalidated_close,
            revoked_generation: s.revoked_generation,
            retained_leases: s.retained_leases,
            retained_bytes: s.retained_bytes,
            copied_bytes: s.copied_bytes,
            copy_ns: s.copy_ns,
            publish_busy: s.publish_busy,
            acquire_busy: s.acquire_busy,
            consumer_busy: s.consumer_busy,
        };
    }
    true
}
/// # Safety
/// `bridge` must be live. reason=0 is close; reason=1 is generation/viewport
/// replacement. Any other reason fails without changing the mailbox.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_revoke_reason(bridge: *const Bridge, reason: u32) -> bool {
    let reason = match reason {
        0 => Revocation::Close,
        1 => Revocation::Generation,
        _ => return false,
    };
    let Some(b) = (unsafe { bridge.as_ref() }) else {
        return false;
    };
    b.live.store(false, Ordering::Release);
    b.mailbox.invalidate_reason(reason).is_ok()
}
/// # Safety
/// `bridge` is live. Revocation invalidates leases, but their bytes remain owned
/// until release so cancellation never becomes a use-after-free.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_revoke(bridge: *const Bridge) {
    let _ = unsafe { motive_frames_revoke_reason(bridge, 0) };
}
/// # Safety
/// `bridge` must be null or a live handle, destroyed exactly once after all calls
/// have joined. Outstanding leases may be released later but are invalidated.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn motive_frames_destroy(bridge: *mut Bridge) {
    if !bridge.is_null() {
        unsafe {
            motive_frames_revoke(bridge);
            drop(Box::from_raw(bridge));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn callback_copy_and_lease_survive_revoke_without_reuse() {
        unsafe {
            let b = motive_frames_create(1, 7, 9, 2, 1);
            let mut bytes = [0, 0, 128, 128, 0, 0, 0, 0];
            assert_eq!(motive_frames_publish(b, 7, 9, 1, bytes.as_ptr(), 8), 0);
            bytes.fill(255);
            let mut m = Metadata::default();
            let mut p = ptr::null();
            let l = motive_frames_acquire(b, 1, 100, &mut m, &mut p);
            assert!(!l.is_null());
            assert_eq!(slice::from_raw_parts(p, 8)[2], 128);
            for t in 2..100 {
                assert_eq!(motive_frames_publish(b, 7, 9, t, bytes.as_ptr(), 8), 0);
            }
            assert!(motive_frames_acquire(b, 100, 100, &mut m, &mut p).is_null());
            assert_eq!((m.generation, m.epoch, m.index, m.alpha_mode), (7, 9, 1, 0));
            motive_frames_revoke(b);
            assert!(!motive_frames_lease_valid(l));
            motive_frames_destroy(b);
            assert_eq!(slice::from_raw_parts(p, 8)[2], 128);
            motive_frames_release(l);
        }
    }
    #[test]
    fn generation_epoch_size_time_and_stale_are_fail_closed() {
        unsafe {
            assert!(motive_frames_create(0, 1, 1, 1, 1).is_null());
            assert!(motive_frames_create(1, 1, 1, u32::MAX, 1).is_null());
            let b = motive_frames_create(1, 2, 3, 1, 1);
            let p = [0; 4];
            assert_eq!(motive_frames_publish(b, 1, 3, 1, p.as_ptr(), 4), -2);
            assert_eq!(motive_frames_publish(b, 2, 4, 1, p.as_ptr(), 4), -2);
            assert_eq!(
                motive_frames_publish(b, 2, 3, 1, p.as_ptr(), usize::MAX),
                -3
            );
            assert_eq!(motive_frames_publish(b, 2, 3, 10, p.as_ptr(), 4), 0);
            assert_eq!(motive_frames_publish(b, 2, 3, 9, p.as_ptr(), 4), -4);
            let mut m = Metadata::default();
            let mut pixels = ptr::null();
            assert!(motive_frames_acquire(b, 20, 9, &mut m, &mut pixels).is_null());
            let mut stats = Statistics::default();
            assert!(motive_frames_stats(b, &mut stats));
            assert_eq!(stats.stale, 1);
            motive_frames_destroy(b);
        }
    }
}

#[cfg(feature = "creator-bridge")]
pub mod goal_binding;
