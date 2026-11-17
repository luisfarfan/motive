//! Read native receipts every render; never advance a media clock in GPUI.
use super::*;
use crate::core::overlays::{Animation, AnimationKind, Definition, Easing, Event, WidgetKind};
use gpui_kit::component::input::InputState;
pub(super) struct AnimationDraft {
    kind: AnimationKind,
    easing: Easing,
    duration: Entity<InputState>,
    distance: Entity<InputState>,
    scale: Entity<InputState>,
}
impl AnimationDraft {
    pub fn new(w: &mut Window, cx: &mut Context<Studio>) -> Self {
        Self {
            kind: AnimationKind::FadeIn,
            easing: Easing::Linear,
            duration: cx.new(|cx| InputState::new(w, cx).default_value("1200")),
            distance: cx.new(|cx| InputState::new(w, cx).default_value("160")),
            scale: cx.new(|cx| InputState::new(w, cx).default_value("0.7")),
        }
    }
    fn value(&self, cx: &App) -> anyhow::Result<Animation> {
        let a = Animation {
            kind: self.kind,
            easing: self.easing,
            duration_ms: forms::integer(&self.duration.read(cx).value())
                .map_err(anyhow::Error::msg)?,
            distance: draft::number(&self.distance.read(cx).value())?,
            scale_from: draft::number(&self.scale.read(cx).value())?,
        };
        a.validate()?;
        Ok(a)
    }
}
fn phase(value: &Value) -> String {
    match value.as_str().unwrap_or("unavailable") {
        "running" => "En curso",
        "cancel_pending" => "Cancelación solicitada",
        "cancelled" => "Cancelada",
        "completed" => "Completada",
        "failed" => "Fallida",
        "visible" => "Visible",
        "hidden" => "Oculto",
        "showing" => "Entrando",
        "hiding" => "Saliendo",
        "paused" => "Pausado",
        "idle" => "Preparado",
        "playing" => "Reproduciendo",
        "stopped" => "Detenido",
        "ended" => "Finalizado",
        "error" => "Error",
        _ => return value.as_str().unwrap_or("Sin estado nativo").into(),
    }
    .into()
}
impl Studio {
    pub(super) fn overlay_live_controls(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let mut body = col().gap(px(10.));
        let Some(draft) = &self.creative.draft else {
            return body;
        };
        let Some(id) = &draft.source_id else {
            return body;
        };
        let state = self.production.overlay_status();
        let native = state["runtime"]["sources"]
            .as_array()
            .and_then(|a| a.iter().find(|v| v["id"] == *id));
        if let Some(s) = native {
            body = body.child(label(
                format!("Estado: {}", phase(&s["phase"])),
                p.secondary,
            ));
            if let Some(code) = s["health"].as_str().filter(|s| !s.is_empty()) {
                body = body.child(label(code.to_owned(), p.warn));
            }
            if let Some(ms) = s["remaining_ms"]
                .as_u64()
                .filter(|_| matches!(draft.definition, Definition::Widget { .. }))
            {
                let seconds = ms.div_ceil(1000);
                body = body.child(label(
                    format!("Restante: {:02}:{:02}", seconds / 60, seconds % 60),
                    p.ink,
                ));
            }
            if matches!(draft.definition, Definition::Video { .. }) {
                body = body.child(label(
                    format!(
                        "Video: {} · {} / {} ms",
                        phase(&s["media_state"]),
                        s["media_time_ms"],
                        s["media_duration_ms"]
                    ),
                    p.secondary,
                ));
                body = body.child(label("Ocultar una capa no detiene el video. Usa Pausar o Detener para parar su reproducción.", p.muted));
            }
        } else {
            body = body.child(label("Sin estado nativo para esta fuente.", p.warn));
        }
        let events: Vec<(Event, &str)> = match &draft.definition {
            Definition::Widget { widget } => match widget.kind {
                WidgetKind::LowerThird => vec![(Event::Show, "Mostrar"), (Event::Hide, "Ocultar")],
                WidgetKind::Countdown => vec![
                    (Event::TimerStart, "Iniciar / continuar"),
                    (Event::TimerStop, "Pausar"),
                    (Event::TimerReset, "Restablecer"),
                ],
                WidgetKind::Alert => {
                    vec![(Event::Trigger, "Lanzar alerta"), (Event::Hide, "Ocultar")]
                }
            },
            Definition::Video { .. } => vec![
                (Event::Play, "Reproducir"),
                (Event::Pause, "Pausar"),
                (Event::Restart, "Reiniciar"),
                (Event::Stop, "Detener"),
            ],
            _ => vec![
                (Event::Show, "Mostrar fuente"),
                (Event::Hide, "Ocultar fuente"),
            ],
        };
        body = body.child(
            row()
                .flex_wrap()
                .children(events.into_iter().enumerate().map(|(i, (event, title))| {
                    self.action(
                        ("overlay-event", i),
                        title,
                        Command::Overlay(OverlayCommand::OverlayEvent {
                            source_id: id.clone(),
                            event,
                        }),
                        cx,
                    )
                })),
        );
        body.child(label("Los eventos afectan esta fuente en todas sus escenas. La visibilidad de cada capa se controla con su icono de ojo.",p.muted))
            .child(self.action("overlay-reconnect","Reconectar fuente",Command::ReconnectSource{source_id:id.clone()},cx).disabled(self.production.status()["output"]!="idle"))
    }
    pub(super) fn overlay_animation_controls(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let mut body = col().gap(px(10.));
        let Some(draft) = &self.creative.draft else {
            return body;
        };
        let Some(a) = &self.creative.animation else {
            return body;
        };
        let graph = self.production.graph();
        let layer = graph.scene(&graph.active_scene).ok().and_then(|s| {
            s.layers.iter().find(|l| {
                Some(&l.id) == self.selected_layer.as_ref()
                    && Some(&l.source_id) == draft.source_id.as_ref()
            })
        });
        if layer.is_none() {
            body = body.child(label(
                "Selecciona una capa de esta fuente en la escena activa para animarla.",
                p.warn,
            ));
        }
        let state = self.production.overlay_status();
        let runtime = &state["runtime"]["animations"];
        let jobs = runtime["jobs"].as_array().cloned().unwrap_or_default();
        // Keep the actual receipt and cancellation visible above the settings.
        if let Some(job) = jobs.iter().rev().find(|j| {
            layer.is_some_and(|l| j["layer_id"] == l.id) && j["scene_id"] == graph.active_scene
        }) {
            let id = job["operation_id"].as_u64().unwrap_or(0);
            body = body.child(
                row()
                    .flex_wrap()
                    .child(label(
                        format!(
                            "#{id} · {} · {}%{}",
                            phase(&job["phase"]),
                            (job["progress"].as_f64().unwrap_or(0.) * 100.).round(),
                            if job["pending_ack"] == true {
                                " · confirmación pendiente"
                            } else {
                                ""
                            }
                        ),
                        p.secondary,
                    ))
                    .child(
                        self.action(
                            "cancel-current-animation",
                            format!("Cancelar #{id}"),
                            Command::Overlay(OverlayCommand::CancelOverlayAnimation {
                                operation_id: id,
                            }),
                            cx,
                        )
                        .disabled(job["phase"] != "running"),
                    ),
            );
            if let Some(error) = job["error"].as_str() {
                body = body.child(label(error.to_owned(), p.warn));
            }
        } else {
            body = body.child(label(
                "Esta capa aún no tiene operaciones de animación.",
                p.muted,
            ));
        }
        body = body
            .child(
                row().flex_wrap().children(
                    [
                        (AnimationKind::FadeIn, "Fade in"),
                        (AnimationKind::FadeOut, "Fade out"),
                        (AnimationKind::SlideIn, "Slide in"),
                        (AnimationKind::SlideOut, "Slide out"),
                        (AnimationKind::ScaleIn, "Scale in"),
                        (AnimationKind::ScaleOut, "Scale out"),
                    ]
                    .into_iter()
                    .enumerate()
                    .map(|(i, (kind, name))| {
                        quiet(("animation-kind", i), name)
                            .selected(a.kind == kind)
                            .on_click(cx.listener(move |v, _, _, cx| {
                                if let Some(a) = &mut v.creative.animation {
                                    a.kind = kind;
                                    if matches!(
                                        kind,
                                        AnimationKind::FadeIn | AnimationKind::FadeOut
                                    ) {
                                        a.easing = Easing::Linear;
                                    }
                                }
                                cx.notify();
                            }))
                    }),
                ),
            )
            .child(forms::field("Duración · 100 a 10000 ms", &a.duration, p));
        let fade = matches!(a.kind, AnimationKind::FadeIn | AnimationKind::FadeOut);
        if !fade {
            body = body.child(
                row().flex_wrap().children(
                    [
                        (Easing::Linear, "Lineal"),
                        (Easing::EaseIn, "Entrada"),
                        (Easing::EaseOut, "Salida"),
                        (Easing::EaseInOut, "Entrada/salida"),
                    ]
                    .into_iter()
                    .enumerate()
                    .map(|(i, (easing, name))| {
                        quiet(("animation-easing", i), name)
                            .selected(a.easing == easing)
                            .on_click(cx.listener(move |v, _, _, cx| {
                                if let Some(a) = &mut v.creative.animation {
                                    a.easing = easing;
                                }
                                cx.notify();
                            }))
                    }),
                ),
            );
        } else {
            body = body.child(label("Fade usa la curva lineal nativa.", p.muted));
        }
        if matches!(a.kind, AnimationKind::SlideIn | AnimationKind::SlideOut) {
            body = body.child(forms::field("Distancia · −1920 a 1920 px", &a.distance, p));
        }
        if matches!(a.kind, AnimationKind::ScaleIn | AnimationKind::ScaleOut) {
            body = body.child(forms::field("Escala inicial · 0.1 a 2", &a.scale, p));
        }

        let scene = graph.active_scene.clone();
        let layer_id = layer.map(|l| l.id.clone());
        let transition = self.production.status()["transition"]["phase"].clone();

        let layer_busy = jobs.iter().any(|j| {
            Some(j["layer_id"].as_str().unwrap_or_default()) == layer_id.as_deref()
                && (matches!(j["phase"].as_str(), Some("running" | "cancel_pending"))
                    || j["pending_ack"] == true)
        });
        body=body.child(control("start-overlay-animation","Iniciar animación").disabled(layer_id.is_none() || layer_busy || transition=="preparing" || transition=="running")
            .on_click(cx.listener(move|v,_,_,cx|{
                let Some(layer_id)=&layer_id else{return};let Some(a)=&v.creative.animation else{return};
                match a.value(cx) {
                    Ok(animation)=>{let r=v.command(Command::Overlay(OverlayCommand::AnimateOverlay{scene_id:scene.clone(),layer_id:layer_id.clone(),animation}),"UI",cx);if r["ok"]==true{v.creative.last_animation=r["result"]["operation_id"].as_u64();}},
                    Err(e)=>{v.message=e.to_string();cx.notify();}
                }
            })))
            .child(label("Una animación por capa, hasta ocho. Cut/Fade y los cambios estructurales esperan la finalización nativa.",p.muted));
        if let Some(id) = self.creative.last_animation {
            body = body.child(label(
                format!("Última operación solicitada: {id}"),
                p.secondary,
            ));
        }
        if let Some(error) = state["completion_error"].as_str() {
            body = body.child(label(error.to_owned(), p.warn));
        }
        for (i, j) in jobs.iter().enumerate() {
            let id = j["operation_id"].as_u64().unwrap_or(0);
            body = body.child(
                col()
                    .gap(px(5.))
                    .border_t_1()
                    .border_color(p.line)
                    .py(px(6.))
                    .child(label(
                        format!(
                            "#{id} · {} · {}%{}",
                            phase(&j["phase"]),
                            (j["progress"].as_f64().unwrap_or(0.) * 100.).round(),
                            if j["pending_ack"] == true {
                                " · confirmación pendiente"
                            } else {
                                ""
                            }
                        ),
                        p.secondary,
                    ))
                    .child(label(
                        format!(
                            "{} · {}",
                            j["scene_id"].as_str().unwrap_or(""),
                            j["layer_id"].as_str().unwrap_or("")
                        ),
                        p.muted,
                    ))
                    .when_some(j["error"].as_str().map(str::to_owned), |d, e| {
                        d.child(label(e, p.warn))
                    })
                    .child(
                        self.action(
                            ("cancel-overlay-animation", i),
                            format!("Cancelar #{id}"),
                            Command::Overlay(OverlayCommand::CancelOverlayAnimation {
                                operation_id: id,
                            }),
                            cx,
                        )
                        .disabled(j["phase"] != "running"),
                    ),
            );
        }
        body
    }
}
