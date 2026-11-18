//! Explicit offline checkpoints. Restore never replays queued or dispatched mutations.
use crate::model::{Error, Scalar};
use crate::runtime::{Clock, Config, Job, JobState, Runtime};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Checkpoint {
    schema_version: u16,
    config: Config,
    variables: BTreeMap<String, Scalar>,
    seen: BTreeSet<String>,
    last_timestamp: BTreeMap<String, u64>,
    cooldown_remaining: BTreeMap<String, u64>,
    debounce_remaining: BTreeMap<String, u64>,
    rate_remaining: BTreeMap<String, (u64, u32)>,
    next_id: u64,
    budgets: BTreeMap<String, usize>,
    jobs: Vec<Job>,
}
/// Documented draft-v0 migration fixture, not a Motive project schema.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct DraftCheckpoint {
    schema_version: u16,
    config: Config,
    variables: BTreeMap<String, Scalar>,
    consumed_event_ids: Vec<String>,
}

impl<C: Clock> Runtime<C> {
    pub fn checkpoint(&self) -> Result<String, Error> {
        let now = self.clock.now_ms();
        let remaining = |map: &BTreeMap<String, u64>| {
            map.iter()
                .map(|(k, d)| (k.clone(), d.saturating_sub(now)))
                .collect()
        };
        let checkpoint = Checkpoint {
            schema_version: if self.jobs.iter().any(|job| {
                job.records
                    .iter()
                    .any(|record| record.terminal_receipt.is_some())
            }) {
                3
            } else if self.jobs.iter().any(|job| {
                job.records
                    .iter()
                    .any(|record| !record.revision_receipts.is_empty())
            }) {
                2
            } else {
                1
            },
            config: self.config.clone(),
            variables: self.variables.clone(),
            seen: self.seen.clone(),
            last_timestamp: self.last_timestamp.clone(),
            cooldown_remaining: remaining(&self.cooldowns),
            debounce_remaining: remaining(&self.debounce),
            rate_remaining: self
                .rates
                .iter()
                .map(|(k, (start, n))| {
                    (
                        k.clone(),
                        (
                            start
                                .saturating_add(self.config.rate_window_ms)
                                .saturating_sub(now),
                            *n,
                        ),
                    )
                })
                .collect(),
            next_id: self.next_id,
            budgets: self.budgets.clone(),
            jobs: self.jobs.clone(),
        };
        serde_json::to_string_pretty(&checkpoint)
            .map_err(|_| Error::new("SERIALIZE", "checkpoint serialization failed"))
    }
    pub fn restore(json: &str, clock: C) -> Result<Self, Error> {
        if json.len() > 16_777_216 {
            return Err(Error::new("INPUT_TOO_LARGE", "checkpoint exceeds 16 MiB"));
        }
        let value: serde_json::Value = serde_json::from_str(json)
            .map_err(|_| Error::new("INVALID_JSON", "invalid checkpoint JSON"))?;
        let version = value
            .get("schema_version")
            .and_then(serde_json::Value::as_u64)
            .ok_or_else(|| Error::new("UNKNOWN_SCHEMA", "missing checkpoint version"))?;
        let state: Checkpoint = match version {
            1..=3 => serde_json::from_value(value)
                .map_err(|_| Error::new("INVALID_CHECKPOINT", "malformed checkpoint fields"))?,
            0 => {
                let old: DraftCheckpoint = serde_json::from_value(value)
                    .map_err(|_| Error::new("INVALID_CHECKPOINT", "invalid draft-v0 checkpoint"))?;
                if old.consumed_event_ids.len() > 8192 {
                    return Err(Error::new("INVALID_CHECKPOINT", "too many consumed events"));
                }
                Checkpoint {
                    schema_version: 1,
                    config: old.config,
                    variables: old.variables,
                    seen: old
                        .consumed_event_ids
                        .into_iter()
                        .map(|id| format!("id:{id}"))
                        .collect(),
                    last_timestamp: BTreeMap::new(),
                    cooldown_remaining: BTreeMap::new(),
                    debounce_remaining: BTreeMap::new(),
                    rate_remaining: BTreeMap::new(),
                    next_id: 1,
                    budgets: BTreeMap::new(),
                    jobs: Vec::new(),
                }
            }
            _ => return Err(Error::new("UNKNOWN_SCHEMA", "unknown checkpoint version")),
        };
        state.config.validate()?;
        let mut variable_check = state.config.clone();
        variable_check.variables = state.variables.clone();
        variable_check.validate()?;
        if state.seen.len() > 8192
            || state.seen.iter().any(|s| s.len() > 300)
            || state.last_timestamp.len() > 64
            || state.cooldown_remaining.len() > 1088
            || state.debounce_remaining.len() > 64
            || state.rate_remaining.len() > 64
            || state.budgets.len() > 4096
            || state.jobs.len() > state.config.queue_capacity + 128
            || state.cooldown_remaining.values().any(|v| *v > 3_600_000)
            || state.debounce_remaining.values().any(|v| *v > 60_000)
            || state
                .rate_remaining
                .values()
                .any(|(ms, n)| *ms > state.config.rate_window_ms || *n > state.config.rate_limit)
            || state
                .budgets
                .values()
                .any(|n| *n > state.config.max_actions_per_event)
        {
            return Err(Error::new(
                "INVALID_CHECKPOINT",
                "checkpoint limits exceeded",
            ));
        }
        let mut ids = BTreeSet::new();
        for job in &state.jobs {
            if job.id >= state.next_id
                || !ids.insert(job.id)
                || job.actions.len() > 32
                || job.cursor > job.actions.len()
                || job.records.len() > 32
                || job.lineage.len() > 8
                || !state.config.rules.iter().any(|r| r.id == job.rule_id)
                || job.priority > 9
            {
                return Err(Error::new("INVALID_CHECKPOINT", "invalid persisted job"));
            }
            for action in &job.actions {
                action.validate()?;
            }
            for record in &job.records {
                if record.revision_receipts.len() > 2
                    || (state.schema_version < 2 && !record.revision_receipts.is_empty())
                    || (state.schema_version < 3 && record.terminal_receipt.is_some())
                {
                    return Err(Error::new(
                        "INVALID_CHECKPOINT",
                        "invalid receipt schema or count",
                    ));
                }
                let mut previous = None;
                for receipt in &record.revision_receipts {
                    let expected = previous.unwrap_or(receipt.before);
                    receipt.validate(
                        &format!("{}:{}:{}", job.correlation_id, job.id, record.index),
                        expected,
                        record.operation_id.as_deref(),
                    )?;
                    if receipt.after.pid != job.expected.pid {
                        return Err(Error::new(
                            "INVALID_CHECKPOINT",
                            "receipt belongs to another owner",
                        ));
                    }
                    previous = Some(receipt.after);
                }
                if let Some(receipt) = &record.terminal_receipt {
                    let operation = record.operation_id.as_deref().ok_or_else(|| {
                        Error::new("INVALID_CHECKPOINT", "terminal has no accepted operation")
                    })?;
                    receipt.validate(
                        &format!("{}:{}:{}", job.correlation_id, job.id, record.index),
                        operation,
                        job.expected.pid,
                    )?;
                    if record.revision_receipts.len() != 1
                        || record.revision_receipts[0].after != job.expected
                        || record.stage != crate::runtime::Stage::Completed
                        || !matches!(job.state, JobState::Completed | JobState::Cancelled)
                    {
                        return Err(Error::new(
                            "INVALID_CHECKPOINT",
                            "terminal evidence cannot resume or replace dispatch attribution",
                        ));
                    }
                }
                if let Some(plan) = &record.plan {
                    plan.action.validate()?;
                }
            }
        }
        let mut runtime = Self::new(state.config, clock)?;
        let now = runtime.clock.now_ms();
        runtime.variables = state.variables;
        runtime.seen = state.seen;
        runtime.last_timestamp = state.last_timestamp;
        runtime.cooldowns = state
            .cooldown_remaining
            .into_iter()
            .map(|(k, d)| (k, now.saturating_add(d)))
            .collect();
        runtime.debounce = state
            .debounce_remaining
            .into_iter()
            .map(|(k, d)| (k, now.saturating_add(d)))
            .collect();
        // Full conservative window after restart avoids forgetting a rate limit when clock starts at zero.
        runtime.rates = state
            .rate_remaining
            .into_iter()
            .filter(|(_, (remaining, _))| *remaining > 0)
            .map(|(k, (_, n))| (k, (now, n)))
            .collect();
        runtime.next_id = state.next_id;
        runtime.budgets = state.budgets;
        runtime.jobs = state
            .jobs
            .into_iter()
            .map(|mut job| {
                if job.state == JobState::AwaitingCompletion {
                    job.state = JobState::NeedsReconciliation;
                } else if !job.state.terminal() {
                    job.state = JobState::Cancelled;
                }
                job.deadline_ms = now;
                job
            })
            .collect();
        Ok(runtime)
    }
}
