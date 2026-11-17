mod components;
mod fixture;
mod studio;
mod theme;
use gpui_kit::*;
pub use studio::Studio;
pub fn window_options(cx: &App) -> WindowOptions {
    let compact = std::env::var("MOTIVE_UI_SIZE").as_deref() == Ok("1024x780");
    let (w, h) = if compact {
        (1024., 780.)
    } else {
        (1440., 980.)
    };
    let mut options = crate::window_options("Motive — Estudio local", w, h, cx);
    options.titlebar = Some(TitlebarOptions {
        title: Some("Motive — Estudio local".into()),
        appears_transparent: true,
        traffic_light_position: Some(point(px(18.), px(20.))),
    });
    options.app_owns_titlebar_drag = true;
    options.window_min_size = Some(size(px(1024.), px(780.)));
    options
}

pub fn init(cx: &mut App) {
    theme::Palette::apply(false, None, cx);
}

mod preferences;
