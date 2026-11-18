//! Bounded visual definitions. libobs owns composition, clocks and encoding.
pub mod assets;
mod presets;
pub(super) mod production;
pub mod protocol;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Definition {
    Text {
        text: String,
        font: Font,
        size: u32,
        color: u32,
        opacity: f32,
        align: Alignment,
        width: u32,
        height: u32,
        background: Option<u32>,
        background_opacity: f32,
        outline: bool,
    },
    Image {
        asset_id: String,
        opacity: f32,
    },
    Video {
        asset_id: String,
        opacity: f32,
        looping: bool,
    },
    Shape {
        shape: Shape,
        width: u32,
        height: u32,
        color: u32,
        opacity: f32,
        border_color: Option<u32>,
        border_width: u32,
    },
    Widget {
        widget: Widget,
    },
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub enum Font {
    Helvetica,
    Arial,
    Menlo,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    Left,
    Center,
    Right,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    Rectangle,
    Circle,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WidgetKind {
    LowerThird,
    Countdown,
    Alert,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Widget {
    pub kind: WidgetKind,
    pub title: String,
    pub subtitle: String,
    pub width: u32,
    pub height: u32,
    pub background: u32,
    pub accent: u32,
    pub color: u32,
    pub opacity: f32,
    pub duration_ms: u32,
}
fn color(c: u32) -> anyhow::Result<()> {
    anyhow::ensure!(c <= 0xffffff, "INVALID_OVERLAY_COLOR");
    Ok(())
}
fn opacity(v: f32) -> anyhow::Result<()> {
    anyhow::ensure!(
        v.is_finite() && (0.0..=1.0).contains(&v),
        "INVALID_OVERLAY_OPACITY"
    );
    Ok(())
}
fn dimensions(w: u32, h: u32) -> anyhow::Result<()> {
    anyhow::ensure!(
        (1..=1920).contains(&w) && (1..=1080).contains(&h),
        "OVERLAY_DIMENSION_LIMIT"
    );
    Ok(())
}
fn text(s: &str) -> anyhow::Result<()> {
    anyhow::ensure!(
        s.len() <= 4096 && !s.chars().any(|c| c.is_control() && c != '\n' && c != '\t'),
        "INVALID_OVERLAY_TEXT"
    );
    Ok(())
}
impl Definition {
    pub fn asset_id(&self) -> Option<&str> {
        match self {
            Self::Image { asset_id, .. } | Self::Video { asset_id, .. } => Some(asset_id),
            _ => None,
        }
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        match self {
            Self::Text {
                text: t,
                size,
                color: c,
                opacity: o,
                width,
                height,
                background,
                background_opacity,
                ..
            } => {
                text(t)?;
                dimensions(*width, *height)?;
                color(*c)?;
                opacity(*o)?;
                opacity(*background_opacity)?;
                anyhow::ensure!(
                    t.lines().count() <= 16
                        && t.chars().count().saturating_mul(*size as usize) <= 24576,
                    "OVERLAY_TEXT_RENDER_LIMIT"
                );
                if let Some(c) = background {
                    color(*c)?;
                }
                anyhow::ensure!((8..=192).contains(size), "OVERLAY_FONT_SIZE_LIMIT");
            }
            Self::Image {
                asset_id,
                opacity: o,
            }
            | Self::Video {
                asset_id,
                opacity: o,
                ..
            } => {
                anyhow::ensure!(
                    asset_id
                        .strip_prefix("asset-")
                        .is_some_and(|v| v.len() == 64
                            && v.bytes()
                                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))),
                    "INVALID_ASSET_ID"
                );
                opacity(*o)?;
            }
            Self::Shape {
                width,
                height,
                color: c,
                opacity: o,
                border_color,
                border_width,
                ..
            } => {
                dimensions(*width, *height)?;
                color(*c)?;
                opacity(*o)?;
                if let Some(c) = border_color {
                    color(*c)?;
                }
                anyhow::ensure!(
                    *border_width <= 32 && *border_width <= (*width).min(*height) / 2,
                    "INVALID_OVERLAY_BORDER"
                );
            }
            Self::Widget { widget: w } => {
                text(&w.title)?;
                text(&w.subtitle)?;
                dimensions(w.width, w.height)?;
                anyhow::ensure!(
                    w.title.chars().count() <= 160
                        && w.subtitle.chars().count() <= 256
                        && w.title.lines().count() <= 3
                        && w.subtitle.lines().count() <= 4,
                    "WIDGET_TEXT_LIMIT"
                );
                anyhow::ensure!(w.width >= 240 && w.height >= 100, "WIDGET_DIMENSION_LIMIT");
                for c in [w.background, w.accent, w.color] {
                    color(c)?;
                }
                opacity(w.opacity)?;
                anyhow::ensure!(
                    match w.kind {
                        WidgetKind::LowerThird => w.duration_ms == 0,
                        WidgetKind::Countdown => (1000..=3_600_000).contains(&w.duration_ms),
                        WidgetKind::Alert => (100..=60_000).contains(&w.duration_ms),
                    },
                    "INVALID_WIDGET_DURATION"
                );
            }
        }
        Ok(())
    }
    pub fn compatible_update(&self, next: &Self) -> bool {
        std::mem::discriminant(self) == std::mem::discriminant(next)
            && self.asset_id() == next.asset_id()
            && match (self, next) {
                (Self::Widget { widget: a }, Self::Widget { widget: b }) => a.kind == b.kind,
                (Self::Shape { shape: a, .. }, Self::Shape { shape: b, .. }) => a == b,
                _ => true,
            }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Event {
    Show,
    Hide,
    Trigger,
    TimerStart,
    TimerStop,
    TimerReset,
    Play,
    Pause,
    Restart,
    Stop,
}
impl Event {
    pub fn native(self) -> &'static str {
        match self {
            Self::Show => "show",
            Self::Hide => "hide",
            Self::Trigger => "trigger",
            Self::TimerStart => "timer_start",
            Self::TimerStop => "timer_stop",
            Self::TimerReset => "timer_reset",
            Self::Play => "play",
            Self::Pause => "pause",
            Self::Restart => "restart",
            Self::Stop => "stop",
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AnimationKind {
    FadeIn,
    FadeOut,
    SlideIn,
    SlideOut,
    ScaleIn,
    ScaleOut,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Easing {
    Linear,
    EaseIn,
    EaseOut,
    EaseInOut,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Animation {
    pub kind: AnimationKind,
    pub easing: Easing,
    pub duration_ms: u32,
    pub distance: f32,
    pub scale_from: f32,
}
impl Animation {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            (100..=10000).contains(&self.duration_ms)
                && self.distance.is_finite()
                && self.distance.abs() <= 1920.
                && self.scale_from.is_finite()
                && (0.1..=2.0).contains(&self.scale_from),
            "INVALID_OVERLAY_ANIMATION"
        );
        anyhow::ensure!(
            !matches!(self.kind, AnimationKind::FadeIn | AnimationKind::FadeOut)
                || self.easing == Easing::Linear,
            "UNSUPPORTED_FADE_EASING: native OBS fade is linear"
        );
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Preset {
    ProfessionalLowerThird,
    StartingSoon,
    BeRightBack,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PresetParameters {
    pub title: String,
    pub subtitle: String,
    pub background: u32,
    pub accent: u32,
    pub color: u32,
    pub duration_ms: u32,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum OverlayCommand {
    OverlayCapabilities,
    ListAssets,
    AssetInventory,
    ImportAsset {
        file_name: String,
    },
    RemoveAsset {
        asset_id: String,
    },
    CreateOverlay {
        scene_id: String,
        name: String,
        definition: Definition,
    },
    UpdateOverlay {
        source_id: String,
        definition: Definition,
    },
    OverlayState,
    OverlayEvent {
        source_id: String,
        event: Event,
    },
    AnimateOverlay {
        scene_id: String,
        layer_id: String,
        animation: Animation,
    },
    TriggerAnimatedWidget {
        source_id: String,
        scene_id: String,
        layer_id: String,
        animation: Animation,
    },
    CancelOverlayAnimation {
        operation_id: u64,
    },
    OverlayPresets,
    InstantiateOverlayPreset {
        scene_id: String,
        preset: Preset,
        parameters: PresetParameters,
    },
}
impl OverlayCommand {
    pub fn query(&self) -> bool {
        matches!(
            self,
            Self::OverlayCapabilities
                | Self::ListAssets
                | Self::AssetInventory
                | Self::OverlayState
                | Self::OverlayPresets
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn text_supports_utf8_newlines_and_empty_but_not_control_bytes() {
        for t in ["", "Áéíóú — 東京\nMotive \t ✓"] {
            assert!(text(t).is_ok());
        }
        assert!(text("no\0").is_err());
        assert!(text(&"x".repeat(4097)).is_err());
    }
    #[test]
    fn flat_commands_share_the_strict_control_parser() {
        for op in [
            "overlay_capabilities",
            "overlay_state",
            "list_assets",
            "asset_inventory",
            "overlay_presets",
        ] {
            let value = serde_json::json!({"op":op});
            let command = crate::core::parse_command(value.clone()).unwrap();
            assert_eq!(serde_json::to_value(command).unwrap(), value);
            assert!(
                crate::core::parse_command(serde_json::json!({"op":op,"path":"/etc/passwd"}))
                    .is_err()
            );
        }
        assert!(crate::core::parse_command(serde_json::json!({"op":"overlay_event","source_id":"source-2","event":"javascript"})).is_err());
    }
    #[test]
    fn bounded_properties_and_native_fade_semantics() {
        assert!(opacity(f32::NAN).is_err());
        assert!(dimensions(1921, 1080).is_err());
        let mut a = Animation {
            kind: AnimationKind::FadeIn,
            easing: Easing::Linear,
            duration_ms: 1000,
            distance: 100.,
            scale_from: 0.5,
        };
        assert!(a.validate().is_ok());
        a.easing = Easing::EaseIn;
        assert!(a.validate().is_err());
        a.kind = AnimationKind::SlideIn;
        assert!(a.validate().is_ok());
    }
}
