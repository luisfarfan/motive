//! Presentation of the shared output registry. No UI lifecycle or media clock.
use super::*;
use crate::core::output::OutputTarget;

fn duration(slot: &Value) -> String {
    let seconds = slot["active_duration_ms"].as_u64().unwrap_or(0) / 1000;
    format!(
        "{:02}:{:02}:{:02}",
        seconds / 3600,
        seconds / 60 % 60,
        seconds % 60
    )
}

fn caption(slot: &Value) -> &'static str {
    if slot["cancel_deferred"] == true {
        return "Cancelación pendiente de conexión";
    }
    if slot["cancel_requested"] == true && slot["native_busy"] == true {
        return "Finalizando";
    }
    match slot["phase"].as_str() {
        Some("idle") => "Detenida",
        Some("starting") => "Iniciando",
        Some("connecting") => "Conectando",
        Some("active") => "Activa",
        Some("stopping") => "Finalizando",
        Some("error") => "Requiere recuperación",
        _ => "Estado no disponible",
    }
}

impl Studio {
    pub(super) fn output_details_action(&self, cx: &mut Context<Self>) -> Button {
        quiet("show-output-details", "Ver salidas").on_click(cx.listener(|v, _, w, cx| {
            v.panel = Some(Panel::Output);
            v.picker = None;
            v.prepare_forms(w, cx);
            cx.notify();
        }))
    }

    pub(super) fn output_encoder_summary(&self, status: &Value) -> String {
        let entries: Vec<_> = OutputTarget::ALL
            .into_iter()
            .filter_map(|target| {
                let slot = &status["outputs"][target.name()];
                if slot["native_busy"] != true {
                    return None;
                }
                let name = if target == OutputTarget::Recording {
                    "REC"
                } else if slot["kind"] == "local_stream" {
                    "UDP"
                } else {
                    "RTMP"
                };
                let encoder = slot["encoding"]["selected_id"]
                    .as_str()
                    .unwrap_or("pendiente");
                let encoder = if encoder.contains("videotoolbox") {
                    "VideoToolbox"
                } else if encoder.contains("x264") {
                    "x264"
                } else {
                    encoder
                };
                Some(format!("{name}: {encoder}"))
            })
            .collect();
        if entries.is_empty() {
            "Salidas detenidas".into()
        } else {
            entries.join(" · ")
        }
    }

    pub(super) fn output_control(
        &self,
        status: &Value,
        target: OutputTarget,
        compact: bool,
        cx: &mut Context<Self>,
    ) -> Button {
        let slot = &status["outputs"][target.name()];
        let recording = target == OutputTarget::Recording;
        let short = if recording {
            "REC"
        } else if slot["kind"] == "local_stream" && slot["native_busy"] == true {
            "UDP"
        } else {
            "RTMP"
        };
        let phase = slot["phase"].as_str().unwrap_or("unknown");
        let busy = slot["native_busy"] == true;
        let failed = slot["recovery_required"] == true;
        let cancelling = busy && slot["cancel_requested"] == true;
        let (text, icon, command, tooltip) = if cancelling || phase == "stopping" {
            (
                format!("{short} · Finalizando"),
                IconName::Square,
                Command::CancelOutputTarget { target },
                "Esperando la finalización del destino",
            )
        } else if busy && matches!(phase, "connecting" | "starting") {
            (
                if compact {
                    format!(
                        "{short} · {}",
                        if phase == "starting" {
                            "Iniciando"
                        } else {
                            "Conectando"
                        }
                    )
                } else {
                    "Cancelar inicio".into()
                },
                IconName::X,
                Command::CancelOutputTarget { target },
                "Solicitar cancelación; la conexión puede tardar en finalizar",
            )
        } else if busy {
            (
                if compact {
                    format!("{short} {}", duration(slot))
                } else {
                    "Detener".into()
                },
                IconName::Square,
                Command::StopOutputTarget { target },
                if recording {
                    "Detener solo la grabación"
                } else {
                    "Detener solo la transmisión"
                },
            )
        } else if failed {
            (
                if compact {
                    format!("Recuperar {short}")
                } else {
                    "Recuperar".into()
                },
                IconName::TriangleAlert,
                Command::RecoverOutputTarget { target },
                "Restablecer este destino; no inicia una nueva salida",
            )
        } else {
            (
                if recording {
                    "Grabar".into()
                } else {
                    "Transmitir".into()
                },
                if recording {
                    IconName::Circle
                } else {
                    IconName::Radio
                },
                Command::StartOutput { target },
                if recording {
                    "Iniciar grabación MKV"
                } else {
                    "Iniciar transmisión al receptor local configurado"
                },
            )
        };
        control(
            SharedString::from(format!(
                "output-{}-{}",
                target.name(),
                if compact { "header" } else { "panel" }
            )),
            text,
        )
        .icon(icon)
        .tooltip(tooltip)
        .disabled(
            cancelling
                || phase == "stopping"
                || phase == "unknown"
                || status["output_lifecycle"]["shutdown_pending"] == true,
        )
        .on_click(cx.listener(move |v, _, w, cx| {
            if matches!(
                command,
                Command::StopOutputTarget { .. } | Command::CancelOutputTarget { .. }
            ) || matches!(command, Command::StartOutput { target } if !v.production.output_warnings(target).is_empty()) {
                v.confirm_command(command.clone(), w, cx);
            } else {
                v.command(command.clone(), "UI", cx);
            }
        }))
    }

