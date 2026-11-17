use super::*;
use crate::core::overlays::{Definition, Shape, WidgetKind, assets::AssetKind};
impl Studio {
    fn asset_library(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let state = self.production.overlay_status();
        let job = &state["import"];
        let busy = self.creative.choosing
            || self.creative.copying
            || self.creative.staged.is_some()
            || job["phase"] == "running"
            || self.production.status()["output"] != "idle";
        let mut body = col().gap(px(10.))
            .child(label("Recursos locales", p.secondary))
            .child(quiet("import-picked-asset", "Importar archivo…").icon(IconName::Plus).disabled(busy)
                .on_click(cx.listener(|v, _, _, cx| v.choose_asset(cx))))
            .child(label("PNG / JPEG / WebP hasta 2048 × 2048. Video H.264 / VP8 / VP9 hasta 1080p, 60 fps y 60 s. Máximo 64 MiB por archivo.", p.muted))
            .child(label("La importación requiere la salida detenida. El audio de los videos permanece desactivado.", p.muted))
            .child(label(self.creative.import_message.clone(), p.secondary))
            .child(quiet("refresh-assets", "Actualizar recursos").disabled(busy).on_click(cx.listener(|v, _, _, cx| {v.refresh_assets(); cx.notify();})));
        if let Some(id) = job["operation_id"].as_u64() {
            body = body.child(label(
                format!(
                    "Importación #{id}: {}",
                    match job["phase"].as_str() {
                        Some("running") => "procesando…",
                        Some("completed") => "finalizada",
                        Some("failed") => "fallida",
                        _ => "estado no disponible",
                    }
                ),
                if job["phase"] == "failed" {
                    p.warn
                } else {
                    p.secondary
                },
            ));
            if let Some(code) = job["error"]["code"].as_str() {
                body = body.child(label(code.to_owned(), p.warn));
            }
        }
        if let Some(error) = &self.creative.inventory_error {
            body = body.child(label(error.clone(), p.warn));
        }
        for (i, row) in self.creative.assets.iter().enumerate() {
            let refs = self
                .production
                .graph()
                .sources
                .iter()
                .filter(|s| {
                    s.overlay.as_ref().and_then(|d| d.asset_id()) == Some(row.asset.id.as_str())
                })
                .collect::<Vec<_>>();
            let scenes = self
                .production
                .graph()
                .scenes
                .iter()
                .filter(|scene| {
                    scene
                        .layers
                        .iter()
                        .any(|layer| refs.iter().any(|s| s.id == layer.source_id))
                })
                .map(|scene| scene.name.clone())
                .collect::<Vec<_>>();
            body = body.child(
                col()
                    .gap(px(5.))
                    .py(px(8.))
                    .border_t_1()
                    .border_color(p.line)
                    .child(label(
                        format!(
                            "{} · {} × {} · {:.1} MiB",
                            &row.asset.id[..18],
                            row.asset.width,
                            row.asset.height,
                            row.asset.bytes as f64 / 1048576.
                        ),
                        p.secondary,
                    ))
                    .child(label(
                        if scenes.is_empty() {
                            "Sin uso en escenas".into()
                        } else {
                            format!("En uso: {}", scenes.join(", "))
                        },
                        p.muted,
                    ))
                    .when_some(row.error.clone(), |d, error| {
                        d.child(label(
                            format!("{error} · Reimporta el original para recuperar este ID."),
                            p.warn,
                        ))
                    })
                    .child(
                        quiet(
                            ("use-asset", i),
                            if row.asset.kind == AssetKind::Image {
                                "Crear imagen"
                            } else {
                                "Crear video"
                            },
                        )
                        .disabled(busy || row.error.is_some())
                        .on_click(cx.listener({
                            let asset = row.asset.clone();
                            move |v, _, w, cx| {
                                let definition = if asset.kind == AssetKind::Image {
                                    Definition::Image {
                                        asset_id: asset.id.clone(),
                                        opacity: 1.,
                                    }
                                } else {
                                    Definition::Video {
                                        asset_id: asset.id.clone(),
                                        opacity: 1.,
                                        looping: true,
                                    }
                                };
                                v.begin_overlay_draft(
                                    definition,
                                    None,
                                    if asset.kind == AssetKind::Image {
                                        "Imagen"
                                    } else {
                                        "Video"
                                    }
                                    .into(),
                                    w,
                                    cx,
                                );
                            }
                        })),
                    )
                    .child(
                        self.action(
                            ("remove-asset", i),
                            "Eliminar recurso",
                            Command::Overlay(OverlayCommand::RemoveAsset {
                                asset_id: row.asset.id.clone(),
                            }),
                            cx,
                        )
                        .disabled(busy || !refs.is_empty()),
                    ),
            );
        }
        body
    }
}
impl Studio {
    pub(in crate::ui::studio) fn creative_library(&self, cx: &mut Context<Self>) -> Div {
        if self.creative.draft.is_some() {
            return self.creative_inspector(cx);
        }
        let p = Palette::new(self.dark);
        let mut body = col().gap(px(12.)).child(
            row().children(
                [
                    (LibraryTab::Create, "Crear"),
                    (LibraryTab::Assets, "Recursos"),
                    (LibraryTab::Presets, "Presets"),
                    (LibraryTab::Sources, "Fuentes"),
                ]
                .into_iter()
                .enumerate()
                .map(|(i, (tab, name))| {
                    quiet(("library-tab", i), name)
                        .selected(self.creative.tab == tab)
                        .on_click(cx.listener(move |v, _, _, cx| {
                            v.creative.tab = tab;
                            if tab == LibraryTab::Assets {
                                v.refresh_assets();
                            }
                            cx.notify();
                        }))
                }),
            ),
        );
        let state = self.production.status();
        let busy = state["output"] != "idle"
            || self.production.overlay_status()["runtime"]["animations"]["busy"] == true
            || matches!(
                state["transition"]["phase"].as_str(),
                Some("preparing" | "running")
            );
        match self.creative.tab {
            LibraryTab::Assets => body = body.child(self.asset_library(cx)),
            LibraryTab::Create => {
                body=body.child(label("Contenido propio, compuesto en libobs. Los nuevos recursos se añaden a la escena activa.",p.secondary));
                for (i, (name, definition)) in [
                    ("Texto", draft::text_default()),
                    ("Rectángulo", draft::shape_default(Shape::Rectangle)),
                    ("Círculo", draft::shape_default(Shape::Circle)),
                    (
                        "Cuenta regresiva",
                        draft::widget_default(WidgetKind::Countdown),
                    ),
                    ("Alerta local", draft::widget_default(WidgetKind::Alert)),
                ]
                .into_iter()
                .enumerate()
                {
                    body = body.child(
                        quiet(("create-overlay-kind", i), name)
                            .disabled(busy)
                            .on_click(cx.listener(move |v, _, w, cx| {
                                v.begin_overlay_draft(definition.clone(), None, name.into(), w, cx)
                            })),
                    );
                }
                body=body.child(label("Para crear una imagen o video, selecciona un archivo en Recursos. Los lower thirds están en Presets.",p.muted));
            }
            LibraryTab::Presets => {
                if let Some(presets) = self.creative.presets["presets"].as_array() {
                    for (i, preset) in presets.iter().enumerate() {
                        let preset = preset.clone();
                        body = body.child(
                            quiet(
                                ("create-preset", i),
                                preset["name"].as_str().unwrap_or("Preset").to_owned(),
                            )
                            .disabled(busy)
                            .on_click(cx.listener(
                                move |v, _, w, cx| {
                                    let parsed = serde_json::from_value(preset["id"].clone())
                                        .and_then(|kind| {
                                            serde_json::from_value(preset["parameters"].clone())
                                                .map(|params| (kind, params))
                                        });
                                    match parsed {
                                        Ok((preset_kind, parameters)) => {
                                            let r = v.command(
                                                Command::Overlay(
                                                    OverlayCommand::InstantiateOverlayPreset {
                                                        scene_id: v
                                                            .production
                                                            .graph()
                                                            .active_scene
                                                            .clone(),
                                                        preset: preset_kind,
                                                        parameters,
                                                    },
                                                ),
                                                "UI",
                                                cx,
                                            );
                                            if r["ok"] == true
                                                && let Some(ids) =
                                                    r["result"]["source_ids"].as_array()
                                            {
                                                let source = v
                                                    .production
                                                    .graph()
                                                    .sources
                                                    .iter()
                                                    .find(|s| {
                                                        ids.iter().any(|id| id == &s.id)
                                                            && matches!(
                                                                s.overlay,
                                                                Some(Definition::Widget { .. })
                                                            )
                                                    })
                                                    .cloned();
                                                if let Some(source) = source {
                                                    v.selected_layer = v
                                                        .production
                                                        .graph()
                                                        .scene(&v.production.graph().active_scene)
                                                        .ok()
                                                        .and_then(|s| {
                                                            s.layers
                                                                .iter()
                                                                .find(|l| l.source_id == source.id)
                                                        })
                                                        .map(|l| l.id.clone());
                                                    v.edit_overlay(&source.id, w, cx);
                                                }
                                            }
                                        }
                                        Err(_) => {
                                            v.message = "OVERLAY_PRESET_INVALID".into();
                                            cx.notify();
                                        }
                                    }
                                },
                            )),
                        );
                    }
                }
                body=body.child(label("Presets v1 editables. Lower Third y BRB empiezan ocultos; usa Mostrar. Starting Soon comienza preparado; usa Iniciar. BRB incluye una capa Accent que puedes animar con Scale in.",p.muted));
            }
            LibraryTab::Sources => {
                for (i, source) in self
                    .production
                    .graph()
                    .sources
                    .iter()
                    .filter(|s| s.overlay.is_some())
                    .enumerate()
                {
                    let id = source.id.clone();
                    let sid = id.clone();
                    let source_id = id.clone();
                    body = body.child(
                        col()
                            .gap(px(6.))
                            .border_t_1()
                            .border_color(p.line)
                            .py(px(8.))
                            .child(label(
                                format!(
                                    "{} · {}",
                                    source.name,
                                    inspector::kind_label(source.overlay.as_ref().unwrap())
                                ),
                                p.secondary,
                            ))
                            .child(
                                quiet(("inspect-overlay-source", i), "Editar fuente").on_click(
                                    cx.listener(move |v, _, w, cx| {
                                        v.selected_layer = v
                                            .production
                                            .graph()
                                            .scene(&v.production.graph().active_scene)
                                            .ok()
                                            .and_then(|s| {
                                                s.layers.iter().find(|l| l.source_id == id)
                                            })
                                            .map(|l| l.id.clone());
                                        v.edit_overlay(&id, w, cx);
                                    }),
                                ),
                            )
                            .child(
                                quiet(("reuse-overlay-source", i), "Añadir capa en esta escena")
                                    .disabled(busy)
                                    .on_click(cx.listener(move |v, _, w, cx| {
                                        let r = v.command(
                                            Command::AddLayer {
                                                scene_id: v.production.graph().active_scene.clone(),
                                                source_id: sid.clone(),
                                            },
                                            "UI",
                                            cx,
                                        );
                                        if r["ok"] == true {
                                            v.selected_layer = v
                                                .production
                                                .graph()
                                                .scene(&v.production.graph().active_scene)
                                                .ok()
                                                .and_then(|s| {
                                                    s.layers
                                                        .iter()
                                                        .rev()
                                                        .find(|l| l.source_id == sid)
                                                })
                                                .map(|l| l.id.clone());
                                            v.edit_overlay(&sid, w, cx);
                                        }
                                    })),
                            )
                            .child(
                                self.action(
                                    ("remove-overlay-source", i),
                                    "Eliminar fuente sin uso",
                                    Command::RemoveSource { source_id },
                                    cx,
                                )
                                .disabled(
                                    busy || self
                                        .production
                                        .graph()
                                        .scenes
                                        .iter()
                                        .any(|s| s.layers.iter().any(|l| l.source_id == source.id)),
                                ),
                            ),
                    );
                }
                body=body.child(label("Reutilizar añade una capa; conserva la misma fuente y sus recursos. Eliminar una capa no elimina su fuente.",p.muted));
            }
        }
        if busy {
            body=body.child(label("La creación y la gestión de recursos requieren salida detenida y ninguna transición o animación pendiente.",p.warn));
        }
        body
    }
}
