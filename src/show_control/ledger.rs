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
    AnimatedWidget {
        source_id: &'a str,
        operation_id: u64,
    },
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
    animated_sources: BTreeMap<u64, String>,
}

/// Native proof covers the complete interval since the owner's observation.
/// A later owned change cannot erase an external change or an observation gap.
pub(in crate::core) fn source_lifecycle_operation(
    before: &serde_json::Value,
    after: &serde_json::Value,
) -> Option<u64> {
    if before["exhausted"] != false || after["exhausted"] != false {
        return None;
    }
    let before = before["revision"].as_u64()?;
    let end = after["revision"].as_u64()?;
    let start = after["from_revision"].as_u64()?;
    let operation = after["operation_id"].as_u64()?;
    (operation != 0 && start <= before && before < end).then_some(operation)
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
    pub(in crate::core) fn bind_animated_widget(&mut self, id: u64, source_id: &str) {
        self.bind_animation(id);
        if self.scope.as_ref().is_some_and(|scope| {
            self.operations.get(&NativeOperation::Animation(id)) == Some(&scope.key)
        }) {
            self.animated_sources
                .entry(id)
                .or_insert_with(|| source_id.into());
        }
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
        if let NativeOperation::Animation(id) = operation {
            self.animated_sources.remove(&id);
        }
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
            Cause::AnimatedWidget {
                source_id,
                operation_id,
            } => self
                .animated_sources
                .get(&operation_id)
                .filter(|id| id.as_str() == source_id)
                .and_then(|_| {
                    self.operations
                        .get(&NativeOperation::Animation(operation_id))
                })
                .cloned(),
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
    use serde_json::json;
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
    fn source_receipt(revision: u64, from: u64, operation: u64) -> serde_json::Value {
        json!({"revision":revision,"from_revision":from,"operation_id":operation,"exhausted":false})
    }
    #[test]
    fn animated_widget_receipt_covers_only_an_unbroken_native_interval() {
        let before = source_receipt(10, 9, 0);
        assert_eq!(
            source_lifecycle_operation(&before, &source_receipt(13, 10, 4)),
            Some(4)
        );
        // An intervening external event at revision 11 broke the owned run.
        assert_eq!(
            source_lifecycle_operation(&before, &source_receipt(13, 11, 4)),
            None
        );
        assert_eq!(
            source_lifecycle_operation(&before, &source_receipt(10, 9, 4)),
            None
        );
        assert_eq!(
            source_lifecycle_operation(&before, &source_receipt(9, 8, 4)),
            None
        );
        assert_eq!(
            source_lifecycle_operation(&before, &source_receipt(13, 10, 0)),
            None
        );
        assert_eq!(
            source_lifecycle_operation(&serde_json::Value::Null, &source_receipt(13, 10, 4)),
            None
        );
        let mut exhausted = source_receipt(13, 10, 4);
        exhausted["exhausted"] = json!(true);
        assert_eq!(source_lifecycle_operation(&before, &exhausted), None);
    }
    #[test]
    fn animated_widget_source_binding_and_counter_continuation_are_exact() {
        let mut l = RevisionLedger::default();
        assert!(l.begin("goal:0", None));
        l.bind_animated_widget(4, "goal");
        l.record(20, 21, Cause::Command);
        l.end();
        l.record(
            21,
            22,
            Cause::AnimatedWidget {
                source_id: "goal",
                operation_id: 4,
            },
        );
        l.record(22, 23, Cause::Animation(4));
        // This is the exact version the following counter action may inherit.
        assert!(
            l.receipt("goal:0", Some("session:animation:4"), rev(20), rev(23))
                .is_some()
        );
        l.record(
            23,
            24,
            Cause::AnimatedWidget {
                source_id: "other",
                operation_id: 4,
            },
        );
        assert!(l.receipt("goal:0", None, rev(23), rev(24)).is_none());
        l.record(
            24,
            25,
            Cause::AnimatedWidget {
                source_id: "goal",
                operation_id: 99,
            },
        );
        assert!(l.receipt("goal:0", None, rev(24), rev(25)).is_none());
        l.record(25, 26, Cause::External);
        l.record(26, 27, Cause::Animation(4));
        assert!(l.receipt("goal:0", None, rev(25), rev(27)).is_none());
    }
    #[test]
    fn autonomous_phase_after_animation_end_does_not_inherit_ownership() {
        let before = source_receipt(13, 10, 4);
        // Native end clears the source lease. Its later alert timeout is op 0.
        let timeout = source_receipt(14, 13, 0);
        assert_eq!(source_lifecycle_operation(&before, &timeout), None);
        let mut l = RevisionLedger::default();
        l.begin("goal:0", None);
        l.bind_animated_widget(4, "goal");
        l.end();
        l.record(30, 31, Cause::OverlaySource("goal"));
        assert!(l.receipt("goal:0", None, rev(30), rev(31)).is_none());
        l.forget(NativeOperation::Animation(4));
        l.record(
            31,
            32,
            Cause::AnimatedWidget {
                source_id: "goal",
                operation_id: 4,
            },
        );
        assert!(l.receipt("goal:0", None, rev(31), rev(32)).is_none());
    }
}
