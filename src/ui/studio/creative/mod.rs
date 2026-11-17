//! Native adapters and revision-bound drafts; Production remains the sole writer.
use super::*;
use crate::core::{
    data_dir,
    overlays::{
        OverlayCommand,
        assets::{AssetCatalog, AssetStatus, StagedImport},
    },
};

#[derive(Default)]
pub(super) struct Creative {
    assets: Vec<AssetStatus>,
    inventory_error: Option<String>,
    choosing: bool,
    copying: bool,
    staged: Option<(u64, StagedImport)>,
    import_message: String,
}
impl Studio {
    pub(super) fn refresh_assets(&mut self) {
        let r = self
            .production
            .apply(Command::Overlay(OverlayCommand::AssetInventory), "UI");
        if r["ok"] == true {
            match serde_json::from_value(r["result"]["assets"].clone()) {
                Ok(assets) => {
                    self.creative.assets = assets;
                    self.creative.inventory_error = None;
                }
                Err(_) => self.creative.inventory_error = Some("ASSET_INVENTORY_INVALID".into()),
            }
        } else {
            self.creative.inventory_error = Some(
                r["error"]["code"]
                    .as_str()
                    .unwrap_or("ASSET_INVENTORY_UNAVAILABLE")
                    .into(),
            );
        }
    }
    pub(super) fn poll_creative_import(&mut self, cx: &mut Context<Self>) {
        let Some((id, _)) = &self.creative.staged else {
            return;
        };
        let id = *id;
        let status = self.production.overlay_status();
        let job = &status["import"];
        if job["operation_id"] == id && job["phase"] == "running" {
            return;
        }
        self.creative.import_message = if job["operation_id"] != id {
            format!("Importación {id}: el núcleo ya muestra otra operación. Revisa el inventario.")
        } else if job["phase"] == "completed" {
            format!("Recurso disponible · importación {id}")
        } else {
            format!(
                "Importación {id}: {}",
                job["error"]["code"]
                    .as_str()
                    .unwrap_or("ASSET_IMPORT_FAILED")
            )
        };
        self.message = self.creative.import_message.clone();
        self.creative.staged = None;
        self.refresh_assets();
        cx.notify();
    }
    fn choose_asset(&mut self, cx: &mut Context<Self>) {
        if self.creative.choosing || self.creative.copying || self.creative.staged.is_some() {
            return;
        }
        self.creative.choosing = true;
        self.creative.import_message = "Selecciona una copia local autorizada.".into();
        let selection = cx.prompt_for_paths(PathPromptOptions {
            files: true,
            directories: false,
            multiple: false,
            prompt: Some("Importar recurso".into()),
        });
        cx.spawn(async move |this, cx| {
            let path = match selection.await {
                Ok(Ok(Some(mut paths))) if paths.len() == 1 => paths.pop(),
                Ok(Ok(None)) => None,
                _ => {
                    let _ = this.update(cx, |v, cx| {
                        v.creative.choosing = false;
                        v.creative.import_message = "ASSET_SELECTION_UNAVAILABLE".into();
                        cx.notify();
                    });
                    return;
                }
            };
            if this
                .update(cx, |v, cx| {
                    v.creative.choosing = false;
                    v.creative.copying = path.is_some();
                    v.creative.import_message = if path.is_some() {
                        "Copiando a la bandeja privada…"
                    } else {
                        "Selección cancelada."
                    }
                    .into();
                    cx.notify();
                })
                .is_err()
            {
                return;
            }
            let Some(path) = path else { return };
            let staged = cx
                .background_executor()
                .spawn(async move { AssetCatalog::new(data_dir())?.stage_selected_file(&path) })
                .await;
            let _ = this.update(cx, |v, cx| {
                v.creative.copying = false;
                match staged {
                    Ok(staged) => {
                        let r = v.command(
                            Command::Overlay(OverlayCommand::ImportAsset {
                                file_name: staged.file_name().into(),
                            }),
                            "UI",
                            cx,
                        );
                        if r["ok"] == true
                            && let Some(id) = r["result"]["import"]["operation_id"].as_u64()
                        {
                            v.creative.staged = Some((id, staged));
                            v.creative.import_message =
                                format!("Validando y normalizando · importación {id}…");
                        } else {
                            v.creative.import_message = v.message.clone();
                        }
                    }
                    Err(error) => v.creative.import_message = error.to_string(),
                }
                cx.notify();
            });
        })
        .detach();
        cx.notify();
    }
    pub(super) fn creative_library(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let busy = self.creative.choosing
            || self.creative.copying
            || self.creative.staged.is_some()
            || self.production.status()["output"] != "idle";
        let mut body = col().gap(px(10.))
            .child(label("Recursos locales", p.secondary))
            .child(quiet("import-picked-asset", "Importar archivo…").icon(IconName::Plus).disabled(busy)
                .on_click(cx.listener(|v, _, _, cx| v.choose_asset(cx))))
            .child(label("PNG / JPEG / WebP hasta 2048 × 2048. Video H.264 / VP8 / VP9 hasta 1080p, 60 fps y 60 s. Máximo 64 MiB por archivo.", p.muted))
            .child(label("La importación requiere la salida detenida. El audio de los videos permanece desactivado.", p.muted))
            .child(label(self.creative.import_message.clone(), p.secondary))
            .child(quiet("refresh-assets", "Actualizar recursos").disabled(busy).on_click(cx.listener(|v, _, _, cx| {v.refresh_assets(); cx.notify();})));
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
