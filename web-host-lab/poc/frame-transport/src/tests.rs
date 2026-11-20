use super::*;
use std::thread;

fn secret() -> LaunchSecret {
    LaunchSecret(Zeroizing::new([7; 48]))
} // unit fixtures only
fn grant() -> Grant {
    Grant {
        identity: Identity::new(2, 19).unwrap(),
        viewport: Viewport {
            width: 4,
            height: 2,
            epoch: 3,
        },
    }
}
fn pair(timeout: Duration) -> (UnixStream, Receiver) {
    let (a, b) = UnixStream::pair().unwrap();
    (a, Receiver::new(b, secret(), grant(), timeout).unwrap())
}
fn packet(h: [u8; HEADER_BYTES], pixels: &[u8]) -> Vec<u8> {
    let key = secret();
    let mut bytes = h.to_vec();
    bytes.extend_from_slice(
        &key.mac(b"MOTIVE-H22-HEADER\0", &h, &[])
            .finalize()
            .into_bytes(),
    );
    bytes.extend_from_slice(pixels);
    bytes.extend_from_slice(
        &key.mac(b"MOTIVE-H22-BODY\0", &h, pixels)
            .finalize()
            .into_bytes(),
    );
    bytes
}
fn pixels() -> Vec<u8> {
    [0, 0, 0, 0, 0, 0, 128, 128, 12, 24, 48, 255, 64, 32, 16, 128].repeat(2)
}
fn timeout() -> Duration {
    Duration::from_millis(500)
}

#[test]
fn real_socket_roundtrip_preserves_full_bgra_alpha_and_stride() {
    let (a, b) = UnixStream::pair().unwrap();
    let g = grant();
    let bytes = pixels();
    let expected = bytes.clone();
    let worker = thread::spawn(move || {
        let mailbox = Mailbox::new(g.identity, g.viewport).unwrap();
        mailbox
            .publish(g.identity, g.viewport, 1, &bytes, &[])
            .unwrap();
        let lease = mailbox.acquire(1, 1).unwrap().unwrap();
        let mut sender = Sender::new(a, secret(), g, timeout()).unwrap();
        sender.send(&lease).unwrap();
        assert!(lease.mark_consumed());
        drop(lease);
        assert!(mailbox.stats().unwrap().is_conserved());
    });
    let mut r = Receiver::new(b, secret(), g, timeout()).unwrap();
    assert_eq!(
        r.receive(300).unwrap(),
        Receipt {
            wire_sequence: 1,
            mailbox_index: Some(1)
        }
    );
    let m = r.mailbox();
    let lease = m.acquire(300, 10).unwrap().unwrap();
    assert_eq!(lease.frame().pixels(), expected);
    assert_eq!(lease.frame().stride, 16);
    assert_eq!(lease.frame().observed_ns, 300);
    assert_eq!(lease.frame().identity, g.identity);
    assert_eq!(lease.frame().viewport, g.viewport);
    assert!(lease.mark_consumed());
    drop(lease);
    worker.join().unwrap();
    r.revoke();
    assert_eq!(m.stats().unwrap().retained_bytes, 0);
}

#[test]
fn authenticated_header_rejects_every_ungranted_field_before_allocation() {
    for offset in [0, 8, 10, 12, 16, 32, 40, 48, 64, 68, 72, 76, 80, 84] {
        let (mut writer, mut reader) = pair(timeout());
        let mut h = header(grant(), 1, &secret()).unwrap();
        h[offset] ^= 1;
        writer.write_all(&packet(h, &pixels())).unwrap();
        assert_eq!(reader.receive(1), Err("HEADER_GRANT"), "offset {offset}");
        assert_eq!(reader.payload_allocations, 0);
        assert_eq!(reader.mailbox().stats().unwrap().paints, 0);
        assert_eq!(reader.receive(2), Err("CHANNEL_REVOKED"));
    }
}

#[test]
fn unauthenticated_header_and_payload_mutations_never_publish() {
    for offset in [0, 88, 120, 151, 152] {
        let (mut writer, mut reader) = pair(timeout());
        let mut p = packet(header(grant(), 1, &secret()).unwrap(), &pixels());
        p[offset] ^= 1;
        writer.write_all(&p).unwrap();
        assert!(reader.receive(1).is_err());
        assert_eq!(reader.mailbox().stats().unwrap().paints, 0);
        if offset < 120 {
            assert_eq!(reader.payload_allocations, 0);
        }
    }
}

#[test]
fn replay_revokes_an_outstanding_lease_and_never_relabels_its_bytes() {
    let (mut writer, mut reader) = pair(timeout());
    let p = packet(header(grant(), 1, &secret()).unwrap(), &pixels());
    writer.write_all(&p).unwrap();
    reader.receive(1).unwrap();
    let m = reader.mailbox();
    let lease = m.acquire(1, 100).unwrap().unwrap();
    writer.write_all(&p).unwrap();
    assert_eq!(reader.receive(2), Err("REPLAY"));
    assert_eq!(reader.payload_allocations, 1);
    assert!(!lease.is_valid());
    assert!(!lease.mark_consumed());
    assert_eq!(lease.frame().pixels(), pixels());
    drop(lease);
    let stats = m.stats().unwrap();
    assert!(stats.is_conserved());
    assert_eq!(stats.retained_bytes, 0);
}

