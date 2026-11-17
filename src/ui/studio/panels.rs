use super::*;
impl Studio {
    pub(super) fn render_panel(
        &self,
        panel: &'static str,
        cx: &mut Context<Self>,
    ) -> impl IntoElement {
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
                    .child(label("Escenas en vivo", p.muted))
                    .child(
                        row()
                            .child(self.action(
                                "cut",
                                "Cut",
                                Command::ConfigureTransition {
                                    transition: TransitionConfig {
                                        kind: TransitionKind::Cut,
                                        duration_ms: 0,
                                    },
                                },
                                cx,
                            ))
                            .child(self.action(
                                "fade",
                                "Fade · 300 ms",
                                Command::ConfigureTransition {
                                    transition: TransitionConfig {
                                        kind: TransitionKind::Fade,
                                        duration_ms: 300,
                                    },
                                },
                                cx,
                            )),
                    )
                    .child(self.action(
                        "remove-scene",
                        "Eliminar escena actual",
                        Command::RemoveScene {
                            scene_id: scene.id.clone(),
                        },
                        cx,
                    ))
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
                if panel == "add-source" {
                    content = content
                        .child(
                            row().children(
                                [
                                    ("windows", "Ventana", IconName::Monitor),
                                    ("cameras", "Webcam", IconName::Video),
                                ]
                                .map(|(kind, title, icon)| {
                                    quiet(kind, title).icon(icon).on_click(cx.listener(
                                        move |v, _, _, cx| {
                                            v.devices = v.production.engine.devices();
                                            v.picker = Some(kind);
                                            cx.notify();
                                        },
                                    ))
                                }),
                            ),
                        )
                        .child(
                            row()
                                .child(
                                    self.action(
                                        "add-overlay",
                                        "Overlay",
                                        Command::AddSource {
                                            scene_id: scene.id.clone(),
                                            name: "Overlay".into(),
                                            source: SourceInput::Overlay { color: 0x33e8b5 },
                                        },
                                        cx,
                                    )
                                    .icon(IconName::Layers),
                                )
                                .child(
                                    self.action(
                                        "add-pattern",
                                        "Patrón",
                                        Command::AddSource {
                                            scene_id: scene.id.clone(),
                                            name: "Patrón".into(),
                                            source: SourceInput::Pattern,
                                        },
                                        cx,
                                    )
                                    .icon(IconName::Monitor),
                                ),
                        )
                        .child(label("Reutilizar una fuente existente", p.muted))
                        .children(graph.sources.iter().enumerate().map(|(i, s)| {
                            self.action(
                                ("reuse", i),
                                s.name.clone(),
                                Command::AddLayer {
                                    scene_id: scene.id.clone(),
                                    source_id: s.id.clone(),
                                },
                                cx,
                            )
                        }));
                } else {
                    content = content
                        .child(
                            row()
                                .child(self.action(
                                    "audio-none",
                                    "Sin audio",
                                    Command::SelectAudio { id: "none".into() },
                                    cx,
                                ))
                                .child(self.action(
                                    "audio-tone",
                                    "Tono de prueba",
                                    Command::SelectAudio { id: "tone".into() },
                                    cx,
                                )),
                        )
                        .child(label("Micrófonos disponibles", p.muted));
                }
                let kind = if panel == "audio" {
                    Some("audio")
                } else {
                    self.picker
                };
                if let Some(kind) = kind {
                    let entries = self.devices[kind].as_array().cloned().unwrap_or_default();
                    if entries.is_empty() {
                        content = content.child(label(
                            "No hay dispositivos disponibles. Revisa conexión y permisos.",
                            p.warn,
                        ));
                    }
                    content = content.children(entries.iter().enumerate().filter_map(|(i, d)| {
                        let name = d["name"].as_str()?;
                        let clean = name
                            .chars()
                            .filter(|c| !c.is_control())
                            .take(80)
                            .collect::<String>();
                        let command = match kind {
                            "audio" => Command::SelectAudio {
                                id: d["id"].as_str()?.into(),
                            },
                            _ => Command::AddSource {
                                scene_id: scene.id.clone(),
                                name: if clean.trim().is_empty() {
                                    "Fuente".into()
                                } else {
                                    clean
                                },
                                source: if kind == "windows" {
                                    SourceInput::Window {
                                        window_id: d["id"].as_u64()? as u32,
                                    }
                                } else {
                                    SourceInput::Camera {
                                        device_id: d["id"].as_str()?.into(),
                                    }
                                },
                            },
                        };
                        Some(self.action(("device", i), name.to_owned(), command, cx))
                    }));
                    content =
                        content.child(quiet("permission", "Revisar permiso de macOS").on_click(
                            cx.listener(move |v, _, _, cx| {
                                v.production.engine.request_permission(match kind {
                                    "audio" => 1,
                                    "cameras" => 2,
                                    _ => 0,
                                });
                                v.devices = v.production.engine.devices();
                                cx.notify();
                            }),
                        ));
                }
            }
            "output" => {
                let s = self.production.status();
                content = content
                    .child("Solo receptor local controlado · una salida a la vez")
                    .child(label(
                        if let Some(port) = s["output_configuration"]["endpoint"]["port"].as_u64() {
                            format!("Receptor local · 127.0.0.1:{port}")
                        } else {
                            "Sin receptor local configurado · usa CLI o MCP".into()
                        },
                        p.secondary,
                    ))
                    .child(self.action(
                        "preflight",
                        "Comprobar salida",
                        Command::PreflightOutput {
                            target: crate::core::output::OutputTarget::Streaming,
                        },
                        cx,
                    ))
                    .child(self.action(
                        "start-stream",
                        "Iniciar RTMP local",
                        Command::StartStream,
                        cx,
                    ))
                    .child(self.action(
                        "recover-output",
                        "Recuperar salida",
                        Command::RecoverOutput,
                        cx,
                    ))
                    .child(label(
                        "No se habilitan destinos públicos desde esta pantalla.",
                        p.muted,
                    ));
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
            .child(content.id("panel-scroll").overflow_y_scroll())
            .child(label(self.message.clone(), p.secondary))
    }
}
