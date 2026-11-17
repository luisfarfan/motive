//! H10 presentation only: ID joins, real meters, and release-committed Kit faders.
use super::*;
use crate::core::audio::{AudioInput, AudioSource};
use gpui_kit::component::slider::{Slider, SliderEvent, SliderState};
use std::collections::BTreeMap;
#[derive(Default)]
pub(super) struct MixerUi {
    controls: BTreeMap<String, GainControl>,
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
                        d.child(label("Añade un micrófono o tono de prueba.", p.muted))
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
                            .when_some(native, |d, r| {
                                d.child(levels(&r["levels"], p)).when(
                                    r["phase"] != "ready" || input.muted,
                                    |d| {
                                        d.child(label(
                                            format!(
                                                "{}{}",
                                                r["phase"].as_str().unwrap_or("unavailable"),
                                                if input.muted { " · Silenciado" } else { "" }
                                            ),
                                            if r["phase"] == "ready" {
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
                mixer["issues"].as_array().is_some_and(|a| !a.is_empty()),
                |d| d.child(label("Mixer requiere atención · abre Audio", p.warn)),
            )
    }
    pub(super) fn mixer_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let m = self.production.audio_mixer_status();
        let inputs: Vec<AudioInput> =
            serde_json::from_value(m["store"]["inputs"].clone()).unwrap_or_default();
        col().gap(px(10.)).child(label("Entradas globales · P: peak / R: RMS · dBFS · post-fader / pre-mute",p.secondary))
            .child(quiet("microphone-permission", "Revisar permiso de micrófono").on_click(cx.listener(|v, _, _, cx| {v.production.engine.request_permission(1);v.devices=v.production.engine.devices();cx.notify();})))
            .child(self.action("add-tone","Añadir tono de prueba",Command::AddAudioInput{name:"Tono de prueba".into(),source:AudioSource::Tone},cx))
            .children(self.devices["audio"].as_array().into_iter().flatten().enumerate().filter_map(|(i,d)|Some(self.action(("mixer-device",i),format!("Añadir {}",d["name"].as_str()?),Command::AddAudioInput{name:d["name"].as_str()?.chars().take(80).collect(),source:AudioSource::Microphone{device_id:d["id"].as_str()?.into()}},cx))))
            .children(inputs.iter().enumerate().map(|(i,input)|{
                property_group(input.name.clone(),p).child(row().flex_wrap()
                    .child(self.action(("disconnect-audio",i),"Desconectar…",Command::DisconnectAudioInput{input_id:input.id.clone()},cx))
                    .child(self.action(("reconnect-audio",i),"Reconectar",Command::ReconnectAudioInput{input_id:input.id.clone()},cx))
                    .child(self.action(("remove-audio",i),"Eliminar…",Command::RemoveAudioInput{input_id:input.id.clone()},cx)))
            }))
            .children(m["issues"].as_array().into_iter().flatten().map(|issue|label(format!("{} · {} · {}",issue["input_id"].as_str().unwrap_or("Master"),issue["code"].as_str().unwrap_or(""),issue["recovery"].as_str().unwrap_or("")),p.warn)))
            .child(row().child(self.action("save-mixer","Guardar mixer",Command::SaveAudioMixer,cx)).child(self.action("load-mixer","Restaurar mixer…",Command::LoadAudioMixer,cx)))
            .child(label("Fader: aplica al soltar; flechas ajustan 1 dB. Silenciar conserva el medidor de entrada. Si la mezcla satura, baja la ganancia.",p.muted))
            .child(label("Entradas disponibles: micrófonos y tono de prueba.",p.muted))
    }
}