#[test]
fn fragmented_packet_is_reassembled_but_truncated_body_is_not_a_frame() {
    let (mut writer, mut reader) = pair(timeout());
    let p = packet(header(grant(), 1, &secret()).unwrap(), &pixels());
    let worker = thread::spawn(move || {
        for chunk in p.chunks(7) {
            writer.write_all(chunk).unwrap();
        }
    });
    reader.receive(1).unwrap();
    worker.join().unwrap();
    let (mut writer, mut reader) = pair(timeout());
    let p = packet(header(grant(), 1, &secret()).unwrap(), &pixels());
    writer.write_all(&p[..125]).unwrap();
    writer.shutdown(Shutdown::Write).unwrap();
    assert_eq!(reader.receive(1), Err("EOF"));
    assert_eq!(reader.mailbox().stats().unwrap().paints, 0);
}

#[test]
fn absolute_deadline_is_not_reset_by_a_slow_writer() {
    let (mut writer, mut reader) = pair(Duration::from_millis(80));
    let worker = thread::spawn(move || {
        for _ in 0..20 {
            if writer.write_all(&[0]).is_err() {
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
    });
    let start = Instant::now();
    assert_eq!(reader.receive(1), Err("DEADLINE"));
    assert!(start.elapsed() < Duration::from_millis(300));
    assert_eq!(reader.payload_allocations, 0);
    worker.join().unwrap();
}

#[test]
fn coalescing_and_one_lease_bound_survive_one_hundred_wire_frames() {
    let (mut writer, mut reader) = pair(timeout());
    let bytes = pixels();
    writer
        .write_all(&packet(header(grant(), 1, &secret()).unwrap(), &bytes))
        .unwrap();
    reader.receive(1).unwrap();
    let m = reader.mailbox();
    let lease = m.acquire(1, 1).unwrap().unwrap();
    for seq in 2..=100 {
        writer
            .write_all(&packet(header(grant(), seq, &secret()).unwrap(), &bytes))
            .unwrap();
        reader.receive(seq).unwrap();
    }
    let stats = m.stats().unwrap();
    assert_eq!(stats.coalesced, 98);
    assert_eq!(stats.retained_bytes, 64);
    assert!(stats.is_conserved());
    assert!(matches!(m.acquire(100, 100), Err("CONSUMER_BUSY")));
    drop(lease);
    let newest = m.acquire(100, 100).unwrap().unwrap();
    assert_eq!(newest.frame().index, 100);
    drop(reader);
    assert!(!newest.is_valid());
    drop(newest);
    assert_eq!(m.stats().unwrap().retained_bytes, 0);
}

#[test]
fn blocked_writer_times_out_without_blocking_the_producer_mailbox() {
    let g = Grant {
        identity: grant().identity,
        viewport: Viewport {
            width: 640,
            height: 360,
            epoch: 1,
        },
    };
    let m = Arc::new(Mailbox::new(g.identity, g.viewport).unwrap());
    let bytes = vec![0; g.viewport.bytes().unwrap()];
    m.publish(g.identity, g.viewport, 1, &bytes, &[]).unwrap();
    let lease = m.acquire(1, 1).unwrap().unwrap();
    let (a, _unread) = UnixStream::pair().unwrap();
    let mut tx = Sender::new(a, secret(), g, Duration::from_millis(80)).unwrap();
    let start = Instant::now();
    let worker = thread::spawn(move || tx.send(&lease));
    for now in 2..=20 {
        m.publish(g.identity, g.viewport, now, &bytes, &[]).unwrap();
    }
    assert_eq!(worker.join().unwrap(), Err("DEADLINE"));
    assert!(start.elapsed() < Duration::from_secs(1));
    assert!(m.stats().unwrap().is_conserved());
    assert!(m.stats().unwrap().retained_bytes <= 2 * bytes.len() as u64);
}

#[test]
fn private_bootstrap_rejects_extra_data_and_random_launches_differ() {
    let a = LaunchSecret::fresh().unwrap();
    let b = LaunchSecret::fresh().unwrap();
    assert!(a.0[..] != b.0[..]);
    let (mut tx, mut rx) = UnixStream::pair().unwrap();
    a.send_bootstrap(&mut tx).unwrap();
    let received = LaunchSecret::receive_bootstrap(&mut rx).unwrap();
    assert!(received.0[..] == a.0[..]);
    let (mut tx, mut rx) = UnixStream::pair().unwrap();
    tx.write_all(&[0; 49]).unwrap();
    tx.shutdown(Shutdown::Write).unwrap();
    assert!(matches!(
        LaunchSecret::receive_bootstrap(&mut rx),
        Err("BOOTSTRAP_EXTRA")
    ));
}

#[test]
fn bounds_and_invalid_deadlines_cannot_be_overridden() {
    let (a, _) = UnixStream::pair().unwrap();
    assert!(Sender::new(a, secret(), grant(), Duration::ZERO).is_err());
    let bad = Grant {
        viewport: Viewport {
            width: u32::MAX,
            height: u32::MAX,
            epoch: 1,
        },
        ..grant()
    };
    assert!(bad.validate().is_err());
    let (a, _) = UnixStream::pair().unwrap();
    assert!(Receiver::new(a, secret(), grant(), Duration::from_secs(3)).is_err());
}
