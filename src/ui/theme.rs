//! Provisional Phase 1 tokens from design/direction.md. No production state lives here.
use gpui_kit::{
    component::{Theme, ThemeMode},
    *,
};

#[derive(Clone, Copy)]
pub(super) struct Palette {
    pub shell: Hsla,
    pub raised: Hsla,
    pub sunken: Hsla,
    pub ink: Hsla,
    pub secondary: Hsla,
    pub muted: Hsla,
    pub line: Hsla,
    pub selected: Hsla,
    pub stage: Hsla,
    pub ready: Hsla,
    pub live: Hsla,
    pub warn: Hsla,
}
impl Palette {
    pub fn new(dark: bool) -> Self {
        let c = |light, night| rgb(if dark { night } else { light }).into();
        Self {
            shell: c(0xf2f3f5, 0x1b1c20),
            raised: c(0xffffff, 0x26272c),
            sunken: c(0xe9ebee, 0x141518),
            ink: c(0x16181d, 0xeeeff1),
            secondary: c(0x545a65, 0xa8adb6),
            muted: c(0x868c96, 0x7a7f89),
            line: if dark {
                rgba(0xffffff12)
            } else {
                rgba(0x16181d14)
            }
            .into(),
            selected: if dark {
                rgba(0xffffff12)
            } else {
                rgba(0x16181d0f)
            }
            .into(),
            stage: c(0x17181c, 0x121316),
            ready: c(0x17905d, 0x45d690),
            live: c(0xdc3328, 0xff5247),
            warn: c(0xb36a00, 0xffb547),
        }
    }
    pub fn apply(dark: bool, window: Option<&mut Window>, cx: &mut App) {
        Theme::change(
            if dark {
                ThemeMode::Dark
            } else {
                ThemeMode::Light
            },
            window,
            cx,
        );
        let p = Self::new(dark);
        let t = Theme::global_mut(cx);
        t.font_size = px(16.);
        t.radius = px(6.);
        t.radius_lg = px(10.);
        t.colors.background = p.shell;
        t.colors.foreground = p.ink;
        t.colors.border = p.line;
        t.colors.title_bar = p.raised;
        t.colors.title_bar_border = p.line;
        t.colors.button = p.raised;
        t.colors.button_foreground = p.ink;
        t.colors.button_hover = p.sunken;
        t.colors.button_active = p.selected;
        t.colors.primary = p.ink;
        t.colors.primary_foreground = p.raised;
        t.colors.ring = rgb(0x0a7aff).into();
    }
}
