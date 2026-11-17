#[path = "../editor/mod.rs"]
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

mod audio;
mod chrome;
mod panels;
mod scenes;
mod sources;
mod workspace;