    pub(super) fn output_summary(&self, status: &Value) -> (String, Hsla) {
        let p = Palette::new(self.dark);
        let slots = OutputTarget::ALL.map(|target| &status["outputs"][target.name()]);
        let active = slots
            .iter()
            .filter(|slot| slot["phase"] == "active")
            .count();
        let failed = slots
            .iter()
            .filter(|slot| slot["recovery_required"] == true)
            .count();
        let pending = slots
            .iter()
            .any(|slot| slot["native_busy"] == true && slot["phase"] != "active");
        if status["output_lifecycle"]["shutdown_pending"] == true {
            ("Cerrando salidas".into(), p.warn)
        } else if failed > 0 {
            (
                if failed == 1 {
                    "Una salida con error"
                } else {
                    "Dos salidas con error"
                }
                .into(),
                p.warn,
            )
        } else if pending {
            ("Salidas en proceso".into(), p.warn)
        } else if active == 2 {
            ("Grabando + RTMP".into(), p.live)
        } else if active == 1 {
            (
                if slots[0]["phase"] == "active" {
                    "Grabando"
                } else {
                    "Transmitiendo"
                }
                .into(),
                p.live,
            )
        } else if status["recovery_required"] == true {
            ("Requiere recuperación".into(), p.warn)
        } else if status["issues"]
            .as_array()
            .is_some_and(|issues| !issues.is_empty())
        {
            ("Fuente no preparada".into(), p.warn)
        } else {
            ("Listo".into(), p.ready)
        }
    }

