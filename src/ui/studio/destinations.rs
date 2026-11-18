//! Local destination approval and start authority never travel through Command.
//! GPUI fields contain metadata only; AppKit owns secure credential entry.
use super::*;
use crate::core::destinations::{
    DestinationProtocol, DestinationSpec, LocalDestinationReview, LocalStartRequest,
};
use gpui_kit::component::{
    WindowExt,
    dialog::{DialogAction, DialogButtonProps, DialogClose, DialogFooter},
    input::InputState,
};
use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use std::{cell::RefCell, rc::Rc};

pub(super) struct DestinationsUi {
    id: Entity<InputState>,
    name: Entity<InputState>,
    host: Entity<InputState>,
    port: Entity<InputState>,
    application: Entity<InputState>,
    editing: Option<DestinationSpec>,
    revision: u64,
}
impl DestinationsUi {
    pub(super) fn new(window: &mut Window, cx: &mut Context<Studio>) -> Self {
        let mut input = || cx.new(|cx| InputState::new(window, cx));
        Self {
            id: input(),
            name: input(),
            host: input(),
            port: input(),
            application: input(),
            editing: None,
            revision: 0,
        }
    }
    fn spec(&self, cx: &App) -> anyhow::Result<DestinationSpec> {
        let mut spec = DestinationSpec {
            id: self.id.read(cx).value().to_string(),
            name: self.name.read(cx).value().to_string(),
            protocol: DestinationProtocol::Rtmps,
            host: self.host.read(cx).value().to_string().try_into()?,
            port: u16::try_from(
                forms::integer(&self.port.read(cx).value())
                    .map_err(|_| anyhow::anyhow!("INVALID_DESTINATION_PORT"))?,
            )
            .map_err(|_| anyhow::anyhow!("INVALID_DESTINATION_PORT"))?,
            application: self.application.read(cx).value().to_string().try_into()?,
            credential_ref: None,
        };
        spec.validate()?;
        if let Some(old) = &self.editing
            && old.credential_binding()? == spec.credential_binding()?
        {
            spec.credential_ref = old.credential_ref.clone();
        }
        Ok(spec)
    }
}

fn describe(spec: &DestinationSpec) -> String {
    format!(
        "{}\nID: {}\nRTMPS · {}:{}\nAplicación: {}",
        spec.name,
        spec.id,
        spec.host.as_str(),
        spec.port,
        spec.application.as_str()
    )
}

fn validation_caption(value: &str) -> &'static str {
    match value {
        "configuration_ready" => "Configuración preparada; conexión sin probar",
        "credential_missing" => "Falta asociar una clave",
        "credential_access_denied" => "Acceso a Keychain denegado",
        "credential_binding_mismatch" => "La clave no corresponde a este destino",
        "keychain_unavailable" => "Keychain no disponible",
        _ => "Sin comprobar",
    }
}

impl Studio {
    fn destinations_disabled(&self) -> bool {
        let status = self.production.status();
        self.production.shutdown_requested
            || status["output_lifecycle"]["shutdown_pending"] == true
            || status["outputs"]["streaming"]["native_busy"] == true
            || self.production.destinations_status()["credential_busy"] == true
    }

    fn destination_result(
        &mut self,
        result: anyhow::Result<()>,
        success: &str,
        cx: &mut Context<Self>,
    ) {
        self.message = match result {
            Ok(()) => success.into(),
            Err(error) => {
                format!("{error} · Revisa el destino y el estado actual antes de reintentar.")
            }
        };
        cx.notify();
    }

    fn current_destination_spec(&self, id: &str) -> anyhow::Result<DestinationSpec> {
        let snapshot = self.production.destinations_status();
        let value = snapshot["destinations"]
            .as_array()
            .into_iter()
            .flatten()
            .find(|row| row["destination"]["id"] == id)
            .ok_or_else(|| anyhow::anyhow!("DESTINATION_UNAVAILABLE"))?;
        serde_json::from_value(value["destination"].clone())
            .map_err(|_| anyhow::anyhow!("INVALID_DESTINATION"))
    }

