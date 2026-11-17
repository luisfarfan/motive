//! Typed editor drafts; values are validated before the single Production write.
use super::*;
use crate::core::overlays::{Alignment, Definition, Font, Shape, Widget, WidgetKind};
use gpui_kit::component::input::{InputState, TextareaState};
use std::collections::BTreeMap;

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(super) enum Field {
    Name,
    Width,
    Height,
    Size,
    Color,
    Opacity,
    Background,
    BackgroundOpacity,
    Accent,
    BorderColor,
    BorderWidth,
    Duration,
}
impl Field {
    pub fn label(self) -> &'static str {
        match self {
            Self::Name => "Nombre de fuente",
            Self::Width => "Ancho del contenido",
            Self::Height => "Alto del contenido",
            Self::Size => "Tamaño de letra",
            Self::Color => "Color · RGB hexadecimal",
            Self::Opacity => "Opacidad · 0 a 1",
            Self::Background => "Fondo · RGB (vacío: transparente)",
            Self::BackgroundOpacity => "Opacidad del fondo · 0 a 1",
            Self::Accent => "Acento · RGB hexadecimal",
            Self::BorderColor => "Borde · RGB (vacío: sin borde)",
            Self::BorderWidth => "Grosor del borde",
            Self::Duration => "Duración · milisegundos",
        }
    }
}
pub(super) struct Draft {
    pub source_id: Option<String>,
    pub scene_id: String,
    pub revision: u64,
    pub definition: Definition,
    pub fields: BTreeMap<Field, Entity<InputState>>,
    pub text: Entity<TextareaState>,
    pub subtitle: Entity<TextareaState>,
}
impl Draft {
    pub fn new(
        definition: Definition,
        source_id: Option<String>,
        scene_id: String,
        revision: u64,
        name: String,
        w: &mut Window,
        cx: &mut Context<Studio>,
    ) -> Self {
        use Field::*;
        let mut values = vec![];
        if source_id.is_none() {
            values.push((Name, name));
        }
        let mut content = String::new();
        let mut sub = String::new();
        let rgb = |v: u32| format!("{v:06x}");
        match &definition {
            Definition::Text {
                text,
                size,
                color,
                opacity,
                width,
                height,
                background,
                background_opacity,
                ..
            } => {
                content = text.clone();
                values.extend([
                    (Width, width.to_string()),
                    (Height, height.to_string()),
                    (Size, size.to_string()),
                    (Color, rgb(*color)),
                    (Opacity, opacity.to_string()),
                    (Background, background.map(rgb).unwrap_or_default()),
                    (BackgroundOpacity, background_opacity.to_string()),
                ]);
            }
            Definition::Image { opacity, .. } | Definition::Video { opacity, .. } => {
                values.push((Opacity, opacity.to_string()))
            }
            Definition::Shape {
                width,
                height,
                color,
                opacity,
                border_color,
                border_width,
                ..
            } => values.extend([
                (Width, width.to_string()),
                (Height, height.to_string()),
                (Color, rgb(*color)),
                (Opacity, opacity.to_string()),
                (BorderColor, border_color.map(rgb).unwrap_or_default()),
                (BorderWidth, border_width.to_string()),
            ]),
            Definition::Widget { widget } => {
                content = widget.title.clone();
                sub = widget.subtitle.clone();
                values.extend([
                    (Width, widget.width.to_string()),
                    (Height, widget.height.to_string()),
                    (Color, rgb(widget.color)),
                    (Opacity, widget.opacity.to_string()),
                    (Background, rgb(widget.background)),
                    (Accent, rgb(widget.accent)),
                ]);
                if widget.kind != WidgetKind::LowerThird {
                    values.push((Duration, widget.duration_ms.to_string()));
                }
            }
        }
        let fields = values
            .into_iter()
            .map(|(key, value)| {
                (
                    key,
                    cx.new(|cx| InputState::new(w, cx).default_value(value)),
                )
            })
            .collect();
        let text = cx.new(|cx| {
            TextareaState::new(w, cx)
                .auto_grow(2, 4)
                .default_value(content)
        });
        let subtitle = cx.new(|cx| TextareaState::new(w, cx).auto_grow(2, 3).default_value(sub));
        Self {
            source_id,
            scene_id,
            revision,
            definition,
            fields,
            text,
            subtitle,
        }
    }
    pub fn value(&self, key: Field, cx: &App) -> String {
        self.fields[&key].read(cx).value().to_string()
    }
    pub fn definition(&self, cx: &App) -> anyhow::Result<Definition> {
        use Field::*;
        let integer = |key| forms::integer(&self.value(key, cx)).map_err(anyhow::Error::msg);
        let decimal = |key| number(&self.value(key, cx));
        let rgb = |key| color(&self.value(key, cx));
        let optional = |key| {
            let s = self.value(key, cx);
            if s.is_empty() {
                Ok(None)
            } else {
                color(&s).map(Some)
            }
        };
        let mut d = self.definition.clone();
        match &mut d {
            Definition::Text {
                text,
                size,
                color,
                opacity,
                width,
                height,
                background,
                background_opacity,
                ..
            } => {
                *text = self.text.read(cx).value().to_string();
                *size = integer(Size)?;
                *color = rgb(Color)?;
                *opacity = decimal(Opacity)?;
                *width = integer(Width)?;
                *height = integer(Height)?;
                *background = optional(Background)?;
                *background_opacity = decimal(BackgroundOpacity)?;
            }
            Definition::Image { opacity, .. } | Definition::Video { opacity, .. } => {
                *opacity = decimal(Opacity)?
            }
            Definition::Shape {
                width,
                height,
                color,
                opacity,
                border_color,
                border_width,
                ..
            } => {
                *width = integer(Width)?;
                *height = integer(Height)?;
                *color = rgb(Color)?;
                *opacity = decimal(Opacity)?;
                *border_color = optional(BorderColor)?;
                *border_width = integer(BorderWidth)?;
            }
            Definition::Widget { widget } => {
                widget.title = self.text.read(cx).value().to_string();
                widget.subtitle = self.subtitle.read(cx).value().to_string();
                widget.width = integer(Width)?;
                widget.height = integer(Height)?;
                widget.color = rgb(Color)?;
                widget.opacity = decimal(Opacity)?;
                widget.background = rgb(Background)?;
                widget.accent = rgb(Accent)?;
                if widget.kind != WidgetKind::LowerThird {
                    widget.duration_ms = integer(Duration)?;
                }
            }
        }
        d.validate()?;
        Ok(d)
    }
}
pub(super) fn number(s: &str) -> anyhow::Result<f32> {
    anyhow::ensure!(
        !s.is_empty()
            && s.bytes()
                .all(|b| b.is_ascii_digit() || b == b'.' || b == b'-'),
        "INVALID_NUMBER: usa un decimal sin espacios"
    );
    let value: f32 = s.parse().map_err(|_| anyhow::anyhow!("INVALID_NUMBER"))?;
    anyhow::ensure!(value.is_finite(), "INVALID_NUMBER");
    Ok(value)
}
fn color(s: &str) -> anyhow::Result<u32> {
    anyhow::ensure!(
        s.len() == 6 && s.bytes().all(|b| b.is_ascii_hexdigit()),
        "INVALID_OVERLAY_COLOR: usa seis dígitos RGB"
    );
    Ok(u32::from_str_radix(s, 16)?)
}
pub(super) fn text_default() -> Definition {
    Definition::Text {
        text: "Tu mensaje".into(),
        font: Font::Helvetica,
        size: 48,
        color: 0xf3fafa,
        opacity: 1.,
        align: Alignment::Left,
        width: 640,
        height: 160,
        background: None,
        background_opacity: 0.8,
        outline: false,
    }
}
pub(super) fn shape_default(shape: Shape) -> Definition {
    Definition::Shape {
        shape,
        width: 320,
        height: 160,
        color: 0x33e8b5,
        opacity: 1.,
        border_color: None,
        border_width: 0,
    }
}
pub(super) fn widget_default(kind: WidgetKind) -> Definition {
    Definition::Widget {
        widget: Widget {
            kind,
            title: if kind == WidgetKind::Countdown {
                "Comenzamos pronto"
            } else {
                "Nueva alerta"
            }
            .into(),
            subtitle: "Motive".into(),
            width: 480,
            height: 200,
            background: 0x0b1719,
            accent: 0x33e8b5,
            color: 0xf3fafa,
            opacity: 1.,
            duration_ms: if kind == WidgetKind::Countdown {
                60000
            } else {
                4000
            },
        },
    }
}
#[cfg(test)]
mod tests {
    use super::{color, number};
    #[test]
    fn editor_rejects_nonfinite_ambiguous_numbers_and_non_rgb_colors() {
        assert_eq!(number("-123.25").unwrap(), -123.25);
        for s in ["NaN", "inf", "1e3", " 2", "2 ", "1,2", "--1", "", "1.2.3"] {
            assert!(number(s).is_err(), "{s}");
        }
        assert_eq!(color("Ab12EF").unwrap(), 0xab12ef);
        for s in ["#ffffff", "fff", "1234567", "gggggg", " fffff"] {
            assert!(color(s).is_err());
        }
    }
}
