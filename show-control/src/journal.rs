//! Bounded durable intent journal for the single Production-owner adapter.
//! Creating a journal never dispatches. Reopening is read-only and never replays.
use crate::actions::{PreparedAction, Revision};
use crate::model::{Error, validate_id};
use crate::runtime::{Completion, DispatchOutcome, DispatchReport, PollReport};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::Path;

pub const MAX_JOURNAL_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_JOURNAL_RECORDS: usize = 4096;
pub const MAX_RECORD_BYTES: usize = 64 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DispatchIntent {
    pub action_key: String,
    pub expected: Revision,
    pub prepared: PreparedAction,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "entry", rename_all = "snake_case", deny_unknown_fields)]
pub enum JournalEntry {
    Header {
        schema_version: u16,
        owner_session: String,
        pid: u32,
    },
    Intent {
        intent: DispatchIntent,
    },
    Dispatch {
        action_key: String,
        report: DispatchReport,
    },
    Completion {
        action_key: String,
        operation_id: String,
        report: PollReport,
    },
    CancelIntent {
        action_key: String,
        operation_id: String,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RecoveryState {
    /// Intent was durable; dispatch/result may or may not have occurred.
    Uncertain,
    Accepted {
        operation_id: String,
        cancel_requested: bool,
    },
    Terminal,
}

#[derive(Clone, Debug)]
struct EntryState {
    expected: Revision,
    dispatched: bool,
    recovery: RecoveryState,
}

#[derive(Clone, Debug)]
pub struct RecoveredJournal {
    pub owner_session: String,
    pub pid: u32,
    pub entries: Vec<JournalEntry>,
    pub actions: BTreeMap<String, RecoveryState>,
}

/// One writer owned by Production; never share it with UI/audio/native threads.
pub struct IntentJournal {
    file: File,
    pid: u32,
    bytes: usize,
    records: usize,
    poisoned: bool,
    states: BTreeMap<String, EntryState>,
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_JOURNAL", message)
}
fn io_error() -> Error {
    Error::new(
        "JOURNAL_IO",
        "journal durability failed; no automatic dispatch retry",
    )
}

fn apply_entry(
    states: &mut BTreeMap<String, EntryState>,
    pid: u32,
    entry: &JournalEntry,
) -> Result<(), Error> {
    match entry {
        JournalEntry::Header { .. } => return Err(invalid("unexpected second header")),
        JournalEntry::Intent { intent } => {
            if intent.expected.pid != pid
                || intent.action_key.is_empty()
                || intent.action_key.len() > 300
                || !intent
                    .action_key
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"-_:.".contains(&c))
                || intent.prepared.local
                || intent.prepared.commands.is_empty()
                || intent.prepared.commands.len() > 2
            {
                return Err(invalid("invalid owner or multimedia intent"));
            }
            intent.prepared.action.validate()?;
            if states.contains_key(&intent.action_key) {
                return Err(Error::new(
                    "INTENT_ALREADY_RECORDED",
                    "this action must not be dispatched again",
                ));
            }
            states.insert(
                intent.action_key.clone(),
                EntryState {
                    expected: intent.expected,
                    dispatched: false,
                    recovery: RecoveryState::Uncertain,
                },
            );
        }
        JournalEntry::Dispatch { action_key, report } => {
            let state = states
                .get_mut(action_key)
                .ok_or_else(|| invalid("dispatch has no durable intent"))?;
            if state.dispatched {
                return Err(invalid("duplicate dispatch result"));
            }
            let operation = match &report.outcome {
                DispatchOutcome::Accepted { operation_id } => Some(operation_id.as_str()),
                _ => None,
            };
            if let Some(receipt) = &report.receipt {
                if !matches!(
                    report.outcome,
                    DispatchOutcome::Accepted { .. } | DispatchOutcome::Completed
                ) {
                    return Err(invalid("receipt on an unacknowledged dispatch"));
                }
                receipt.validate(action_key, state.expected, operation)?;
                state.expected = receipt.after;
            }
            state.recovery = match &report.outcome {
                DispatchOutcome::Accepted { operation_id } => {
                    if operation_id.is_empty() || operation_id.len() > 256 {
                        return Err(invalid("invalid operation identity"));
                    }
                    RecoveryState::Accepted {
                        operation_id: operation_id.clone(),
                        cancel_requested: false,
                    }
                }
                DispatchOutcome::Completed | DispatchOutcome::Rejected(_) => {
                    RecoveryState::Terminal
                }
                DispatchOutcome::Uncertain => RecoveryState::Uncertain,
                DispatchOutcome::Simulated => {
                    return Err(invalid("live journal cannot record a simulated dispatch"));
                }
            };
            state.dispatched = true;
        }
        JournalEntry::Completion {
            action_key,
            operation_id,
            report,
        } => {
            let state = states
                .get_mut(action_key)
                .ok_or_else(|| invalid("completion has no intent"))?;
            if !matches!(&state.recovery, RecoveryState::Accepted { operation_id: known, .. } if known == operation_id)
            {
                return Err(invalid("completion does not match the accepted operation"));
            }
            if let Some(receipt) = &report.terminal_receipt {
                if !matches!(
                    report.completion,
                    Completion::Completed | Completion::Cancelled | Completion::Failed(_)
                ) {
                    return Err(invalid("terminal receipt on a non-terminal observation"));
                }
                receipt.validate(action_key, operation_id, pid)?;
            }
            if let Some(receipt) = &report.receipt {
                if !matches!(report.completion, Completion::Completed) {
                    return Err(invalid("receipt on non-completed operation"));
                }
                receipt.validate(action_key, state.expected, Some(operation_id))?;
                state.expected = receipt.after;
            }
            state.recovery = match report.completion {
                Completion::Completed | Completion::Cancelled | Completion::Failed(_) => {
                    RecoveryState::Terminal
                }
                Completion::Unknown => RecoveryState::Uncertain,
                Completion::Pending => {
                    return Err(invalid("pending polling is not a durable completion"));
                }
            };
        }
        JournalEntry::CancelIntent {
            action_key,
            operation_id,
        } => {
            let state = states
                .get_mut(action_key)
                .ok_or_else(|| invalid("cancellation has no accepted operation"))?;
            match &mut state.recovery {
                RecoveryState::Accepted {
                    operation_id: known,
                    cancel_requested,
                } if known == operation_id && !*cancel_requested => *cancel_requested = true,
                _ => {
                    return Err(invalid(
                        "cancellation is duplicate or operation does not match",
                    ));
                }
            }
        }
    }
    Ok(())
}

impl IntentJournal {
    /// `path` comes from the trusted application path policy, never an event.
    /// Its immediate parent must already be a private directory (0700).
    /// A fresh owner-session file is required; existing files are never resumed.
    pub fn create(path: &Path, owner_session: &str, pid: u32) -> Result<Self, Error> {
        validate_id(owner_session)?;
        if pid == 0 || !path.is_absolute() {
            return Err(invalid(
                "explicit absolute path and real owner PID required",
            ));
        }
        let parent = path
            .parent()
            .ok_or_else(|| invalid("journal parent missing"))?;
        let metadata = parent.symlink_metadata().map_err(|_| io_error())?;
        if !metadata.is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
            return Err(invalid(
                "journal parent must be a private non-symlink directory",
            ));
        }
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)
            .map_err(|_| io_error())?;
        let mut journal = Self {
            file,
            pid,
            bytes: 0,
            records: 0,
            poisoned: false,
            states: BTreeMap::new(),
        };
        journal.write_entry(&JournalEntry::Header {
            schema_version: 1,
            owner_session: owner_session.into(),
            pid,
        })?;
        File::open(parent)
            .and_then(|file| file.sync_all())
            .map_err(|_| io_error())?;
        Ok(journal)
    }

    fn write_entry(&mut self, entry: &JournalEntry) -> Result<(), Error> {
        if self.poisoned {
            return Err(io_error());
        }
        let mut bytes =
            serde_json::to_vec(entry).map_err(|_| invalid("journal serialization failed"))?;
        bytes.push(b'\n');
        if bytes.len() > MAX_RECORD_BYTES
            || self.bytes + bytes.len() > MAX_JOURNAL_BYTES
            || self.records >= MAX_JOURNAL_RECORDS
        {
            return Err(Error::new(
                "JOURNAL_FULL",
                "journal limit reached; no silent eviction or dispatch",
            ));
        }
        if self
            .file
            .write_all(&bytes)
            .and_then(|()| self.file.sync_all())
            .is_err()
        {
            self.poisoned = true;
            return Err(io_error());
        }
        self.bytes += bytes.len();
        self.records += 1;
        Ok(())
    }

    fn append(&mut self, entry: JournalEntry) -> Result<(), Error> {
        let mut states = self.states.clone();
        apply_entry(&mut states, self.pid, &entry)?;
        self.write_entry(&entry)?;
        self.states = states;
        Ok(())
    }

    /// Must succeed before the owner calls Production::apply.
    pub fn begin(&mut self, intent: DispatchIntent) -> Result<(), Error> {
        self.append(JournalEntry::Intent { intent })
    }
    /// Failure after dispatch means uncertainty, never permission to retry.
    pub fn record_dispatch(
        &mut self,
        action_key: &str,
        report: DispatchReport,
    ) -> Result<(), Error> {
        self.append(JournalEntry::Dispatch {
            action_key: action_key.into(),
            report,
        })
    }
    pub fn record_completion(
        &mut self,
        action_key: &str,
        operation_id: &str,
        report: PollReport,
    ) -> Result<(), Error> {
        self.append(JournalEntry::Completion {
            action_key: action_key.into(),
            operation_id: operation_id.into(),
            report,
        })
    }
    /// Durable cancellation intention precedes the one native cancel request.
    pub fn begin_cancel(&mut self, action_key: &str, operation_id: &str) -> Result<(), Error> {
        self.append(JournalEntry::CancelIntent {
            action_key: action_key.into(),
            operation_id: operation_id.into(),
        })
    }

    /// Read-only recovery; incomplete/corrupt records fail closed and remain on disk.
    pub fn read(path: &Path) -> Result<RecoveredJournal, Error> {
        let before = path.symlink_metadata().map_err(|_| io_error())?;
        if !before.is_file()
            || before.permissions().mode() & 0o777 != 0o600
            || before.len() > MAX_JOURNAL_BYTES as u64
        {
            return Err(invalid("journal is not a bounded private regular file"));
        }
        let file = File::open(path).map_err(|_| io_error())?;
        let after = file.metadata().map_err(|_| io_error())?;
        if (before.dev(), before.ino()) != (after.dev(), after.ino()) {
            return Err(invalid("journal changed during open"));
        }
        let mut bytes = Vec::new();
        file.take((MAX_JOURNAL_BYTES + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| io_error())?;
        if bytes.len() > MAX_JOURNAL_BYTES || bytes.last() != Some(&b'\n') {
            return Err(invalid(
                "journal is oversized or has an incomplete final record",
            ));
        }
        let mut entries = Vec::new();
        for line in bytes[..bytes.len() - 1].split(|b| *b == b'\n') {
            if line.len() + 1 > MAX_RECORD_BYTES || entries.len() >= MAX_JOURNAL_RECORDS {
                return Err(invalid("journal limits exceeded"));
            }
            entries.push(
                serde_json::from_slice::<JournalEntry>(line)
                    .map_err(|_| invalid("malformed journal record"))?,
            );
        }
        let (owner_session, pid) = match entries.first() {
            Some(JournalEntry::Header {
                schema_version: 1,
                owner_session,
                pid,
            }) if *pid != 0 => {
                validate_id(owner_session)?;
                (owner_session.clone(), *pid)
            }
            _ => return Err(invalid("missing or unsupported journal header")),
        };
        let mut states = BTreeMap::new();
        for entry in entries.iter().skip(1) {
            apply_entry(&mut states, pid, entry)?;
        }
        Ok(RecoveredJournal {
            owner_session,
            pid,
            entries,
            actions: states
                .into_iter()
                .map(|(key, state)| (key, state.recovery))
                .collect(),
        })
    }
}
