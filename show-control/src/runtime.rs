use crate::actions::{Action, PreparedAction, ProductionSnapshot, Revision, prepare};
use crate::model::{Error, Event, Payload, Scalar};
use serde::{Deserialize, Serialize};
use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::rc::Rc;
use std::time::Instant;

pub trait Clock {
    fn now_ms(&self) -> u64;
}
#[derive(Clone, Default)]
pub struct ManualClock(Rc<Cell<u64>>);
impl ManualClock {
    pub fn advance(&self, ms: u64) {
        self.0.set(self.0.get().saturating_add(ms));
    }
}
impl Clock for ManualClock {
    fn now_ms(&self) -> u64 {
        self.0.get()
    }
}
pub struct MonotonicClock(Instant);
impl Default for MonotonicClock {
    fn default() -> Self {
        Self(Instant::now())
    }
}
impl Clock for MonotonicClock {
    fn now_ms(&self) -> u64 {
        self.0.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Condition {
    Equals {
        field: String,
        value: Scalar,
    },
    Numeric {
        field: String,
        comparison: Comparison,
        value: i64,
    },
    Contains {
        field: String,
        phrase: String,
        whole_word: bool,
    },
    Variable {
        name: String,
        value: Scalar,
    },
    Counter {
        name: String,
        comparison: Comparison,
        value: i64,
    },
    Cooldown {
        key: String,
        duration_ms: u64,
    },
    ProductionActive {
        active: bool,
    },
    AuthorizedOrigin,
    AuthorizedUser,
    ConfidenceAtLeast {
        milli: u16,
    },
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Comparison {
    Less,
    LessEqual,
    Equal,
    GreaterEqual,
    Greater,
}
impl Comparison {
    fn matches(self, a: i64, b: i64) -> bool {
        match self {
            Self::Less => a < b,
            Self::LessEqual => a <= b,
            Self::Equal => a == b,
            Self::GreaterEqual => a >= b,
            Self::Greater => a > b,
        }
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum BusyPolicy {
    Reject,
    Defer,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum FailurePolicy {
    Stop,
    ContinueUnavailable,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub id: String,
    pub enabled: bool,
    pub event_kind: String,
    pub priority: u8,
    pub conditions: Vec<Condition>,
    pub actions: Vec<Action>,
    pub cooldown_ms: u64,
    pub debounce_ms: u64,
    pub timeout_ms: u64,
    pub busy_policy: BusyPolicy,
    pub failure_policy: FailurePolicy,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema_version: u16,
    pub rules: Vec<Rule>,
    pub variables: BTreeMap<String, Scalar>,
    pub queue_capacity: usize,
    pub rate_limit: u32,
    pub rate_window_ms: u64,
    pub max_actions_per_event: usize,
}
fn valid_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_:.".contains(c))
}
pub fn event_kinds() -> &'static [&'static str] {
    &[
        "manual.button_pressed",
        "keyboard.shortcut",
        "voice.keyword_detected",
        "chat.message",
        "chat.command",
        "viewer.follow",
        "viewer.subscribe",
        "viewer.donation",
        "viewer.reward_redeemed",
        "timer.completed",
        "production.started",
        "production.stopped",
        "motive.custom_event",
    ]
}
impl Config {
    pub fn from_json(json: &str) -> Result<Self, Error> {
        if json.len() > 1_048_576 {
            return Err(Error::new("INPUT_TOO_LARGE", "configuration exceeds 1 MiB"));
        }
        let value: Self = serde_json::from_str(json)
            .map_err(|_| Error::new("INVALID_JSON", "invalid Show Control configuration"))?;
        value.validate()?;
        Ok(value)
    }
    pub fn validate(&self) -> Result<(), Error> {
        if self.schema_version != 1 {
            return Err(Error::new(
                "UNKNOWN_SCHEMA",
                "Show Control schema must be 1",
            ));
        }
        if self.rules.len() > 64
            || self.variables.len() > 128
            || !(1..=256).contains(&self.queue_capacity)
            || !(1..=1000).contains(&self.rate_limit)
            || !(1..=60_000).contains(&self.rate_window_ms)
            || !(1..=128).contains(&self.max_actions_per_event)
        {
            return Err(Error::new("LIMIT", "configuration limits exceeded"));
        }
        let mut ids = BTreeSet::new();
        for (name, value) in &self.variables {
            if !valid_name(name) || matches!(value,Scalar::String(s) if s.len()>4096) {
                return Err(Error::new("INVALID_VARIABLE", "invalid typed variable"));
            }
        }
        for r in &self.rules {
            if !valid_name(&r.id)
                || !ids.insert(&r.id)
                || !event_kinds().contains(&r.event_kind.as_str())
                || r.conditions.len() > 16
                || r.actions.is_empty()
                || r.priority > 9
                || !(1..=60_000).contains(&r.timeout_ms)
                || r.cooldown_ms > 3_600_000
                || r.debounce_ms > 60_000
            {
                return Err(Error::new("INVALID_RULE", "invalid or duplicate rule"));
            }
            let actions = flatten(&r.actions)?;
            if actions.len() > 32 {
                return Err(Error::new("ACTION_LIMIT", "rule exceeds 32 actions"));
            }
            for a in &r.actions {
                a.validate()?;
            }
            for c in &r.conditions {
                match c {
                    Condition::Equals { field, .. } | Condition::Numeric { field, .. }
                        if !valid_name(field) =>
                    {
                        return Err(Error::new("INVALID_CONDITION", "invalid payload field"));
                    }
                    Condition::Contains { field, phrase, .. }
                        if !valid_name(field) || phrase.is_empty() || phrase.len() > 256 =>
                    {
                        return Err(Error::new("INVALID_CONDITION", "invalid phrase condition"));
                    }
                    Condition::Variable { name, .. } | Condition::Counter { name, .. }
                        if !valid_name(name) =>
                    {
                        return Err(Error::new("INVALID_CONDITION", "invalid variable name"));
                    }
                    Condition::Cooldown { key, duration_ms }
                        if !valid_name(key) || *duration_ms > 3_600_000 =>
                    {
                        return Err(Error::new("INVALID_CONDITION", "invalid cooldown"));
                    }
                    Condition::ConfidenceAtLeast { milli } if *milli > 1000 => {
                        return Err(Error::new("INVALID_CONDITION", "invalid confidence"));
                    }
                    _ => {}
                }
            }
        }
        Ok(())
    }
}
fn flatten(actions: &[Action]) -> Result<Vec<Action>, Error> {
    fn walk(input: &[Action], out: &mut Vec<Action>, depth: usize) -> Result<(), Error> {
        if depth > 4 {
            return Err(Error::new("ACTION_DEPTH", "sequence nesting exceeds four"));
        }
        for a in input {
            if let Action::Sequence { actions } = a {
                walk(actions, out, depth + 1)?;
            } else {
                out.push(a.clone());
            }
            if out.len() > 32 {
                return Err(Error::new("ACTION_LIMIT", "sequence exceeds 32 actions"));
            }
        }
        Ok(())
    }
    let mut out = Vec::new();
    walk(actions, &mut out, 0)?;
    Ok(out)
}

/// Constructed by a trusted local ingress adapter, never deserialized from viewer data.
#[derive(Clone, Debug, Default)]
pub struct Trust {
    pub authorized_origins: BTreeSet<String>,
    pub authorized_users: BTreeSet<String>,
    pub confidence_origins: BTreeSet<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum JobState {
    Queued,
    Deferred,
    Running,
    AwaitingCompletion,
    Completed,
    Simulated,
    Rejected,
    Failed,
    Cancelled,
    TimedOut,
    NeedsReconciliation,
}
impl JobState {
    pub fn terminal(&self) -> bool {
        matches!(
            self,
            Self::Completed
                | Self::Simulated
                | Self::Rejected
                | Self::Failed
                | Self::Cancelled
                | Self::TimedOut
                | Self::NeedsReconciliation
        )
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Stage {
    Validated,
    Prepared,
    Sent,
    Accepted,
    Completed,
    Simulated,
    Rejected,
    Failed,
    Cancelled,
    TimedOut,
    Uncertain,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActionRecord {
    pub index: usize,
    pub stage: Stage,
    pub operation_id: Option<String>,
    pub code: Option<String>,
    pub plan: Option<PreparedAction>,
    /// Owner-attributed revision changes, never inferred from a later snapshot.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub revision_receipts: Vec<MutationReceipt>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Job {
    pub id: u64,
    pub rule_id: String,
    pub event_id: String,
    pub correlation_id: String,
    pub priority: u8,
    pub state: JobState,
    pub records: Vec<ActionRecord>,
    pub actions: Vec<Action>,
    pub cursor: usize,
    pub deadline_ms: u64,
    pub expected: Revision,
    pub simulated: bool,
    pub busy_policy: BusyPolicy,
    pub failure_policy: FailurePolicy,
    pub lineage: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Decision {
    pub at_ms: u64,
    pub event_id: String,
    pub rule_id: Option<String>,
    pub code: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum DispatchOutcome {
    Simulated,
    Accepted { operation_id: String },
    Completed,
    Rejected(Error),
    Uncertain,
}
/// Evidence created by the Production owner after an attributable mutation.
/// These values are not authorization supplied by an external event or socket.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MutationReceipt {
    pub action_key: String,
    pub operation_id: Option<String>,
    pub before: Revision,
    pub after: Revision,
}
impl MutationReceipt {
    pub fn validate(
        &self,
        action_key: &str,
        before: Revision,
        operation_id: Option<&str>,
    ) -> Result<(), Error> {
        if self.action_key != action_key
            || self.action_key.is_empty()
            || self.action_key.len() > 300
            || self.operation_id.as_deref() != operation_id
            || self
                .operation_id
                .as_ref()
                .is_some_and(|id| id.is_empty() || id.len() > 256)
            || self.before != before
            || self.after.pid != before.pid
            || before.pid == 0
            || self.after.revision < before.revision
        {
            return Err(Error::new(
                "INVALID_MUTATION_RECEIPT",
                "owner receipt does not match the action, operation and exact revision chain",
            ));
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DispatchReport {
    pub outcome: DispatchOutcome,
    pub receipt: Option<MutationReceipt>,
}
impl DispatchReport {
    pub fn legacy(outcome: DispatchOutcome) -> Self {
        Self {
            outcome,
            receipt: None,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum Completion {
    Pending,
    Completed,
    Failed(Error),
    Cancelled,
    Unknown,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PollReport {
    pub completion: Completion,
    pub receipt: Option<MutationReceipt>,
}
impl PollReport {
    pub fn legacy(completion: Completion) -> Self {
        Self {
            completion,
            receipt: None,
        }
    }
}
/// An eventual live adapter must write a durable dispatch intent before mutation.
/// No live adapter ships in this crate. Dispatch is called once per action.
pub trait Backend {
    fn snapshot(&self) -> ProductionSnapshot;
    fn simulated(&self) -> bool;
    fn dispatch(&mut self, action: &PreparedAction, idempotency_key: &str) -> DispatchOutcome;
    fn poll(&mut self, operation_id: &str) -> Completion;
    fn request_cancel(&mut self, operation_id: &str) -> Result<(), Error>;
    /// A live implementation checks this exact revision again on the owner,
    /// persists intent, and dispatches without yielding to another command.
    /// The default retains legacy behavior and grants no revision advancement.
    fn dispatch_checked(
        &mut self,
        action: &PreparedAction,
        action_key: &str,
        _expected: Revision,
    ) -> DispatchReport {
        DispatchReport::legacy(self.dispatch(action, action_key))
    }
    /// A terminal receipt may advance only revisions proven to belong to this
    /// operation. Concurrent UI/MCP changes must never enter that receipt.
    fn poll_checked(
        &mut self,
        operation_id: &str,
        _action_key: &str,
        _expected: Revision,
    ) -> PollReport {
        PollReport::legacy(self.poll(operation_id))
    }
}

fn action_key(job: &Job, index: usize) -> String {
    format!("{}:{}:{}", job.correlation_id, job.id, index)
}

fn accept_revision_receipt(
    job: &mut Job,
    receipt: MutationReceipt,
    operation_id: Option<&str>,
) -> Result<(), Error> {
    let record = job.records.last().ok_or_else(|| {
        Error::new(
            "INVALID_MUTATION_RECEIPT",
            "no action record for owner receipt",
        )
    })?;
    receipt.validate(&action_key(job, record.index), job.expected, operation_id)?;
    if record.revision_receipts.len() >= 2 {
        return Err(Error::new(
            "INVALID_MUTATION_RECEIPT",
            "receipt chain limit exceeded",
        ));
    }
    job.expected = receipt.after;
    job.records
        .last_mut()
        .unwrap()
        .revision_receipts
        .push(receipt);
    Ok(())
}

fn accept_poll_report(job: &mut Job, report: PollReport, simulated: bool) -> Completion {
    if !simulated
        && report.receipt.is_none()
        && matches!(report.completion, Completion::Completed)
        && job
            .records
            .last()
            .and_then(|record| record.plan.as_ref())
            .is_some_and(|plan| matches!(&plan.action, Action::TriggerAnimatedWidget { .. }))
    {
        job.state = JobState::NeedsReconciliation;
        let record = job.records.last_mut().unwrap();
        record.stage = Stage::Uncertain;
        record.code = Some("MISSING_MUTATION_RECEIPT".into());
        return Completion::Unknown;
    }
    if let Some(receipt) = report.receipt {
        let operation_id = job.records.last().and_then(|r| r.operation_id.clone());
        if simulated
            || !matches!(report.completion, Completion::Completed)
            || accept_revision_receipt(job, receipt, operation_id.as_deref()).is_err()
        {
            let record = job.records.last_mut().unwrap();
            record.stage = Stage::Uncertain;
            record.code = Some("INVALID_MUTATION_RECEIPT".into());
            return Completion::Unknown;
        }
    }
    report.completion
}

pub struct Runtime<C: Clock> {
    pub config: Config,
    pub variables: BTreeMap<String, Scalar>,
    pub jobs: Vec<Job>,
    pub decisions: VecDeque<Decision>,
    pub(crate) seen: BTreeSet<String>,
    pub(crate) last_timestamp: BTreeMap<String, u64>,
    pub(crate) cooldowns: BTreeMap<String, u64>,
    pub(crate) debounce: BTreeMap<String, u64>,
    pub(crate) rates: BTreeMap<String, (u64, u32)>,
    pub(crate) next_id: u64,
    pub(crate) clock: C,
    // Shared budget survives child events; only a bounded number of roots are retained.
    pub(crate) budgets: BTreeMap<String, usize>,
}
impl<C: Clock> Runtime<C> {
    pub fn new(config: Config, clock: C) -> Result<Self, Error> {
        config.validate()?;
        Ok(Self {
            variables: config.variables.clone(),
            config,
            jobs: Vec::new(),
            decisions: VecDeque::new(),
            seen: BTreeSet::new(),
            last_timestamp: BTreeMap::new(),
            cooldowns: BTreeMap::new(),
            debounce: BTreeMap::new(),
            rates: BTreeMap::new(),
            next_id: 1,
            clock,
            budgets: BTreeMap::new(),
        })
    }
    fn log(&mut self, event_id: &str, rule_id: Option<&str>, code: &str) {
        if self.decisions.len() == 512 {
            self.decisions.pop_front();
        }
        self.decisions.push_back(Decision {
            at_ms: self.clock.now_ms(),
            event_id: event_id.into(),
            rule_id: rule_id.map(str::to_owned),
            code: code.into(),
        });
    }
    pub fn submit(
        &mut self,
        event: Event,
        trust: &Trust,
        snapshot: &ProductionSnapshot,
    ) -> Result<Vec<u64>, Error> {
        self.prune();
        self.submit_inner(event, trust, snapshot, Vec::new())
    }
    fn submit_inner(
        &mut self,
        event: Event,
        trust: &Trust,
        snapshot: &ProductionSnapshot,
        lineage: Vec<String>,
    ) -> Result<Vec<u64>, Error> {
        event.validate()?;
        if !trust.authorized_origins.contains(&event.origin) {
            self.log(&event.id, None, "UNAUTHORIZED_ORIGIN");
            return Err(Error::new(
                "UNAUTHORIZED_ORIGIN",
                "ingress origin not authorized",
            ));
        }
        let mut keys = vec![format!("id:{}", event.id)];
        if let Some(external) = &event.external_id {
            keys.push(format!("external:{}:{external}", event.origin));
        }
        if keys.iter().any(|k| self.seen.contains(k)) {
            self.log(&event.id, None, "DUPLICATE");
            return Err(Error::new("DUPLICATE", "event already consumed"));
        }
        if self.seen.len() + keys.len() > 8192 {
            return Err(Error::new(
                "JOURNAL_FULL",
                "dedup journal requires explicit new session; no silent eviction",
            ));
        }
        if self.last_timestamp.len() >= 64 && !self.last_timestamp.contains_key(&event.origin) {
            return Err(Error::new("ORIGIN_LIMIT", "too many origins"));
        }
        self.seen.extend(keys);
        if self
            .last_timestamp
            .get(&event.origin)
            .is_some_and(|ts| event.timestamp_ms < *ts)
        {
            self.log(&event.id, None, "OUT_OF_ORDER");
            return Err(Error::new(
                "OUT_OF_ORDER",
                "timestamp regressed within origin",
            ));
        }
        self.last_timestamp
            .insert(event.origin.clone(), event.timestamp_ms);
        let now = self.clock.now_ms();
        let rate = self.rates.entry(event.origin.clone()).or_insert((now, 0));
        if now.saturating_sub(rate.0) >= self.config.rate_window_ms {
            *rate = (now, 0);
        }
        if rate.1 >= self.config.rate_limit {
            self.log(&event.id, None, "RATE_LIMITED");
            return Err(Error::new("RATE_LIMITED", "origin rate limit exceeded"));
        }
        rate.1 += 1;
        let mut selected = Vec::new();
        let mut rules = self.config.rules.clone();
        rules.sort_by_key(|r| std::cmp::Reverse(r.priority));
        let mut reserved = BTreeSet::new();
        for rule in rules {
            if rule.event_kind != event.kind() {
                continue;
            }
            let code=if !rule.enabled { Some("DISABLED") }
                else if lineage.contains(&rule.id)||lineage.len()>=8 { Some("CYCLE_BLOCKED") }
                else if self.debounce.get(&rule.id).is_some_and(|d|now<*d) { Some("DEBOUNCED") }
                else if self.cooldowns.get(&format!("rule:{}",rule.id)).is_some_and(|d|now<*d) || rule.conditions.iter().any(|c|matches!(c,Condition::Cooldown{key,duration_ms} if *duration_ms>0&&reserved.contains(key))) {Some("COOLDOWN")}
                else if !rule.conditions.iter().all(|c|self.matches(c,&event,trust,snapshot)) { Some("CONDITIONS_FALSE") }
                else { None };
            if let Some(code) = code {
                self.log(&event.id, Some(&rule.id), code);
            } else {
                for c in &rule.conditions {
                    if let Condition::Cooldown { key, duration_ms } = c
                        && *duration_ms > 0
                    {
                        reserved.insert(key.clone());
                    }
                }
                selected.push(rule);
            }
        }
        let count = selected
            .iter()
            .try_fold(0usize, |n, r| Ok(n + flatten(&r.actions)?.len()))?;
        let used = *self.budgets.get(&event.correlation_id).unwrap_or(&0);
        if count + used > self.config.max_actions_per_event {
            self.log(&event.id, None, "ACTION_LIMIT");
            return Err(Error::new(
                "ACTION_LIMIT",
                "correlated event action budget exceeded",
            ));
        }
        if self
            .jobs
            .iter()
            .filter(|j| !j.state.terminal() || j.state == JobState::NeedsReconciliation)
            .count()
            + selected.len()
            > self.config.queue_capacity
        {
            self.log(&event.id, None, "QUEUE_FULL");
            return Err(Error::new(
                "QUEUE_FULL",
                "atomic event admission rejected; queue full",
            ));
        }
        if self.budgets.len() >= 4096 && !self.budgets.contains_key(&event.correlation_id) {
            return Err(Error::new("JOURNAL_FULL", "correlation journal full"));
        }
        self.budgets
            .insert(event.correlation_id.clone(), used + count);
        let mut ids = Vec::new();
        for rule in selected {
            self.cooldowns.insert(
                format!("rule:{}", rule.id),
                now.saturating_add(rule.cooldown_ms),
            );
            self.debounce
                .insert(rule.id.clone(), now.saturating_add(rule.debounce_ms));
            for c in &rule.conditions {
                if let Condition::Cooldown { key, duration_ms } = c {
                    self.cooldowns
                        .insert(format!("condition:{key}"), now.saturating_add(*duration_ms));
                }
            }
            let mut path = lineage.clone();
            path.push(rule.id.clone());
            let id = self.next_id;
            self.next_id = self
                .next_id
                .checked_add(1)
                .ok_or_else(|| Error::new("ID_EXHAUSTED", "job identity exhausted"))?;
            let actions = flatten(&rule.actions)?;
            self.log(&event.id, Some(&rule.id), "QUEUED");
            self.jobs.push(Job {
                id,
                rule_id: rule.id,
                event_id: event.id.clone(),
                correlation_id: event.correlation_id.clone(),
                priority: rule.priority,
                state: JobState::Queued,
                records: Vec::new(),
                actions,
                cursor: 0,
                deadline_ms: now.saturating_add(rule.timeout_ms),
                expected: Revision {
                    pid: snapshot.pid,
                    revision: snapshot.revision,
                },
                simulated: event.simulated,
                busy_policy: rule.busy_policy,
                failure_policy: rule.failure_policy,
                lineage: path,
            });
            ids.push(id);
        }
        Ok(ids)
    }
    fn matches(
        &self,
        c: &Condition,
        event: &Event,
        trust: &Trust,
        snapshot: &ProductionSnapshot,
    ) -> bool {
        match c {
            Condition::Equals { field, value } => event.field(field).as_ref() == Some(value),
            Condition::Numeric {
                field,
                comparison,
                value,
            } => matches!(event.field(field),Some(Scalar::Int(n)) if comparison.matches(n,*value)),
            Condition::Contains {
                field,
                phrase,
                whole_word,
            } => match event.field(field) {
                Some(Scalar::String(text)) => {
                    let text = text.to_lowercase();
                    let phrase = phrase.to_lowercase();
                    if *whole_word {
                        let words: Vec<_> = text
                            .split(|c: char| !c.is_alphanumeric())
                            .filter(|s| !s.is_empty())
                            .collect();
                        let needle: Vec<_> = phrase
                            .split(|c: char| !c.is_alphanumeric())
                            .filter(|s| !s.is_empty())
                            .collect();
                        !needle.is_empty() && words.windows(needle.len()).any(|w| w == needle)
                    } else {
                        text.contains(&phrase)
                    }
                }
                _ => false,
            },
            Condition::Variable { name, value } => self.variables.get(name) == Some(value),
            Condition::Counter {
                name,
                comparison,
                value,
            } => {
                matches!(self.variables.get(name),Some(Scalar::Int(n)) if comparison.matches(*n,*value))
            }
            Condition::Cooldown { key, .. } => self
                .cooldowns
                .get(&format!("condition:{key}"))
                .is_none_or(|d| self.clock.now_ms() >= *d),
            Condition::ProductionActive { active } => snapshot.output_active == *active,
            Condition::AuthorizedOrigin => trust.authorized_origins.contains(&event.origin),
            Condition::AuthorizedUser => {
                matches!(event.field("user_id"),Some(Scalar::String(id)) if trust.authorized_users.contains(&id))
            }
            Condition::ConfidenceAtLeast { milli } => {
                trust.confidence_origins.contains(&event.origin)
                    && matches!(&event.payload,Payload::VoiceKeywordDetected{confidence_milli:Some(n),..} if n>=milli)
            }
        }
    }
    fn prune(&mut self) {
        let disposable = |j: &Job| j.state.terminal() && j.state != JobState::NeedsReconciliation;
        let mut terminal = self.jobs.iter().filter(|j| disposable(j)).count();
        self.jobs.retain(|j| {
            if terminal > 128 && disposable(j) {
                terminal -= 1;
                false
            } else {
                true
            }
        });
    }
    pub fn cancel<B: Backend>(&mut self, id: u64, backend: &mut B) -> Result<(), Error> {
        let j = self
            .jobs
            .iter_mut()
            .find(|j| j.id == id)
            .ok_or_else(|| Error::new("UNKNOWN_JOB", "job not found"))?;
        if j.state.terminal() {
            return Ok(());
        }
        if j.state == JobState::AwaitingCompletion {
            if backend.snapshot().pid != j.expected.pid {
                j.state = JobState::NeedsReconciliation;
                return Err(Error::new(
                    "CORE_RESTARTED",
                    "native operation belongs to another process",
                ));
            }
            let op = j
                .records
                .last()
                .and_then(|r| r.operation_id.as_ref())
                .ok_or_else(|| {
                    Error::new(
                        "MISSING_OPERATION",
                        "cannot safely cancel unknown operation",
                    )
                })?;
            backend.request_cancel(op)?;
            // Cancellation request is not native completion; reconciliation remains necessary.
            j.state = JobState::NeedsReconciliation;
            j.records.last_mut().unwrap().code = Some("CANCEL_REQUESTED".into());
        } else {
            j.state = JobState::Cancelled;
        }
        self.log("local", None, "CANCEL_REQUESTED");
        Ok(())
    }
    /// Explicit observation only: never dispatches or resumes the remaining sequence.
    pub fn reconcile<B: Backend>(&mut self, id: u64, backend: &mut B) -> Result<JobState, Error> {
        let j = self
            .jobs
            .iter_mut()
            .find(|j| j.id == id)
            .ok_or_else(|| Error::new("UNKNOWN_JOB", "job not found"))?;
        if j.state != JobState::NeedsReconciliation {
            return Err(Error::new(
                "RECONCILIATION_NOT_REQUIRED",
                "job is not awaiting reconciliation",
            ));
        }
        if backend.snapshot().pid != j.expected.pid {
            return Err(Error::new(
                "CORE_RESTARTED",
                "native operation belongs to another process",
            ));
        }
        let record = j
            .records
            .last()
            .ok_or_else(|| Error::new("MISSING_OPERATION", "no dispatch evidence"))?;
        let operation = record.operation_id.as_ref().ok_or_else(|| {
            Error::new(
                "MISSING_OPERATION",
                "uncertain transport requires manual owner-side reconciliation",
            )
        })?;
        let report = backend.poll_checked(operation, &action_key(j, record.index), j.expected);
        let completion = accept_poll_report(j, report, backend.simulated());
        let record = j.records.last_mut().unwrap();
        match completion {
            Completion::Completed => {
                record.stage = Stage::Completed;
                j.state = if j.cursor + 1 == j.actions.len() {
                    JobState::Completed
                } else {
                    JobState::Cancelled
                };
            }
            Completion::Cancelled => {
                record.stage = Stage::Cancelled;
                j.state = JobState::Cancelled;
            }
            Completion::Failed(error) => {
                record.stage = Stage::Failed;
                record.code = Some(error.code);
                j.state = JobState::Failed;
            }
            Completion::Pending | Completion::Unknown => {}
        }
        Ok(j.state.clone())
    }
    /// One action per ready job per tick. Stable priority/FIFO order; no sleeps or media clock.
    pub fn tick<B: Backend>(&mut self, backend: &mut B) {
        let mut order: Vec<_> = self
            .jobs
            .iter()
            .filter(|j| !j.state.terminal())
            .map(|j| (j.priority, j.id))
            .collect();
        order.sort_by_key(|(priority, id)| (std::cmp::Reverse(*priority), *id));
        for (_, id) in order {
            if let Some(i) = self.jobs.iter().position(|j| j.id == id) {
                self.step(i, backend);
            }
        }
        self.prune();
    }
    fn step<B: Backend>(&mut self, index: usize, backend: &mut B) {
        if self.clock.now_ms() >= self.jobs[index].deadline_ms {
            let j = &mut self.jobs[index];
            j.state = if j.state == JobState::AwaitingCompletion {
                JobState::NeedsReconciliation
            } else {
                JobState::TimedOut
            };
            self.log("local", None, "TIMEOUT_NO_RETRY");
            return;
        }
        if self.jobs[index].state == JobState::AwaitingCompletion {
            if backend.snapshot().pid != self.jobs[index].expected.pid {
                self.jobs[index].state = JobState::NeedsReconciliation;
                self.jobs[index].records.last_mut().unwrap().code = Some("CORE_RESTARTED".into());
                return;
            }
            let op = self.jobs[index]
                .records
                .last()
                .unwrap()
                .operation_id
                .clone()
                .unwrap();
            let job = &self.jobs[index];
            let report = backend.poll_checked(
                &op,
                &action_key(job, job.records.last().unwrap().index),
                job.expected,
            );
            let completion = accept_poll_report(&mut self.jobs[index], report, backend.simulated());
            match completion {
                Completion::Pending => return,
                Completion::Completed => {
                    let j = &mut self.jobs[index];
                    j.records.last_mut().unwrap().stage = Stage::Completed;
                    j.cursor += 1;
                    j.state = JobState::Running;
                }
                Completion::Failed(e) => {
                    let j = &mut self.jobs[index];
                    j.state = JobState::Failed;
                    j.records.last_mut().unwrap().stage = Stage::Failed;
                    j.records.last_mut().unwrap().code = Some(e.code);
                    return;
                }
                Completion::Cancelled => {
                    self.jobs[index].state = JobState::Cancelled;
                    return;
                }
                Completion::Unknown => {
                    self.jobs[index].state = JobState::NeedsReconciliation;
                    return;
                }
            }
        }
        if self.jobs[index].cursor >= self.jobs[index].actions.len() {
            self.finish(index, backend.simulated());
            return;
        }
        let action = self.jobs[index].actions[self.jobs[index].cursor].clone();
        let snapshot = backend.snapshot();
        let expected = self.jobs[index].expected;
        let prepared = match prepare(&action, &snapshot, Some(expected)) {
            Ok(p) => p,
            Err(e) => {
                let j = &mut self.jobs[index];
                if j.busy_policy == BusyPolicy::Defer
                    && [
                        "BUSY",
                        "PRODUCTION_BUSY",
                        "SOURCE_NOT_READY",
                        "TRANSITION_BUSY",
                        "ANIMATION_BUSY",
                        "STRUCTURAL_BUSY",
                    ]
                    .contains(&e.code.as_str())
                {
                    j.state = JobState::Deferred;
                    return;
                }
                j.records.push(ActionRecord {
                    index: j.cursor,
                    stage: Stage::Rejected,
                    operation_id: None,
                    code: Some(e.code.clone()),
                    plan: None,
                    revision_receipts: Vec::new(),
                });
                if e.code == "CAPABILITY_UNAVAILABLE"
                    && j.failure_policy == FailurePolicy::ContinueUnavailable
                {
                    j.cursor += 1;
                    j.state = JobState::Running;
                } else {
                    j.state = JobState::Rejected;
                }
                return;
            }
        };
        let j = &mut self.jobs[index];
        j.records.push(ActionRecord {
            index: j.cursor,
            stage: Stage::Validated,
            operation_id: None,
            code: None,
            plan: Some(prepared.clone()),
            revision_receipts: Vec::new(),
        });
        j.records.last_mut().unwrap().stage = Stage::Prepared;
        if !backend.simulated() && j.simulated {
            j.state = JobState::Rejected;
            j.records.last_mut().unwrap().code = Some("SIMULATION_ONLY".into());
            j.records.last_mut().unwrap().stage = Stage::Rejected;
            return;
        }
        match action {
            Action::IncrementCounter { name, amount } => {
                let old = match self.variables.get(&name) {
                    Some(Scalar::Int(n)) => *n,
                    None if self.variables.len() < 128 => 0,
                    _ => {
                        self.fail_local(index, "VARIABLE_TYPE");
                        return;
                    }
                };
                if let Some(value) = old.checked_add(amount) {
                    self.variables.insert(name, Scalar::Int(value));
                } else {
                    self.fail_local(index, "COUNTER_OVERFLOW");
                    return;
                }
                self.complete_local(index, backend.simulated());
            }
            Action::Notify { .. } | Action::PrepareSpeech { .. } => {
                self.complete_local(index, backend.simulated())
            }
            Action::EmitEvent { name } => {
                let job = &self.jobs[index];
                let event = Event {
                    schema_version: 1,
                    id: format!("internal-{}-{}", job.id, job.cursor),
                    origin: "runtime".into(),
                    timestamp_ms: self.clock.now_ms(),
                    correlation_id: job.correlation_id.clone(),
                    external_id: None,
                    simulated: job.simulated,
                    payload: Payload::CustomEvent {
                        name,
                        fields: BTreeMap::new(),
                    },
                };
                let trust = Trust {
                    authorized_origins: BTreeSet::from(["runtime".into()]),
                    ..Trust::default()
                };
                let lineage = job.lineage.clone();
                match self.submit_inner(event, &trust, &snapshot, lineage) {
                    Ok(_) => self.complete_local(index, backend.simulated()),
                    Err(e) => self.fail_local(index, &e.code),
                }
            }
            _ => {
                let j = &mut self.jobs[index];
                j.records.last_mut().unwrap().stage = Stage::Sent;
                let key = action_key(j, j.cursor);
                let report = backend.dispatch_checked(&prepared, &key, j.expected);
                if !backend.simulated()
                    && matches!(&prepared.action, Action::TriggerAnimatedWidget { .. })
                    && report.receipt.is_none()
                    && matches!(
                        report.outcome,
                        DispatchOutcome::Accepted { .. } | DispatchOutcome::Completed
                    )
                {
                    j.state = JobState::NeedsReconciliation;
                    let record = j.records.last_mut().unwrap();
                    record.stage = Stage::Uncertain;
                    record.code = Some("MISSING_MUTATION_RECEIPT".into());
                    if let DispatchOutcome::Accepted { operation_id } = report.outcome {
                        record.operation_id = Some(operation_id);
                    }
                    return;
                }
                if let Some(receipt) = report.receipt {
                    let operation = match &report.outcome {
                        DispatchOutcome::Accepted { operation_id } => Some(operation_id.as_str()),
                        _ => None,
                    };
                    if backend.simulated()
                        || !matches!(
                            report.outcome,
                            DispatchOutcome::Accepted { .. } | DispatchOutcome::Completed
                        )
                        || accept_revision_receipt(j, receipt, operation).is_err()
                    {
                        j.state = JobState::NeedsReconciliation;
                        let record = j.records.last_mut().unwrap();
                        record.stage = Stage::Uncertain;
                        record.code = Some("INVALID_MUTATION_RECEIPT".into());
                        record.operation_id = operation.map(str::to_owned);
                        return;
                    }
                }
                match report.outcome {
                    DispatchOutcome::Simulated => self.complete_local(index, true),
                    DispatchOutcome::Completed => self.complete_local(index, false),
                    DispatchOutcome::Accepted { operation_id } => {
                        let j = &mut self.jobs[index];
                        let r = j.records.last_mut().unwrap();
                        r.stage = Stage::Accepted;
                        r.operation_id = Some(operation_id);
                        j.state = JobState::AwaitingCompletion;
                    }
                    DispatchOutcome::Rejected(e) => {
                        let j = &mut self.jobs[index];
                        j.state = JobState::Rejected;
                        let r = j.records.last_mut().unwrap();
                        r.stage = Stage::Rejected;
                        r.code = Some(e.code);
                    }
                    DispatchOutcome::Uncertain => {
                        let j = &mut self.jobs[index];
                        j.state = JobState::NeedsReconciliation;
                        j.records.last_mut().unwrap().stage = Stage::Uncertain;
                    }
                }
            }
        }
        if self.jobs[index].state == JobState::Running
            && self.jobs[index].cursor >= self.jobs[index].actions.len()
        {
            self.finish(index, backend.simulated());
        }
    }
    fn fail_local(&mut self, i: usize, code: &str) {
        let j = &mut self.jobs[i];
        j.state = JobState::Failed;
        let r = j.records.last_mut().unwrap();
        r.stage = Stage::Failed;
        r.code = Some(code.into());
    }
    fn complete_local(&mut self, i: usize, simulated: bool) {
        let j = &mut self.jobs[i];
        j.records.last_mut().unwrap().stage = if simulated {
            Stage::Simulated
        } else {
            Stage::Completed
        };
        j.cursor += 1;
        j.state = JobState::Running;
    }
    fn finish(&mut self, i: usize, simulated: bool) {
        self.jobs[i].state = if simulated {
            JobState::Simulated
        } else {
            JobState::Completed
        };
    }
}
pub fn revision(snapshot: &ProductionSnapshot) -> Revision {
    Revision {
        pid: snapshot.pid,
        revision: snapshot.revision,
    }
}
