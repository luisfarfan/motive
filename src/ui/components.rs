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
        .text_size(px(12.))
        .text_color(color.into())
        .child(text.into())
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
        .h(px(28.))
        .text_size(px(13.))
        .rounded(px(6.))
}
pub(super) fn control(id: impl Into<ElementId>, text: impl Into<SharedString>) -> Button {
    Button::new(id)
        .label(text)
        .small()
        .h(px(28.))
        .text_size(px(13.))
        .rounded(px(6.))
}
