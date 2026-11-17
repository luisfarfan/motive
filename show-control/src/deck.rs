//! Local Live Deck presentation model and deterministic interaction prototype.
//! This module does not connect to Production or authorize live mutations.
use crate::model::Error;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

fn fail(code: &str, message: &str) -> Error {
    Error::new(code, message)
}
fn label(s: &str, max: usize) -> bool {
    !s.trim().is_empty() && s.len() <= max && !s.chars().any(char::is_control)
}
fn identifier(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Deck {
    pub schema_version: u32,
    pub id: String,
    pub name: String,
    pub groups: Vec<DeckGroup>,
    pub buttons: Vec<DeckButton>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DeckGroup {
    pub id: String,
    pub label: String,
    pub order: u16,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DeckButton {
    pub id: String,
    pub group_id: String,
    pub label: String,
    pub icon: DeckIcon,
    pub order: u16,
    pub enabled: bool,
    pub shortcut: Option<Shortcut>,
    pub cooldown_ms: u64,
    pub sensitive: bool,
    pub target: ButtonTarget,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DeckIcon {
    Play,
    Pause,
    Goal,
    Timer,
    Scene,
    Spark,
    Text,
    Bell,
    Stop,
    Layers,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(deny_unknown_fields)]
pub struct Shortcut {
    pub key: String,
    pub command: bool,
    pub option: bool,
    pub shift: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ButtonTarget {
    Rule {
        rule_id: String,
    },
    Overlay {
        source_ref: String,
        show: bool,
    },
    Animation {
        animation_id: String,
    },
    Scene {
        scene_ref: String,
        transition: DeckTransition,
    },
    Countdown {
        source_ref: String,
        reset: bool,
    },
    Composite {
        rule_id: String,
    },
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum DeckTransition {
    Cut,
    Fade { duration_ms: u32 },
}
impl Deck {
    pub fn from_json(input: &str) -> Result<Self, Error> {
        if input.len() > 64 * 1024 {
            return Err(fail("DECK_SIZE", "Deck exceeds 64 KiB"));
        }
        let deck: Self = serde_json::from_str(input)
            .map_err(|_| fail("DECK_SCHEMA", "Malformed or unknown deck field"))?;
        deck.validate()?;
        Ok(deck)
    }
    pub fn validate(&self) -> Result<(), Error> {
        if self.schema_version != 1 || !identifier(&self.id) || !label(&self.name, 128) {
            return Err(fail(
                "DECK_SCHEMA",
                "Version 1 and bounded identity/name required",
            ));
        }
        if self.groups.is_empty()
            || self.groups.len() > 8
            || self.buttons.is_empty()
            || self.buttons.len() > 64
        {
            return Err(fail(
                "DECK_LIMIT",
                "Deck requires 1..8 groups and 1..64 buttons",
            ));
        }
        let mut groups = BTreeSet::new();
        let mut group_orders = BTreeSet::new();
        for group in &self.groups {
            if !identifier(&group.id)
                || !label(&group.label, 64)
                || !groups.insert(group.id.as_str())
                || !group_orders.insert(group.order)
            {
                return Err(fail(
                    "DECK_GROUP",
                    "Group IDs and orders must be unique and bounded",
                ));
            }
        }
        let mut buttons = BTreeSet::new();
        let mut shortcuts = BTreeSet::new();
        let mut orders = BTreeSet::new();
        for button in &self.buttons {
            if !identifier(&button.id)
                || !label(&button.label, 64)
                || !buttons.insert(button.id.as_str())
                || !groups.contains(button.group_id.as_str())
                || !orders.insert((&button.group_id, button.order))
                || button.cooldown_ms > 3600000
            {
                return Err(fail(
                    "DECK_BUTTON",
                    "Invalid identity, group, order or cooldown",
                ));
            }
            if let Some(shortcut) = &button.shortcut {
                let key = &shortcut.key;
                if !(key.len() == 1
                    && key
                        .bytes()
                        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit()))
                    || !shortcuts.insert(shortcut)
                {
                    return Err(fail(
                        "DECK_SHORTCUT",
                        "Shortcuts require a unique ASCII key and explicit modifiers",
                    ));
                }
            }
            let reference = match &button.target {
                ButtonTarget::Rule { rule_id } | ButtonTarget::Composite { rule_id } => rule_id,
                ButtonTarget::Overlay { source_ref, .. }
                | ButtonTarget::Countdown { source_ref, .. } => source_ref,
                ButtonTarget::Animation { animation_id } => animation_id,
                ButtonTarget::Scene {
                    scene_ref,
                    transition,
                } => {
                    if let DeckTransition::Fade { duration_ms } = transition
                        && !(100..=5000).contains(duration_ms)
                    {
                        return Err(fail(
                            "DECK_TRANSITION",
                            "Scene Fade duration must be 100..5000 ms",
                        ));
                    }
                    scene_ref
                }
            };
            if !identifier(reference) {
                return Err(fail(
                    "DECK_REFERENCE",
                    "Targets must be symbolic bounded references, not commands",
                ));
            }
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DeckPress {
    pub request_id: u64,
    pub button_id: String,
    pub event_kind: String,
    pub target: ButtonTarget,
    pub simulated: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub enum ButtonState {
    Ready,
    Disabled,
    AwaitingConfirmation,
    CoolingDown { remaining_ms: u64 },
    Pending { request_id: u64 },
    Simulated,
    Rejected { code: String },
    Cancelled,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DeckHistory {
    pub button_id: String,
    pub request_id: Option<u64>,
    pub timestamp_ms: u64,
    pub state: ButtonState,
}
#[derive(Clone, Debug)]
pub struct DeckRuntime {
    deck: Deck,
    next_request: u64,
    last_now: u64,
    cooldown_until: BTreeMap<String, u64>,
    pending: BTreeMap<String, u64>,
    states: BTreeMap<String, ButtonState>,
    history: VecDeque<DeckHistory>,
}
impl DeckRuntime {
    pub fn new(deck: Deck) -> Result<Self, Error> {
        deck.validate()?;
        Ok(Self {
            deck,
            next_request: 1,
            last_now: 0,
            cooldown_until: BTreeMap::new(),
            pending: BTreeMap::new(),
            states: BTreeMap::new(),
            history: VecDeque::new(),
        })
    }
    pub fn deck(&self) -> &Deck {
        &self.deck
    }
    pub fn history(&self) -> &VecDeque<DeckHistory> {
        &self.history
    }
    fn advance(&mut self, now_ms: u64) -> Result<(), Error> {
        if now_ms < self.last_now {
            return Err(fail(
                "CLOCK_REGRESSION",
                "Monotonic deck time moved backwards",
            ));
        }
        self.last_now = now_ms;
        Ok(())
    }
    fn remember(&mut self, button_id: &str, request_id: Option<u64>, state: ButtonState) {
        self.states.insert(button_id.into(), state.clone());
        self.history.push_back(DeckHistory {
            button_id: button_id.into(),
            request_id,
            timestamp_ms: self.last_now,
            state,
        });
        if self.history.len() > 64 {
            self.history.pop_front();
        }
    }
    pub fn state(&self, button_id: &str, now_ms: u64) -> Result<ButtonState, Error> {
        if now_ms < self.last_now {
            return Err(fail(
                "CLOCK_REGRESSION",
                "Monotonic deck time moved backwards",
            ));
        }
        let button = self
            .deck
            .buttons
            .iter()
            .find(|b| b.id == button_id)
            .ok_or_else(|| fail("DECK_NOT_FOUND", "Unknown deck button"))?;
        if !button.enabled {
            return Ok(ButtonState::Disabled);
        }
        if let Some(request_id) = self.pending.get(button_id) {
            return Ok(ButtonState::Pending {
                request_id: *request_id,
            });
        }
        if let Some(deadline) = self.cooldown_until.get(button_id)
            && *deadline > now_ms
        {
            return Ok(ButtonState::CoolingDown {
                remaining_ms: *deadline - now_ms,
            });
        }
        Ok(match self.states.get(button_id) {
            Some(ButtonState::AwaitingConfirmation) => ButtonState::AwaitingConfirmation,
            _ => ButtonState::Ready,
        })
    }
    /// `confirmed` is a local interaction prototype input, not remote security authorization.
    /// Every returned press is explicitly simulated; future GPUI owns a real confirmation token.
    pub fn press(
        &mut self,
        button_id: &str,
        now_ms: u64,
        confirmed: bool,
    ) -> Result<DeckPress, Error> {
        self.advance(now_ms)?;
        let button = self
            .deck
            .buttons
            .iter()
            .find(|b| b.id == button_id)
            .cloned()
            .ok_or_else(|| fail("DECK_NOT_FOUND", "Unknown deck button"))?;
        match self.state(button_id, now_ms)? {
            ButtonState::Disabled => return Err(fail("DECK_DISABLED", "Button is disabled")),
            ButtonState::Pending { .. } => {
                return Err(fail(
                    "DECK_PENDING",
                    "Observe the previous request before another press",
                ));
            }
            ButtonState::CoolingDown { .. } => {
                return Err(fail("DECK_COOLDOWN", "Button cooldown is active"));
            }
            _ => {}
        }
        if button.sensitive && !confirmed {
            self.remember(button_id, None, ButtonState::AwaitingConfirmation);
            return Err(fail(
                "DECK_CONFIRMATION",
                "Local confirmation required for this simulated action",
            ));
        }
        let request_id = self.next_request;
        self.next_request = self
            .next_request
            .checked_add(1)
            .ok_or_else(|| fail("DECK_EXHAUSTED", "Request counter exhausted"))?;
        let deadline = now_ms
            .checked_add(button.cooldown_ms)
            .ok_or_else(|| fail("CLOCK_OVERFLOW", "Cooldown deadline exceeds clock range"))?;
        self.cooldown_until.insert(button_id.into(), deadline);
        self.pending.insert(button_id.into(), request_id);
        self.remember(
            button_id,
            Some(request_id),
            ButtonState::Pending { request_id },
        );
        Ok(DeckPress {
            request_id,
            button_id: button_id.into(),
            event_kind: "manual.button_pressed".into(),
            target: button.target,
            simulated: true,
        })
    }
    pub fn finish_simulation(
        &mut self,
        request_id: u64,
        now_ms: u64,
        error_code: Option<&str>,
    ) -> Result<(), Error> {
        self.advance(now_ms)?;
        if error_code.is_some_and(|c| !identifier(c)) {
            return Err(fail(
                "DECK_ERROR_CODE",
                "Error codes must be bounded identifiers",
            ));
        }
        let button_id = self
            .pending
            .iter()
            .find(|(_, id)| **id == request_id)
            .map(|(button, _)| button.clone())
            .ok_or_else(|| fail("DECK_REQUEST", "Unknown or already terminal request"))?;
        self.pending.remove(&button_id);
        let state = error_code.map_or(ButtonState::Simulated, |code| ButtonState::Rejected {
            code: code.into(),
        });
        self.remember(&button_id, Some(request_id), state);
        Ok(())
    }
    pub fn cancel_pending(&mut self, request_id: u64, now_ms: u64) -> Result<(), Error> {
        self.advance(now_ms)?;
        let button_id = self
            .pending
            .iter()
            .find(|(_, id)| **id == request_id)
            .map(|(button, _)| button.clone())
            .ok_or_else(|| fail("DECK_REQUEST", "Unknown or already terminal request"))?;
        self.pending.remove(&button_id);
        self.remember(&button_id, Some(request_id), ButtonState::Cancelled);
        Ok(())
    }
}
