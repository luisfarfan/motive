use motive_browser_contracts::{
    Identity,
    adapter::Decision,
    frame::Viewport,
    lifecycle::State,
    manager::{BrowserHostManager, BrowserIdentity, OwnedFixtureDescriptor, ProcessIdentity},
};
fn descriptor(instance: u64, generation: u64) -> OwnedFixtureDescriptor {
    OwnedFixtureDescriptor {
        identity: Identity::new(instance, generation).unwrap(),
        viewport: Viewport {
            width: 2,
            height: 1,
            epoch: generation,
        },
        package_sha256: [1; 32],
        inventory_sha256: [2; 32],
        request_context: instance * 100 + generation,
        max_age_ns: 1000,
        static_hold: true,
    }
}
fn process(pid: u32) -> ProcessIdentity {
    ProcessIdentity {
        pid,
        start_token: 100,
    }
}
fn browser(id: u32, renderer: Option<u32>) -> BrowserIdentity {
    BrowserIdentity {
        host: process(10),
        browser_id: id,
        renderer: renderer.map(process),
    }
}
fn active(manager: &mut BrowserHostManager, instance: u64, renderer: Option<u32>) -> Identity {
    let d = descriptor(instance, 1);
    let identity = d.identity;
    manager.register_owned_fixture(d, 0).unwrap();
    manager
        .browser_created(identity, browser(instance as u32, renderer), 1)
        .unwrap();
    manager.set_visible_references(identity, 1).unwrap();
    identity
}
#[test]
fn shared_renderer_crash_revokes_every_affected_instance_and_unknown_assignment() {
    let mut manager = BrowserHostManager::new(5).unwrap();
    let a = active(&mut manager, 1, Some(20));
    let b = active(&mut manager, 2, Some(20));
    let c = active(&mut manager, 3, Some(30));
    let d = active(&mut manager, 4, None);
    let viewport = manager.get(a).unwrap().descriptor().viewport;
    manager
        .get(a)
        .unwrap()
        .mailbox()
        .publish(a, viewport, 1, &[42; 8], &[])
        .unwrap();
    let lease = manager
        .get(a)
        .unwrap()
        .mailbox()
        .acquire(1, 0)
        .unwrap()
        .unwrap();
    assert_eq!(
        manager
            .renderer_failed(process(10), Some(process(20)))
            .unwrap(),
        vec![a, b, d]
    );
    assert!(!lease.is_valid());
    assert_eq!(
        manager
            .get(a)
            .unwrap()
            .frame_stats()
            .unwrap()
            .revoked_generation,
        1
    );
    for identity in [a, b, d] {
        assert_eq!(manager.get(identity).unwrap().state(), State::Failed);
        assert_eq!(
            manager.frame_decision(identity, None, 2),
            Ok(Decision::Blank)
        );
    }
    assert_eq!(manager.get(c).unwrap().state(), State::Ready);
    assert!(
        manager
            .renderer_failed(
                ProcessIdentity {
                    pid: 10,
                    start_token: 101
                },
                None
            )
            .unwrap()
            .is_empty()
    );
}
#[test]
fn layers_share_source_visibility_and_cross_instance_frames_fail() {
    let mut manager = BrowserHostManager::new(3).unwrap();
    let a = active(&mut manager, 1, Some(20));
    let b = active(&mut manager, 2, Some(30));
    let viewport = manager.get(a).unwrap().descriptor().viewport;
    manager
        .get(a)
        .unwrap()
        .mailbox()
        .publish(a, viewport, 1, &[42; 8], &[])
        .unwrap();
    let lease = manager
        .get(a)
        .unwrap()
        .mailbox()
        .acquire(1, 0)
        .unwrap()
        .unwrap();
    assert_eq!(
        manager.frame_decision(b, Some(lease.frame()), 1),
        Err("STALE_FRAME")
    );
    manager.set_visible_references(a, 2).unwrap();
    assert_eq!(
        manager.frame_decision(a, Some(lease.frame()), 1),
        Ok(Decision::Upload { index: 1 })
    );
    manager.set_visible_references(a, 1).unwrap();
    assert_eq!(
        manager.frame_decision(a, None, 2),
        Ok(Decision::Repeat { index: 1 })
    );
    manager.set_visible_references(a, 0).unwrap();
    assert_eq!(manager.frame_decision(a, None, 3), Ok(Decision::Blank));
    manager.set_visible_references(a, 1).unwrap();
    assert_eq!(
        manager.frame_decision(a, None, 4),
        Ok(Decision::Repeat { index: 1 })
    );
}
#[test]
fn replacement_requires_native_close_new_identity_context_and_released_lease() {
    let mut manager = BrowserHostManager::new(1).unwrap();
    let old = active(&mut manager, 1, Some(20));
    let v = manager.get(old).unwrap().descriptor().viewport;
    manager
        .get(old)
        .unwrap()
        .mailbox()
        .publish(old, v, 1, &[42; 8], &[])
        .unwrap();
    let lease = manager
        .get(old)
        .unwrap()
        .mailbox()
        .acquire(1, 0)
        .unwrap()
        .unwrap();
    let mut new = descriptor(1, 2);
    new.viewport.epoch = 1; // A new generation may restart its viewport epochs.
    assert_eq!(
        manager.replace_closed(old, new.clone(), 2),
        Err("NATIVE_CLOSE_REQUIRED")
    );
    manager.close(old, false, 2).unwrap();
    assert!(!lease.is_valid());
    assert_eq!(
        manager.replace_closed(old, new.clone(), 3),
        Err("NATIVE_CLOSE_REQUIRED")
    );
    assert_eq!(
        manager.browser_closed(old, browser(2, Some(20)), 3),
        Err("BROWSER_IDENTITY")
    );
    manager
        .browser_closed(old, browser(1, Some(20)), 3)
        .unwrap();
    assert_eq!(
        manager.replace_closed(old, new.clone(), 4),
        Err("LEASES_RETAINED")
    );
    drop(lease);
    assert_eq!(
        manager.replace_closed(old, new.clone(), u64::MAX),
        Err("TIME_OVERFLOW")
    );
    assert_eq!(manager.get(old).unwrap().state(), State::Suspended);
    manager.replace_closed(old, new.clone(), 4).unwrap();
    assert!(matches!(manager.get(old), Err("STALE_GENERATION")));
    assert_eq!(manager.get(new.identity).unwrap().state(), State::Starting);
}
#[test]
fn host_reap_is_distinct_from_crash_and_browser_close() {
    let mut manager = BrowserHostManager::new(1).unwrap();
    let old = active(&mut manager, 1, Some(20));
    manager.host_failed(process(10)).unwrap();
    assert_eq!(
        manager.replace_closed(old, descriptor(1, 2), 2),
        Err("NATIVE_CLOSE_REQUIRED")
    );
    assert_eq!(manager.observe_host_reaped(process(10)).unwrap(), vec![old]);
    manager.replace_closed(old, descriptor(1, 2), 3).unwrap();
}
#[test]
fn disposed_identity_cannot_be_reused_after_removal() {
    let mut manager = BrowserHostManager::new(1).unwrap();
    let id = active(&mut manager, 1, Some(20));
    manager.close(id, true, 2).unwrap();
    assert!(matches!(
        manager.remove_disposed(id),
        Err("NATIVE_CLOSE_REQUIRED")
    ));
    manager.browser_closed(id, browser(1, Some(20)), 3).unwrap();
    assert!(manager.remove_disposed(id).unwrap().is_conserved());
    assert_eq!(
        manager.register_owned_fixture(descriptor(1, 1), 4),
        Err("GENERATION_REUSED")
    );
    manager.register_owned_fixture(descriptor(1, 2), 4).unwrap();
}
#[test]
fn admission_is_bounded_and_context_browser_identity_are_not_reused() {
    let mut manager = BrowserHostManager::new(2).unwrap();
    let a = active(&mut manager, 1, Some(20));
    let mut d = descriptor(2, 1);
    d.request_context = descriptor(1, 1).request_context;
    assert_eq!(manager.register_owned_fixture(d, 2), Err("CONTEXT_REUSED"));
    let b = descriptor(2, 1);
    manager.register_owned_fixture(b.clone(), 2).unwrap();
    assert_eq!(
        manager.browser_created(b.identity, browser(1, Some(30)), 3),
        Err("BROWSER_REUSED")
    );
    assert_eq!(
        manager.register_owned_fixture(descriptor(3, 1), 3),
        Err("INSTANCE_LIMIT")
    );
    assert_eq!(
        manager.get(a).unwrap().descriptor().origin(),
        "motive-asset://i1-g1"
    );
}

#[test]
fn failed_disposal_cannot_be_restarted_and_requires_host_reap_before_removal() {
    let mut manager = BrowserHostManager::new(1).unwrap();
    let old = active(&mut manager, 1, Some(20));
    manager.close(old, true, 2).unwrap();
    assert_eq!(manager.poll(5002).unwrap(), vec![old]);
    assert!(matches!(
        manager.remove_disposed(old),
        Err("NATIVE_CLOSE_REQUIRED")
    ));
    manager.observe_host_reaped(process(10)).unwrap();
    assert_eq!(
        manager.replace_closed(old, descriptor(1, 2), 5003),
        Err("DISPOSE_IS_TERMINAL")
    );
    assert!(manager.remove_disposed(old).unwrap().is_conserved());
}
