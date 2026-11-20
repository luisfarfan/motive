//! H22 isolated binary channel. No CEF/OBS loading, MCP, public listener or AV clock.
//!
//! One socketpair capability per immutable instance/generation/epoch grant. The
//! owner must revoke the old receiver BEFORE cold replacement; recovery creates
//! a fresh key and endpoint. HMAC authenticates the trusted host, not its honesty
//! or confinement. A compromised holder can forge its own granted pixels.
use hmac::{Hmac, Mac};
use motive_browser_contracts::{
    Identity,
    frame::{Frame, Lease, Mailbox, Revocation, Viewport},
};
use sha2::Sha256;
use std::{
    io::{Read, Write},
    net::Shutdown,
    os::unix::net::UnixStream,
    sync::Arc,
    time::{Duration, Instant},
};
use zeroize::Zeroizing;

pub const HEADER_BYTES: usize = 88;
pub const TAG_BYTES: usize = 32;
pub const MAX_DEADLINE: Duration = Duration::from_secs(2);
const MAGIC: &[u8; 8] = b"MTVBGRA1";
type Hmac256 = Hmac<Sha256>;
pub type Result<T> = std::result::Result<T, &'static str>;

/// Deliberately not Debug, Clone or serializable. Bootstrap only through an
/// inherited private descriptor, never arguments, environment, disk or logs.
pub struct LaunchSecret(Zeroizing<[u8; 48]>);
impl LaunchSecret {
    pub fn fresh() -> Result<Self> {
        let mut bytes = Zeroizing::new([0; 48]);
        getrandom::fill(bytes.as_mut()).map_err(|_| "OS_RANDOM")?;
        Ok(Self(bytes))
    }
    pub fn send_bootstrap(&self, stream: &mut UnixStream) -> Result<()> {
        stream.set_nonblocking(true).map_err(|_| "SOCKET_MODE")?;
        let deadline = Instant::now() + Duration::from_secs(1);
        write_all(stream, self.0.as_ref(), deadline)?;
        stream
            .shutdown(Shutdown::Write)
            .map_err(|_| "BOOTSTRAP_CLOSE")
    }
    pub fn receive_bootstrap(stream: &mut UnixStream) -> Result<Self> {
        stream.set_nonblocking(true).map_err(|_| "SOCKET_MODE")?;
        let deadline = Instant::now() + Duration::from_secs(1);
        let mut bytes = Zeroizing::new([0; 48]);
        read_all(stream, bytes.as_mut(), deadline)?;
        wait_io(stream, libc::POLLIN, deadline)?;
        let mut extra = [0; 1];
        if stream.read(&mut extra).map_err(|_| "BOOTSTRAP_EOF")? != 0 {
            return Err("BOOTSTRAP_EXTRA");
        }
        Ok(Self(bytes))
    }
    fn nonce(&self) -> &[u8] {
        &self.0[32..]
    }
    fn mac(&self, domain: &[u8], header: &[u8], body: &[u8]) -> Hmac256 {
        let mut mac = Hmac256::new_from_slice(&self.0[..32]).expect("fixed HMAC key length");
        mac.update(domain);
        mac.update(header);
        mac.update(body);
        mac
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Grant {
    pub identity: Identity,
    pub viewport: Viewport,
}
impl Grant {
    pub fn validate(self) -> Result<Self> {
        Identity::new(self.identity.instance, self.identity.generation)?;
        self.viewport.bytes()?;
        Ok(self)
    }
}

fn remaining(deadline: Instant) -> Result<Duration> {
    let d = deadline
        .checked_duration_since(Instant::now())
        .ok_or("DEADLINE")?;
    if d.is_zero() { Err("DEADLINE") } else { Ok(d) }
}
fn wait_io(stream: &UnixStream, events: libc::c_short, deadline: Instant) -> Result<()> {
    use std::os::fd::AsRawFd;
    loop {
        let duration = remaining(deadline)?;
        let millis = duration.as_millis().saturating_add(1).min(i32::MAX as u128) as i32;
        let mut fd = libc::pollfd {
            fd: stream.as_raw_fd(),
            events,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut fd, 1, millis) };
        if result < 0 {
            if std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted {
                continue;
            }
            return Err("SOCKET_POLL");
        }
        if result == 0 {
            return Err("DEADLINE");
        }
        if fd.revents & libc::POLLNVAL != 0 {
            return Err("SOCKET_DESCRIPTOR");
        }
        // HUP may coexist with a final buffered packet. Read it before EOF.
        // No SO_RCVTIMEO mutation on Darwin's disconnected socket (EINVAL).
        remaining(deadline)?;
        return Ok(());
    }
}
fn read_all(stream: &mut UnixStream, mut data: &mut [u8], deadline: Instant) -> Result<()> {
    while !data.is_empty() {
        wait_io(stream, libc::POLLIN, deadline)?;
        match stream.read(data) {
            Ok(0) => return Err("EOF"),
            Ok(n) => {
                data = &mut data[n..];
            }
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => continue,
            Err(_) => return Err("SOCKET_READ"),
        }
    }
    remaining(deadline)?;
    Ok(())
}
fn write_all(stream: &mut UnixStream, mut data: &[u8], deadline: Instant) -> Result<()> {
    while !data.is_empty() {
        wait_io(stream, libc::POLLOUT, deadline)?;
        match stream.write(data) {
            Ok(0) => return Err("SOCKET_ZERO_WRITE"),
            Ok(n) => data = &data[n..],
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => continue,
            Err(_) => return Err("SOCKET_WRITE"),
        }
    }
    remaining(deadline)?;
    Ok(())
}
fn configure(stream: &UnixStream, timeout: Duration) -> Result<()> {
    if timeout.is_zero() || timeout > MAX_DEADLINE {
        return Err("DEADLINE_POLICY");
    }
    // Rust socketpairs are CLOEXEC. H23's launch adapter must set CLOEXEC again
    // on its deliberately inherited endpoint before spawning any CEF helpers.
    use std::os::fd::AsRawFd;
    let fd = stream.as_raw_fd();
    if unsafe { libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err("CLOEXEC");
    }
    for option in [libc::SO_SNDBUF, libc::SO_RCVBUF] {
        let size: libc::c_int = 65536;
        if unsafe {
            libc::setsockopt(
                fd,
                libc::SOL_SOCKET,
                option,
                (&size as *const libc::c_int).cast(),
                std::mem::size_of_val(&size) as libc::socklen_t,
            )
        } < 0
        {
            return Err("SOCKET_BUFFER");
        }
    }
    stream.set_nonblocking(true).map_err(|_| "SOCKET_MODE")
}

fn header(grant: Grant, sequence: u64, secret: &LaunchSecret) -> Result<[u8; HEADER_BYTES]> {
    let bytes = grant.validate()?.viewport.bytes()?;
    if sequence == 0 {
        return Err("SEQUENCE");
    }
    let mut h = [0; HEADER_BYTES];
    h[..8].copy_from_slice(MAGIC);
    h[8..10].copy_from_slice(&1u16.to_le_bytes()); // version
    h[10..12].copy_from_slice(&1u16.to_le_bytes()); // premultiplied sRGB BGRA8
    h[12..16].copy_from_slice(&(HEADER_BYTES as u32).to_le_bytes());
    h[16..32].copy_from_slice(secret.nonce());
    for (at, value) in [
        (32, grant.identity.instance),
        (40, grant.identity.generation),
        (48, grant.viewport.epoch),
        (56, sequence),
    ] {
        h[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    for (at, value) in [
        (64, grant.viewport.width),
        (68, grant.viewport.height),
        (72, grant.viewport.width * 4),
        (76, bytes as u32),
        (80, 1),
    ] {
        h[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    Ok(h)
}
fn sequence(h: &[u8; HEADER_BYTES]) -> u64 {
    u64::from_le_bytes(h[56..64].try_into().expect("fixed header"))
}

pub struct Sender {
    stream: UnixStream,
    secret: LaunchSecret,
    grant: Grant,
    last: u64,
    timeout: Duration,
    failed: bool,
}
impl Sender {
    pub fn new(
        stream: UnixStream,
        secret: LaunchSecret,
        grant: Grant,
        timeout: Duration,
    ) -> Result<Self> {
        configure(&stream, timeout)?;
        Ok(Self {
            stream,
            secret,
            grant: grant.validate()?,
            last: 0,
            timeout,
            failed: false,
        })
    }
    /// Worker only. Never called in OnPaint or OBS rendering. One existing
    /// mailbox lease, no transport queue; writes have one whole-frame deadline.
    pub fn send(&mut self, lease: &Lease) -> Result<()> {
        if self.failed {
            return Err("CHANNEL_REVOKED");
        }
        let result = (|| {
            if !lease.is_valid() {
                return Err("LEASE_REVOKED");
            }
            let frame = lease.frame();
            self.validate_frame(frame)?;
            let deadline = Instant::now() + self.timeout;
            let h = header(self.grant, frame.index, &self.secret)?;
            let head_tag = self
                .secret
                .mac(b"MOTIVE-H22-HEADER\0", &h, &[])
                .finalize()
                .into_bytes();
            let body_tag = self
                .secret
                .mac(b"MOTIVE-H22-BODY\0", &h, frame.pixels())
                .finalize()
                .into_bytes();
            write_all(&mut self.stream, &h, deadline)?;
            write_all(&mut self.stream, &head_tag, deadline)?;
            write_all(&mut self.stream, frame.pixels(), deadline)?;
            write_all(&mut self.stream, &body_tag, deadline)?;
            if !lease.is_valid() {
                return Err("LEASE_REVOKED");
            }
            self.last = frame.index;
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
            let _ = self.stream.shutdown(Shutdown::Both);
        }
        result
    }
    fn validate_frame(&self, f: &Frame) -> Result<()> {
        if f.identity != self.grant.identity || f.viewport != self.grant.viewport {
            return Err("STALE_FRAME");
        }
        if f.index <= self.last {
            return Err("REPLAY");
        }
        if f.stride != f.viewport.width * 4 || f.pixels().len() != f.viewport.bytes()? {
            return Err("FRAME_LAYOUT");
        }
        Ok(())
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct Receipt {
    pub wire_sequence: u64,
    pub mailbox_index: Option<u64>,
}
pub struct Receiver {
    stream: UnixStream,
    secret: LaunchSecret,
    grant: Grant,
    last: u64,
    timeout: Duration,
    failed: bool,
    mailbox: Arc<Mailbox>,
    pub payload_allocations: u64,
}
impl Receiver {
    pub fn new(
        stream: UnixStream,
        secret: LaunchSecret,
        grant: Grant,
        timeout: Duration,
    ) -> Result<Self> {
        configure(&stream, timeout)?;
        let grant = grant.validate()?;
        Ok(Self {
            stream,
            secret,
            grant,
            last: 0,
            timeout,
            failed: false,
            mailbox: Arc::new(Mailbox::new(grant.identity, grant.viewport)?),
            payload_allocations: 0,
        })
    }
    pub fn mailbox(&self) -> Arc<Mailbox> {
        self.mailbox.clone()
    }
    pub fn revoke(&mut self) {
        self.failed = true;
        let _ = self.mailbox.invalidate_reason(Revocation::Generation);
        let _ = self.stream.shutdown(Shutdown::Both);
    }
    /// The caller supplies an OWNER receive observation, never a wire/CEF PTS.
    /// H23 must call this on a worker and serialize revocation with owner grants.
    pub fn receive(&mut self, owner_observed_ns: u64) -> Result<Receipt> {
        if self.failed {
            return Err("CHANNEL_REVOKED");
        }
        let result = self.receive_inner(owner_observed_ns);
        if result.is_err() {
            self.revoke();
        }
        result
    }
    fn receive_inner(&mut self, owner_observed_ns: u64) -> Result<Receipt> {
        let deadline = Instant::now() + self.timeout;
        let mut h = [0; HEADER_BYTES];
        let mut tag = [0; TAG_BYTES];
        read_all(&mut self.stream, &mut h, deadline)?;
        read_all(&mut self.stream, &mut tag, deadline)?;
        // Constant-time authentication precedes interpreting lengths/allocation.
        self.secret
            .mac(b"MOTIVE-H22-HEADER\0", &h, &[])
            .verify_slice(&tag)
            .map_err(|_| "HEADER_AUTH")?;
        let seq = sequence(&h);
        if seq == 0 || seq <= self.last {
            return Err("REPLAY");
        }
        // Equality to a locally constructed grant validates version, format,
        // reserved fields, session, identity, dimensions, packed stride and size.
        if h != header(self.grant, seq, &self.secret)? {
            return Err("HEADER_GRANT");
        }
        let length = self.grant.viewport.bytes()?;
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(length)
            .map_err(|_| "PAYLOAD_ALLOCATION")?;
        pixels.resize(length, 0);
        self.payload_allocations += 1;
        read_all(&mut self.stream, &mut pixels, deadline)?;
        read_all(&mut self.stream, &mut tag, deadline)?;
        self.secret
            .mac(b"MOTIVE-H22-BODY\0", &h, &pixels)
            .verify_slice(&tag)
            .map_err(|_| "BODY_AUTH")?;
        remaining(deadline)?;
        let index = match self.mailbox.publish(
            self.grant.identity,
            self.grant.viewport,
            owner_observed_ns,
            &pixels,
            &[],
        ) {
            Ok(index) => Some(index),
            Err("FRAME_BUSY") => None,
            Err(e) => return Err(e),
        };
        self.last = seq;
        Ok(Receipt {
            wire_sequence: seq,
            mailbox_index: index,
        })
    }
}
impl Drop for Receiver {
    fn drop(&mut self) {
        self.revoke();
    }
}

#[cfg(test)]
mod tests;
