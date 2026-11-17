use super::*;
impl Studio {
    pub(super) fn render_panel(&self, panel: Panel, cx: &mut Context<Self>) -> impl IntoElement {
        let panel = panel.id();
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let title = match panel {
            "project" => "Mi producción",
            "add-source" => "Añadir fuente",
            "audio" => "Entrada de audio",
            "output" => "Salida RTMP local",
            "agent" => "Control por agentes",
            "layer" => "Propiedades de capa",
            "profiles" => "Perfiles de salida",
            "settings" => "Preferencias y diagnóstico",
            "scenes" => "Escenas y transiciones",
            _ => "Estudio",
        };
        let mut content = col().gap(px(8.));
        match panel {
            "project" => {
                content = content
                    .child(self.action("save", "Guardar proyecto", Command::SaveProject, cx))
                    .child(self.action(
                        "load",
                        "Restaurar proyecto guardado",
                        Command::LoadProject,
                        cx,
                    ))
                    .child(self.scene_settings(cx))
                    .child(label("Desarrollo · contenido propio", p.muted))
                    .child(self.action(
                        "fixture",
                        "Abrir ventana controlada",
                        Command::SetTestWindow { open: true },
                        cx,
                    ))
                    .child(self.action(
                        "fixture-close",
                        "Cerrar ventana controlada",
                        Command::SetTestWindow { open: false },
                        cx,
                    ));
            }
            "agent" => {
                content = content
                    .child("CLI y MCP controlan este mismo núcleo local.")
                    .child(label(
                        format!(
                            "Revisión {} · {}",
                            self.production.revision, self.production.last_action
                        ),
                        p.secondary,
                    ))
                    .child(label("Propuestas visuales de agentes: futuras.", p.muted));
            }
            "add-source" | "audio" => {
                content = content.child(self.device_picker(panel, cx));
            }
            "output" => {
                content = content.child(self.output_settings(cx));
            }
            "profiles" => {
                content = content.child(self.profile_settings(cx));
            }
            "settings" => {
                content = content.child(self.studio_settings(cx));
            }
            "scenes" => {
                content = content.child(self.scene_settings(cx));
            }
            "layer" => {
                if let Some(l) = scene
                    .layers
                    .iter()
                    .find(|l| Some(&l.id) == self.selected_layer.as_ref())
                {
                    let variant = self.production.project.variant;
                    let t = l.layouts.get(variant);
                    content = content
                        .child(label(
                            format!(
                                "{} · X {} / Y {} · {} × {}",
                                l.id, t.x, t.y, t.width, t.height
                            ),
                            p.secondary,
                        ))
                        .children(
                            [("lower", "Bajar capa", -1_i32), ("raise", "Subir capa", 1)].map(
                                |(id, title, delta)| {
                                    let mut transform = t.clone();
                                    transform.order =
                                        (transform.order as i32 + delta).clamp(0, 31) as u32;
                                    self.action(
                                        id,
                                        title,
                                        Command::SetTransform {
                                            scene_id: scene.id.clone(),
                                            layer_id: l.id.clone(),
                                            variant,
                                            transform,
                                        },
                                        cx,
                                    )
                                },
                            ),
                        )
                        .child(self.action(
                            "reconnect-layer",
                            "Reconectar fuente",
                            Command::ReconnectSource {
                                source_id: l.source_id.clone(),
                            },
                            cx,
                        ))
                        .child(self.action(
                            "remove-layer",
                            "Eliminar capa",
                            Command::RemoveLayer {
                                scene_id: scene.id.clone(),
                                layer_id: l.id.clone(),
                            },
                            cx,
                        ));
                    if matches!(
                        graph
                            .sources
                            .iter()
                            .find(|s| s.id == l.source_id)
                            .unwrap()
                            .spec,
                        SourceKind::Overlay { .. }
                    ) {
                        let source_id = l.source_id.clone();
                        content = content
                            .child(forms::field(
                                "Color overlay (RGB hexadecimal)",
                                &self.forms.overlay_color,
                                p,
                            ))
                            .child(quiet("apply-overlay-color", "Aplicar color").on_click(
                                cx.listener(move |v, _, _, cx| {
                                    let text = v.forms.overlay_color.read(cx).value();
                                    if text.len() == 6
                                        && text.bytes().all(|b| b.is_ascii_hexdigit())
                                    {
                                        let color = u32::from_str_radix(&text, 16).unwrap();
                                        v.form_submit(
                                            Command::SetOverlayColor {
                                                source_id: source_id.clone(),
                                                color,
                                            },
                                            cx,
                                        );
                                    } else {
                                        v.message = "Usa seis dígitos RGB hexadecimales".into();
                                        cx.notify();
                                    }
                                }),
                            ));
                        content = content.child(
                            row().children(
                                [
                                    ("Mint", 0x33e8b5),
                                    ("Ámbar", 0xffb547),
                                    ("Blanco", 0xffffff),
                                ]
                                .map(|(name, color)| {
                                    self.action(
                                        name,
                                        name,
                                        Command::SetOverlayColor {
                                            source_id: l.source_id.clone(),
                                            color,
                                        },
                                        cx,
                                    )
                                }),
                            ),
                        );
                    }
                }
            }
            _ => {}
        }

        col()
            .w(px(420.))
            .max_h(px(540.))
            .p(px(18.))
            .gap(px(14.))
            .child(
                row()
                    .child(
                        div()
                            .flex_1()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child(title),
                    )
                    .child(
                        quiet("close-panel", "")
                            .icon(IconName::X)
                            .tooltip("Cerrar")
                            .on_click(cx.listener(|v, _, w, cx| {
                                v.panel = None;
                                v.picker = None;
                                v.focus.focus(w, cx);
                                cx.notify();
                            })),
                    ),
            )
            .when(self.forms.revision != self.production.revision, |d| {
                d.child(label(
                    "El estado cambió. Reabre para actualizar los formularios.",
                    p.warn,
                ))
            })
            .child(content.id("panel-scroll").overflow_y_scroll())
            .child(label(self.message.clone(), p.secondary))
    }
}
