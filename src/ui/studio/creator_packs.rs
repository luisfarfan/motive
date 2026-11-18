//! Reviewed owner installation; no project mutations or capability inference here.
use super::*;
use crate::core::creator_packs::LocalPackReview;
use gpui_kit::component::{
    WindowExt,
    dialog::{DialogAction, DialogButtonProps, DialogClose, DialogFooter},
};
use std::{cell::RefCell, rc::Rc};

impl Studio {
    pub(super) fn matchday_card(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let report = self.production.creator_packs_status();
        let phase = report["phase"].as_str().unwrap_or("unknown");
        let status = self.production.status();
        let closing = self.production.shutdown_requested
            || status["output_lifecycle"]["shutdown_pending"] == true;
        let mut card = col().gap(px(7.)).p(px(10.)).rounded(px(8.)).bg(p.sunken)
            .child(label("MATCHDAY · Creator Pack", p.ink).font_weight(FontWeight::SEMIBOLD))
            .child(label("Escenas, overlays y Live Deck de producción. Requiere salidas detenidas y ningún trabajo pendiente.", p.secondary))
            .child(quiet("review-matchday-install", "Revisar instalación de MATCHDAY")
                .disabled(closing || phase != "not_installed")
                .on_click(cx.listener(|view, _, window, cx| {
                    match view.production.prepare_matchday_install() {
                        Ok(review) => view.confirm_matchday_install(review, window, cx),
                        Err(error) => { view.message = error.to_string(); cx.notify(); }
                    }
                })));
        if phase == "completed" || phase == "partial" {
            card = card
                .child(label(
                    format!(
                        "{} · pasos {}/{}",
                        if phase == "completed" {
                            "Instalación terminada"
                        } else {
                            "Instalación parcial"
                        },
                        report["steps_completed"],
                        report["steps_total"]
                    ),
                    if phase == "completed" {
                        p.ready
                    } else {
                        p.warn
                    },
                ))
                .child(label(
                    format!(
                        "Recursos vinculados: {} escenas · {} fuentes · {} capas",
                        report["bindings"]["scenes"]
                            .as_object()
                            .map_or(0, |v| v.len()),
                        report["bindings"]["sources"]
                            .as_object()
                            .map_or(0, |v| v.len()),
                        report["bindings"]["layers"]
                            .as_object()
                            .map_or(0, |v| v.len())
                    ),
                    p.secondary,
                ));
            if let Some(error) = report["error"].as_str() {
                card = card.child(label(format!("{error} · Los recursos ya creados se conservan. Revisa escenas y fuentes; no se reintentará la instalación automáticamente."),p.warn));
            }
            if let Some(error) = report["restore_error"].as_str() {
                card = card.child(label(
                    format!("No se pudo solicitar el regreso a la escena anterior: {error}"),
                    p.warn,
                ));
            } else if report["restore_accepted"] == true {
                card = card.child(label("Se solicitó volver a la escena anterior. Comprueba el preview antes de continuar.",p.secondary));
            }
            card = card.child(label("La instalación no guardó el proyecto ni Show Control. Guarda ambos cuando hayas revisado el resultado.",p.secondary))
                .child(self.action("save-matchday-project","Guardar proyecto",Command::SaveProject,cx).disabled(closing));
            if phase == "completed" {
                card = card.child(label("Selecciona la escena MATCHDAY de producción desde Escenas. Revisa los botones de Live Deck antes de usarlos.",p.secondary));
            }
        }
        card
    }

    fn confirm_matchday_install(
        &mut self,
        review: LocalPackReview,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let summary = review.summary();
        let memory = summary["estimated_texture_bytes"]
            .as_u64()
            .map(|bytes| format!("{:.1} MiB", bytes as f64 / 1_048_576.))
            .unwrap_or_else(|| "estimación no disponible".into());
        let description = format!(
            "MATCHDAY · versión {}\n{} escenas · {} fuentes · {} capas · {} pasos\nPresupuesto estimado de texturas: {memory}\n\n{}\n\nLa confirmación corresponde a la producción actual y caduca en dos minutos.",
            summary["pack_version"],
            summary["scenes"],
            summary["sources"],
            summary["layers"],
            summary["steps"],
            summary["limitations"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|v| v.as_str())
                .collect::<Vec<_>>()
                .join("\n")
        );
        let review = Rc::new(RefCell::new(Some(review)));
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx,move|dialog,_,_| {
            let review=review.clone();let weak=weak.clone();
            dialog.title(Text::new("matchday-review-title".into(), "Revisar instalación de MATCHDAY".into()))
                .child(col().id("matchday-review-scroll").max_h(px(300.)).overflow_y_scroll().child(Text::new("matchday-review-body".into(), description.clone().into())))
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b|b.label("Cancelar")))
                    .child(DialogAction::new().child(control("install-matchday-local","Instalar MATCHDAY"))))
                .button_props(DialogButtonProps::default().ok_text("Instalar MATCHDAY").cancel_text("Cancelar").show_cancel(true)
                    .on_ok(move|_,_,cx| {
                        let Some(review)=review.borrow_mut().take() else {return true;};
                        let _=weak.update(cx,|view,cx| {
                            view.message=match view.production.install_matchday_local(review) {
                                Ok(report) if report["phase"]=="completed" => "MATCHDAY instalado. Revisa escenas y Live Deck, y guarda proyecto y Show Control.".into(),
                                Ok(report) => format!("Instalación parcial · {}. Revisa los recursos conservados en Live Deck.",report["error"].as_str().unwrap_or("consulta el informe")),
                                Err(error)=>error.to_string(),
                            };
                            view.panel=Some(Panel::LiveDeck);
                            cx.notify();
                        });true
                    }))
        });
        cx.notify();
    }
}
