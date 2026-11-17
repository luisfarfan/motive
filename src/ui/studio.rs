#[path = "editor.rs"]
mod editor;
use super::{components::*, fixture::Pattern, theme::Palette};
use crate::{
    control,
    core::{Command, Production, Variant},
    scene::{SourceInput, SourceKind, TransitionConfig, TransitionKind},
    window_options,
};
use gpui_kit::assets::IconName;
use gpui_kit::prelude::FluentBuilder;
use gpui_kit::{
    component::{Disableable, Icon, Selectable, TitleBar, button::Button},
    *,
};
use serde_json::Value;
use std::{
    sync::{Arc, mpsc::Receiver},
    time::{Duration, Instant},
};
pub struct Studio {
    pub(crate) production: Production,
    frame: Option<Arc<RenderImage>>,
    sequence: u64,
    requests: Receiver<control::Request>,
    _server: control::Server,
    pub(crate) message: String,
    devices: Value,
    last_device_refresh: Instant,
    picker: Option<&'static str>,
    selected_layer: Option<String>,
    dark: bool,
    panel: Option<&'static str>,
    focus: FocusHandle,
    editor: editor::Editor,
}
impl Studio {
    pub fn new(
        production: Production,
        server: control::Server,
        requests: Receiver<control::Request>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) -> Self {
        let devices = production.engine.devices();
        let editor = editor::Editor::new(window, cx);
        cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor()
                    .timer(Duration::from_millis(33))
                    .await;
                if this
                    .update(cx, |view, cx| {
                        if view.last_device_refresh.elapsed() >= Duration::from_secs(1) {
                            view.production.poll_health();
                            // Freeze choices while a picker is open: activating windows can
                            // reorder the OS inventory between pointer-down and pointer-up.
                            if view.picker.is_none() {
                                view.devices = view.production.engine.devices();
                            }
                            view.last_device_refresh = Instant::now();
                        }
                        if view.production.shutdown_requested {
                            cx.quit();
                            return;
                        }
                        if let Some(open) = view.production.test_window_request.take() {
                            if open {
                                if !view.production.engine.devices()["windows"]
                                    .as_array()
                                    .is_some_and(|w| w.iter().any(|v| v["test"] == true))
                                    && let Err(e) = open_window(
                                        window_options(
                                            "Motive — Fuente controlada",
                                            680.,
                                            420.,
                                            cx,
                                        ),
                                        cx,
                                        |_, cx| cx.new(Pattern::new),
                                    )
                                {
                                    view.message = e.to_string();
                                }
                            } else {
                                view.production.engine.close_test_window();
                            }
                        }
                        for _ in 0..4 {
                            let Ok(request) = view.requests.try_recv() else {
                                break;
                            };
                            let result = view.command(request.command, request.origin, cx);
                            let _ = request.reply.send(result);
                        }
                        if let Some((seq, _, pixels)) =
                            view.production.engine.frame_if_new(view.sequence)
                        {
                            view.sequence = seq;
                            let e = &view.production.engine;
                            let buffer =
                                image::RgbaImage::from_raw(e.width, e.height, pixels).unwrap();
                            let next = Arc::new(RenderImage::new([image::Frame::new(buffer)]));
                            if let Some(old) = view.frame.replace(next) {
                                cx.drop_image(old, None);
                            }
                        }
                        cx.notify();
                    })
                    .is_err()
                {
                    break;
                }
            }
        })
        .detach();
        Self {
            production,
            frame: None,
            sequence: 0,
            requests,
            _server: server,
            message: "Listo. La fuente y el overlay se componen en libobs.".into(),
            devices,
            last_device_refresh: Instant::now(),
            picker: None,
            selected_layer: None,
            dark: false,
            panel: None,
            focus: cx.focus_handle(),
            editor,
        }
    }
    fn command(&mut self, cmd: Command, origin: &str, cx: &mut Context<Self>) -> Value {
        let revision = self.production.revision;
        let preflight = matches!(cmd, Command::PreflightOutput { .. });
        let result = self.production.apply(cmd, origin);
        if result["ok"] != true {
            self.message = format!(
                "{} · {}",
                result["error"]["code"].as_str().unwrap_or("Error"),
                result["error"]["message"]
                    .as_str()
                    .unwrap_or("Operación rechazada")
            );
        } else if preflight {
            self.message = "Configuración válida. La comprobación no abre una conexión.".into();
        } else if self.production.revision != revision {
            self.message = self.production.last_action.clone();
        }
        cx.notify();
        result
    }
}
impl Studio {
    fn action(
        &self,
        id: impl Into<ElementId>,
        text: impl Into<SharedString>,
        command: Command,
        cx: &mut Context<Self>,
    ) -> Button {
        quiet(id, text).on_click(cx.listener(move |v, _, _, cx| {
            v.command(command.clone(), "UI", cx);
        }))
    }
    fn popover(
        &self,
        id: impl Into<ElementId>,
        panel: &'static str,
        trigger: Button,
        layer: Option<String>,
        cx: &mut Context<Self>,
    ) -> gpui_kit::component::popover::Popover {
        let weak = cx.entity().downgrade();
        let open = self.panel == Some(panel) && (layer.is_none() || layer == self.selected_layer);
        gpui_kit::component::popover::Popover::new(id)
            .p_0()
            .bg(Palette::new(self.dark).raised)
            .rounded(px(10.))
            .open(open)
            .trigger(trigger)
            .on_open_change(cx.listener(move |v, open, _, cx| {
                if *open {
                    v.panel = Some(panel);
                    if let Some(layer) = &layer {
                        v.selected_layer = Some(layer.clone());
                    }
                    v.devices = v.production.engine.devices();
                } else {
                    v.panel = None;
                }
                v.picker = None;
                cx.notify();
            }))
            .content(move |_, _, cx| {
                weak.update(cx, |v, cx| v.render_panel(panel, cx).into_any_element())
                    .unwrap_or_else(|_| div().into_any_element())
            })
    }
    fn panel_button(
        &self,
        id: &'static str,
        text: &'static str,
        icon: IconName,
        cx: &mut Context<Self>,
    ) -> gpui_kit::component::popover::Popover {
        let disabled = id == "output" && self.production.status()["output"] != "idle";
        self.popover(
            id,
            id,
            quiet((ElementId::from("trigger"), id), text)
                .icon(icon)
                .tooltip(match id {
                    "audio" => "Seleccionar entrada de audio",
                    "add-source" => "Añadir fuente",
                    _ => text,
                })
                .disabled(disabled),
            None,
            cx,
        )
    }
    fn header(&self, status: &Value, cx: &mut Context<Self>) -> TitleBar {
        let p = Palette::new(self.dark);
        let output = status["output"].as_str().unwrap_or("error");
        let active = matches!(output, "recording" | "streaming");
        let busy = matches!(output, "connecting" | "cancel_pending" | "stopping");
        let source_issue = status["issues"].as_array().is_some_and(|a| !a.is_empty());
        let color = if active {
            p.live
        } else if busy || output == "error" || status["recovery_required"] == true || source_issue {
            p.warn
        } else {
            p.ready
        };
        let caption = match output {
            "recording" => "Grabando",
            "streaming" => "RTMP local",
            "connecting" => "Conectando",
            "cancel_pending" => "Cancelación pendiente",
            "stopping" => "Finalizando",
            "error" => "Error de salida",
            _ => {
                if status["recovery_required"] == true {
                    "Requiere recuperación"
                } else if source_issue {
                    "Fuente no preparada"
                } else {
                    "Listo"
                }
            }
        };
        let seconds = status["stats"]["output_frames"].as_u64().unwrap_or(0) / 30;
        TitleBar::new()
            .h(px(52.))
            .pl(px(88.))
            .pr(px(14.))
            .bg(p.raised)
            .border_color(p.line)
            .child(
                row()
                    .flex_1()
                    .min_w_0()
                    .child(
                        div()
                            .size(px(18.))
                            .rounded(px(5.))
                            .bg(rgb(0x5fe3c6))
                            .text_color(rgb(0x0f2a2e))
                            .font_weight(FontWeight::BOLD)
                            .text_size(px(13.))
                            .flex()
                            .items_center()
                            .justify_center()
                            .child(
                                Icon::default()
                                    .data(include_bytes!("assets/motive-mark.svg"))
                                    .size(px(18.)),
                            ),
                    )
                    .child(
                        div()
                            .font_weight(FontWeight::SEMIBOLD)
                            .text_size(px(15.))
                            .child("motive"),
                    )
                    .child(div().mx(px(6.)).w(px(1.)).h(px(18.)).bg(p.line))
                    .child(self.panel_button(
                        "project",
                        "Mi producción",
                        IconName::ChevronDown,
                        cx,
                    )),
            )
            .child(
                row()
                    .px(px(12.))
                    .h(px(30.))
                    .rounded_full()
                    .bg(color.opacity(0.08))
                    .text_color(color)
                    .child(dot(color))
                    .child(caption)
                    .when(active, |d| {
                        d.child(
                            div()
                                .font_weight(FontWeight::SEMIBOLD)
                                .text_color(p.ink)
                                .child(format!(
                                    "{:02}:{:02}:{:02}",
                                    seconds / 3600,
                                    seconds / 60 % 60,
                                    seconds % 60
                                )),
                        )
                    }),
            )
            .child(
                row()
                    .flex_1()
                    .justify_end()
                    .child(
                        quiet("appearance", "")
                            .icon(if self.dark {
                                IconName::Sun
                            } else {
                                IconName::Moon
                            })
                            .tooltip("Cambiar tema de Motive")
                            .on_click(cx.listener(|v, _, w, cx| {
                                v.dark = !v.dark;
                                Palette::apply(v.dark, Some(w), cx);
                                cx.notify();
                            })),
                    )
                    .child(self.panel_button("agent", "MCP", IconName::Circle, cx))
                    .child(
                        control(
                            "record",
                            if output == "recording" {
                                "Grabando"
                            } else {
                                "Grabar"
                            },
                        )
                        .icon(IconName::Circle)
                        .disabled(
                            output != "idle" || status["recovery_required"] == true || source_issue,
                        )
                        .on_click(cx.listener(|v, _, _, cx| {
                            v.command(Command::StartRecording, "UI", cx);
                        })),
                    )
                    .child(self.panel_button("output", "Emitir", IconName::Radio, cx))
                    .when(output != "idle", |d| {
                        d.child(
                            control(
                                "stop",
                                if output == "connecting" {
                                    "Cancelar"
                                } else if output == "error" {
                                    "Recuperar"
                                } else {
                                    "Finalizar"
                                },
                            )
                            .icon(IconName::Square)
                            .disabled(matches!(output, "cancel_pending" | "stopping"))
                            .on_click(cx.listener(
                                move |v, _, _, cx| {
                                    let cmd = match v.production.status()["output"].as_str() {
                                        Some("connecting") => Command::CancelOutput,
                                        Some("error") => Command::RecoverOutput,
                                        _ => Command::StopOutput,
                                    };
                                    v.command(cmd, "UI", cx);
                                },
                            )),
                        )
                    }),
            )
    }
    fn layers(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let variant = self.production.project.variant;
        let health = self.production.status()["sources"].clone();
        let mut layers = scene.layers.iter().collect::<Vec<_>>();
        layers.sort_by_key(|l| std::cmp::Reverse(l.layouts.get(variant).order));
        col()
            .mt(px(14.))
            .child(
                row()
                    .h(px(30.))
                    .px(px(8.))
                    .child(div().font_weight(FontWeight::SEMIBOLD).child("Capas"))
                    .child(label(format!("en {}", scene.name), p.muted))
                    .child(div().flex_1())
                    .child(self.panel_button("add-source", "Añadir fuente", IconName::Plus, cx)),
            )
            .child(col().border_t_1().border_color(p.line).children(
                layers.into_iter().enumerate().map(|(i, l)| {
                    let source = graph.sources.iter().find(|s| s.id == l.source_id).unwrap();
                    let t = l.layouts.get(variant);
                    let selected = self.selected_layer.as_ref() == Some(&l.id);
                    let layer = l.id.clone();
                    let (icon, detail) = match source.spec {
                        SourceKind::Window { .. } => (IconName::Monitor, "Captura de ventana"),
                        SourceKind::Camera { .. } => (IconName::Video, "Cámara"),
                        SourceKind::Overlay { .. } => (IconName::Layers, "Gráfico animado"),
                        SourceKind::Pattern => (IconName::Monitor, "Patrón libobs"),
                    };
                    let fault = health
                        .as_array()
                        .and_then(|a| a.iter().find(|x| x["id"] == source.id))
                        .and_then(|x| x["issue"].as_str())
                        .is_some_and(|x| !x.is_empty());
                    let mut toggle = t.clone();
                    toggle.visible = !toggle.visible;
                    row()
                        .id(("layer", i))
                        .role(Role::Group)
                        .aria_label(source.name.clone())
                        .focusable()
                        .tab_stop(true)
                        .focus_visible(|s| s.bg(p.selected).border_color(rgb(0x0a7aff)))
                        .on_key_down(cx.listener({
                            let layer = l.id.clone();
                            move |v, e: &KeyDownEvent, w, cx| {
                                if matches!(e.keystroke.key.as_str(), "enter" | "space") {
                                    v.selected_layer = Some(layer.clone());
                                    v.focus.focus(w, cx);
                                    cx.stop_propagation();
                                    cx.notify();
                                }
                            }
                        }))
                        .min_h(px(46.))
                        .px(px(8.))
                        .gap(px(10.))
                        .border_b_1()
                        .border_color(p.line)
                        .when(selected, |d| d.bg(p.selected))
                        .hover(|s| s.bg(p.selected))
                        .cursor_pointer()
                        .on_click(cx.listener(move |v, _, w, cx| {
                            v.selected_layer = Some(layer.clone());
                            if !v.field_focused(w, cx) {
                                v.focus.focus(w, cx);
                            }
                            cx.notify();
                        }))
                        .child(Icon::new(icon).size(px(16.)).text_color(p.secondary))
                        .child(
                            col()
                                .w(px(160.))
                                .min_w(px(96.))
                                .child(
                                    div()
                                        .text_size(px(13.))
                                        .truncate()
                                        .child(source.name.clone()),
                                )
                                .child(
                                    row()
                                        .gap(px(5.))
                                        .child(dot(if fault {
                                            p.warn
                                        } else if !t.visible {
                                            p.muted
                                        } else {
                                            p.ready
                                        }))
                                        .child(
                                            label(
                                                if fault { "Sin señal" } else { detail },
                                                if fault { p.warn } else { p.muted },
                                            )
                                            .text_size(px(11.)),
                                        ),
                                ),
                        )
                        .child(
                            self.action(
                                ("eye", i),
                                "",
                                Command::SetTransform {
                                    scene_id: scene.id.clone(),
                                    layer_id: l.id.clone(),
                                    variant,
                                    transform: toggle,
                                },
                                cx,
                            )
                            .icon(if t.visible {
                                IconName::Eye
                            } else {
                                IconName::EyeOff
                            })
                            .tooltip(if t.visible {
                                "Ocultar capa"
                            } else {
                                "Mostrar capa"
                            }),
                        )
                        .child(
                            row()
                                .flex_1()
                                .when(selected, |d| d.child(self.inspector(cx)))
                                .when(!selected, |d| {
                                    d.child(label(
                                        format!("{:.0} × {:.0}", t.width, t.height),
                                        p.muted,
                                    ))
                                }),
                        )
                        .child(
                            self.popover(
                                ("layer-popup", i),
                                "layer",
                                quiet(("layer-more", i), "")
                                    .icon(IconName::Ellipsis)
                                    .tooltip("Acciones de capa"),
                                Some(l.id.clone()),
                                cx,
                            ),
                        )
                }),
            ))
    }
    fn scenes(&self, rail: f32, status: &Value, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let active = graph.active_scene.clone();
        let live = matches!(status["output"].as_str(), Some("recording" | "streaming"));
        col()
            .flex_1()
            .min_h_0()
            .child(
                row()
                    .h(px(56.))
                    .flex_none()
                    .px(px(4.))
                    .child(div().font_weight(FontWeight::SEMIBOLD).child("Escenas"))
                    .child(label(graph.scenes.len().to_string(), p.muted))
                    .child(div().flex_1())
                    .child(
                        self.action(
                            "new-scene",
                            "",
                            Command::CreateScene {
                                name: format!("Escena {}", graph.next_id),
                            },
                            cx,
                        )
                        .icon(IconName::Plus)
                        .tooltip("Nueva escena"),
                    ),
            )
            .child(
                col()
                    .id("scenes-scroll")
                    .overflow_y_scroll()
                    .flex_1()
                    .min_h_0()
                    .gap(px(4.))
                    .children(graph.scenes.iter().enumerate().map(|(i, s)| {
                        let selected = s.id == active;
                        let id = s.id.clone();
                        let tw = rail - 48.;
                        let th = tw * 9. / 16.;
                        col()
                            .id(("scene", i))
                            .role(Role::Button)
                            .aria_label(s.name.clone())
                            .focusable()
                            .tab_stop(true)
                            .focus_visible(|s| {
                                s.bg(p.selected).border_1().border_color(rgb(0x0a7aff))
                            })
                            .on_key_down(cx.listener({
                                let id = id.clone();
                                move |v, e: &KeyDownEvent, _, cx| {
                                    if matches!(e.keystroke.key.as_str(), "enter" | "space") {
                                        v.command(
                                            Command::SelectScene {
                                                scene_id: id.clone(),
                                            },
                                            "UI",
                                            cx,
                                        );
                                        v.selected_layer = None;
                                        cx.stop_propagation();
                                    }
                                }
                            }))
                            .p(px(6.))
                            .rounded(px(10.))
                            .cursor_pointer()
                            .hover(|d| d.bg(p.selected))
                            .on_click(cx.listener(move |v, _, _, cx| {
                                let r = v.command(
                                    Command::SelectScene {
                                        scene_id: id.clone(),
                                    },
                                    "UI",
                                    cx,
                                );
                                if r["ok"] == true {
                                    v.selected_layer = None;
                                }
                            }))
                            .child(
                                div()
                                    .w(px(tw))
                                    .h(px(th))
                                    .flex()
                                    .items_center()
                                    .justify_center()
                                    .rounded(px(7.))
                                    .overflow_hidden()
                                    .bg(rgb(0x0e0f12))
                                    .border_1()
                                    .border_color(if selected {
                                        if live { p.live } else { p.ink }
                                    } else {
                                        p.line
                                    })
                                    .when(selected, |d| {
                                        d.children(self.frame.clone().map(|f| {
                                            img(f)
                                                .w(px(tw))
                                                .h(px(th))
                                                .object_fit(ObjectFit::Contain)
                                        }))
                                    })
                                    .when(!selected, |d| {
                                        d.child(
                                            col()
                                                .items_center()
                                                .gap(px(8.))
                                                .text_color(rgb(0x6b7079))
                                                .child(Icon::new(IconName::Layers).size(px(22.)))
                                                .child(label("Sin vista previa", rgb(0xa2a7b0))),
                                        )
                                    }),
                            )
                            .child(
                                row()
                                    .pt(px(7.))
                                    .child(div().flex_1().child(s.name.clone()))
                                    .when(selected, |d| {
                                        d.child(label(
                                            if live { "● En salida" } else { "Actual" },
                                            if live { p.live } else { p.secondary },
                                        ))
                                    })
                                    .child(label(format!("⌘{}", i + 1), p.muted)),
                            )
                    })),
            )
    }
    fn audio(&self, status: &Value, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let peak = status["stats"]["audio_peak"]
            .as_f64()
            .unwrap_or(0.)
            .clamp(0., 1.);
        let db = if peak > 0. { 20. * peak.log10() } else { -60. };
        let bars = ((db + 60.) / 60. * 48.).clamp(0., 48.) as usize;
        let audio = &self.production.project.audio;
        let name = if audio == "tone" {
            "Tono de prueba".to_owned()
        } else if audio == "none" {
            "Sin entrada".to_owned()
        } else {
            self.devices["audio"]
                .as_array()
                .and_then(|a| a.iter().find(|x| x["id"].as_str() == Some(audio)))
                .and_then(|x| x["name"].as_str())
                .unwrap_or("Micrófono físico")
                .to_owned()
        };
        col()
            .flex_none()
            .border_t_1()
            .border_color(p.line)
            .pt(px(12.))
            .pb(px(20.))
            .gap(px(10.))
            .child(
                row()
                    .child(
                        div()
                            .flex_1()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child("Audio"),
                    )
                    .child(self.panel_button("audio", "", IconName::SlidersHorizontal, cx)),
            )
            .child(
                row()
                    .child(
                        Icon::new(IconName::Mic)
                            .size(px(16.))
                            .text_color(p.secondary),
                    )
                    .child(
                        div()
                            .flex_1()
                            .overflow_hidden()
                            .text_size(px(12.))
                            .child(name),
                    )
                    .child(label(
                        if peak > 0. {
                            format!("{db:.1} dBFS")
                        } else {
                            "−∞ dBFS".into()
                        },
                        p.secondary,
                    )),
            )
            .child(row().gap(px(1.)).children((0..48).map(|i| {
                div().flex_1().h(px(5.)).bg(if i < bars {
                    if i > 43 {
                        p.live
                    } else if i > 36 {
                        p.warn
                    } else {
                        p.ready
                    }
                } else {
                    p.sunken
                })
            })))
            .child(
                row().justify_between().children(
                    ["−60", "−30", "−12", "0"].map(|x| label(x, p.muted).text_size(px(10.))),
                ),
            )
            .child(label("Nivel pico real · entrada global", p.secondary))
            .child(label("Ganancia y mezcla: próximo hito", p.muted).text_size(px(11.)))
    }
}
impl Render for Studio {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        self.sync_fields(window, cx);
        let p = Palette::new(self.dark);
        let status = self.production.status();
        let bounds = window.viewport_size();
        let width = f32::from(bounds.width);
        let height = f32::from(bounds.height);
        let rail = if width < 1200. { 232. } else { 296. };
        let main = width - rail;
        let pad = if width < 1200. { 18. } else { 24. };
        let stage_w = main - pad * 2.;
        let stage_h = (height - 52. - 56. - 210. - 24.).max(280.);
        let image_h = stage_h - 36. - 54.;
        let image_w = stage_w - 48.;
        let aspect = self.production.engine.width as f32 / self.production.engine.height as f32;
        let pw = image_w.min(image_h * aspect);
        let ph = pw / aspect;
        let scene = self
            .production
            .graph()
            .scene(&self.production.graph().active_scene)
            .unwrap();
        let vertical = self.production.project.variant == Variant::Vertical;
        let output_fault = status["recovery_sources"]
            .as_array()
            .is_some_and(|a| a.iter().any(|x| x == "output"));
        let issues = status["issues"].as_array().is_some_and(|a| !a.is_empty())
            || status["recovery_required"] == true;
        let active = matches!(status["output"].as_str(), Some("recording" | "streaming"));
        let encoder = status["encoding"]["selected_id"]
            .as_str()
            .unwrap_or("Sin encoder activo");
        let bitrate = status["output_configuration"][if status["output"] == "streaming" {
            "streaming"
        } else {
            "recording"
        }]["bitrate_kbps"]
            .as_u64()
            .unwrap_or(0);
        let encoder = if encoder.contains("videotoolbox") {
            "VideoToolbox H.264"
        } else if encoder.contains("x264") {
            "x264 H.264"
        } else {
            encoder
        };
        div().id("studio").track_focus(&self.focus).on_key_down(cx.listener(Self::editor_key)).on_mouse_move(cx.listener(|v,e,_,cx|v.drag_move(e,cx))).on_mouse_up(MouseButton::Left,cx.listener(|v,_,_,cx|v.end_drag(cx))).on_mouse_up_out(MouseButton::Left,cx.listener(|v,_,_,cx|v.end_drag(cx))).size_full().flex().flex_col().bg(p.shell).text_color(p.ink).text_size(px(13.))
            .child(self.header(&status,cx))
            .child(row().items_start().gap_0().flex_1().min_h_0()
                .child(col().w(px(main)).h_full().px(px(pad))
                    .child(row().h(px(56.)).flex_none().child(div().text_size(px(22.)).font_weight(FontWeight::SEMIBOLD).child(scene.name.clone()))
                        .child(row().gap_0().bg(p.sunken).rounded(px(5.)).ml(px(6.))
                            .child(self.action("horizontal","16:9",Command::SetVariant{variant:Variant::Horizontal},cx).icon(IconName::Monitor).selected(!vertical).disabled(status["output"]!="idle"))
                            .child(self.action("vertical","9:16",Command::SetVariant{variant:Variant::Vertical},cx).icon(IconName::Smartphone).selected(vertical).disabled(status["output"]!="idle")))
                        .child(label(format!("{} × {}   30 fps",self.production.engine.width,self.production.engine.height),p.muted)))
                    .child(col().flex_none().w(px(stage_w)).h(px(stage_h)).rounded(px(12.)).overflow_hidden().bg(p.stage).shadow_lg().border_t_2().border_color(if active {p.live}else{p.stage})
                        .child(div().relative().flex_1().flex().items_center().justify_center()
                            .child(self.canvas_view(pw,ph,cx))
                            .when(issues,|d|d.child(row().absolute().top(px(14.)).left(px(14.)).right(px(14.)).p(px(10.)).rounded(px(10.)).bg(rgb(0x222429)).text_color(rgb(0xf1f2f4)).child(Icon::new(IconName::TriangleAlert).size(px(16.)).text_color(rgb(0xffb547))).child(col().flex_1().child(if output_fault {"Salida no disponible"}else{"Fuente no preparada"}).child(label(if output_fault {"Revisa el receptor y recupera la salida explícitamente."}else{"Revisa la captura y reconecta antes de continuar."},rgb(0xa2a7b0)))).child(self.action("recover-sources",if output_fault {"Recuperar salida"}else{"Reconectar"},if output_fault {Command::RecoverOutput}else{Command::ReconnectSources},cx).bg(rgb(0xffffff)).text_color(rgb(0x16181d))))))
                        .child(row().h(px(36.)).flex_none().px(px(14.)).border_t_1().border_color(rgba(0xffffff13)).child(label("Ajustar",rgb(0xa2a7b0))).child(div().flex_1()).child(label(encoder,rgb(0xa2a7b0))).child(label(format!("{bitrate} kb/s"),rgb(0xa2a7b0))).when(width>=1200.,|d|d.child(label("30 fps configurados",rgb(0xa2a7b0)))).child(label(format!("Perdidos {}",status["stats"]["output_dropped_frames"]),rgb(0x45d690)))))
                    .child(col().id("layers-scroll").overflow_y_scroll().flex_1().min_h_0().child(self.layers(cx))))
                .child(col().w(px(rail)).h_full().border_l_1().border_color(p.line).px(px(18.)).child(self.scenes(rail,&status,cx)).child(self.audio(&status,cx))))
            .child(row().h(px(24.)).flex_none().px(px(24.)).border_t_1().border_color(p.line).child(label(self.message.clone(),p.secondary).flex_1().overflow_hidden()).child(label(format!("Rev. {} · MCP local",self.production.revision),p.muted)))
    }
}
impl Studio {
    fn render_panel(&self, panel: &'static str, cx: &mut Context<Self>) -> impl IntoElement {
        let p = Palette::new(self.dark);
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let title = match panel {
            "project" => "Mi producción",
            "add-source" => "Añadir fuente",
            "audio" => "Entrada de audio",
            "output" => "Salida RTMP local",
            "agent" => "Control por agentes",
            "layer" => "Propiedades de capa",
            _ => "Estudio",
        };
        let mut content = col().gap(px(8.));
        match panel {
            "project" => {
                content = content
                    .child(self.action("save", "Guardar proyecto", Command::SaveProject, cx))
                    .child(self.action(
                        "load",
                        "Restaurar proyecto guardado",
                        Command::LoadProject,
                        cx,
                    ))
                    .child(label("Escenas en vivo", p.muted))
                    .child(
                        row()
                            .child(self.action(
                                "cut",
                                "Cut",
                                Command::ConfigureTransition {
                                    transition: TransitionConfig {
                                        kind: TransitionKind::Cut,
                                        duration_ms: 0,
                                    },
                                },
                                cx,
                            ))
                            .child(self.action(
                                "fade",
                                "Fade · 300 ms",
                                Command::ConfigureTransition {
                                    transition: TransitionConfig {
                                        kind: TransitionKind::Fade,
                                        duration_ms: 300,
                                    },
                                },
                                cx,
                            )),
                    )
                    .child(self.action(
                        "remove-scene",
                        "Eliminar escena actual",
                        Command::RemoveScene {
                            scene_id: scene.id.clone(),
                        },
                        cx,
                    ))
                    .child(label("Desarrollo · contenido propio", p.muted))
                    .child(self.action(
                        "fixture",
                        "Abrir ventana controlada",
                        Command::SetTestWindow { open: true },
                        cx,
                    ))
                    .child(self.action(
                        "fixture-close",
                        "Cerrar ventana controlada",
                        Command::SetTestWindow { open: false },
                        cx,
                    ));
            }
            "agent" => {
                content = content
                    .child("CLI y MCP controlan este mismo núcleo local.")
                    .child(label(
                        format!(
                            "Revisión {} · {}",
                            self.production.revision, self.production.last_action
                        ),
                        p.secondary,
                    ))
                    .child(label("Propuestas visuales de agentes: futuras.", p.muted));
            }
            "add-source" | "audio" => {
                if panel == "add-source" {
                    content = content
                        .child(
                            row().children(
                                [
                                    ("windows", "Ventana", IconName::Monitor),
                                    ("cameras", "Webcam", IconName::Video),
                                ]
                                .map(|(kind, title, icon)| {
                                    quiet(kind, title).icon(icon).on_click(cx.listener(
                                        move |v, _, _, cx| {
                                            v.devices = v.production.engine.devices();
                                            v.picker = Some(kind);
                                            cx.notify();
                                        },
                                    ))
                                }),
                            ),
                        )
                        .child(
                            row()
                                .child(
                                    self.action(
                                        "add-overlay",
                                        "Overlay",
                                        Command::AddSource {
                                            scene_id: scene.id.clone(),
                                            name: "Overlay".into(),
                                            source: SourceInput::Overlay { color: 0x33e8b5 },
                                        },
                                        cx,
                                    )
                                    .icon(IconName::Layers),
                                )
                                .child(
                                    self.action(
                                        "add-pattern",
                                        "Patrón",
                                        Command::AddSource {
                                            scene_id: scene.id.clone(),
                                            name: "Patrón".into(),
                                            source: SourceInput::Pattern,
                                        },
                                        cx,
                                    )
                                    .icon(IconName::Monitor),
                                ),
                        )
                        .child(label("Reutilizar una fuente existente", p.muted))
                        .children(graph.sources.iter().enumerate().map(|(i, s)| {
                            self.action(
                                ("reuse", i),
                                s.name.clone(),
                                Command::AddLayer {
                                    scene_id: scene.id.clone(),
                                    source_id: s.id.clone(),
                                },
                                cx,
                            )
                        }));
                } else {
                    content = content
                        .child(
                            row()
                                .child(self.action(
                                    "audio-none",
                                    "Sin audio",
                                    Command::SelectAudio { id: "none".into() },
                                    cx,
                                ))
                                .child(self.action(
                                    "audio-tone",
                                    "Tono de prueba",
                                    Command::SelectAudio { id: "tone".into() },
                                    cx,
                                )),
                        )
                        .child(label("Micrófonos disponibles", p.muted));
                }
                let kind = if panel == "audio" {
                    Some("audio")
                } else {
                    self.picker
                };
                if let Some(kind) = kind {
                    let entries = self.devices[kind].as_array().cloned().unwrap_or_default();
                    if entries.is_empty() {
                        content = content.child(label(
                            "No hay dispositivos disponibles. Revisa conexión y permisos.",
                            p.warn,
                        ));
                    }
                    content = content.children(entries.iter().enumerate().filter_map(|(i, d)| {
                        let name = d["name"].as_str()?;
                        let clean = name
                            .chars()
                            .filter(|c| !c.is_control())
                            .take(80)
                            .collect::<String>();
                        let command = match kind {
                            "audio" => Command::SelectAudio {
                                id: d["id"].as_str()?.into(),
                            },
                            _ => Command::AddSource {
                                scene_id: scene.id.clone(),
                                name: if clean.trim().is_empty() {
                                    "Fuente".into()
                                } else {
                                    clean
                                },
                                source: if kind == "windows" {
                                    SourceInput::Window {
                                        window_id: d["id"].as_u64()? as u32,
                                    }
                                } else {
                                    SourceInput::Camera {
                                        device_id: d["id"].as_str()?.into(),
                                    }
                                },
                            },
                        };
                        Some(self.action(("device", i), name.to_owned(), command, cx))
                    }));
                    content =
                        content.child(quiet("permission", "Revisar permiso de macOS").on_click(
                            cx.listener(move |v, _, _, cx| {
                                v.production.engine.request_permission(match kind {
                                    "audio" => 1,
                                    "cameras" => 2,
                                    _ => 0,
                                });
                                v.devices = v.production.engine.devices();
                                cx.notify();
                            }),
                        ));
                }
            }
            "output" => {
                let s = self.production.status();
                content = content
                    .child("Solo receptor local controlado · una salida a la vez")
                    .child(label(
                        if let Some(port) = s["output_configuration"]["endpoint"]["port"].as_u64() {
                            format!("Receptor local · 127.0.0.1:{port}")
                        } else {
                            "Sin receptor local configurado · usa CLI o MCP".into()
                        },
                        p.secondary,
                    ))
                    .child(self.action(
                        "preflight",
                        "Comprobar salida",
                        Command::PreflightOutput {
                            target: crate::core::output::OutputTarget::Streaming,
                        },
                        cx,
                    ))
                    .child(self.action(
                        "start-stream",
                        "Iniciar RTMP local",
                        Command::StartStream,
                        cx,
                    ))
                    .child(self.action(
                        "recover-output",
                        "Recuperar salida",
                        Command::RecoverOutput,
                        cx,
                    ))
                    .child(label(
                        "No se habilitan destinos públicos desde esta pantalla.",
                        p.muted,
                    ));
            }
            "layer" => {
                if let Some(l) = scene
                    .layers
                    .iter()
                    .find(|l| Some(&l.id) == self.selected_layer.as_ref())
                {
                    let variant = self.production.project.variant;
                    let t = l.layouts.get(variant);
                    content = content
                        .child(label(
                            format!(
                                "{} · X {} / Y {} · {} × {}",
                                l.id, t.x, t.y, t.width, t.height
                            ),
                            p.secondary,
                        ))
                        .children(
                            [("lower", "Bajar capa", -1_i32), ("raise", "Subir capa", 1)].map(
                                |(id, title, delta)| {
                                    let mut transform = t.clone();
                                    transform.order =
                                        (transform.order as i32 + delta).clamp(0, 31) as u32;
                                    self.action(
                                        id,
                                        title,
                                        Command::SetTransform {
                                            scene_id: scene.id.clone(),
                                            layer_id: l.id.clone(),
                                            variant,
                                            transform,
                                        },
                                        cx,
                                    )
                                },
                            ),
                        )
                        .child(self.action(
                            "reconnect-layer",
                            "Reconectar fuente",
                            Command::ReconnectSource {
                                source_id: l.source_id.clone(),
                            },
                            cx,
                        ))
                        .child(self.action(
                            "remove-layer",
                            "Eliminar capa",
                            Command::RemoveLayer {
                                scene_id: scene.id.clone(),
                                layer_id: l.id.clone(),
                            },
                            cx,
                        ));
                    if matches!(
                        graph
                            .sources
                            .iter()
                            .find(|s| s.id == l.source_id)
                            .unwrap()
                            .spec,
                        SourceKind::Overlay { .. }
                    ) {
                        content = content.child(
                            row().children(
                                [
                                    ("Mint", 0x33e8b5),
                                    ("Ámbar", 0xffb547),
                                    ("Blanco", 0xffffff),
                                ]
                                .map(|(name, color)| {
                                    self.action(
                                        name,
                                        name,
                                        Command::SetOverlayColor {
                                            source_id: l.source_id.clone(),
                                            color,
                                        },
                                        cx,
                                    )
                                }),
                            ),
                        );
                    }
                }
            }
            _ => {}
        }

        col()
            .w(px(420.))
            .max_h(px(540.))
            .p(px(18.))
            .gap(px(14.))
            .child(
                row()
                    .child(
                        div()
                            .flex_1()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child(title),
                    )
                    .child(
                        quiet("close-panel", "")
                            .icon(IconName::X)
                            .tooltip("Cerrar")
                            .on_click(cx.listener(|v, _, w, cx| {
                                v.panel = None;
                                v.picker = None;
                                v.focus.focus(w, cx);
                                cx.notify();
                            })),
                    ),
            )
            .child(content.id("panel-scroll").overflow_y_scroll())
            .child(label(self.message.clone(), p.secondary))
    }
}
