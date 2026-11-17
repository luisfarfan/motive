use super::*;
impl Studio {
    pub(super) fn layers(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let variant = self.production.project.variant;
        let health = self.production.status()["sources"].clone();
        let mut layers = scene.layers.iter().collect::<Vec<_>>();
        layers.sort_by_key(|l| std::cmp::Reverse(l.layouts.get(variant).order));
        col()
            .mt(px(14.))
            .child(
                row()
                    .h(px(30.))
                    .px(px(8.))
                    .child(div().font_weight(FontWeight::SEMIBOLD).child("Capas"))
                    .child(label(format!("en {}", scene.name), p.muted))
                    .child(div().flex_1())
                    .child(self.panel_button(Panel::Creative, "Biblioteca", IconName::Layers, cx))
                    .child(self.panel_button(Panel::Sources, "Añadir fuente", IconName::Plus, cx)),
            )
            .child(col().border_t_1().border_color(p.line).children(
                layers.into_iter().enumerate().map(|(i, l)| {
                    let source = graph.sources.iter().find(|s| s.id == l.source_id).unwrap();
                    let t = l.layouts.get(variant);
                    let selected = self.selected_layer.as_ref() == Some(&l.id);
                    let layer = l.id.clone();
                    let (icon, detail) = match source.spec {
                        SourceKind::Window { .. } => (IconName::Monitor, "Captura de ventana"),
                        SourceKind::Camera { .. } => (IconName::Video, "Cámara"),
                        SourceKind::Overlay { .. } => (
                            IconName::Layers,
                            source
                                .overlay
                                .as_ref()
                                .map(creative::inspector::kind_label)
                                .unwrap_or("Overlay clásico"),
                        ),
                        SourceKind::Pattern => (IconName::Monitor, "Patrón libobs"),
                    };
                    let fault = health
                        .as_array()
                        .and_then(|a| a.iter().find(|x| x["id"] == source.id))
                        .and_then(|x| x["issue"].as_str())
                        .is_some_and(|x| !x.is_empty());
                    let mut toggle = t.clone();
                    toggle.visible = !toggle.visible;
                    row()
                        .id(("layer", i))
                        .role(Role::Group)
                        .aria_label(source.name.clone())
                        .focusable()
                        .tab_stop(true)
                        .focus_visible(|s| s.bg(p.selected).border_color(rgb(0x0a7aff)))
                        .on_key_down(cx.listener({
                            let layer = l.id.clone();
                            move |v, e: &KeyDownEvent, w, cx| {
                                if matches!(e.keystroke.key.as_str(), "enter" | "space") {
                                    v.selected_layer = Some(layer.clone());
                                    v.focus.focus(w, cx);
                                    cx.stop_propagation();
                                    cx.notify();
                                }
                            }
                        }))
                        .min_h(px(metrics::LAYER_ROW))
                        .px(px(8.))
                        .gap(px(10.))
                        .border_b_1()
                        .border_color(p.line)
                        .when(selected, |d| d.bg(p.selected))
                        .hover(|s| s.bg(p.selected))
                        .cursor_pointer()
                        .on_click(cx.listener(move |v, _, w, cx| {
                            v.selected_layer = Some(layer.clone());
                            if !v.field_focused(w, cx) {
                                v.focus.focus(w, cx);
                            }
                            cx.notify();
                        }))
                        .child(Icon::new(icon).size(px(16.)).text_color(p.secondary))
                        .child(
                            col()
                                .w(px(160.))
                                .min_w(px(96.))
                                .child(
                                    div()
                                        .text_size(px(metrics::BODY))
                                        .truncate()
                                        .child(source.name.clone()),
                                )
                                .child(
                                    row()
                                        .gap(px(5.))
                                        .child(dot(if fault {
                                            p.warn
                                        } else if !t.visible {
                                            p.muted
                                        } else {
                                            p.ready
                                        }))
                                        .child(
                                            label(
                                                if fault { "Sin señal" } else { detail },
                                                if fault { p.warn } else { p.muted },
                                            )
                                            .text_size(px(11.)),
                                        ),
                                ),
                        )
                        .child(
                            self.action(
                                ("eye", i),
                                "",
                                Command::SetTransform {
                                    scene_id: scene.id.clone(),
                                    layer_id: l.id.clone(),
                                    variant,
                                    transform: toggle,
                                },
                                cx,
                            )
                            .icon(if t.visible {
                                IconName::Eye
                            } else {
                                IconName::EyeOff
                            })
                            .tooltip(if t.visible {
                                "Ocultar capa"
                            } else {
                                "Mostrar capa"
                            }),
                        )
                        .child(
                            row()
                                .flex_1()
                                .when(selected, |d| d.child(self.inspector(cx)))
                                .when(!selected, |d| {
                                    d.child(label(
                                        format!("{:.0} × {:.0}", t.width, t.height),
                                        p.muted,
                                    ))
                                }),
                        )
                        .child(
                            self.popover(
                                ("layer-popup", i),
                                Panel::Layer,
                                quiet(("layer-more", i), "")
                                    .icon(IconName::Ellipsis)
                                    .tooltip("Acciones de capa"),
                                Some(l.id.clone()),
                                cx,
                            ),
                        )
                }),
            ))
    }
}
