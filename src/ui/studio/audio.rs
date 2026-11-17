//! Shared mixer presentation: ID joins, real meters and explicit target discovery.
use super::*;
use crate::core::audio::{
    AudioInput, AudioIssueCode, AudioSource, MAX_INPUTS, SystemAudioPermission, SystemAudioSources,
};
use gpui_kit::component::slider::{Slider, SliderEvent, SliderState};
use std::collections::BTreeMap;
#[derive(Default)]
pub(super) struct MixerUi {
    controls: BTreeMap<String, GainControl>,
    // Read-only inventory snapshot. Only an explicit button updates it; render
    // and the 33 ms studio loop must never enumerate ScreenCaptureKit targets.
    system_sources: Option<SystemAudioSources>,
    system_error: Option<String>,
}
struct GainControl {
    slider: Entity<SliderState>,
    revision: u64,
    pending: bool,
    pointer_focus: FocusHandle,
}
fn db(value: &Value) -> String {
    value
        .as_f64()
        .map(|n| format!("{n:.1}"))
        .unwrap_or("−∞".into())
}
fn input_name(name: &str, fallback: &str) -> String {
    let clean: String = name.chars().filter(|c| !c.is_control()).take(80).collect();
    if clean.trim().is_empty() {
        fallback.into()
    } else {
        clean
    }
}
fn source_caption(source: &AudioSource) -> String {
    match source {
        AudioSource::Tone => "Tono de prueba · 440 Hz".into(),
        AudioSource::Microphone { .. } => "Micrófono".into(),
        AudioSource::SystemApplication { bundle_id } => format!("Aplicación · {bundle_id}"),
        AudioSource::SystemDesktop { display_uuid } => format!("Escritorio · {display_uuid}"),
    }
}
fn phase_caption(phase: &str) -> &'static str {
    match phase {
        "ready" => "Recibiendo audio",
        "warming" => "Iniciando captura",
        "awaiting_audio" => "Esperando audio · sin muestras recientes",
        "disconnected" => "Desconectada",
        "failed" => "Captura no disponible",
        _ => "Estado no disponible",
    }
}
fn issue_caption(issue: AudioIssueCode) -> &'static str {
    match issue {
        AudioIssueCode::DeviceUnavailable => {
            "El dispositivo no está disponible. Comprueba su conexión y pulsa Reconectar."
        }
        AudioIssueCode::MicrophonePermissionDenied => {
            "macOS no ha autorizado el micrófono. Revisa el permiso y reconecta la entrada."
        }
        AudioIssueCode::AudioNotReady => "La captura está iniciando; espera las primeras muestras.",
        AudioIssueCode::AudioCreateFailed => {
            "No se pudo iniciar esta captura. Revisa el destino y pulsa Reconectar."
        }
        AudioIssueCode::AudioDisconnected => {
            "Entrada desconectada. Reconectar vuelve a abrir el mismo destino."
        }
        AudioIssueCode::AudioStalled => {
            "Dejaron de llegar muestras. Revisa el dispositivo y pulsa Reconectar."
        }
        AudioIssueCode::AudioStateUnavailable => "No se pudo consultar el estado de audio.",
        AudioIssueCode::AudioInputClipping => {
            "La señal de entrada ha saturado. Reduce el nivel en el dispositivo o aplicación de origen."
        }
        AudioIssueCode::AudioMixClipping => {
            "La mezcla ha saturado. Reduce la ganancia de sus entradas."
        }
        AudioIssueCode::AudioHeadroomLow => {
            "La mezcla está cerca de saturar. Reduce la ganancia para dejar margen."
        }
        AudioIssueCode::ScreenPermissionDenied => {
            "macOS no ha autorizado la captura. Revisa el permiso de pantalla y audio del sistema."
        }
        AudioIssueCode::SystemAudioUnavailable => {
            "La captura de audio del sistema no está disponible en este motor."
        }
        AudioIssueCode::SystemAudioEnumerationFailed => {
            "No se pudo consultar el audio del sistema. Vuelve a actualizar la lista."
        }
        AudioIssueCode::ApplicationUnavailable => {
            "La aplicación seleccionada se cerró o cambió de proceso. Ábrela y pulsa Reconectar."
        }
        AudioIssueCode::ApplicationAmbiguous => {
            "Hay varias instancias con la misma identidad. Deja una abierta y vuelve a consultar."
        }
        AudioIssueCode::DisplayUnavailable => {
            "La pantalla elegida ya no es la principal o no está disponible. No se seleccionó otra automáticamente."
        }
        AudioIssueCode::SystemAudioSelfCapture => {
            "Motive no puede seleccionarse como destino de audio del sistema."
        }
        AudioIssueCode::SystemAudioStreamStopped => {
            "macOS detuvo esta captura. Revisa el destino y pulsa Reconectar."
        }
        AudioIssueCode::SystemAudioNoSamples => {
            "La captura está abierta, pero no están llegando muestras. No equivale a silencio medido ni detiene las otras entradas."
        }
    }
}
fn levels(levels: &Value, p: Palette) -> Div {
    col()
        .gap(px(2.))
        .children((0..2).map(|channel| {
            let peak = levels["peak_dbfs"][channel].as_f64();
            row()
                .h(px(8.))
                .child(
                    label(if channel == 0 { "L" } else { "R" }, p.muted)
                        .text_size(px(9.))
                        .line_height(px(8.)),
                )
                .child(audio_meter(peak.map(|v| 10_f64.powf(v / 20.)).unwrap_or(0.), p).flex_1())
        }))
        .child(
            label(
                format!(
                    "P {} / {} · R {} / {}",
                    db(&levels["peak_dbfs"][0]),
                    db(&levels["peak_dbfs"][1]),
                    db(&levels["rms_dbfs"][0]),
                    db(&levels["rms_dbfs"][1])
                ),
                p.secondary,
            )
            .text_size(px(11.))
            .line_height(px(14.))
            .whitespace_nowrap(),
        )
        .when(levels["stale"] == true, |d| {
            d.child(label("Sin muestras recientes", p.warn))
        })
}
impl Studio {
    fn refresh_system_audio(&mut self, cx: &mut Context<Self>) {
        match self.production.engine.system_audio_sources() {
            Ok(sources) => {
                self.mixer_ui.system_sources = Some(sources);
                self.mixer_ui.system_error = None;
            }
            Err(error) => {
                self.mixer_ui.system_sources = None;
                self.mixer_ui.system_error = Some(error.to_string());
            }
        }
        cx.notify();
    }
    pub(super) fn sync_mixer_controls(
        &mut self,
        status: &Value,
        w: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let inputs: Vec<AudioInput> =
            serde_json::from_value(status["audio_mixer"]["store"]["inputs"].clone())
                .unwrap_or_default();
        self.mixer_ui
            .controls
            .retain(|id, _| inputs.iter().any(|i| &i.id == id));
        for input in inputs {
            if !self.mixer_ui.controls.contains_key(&input.id) {
                let slider = cx.new(|_| {
                    SliderState::new()
                        .min(-60.)
                        .max(24.)
                        .step(1.)
                        .default_value(input.gain_db)
                });
                let id = input.id.clone();
                cx.subscribe_in(&slider, w, move |v, _, event, _, cx| {
                    let Some(control) = v.mixer_ui.controls.get_mut(&id) else {
                        return;
                    };
                    match event {
                        SliderEvent::Change(_) => control.pending = true,
                        SliderEvent::Release(value) => {
                            let revision = control.revision;
                            control.pending = false;
                            if revision != v.production.revision {
                                v.message =
                                    "El mixer cambió durante el gesto; ganancia descartada.".into();
                                cx.notify();
                                return;
                            }
                            v.command(
                                Command::SetAudioGain {
                                    input_id: id.clone(),
                                    gain_db: value.start(),
                                },
                                "UI",
                                cx,
                            );
                        }
                    }
                })
                .detach();
                self.mixer_ui.controls.insert(
                    input.id.clone(),
                    GainControl {
                        slider,
                        revision: self.production.revision,
                        pending: false,
                        pointer_focus: cx.focus_handle(),
                    },
                );
            }
            let control = self.mixer_ui.controls.get_mut(&input.id).unwrap();
            if !control.pending {
                control.revision = self.production.revision;
                if control.slider.read(cx).value().start() != input.gain_db {
                    control
                        .slider
                        .update(cx, |s, cx| s.set_value(input.gain_db, w, cx));
                }
            }
        }
    }
    pub(super) fn audio(&self, status: &Value, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let mixer = &status["audio_mixer"];
        let inputs: Vec<AudioInput> =
            serde_json::from_value(mixer["store"]["inputs"].clone()).unwrap_or_default();
        let runtime = mixer["runtime"]["inputs"].as_array();
        col()
            .flex_none()
            .max_h(px(400.))
            .border_t_1()
            .border_color(p.line)
            .py(px(8.))
            .gap(px(8.))
            .child(
                row()
                    .child(
                        div()
                            .flex_1()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child("Audio"),
                    )
                    .child(self.panel_button(Panel::Audio, "", IconName::SlidersHorizontal, cx)),
            )
            .child(
                col()
                    .id("mixer-channels")
                    .overflow_y_scroll()
                    .min_h_0()
                    .gap(px(10.))
                    .when(inputs.is_empty(), |d| {
                        d.child(label(
                            "Añade un micrófono, una aplicación o un tono de prueba.",
                            p.muted,
                        ))
                    })
                    .children(inputs.iter().map(|input| {
                        let native = runtime.and_then(|a| a.iter().find(|r| r["id"] == input.id));
                        let id = input.id.clone();
                        col()
                            .gap(px(4.))
                            .line_height(px(16.))
                            .child(
                                row()
                                    .child(label(input.name.clone(), p.ink).flex_1().truncate())
                                    .child(label(format!("{:.1} dB", input.gain_db), p.secondary)),
                            )
                            .child(
                                label(source_caption(&input.source), p.muted)
                                    .text_size(px(10.))
                                    .truncate(),
                            )
                            .when_some(native, |d, r| {
                                d.child(levels(&r["levels"], p)).when(
                                    r["phase"] != "ready" || input.muted,
                                    |d| {
                                        d.child(label(
                                            format!(
                                                "{}{}",
                                                phase_caption(
                                                    r["phase"].as_str().unwrap_or("unavailable")
                                                ),
                                                if input.muted { " · Silenciado" } else { "" }
                                            ),
                                            if matches!(
                                                r["phase"].as_str(),
                                                Some("ready" | "awaiting_audio" | "disconnected")
                                            ) {
                                                p.secondary
                                            } else {
                                                p.warn
                                            },
                                        ))
                                    },
                                )
                            })
                            .when_some(self.mixer_ui.controls.get(&input.id), |d, control| {
                                // Kit 0.10 supports Tab focus but does not focus its thumb
                                // on pointer-down. Keep arrows inside the fader after a click.
                                let focus = control.pointer_focus.clone();
                                let slider = control.slider.clone();
                                d.child(
                                    div()
                                        .id(SharedString::from(format!("gain-focus-{id}")))
                                        .track_focus(&control.pointer_focus.clone().tab_stop(false))
                                        .focus_visible(|s| s.border_1().border_color(rgb(0x0a7aff)))
                                        .capture_any_mouse_down(move |_, w, cx| focus.focus(w, cx))
                                        .on_key_down(move |event, w, cx| {
                                            let delta = match event.keystroke.key.as_str() {
                                                "left" | "down" => -1.,
                                                "right" | "up" => 1.,
                                                _ => return,
                                            };
                                            slider.update(cx, |s, cx| {
                                                s.step_thumb(false, delta, w, cx)
                                            });
                                            cx.stop_propagation();
                                        })
                                        .child(
                                            Slider::new(&control.slider)
                                                .accessibility_label(format!(
                                                    "Ganancia {}",
                                                    input.name
                                                ))
                                                .tab_stop(true)
                                                .w_full(),
                                        ),
                                )
                            })
                            .child(
                                row()
                                    .child(self.action(
                                        SharedString::from(format!("mute-{id}")),
                                        if input.muted { "Activar" } else { "Silenciar" },
                                        Command::SetAudioMute {
                                            input_id: id.clone(),
                                            muted: !input.muted,
                                        },
                                        cx,
                                    ))
                                    .child(self.action(
                                        SharedString::from(format!("zero-{id}")),
                                        "0 dB",
                                        Command::SetAudioGain {
                                            input_id: id.clone(),
                                            gain_db: 0.,
                                        },
                                        cx,
                                    )),
                            )
                    })),
            )
            .child(label("Master · post-mute · dBFS", p.secondary))
            .child(levels(&mixer["runtime"]["mix"], p))
            .when(
                mixer["issues"]
                    .as_array()
                    .is_some_and(|a| a.iter().any(|issue| issue["severity"] != "info")),
                |d| d.child(label("Mixer requiere atención · abre Audio", p.warn)),
            )
    }
    pub(super) fn mixer_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let m = self.production.audio_mixer_status();
        let inputs: Vec<AudioInput> =
            serde_json::from_value(m["store"]["inputs"].clone()).unwrap_or_default();
        let busy = self.production.engine.output_state() != 0;
        let full = inputs.len() >= MAX_INPUTS;
        let has_desktop = inputs
            .iter()
            .any(|i| matches!(i.source, AudioSource::SystemDesktop { .. }));
        let has_application = inputs
            .iter()
            .any(|i| matches!(i.source, AudioSource::SystemApplication { .. }));
        let mut content = col().gap(px(10.))
            .child(label("Entradas globales · P: peak / R: RMS · dBFS · post-fader / pre-mute", p.secondary))
            .child(label("El audio continúa al cambiar de escena. Monitoreo audible desactivado.", p.muted))
            .when(busy, |d| d.child(label("Detén las salidas para añadir, eliminar o restaurar entradas. Ganancia, mute y recuperación siguen disponibles.", p.secondary)))
            .child(quiet("microphone-permission", "Revisar permiso de micrófono").on_click(cx.listener(|v, _, _, cx| {
                v.production.engine.request_permission(1);
                v.devices = v.production.engine.devices();
                cx.notify();
            })))
            .child(self.action("add-tone", "Añadir tono de prueba", Command::AddAudioInput { name: "Tono de prueba".into(), source: AudioSource::Tone }, cx)
                .disabled(busy || full && !inputs.iter().any(|i| i.source == AudioSource::Tone)))
            .children(self.devices["audio"].as_array().into_iter().flatten().enumerate().filter_map(|(i, device)| {
                let name = device["name"].as_str()?;
                let source = AudioSource::Microphone { device_id: device["id"].as_str()?.into() };
                let existing = inputs.iter().any(|input| input.source == source);
                Some(self.action(("mixer-device", i), format!("Añadir {name}"), Command::AddAudioInput {
                    name: input_name(name, "Micrófono"), source,
                }, cx).disabled(busy || full && !existing))
            }))
            .child(property_group("Audio de aplicaciones y escritorio", p)
                .child(label("Elige un destino explícito. La lista se mantiene fija hasta que pulses Actualizar.", p.secondary))
                .child(quiet("system-audio-refresh", if self.mixer_ui.system_sources.is_some() { "Actualizar aplicaciones y pantallas" } else { "Consultar aplicaciones y pantallas" })
                    .on_click(cx.listener(|v, _, _, cx| v.refresh_system_audio(cx))))
                .child(quiet("system-audio-permission", "Revisar permiso de pantalla y audio").on_click(cx.listener(|v, _, _, cx| {
                    v.production.engine.request_permission(0);
                    v.refresh_system_audio(cx);
                }))))
            .when_some(self.mixer_ui.system_error.as_ref(), |d, error| {
                d.child(label(format!("No se pudo actualizar la lista · {error}"), p.warn))
            });
        if let Some(sources) = &self.mixer_ui.system_sources {
            let authorized = sources.permission == SystemAudioPermission::Authorized;
            let selectable = sources.available && authorized && sources.issue.is_none();
            if let Some(issue) = sources.issue {
                content = content.child(label(issue_caption(issue), p.warn));
            }
            if !authorized {
                content = content.child(label(
                    "Después de autorizar en macOS, pulsa Actualizar.",
                    p.secondary,
                ));
            }
            if has_desktop {
                content = content.child(label("El escritorio ya cubre audio de aplicaciones. Elimina esa entrada antes de añadir una aplicación; silenciarla o desconectarla conserva su selección.", p.secondary));
            }
            content = content
                .child(label("Aplicaciones", p.ink))
                .when(sources.applications.is_empty() && selectable, |d| d.child(label("No hay aplicaciones seleccionables. Abre la aplicación que quieras capturar y actualiza la lista.", p.muted)))
                .children(sources.applications.iter().enumerate().map(|(i, app)| {
                    let source = AudioSource::SystemApplication { bundle_id: app.bundle_id.clone() };
                    let existing = inputs.iter().any(|input| input.source == source);
                    col().gap(px(2.))
                        .child(self.action(("system-audio-application", i), if existing { format!("{} · ya en el mixer", app.name) } else { format!("Añadir {}", app.name) }, Command::AddAudioInput {
                            name: input_name(&app.name, "Aplicación"), source,
                        }, cx).disabled(busy || full || !selectable || !app.selectable || has_desktop || existing))
                        .child(label(app.bundle_id.clone(), p.muted).text_size(px(10.)).truncate())
                        .when(!app.selectable, |d| d.child(label(
                            if app.running_instances > 1 { "Hay varias instancias. Deja una abierta y actualiza la lista." } else { "Este destino no está disponible para selección." }, p.secondary)))
                }))
                .child(label("Escritorio · captura amplia de audio", p.ink))
                .child(label("Puede incluir sonido de varias aplicaciones. Se admite únicamente la pantalla principal y no puede combinarse con una entrada de aplicación.", p.secondary))
                .when(has_application, |d| d.child(label("Elimina las entradas de aplicación antes de añadir el escritorio. Silenciar no evita el solapamiento.", p.secondary)))
                .children(sources.displays.iter().enumerate().map(|(i, display)| {
                    let source = AudioSource::SystemDesktop { display_uuid: display.display_uuid.clone() };
                    let existing = inputs.iter().any(|input| input.source == source);
                    col().gap(px(2.))
                        .child(self.action(("system-audio-desktop", i),
                            if existing { format!("{} · ya en el mixer", display.name) } else if display.is_main { format!("Añadir escritorio · {}", display.name) } else { format!("{} · no es la principal", display.name) },
                            Command::AddAudioInput { name: "Audio del escritorio".into(), source }, cx)
                            .disabled(busy || full || !selectable || !display.selectable || has_application || has_desktop))
                        .child(label(display.display_uuid.clone(), p.muted).text_size(px(10.)).truncate())
                }));
        }
        content
            .when(full, |d| d.child(label("El mixer tiene sus ocho entradas. Elimina una para añadir otro destino.", p.secondary)))
            .children(inputs.iter().enumerate().map(|(i, input)| {
                let runtime = m["runtime"]["inputs"].as_array().and_then(|all| all.iter().find(|r| r["id"] == input.id));
                property_group(input.name.clone(), p)
                    .child(label(source_caption(&input.source), p.secondary).truncate())
                    .when_some(runtime, |d, runtime| d.child(label(phase_caption(runtime["phase"].as_str().unwrap_or("unavailable")), p.secondary)))
                    .child(row().flex_wrap()
                        .child(self.action(("disconnect-audio", i), "Desconectar…", Command::DisconnectAudioInput { input_id: input.id.clone() }, cx))
                        .child(self.action(("reconnect-audio", i), "Reconectar", Command::ReconnectAudioInput { input_id: input.id.clone() }, cx))
                        .child(self.action(("remove-audio", i), "Eliminar…", Command::RemoveAudioInput { input_id: input.id.clone() }, cx).disabled(busy)))
            }))
            .children(m["issues"].as_array().into_iter().flatten().map(|issue| {
                let input_id = issue["input_id"].as_str();
                let name = inputs.iter().find(|input| Some(input.id.as_str()) == input_id).map(|i| i.name.as_str()).unwrap_or("Master");
                let detail = serde_json::from_value::<AudioIssueCode>(issue["code"].clone()).map(issue_caption).unwrap_or("Revisa el estado de esta entrada.");
                col().gap(px(2.))
                    .child(label(format!("{name} · {detail}"), if issue["severity"] == "info" { p.secondary } else { p.warn }))
                    .child(label(issue["code"].as_str().unwrap_or("").to_owned(), p.muted).text_size(px(10.)))
            }))
            .child(row()
                .child(self.action("save-mixer", "Guardar mixer", Command::SaveAudioMixer, cx))
                .child(self.action("load-mixer", "Restaurar mixer…", Command::LoadAudioMixer, cx).disabled(busy)))
            .child(label("Fader: aplica al soltar; flechas ajustan 1 dB. Silenciar conserva el medidor de entrada. Si la mezcla satura, baja la ganancia.", p.muted))
    }
}
