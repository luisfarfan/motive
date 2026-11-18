//! Recording discovery uses the shared core; Finder receives a validated local
//! capability. Neither rendering nor the UI owner scans or decodes a directory.
use super::*;
use crate::recordings::{RecordingState, ScanPhase};

#[derive(Default)]
pub(super) struct RecordingsUi {
    pub(super) revealing: bool,
}

fn size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{bytes} B")
    } else if bytes < 1024 * 1024 {
        format!("{:.1} KiB", bytes as f64 / 1024.)
    } else {
        format!("{:.1} MiB", bytes as f64 / 1_048_576.)
    }
}

impl Studio {
    pub(super) fn recordings_closing(&self) -> bool {
        self.production.shutdown_requested
            || self.production.status()["output_lifecycle"]["shutdown_pending"] == true
    }

    pub(super) fn refresh_recordings(&mut self, cx: &mut Context<Self>) {
        if self.recordings_closing() {
            return;
        }
        self.command(Command::RefreshRecordings, "UI", cx);
        cx.notify();
    }

    pub(super) fn recordings_panel(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let snapshot = self.production.recordings_snapshot();
        let closing = self.recordings_closing();
        let mut body = col().gap(px(10.))
            .child(label(snapshot.directory, p.secondary))
            .child(label("Carpeta local de grabaciones. El tamaño corresponde a la última actualización.", p.muted))
            .child(quiet("refresh-recordings", if snapshot.phase == ScanPhase::Scanning { "Actualizando…" } else { "Actualizar lista" })
                .disabled(snapshot.phase == ScanPhase::Scanning || closing)
                .on_click(cx.listener(|view, _, _, cx| view.refresh_recordings(cx))))
            .child(label("Por verificar: la biblioteca todavía no comprueba el contenido ni la integridad del video.", p.muted));
        if let Some(error) = snapshot.error {
            body = body.child(label(
                format!(
                    "{} · No se pudo consultar la carpeta. Revisa su acceso y vuelve a actualizar.",
                    error.code
                ),
                p.warn,
            ));
        }
        if snapshot.truncated {
            body = body.child(label(format!("Lista parcial: se consultaron hasta {} entradas y se muestran hasta {} archivos.", snapshot.scan_limit, snapshot.display_limit), p.warn));
        }
        if snapshot.items.is_empty() {
            body = body.child(label(
                match snapshot.phase {
                    ScanPhase::Idle => "Actualiza la lista para consultar las grabaciones.",
                    ScanPhase::Scanning => "Consultando la carpeta…",
                    ScanPhase::Ready => "No hay grabaciones de Motive en esta carpeta.",
                    ScanPhase::Error => "La lista no está disponible.",
                },
                p.secondary,
            ));
        }
        for (index, recording) in snapshot.items.into_iter().enumerate() {
            let (caption, color) = match recording.state {
                RecordingState::Writing => ("Grabando", p.live),
                RecordingState::Finalizing => ("Finalizando · espera la salida", p.warn),
                RecordingState::Error => ("Grabación con error · puede estar incompleta", p.warn),
                RecordingState::ClosedUnverified => ("Por verificar", p.secondary),
            };
            let id = recording.id.clone();
            body = body.child(
                col()
                    .gap(px(5.))
                    .py(px(8.))
                    .border_t_1()
                    .border_color(p.line)
                    .child(label(recording.id, p.ink))
                    .child(label(
                        format!("{caption} · {}", size(recording.bytes)),
                        color,
                    ))
                    .when_some(recording.failure_code, |row, code| {
                        row.child(label(code, p.warn))
                    })
                    .child(
                        quiet(("reveal-recording", index), "Mostrar en Finder")
                            .accessibility_label(format!("Mostrar {id} en Finder"))
                            .disabled(self.recordings.revealing || closing)
                            .on_click(cx.listener(move |view, _, _, cx| {
                                view.reveal_recording(id.clone(), cx)
                            })),
                    ),
            );
        }
        body
    }

    fn reveal_recording(&mut self, id: String, cx: &mut Context<Self>) {
        if self.recordings.revealing || self.recordings_closing() {
            return;
        }
        self.recordings.revealing = true;
        self.message = "Comprobando el archivo para mostrarlo en Finder…".into();
        cx.spawn(async move |this, cx| {
            let capability = cx
                .background_executor()
                .spawn(async move { crate::recordings::prepare_reveal(&id) })
                .await;
            let _ = this.update(cx, |view, cx| {
                view.recordings.revealing = false;
                if view.recordings_closing() {
                    cx.notify();
                    return;
                }
                match capability {
                    Ok(capability) => {
                        // GPUI's macOS implementation dispatches NSWorkspace's
                        // Finder selection. It never opens or plays this media.
                        cx.reveal_path(capability.path());
                        view.message = "Se solicitó mostrar la grabación en Finder.".into();
                    }
                    Err(error) => {
                        view.message = format!(
                            "{} · El archivo cambió o no está disponible. Actualiza la lista.",
                            error.code
                        );
                    }
                }
                cx.notify();
            });
        })
        .detach();
        cx.notify();
    }
}
