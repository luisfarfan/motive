//! Control intentions and conservative preparation against an observed snapshot.
//!
//! This module does not own production state or dispatch to Motive. The eventual
//! adapter must obtain and revalidate this snapshot on Production's owner thread.
use crate::model::{Error, validate_id, validate_text};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TransitionKind {
    Cut,
    Fade,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Transition {
    pub kind: TransitionKind,
    pub duration_ms: u32,
}
impl Transition {
    pub fn validate(&self) -> Result<(), Error> {
        if !match self.kind {
            TransitionKind::Cut => self.duration_ms == 0,
            TransitionKind::Fade => (100..=5000).contains(&self.duration_ms),
        } {
            return Err(Error::new(
                "INVALID_TRANSITION",
                "Cut requires 0 ms; Fade requires 100–5000 ms",
            ));
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AnimationKind {
    FadeIn,
    FadeOut,
    SlideIn,
    SlideOut,
    ScaleIn,
    ScaleOut,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Easing {
    Linear,
    EaseIn,
    EaseOut,
    EaseInOut,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Animation {
    pub kind: AnimationKind,
    pub easing: Easing,
    pub duration_ms: u32,
    pub distance: f32,
    pub scale_from: f32,
}
impl Animation {
    pub fn validate(&self) -> Result<(), Error> {
        if !(100..=10000).contains(&self.duration_ms)
            || !self.distance.is_finite()
            || self.distance.abs() > 1920.
            || !self.scale_from.is_finite()
            || !(0.1..=2.).contains(&self.scale_from)
        {
            return Err(Error::new(
                "INVALID_ANIMATION",
                "Animation exceeds H11 duration, distance or scale limits",
            ));
        }
        if matches!(self.kind, AnimationKind::FadeIn | AnimationKind::FadeOut)
            && self.easing != Easing::Linear
        {
            return Err(Error::new("UNSUPPORTED_FADE_EASING", "OBS fade is linear"));
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WidgetEvent {
    Show,
    Hide,
    Trigger,
    TimerStart,
    TimerStop,
    TimerReset,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    ShowOverlay {
        source_id: String,
    },
    HideOverlay {
        source_id: String,
    },
    Widget {
        source_id: String,
        event: WidgetEvent,
    },
    Animate {
        scene_id: String,
        layer_id: String,
        animation: Animation,
    },
    CancelAnimation {
        operation_id: u64,
    },
    CountdownStart {
        source_id: String,
    },
    CountdownReset {
        source_id: String,
    },
    SelectScene {
        scene_id: String,
        transition: Transition,
    },
    UpdateText {
        source_id: String,
        text: String,
    },
    IncrementCounter {
        name: String,
        amount: i64,
    },
    Notify {
        message: String,
    },
    /// Prepares inert text only; it neither synthesizes nor plays audio.
    PrepareSpeech {
        text: String,
    },
    Sound {
        resource: String,
    },
    Sequence {
        actions: Vec<Action>,
    },
    EmitEvent {
        name: String,
    },
}
impl Action {
    pub fn validate(&self) -> Result<(), Error> {
        self.flattened().map(|_| ())
    }
    pub fn flattened(&self) -> Result<Vec<Action>, Error> {
        fn visit(action: &Action, depth: usize, out: &mut Vec<Action>) -> Result<(), Error> {
            if depth > 4 {
                return Err(Error::new(
                    "SEQUENCE_DEPTH",
                    "At most four nested sequences are allowed",
                ));
            }
            if let Action::Sequence { actions } = action {
                if actions.is_empty() || actions.len() > 32 {
                    return Err(Error::new("ACTION_LIMIT", "Sequences require 1–32 actions"));
                }
                for action in actions {
                    visit(action, depth + 1, out)?;
                }
                return Ok(());
            }
            action.validate_leaf()?;
            if out.len() == 32 {
                return Err(Error::new(
                    "ACTION_LIMIT",
                    "At most 32 leaf actions are allowed",
                ));
            }
            out.push(action.clone());
            Ok(())
        }
        let mut out = Vec::new();
        visit(self, 0, &mut out)?;
        Ok(out)
    }
    fn validate_leaf(&self) -> Result<(), Error> {
        match self {
            Self::ShowOverlay { source_id }
            | Self::HideOverlay { source_id }
            | Self::Widget { source_id, .. }
            | Self::CountdownStart { source_id }
            | Self::CountdownReset { source_id } => validate_id(source_id),
            Self::Animate {
                scene_id,
                layer_id,
                animation,
            } => {
                validate_id(scene_id)?;
                validate_id(layer_id)?;
                animation.validate()
            }
            Self::CancelAnimation { operation_id } => {
                if *operation_id == 0 {
                    Err(Error::new(
                        "INVALID_OPERATION",
                        "Operation ID must be nonzero",
                    ))
                } else {
                    Ok(())
                }
            }
            Self::SelectScene {
                scene_id,
                transition,
            } => {
                validate_id(scene_id)?;
                transition.validate()
            }
            Self::UpdateText { source_id, text } => {
                validate_id(source_id)?;
                validate_text(text, 4096)
            }
            Self::IncrementCounter { name, .. } | Self::EmitEvent { name } => validate_id(name),
            Self::Notify { message } => validate_text(message, 4096),
            Self::PrepareSpeech { text } => validate_text(text, 4096),
            Self::Sound { resource } => validate_id(resource),
            Self::Sequence { .. } => unreachable!("sequences handled by bounded traversal"),
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Revision {
    pub pid: u32,
    pub revision: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceReadiness {
    Ready,
    Missing,
    Recovering,
    Failed,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    Text,
    Shape,
    Image,
    Video,
    LowerThird,
    Alert,
    Countdown,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LayerBinding {
    pub scene_id: String,
    pub source_id: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Font {
    Helvetica,
    Arial,
    Menlo,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    Left,
    Center,
    Right,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextDefinition {
    pub text: String,
    pub font: Font,
    pub size: u32,
    pub color: u32,
    pub opacity: f32,
    pub align: Alignment,
    pub width: u32,
    pub height: u32,
    pub background: Option<u32>,
    pub background_opacity: f32,
    pub outline: bool,
}
impl TextDefinition {
    pub fn validate(&self) -> Result<(), Error> {
        validate_text(&self.text, 4096)?;
        if !(8..=192).contains(&self.size)
            || self.text.lines().count() > 16
            || self.text.chars().count() * self.size as usize > 24576
            || self.color > 0xffffff
            || self.background.is_some_and(|c| c > 0xffffff)
            || !self.opacity.is_finite()
            || !(0.0..=1.0).contains(&self.opacity)
            || !self.background_opacity.is_finite()
            || !(0.0..=1.0).contains(&self.background_opacity)
            || !(1..=1920).contains(&self.width)
            || !(1..=1080).contains(&self.height)
        {
            return Err(Error::new(
                "INVALID_TEXT_DEFINITION",
                "Text definition exceeds H11 limits",
            ));
        }
        Ok(())
    }
}

/// A disposable observed snapshot, never a second authority or persisted graph.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProductionSnapshot {
    pub pid: u32,
    pub revision: u64,
    pub active_scene: String,
    pub output_active: bool,
    pub structural_busy: bool,
    pub transition_active: bool,
    pub animation_active: bool,
    pub sources: BTreeMap<String, SourceReadiness>,
    pub source_kinds: BTreeMap<String, SourceKind>,
    pub text_definitions: BTreeMap<String, TextDefinition>,
    pub scenes: BTreeMap<String, Vec<String>>,
    pub layers: BTreeMap<String, LayerBinding>,
    pub busy_layers: BTreeSet<String>,
    pub animation_operations: BTreeSet<u64>,
}
impl ProductionSnapshot {
    pub fn version(&self) -> Revision {
        Revision {
            pid: self.pid,
            revision: self.revision,
        }
    }
    fn ready(&self, source_id: &str) -> Result<(), Error> {
        match self.sources.get(source_id) {
            Some(SourceReadiness::Ready) => Ok(()),
            Some(_) => Err(Error::new(
                "SOURCE_NOT_READY",
                "Source must be explicitly recovered before use",
            )),
            None => Err(Error::new(
                "SOURCE_MISSING",
                "Source is not present in the observed production",
            )),
        }
    }
}

/// These are existing command shapes, not executable arbitrary MCP payloads.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum CoreCommand {
    OverlayEvent {
        source_id: String,
        event: WidgetEvent,
    },
    AnimateOverlay {
        scene_id: String,
        layer_id: String,
        animation: Animation,
    },
    CancelOverlayAnimation {
        operation_id: u64,
    },
    ConfigureTransition {
        transition: Transition,
    },
    SelectScene {
        scene_id: String,
    },
    UpdateOverlay {
        source_id: String,
        definition: CoreTextDefinition,
    },
}
/// The native update is a complete tagged definition, never a text patch.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum CoreTextDefinition {
    Text(TextDefinition),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PreparedAction {
    pub action: Action,
    pub commands: Vec<CoreCommand>,
    pub local: bool,
    pub requires_completion: bool,
}

pub fn prepare(
    action: &Action,
    snapshot: &ProductionSnapshot,
    expected: Option<Revision>,
) -> Result<PreparedAction, Error> {
    action.validate()?;
    let local = matches!(
        action,
        Action::IncrementCounter { .. }
            | Action::Notify { .. }
            | Action::PrepareSpeech { .. }
            | Action::EmitEvent { .. }
    );
    if matches!(action, Action::Sound { .. }) {
        return Err(Error::new(
            "CAPABILITY_UNAVAILABLE",
            "Sound playback has no approved H12 audio contract",
        ));
    }
    if matches!(action, Action::Sequence { .. }) {
        return Err(Error::new(
            "SEQUENCE_REQUIRES_RUNTIME",
            "Prepare each bounded sequence step immediately before dispatch",
        ));
    }
    if !local {
        if expected.is_some_and(|revision| revision != snapshot.version()) {
            return Err(Error::new(
                "STALE_REVISION",
                "Production process or revision changed; refresh explicitly",
            ));
        }
        if snapshot.structural_busy {
            return Err(Error::new(
                "PRODUCTION_BUSY",
                "A structural operation or shutdown is pending",
            ));
        }
    }
    let mut commands = Vec::new();
    let mut requires_completion = false;
    match action {
        Action::ShowOverlay { source_id } | Action::HideOverlay { source_id } => {
            snapshot.ready(source_id)?;
            if !snapshot.source_kinds.contains_key(source_id) {
                return Err(Error::new(
                    "NOT_AN_OVERLAY",
                    "Source overlay kind is unavailable",
                ));
            }
            commands.push(CoreCommand::OverlayEvent {
                source_id: source_id.clone(),
                event: if matches!(action, Action::ShowOverlay { .. }) {
                    WidgetEvent::Show
                } else {
                    WidgetEvent::Hide
                },
            });
            requires_completion = true;
        }
        Action::Widget { source_id, event } => {
            snapshot.ready(source_id)?;
            let kind = snapshot.source_kinds.get(source_id);
            let allowed = match event {
                WidgetEvent::Trigger => {
                    matches!(kind, Some(SourceKind::Alert | SourceKind::LowerThird))
                }
                WidgetEvent::TimerStart | WidgetEvent::TimerStop | WidgetEvent::TimerReset => {
                    kind == Some(&SourceKind::Countdown)
                }
                WidgetEvent::Show | WidgetEvent::Hide => kind.is_some(),
            };
            if !allowed {
                return Err(Error::new(
                    "INVALID_OVERLAY_ACTION",
                    "Event is not supported by this overlay kind",
                ));
            }
            commands.push(CoreCommand::OverlayEvent {
                source_id: source_id.clone(),
                event: *event,
            });
            requires_completion = true;
        }
        Action::CountdownStart { source_id } | Action::CountdownReset { source_id } => {
            snapshot.ready(source_id)?;
            if snapshot.source_kinds.get(source_id) != Some(&SourceKind::Countdown) {
                return Err(Error::new(
                    "INVALID_OVERLAY_ACTION",
                    "Countdown action needs a countdown source",
                ));
            }
            commands.push(CoreCommand::OverlayEvent {
                source_id: source_id.clone(),
                event: if matches!(action, Action::CountdownStart { .. }) {
                    WidgetEvent::TimerStart
                } else {
                    WidgetEvent::TimerReset
                },
            });
            requires_completion = true;
        }
        Action::Animate {
            scene_id,
            layer_id,
            animation,
        } => {
            if snapshot.transition_active || snapshot.active_scene != *scene_id {
                return Err(Error::new(
                    "PRODUCTION_BUSY",
                    "Animation requires the active scene without a transition",
                ));
            }
            let layer = snapshot.layers.get(layer_id).ok_or_else(|| {
                Error::new(
                    "LAYER_MISSING",
                    "Layer does not exist in the observed snapshot",
                )
            })?;
            if layer.scene_id != *scene_id {
                return Err(Error::new(
                    "LAYER_MISMATCH",
                    "Layer belongs to another scene",
                ));
            }
            snapshot.ready(&layer.source_id)?;
            if !snapshot.source_kinds.contains_key(&layer.source_id) {
                return Err(Error::new(
                    "NOT_AN_OVERLAY",
                    "Layer source is not a known overlay",
                ));
            }
            if snapshot.busy_layers.contains(layer_id) || snapshot.busy_layers.len() >= 8 {
                return Err(Error::new(
                    "ANIMATION_BUSY",
                    "Layer is running, cancelling, pending acknowledgement or the eight-animation limit is reached",
                ));
            }
            commands.push(CoreCommand::AnimateOverlay {
                scene_id: scene_id.clone(),
                layer_id: layer_id.clone(),
                animation: animation.clone(),
            });
            requires_completion = true;
        }
        Action::CancelAnimation { operation_id } => {
            if !snapshot.animation_operations.contains(operation_id) {
                return Err(Error::new(
                    "OPERATION_MISSING",
                    "Unknown animation operation; import IDs cannot be cancelled",
                ));
            }
            commands.push(CoreCommand::CancelOverlayAnimation {
                operation_id: *operation_id,
            });
            requires_completion = true;
        }
        Action::SelectScene {
            scene_id,
            transition,
        } => {
            if snapshot.transition_active
                || snapshot.animation_active
                || !snapshot.busy_layers.is_empty()
            {
                return Err(Error::new(
                    "PRODUCTION_BUSY",
                    "Cut/Fade and layer animations are mutually exclusive",
                ));
            }
            let sources = snapshot.scenes.get(scene_id).ok_or_else(|| {
                Error::new(
                    "SCENE_MISSING",
                    "Target scene is not in the observed snapshot",
                )
            })?;
            if sources.is_empty()
                && (snapshot.output_active || transition.kind == TransitionKind::Fade)
            {
                return Err(Error::new(
                    "EMPTY_SCENE",
                    "An empty scene cannot be selected live or used as a Fade target",
                ));
            }
            for source in sources {
                snapshot.ready(source)?;
            }
            commands.push(CoreCommand::ConfigureTransition {
                transition: transition.clone(),
            });
            commands.push(CoreCommand::SelectScene {
                scene_id: scene_id.clone(),
            });
            requires_completion = true;
        }
        Action::UpdateText { source_id, text } => {
            snapshot.ready(source_id)?;
            if snapshot.transition_active
                || snapshot.animation_active
                || !snapshot.busy_layers.is_empty()
            {
                return Err(Error::new(
                    "PRODUCTION_BUSY",
                    "Updating text requires a stable scene",
                ));
            }
            if snapshot.source_kinds.get(source_id) != Some(&SourceKind::Text) {
                return Err(Error::new(
                    "TEXT_DEFINITION_REQUIRED",
                    "Only full plain-text definitions are supported by this action",
                ));
            }
            let mut definition = snapshot
                .text_definitions
                .get(source_id)
                .ok_or_else(|| {
                    Error::new(
                        "TEXT_DEFINITION_REQUIRED",
                        "Read the complete current text definition before replacement",
                    )
                })?
                .clone();
            definition.text = text.clone();
            definition.validate()?;
            commands.push(CoreCommand::UpdateOverlay {
                source_id: source_id.clone(),
                definition: CoreTextDefinition::Text(definition),
            });
            requires_completion = true;
        }
        _ => {}
    }
    Ok(PreparedAction {
        action: action.clone(),
        commands,
        local,
        requires_completion,
    })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionStatus {
    Validated,
    Prepared,
    Sent,
    Accepted,
    Completed,
    Rejected,
    Failed,
    Cancelled,
    TimedOut,
    Uncertain,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActionReceipt {
    pub action_id: String,
    pub status: ActionStatus,
    pub operation_id: Option<u64>,
    pub error: Option<Error>,
    pub simulated: bool,
}
impl ActionReceipt {
    /// An accepted mutation is never silently promoted to completion. Only an
    /// adapter observation may request Accepted -> Completed.
    pub fn transition(&mut self, next: ActionStatus) -> Result<(), Error> {
        use ActionStatus::*;
        let allowed = matches!(
            (self.status, next),
            (Validated, Prepared | Rejected | Cancelled)
                | (Prepared, Sent | Rejected | Cancelled | TimedOut)
                | (Sent, Accepted | Rejected | Failed | Uncertain)
                | (Accepted, Completed | Failed | Cancelled | Uncertain)
                | (Uncertain, Completed | Failed | Cancelled)
        );
        if !allowed {
            return Err(Error::new(
                "INVALID_ACTION_TRANSITION",
                "Action receipt transition requires valid dispatch or observed completion evidence",
            ));
        }
        self.status = next;
        Ok(())
    }
}
