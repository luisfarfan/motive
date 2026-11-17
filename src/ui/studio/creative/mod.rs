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
    draft: Option<draft::Draft>,
    tab: LibraryTab,
    editor_tab: EditorTab,
    presets: Value,
    animation: Option<runtime::AnimationDraft>,
    last_animation: Option<u64>,
}
impl Studio {
    pub(super) fn creative_scroll_key(&self) -> String {
        match &self.creative.draft {
            Some(d) => format!(
                "{}-{}",
                d.source_id
                    .clone()
                    .unwrap_or_else(|| format!("new-{}", inspector::kind_label(&d.definition))),
                self.creative.editor_tab as u8
            ),
            None => format!("library-{}", self.creative.tab as u8),
        }
    }
    pub(super) fn has_overlay_draft_for(&self, id: &str) -> bool {
        self.creative
            .draft
            .as_ref()
            .is_some_and(|d| d.source_id.as_deref() == Some(id))
    }
    pub(super) fn refresh_assets(&mut self) {
        let presets = self
            .production
            .apply(Command::Overlay(OverlayCommand::OverlayPresets), "UI");
        if presets["ok"] == true {
            self.creative.presets = presets["result"].clone();
        }
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
}

mod draft;
mod importing;
pub(super) mod inspector;
mod library;
mod runtime;

#[derive(Default, Clone, Copy, PartialEq, Eq)]
enum LibraryTab {
    #[default]
    Create,
    Assets,
    Presets,
    Sources,
}
#[derive(Default, Clone, Copy, PartialEq, Eq)]
enum EditorTab {
    #[default]
    Content,
    Live,
    Animation,
}
