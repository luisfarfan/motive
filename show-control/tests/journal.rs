//! Filesystem durability/validation tests; no native commands are dispatched.
use motive_show_control::actions::{
    Action, ProductionSnapshot, SourceKind, SourceReadiness, prepare,
};
use motive_show_control::journal::*;
use motive_show_control::model::Error;
use motive_show_control::runtime::*;
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct OwnedDirectory(PathBuf);
impl OwnedDirectory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "motive-journal-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }
    fn path(&self) -> PathBuf {
        self.0.join("owner-session.jsonl")
    }
}
impl Drop for OwnedDirectory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn intent() -> DispatchIntent {
    let snapshot = ProductionSnapshot {
        pid: 71,
        revision: 10,
        sources: BTreeMap::from([("title".into(), SourceReadiness::Ready)]),
        source_kinds: BTreeMap::from([("title".into(), SourceKind::Text)]),
        ..ProductionSnapshot::default()
    };
    DispatchIntent {
        action_key: "event:1:0".into(),
        expected: snapshot.version(),
        prepared: prepare(
            &Action::ShowOverlay {
                source_id: "title".into(),
            },
            &snapshot,
            Some(snapshot.version()),
        )
        .unwrap(),
    }
}
fn accepted() -> DispatchReport {
    let before = intent().expected;
    let mut after = before;
    after.revision += 1;
    DispatchReport {
        outcome: DispatchOutcome::Accepted {
            operation_id: "animation-1".into(),
        },
        receipt: Some(MutationReceipt {
            action_key: "event:1:0".into(),
            operation_id: Some("animation-1".into()),
            before,
            after,
        }),
    }
}

#[test]
fn intent_is_recoverable_before_dispatch_and_acknowledgment_is_separate() {
    let directory = OwnedDirectory::new();
    let mut journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    journal.begin(intent()).unwrap();
    let pending = IntentJournal::read(&directory.path()).unwrap();
    assert_eq!(pending.actions["event:1:0"], RecoveryState::Uncertain);
    assert_eq!(pending.entries.len(), 2);
    assert_eq!(
        fs::metadata(directory.path()).unwrap().permissions().mode() & 0o777,
        0o600
    );
    journal.record_dispatch("event:1:0", accepted()).unwrap();
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap().actions["event:1:0"],
        RecoveryState::Accepted {
            operation_id: "animation-1".into(),
            cancel_requested: false
        }
    );
    journal.begin_cancel("event:1:0", "animation-1").unwrap();
    assert!(journal.begin_cancel("event:1:0", "animation-1").is_err());
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap().actions["event:1:0"],
        RecoveryState::Accepted {
            operation_id: "animation-1".into(),
            cancel_requested: true
        }
    );
    let before = accepted().receipt.unwrap().after;
    let mut after = before;
    after.revision += 1;
    journal
        .record_completion(
            "event:1:0",
            "animation-1",
            PollReport {
                completion: Completion::Completed,
                receipt: Some(MutationReceipt {
                    action_key: "event:1:0".into(),
                    operation_id: Some("animation-1".into()),
                    before,
                    after,
                }),
                terminal_receipt: None,
            },
        )
        .unwrap();
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap().actions["event:1:0"],
        RecoveryState::Terminal
    );
    assert_eq!(
        journal.begin(intent()).unwrap_err().code,
        "INTENT_ALREADY_RECORDED"
    );
}

#[test]
fn crash_gap_and_truncated_tail_are_never_replayed_or_repaired() {
    let directory = OwnedDirectory::new();
    let mut journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    journal.begin(intent()).unwrap();
    drop(journal);
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap().actions["event:1:0"],
        RecoveryState::Uncertain
    );
    assert!(IntentJournal::create(&directory.path(), "session-2", 72).is_err());
    OpenOptions::new()
        .append(true)
        .open(directory.path())
        .unwrap()
        .write_all(b"{\"entry\":")
        .unwrap();
    let original = fs::read(directory.path()).unwrap();
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap_err().code,
        "INVALID_JOURNAL"
    );
    assert_eq!(original, fs::read(directory.path()).unwrap());
}

#[test]
fn unsupported_header_and_unknown_fields_are_rejected() {
    let directory = OwnedDirectory::new();
    let journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    drop(journal);
    for data in [
        "{\"entry\":\"header\",\"schema_version\":2,\"owner_session\":\"session-1\",\"pid\":71}\n",
        "{\"entry\":\"header\",\"schema_version\":1,\"owner_session\":\"session-1\",\"pid\":71,\"untrusted\":true}\n",
    ] {
        fs::write(directory.path(), data).unwrap();
        assert_eq!(
            IntentJournal::read(&directory.path()).unwrap_err().code,
            "INVALID_JOURNAL"
        );
    }
}