    fn output_card(&self, status: &Value, target: OutputTarget, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let slot = &status["outputs"][target.name()];
        let busy = slot["native_busy"] == true;
        let failed = slot["recovery_required"] == true;
        let color = if failed || (busy && slot["phase"] != "active") {
            p.warn
        } else if busy {
            p.live
        } else {
            p.muted
        };
        let selected_key = format!("{}_profile", target.name());
        let selected = status["output_configuration"][&selected_key]
            .as_str()
            .unwrap_or("—");
        let mut card = col()
            .gap(px(8.))
            .p(px(12.))
            .rounded(px(8.))
            .bg(p.sunken)
            .child(
                row().child(dot(color)).child(
                    label(
                        if target == OutputTarget::Recording {
                            "Grabación MKV"
                        } else if slot["kind"] == "local_stream" {
                            "Transmisión UDP heredada"
                        } else {
                            "Transmisión RTMP local"
                        },
                        p.ink,
                    )
                    .font_weight(FontWeight::SEMIBOLD),
                ),
            )
            .child(label(caption(slot), color))
            .child(
                row()
                    .child(self.output_control(status, target, false, cx))
                    .child(
                        self.action(
                            SharedString::from(format!("preflight-{}", target.name())),
                            "Comprobar",
                            Command::PreflightOutput { target },
                            cx,
                        )
                        .disabled(
                            busy || failed
                                || status["output_lifecycle"]["shutdown_pending"] == true,
                        ),
                    ),
            )
            .child(label(
                format!("Perfil seleccionado: {selected}"),
                p.secondary,
            ));
        for warning in self.production.output_warnings(target) {
            card = card.child(label(
                format!("{} {}", warning.message, warning.recommendation),
                p.warn,
            ));
        }
        if slot["attempt_id"].is_number() {
            let profile = slot["profile"]["id"].as_str().unwrap_or("—");
            let encoder = slot["encoding"]["selected_id"]
                .as_str()
                .unwrap_or("Sin encoder seleccionado");
            card = card
                .child(label(
                    format!(
                        "Intento {} · tiempo activo {}",
                        slot["attempt_id"],
                        duration(slot)
                    ),
                    p.secondary,
                ))
                .child(label(
                    format!(
                        "Perfil del intento: {profile} · {} kb/s",
                        slot["profile"]["bitrate_kbps"].as_u64().unwrap_or(0)
                    ),
                    p.secondary,
                ))
                .child(label(encoder.to_owned(), p.muted))
                .child(label(
                    format!(
                        "Video del intento: {} × {} · {} FPS",
                        slot["video"]["width"], slot["video"]["height"], slot["video"]["fps"]
                    ),
                    p.muted,
                ))
                .child(label(
                    format!(
                        "{} frames · {} perdidos · {:.2} MiB",
                        slot["stats"]["output_frames"].as_u64().unwrap_or(0),
                        slot["stats"]["output_dropped_frames"].as_i64().unwrap_or(0),
                        slot["stats"]["output_bytes"].as_u64().unwrap_or(0) as f64 / 1_048_576.
                    ),
                    p.muted,
                ));
            if let Some(reason) = slot["encoding"]["fallback_reason"].as_str() {
                card = card.child(label(format!("Fallback: {reason}"), p.warn));
            }
            if let Some(path) = slot["path"].as_str() {
                let filename = std::path::Path::new(path)
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or(path);
                card = card
                    .child(label(format!("Destino del intento: {filename}"), p.muted).truncate());
            }
        }
        if let Some(code) = slot["failure"]["code"].as_str() {
            let native = slot["failure"]["native_code"]
                .as_i64()
                .map(|code| format!(" · libobs {code}"))
                .unwrap_or_default();
            card = card.child(label(format!("{code}{native}"), p.warn));
        }
        if failed {
            card = card.child(label(if busy {
                "El fallo está registrado. Esperando la finalización antes de permitir recuperación."
            } else {
                "Revisa el destino y recupera esta salida. Después podrás iniciarla de nuevo."
            }, p.warn));
        } else if slot["cancel_deferred"] == true {
            card = card.child(label("Cancelación solicitada. La conexión aún tiene trabajo pendiente; este destino continúa ocupado.", p.warn));
        }
        card
    }

    pub(super) fn output_dashboard(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let status = self.production.status();
        col()
            .gap(px(10.))
            .child(control("stop-all-outputs", "Detener todas las salidas")
                .icon(IconName::Square)
                .disabled(status["output_lifecycle"]["native_busy"] != true || status["output_lifecycle"]["shutdown_pending"] == true)
                .on_click(cx.listener(|v, _, w, cx| v.confirm_command(Command::CancelAllOutputs, w, cx))))
            .children(OutputTarget::ALL.map(|target| self.output_card(&status, target, cx)))
            .child(label("Comprobar valida la configuración sin abrir la conexión. Cada salida se detiene y recupera por separado.", p.muted))
            .child(self.output_settings(cx))
    }
}