    pub(super) fn prepare_destination_draft(
        &mut self,
        spec: Option<DestinationSpec>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        for (input, value) in [
            (
                &self.destinations_ui.id,
                spec.as_ref().map_or(String::new(), |s| s.id.clone()),
            ),
            (
                &self.destinations_ui.name,
                spec.as_ref().map_or(String::new(), |s| s.name.clone()),
            ),
            (
                &self.destinations_ui.host,
                spec.as_ref()
                    .map_or(String::new(), |s| s.host.as_str().into()),
            ),
            (
                &self.destinations_ui.port,
                spec.as_ref().map_or("443".into(), |s| s.port.to_string()),
            ),
            (
                &self.destinations_ui.application,
                spec.as_ref()
                    .map_or("/live".into(), |s| s.application.as_str().into()),
            ),
        ] {
            input.update(cx, |state, cx| state.set_value(value, window, cx));
        }
        self.destinations_ui.editing = spec;
        self.destinations_ui.revision = self.production.revision;
        cx.notify();
    }

    pub(super) fn destinations_panel(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let snapshot = self.production.destinations_status();
        let disabled = self.destinations_disabled();
        let stale = self.destinations_ui.revision != self.production.revision;
        let mut body = col().gap(px(10.))
            .child(label("Destinos RTMPS aprobados", p.ink))
            .child(label("Guarda los datos del servidor, asocia la clave en el asistente seguro y revisa el destino. Cada emisión necesita confirmación local.", p.secondary))
            .child(quiet("destination-local-mode", "Usar receptor local de prueba")
                .disabled(disabled).on_click(cx.listener(|view, _, _, cx| {
                    let result = view.production.select_approved_destination(None);
                    view.destination_result(result, "Modo receptor local seleccionado. No se inició ninguna salida.", cx);
                })));
        if let Some(code) = snapshot["load_error"].as_str() {
            body = body.child(label(
                format!("{code} · No se pudo abrir el registro privado de destinos."),
                p.warn,
            ));
        }
        let enrollment = &snapshot["enrollment"];
        if let Some(error) = enrollment["persistence_error"].as_str() {
            let consequence = if enrollment["shutdown_blocked"] == true {
                "La referencia sigue en memoria y el cierre está pendiente. Revisa el espacio libre y los permisos de la carpeta privada de Motive; se reintentará cada segundo. Cancelar evita asociarla al destino, pero espera a que el recibo quede guardado."
            } else {
                "El recibo de Keychain quedó guardado, pero no se confirmó el cambio del destino. El registro está bloqueado en esta sesión; revisa el almacenamiento antes de reabrir Motive."
            };
            body = body.child(label(format!("{error} · {consequence}"), p.warn));
        }
        if let Some(phase) = enrollment["phase"].as_str() {
            let message = if enrollment["reconciliation_required"] == true {
                format!(
                    "Clave guardada sin vincular al destino actual. Revisión local pendiente. Referencia: {}. No se eliminó la entrada de Keychain.",
                    enrollment["credential_ref"]
                        .as_str()
                        .unwrap_or("no disponible")
                )
            } else if enrollment["attached"] == true {
                "Clave guardada y asociada. Revisa y aprueba de nuevo el destino antes de seleccionarlo.".into()
            } else {
                match phase {
                    "awaiting_user" => {
                        "Asistente seguro abierto; todavía no se ha guardado una clave.".into()
                    }
                    "writing" => "Guardando en Keychain; espera la confirmación.".into(),
                    "cancelled" => "Asociación de clave cancelada.".into(),
                    "failed" => format!(
                        "No se pudo guardar la clave (código {}).",
                        enrollment["code"]
                    ),
                    "stored" | "stored_after_cancel" =>
                        "La clave no quedó vinculada al destino. Revisa el resultado del asistente antes de reintentar.".into(),
                    _ => "El estado de la asociación de clave no está disponible.".into(),
                }
            };
            body = body.child(label(message, p.warn));
        }
        for receipt in snapshot["reconciliation_pending"]
            .as_array()
            .into_iter()
            .flatten()
        {
            let destination =
                serde_json::from_value::<DestinationSpec>(receipt["destination"].clone())
                    .map(|spec| describe(&spec))
                    .unwrap_or_else(|_| "Destino guardado no disponible".into());
            body = body.child(label(format!(
                "Recibo pendiente · {destination} · referencia {}. Conservado para revisión local; no se asociará ni eliminará automáticamente.",
                receipt["credential_ref"].as_str().unwrap_or("no disponible")
            ), p.warn));
        }
        if snapshot["credential_busy"] == true {
            body = body.child(quiet("cancel-destination-credential", "Cancelar asociación de clave")
                .on_click(cx.listener(|view, _, _, cx| {
                    view.production.cancel_destination_credential();
                    view.message = "Cancelación solicitada. Si Keychain ya comenzó a guardar, espera el resultado.".into();
                    cx.notify();
                })));
        }
        for (index, item) in snapshot["destinations"]
            .as_array()
            .into_iter()
            .flatten()
            .enumerate()
        {
            let Ok(spec) = serde_json::from_value::<DestinationSpec>(item["destination"].clone())
            else {
                continue;
            };
            let edit = spec.id.clone();
            let review = spec.id.clone();
            let credential = spec.id.clone();
            let select = spec.id.clone();
            let preflight = spec.id.clone();
            let remove = spec.id.clone();
            let approved = item["approval"] == "approved";
            body = body.child(col().gap(px(6.)).py(px(8.)).border_t_1().border_color(p.line)
                .child(label(describe(&spec), p.ink))
                .child(label(format!("{} · {}{}", if approved {"Aprobado"} else {"Borrador"},
                    validation_caption(item["validation"].as_str().unwrap_or("")),
                    if item["selected"] == true {" · Seleccionado"} else {""}), p.secondary))
                .child(row()
                    .child(quiet(("edit-destination", index), "Editar").disabled(disabled).accessibility_label(format!("Editar destino {}",spec.name))
                        .on_click(cx.listener(move |view, _, window, cx| {
                            match view.current_destination_spec(&edit) {
                                Ok(spec) => view.prepare_destination_draft(Some(spec), window, cx),
                                Err(error) => view.destination_result(Err(error), "", cx),
                            }
                        })))
                    .child(quiet(("review-destination", index), "Revisar y aprobar").disabled(disabled).accessibility_label(format!("Revisar destino {}",spec.name))
                        .on_click(cx.listener(move |view, _, window, cx| {
                            match view.production.review_destination_local(&review) {
                                Ok(review) => view.confirm_destination_review(review, window, cx),
                                Err(error) => view.destination_result(Err(error), "", cx),
                            }
                        })))
                    .child(quiet(("credential-destination", index), "Asociar clave…").disabled(disabled).accessibility_label(format!("Asociar clave segura a {}",spec.name))
                        .on_click(cx.listener(move |view, _, window, cx| view.enroll_destination_credential(&credential, window, cx)))))
                .child(row()
                    .child(quiet(("select-destination", index), if item["selected"] == true {"Seleccionado"} else {"Seleccionar"})
                        .disabled(disabled || !approved).accessibility_label(format!("Seleccionar destino {}", spec.name)).on_click(cx.listener(move |view, _, _, cx| {
                            let result = view.production.select_approved_destination(Some(&select));
                            view.destination_result(result, "Destino seleccionado. Todavía no se ha iniciado la transmisión.", cx);
                        })))
                    .child(quiet(("preflight-destination", index), "Comprobar").disabled(disabled || !approved).accessibility_label(format!("Comprobar destino {}", spec.name))
                        .on_click(cx.listener(move |view, _, _, cx| {
                            let result = view.production.preflight_destination(&preflight).map(|_| ());
                            view.destination_result(result, "Configuración y acceso a Keychain preparados. La conexión TLS y la entrega de medios no se han probado.", cx);
                        })))
                    .child(quiet(("remove-destination", index), "Eliminar…").disabled(disabled).accessibility_label(format!("Eliminar destino {}", spec.name))
                        .on_click(cx.listener(move |view, _, window, cx| {
                            match view.current_destination_spec(&remove) {
                                Ok(spec) => view.confirm_remove_destination(spec, window, cx),
                                Err(error) => view.destination_result(Err(error), "", cx),
                            }
                        })))));
        }
        body = body.child(quiet("new-destination", "Nuevo destino / descartar borrador").disabled(disabled)
            .on_click(cx.listener(|view, _, window, cx| view.prepare_destination_draft(None, window, cx))))
            .child(forms::field("ID estable (a-z, 0-9, -, _)", &self.destinations_ui.id, p))
            .child(forms::field("Nombre visible", &self.destinations_ui.name, p))
            .child(forms::field("Host (sin rtmps:// ni clave)", &self.destinations_ui.host, p))
            .child(forms::field("Puerto RTMPS (1–65535)", &self.destinations_ui.port, p))
            .child(forms::field("Aplicación (por ejemplo /live; sin clave)", &self.destinations_ui.application, p))
            .child(label("Cambiar ID, host, puerto o aplicación requiere asociar una clave nueva. Guardar modifica el registro y deja el destino en borrador.", p.muted));
        if stale {
            body = body.child(label("El estado cambió. Vuelve a Editar el destino o inicia un formulario nuevo antes de guardar.", p.warn));
        }
        body.child(
            quiet("save-destination", "Guardar y revisar destino")
                .disabled(disabled || stale)
                .on_click(cx.listener(|view, _, window, cx| {
                    let result = view.destinations_ui.spec(cx).and_then(|spec| {
                        view.production
                            .save_destination_local(spec, view.destinations_ui.revision)
                    });
                    match result {
                        Ok(review) => {
                            view.prepare_destination_draft(
                                Some(review.destination().clone()),
                                window,
                                cx,
                            );
                            view.confirm_destination_review(review, window, cx);
                        }
                        Err(error) => view.destination_result(Err(error), "", cx),
                    }
                })),
        )
    }