#[test]
fn private_paths_are_explicit_and_existing_files_or_links_survive() {
    let directory = OwnedDirectory::new();
    fs::set_permissions(&directory.0, fs::Permissions::from_mode(0o755)).unwrap();
    assert!(IntentJournal::create(&directory.path(), "session-1", 71).is_err());
    fs::set_permissions(&directory.0, fs::Permissions::from_mode(0o700)).unwrap();
    let target = directory.0.join("untouched");
    fs::write(&target, "owned fixture").unwrap();
    symlink(&target, directory.path()).unwrap();
    assert!(IntentJournal::create(&directory.path(), "session-1", 71).is_err());
    assert!(IntentJournal::read(&directory.path()).is_err());
    assert_eq!(fs::read_to_string(target).unwrap(), "owned fixture");
}

#[test]
fn missing_intent_wrong_operation_or_wrong_receipt_never_append() {
    let directory = OwnedDirectory::new();
    let mut journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    assert!(journal.record_dispatch("event:1:0", accepted()).is_err());
    journal.begin(intent()).unwrap();
    let bytes = fs::read(directory.path()).unwrap();
    let mut wrong = accepted();
    wrong.receipt.as_mut().unwrap().before.revision += 1;
    assert!(journal.record_dispatch("event:1:0", wrong).is_err());
    assert_eq!(bytes, fs::read(directory.path()).unwrap());
    journal.record_dispatch("event:1:0", accepted()).unwrap();
    let bytes = fs::read(directory.path()).unwrap();
    assert!(
        journal
            .record_completion(
                "event:1:0",
                "another-operation",
                PollReport::legacy(Completion::Completed)
            )
            .is_err()
    );
    assert_eq!(bytes, fs::read(directory.path()).unwrap());
}

#[test]
fn oversized_result_fails_closed_without_erasing_durable_intent() {
    let directory = OwnedDirectory::new();
    let mut journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    journal.begin(intent()).unwrap();
    let bytes = fs::read(directory.path()).unwrap();
    let report = DispatchReport::legacy(DispatchOutcome::Rejected(Error::new(
        "EXAMPLE",
        &"x".repeat(MAX_RECORD_BYTES),
    )));
    assert_eq!(
        journal
            .record_dispatch("event:1:0", report)
            .unwrap_err()
            .code,
        "JOURNAL_FULL"
    );
    assert_eq!(bytes, fs::read(directory.path()).unwrap());
    assert_eq!(
        IntentJournal::read(&directory.path()).unwrap().actions["event:1:0"],
        RecoveryState::Uncertain
    );
}

#[test]
fn terminal_proof_is_durable_without_claiming_foreign_revisions() {
    let directory = OwnedDirectory::new();
    let mut journal = IntentJournal::create(&directory.path(), "session-1", 71).unwrap();
    journal.begin(intent()).unwrap();
    journal.record_dispatch("event:1:0", accepted()).unwrap();
    let accepted_bytes = fs::read(directory.path()).unwrap();
    let report = PollReport {
        completion: Completion::Completed,
        receipt: None,
        terminal_receipt: Some(TerminalReceipt {
            action_key: "event:1:0".into(),
            operation_id: "animation-1".into(),
            pid: 71,
        }),
    };
    for corruption in ["key", "operation", "pid", "pending", "unknown"] {
        let mut invalid = report.clone();
        let receipt = invalid.terminal_receipt.as_mut().unwrap();
        match corruption {
            "key" => receipt.action_key = "another:1:0".into(),
            "operation" => receipt.operation_id = "other-session:animation-1".into(),
            "pid" => receipt.pid = 72,
            "pending" => invalid.completion = Completion::Pending,
            "unknown" => invalid.completion = Completion::Unknown,
            _ => unreachable!(),
        }
        assert!(
            journal
                .record_completion("event:1:0", "animation-1", invalid)
                .is_err()
        );
        assert_eq!(fs::read(directory.path()).unwrap(), accepted_bytes);
    }
    journal
        .record_completion("event:1:0", "animation-1", report)
        .unwrap();
    let recovered = IntentJournal::read(&directory.path()).unwrap();
    assert_eq!(recovered.actions["event:1:0"], RecoveryState::Terminal);
    assert_eq!(recovered.entries.len(), 4);
    assert!(
        fs::read(directory.path())
            .unwrap()
            .starts_with(&accepted_bytes)
    );
    match &recovered.entries[3] {
        JournalEntry::Completion { report, .. } => {
            assert!(report.receipt.is_none());
            assert_eq!(report.terminal_receipt.as_ref().unwrap().pid, 71);
        }
        _ => panic!("expected retained native terminal"),
    }
    assert_eq!(
        journal.begin(intent()).unwrap_err().code,
        "INTENT_ALREADY_RECORDED"
    );
}
