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
    sync::Arc,
    time::{Duration, Instant},
};
pub struct Studio {
    pub(crate) production: Production,
    frame: Option<Arc<RenderImage>>,
    sequence: u64,
    _server: control::Server,
    pub(crate) message: String,
    devices: Value,
    last_device_refresh: Instant,
    picker: Option<&'static str>,
    selected_layer: Option<String>,
    dark: bool,
    panel: Option<Panel>,
    focus: FocusHandle,
    editor: editor::Editor,
    forms: forms::Forms,
    mixer_ui: audio::MixerUi,
    creative: creative::Creative,
    lifecycle: lifecycle::Lifecycle,
    recordings: recordings::RecordingsUi,
    destinations_ui: destinations::DestinationsUi,
    deck_ui: show_control::DeckUi,
    #[cfg(feature = "ui-profiler")]
    ui_profile: Option<profiling::Profile>,
}
impl Studio {
    pub fn new(
        production: Production,
        server: control::Server,
        requests: async_channel::Receiver<control::Request>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) -> Self {
        let devices = production.engine.devices();
        let prefs = super::preferences::Preferences::load();
        Palette::apply(prefs.dark, Some(window), cx);
        let editor = editor::Editor::new(window, cx);
        let forms = forms::Forms::new(window, cx);
        let destinations_ui = destinations::DestinationsUi::new(window, cx);
        // Control wakes the same foreground owner directly. Preview cadence is
        // not a control scheduler; Production and libobs keep their ownership.
        // Rules still advance only in the heartbeat below, including with no
        // MCP client. No second owner, media clock or automatic command retry.
        cx.spawn(async move |this, cx| {
            while let Ok(request) = requests.recv().await {
                if this
                    .update(cx, |view, cx| {
                        let result = view.command(request.command, request.origin, cx);
                        let _ = request.reply.send(result);
                    })
                    .is_err()
                {
                    break;
                }
            }
        })
        .detach();
        cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor()
                    .timer(Duration::from_millis(33))
                    .await;
                if this
                    .update(cx, |view, cx| {
                        #[cfg(feature = "ui-profiler")]
                        let profile_start = view.ui_profile.as_ref().map(|_| Instant::now());
                        #[cfg(feature = "ui-profiler")]
                        let profile_sequence = view.sequence;
                        if view.last_device_refresh.elapsed() >= Duration::from_secs(1) {
                            view.production.poll_health();
                            view.poll_creative_import(cx);
                            // Freeze choices while a picker is open: activating windows can
                            // reorder the OS inventory between pointer-down and pointer-up.
                            if view.picker.is_none() {
                                view.devices = view.production.engine.devices();
                            }
                            view.last_device_refresh = Instant::now();
                        }
                        // The scheduler runs once per owner heartbeat, never
                        // recursively from apply() or health polling.
                        view.production.poll_show_control();
                        if view.poll_lifecycle(cx) {
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
                        #[cfg(feature = "ui-profiler")]
                        if let (Some(profile), Some(start)) =
                            (view.ui_profile.as_mut(), profile_start)
                        {
                            profile.heartbeat(start.elapsed(), view.sequence != profile_sequence);
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
            _server: server,
            message: "Listo. La fuente y el overlay se componen en libobs.".into(),
            devices,
            last_device_refresh: Instant::now(),
            picker: None,
            selected_layer: None,
            dark: prefs.dark,
            panel: None,
            focus: cx.focus_handle(),
            editor,
            forms,
            mixer_ui: audio::MixerUi::default(),
            creative: creative::Creative::default(),
            lifecycle: lifecycle::Lifecycle::new(window.window_handle()),
            recordings: recordings::RecordingsUi::default(),
            destinations_ui,
            deck_ui: show_control::DeckUi::default(),
            #[cfg(feature = "ui-profiler")]
            ui_profile: profiling::Profile::new(window),
        }
    }
    fn command(&mut self, cmd: Command, origin: &str, cx: &mut Context<Self>) -> Value {
        let revision = self.production.revision;
        let requests_shutdown = matches!(cmd, Command::RequestShutdown);
        let preflight = matches!(cmd, Command::PreflightOutput { .. });
        let refresh_assets = matches!(
            &cmd,
            Command::Overlay(crate::core::overlays::OverlayCommand::RemoveAsset { .. })
        );
        let result = self.production.apply(cmd, origin);
        if requests_shutdown && result["ok"] == true {
            self.lifecycle.shutdown_waiting = true;
        }
        if result["ok"] != true {
            self.message = format!(
                "{} · {}",
                result["error"]["code"].as_str().unwrap_or("Error"),
                result["error"]["message"]
                    .as_str()
                    .unwrap_or("Operación rechazada")
            );
        } else if let Some(sequence) = result["result"]["saved_configuration"]["sequence"].as_u64()
        {
            self.message = format!("Configuración guardada · recibo {sequence}");
        } else if preflight {
            let warnings = result["preflight"]["warnings"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|warning| warning["message"].as_str())
                .collect::<Vec<_>>();
            self.message = if warnings.is_empty() {
                "Configuración válida. La comprobación no abre una conexión ni verifica el medio."
                    .into()
            } else {
                format!(
                    "Configuración válida con advertencia: {}",
                    warnings.join(" ")
                )
            };
        } else if self.production.revision != revision {
            self.message = self.production.last_action.clone();
        }
        if result["ok"] == true && self.production.revision != revision {
            // Query snapshots follow both UI and MCP writes; drafts retain their guard.
            self.refresh_profiles();
        }
        if origin == "UI" && self.forms.revision == revision {
            self.forms.revision = self.production.revision;
        }
        if refresh_assets && result["ok"] == true {
            self.refresh_assets();
        }
        cx.notify();
        result
    }
}

mod audio;
mod chrome;
mod creative;
mod panels;
mod scenes;
mod sources;
mod workspace;

mod configuration;
mod creator_packs;
mod destinations;
mod forms;
mod lifecycle;
mod outputs;
#[cfg(feature = "ui-profiler")]
mod profiling;
mod recordings;
mod show_control;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Panel {
    Project,
    Sources,
    Audio,
    Output,
    Agent,
    Layer,
    Profiles,
    Settings,
    Scenes,
    Creative,
    Recordings,
    Destinations,
    LiveDeck,
}
impl Panel {
    fn id(self) -> &'static str {
        match self {
            Self::Project => "project",
            Self::Sources => "add-source",
            Self::Audio => "audio",
            Self::Output => "output",
            Self::Agent => "agent",
            Self::Layer => "layer",
            Self::Profiles => "profiles",
            Self::Settings => "settings",
            Self::Scenes => "scenes",
            Self::Creative => "creative",
            Self::Recordings => "recordings",
            Self::Destinations => "destinations",
            Self::LiveDeck => "live-deck",
        }
    }
}

mod devices;
