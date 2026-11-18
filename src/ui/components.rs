pub(super) use super::theme::metrics;
use gpui_kit::{
    component::{
        Sizable,
        button::{Button, ButtonVariants},
    },
    *,
};

pub(super) fn row() -> Div {
    div().flex().items_center().gap(px(8.))
}
pub(super) fn col() -> Div {
    div().flex().flex_col()
}
pub(super) fn label(text: impl Into<SharedString>, color: impl Into<Hsla>) -> Div {
    div()
        .text_size(px(metrics::SECONDARY))
        .text_color(color.into())
        .child(text.into())
}
/// Feedback text needs a stable, distinct ID to appear and update in native AX.
pub(super) fn feedback_label(
    id: impl Into<ElementId>,
    text: impl Into<SharedString>,
    color: impl Into<Hsla>,
) -> Div {
    div()
        .text_size(px(metrics::SECONDARY))
        .text_color(color.into())
        .child(Text::new(id.into(), text.into()))
}
pub(super) fn dot(color: impl Into<Hsla>) -> Div {
    div()
        .flex_none()
        .size(px(6.))
        .rounded_full()
        .bg(color.into())
}
pub(super) fn quiet(id: impl Into<ElementId>, text: impl Into<SharedString>) -> Button {
    Button::new(id)
        .label(text)
        .ghost()
        .small()
        .h(px(metrics::CONTROL))
        .text_size(px(metrics::BODY))
        .rounded(px(metrics::CONTROL_RADIUS))
}
pub(super) fn control(id: impl Into<ElementId>, text: impl Into<SharedString>) -> Button {
    Button::new(id)
        .label(text)
        .small()
        .h(px(metrics::CONTROL))
        .text_size(px(metrics::BODY))
        .rounded(px(metrics::CONTROL_RADIUS))
}

/// Real normalized peak only; no synthetic channels, gain or retained peak.
pub(super) fn audio_meter(peak: f64, p: super::theme::Palette) -> Div {
    let db = if peak > 0. { 20. * peak.log10() } else { -60. };
    let bars = ((db + 60.) / 60. * 48.).clamp(0., 48.) as usize;
    row().gap(px(1.)).children((0..48).map(|i| {
        div().flex_1().h(px(5.)).bg(if i >= bars {
            p.sunken
        } else if i > 43 {
            p.live
        } else if i > 36 {
            p.warn
        } else {
            p.ready
        })
    }))
}
pub(super) fn property_group(title: impl Into<SharedString>, p: super::theme::Palette) -> Div {
    col()
        .gap(px(8.))
        .child(label(title, p.secondary).font_weight(FontWeight::SEMIBOLD))
}
