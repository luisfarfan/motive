use super::*;
impl Studio {
    pub(super) fn device_picker(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let mut content = col().gap(px(8.));

        {
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
            content = content
                .child(label("Fuentes sin capas · liberar recursos", p.muted))
                .children(
                    graph
                        .sources
                        .iter()
                        .filter(|source| {
                            !graph.scenes.iter().any(|scene| {
                                scene
                                    .layers
                                    .iter()
                                    .any(|layer| layer.source_id == source.id)
                            })
                        })
                        .enumerate()
                        .map(|(i, source)| {
                            self.action(
                                ("release-source", i),
                                format!("Liberar {}…", source.name),
                                Command::RemoveSource {
                                    source_id: source.id.clone(),
                                },
                                cx,
                            )
                        }),
                );
        }
        if let Some(kind) = self.picker {
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
                let command = Command::AddSource {
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
                };
                Some(self.action(("device", i), name.to_owned(), command, cx))
            }));
            content = content.child(quiet("permission", "Revisar permiso de macOS").on_click(
                cx.listener(move |v, _, _, cx| {
                    v.production.engine.request_permission(match kind {
                        "cameras" => 2,
                        _ => 0,
                    });
                    v.devices = v.production.engine.devices();
                    cx.notify();
                }),
            ));
        }

        content
    }
}
