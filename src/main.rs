mod control;
mod core;
mod engine;
mod scene;

use core::{Command, Production, Variant};
use gpui_kit::component::button::{Button, ButtonVariants};
use gpui_kit::*;
use scene::{SourceInput, SourceKind};
use serde_json::{Value, json};
use std::{
    sync::{Arc, mpsc::Receiver},
    time::{Duration, Instant},
};

struct Studio {
    production: Production,
    frame: Option<Arc<RenderImage>>,
    sequence: u64,
    requests: Receiver<control::Request>,
    _server: control::Server,
    message: String,
    devices: Value,
    last_device_refresh: Instant,
    picker: Option<&'static str>,
    picker_add: bool,
    selected_layer: Option<String>,
}
impl Studio {
    fn new(
        production: Production,
        server: control::Server,
        requests: Receiver<control::Request>,
        cx: &mut Context<Self>,
    ) -> Self {
        let devices = production.engine.devices();
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
            picker_add: false,
            selected_layer: None,
        }
    }
    fn command(&mut self, cmd: Command, origin: &str, cx: &mut Context<Self>) -> Value {
        let result = self.production.apply(cmd, origin);
        self.message = if result["ok"] == true {
            self.production.last_action.clone()
        } else {
            result["error"]["message"]
                .as_str()
                .unwrap_or("Error")
                .into()
        };
        cx.notify();
        result
    }
    fn button(
        &self,
        id: &'static str,
        label: &str,
        command: Command,
        cx: &mut Context<Self>,
    ) -> Button {
        Button::new(id)
            .label(label.to_owned())
            .on_click(cx.listener(move |view, _, _, cx| {
                view.command(command.clone(), "UI", cx);
            }))
    }
}
impl Studio {
    fn editor(&self, cx: &mut Context<Self>) -> Div {
        let graph = self.production.graph();
        let scene = graph.scene(&graph.active_scene).unwrap();
        let variant = self.production.project.variant;
        let scene_id = scene.id.clone();
        let scene_buttons = div()
            .flex()
            .flex_wrap()
            .gap_2()
            .children(graph.scenes.iter().enumerate().map(|(i, s)| {
                let id = s.id.clone();
                Button::new(("scene", i))
                    .label(format!(
                        "{} {}",
                        if s.id == scene_id { "●" } else { "○" },
                        s.name
                    ))
                    .on_click(cx.listener(move |v, _, _, cx| {
                        v.command(
                            Command::SelectScene {
                                scene_id: id.clone(),
                            },
                            "UI",
                            cx,
                        );
                        v.selected_layer = None;
                    }))
            }))
            .child(self.button(
                "new-scene",
                "Nueva escena",
                Command::CreateScene {
                    name: format!("Escena {}", graph.next_id),
                },
                cx,
            ))
            .child(self.button(
                "remove-scene",
                "Eliminar escena",
                Command::RemoveScene {
                    scene_id: scene_id.clone(),
                },
                cx,
            ));
        let add = div()
            .flex()
            .flex_wrap()
            .gap_2()
            .children(
                [("windows", "Añadir ventana"), ("cameras", "Añadir webcam")]
                    .into_iter()
                    .map(|(kind, label)| {
                        Button::new(if kind == "windows" {
                            "add-window"
                        } else {
                            "add-camera"
                        })
                        .label(label)
                        .on_click(cx.listener(move |v, _, _, cx| {
                            v.picker_add = true;
                            v.picker = Some(kind);
                            v.devices = v.production.engine.devices();
                            cx.notify();
                        }))
                    }),
            )
            .child(self.button(
                "add-overlay",
                "Añadir overlay",
                Command::AddSource {
                    scene_id: scene_id.clone(),
                    name: "Overlay nuevo".into(),
                    source: SourceInput::Overlay { color: 0x33e8b5 },
                },
                cx,
            ))
            .child(self.button(
                "add-pattern",
                "Añadir patrón",
                Command::AddSource {
                    scene_id: scene_id.clone(),
                    name: "Patrón secundario".into(),
                    source: SourceInput::Pattern,
                },
                cx,
            ));
        let layers =
            div()
                .flex()
                .flex_wrap()
                .gap_2()
                .children(scene.layers.iter().enumerate().map(|(i, l)| {
                    let id = l.id.clone();
                    let source = graph.sources.iter().find(|s| s.id == l.source_id).unwrap();
                    let t = l.layouts.get(variant);
                    Button::new(("layer", i))
                        .label(format!(
                            "{} · {} · ({:.0},{:.0}) {:.0}×{:.0} · z{} {}",
                            source.name,
                            l.id,
                            t.x,
                            t.y,
                            t.width,
                            t.height,
                            t.order,
                            if t.visible { "visible" } else { "oculta" }
                        ))
                        .on_click(cx.listener(move |v, _, _, cx| {
                            v.selected_layer = Some(id.clone());
                            cx.notify();
                        }))
                }));
        let selected = self
            .selected_layer
            .as_ref()
            .and_then(|id| scene.layers.iter().find(|l| &l.id == id))
            .or_else(|| scene.layers.first());
        let library =
            div()
                .flex()
                .flex_wrap()
                .gap_2()
                .children(graph.sources.iter().enumerate().map(|(i, source)| {
                    let source_id = source.id.clone();
                    let scene_id = scene_id.clone();
                    let unused = !graph
                        .scenes
                        .iter()
                        .any(|s| s.layers.iter().any(|l| l.source_id == source.id));
                    let mut row = div().flex().gap_1().child(
                        Button::new(("reuse-source", i))
                            .label(format!("Reutilizar {}", source.name))
                            .on_click(cx.listener(move |v, _, _, cx| {
                                v.command(
                                    Command::AddLayer {
                                        scene_id: scene_id.clone(),
                                        source_id: source_id.clone(),
                                    },
                                    "UI",
                                    cx,
                                );
                            })),
                    );
                    if unused {
                        let source_id = source.id.clone();
                        row = row.child(
                            Button::new(("release-source", i))
                                .label("Liberar fuente")
                                .on_click(cx.listener(move |v, _, _, cx| {
                                    v.command(
                                        Command::RemoveSource {
                                            source_id: source_id.clone(),
                                        },
                                        "UI",
                                        cx,
                                    );
                                })),
                        );
                    }
                    row
                }));
        let mut inspector = div().flex().flex_col().gap_2();
        if let Some(l) = selected {
            let t = l.layouts.get(variant);
            let source = graph.sources.iter().find(|s| s.id == l.source_id).unwrap();
            inspector = inspector.child(div().text_sm().child(format!(
                "Propiedades: {} / {} · {:?}",
                source.name, l.id, variant
            )));
            let operations = [
                ("x-left", "X −20", 0, -20.),
                ("x-right", "X +20", 0, 20.),
                ("y-up", "Y −20", 1, -20.),
                ("y-down", "Y +20", 1, 20.),
                ("w-less", "Ancho −20", 2, -20.),
                ("w-more", "Ancho +20", 2, 20.),
                ("h-less", "Alto −20", 3, -20.),
                ("h-more", "Alto +20", 3, 20.),
                ("z-down", "Bajar capa", 4, -1.),
                ("z-up", "Subir capa", 4, 1.),
            ];
            let controls = div()
                .flex()
                .flex_wrap()
                .gap_2()
                .children(operations.into_iter().map(|(id, label, axis, delta)| {
                    let mut next = t.clone();
                    match axis {
                        0 => next.x += delta,
                        1 => next.y += delta,
                        2 => next.width = (next.width + delta).clamp(1., 4096.),
                        3 => next.height = (next.height + delta).clamp(1., 4096.),
                        _ => next.order = (next.order as f32 + delta).clamp(0., 31.) as u32,
                    }
                    self.button(
                        id,
                        label,
                        Command::SetTransform {
                            scene_id: scene_id.clone(),
                            layer_id: l.id.clone(),
                            variant,
                            transform: next,
                        },
                        cx,
                    )
                }));
            let mut hidden = t.clone();
            hidden.visible = !hidden.visible;
            let mut more = div()
                .flex()
                .flex_wrap()
                .gap_2()
                .child(self.button(
                    "layer-visible",
                    if t.visible {
                        "Ocultar capa"
                    } else {
                        "Mostrar capa"
                    },
                    Command::SetTransform {
                        scene_id: scene_id.clone(),
                        layer_id: l.id.clone(),
                        variant,
                        transform: hidden,
                    },
                    cx,
                ))
                .child(self.button(
                    "layer-remove",
                    "Eliminar capa",
                    Command::RemoveLayer {
                        scene_id: scene_id.clone(),
                        layer_id: l.id.clone(),
                    },
                    cx,
                ))
                .child(self.button(
                    "source-reconnect",
                    "Reconectar esta fuente",
                    Command::ReconnectSource {
                        source_id: source.id.clone(),
                    },
                    cx,
                ));
            if let SourceKind::Overlay { color } = source.spec {
                more = more.child(self.button(
                    "overlay-color",
                    "Cambiar acento",
                    Command::SetOverlayColor {
                        source_id: source.id.clone(),
                        color: if color == 0x33e8b5 {
                            0xff7040
                        } else {
                            0x33e8b5
                        },
                    },
                    cx,
                ));
            }
            inspector = inspector.child(controls).child(more);
        }
        div()
            .flex_none()
            .flex()
            .flex_col()
            .gap_2()
            .p_3()
            .bg(rgb(0x1a2330))
            .rounded_lg()
            .child(div().text_sm().child(format!(
                "Editor de escenas · {} · revisión {}",
                scene.id, self.production.revision
            )))
            .child(scene_buttons)
            .child(add)
            .child(layers)
            .child(inspector)
            .child(library)
    }
}
impl Render for Studio {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let p = &self.production;
        let status = p.status();
        let vertical = p.project.variant == Variant::Vertical;
        // Keep choices visible without two competing scroll areas.
        let preview_height = if self.picker.is_some() { 150. } else { 230. };
        let heading = div()
            .flex_none()
            .flex()
            .justify_between()
            .items_center()
            .child(
                div()
                    .flex()
                    .flex_col()
                    .gap_1()
                    .child(div().text_2xl().child("MOTIVE"))
                    .child(
                        div()
                            .text_sm()
                            .text_color(rgb(0x9baabd))
                            .child("Tu producción, en esta Mac."),
                    ),
            )
            .child(div().text_color(rgb(0x64e4c1)).child(format!(
                "{} · {} × {} · 30 fps",
                status["output"].as_str().unwrap_or(""),
                p.engine.width,
                p.engine.height
            )));
        let preview = div()
            .w_full()
            .h(px(preview_height))
            .flex_none()
            .overflow_hidden()
            .flex()
            .items_center()
            .justify_center()
            .bg(rgb(0x080c12))
            .rounded_lg()
            .children(self.frame.clone().map(|f| {
                img(f)
                    .w(px(
                        preview_height * if vertical { 9. / 16. } else { 16. / 9. }
                    ))
                    .h(px(preview_height))
                    .object_fit(ObjectFit::Contain)
            }));
        let rows = div()
            .flex_none()
            .flex()
            .flex_col()
            .gap_2()
            .child(
                div()
                    .flex()
                    .gap_2()
                    .child(self.button(
                        "pattern",
                        "Patrón libobs",
                        Command::SelectSource { window_id: None },
                        cx,
                    ))
                    .child(
                        Button::new("test-window")
                            .label(
                                if self.devices["windows"]
                                    .as_array()
                                    .is_some_and(|w| w.iter().any(|v| v["test"] == true))
                                {
                                    "Cerrar fuente de prueba"
                                } else {
                                    "Abrir fuente de prueba"
                                },
                            )
                            .on_click(cx.listener(|view, _, _, cx| {
                                if view.production.engine.devices()["windows"]
                                    .as_array()
                                    .is_some_and(|w| w.iter().any(|v| v["test"] == true))
                                {
                                    view.production.engine.close_test_window();
                                    view.devices = view.production.engine.devices();
                                    cx.notify();
                                    return;
                                }
                                if let Err(e) = open_window(
                                    window_options("Motive — Fuente controlada", 680., 420., cx),
                                    cx,
                                    |_, cx| cx.new(Pattern::new),
                                ) {
                                    view.message = e.to_string();
                                }
                                view.devices = view.production.engine.devices();
                                cx.notify();
                            })),
                    )
                    .child(
                        Button::new("capture")
                            .label("Capturar fuente de prueba")
                            .on_click(cx.listener(|view, _, _, cx| {
                                view.devices = view.production.engine.devices();
                                if let Some(id) = view.devices["windows"]
                                    .as_array()
                                    .and_then(|a| a.iter().find(|w| w["test"] == true))
                                    .and_then(|w| w["id"].as_u64())
                                {
                                    view.command(
                                        Command::SelectSource {
                                            window_id: Some(id as u32),
                                        },
                                        "UI",
                                        cx,
                                    );
                                } else {
                                    view.message = "Abre primero la fuente de prueba.".into();
                                    cx.notify();
                                }
                            })),
                    )
                    .child(self.button(
                        "variant",
                        if vertical {
                            "Cambiar a horizontal"
                        } else {
                            "Cambiar a vertical"
                        },
                        Command::SetVariant {
                            variant: if vertical {
                                Variant::Horizontal
                            } else {
                                Variant::Vertical
                            },
                        },
                        cx,
                    ))
                    .child(self.button(
                        "overlay",
                        if p.project.overlay {
                            "Ocultar overlay"
                        } else {
                            "Mostrar overlay"
                        },
                        Command::SetOverlay {
                            visible: !p.project.overlay,
                        },
                        cx,
                    )),
            )
            .child(
                div()
                    .flex()
                    .gap_2()
                    .child(self.button(
                        "tone",
                        "Audio: tono de prueba",
                        Command::SelectAudio { id: "tone".into() },
                        cx,
                    ))
                    .child(self.button(
                        "silence",
                        "Sin audio",
                        Command::SelectAudio { id: "none".into() },
                        cx,
                    ))
                    .child(
                        Button::new("devices")
                            .label("Actualizar dispositivos")
                            .on_click(cx.listener(|view, _, _, cx| {
                                view.devices = view.production.engine.devices();
                                cx.notify();
                            })),
                    )
                    .child(self.button("save", "Guardar proyecto", Command::SaveProject, cx))
                    .child(self.button("load", "Restaurar proyecto", Command::LoadProject, cx)),
            )
            .child(
                div()
                    .flex()
                    .gap_2()
                    .child(
                        self.button("record", "Grabar", Command::StartRecording, cx)
                            .primary(),
                    )
                    .child(self.button("stop", "Finalizar salida", Command::StopOutput, cx))
                    .child(self.button(
                        "local-stream",
                        "Enviar a receptor local",
                        Command::StartLocalStream,
                        cx,
                    ))
                    .child(
                        Button::new("screen-permission")
                            .label("Permiso pantalla")
                            .on_click(cx.listener(|view, _, _, cx| {
                                view.production.engine.request_permission(0);
                                view.message =
                                    "Completa la solicitud de macOS y actualiza dispositivos."
                                        .into();
                                cx.notify();
                            })),
                    )
                    .child(
                        Button::new("mic-permission")
                            .label("Permiso micrófono")
                            .on_click(cx.listener(|view, _, _, cx| {
                                view.production.engine.request_permission(1);
                                view.message =
                                    "Completa la solicitud de macOS y actualiza dispositivos."
                                        .into();
                                cx.notify();
                            })),
                    )
                    .child(Button::new("quit").label("Cerrar").on_click(cx.listener(
                        |view, _, _, cx| {
                            if view.production.engine.output_state() != 0 {
                                view.message = "Finaliza la salida antes de cerrar.".into();
                                cx.notify();
                            } else {
                                cx.quit();
                            }
                        },
                    ))),
            );
        let selectors = div()
            .flex_none()
            .flex()
            .gap_2()
            .children(
                [
                    ("windows", "Elegir ventana"),
                    ("cameras", "Elegir cámara"),
                    ("audio", "Elegir micrófono"),
                ]
                .into_iter()
                .map(|(kind, label)| {
                    Button::new(kind)
                        .label(label)
                        .on_click(cx.listener(move |view, _, _, cx| {
                            view.picker_add = false;
                            view.picker = if view.picker == Some(kind) {
                                None
                            } else {
                                Some(kind)
                            };
                            view.devices = view.production.engine.devices();
                            cx.notify();
                        }))
                }),
            )
            .child(self.button(
                "reconnect",
                "Reconectar fuentes",
                Command::ReconnectSources,
                cx,
            ))
            .child(
                Button::new("camera-permission")
                    .label("Permiso cámara")
                    .on_click(cx.listener(|view, _, _, cx| {
                        view.production.engine.request_permission(2);
                        view.message = "Completa el permiso de cámara de macOS.".into();
                        cx.notify();
                    })),
            );
        let picker = self.picker.map(|kind| {
            let entries = self.devices[kind].as_array().cloned().unwrap_or_default();
            div()
                .id("source-picker")
                .h(px(160.))
                .flex_none()
                .overflow_y_scroll()
                .flex()
                .flex_col()
                .gap_1()
                .child(div().text_sm().child(if entries.is_empty() {
                    "No hay fuentes disponibles. Comprueba conexión y permisos."
                } else {
                    "Selecciona una fuente. La salida debe estar detenida."
                }))
                .children(entries.into_iter().enumerate().filter_map(|(i, d)| {
                    let name = d["name"].as_str()?.to_owned();
                    let command = if self.picker_add && kind != "audio" {
                        let source = if kind == "windows" {
                            SourceInput::Window {
                                window_id: d["id"].as_u64()? as u32,
                            }
                        } else {
                            SourceInput::Camera {
                                device_id: d["id"].as_str()?.into(),
                            }
                        };
                        Command::AddSource {
                            scene_id: self.production.graph().active_scene.clone(),
                            name: {
                                let label: String =
                                    name.chars().filter(|c| !c.is_control()).take(80).collect();
                                if label.trim().is_empty() {
                                    "Fuente".into()
                                } else {
                                    label
                                }
                            },
                            source,
                        }
                    } else {
                        match kind {
                            "windows" => Command::SelectSource {
                                window_id: Some(d["id"].as_u64()? as u32),
                            },
                            "cameras" => Command::SelectCamera {
                                id: d["id"].as_str()?.into(),
                            },
                            _ => Command::SelectAudio {
                                id: d["id"].as_str()?.into(),
                            },
                        }
                    };
                    let label = if kind == "windows" {
                        format!("{} · {}", d["app"].as_str().unwrap_or(""), name)
                    } else {
                        name
                    };
                    Some(
                        Button::new(("source-choice", i))
                            .label(label)
                            .on_click(cx.listener(move |view, _, _, cx| {
                                let result = view.command(command.clone(), "UI", cx);
                                if result["ok"] == true {
                                    view.picker = None;
                                }
                                cx.notify();
                            })),
                    )
                }))
        });
        div()
            .id("studio-scroll")
            .overflow_y_scroll()
            .size_full()
            .flex()
            .flex_col()
            .p_6()
            .gap_3()
            .bg(rgb(0x11151c))
            .text_color(rgb(0xf1f5f9))
            .child(heading)
            .child(preview)
            .child(self.editor(cx))
            .child(rows)
            .child(selectors)
            .children(picker)
            .child(div().flex_none().text_sm().text_color(rgb(0xffb58c)).child(
                if status["issues"].as_array().is_some_and(|a| !a.is_empty()) {
                    "Fuente sin datos o desconectada. Revisa la selección y reconecta antes de grabar."
                } else {
                    ""
                },
            ))
            .child(
                div()
                    .text_sm()
                    .text_color(rgb(0x82e8cb))
                    .child(self.message.clone()),
            )
            .child(div().flex_none().text_xs().text_color(rgb(0x9baabd)).child(format!(
                "Fuente: {} · Audio: {} · Frame {} · Revisión {} · CLI/MCP locales activos",
                p.project.camera.as_deref().or(p.project.window.as_ref().map(|w| w.title.as_str())).unwrap_or("patrón libobs"),
                p.project.audio,
                self.sequence,
                p.revision
            )))
            .child(div().flex_none().text_xs().text_color(rgb(0x9baabd)).child(format!(
                "Render: {} · Retrasados: {} · Pantalla: {} · Micrófono: {} · Cámara: {} · Nivel: {:.0}%",
                status["stats"]["rendered_frames"],
                status["stats"]["lagged_frames"],
                self.devices["screen_permission"],
                self.devices["microphone_permission"],
                self.devices["camera_permission"],
                status["stats"]["audio_peak"].as_f64().unwrap_or(0.) * 100.
            )))
    }
}
struct Pattern {
    tick: u64,
}
impl Pattern {
    fn new(cx: &mut Context<Self>) -> Self {
        cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor()
                    .timer(Duration::from_millis(100))
                    .await;
                if this
                    .update(cx, |v, cx| {
                        v.tick += 1;
                        cx.notify();
                    })
                    .is_err()
                {
                    break;
                }
            }
        })
        .detach();
        Self { tick: 0 }
    }
}
impl Render for Pattern {
    fn render(&mut self, _: &mut Window, _: &mut Context<Self>) -> impl IntoElement {
        div()
            .size_full()
            .flex()
            .flex_col()
            .p_8()
            .gap_6()
            .bg(rgb(0x162c40))
            .text_color(rgb(0xffffff))
            .child(div().text_3xl().child("MOTIVE / FUENTE CONTROLADA"))
            .child("Esta es una ventana nativa independiente. Captúrala desde el estudio.")
            .child(format!("Contenido de prueba propio · tick {}", self.tick))
            .child(div().flex().gap_4().children((0..5).map(|i| {
                div().w(px(76.)).h(px(76.)).bg(if self.tick % 5 == i {
                    rgb(0x64e4c1)
                } else {
                    rgb(0x315475)
                })
            })))
    }
}
fn window_options(title: &str, w: f32, h: f32, cx: &App) -> WindowOptions {
    WindowOptions {
        window_bounds: Some(WindowBounds::Windowed(Bounds::centered(
            None,
            size(px(w), px(h)),
            cx,
        ))),
        titlebar: Some(TitlebarOptions {
            title: Some(title.to_owned().into()),
            ..Default::default()
        }),
        ..Default::default()
    }
}
fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).is_some_and(|a| a == "mcp") {
        return control::run_mcp();
    }
    if args.get(1).is_some_and(|a| a == "ctl") {
        let command = serde_json::from_str(
            args.get(2)
                .map(String::as_str)
                .unwrap_or(r#"{"op":"status"}"#),
        )?;
        let response = control::send(command, "cli");
        println!("{}", serde_json::to_string_pretty(&response)?);
        if response["ok"] != true {
            std::process::exit(1);
        }
        return Ok(());
    }
    application().with_assets(assets::Assets).run(|cx| {
        init(cx);
        let setup = (|| -> anyhow::Result<_> {
            let (server, requests) = control::Server::start()?;
            let production = Production::new()?;
            Ok((production, server, requests))
        })();
        match setup {
            Ok((production, server, requests)) => {
                open_window(
                    window_options("Motive — Estudio local", 1160., 780., cx),
                    cx,
                    |window, cx| {
                        let view = cx.new(|cx| Studio::new(production, server, requests, cx));
                        let weak = view.downgrade();
                        window.on_window_should_close(cx, move |_, cx| {
                            let _ = weak.update(cx, |view, cx| {
                                if view.production.engine.output_state() != 0 {
                                    view.message = "Finaliza la salida antes de cerrar.".into();
                                    cx.notify();
                                } else {
                                    cx.quit();
                                }
                            });
                            false
                        });
                        view
                    },
                )
                .expect("No se pudo abrir Motive");
                cx.activate(true);
            }
            Err(e) => {
                eprintln!(
                    "{}",
                    json!({"ok":false,"error":{"code":"STARTUP_FAILED","message":e.to_string()}})
                );
                cx.quit();
            }
        }
    });
    Ok(())
}
