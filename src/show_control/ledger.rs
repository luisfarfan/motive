//! Owner provenance. Missing, evicted and unrelated revisions never grant rebasing.
use motive_show_control::actions::Revision;
use motive_show_control::runtime::MutationReceipt;
use std::collections::{BTreeMap, VecDeque};

const MAX_DELTAS: usize = 4096;
const MAX_OPERATIONS: usize = 512;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(super) enum NativeOperation {
    Animation(u64),
    Transition(u64),
}

pub(in crate::core) enum Cause<'a> {
    External,
    Command,
    Animation(u64),
    Transition(u64),
    OverlaySource(&'a str),
}

struct Scope {
    key: String,
    source: Option<String>,
}

struct Delta {
    before: u64,
    after: u64,
    key: Option<String>,
}

#[derive(Default)]
pub(in crate::core) struct RevisionLedger {
    deltas: VecDeque<Delta>,
    scope: Option<Scope>,
    operations: BTreeMap<NativeOperation, String>,
}

impl RevisionLedger {
    pub(in crate::core) fn in_dispatch(&self) -> bool {
        self.scope.is_some()
    }
    pub(super) fn begin(&mut self, key: &str, source: Option<String>) -> bool {
        if self.scope.is_some() || self.operations.len() >= MAX_OPERATIONS {
            return false;
        }
        self.scope = Some(Scope {
            key: key.into(),
            source,
        });
        true
    }
    pub(super) fn end(&mut self) {
        self.scope = None;
    }

    pub(in crate::core) fn bind_animation(&mut self, id: u64) {
        self.bind(NativeOperation::Animation(id));
    }
    pub(in crate::core) fn bind_transition(&mut self, id: u64) {
        self.bind(NativeOperation::Transition(id));
    }
    fn bind(&mut self, operation: NativeOperation) {
        if let Some(scope) = &self.scope {
            // IDs cannot be reassigned to another action, including cancellation.
            self.operations
                .entry(operation)
                .or_insert_with(|| scope.key.clone());
        }
    }
    pub(super) fn forget(&mut self, operation: NativeOperation) {
        self.operations.remove(&operation);
    }
    pub(in crate::core) fn record(&mut self, before: u64, after: u64, cause: Cause<'_>) {
        let key = match cause {
            Cause::External => None,
            Cause::Command => self.scope.as_ref().map(|s| s.key.clone()),
            Cause::OverlaySource(id) => self
                .scope
                .as_ref()
                .filter(|s| s.source.as_deref() == Some(id))
                .map(|s| s.key.clone()),
            Cause::Animation(id) => self
                .operations
                .get(&NativeOperation::Animation(id))
                .cloned(),
            Cause::Transition(id) => self
                .operations
                .get(&NativeOperation::Transition(id))
                .cloned(),
        };
        if self.deltas.len() == MAX_DELTAS {
            self.deltas.pop_front();
        }
        self.deltas.push_back(Delta { before, after, key });
    }
    pub(super) fn receipt(
        &self,
        key: &str,
        operation_id: Option<&str>,
        before: Revision,
        after: Revision,
    ) -> Option<MutationReceipt> {
        if before.pid == 0 || before.pid != after.pid || after.revision < before.revision {
            return None;
        }
        let mut next = before.revision;
        for delta in self
            .deltas
            .iter()
            .filter(|d| d.after > before.revision && d.after <= after.revision)
        {
            if delta.before != next
                || delta.after != next.checked_add(1)?
                || delta.key.as_deref() != Some(key)
            {
                return None;
            }
            next = delta.after;
        }
        if next != after.revision {
            return None;
        }
        Some(MutationReceipt {
            action_key: key.into(),
            operation_id: operation_id.map(str::to_owned),
            before,
            after,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rev(n: u64) -> Revision {
        Revision {
            pid: 9,
            revision: n,
        }
    }
    #[test]
    fn own_exact_chain_and_namespace() {
        let mut l = RevisionLedger::default();
        assert!(l.begin("job:1", Some("s".into())));
        l.bind_animation(1);
        l.record(3, 4, Cause::Command);
        l.record(4, 5, Cause::OverlaySource("s"));
        l.end();
        l.record(5, 6, Cause::Animation(1));
        assert!(
            l.receipt("job:1", Some("session:animation:1"), rev(3), rev(6))
                .is_some()
        );
        assert!(l.receipt("job:2", None, rev(3), rev(6)).is_none());
        l.record(6, 7, Cause::Transition(1));
        assert!(l.receipt("job:1", None, rev(6), rev(7)).is_none());
    }
    #[test]
    fn other_sources_lifecycle_and_commands_break_chain() {
        let mut l = RevisionLedger::default();
        l.begin("a", Some("owned".into()));
        l.record(0, 1, Cause::OverlaySource("other"));
        l.record(1, 2, Cause::Command);
        l.end();
        assert!(l.receipt("a", None, rev(0), rev(2)).is_none());
        l.record(2, 3, Cause::Command);
        assert!(l.receipt("a", None, rev(2), rev(3)).is_none());
        l.record(3, 4, Cause::OverlaySource("owned"));
        assert!(l.receipt("a", None, rev(3), rev(4)).is_none());
    }
    #[test]
    fn gaps_eviction_restart_and_regression_fail_closed() {
        let mut l = RevisionLedger::default();
        l.begin("a", None);
        l.record(1, 2, Cause::Command);
        assert!(l.receipt("a", None, rev(0), rev(2)).is_none());
        assert!(l.receipt("a", None, rev(2), rev(1)).is_none());
        assert!(
            l.receipt(
                "a",
                None,
                rev(1),
                Revision {
                    pid: 10,
                    revision: 2
                }
            )
            .is_none()
        );
        for n in 2..=4097 {
            l.record(n, n + 1, Cause::Command);
        }
        assert!(l.receipt("a", None, rev(1), rev(4098)).is_none());
        assert!(l.receipt("a", None, rev(2), rev(4098)).is_some());
    }
    #[test]
    fn cancellation_scope_cannot_steal_native_operation() {
        let mut l = RevisionLedger::default();
        l.begin("a", None);
        l.bind_animation(4);
        l.end();
        l.begin("b", None);
        l.bind_animation(4);
        l.end();
        l.record(0, 1, Cause::Animation(4));
        assert!(l.receipt("a", None, rev(0), rev(1)).is_some());
        assert!(l.receipt("b", None, rev(0), rev(1)).is_none());
        l.forget(NativeOperation::Animation(4));
        l.record(1, 2, Cause::Animation(4));
        assert!(l.receipt("a", None, rev(1), rev(2)).is_none());
    }
}
