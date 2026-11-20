//! Own-process integration test using retained, real CEF BGRA. No live CEF,
//! graphics device, public listener, secrets in argv/environment, or AV clock.
use motive_browser_contracts::{
    Identity,
    frame::{Mailbox, Viewport},
};
use motive_frame_transport::{Grant, LaunchSecret, Receiver, Sender};
use sha2::{Digest, Sha256};
use std::{
    fs::OpenOptions,
    io::Read,
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd},
        unix::{fs::OpenOptionsExt, net::UnixStream, process::CommandExt},
    },
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

struct ChildGuard(Child);
impl Drop for ChildGuard {
    fn drop(&mut self) {
        if self.0.try_wait().ok().flatten().is_none() {
            let _ = self.0.kill();
        }
        let _ = self.0.wait();
    }
}
fn image(path: &str, g: Grant) -> Vec<u8> {
    let f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .expect("owned raw file");
    let meta = f.metadata().unwrap();
    assert!(meta.is_file());
    assert_eq!(meta.len(), g.viewport.bytes().unwrap() as u64);
    let mut bytes = Vec::with_capacity(meta.len() as usize);
    f.take(meta.len() + 1).read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes.len(), g.viewport.bytes().unwrap());
    bytes
}
fn child(path: &str, g: Grant, crash: bool) {
    // The only inherited capabilities are one bootstrap socket and one channel.
    let mut boot = unsafe { UnixStream::from_raw_fd(0) };
    let secret = LaunchSecret::receive_bootstrap(&mut boot).unwrap();
    drop(boot);
    let socket = unsafe { UnixStream::from_raw_fd(3) };
    let mut sender = Sender::new(socket, secret, g, Duration::from_secs(1)).unwrap();
    let bytes = image(path, g);
    let mailbox = Mailbox::new(g.identity, g.viewport).unwrap();
    for n in 1..=if crash { 20 } else { 60 } {
        mailbox
            .publish(g.identity, g.viewport, n, &bytes, &[])
            .unwrap();
        let lease = mailbox.acquire(n, 1).unwrap().unwrap();
        sender.send(&lease).unwrap();
        assert!(lease.mark_consumed());
        drop(lease);
    }
    assert!(mailbox.stats().unwrap().is_conserved());
    assert_eq!(mailbox.stats().unwrap().retained_bytes, 0);
    if crash {
        std::process::exit(86);
    }
}
fn run(path: &str, g: Grant, crash: bool) -> u32 {
    let bytes = image(path, g);
    let secret = LaunchSecret::fresh().unwrap();
    let (owner_socket, child_socket) = UnixStream::pair().unwrap();
    let (mut boot_owner, boot_child) = UnixStream::pair().unwrap();
    // Keep the dup source outside stdio/fd3 to avoid descriptor remap collisions.
    let fd = unsafe { libc::fcntl(child_socket.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 10) };
    assert!(fd >= 10);
    let inherited = unsafe { OwnedFd::from_raw_fd(fd) };
    drop(child_socket);
    let mut command = Command::new(std::env::current_exe().unwrap());
    command
        .args([
            "--child",
            path,
            &g.viewport.width.to_string(),
            &g.viewport.height.to_string(),
            &g.identity.generation.to_string(),
            if crash { "crash" } else { "normal" },
        ])
        .stdin(Stdio::from(OwnedFd::from(boot_child)))
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    unsafe {
        command.pre_exec(move || {
            if libc::dup2(fd, 3) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut process = ChildGuard(command.spawn().unwrap());
    let pid = process.0.id();
    drop(inherited);
    secret.send_bootstrap(&mut boot_owner).unwrap();
    drop(boot_owner);
    let mut receiver = Receiver::new(owner_socket, secret, g, Duration::from_secs(1)).unwrap();
    let mailbox = receiver.mailbox();
    let count = if crash { 20 } else { 60 };
    let mut held = None;
    for sequence in 1..=count {
        assert_eq!(receiver.receive(sequence).unwrap().wire_sequence, sequence);
        let lease = mailbox.acquire(sequence, 1).unwrap().unwrap();
        assert_eq!(lease.frame().pixels(), bytes);
        assert_eq!(lease.frame().identity, g.identity);
        assert_eq!(lease.frame().viewport, g.viewport);
        assert_eq!(lease.frame().stride, g.viewport.width * 4);
        if sequence == count {
            held = Some(lease);
        } else {
            assert!(lease.mark_consumed());
            drop(lease);
        }
    }
    if crash {
        assert_eq!(receiver.receive(count + 1), Err("EOF"));
    } else {
        receiver.revoke();
    }
    let held = held.unwrap();
    assert!(!held.is_valid());
    assert!(!held.mark_consumed());
    drop(held);
    let stats = mailbox.stats().unwrap();
    assert!(stats.is_conserved());
    assert_eq!(stats.retained_bytes, 0);
    let deadline = Instant::now() + Duration::from_secs(2);
    let status = loop {
        if let Some(status) = process.0.try_wait().unwrap() {
            break status;
        }
        assert!(Instant::now() < deadline, "child exit deadline");
        std::thread::sleep(Duration::from_millis(5));
    };
    assert_eq!(status.code(), Some(if crash { 86 } else { 0 }));
    pid
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let child_mode = args.get(1).is_some_and(|x| x == "--child");
    let offset = if child_mode { 2 } else { 1 };
    assert_eq!(
        args.len(),
        if child_mode { 7 } else { 4 },
        "usage: replay owned.bgra width height"
    );
    let g = Grant {
        identity: Identity::new(
            22,
            if child_mode {
                args[5].parse().unwrap()
            } else {
                1
            },
        )
        .unwrap(),
        viewport: Viewport {
            width: args[offset + 1].parse().unwrap(),
            height: args[offset + 2].parse().unwrap(),
            epoch: 1,
        },
    };
    g.validate().unwrap();
    if child_mode {
        child(&args[offset], g, args[6] == "crash");
        return;
    }
    let path = &args[1];
    let bytes = image(path, g);
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let mut pids = Vec::new();
    for (generation, crash) in [(1, false), (2, true), (3, false)] {
        pids.push(run(
            path,
            Grant {
                identity: Identity::new(22, generation).unwrap(),
                ..g
            },
            crash,
        ));
    }
    println!(
        "{{\"status\":\"PASS\",\"scope\":\"retained real CEF BGRA across own processes; no live CEF or GPU\",\"sha256\":\"{}\",\"frames\":140,\"bytes_per_frame\":{},\"width\":{},\"height\":{},\"stride\":{},\"child_pids\":{:?},\"children_reaped\":3,\"fresh_bootstraps\":3,\"crash_exit\":86,\"retained_bytes_after_close\":0}}",
        hash,
        bytes.len(),
        g.viewport.width,
        g.viewport.height,
        g.viewport.width * 4,
        pids
    );
}
