use super::*;
impl Studio {
    pub(super) fn action(
        &self,
        id: impl Into<ElementId>,
        text: impl Into<SharedString>,
        command: Command,
        cx: &mut Context<Self>,
    ) -> Button {
        quiet(id, text).on_click(cx.listener(move |v, _, _, cx| {
            v.command(command.clone(), "UI", cx);
        }))
    }
    pub(super) fn popover(
        &self,
        id: impl Into<ElementId>,
        panel: &'static str,
        trigger: Button,
        layer: Option<String>,
        cx: &mut Context<Self>,
    ) -> gpui_kit::component::popover::Popover {
        let weak = cx.entity().downgrade();
        let open = self.panel == Some(panel) && (layer.is_none() || layer == self.selected_layer);
        gpui_kit::component::popover::Popover::new(id)
            .p_0()
            .bg(Palette::new(self.dark).raised)
            .rounded(px(10.))
            .open(open)
            .trigger(trigger)
            .on_open_change(cx.listener(move |v, open, _, cx| {
                if *open {
                    v.panel = Some(panel);
                    if let Some(layer) = &layer {
                        v.selected_layer = Some(layer.clone());
                    }
                    v.devices = v.production.engine.devices();
                } else {
                    v.panel = None;
                }
                v.picker = None;
                cx.notify();
            }))
            .content(move |_, _, cx| {
                weak.update(cx, |v, cx| v.render_panel(panel, cx).into_any_element())
                    .unwrap_or_else(|_| div().into_any_element())
            })
    }
    pub(super) fn panel_button(
        &self,
        id: &'static str,
        text: &'static str,
        icon: IconName,
        cx: &mut Context<Self>,
    ) -> gpui_kit::component::popover::Popover {
        let disabled = id == "output" && self.production.status()["output"] != "idle";
        self.popover(
            id,
            id,
            quiet((ElementId::from("trigger"), id), text)
                .icon(icon)
                .tooltip(match id {
                    "audio" => "Seleccionar entrada de audio",
                    "add-source" => "Añadir fuente",
                    _ => text,
                })
                .disabled(disabled),
            None,
            cx,
        )
    }
    pub(super) fn header(&self, status: &Value, cx: &mut Context<Self>) -> TitleBar {
        let p = Palette::new(self.dark);
        let output = status["output"].as_str().unwrap_or("error");
        let active = matches!(output, "recording" | "streaming");
        let busy = matches!(output, "connecting" | "cancel_pending" | "stopping");
        let source_issue = status["issues"].as_array().is_some_and(|a| !a.is_empty());
        let color = if active {
            p.live
        } else if busy || output == "error" || status["recovery_required"] == true || source_issue {
            p.warn
        } else {
            p.ready
        };
        let caption = match output {
            "recording" => "Grabando",
            "streaming" => "RTMP local",
            "connecting" => "Conectando",
            "cancel_pending" => "Cancelación pendiente",
            "stopping" => "Finalizando",
            "error" => "Error de salida",
            _ => {
                if status["recovery_required"] == true {
                    "Requiere recuperación"
                } else if source_issue {
                    "Fuente no preparada"
                } else {
                    "Listo"
                }
            }
        };
        let seconds = status["stats"]["output_frames"].as_u64().unwrap_or(0) / 30;
        TitleBar::new()
            .h(px(52.))
            .pl(px(88.))
            .pr(px(14.))
            .bg(p.raised)
            .border_color(p.line)
            .child(
                row()
                    .flex_1()
                    .min_w_0()
                    .child(
                        div()
                            .size(px(18.))
                            .rounded(px(5.))
                            .bg(rgb(0x5fe3c6))
                            .text_color(rgb(0x0f2a2e))
                            .font_weight(FontWeight::BOLD)
                            .text_size(px(13.))
                            .flex()
                            .items_center()
                            .justify_center()
                            .child(
                                Icon::default()
                                    .data(include_bytes!("../assets/motive-mark.svg"))
                                    .size(px(18.)),
                            ),
                    )
                    .child(
                        div()
                            .font_weight(FontWeight::SEMIBOLD)
                            .text_size(px(15.))
                            .child("motive"),
                    )
                    .child(div().mx(px(6.)).w(px(1.)).h(px(18.)).bg(p.line))
                    .child(self.panel_button(
                        "project",
                        "Mi producción",
                        IconName::ChevronDown,
                        cx,
                    )),
            )
            .child(
                row()
                    .px(px(12.))
                    .h(px(30.))
                    .rounded_full()
                    .bg(color.opacity(0.08))
                    .text_color(color)
                    .child(dot(color))
                    .child(caption)
                    .when(active, |d| {
                        d.child(
                            div()
                                .font_weight(FontWeight::SEMIBOLD)
                                .text_color(p.ink)
                                .child(format!(
                                    "{:02}:{:02}:{:02}",
                                    seconds / 3600,
                                    seconds / 60 % 60,
                                    seconds % 60
                                )),
                        )
                    }),
            )
            .child(
                row()
                    .flex_1()
                    .justify_end()
                    .child(
                        quiet("appearance", "")
                            .icon(if self.dark {
                                IconName::Sun
                            } else {
                                IconName::Moon
                            })
                            .tooltip("Cambiar tema de Motive")
                            .on_click(cx.listener(|v, _, w, cx| {
                                v.dark = !v.dark;
                                Palette::apply(v.dark, Some(w), cx);
                                cx.notify();
                            })),
                    )
                    .child(self.panel_button("agent", "MCP", IconName::Circle, cx))
                    .child(
                        control(
                            "record",
                            if output == "recording" {
                                "Grabando"
                            } else {
                                "Grabar"
                            },
                        )
                        .icon(IconName::Circle)
                        .disabled(
                            output != "idle" || status["recovery_required"] == true || source_issue,
                        )
                        .on_click(cx.listener(|v, _, _, cx| {
                            v.command(Command::StartRecording, "UI", cx);
                        })),
                    )
                    .child(self.panel_button("output", "Emitir", IconName::Radio, cx))
                    .when(output != "idle", |d| {
                        d.child(
                            control(
                                "stop",
                                if output == "connecting" {
                                    "Cancelar"
                                } else if output == "error" {
                                    "Recuperar"
                                } else {
                                    "Finalizar"
                                },
                            )
                            .icon(IconName::Square)
                            .disabled(matches!(output, "cancel_pending" | "stopping"))
                            .on_click(cx.listener(
                                move |v, _, _, cx| {
                                    let cmd = match v.production.status()["output"].as_str() {
                                        Some("connecting") => Command::CancelOutput,
                                        Some("error") => Command::RecoverOutput,
                                        _ => Command::StopOutput,
                                    };
                                    v.command(cmd, "UI", cx);
                                },
                            )),
                        )
                    }),
            )
    }
}
