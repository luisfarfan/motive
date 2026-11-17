use super::*;
impl Studio {
    pub(super) fn choose_asset(&mut self, cx: &mut Context<Self>) {
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
}
