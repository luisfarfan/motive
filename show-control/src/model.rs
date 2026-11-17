//! Validated platform-independent events. Payloads never establish trust.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const EVENT_SCHEMA_VERSION: u16 = 1;
pub const MAX_JSON_BYTES: usize = 64 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Error {
    pub code: String,
    pub message: String,
}
impl Error {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for Error {}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(
    tag = "type",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Scalar {
    Bool(bool),
    Int(i64),
    String(String),
}

pub fn validate_id(value: &str) -> Result<(), Error> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"-_:.".contains(&c))
    {
        return Err(Error::new(
            "INVALID_ID",
            "Identifiers must contain 1–128 ASCII letters, numbers, '-', '_', ':' or '.'",
        ));
    }
    Ok(())
}
pub fn validate_text(value: &str, maximum: usize) -> Result<(), Error> {
    if value.len() > maximum
        || value
            .chars()
            .any(|c| c.is_control() && c != '\n' && c != '\t')
    {
        return Err(Error::new(
            "INVALID_TEXT",
            "Text exceeds its UTF-8 byte limit or contains a prohibited control character",
        ));
    }
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Event {
    pub schema_version: u16,
    pub id: String,
    pub origin: String,
    /// Provider observation time; never used as a scheduling or media clock.
    pub timestamp_ms: u64,
    pub correlation_id: String,
    pub external_id: Option<String>,
    pub simulated: bool,
    pub payload: Payload,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", deny_unknown_fields)]
pub enum Payload {
    #[serde(rename = "manual.button_pressed")]
    ManualButtonPressed { button_id: String },
    #[serde(rename = "keyboard.shortcut")]
    KeyboardShortcut { shortcut: String },
    #[serde(rename = "voice.keyword_detected")]
    VoiceKeywordDetected {
        keyword: String,
        confidence_milli: Option<u16>,
    },
    #[serde(rename = "chat.message")]
    ChatMessage { user_id: String, text: String },
    #[serde(rename = "chat.command")]
    ChatCommand { user_id: String, command: String },
    #[serde(rename = "viewer.follow")]
    ViewerFollow { user_id: String },
    #[serde(rename = "viewer.subscribe")]
    ViewerSubscribe { user_id: String, tier: String },
    #[serde(rename = "viewer.donation")]
    ViewerDonation {
        user_id: String,
        amount_minor: u64,
        currency: String,
        message: String,
    },
    #[serde(rename = "viewer.reward_redeemed")]
    ViewerRewardRedeemed {
        user_id: String,
        reward_id: String,
        input: String,
    },
    #[serde(rename = "timer.completed")]
    TimerCompleted { timer_id: String },
    #[serde(rename = "production.started")]
    ProductionStarted { output_id: String },
    #[serde(rename = "production.stopped")]
    ProductionStopped { output_id: String },
    #[serde(rename = "motive.custom_event")]
    CustomEvent {
        name: String,
        fields: BTreeMap<String, Scalar>,
    },
}

impl Event {
    pub fn from_json(input: &str) -> Result<Self, Error> {
        if input.len() > MAX_JSON_BYTES {
            return Err(Error::new("INPUT_TOO_LARGE", "Event exceeds 64 KiB"));
        }
        let event: Self = serde_json::from_str(input)
            .map_err(|_| Error::new("INVALID_JSON", "Invalid event schema or JSON"))?;
        event.validate()?;
        Ok(event)
    }
    pub fn kind(&self) -> &'static str {
        self.payload.kind()
    }
    pub fn validate(&self) -> Result<(), Error> {
        if self.schema_version != EVENT_SCHEMA_VERSION {
            return Err(Error::new(
                "UNSUPPORTED_SCHEMA",
                "Only event schema 1 is supported",
            ));
        }
        for id in [&self.id, &self.origin, &self.correlation_id] {
            validate_id(id)?;
        }
        if let Some(id) = &self.external_id {
            validate_id(id)?;
        }
        self.payload.validate()
    }
    /// Bounded, explicit fields; no JSONPath or expression interpreter.
    pub fn field(&self, key: &str) -> Option<Scalar> {
        match key {
            "kind" => Some(Scalar::String(self.kind().into())),
            "origin" => Some(Scalar::String(self.origin.clone())),
            "simulated" => Some(Scalar::Bool(self.simulated)),
            _ => self.payload.field(key),
        }
    }
}

impl Payload {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::ManualButtonPressed { .. } => "manual.button_pressed",
            Self::KeyboardShortcut { .. } => "keyboard.shortcut",
            Self::VoiceKeywordDetected { .. } => "voice.keyword_detected",
            Self::ChatMessage { .. } => "chat.message",
            Self::ChatCommand { .. } => "chat.command",
            Self::ViewerFollow { .. } => "viewer.follow",
            Self::ViewerSubscribe { .. } => "viewer.subscribe",
            Self::ViewerDonation { .. } => "viewer.donation",
            Self::ViewerRewardRedeemed { .. } => "viewer.reward_redeemed",
            Self::TimerCompleted { .. } => "timer.completed",
            Self::ProductionStarted { .. } => "production.started",
            Self::ProductionStopped { .. } => "production.stopped",
            Self::CustomEvent { .. } => "motive.custom_event",
        }
    }
    pub fn validate(&self) -> Result<(), Error> {
        match self {
            Self::ManualButtonPressed { button_id } => validate_id(button_id),
            Self::KeyboardShortcut { shortcut } => {
                validate_text(shortcut, 64)?;
                if shortcut.is_empty() {
                    return Err(Error::new("INVALID_SHORTCUT", "Shortcut is empty"));
                }
                Ok(())
            }
            Self::VoiceKeywordDetected {
                keyword,
                confidence_milli,
            } => {
                validate_text(keyword, 256)?;
                if keyword.trim().is_empty() || confidence_milli.is_some_and(|n| n > 1000) {
                    return Err(Error::new(
                        "INVALID_VOICE_PAYLOAD",
                        "Nonempty keyword and confidence in 0–1000 required",
                    ));
                }
                Ok(())
            }
            Self::ChatMessage { user_id, text } => {
                validate_id(user_id)?;
                validate_text(text, 4096)
            }
            Self::ChatCommand { user_id, command } => {
                validate_id(user_id)?;
                validate_id(command)
            }
            Self::ViewerFollow { user_id } => validate_id(user_id),
            Self::ViewerSubscribe { user_id, tier } => {
                validate_id(user_id)?;
                validate_id(tier)
            }
            Self::ViewerDonation {
                user_id,
                amount_minor,
                currency,
                message,
            } => {
                validate_id(user_id)?;
                validate_text(message, 4096)?;
                if *amount_minor == 0
                    || *amount_minor > 1_000_000_000_000
                    || currency.len() != 3
                    || !currency.bytes().all(|b| b.is_ascii_uppercase())
                {
                    return Err(Error::new(
                        "INVALID_DONATION",
                        "Donation needs bounded positive minor units and a three-letter uppercase currency",
                    ));
                }
                Ok(())
            }
            Self::ViewerRewardRedeemed {
                user_id,
                reward_id,
                input,
            } => {
                validate_id(user_id)?;
                validate_id(reward_id)?;
                validate_text(input, 4096)
            }
            Self::TimerCompleted { timer_id } => validate_id(timer_id),
            Self::ProductionStarted { output_id } | Self::ProductionStopped { output_id } => {
                validate_id(output_id)
            }
            Self::CustomEvent { name, fields } => {
                validate_id(name)?;
                if fields.len() > 16 {
                    return Err(Error::new(
                        "PAYLOAD_LIMIT",
                        "Custom events have at most 16 fields",
                    ));
                }
                let mut bytes = 0;
                for (key, value) in fields {
                    validate_id(key)?;
                    // Metadata keys cannot be shadowed by payload fields.
                    if matches!(key.as_str(), "kind" | "origin" | "simulated" | "name") {
                        return Err(Error::new(
                            "RESERVED_FIELD",
                            "Custom payload cannot shadow envelope metadata",
                        ));
                    }
                    bytes += key.len();
                    if let Scalar::String(text) = value {
                        validate_text(text, 4096)?;
                        bytes += text.len();
                    }
                }
                if bytes > 4096 {
                    return Err(Error::new(
                        "PAYLOAD_LIMIT",
                        "Custom payload text exceeds 4096 bytes",
                    ));
                }
                Ok(())
            }
        }
    }
    fn field(&self, key: &str) -> Option<Scalar> {
        let string = |s: &String| Some(Scalar::String(s.clone()));
        match (self, key) {
            (Self::ManualButtonPressed { button_id }, "button_id") => string(button_id),
            (Self::KeyboardShortcut { shortcut }, "shortcut") => string(shortcut),
            (Self::VoiceKeywordDetected { keyword, .. }, "keyword") => string(keyword),
            (
                Self::VoiceKeywordDetected {
                    confidence_milli: Some(value),
                    ..
                },
                "confidence_milli",
            ) => Some(Scalar::Int(i64::from(*value))),
            (Self::ChatMessage { text, .. }, "text") => string(text),
            (Self::ChatCommand { command, .. }, "command") => string(command),
            (Self::ViewerSubscribe { tier, .. }, "tier") => string(tier),
            (Self::ViewerDonation { amount_minor, .. }, "amount_minor") => {
                i64::try_from(*amount_minor).ok().map(Scalar::Int)
            }
            (Self::ViewerDonation { currency, .. }, "currency") => string(currency),
            (Self::ViewerDonation { message, .. }, "message") => string(message),
            (Self::ViewerRewardRedeemed { reward_id, .. }, "reward_id") => string(reward_id),
            (Self::ViewerRewardRedeemed { input, .. }, "input") => string(input),
            (Self::TimerCompleted { timer_id }, "timer_id") => string(timer_id),
            (
                Self::ProductionStarted { output_id } | Self::ProductionStopped { output_id },
                "output_id",
            ) => string(output_id),
            (
                Self::ChatMessage { user_id, .. }
                | Self::ChatCommand { user_id, .. }
                | Self::ViewerFollow { user_id }
                | Self::ViewerSubscribe { user_id, .. }
                | Self::ViewerDonation { user_id, .. }
                | Self::ViewerRewardRedeemed { user_id, .. },
                "user_id",
            ) => string(user_id),
            (Self::CustomEvent { name, .. }, "name") => string(name),
            (Self::CustomEvent { fields, .. }, key) => fields.get(key).cloned(),
            _ => None,
        }
    }
}
