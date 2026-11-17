//! Future provider ingress contracts and an executable synthetic money normalizer.
//! No networking, OAuth, real provider authentication or credentials ship here.
use crate::model::{Error, Event, Payload, validate_id, validate_text};
use crate::runtime::Trust;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Provider {
    Synthetic,
    LocalVoice,
    Twitch,
    YouTube,
    OfficialDonation,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderCapabilities {
    pub provider: Provider,
    pub adapter_implemented: bool,
    pub synthetic_only: bool,
    pub requires_verified_session: bool,
    pub event_contracts: Vec<String>,
}
pub fn capabilities(provider: Provider) -> ProviderCapabilities {
    let events: &[&str] = match provider {
        Provider::Synthetic => &["viewer.donation", "chat.command", "voice.keyword_detected"],
        Provider::LocalVoice => &["voice.keyword_detected"],
        Provider::Twitch => &[
            "chat.message",
            "chat.command",
            "viewer.follow",
            "viewer.subscribe",
            "viewer.reward_redeemed",
            "motive.custom_event",
        ],
        Provider::YouTube => &[
            "chat.message",
            "chat.command",
            "viewer.subscribe",
            "motive.custom_event",
        ],
        Provider::OfficialDonation => &["viewer.donation"],
    };
    ProviderCapabilities {
        provider,
        adapter_implemented: provider == Provider::Synthetic,
        synthetic_only: true,
        requires_verified_session: provider != Provider::Synthetic,
        event_contracts: events.iter().map(|s| (*s).into()).collect(),
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub enum TransportHealth {
    Unsupported,
    Disconnected,
    Connecting,
    Connected {
        session_generation: u64,
    },
    Backoff {
        attempt: u8,
        retry_at_monotonic_ms: u64,
    },
    AuthorizationDenied,
    Stopped,
}

/// Values here are semantic provider units, never interchangeable money values.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderSemantic {
    CreatorDonation,
    TwitchBits,
    TwitchCharityDonation,
    YouTubeSuperChat,
    YouTubeSuperSticker,
}

/// Host-produced ingress authority. Intentionally not Serialize/Deserialize.
/// Only simulation can construct one in this increment. A future verified
/// transport adapter must add its constructor after authenticated session,
/// channel and provider-message validation; an event cannot claim those facts.
#[derive(Clone, Debug)]
pub struct VerifiedIngress {
    origin: String,
    users: BTreeSet<String>,
}
impl VerifiedIngress {
    pub fn simulation(origin: &str, authorized_users: BTreeSet<String>) -> Result<Self, Error> {
        validate_id(origin)?;
        if origin != "simulation" && !origin.starts_with("simulation.") {
            return Err(Error::new(
                "SIMULATION_ORIGIN_REQUIRED",
                "Synthetic ingress must use the simulation namespace",
            ));
        }
        if authorized_users.len() > 128 {
            return Err(Error::new(
                "USER_LIMIT",
                "At most 128 synthetic authorized users",
            ));
        }
        for user in &authorized_users {
            validate_id(user)?;
        }
        Ok(Self {
            origin: origin.into(),
            users: authorized_users,
        })
    }
    pub fn origin(&self) -> &str {
        &self.origin
    }
    pub fn accept(&self, event: Event) -> Result<AcceptedEvent, Error> {
        event.validate()?;
        if event.origin != self.origin || !event.simulated {
            return Err(Error::new(
                "INGRESS_MISMATCH",
                "Synthetic ingress cannot authorize another origin or real events",
            ));
        }
        Ok(AcceptedEvent {
            event,
            trust: Trust {
                authorized_origins: BTreeSet::from([self.origin.clone()]),
                authorized_users: self.users.clone(),
                // Synthetic confidence is never verified recognizer evidence.
                confidence_origins: BTreeSet::new(),
            },
        })
    }
}

/// Event and out-of-band authority travel together inside the trusted host.
/// Viewer JSON cannot deserialize this wrapper or supply its Trust.
pub struct AcceptedEvent {
    event: Event,
    trust: Trust,
}
impl AcceptedEvent {
    pub fn event(&self) -> &Event {
        &self.event
    }
    pub fn into_parts(self) -> (Event, Trust) {
        (self.event, self.trust)
    }
}

/// Future adapter interface only: no real adapter or worker is instantiated.
pub trait SourceAdapter {
    fn capabilities(&self) -> ProviderCapabilities;
    fn health(&self) -> TransportHealth;
    fn drain(&mut self, maximum: usize) -> Result<Vec<AcceptedEvent>, Error>;
    fn stop(&mut self);
}

/// Explicit small currency table for synthetic fixtures, not a claim of global
/// currency support. Provider integer micros/minor-units must use their own
/// validated normalizer instead of parsing localized display-money strings.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Currency {
    USD,
    EUR,
    PEN,
    JPY,
    KWD,
}
impl Currency {
    pub fn code(self) -> &'static str {
        match self {
            Self::USD => "USD",
            Self::EUR => "EUR",
            Self::PEN => "PEN",
            Self::JPY => "JPY",
            Self::KWD => "KWD",
        }
    }
    pub fn exponent(self) -> u32 {
        match self {
            Self::JPY => 0,
            Self::KWD => 3,
            _ => 2,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DonationInput {
    pub id: String,
    pub correlation_id: String,
    pub external_id: Option<String>,
    pub timestamp_ms: u64,
    pub semantic: ProviderSemantic,
    pub user_id: String,
    pub amount_decimal: String,
    pub currency: Currency,
    pub message: String,
}

/// Exact decimal parsing for controlled synthetic inputs; never rounds money.
pub fn minor_units(decimal: &str, currency: Currency) -> Result<u64, Error> {
    let invalid = || {
        Error::new(
            "INVALID_AMOUNT",
            "Use bounded positive ASCII decimal money with exact currency precision",
        )
    };
    if decimal.is_empty() || decimal.len() > 32 {
        return Err(invalid());
    }
    let mut parts = decimal.split('.');
    let whole = parts.next().ok_or_else(invalid)?;
    let fraction = parts.next();
    if whole.is_empty() || !whole.bytes().all(|c| c.is_ascii_digit()) || parts.next().is_some() {
        return Err(invalid());
    }
    let exponent = currency.exponent();
    if fraction.is_some_and(|p| {
        p.is_empty() || p.len() > exponent as usize || !p.bytes().all(|c| c.is_ascii_digit())
    }) {
        return Err(invalid());
    }
    let whole: u64 = whole.parse().map_err(|_| invalid())?;
    let unit = 10_u64.pow(exponent);
    let fraction = if let Some(p) = fraction {
        p.parse::<u64>()
            .map_err(|_| invalid())?
            .checked_mul(10_u64.pow(exponent - p.len() as u32))
            .ok_or_else(invalid)?
    } else {
        0
    };
    let total = whole
        .checked_mul(unit)
        .and_then(|n| n.checked_add(fraction))
        .ok_or_else(invalid)?;
    if total == 0 || total > 1_000_000_000_000 {
        return Err(invalid());
    }
    Ok(total)
}

pub fn normalize_donation(
    ingress: &VerifiedIngress,
    input: DonationInput,
) -> Result<AcceptedEvent, Error> {
    if input.semantic != ProviderSemantic::CreatorDonation {
        return Err(Error::new(
            "DISTINCT_PROVIDER_SEMANTIC",
            "Bits, charity, Super Chat and Super Stickers require distinct normalizers; they are not creator donations",
        ));
    }
    validate_text(&input.message, 4096)?;
    let amount_minor = minor_units(&input.amount_decimal, input.currency)?;
    ingress.accept(Event {
        schema_version: 1,
        id: input.id,
        origin: ingress.origin.clone(),
        timestamp_ms: input.timestamp_ms,
        correlation_id: input.correlation_id,
        external_id: input.external_id,
        simulated: true,
        payload: Payload::ViewerDonation {
            user_id: input.user_id,
            amount_minor,
            currency: input.currency.code().into(),
            message: input.message,
        },
    })
}

/// Pure retry planning. The caller supplies a monotonic clock; this never sleeps
/// or reconnects. Excessive server delays suspend the attempt rather than retry
/// earlier than the provider requested. Deterministic simulation has no jitter.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BackoffPolicy {
    pub initial_ms: u64,
    pub maximum_ms: u64,
    pub maximum_attempts: u8,
}
impl BackoffPolicy {
    pub fn delay_ms(&self, attempt: u8, server_retry_after_ms: Option<u64>) -> Result<u64, Error> {
        if self.initial_ms == 0
            || self.maximum_ms < self.initial_ms
            || self.maximum_ms > 300_000
            || self.maximum_attempts == 0
            || self.maximum_attempts > 16
        {
            return Err(Error::new(
                "INVALID_BACKOFF",
                "Bound retry planning to 16 attempts and 300 seconds",
            ));
        }
        if attempt >= self.maximum_attempts {
            return Err(Error::new(
                "RETRY_EXHAUSTED",
                "Reconnect needs explicit recovery after the attempt budget",
            ));
        }
        if server_retry_after_ms.is_some_and(|delay| delay > self.maximum_ms) {
            return Err(Error::new(
                "RETRY_SUSPENDED",
                "Server rate limit exceeds this retry budget; do not retry early",
            ));
        }
        Ok(self
            .initial_ms
            .saturating_mul(1_u64 << attempt)
            .min(self.maximum_ms)
            .max(server_retry_after_ms.unwrap_or(0)))
    }
}

/// Store only a host-assigned reference to private future cursor storage, never
/// an OAuth token, provider reconnect URL, raw cursor or viewer message. No such
/// private cursor store is implemented in this increment.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReconnectCheckpoint {
    pub schema_version: u16,
    pub provider: Provider,
    pub session_generation: u64,
    pub cursor_ref: Option<String>,
    pub last_external_event_id: Option<String>,
}
impl ReconnectCheckpoint {
    pub fn validate(&self) -> Result<(), Error> {
        if self.schema_version != 1 {
            return Err(Error::new(
                "UNSUPPORTED_SCHEMA",
                "Only reconnect checkpoint schema 1 is supported",
            ));
        }
        if let Some(reference) = &self.cursor_ref {
            validate_id(reference)?;
            if !reference.starts_with("cursor-ref-") || reference.len() <= "cursor-ref-".len() {
                return Err(Error::new(
                    "CURSOR_REFERENCE_REQUIRED",
                    "Only opaque local cursor references may be serialized",
                ));
            }
        }
        if let Some(id) = &self.last_external_event_id {
            validate_id(id)?;
        }
        Ok(())
    }
}
