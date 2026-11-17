use super::*;
impl Studio {
    pub(in crate::ui::studio) fn canvas_view(
        &self,
        pw: f32,
        ph: f32,
        cx: &mut Context<Self>,
    ) -> impl IntoElement {
        let bounds = self.editor.bounds.clone();
        let scale = pw / self.production.engine.width as f32;
        let selected = self
            .editor
            .drag
            .as_ref()
            .map(|d| d.edit.after.clone())
            .or_else(|| self.selected_edit().map(|e| e.before));
        div()
            .id("program-canvas")
            .relative()
            .w(px(pw))
            .h(px(ph))
            .bg(rgb(0x0e0f12))
            .cursor_crosshair()
            .on_hover(cx.listener(|v, hot, _, cx| {
                if v.editor.hot != *hot {
                    v.editor.hot = *hot;
                    cx.notify();
                }
            }))
            .on_mouse_down(
                MouseButton::Left,
                cx.listener(|v, e, w, cx| v.begin_drag(e, w, cx)),
            )
            .children(
                self.frame
                    .clone()
                    .map(|f| img(f).size_full().object_fit(ObjectFit::Contain)),
            )
            .child(
                canvas(
                    move |b, _, _| {
                        bounds.set(b);
                    },
                    |_, _, _, _| {},
                )
                .absolute()
                .inset_0(),
            )
            .when(self.editor.safe, |d| {
                d.child(
                    div()
                        .absolute()
                        .left(px(32. * scale))
                        .top(px(32. * scale))
                        .w(px(pw - 64. * scale))
                        .h(px(ph - 64. * scale))
                        .border_1()
                        .border_color(rgba(0xffffff55)),
                )
            })
            .children(selected.filter(|t| t.visible).map(|t| {
                let mut selection = div()
                    .absolute()
                    .left(px(t.x * scale))
                    .top(px(t.y * scale))
                    .w(px(t.width * scale))
                    .h(px(t.height * scale));
                for (left, top) in [(true, true), (false, true), (true, false), (false, false)] {
                    selection = selection.child(
                        div()
                            .absolute()
                            .size(px(14.))
                            .border_color(rgb(0xffffff))
                            .when(left, |d| d.left(px(-3.)).border_l_2())
                            .when(!left, |d| d.right(px(-3.)).border_r_2())
                            .when(top, |d| d.top(px(-3.)).border_t_2())
                            .when(!top, |d| d.bottom(px(-3.)).border_b_2()),
                    );
                }
                selection.when(self.editor.hot || self.editor.drag.is_some(), |d| {
                    d.children(
                        [
                            (0., 0.),
                            (0.5, 0.),
                            (1., 0.),
                            (1., 0.5),
                            (1., 1.),
                            (0.5, 1.),
                            (0., 1.),
                            (0., 0.5),
                        ]
                        .into_iter()
                        .map(|(x, y)| {
                            div()
                                .absolute()
                                .left(px(x * t.width * scale - 3.))
                                .top(px(y * t.height * scale - 3.))
                                .size(px(6.))
                                .bg(rgb(0xffffff))
                                .border_1()
                                .border_color(rgb(0x16181d))
                        }),
                    )
                })
            }))
            .children(self.editor.drag.as_ref().and_then(|d| d.guides.0).map(|x| {
                div()
                    .absolute()
                    .left(px(x * scale))
                    .top_0()
                    .w(px(1.))
                    .h(px(ph))
                    .bg(rgb(0x0a7aff))
            }))
            .children(self.editor.drag.as_ref().and_then(|d| d.guides.1).map(|y| {
                div()
                    .absolute()
                    .top(px(y * scale))
                    .left_0()
                    .h(px(1.))
                    .w(px(pw))
                    .bg(rgb(0x0a7aff))
            }))
            .when(self.editor.drag.is_some(), |d| {
                d.child(
                    label("Vista de edición · aplicar al soltar", rgb(0xffffff))
                        .absolute()
                        .top(px(8.))
                        .left(px(8.))
                        .px(px(8.))
                        .py(px(4.))
                        .rounded(px(5.))
                        .bg(rgba(0x000000cc)),
                )
            })
    }
}
