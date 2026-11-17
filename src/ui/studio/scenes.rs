use super::*;
impl Studio {
    pub(super) fn scenes(&self, rail: f32, status: &Value, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let active = graph.active_scene.clone();
        let live = matches!(status["output"].as_str(), Some("recording" | "streaming"));
        col()
            .flex_1()
            .min_h_0()
            .child(
                row()
                    .h(px(56.))
                    .flex_none()
                    .px(px(4.))
                    .child(div().font_weight(FontWeight::SEMIBOLD).child("Escenas"))
                    .child(label(graph.scenes.len().to_string(), p.muted))
                    .child(div().flex_1())
                    .child(
                        self.action(
                            "new-scene",
                            "",
                            Command::CreateScene {
                                name: format!("Escena {}", graph.next_id),
                            },
                            cx,
                        )
                        .icon(IconName::Plus)
                        .tooltip("Nueva escena"),
                    ),
            )
            .child(
                col()
                    .id("scenes-scroll")
                    .overflow_y_scroll()
                    .flex_1()
                    .min_h_0()
                    .gap(px(4.))
                    .children(graph.scenes.iter().enumerate().map(|(i, s)| {
                        let selected = s.id == active;
                        let id = s.id.clone();
                        let tw = rail - 48.;
                        let th = tw * 9. / 16.;
                        col()
                            .id(("scene", i))
                            .role(Role::Button)
                            .aria_label(s.name.clone())
                            .focusable()
                            .tab_stop(true)
                            .focus_visible(|s| {
                                s.bg(p.selected).border_1().border_color(rgb(0x0a7aff))
                            })
                            .on_key_down(cx.listener({
                                let id = id.clone();
                                move |v, e: &KeyDownEvent, _, cx| {
                                    if matches!(e.keystroke.key.as_str(), "enter" | "space") {
                                        v.command(
                                            Command::SelectScene {
                                                scene_id: id.clone(),
                                            },
                                            "UI",
                                            cx,
                                        );
                                        v.selected_layer = None;
                                        cx.stop_propagation();
                                    }
                                }
                            }))
                            .p(px(6.))
                            .rounded(px(10.))
                            .cursor_pointer()
                            .hover(|d| d.bg(p.selected))
                            .on_click(cx.listener(move |v, _, _, cx| {
                                let r = v.command(
                                    Command::SelectScene {
                                        scene_id: id.clone(),
                                    },
                                    "UI",
                                    cx,
                                );
                                if r["ok"] == true {
                                    v.selected_layer = None;
                                }
                            }))
                            .child(
                                div()
                                    .w(px(tw))
                                    .h(px(th))
                                    .flex()
                                    .items_center()
                                    .justify_center()
                                    .rounded(px(7.))
                                    .overflow_hidden()
                                    .bg(rgb(0x0e0f12))
                                    .border_1()
                                    .border_color(if selected {
                                        if live { p.live } else { p.ink }
                                    } else {
                                        p.line
                                    })
                                    .when(selected, |d| {
                                        d.children(self.frame.clone().map(|f| {
                                            img(f)
                                                .w(px(tw))
                                                .h(px(th))
                                                .object_fit(ObjectFit::Contain)
                                        }))
                                    })
                                    .when(!selected, |d| {
                                        d.child(
                                            col()
                                                .items_center()
                                                .gap(px(8.))
                                                .text_color(rgb(0x6b7079))
                                                .child(Icon::new(IconName::Layers).size(px(22.)))
                                                .child(label("Sin vista previa", rgb(0xa2a7b0))),
                                        )
                                    }),
                            )
                            .child(
                                row()
                                    .pt(px(7.))
                                    .child(div().flex_1().child(s.name.clone()))
                                    .when(selected, |d| {
                                        d.child(label(
                                            if live { "● En salida" } else { "Actual" },
                                            if live { p.live } else { p.secondary },
                                        ))
                                    })
                                    .child(label(format!("⌘{}", i + 1), p.muted)),
                            )
                    })),
            )
    }
}