    fn confirm_destination_review(
        &mut self,
        review: LocalDestinationReview,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let description = format!(
            "{}\n\nAprobar autoriza seleccionar estos datos como destino. No inicia una transmisión ni prueba la conexión.",
            describe(review.destination())
        );
        let request = Rc::new(RefCell::new(Some(review)));
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx, move |dialog, _, _| {
            let request = request.clone();
            let weak = weak.clone();
            dialog.title(Text::new("destination-review-title".into(), "Revisar destino RTMPS".into()))
                .child(Text::new("destination-review-body".into(), description.clone().into()))
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b| b.label("Cancelar")))
                    .child(DialogAction::new().child(control("approve-destination", "Aprobar destino"))))
                .button_props(DialogButtonProps::default().ok_text("Aprobar destino").cancel_text("Cancelar").show_cancel(true)
                    .on_ok(move |_, _, cx| {
                        let Some(review) = request.borrow_mut().take() else { return true; };
                        let _ = weak.update(cx, |view, cx| {
                            let result = view.production.approve_destination_local(review);
                            view.destination_result(result, "Destino aprobado. Selección y emisión siguen siendo acciones separadas.", cx);
                        });
                        true
                    }))
        });
        cx.notify();
    }

    fn confirm_remove_destination(
        &mut self,
        spec: DestinationSpec,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let revision = self.production.revision;
        let request = Rc::new(RefCell::new(Some((spec.id.clone(), revision))));
        let description = format!(
            "Eliminar {} del registro de destinos. Esta acción no borra entradas de Keychain.",
            spec.name
        );
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx, move |dialog, _, _| {
            let request = request.clone();
            let weak = weak.clone();
            dialog.title(Text::new("destination-remove-title".into(), "Eliminar destino".into()))
                .child(Text::new("destination-remove-body".into(), description.clone().into()))
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b| b.label("Cancelar")))
                    .child(DialogAction::new().child(control("confirm-remove-destination", "Eliminar destino"))))
                .button_props(DialogButtonProps::default().ok_text("Eliminar destino").cancel_text("Cancelar").show_cancel(true)
                    .on_ok(move |_, _, cx| {
                        let Some((id, revision)) = request.borrow_mut().take() else { return true; };
                        let _ = weak.update(cx, |view, cx| {
                            let result = view.production.remove_destination_local(&id, revision);
                            view.destination_result(result, "Destino eliminado del registro; Keychain conserva sus entradas.", cx);
                        });
                        true
                    }))
        });
        cx.notify();
    }

    fn enroll_destination_credential(
        &mut self,
        id: &str,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let result = (|| -> anyhow::Result<()> {
            let handle = HasWindowHandle::window_handle(window)
                .map_err(|_| anyhow::anyhow!("NATIVE_WINDOW_UNAVAILABLE"))?;
            let RawWindowHandle::AppKit(handle) = handle.as_raw() else {
                anyhow::bail!("NATIVE_WINDOW_UNAVAILABLE");
            };
            // GPUI retains this NSView for the synchronous bridge invocation.
            // The native bridge verifies its exact owning NSWindow and tree.
            unsafe {
                self.production.begin_destination_credential_local(
                    handle.ns_view.as_ptr(),
                    id,
                    self.production.revision,
                )
            }
        })();
        self.destination_result(
            result,
            "Asistente seguro solicitado. Esta acción no inicia una transmisión.",
            cx,
        );
    }

    pub(super) fn request_destination_start(
        &mut self,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        match self.production.prepare_destination_start_local() {
            Ok(request) => self.confirm_destination_start(request, window, cx),
            Err(error) => self.destination_result(Err(error), "", cx),
        }
    }

    fn confirm_destination_start(
        &mut self,
        request: LocalStartRequest,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let profile = request.profile();
        let warning = profile
            .warnings()
            .iter()
            .map(|w| format!("{} {}", w.message, w.recommendation))
            .collect::<Vec<_>>()
            .join("\n");
        let description = format!(
            "{}\n\nPerfil: {} · {} kb/s · keyframes {} s\n{}\n\nConfirmar inicia una emisión hacia este destino. TLS verifica el certificado; la recepción de medios todavía debe comprobarse. La autorización caduca si el estado cambia o pasan 60 segundos.",
            describe(request.destination()),
            profile.id,
            profile.bitrate_kbps,
            profile.keyframe_seconds,
            warning
        );
        let request = Rc::new(RefCell::new(Some(request)));
        let weak = cx.entity().downgrade();
        self.panel = None;
        window.open_dialog(cx, move |dialog, _, _| {
            let request = request.clone();
            let weak = weak.clone();
            dialog.title(Text::new("destination-start-title".into(), "Confirmar transmisión RTMPS".into()))
                .child(Text::new("destination-start-body".into(), description.clone().into()))
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b| b.label("Cancelar")))
                    .child(DialogAction::new().child(control("start-approved-destination", "Iniciar transmisión"))))
                .button_props(DialogButtonProps::default().ok_text("Iniciar transmisión").cancel_text("Cancelar").show_cancel(true)
                    .on_ok(move |_, _, cx| {
                        let Some(request) = request.borrow_mut().take() else { return true; };
                        let _ = weak.update(cx, |view, cx| {
                            let result = view.production.start_destination_local(request);
                            view.destination_result(result, "Inicio de transmisión solicitado. Consulta la fase de la salida y verifica el receptor.", cx);
                        });
                        true
                    }))
        });
        cx.notify();
    }

    pub(super) fn destinations_action(&self, cx: &mut Context<Self>) -> Button {
        quiet("open-destinations", "Configurar destinos RTMPS").on_click(cx.listener(
            |view, _, window, cx| {
                view.prepare_destination_draft(None, window, cx);
                view.panel = Some(Panel::Destinations);
                view.picker = None;
                cx.notify();
            },
        ))
    }
}
