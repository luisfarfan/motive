#[path = "output.rs"]
pub mod output;
use crate::{
    engine::Engine,
    scene::{
        Graph, Layer, Layouts, Recovery, Scene, SourceInput, SourceKind, Transform, VisualSource,
        valid_name,
    },
};
use output::{LocalEndpoint, OutputProfile, OutputTarget, ProfileStore};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};
pub fn data_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("var")
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Variant {
    Horizontal,
    Vertical,
}
/// Runtime recording preference, deliberately outside the v3 scene document.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RecordingEncoder {
    #[default]
    Auto,
    Videotoolbox,
    X264,
}
impl RecordingEncoder {
    #[cfg(test)]
    fn as_str(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::Videotoolbox => "videotoolbox",
            Self::X264 => "x264",
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Status,
    Devices,
    Encoders,
    OutputCapabilities,
    OutputProfiles,
    UpsertOutputProfile {
        profile: OutputProfile,
    },
    RemoveOutputProfile {
        id: String,
    },
    SelectOutputProfile {
        target: OutputTarget,
        profile_id: String,
    },
    SaveOutputProfiles,
    LoadOutputProfiles,
    ConfigureStream {
        endpoint: LocalEndpoint,
    },
    PreflightOutput {
        target: OutputTarget,
    },
    StartStream,
    RecoverOutput,
    SetEncoder {
        encoder: RecordingEncoder,
    },
    SetOverlay {
        visible: bool,
    },
    SetVariant {
        variant: Variant,
    },
    SelectSource {
        window_id: Option<u32>,
    },
    SelectAudio {
        id: String,
    },
    SelectCamera {
        id: String,
    },
    ReconnectSources,
    StartRecording,
    StartLocalStream,
    StopOutput,
    SaveProject,
    LoadProject,
    Snapshot,
    CreateScene {
        name: String,
    },
    RenameScene {
        scene_id: String,
        name: String,
    },
    RemoveScene {
        scene_id: String,
    },
    SelectScene {
        scene_id: String,
    },
    AddSource {
        scene_id: String,
        name: String,
        source: SourceInput,
    },
    RemoveSource {
        source_id: String,
    },
    AddLayer {
        scene_id: String,
        source_id: String,
    },
    RemoveLayer {
        scene_id: String,
        layer_id: String,
    },
    SetTransform {
        scene_id: String,
        layer_id: String,
        variant: Variant,
        transform: Transform,
    },
    SetOverlayColor {
        source_id: String,
        color: u32,
    },
    ReconnectSource {
        source_id: String,
    },
    Shutdown,
    SetTestWindow {
        open: bool,
    },
}
fn same_shape(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, v)| b.get(k).is_some_and(|b| same_shape(v, b)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| same_shape(a, b))
        }
        _ => true,
    }
}
pub fn parse_command(value: Value) -> anyhow::Result<Command> {
    let command: Command = serde_json::from_value(value.clone())?;
    anyhow::ensure!(
        same_shape(&value, &serde_json::to_value(&command)?),
        "Unexpected or missing command fields"
    );
    Ok(command)
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Project {
    pub version: u32,
    pub variant: Variant,
    pub overlay: bool,
    pub audio: String,
    pub capture_window: bool,
    #[serde(default)]
    pub window: Option<WindowIdentity>,
    #[serde(default)]
    pub camera: Option<String>,
    #[serde(default)]
    pub graph: Option<Graph>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WindowIdentity {
    pub bundle_id: String,
    pub title: String,
}
impl Default for Project {
    fn default() -> Self {
        Self {
            version: 3,
            variant: Variant::Horizontal,
            overlay: true,
            audio: "none".into(),
            capture_window: false,
            window: None,
            camera: None,
            graph: Some(Graph::default()),
        }
    }
}
#[derive(Clone, Debug)]
struct WindowBinding {
    id: u32,
    pid: i32,
}
pub struct Production {
    pub engine: Engine,
    profiles: ProfileStore,
    recording_profile: String,
    streaming_profile: String,
    stream_endpoint: Option<LocalEndpoint>,
    pub project: Project,
    pub revision: u64,
    pub last_action: String,
    pub output_kind: String,
    pub output_path: Option<String>,
    pub stopping: bool,
    pub window_id: Option<u32>,
    pub issues: Vec<String>,
    pub recovery: Recovery,
    pub last_fault: Vec<String>,
    pub source_health: Value,
    bindings: BTreeMap<String, WindowBinding>,
    awaiting_recovery: BTreeSet<String>,
    seen_output_error: i32,
    pub shutdown_requested: bool,
    pub test_window_request: Option<bool>,
}
pub fn error(code: &str, message: impl ToString) -> Value {
    json!({"ok":false,"error":{"code":code,"message":message.to_string()}})
}
impl Production {
    pub fn new() -> anyhow::Result<Self> {
        fs::create_dir_all(data_dir().join("recordings"))?;
        fs::create_dir_all(data_dir().join("evidence"))?;
        create_tone()?;
        let mut p = Self {
            engine: Engine::new()?,
            profiles: ProfileStore::default(),
            recording_profile: "standard".into(),
            streaming_profile: "standard".into(),
            stream_endpoint: None,
            project: Project::default(),
            revision: 0,
            last_action: "Estudio iniciado".into(),
            output_kind: "idle".into(),
            output_path: None,
            stopping: false,
            window_id: None,
            issues: vec![],
            recovery: Recovery::default(),
            last_fault: vec![],
            source_health: json!([]),
            bindings: BTreeMap::new(),
            awaiting_recovery: BTreeSet::new(),
            seen_output_error: 0,
            shutdown_requested: false,
            test_window_request: None,
        };
        p.sync(p.graph().clone(), p.bindings.clone(), "")?;
        Ok(p)
    }
    pub fn graph(&self) -> &Graph {
        self.project.graph.as_ref().expect("validated graph")
    }
    pub fn status(&self) -> Value {
        let state = self.engine.output_state();
        let output = if state == 0 && self.engine.output_code() != 0 {
            "error"
        } else if state == 0 {
            "idle"
        } else if self.stopping {
            "stopping"
        } else if state == 3 {
            "connecting"
        } else {
            &self.output_kind
        };
        json!({"pid":std::process::id(),"revision":self.revision,"project":self.project,"encoding":self.encoding_status(),"output_configuration":self.output_configuration(),"issues":self.issues,
            "recovery_required":self.recovery.required(),"recovery_sources":self.recovery.pending,"last_fault":self.last_fault,
            "sources":self.source_health,"window_id":self.window_id,"output":output,"output_code":self.engine.output_code(),
            "output_failure":output_failure(self.engine.output_code()),"output_path":self.output_path,"last_action":self.last_action,"libobs":self.engine.version(),"width":self.engine.width,"height":self.engine.height,"fps":30,"stats":self.engine.stats()})
    }
    fn encoding_status(&self) -> Value {
        let mut value = self.engine.encoding_info();
        value["preference"] = json!(self.profile(OutputTarget::Recording).encoder);
        value["scope"] = json!("selected_recording_profile");
        value
    }
    fn profile(&self, target: OutputTarget) -> &OutputProfile {
        let id = match target {
            OutputTarget::Recording => &self.recording_profile,
            OutputTarget::Streaming => &self.streaming_profile,
        };
        self.profiles.get(id).expect("validated active profile")
    }
    fn output_configuration(&self) -> Value {
        json!({"recording_profile":self.recording_profile,"streaming_profile":self.streaming_profile,
            "recording":self.profile(OutputTarget::Recording),"streaming":self.profile(OutputTarget::Streaming),
            "endpoint":self.stream_endpoint,"credentials_supported":false,"automatic_reconnect":false})
    }
    fn output_capabilities(&self) -> Value {
        json!({"encoders":self.engine.encoding_info(),"rate_controls":["cbr"],"bitrate_kbps":{"min":250,"max":20000},
            "keyframe_seconds":{"min":1,"max":10},"frame_reordering":[true,false],
            "canvas":{"width":self.engine.width,"height":self.engine.height,"fps":30,
                "variants":[{"width":960,"height":540},{"width":540,"height":960}],
                "profile_resolution_configurable":false,"fps_configurable":false},
            "audio":{"codec":"aac","bitrate_kbps":160,"sample_rate":48000,"channels":2},
            "streaming":{"host":"127.0.0.1","port_min":1024,"path":"/live/motive","transport":["rtmp","rtmps"],
                "rtmps_validation":"system_trust_required; trusted media delivery not yet verified",
                "credentials_supported":false,"public_destinations":false},"simultaneous_outputs":1,"cancel_connecting_supported":false})
    }
    fn preflight(&self, target: OutputTarget) -> anyhow::Result<()> {
        self.idle()?;
        self.source_ready()?;
        let p = self.profile(target);
        p.validate()?;
        if p.encoder == RecordingEncoder::Videotoolbox {
            anyhow::ensure!(
                self.engine.encoding_info()["videotoolbox_id"].is_string(),
                "ENCODER_UNAVAILABLE"
            );
        }
        if target == OutputTarget::Streaming {
            self.stream_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("ENDPOINT_REQUIRED"))?
                .validate()?;
            anyhow::ensure!(
                self.engine.encoding_info()["rtmp_available"] == true,
                "SERVICE_UNAVAILABLE"
            );
        }
        Ok(())
    }
    fn faults(&self) -> Vec<(String, String)> {
        self.faults_from(&self.engine.graph_health())
    }
    fn faults_from(&self, health: &Value) -> Vec<(String, String)> {
        let mut result: Vec<_> = health
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|s| {
                let code = s["issue"].as_str()?;
                (!code.is_empty()).then(|| (s["id"].as_str().unwrap_or("").into(), code.into()))
            })
            .collect();
        if let Some(code) = match self.engine.audio_health() {
            1 => Some("DEVICE_UNAVAILABLE"),
            2 => Some("MICROPHONE_PERMISSION_DENIED"),
            3 => Some("AUDIO_NOT_READY"),
            _ => None,
        } {
            result.push(("audio".into(), code.into()));
        }
        result
    }
    pub fn poll_health(&mut self) {
        self.source_health = self.engine.graph_health();
        let faults = self.faults_from(&self.source_health);
        self.issues = faults.iter().map(|(_, c)| c.clone()).collect();
        if !faults.is_empty() && self.engine.output_state() != 0 && !self.stopping {
            self.engine.stop_output();
            self.stopping = true;
            self.recovery
                .pending
                .extend(faults.iter().map(|(id, _)| id.clone()));
            self.last_fault = self.issues.clone();
            self.revision += 1;
            self.last_action = format!(
                "Fuente perdida: {}. Salida finalizando.",
                self.issues.join(", ")
            );
        }
        if self.stopping && self.engine.output_state() == 1 {
            self.engine.stop_output();
        }
        let output_error = self.engine.output_code();
        if output_error != 0 && output_error != self.seen_output_error {
            self.stopping = self.engine.output_state() != 0;
            self.recovery.pending.insert("output".into());
            self.last_fault.push("OUTPUT_FAILED".into());
            self.revision += 1;
            self.last_action = format!(
                "OUTPUT_FAILED: código {output_error}; reconecta antes de volver a iniciar"
            );
        }
        self.seen_output_error = output_error;
        let ready: Vec<_> = self
            .awaiting_recovery
            .iter()
            .filter(|id| !faults.iter().any(|(source, _)| source == *id))
            .cloned()
            .collect();
        for id in ready {
            self.recovery.resolve(&id);
            self.awaiting_recovery.remove(&id);
        }
    }
    fn idle(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.engine.output_state() == 0,
            "OUTPUT_BUSY: espera la finalización de la salida"
        );
        Ok(())
    }
    fn source_ready(&self) -> anyhow::Result<()> {
        let faults = self.faults();
        anyhow::ensure!(
            faults.is_empty(),
            "{}: muestra la ventana o revisa la fuente y espera datos",
            faults
                .first()
                .map(|(_, code)| code.as_str())
                .unwrap_or("SOURCE_UNAVAILABLE")
        );
        anyhow::ensure!(
            !self.recovery.required(),
            "RECOVERY_REQUIRED: recupera las fuentes afectadas"
        );
        anyhow::ensure!(
            self.graph()
                .scene(&self.graph().active_scene)?
                .layers
                .iter()
                .any(|l| l.layouts.get(self.project.variant).visible),
            "EMPTY_SCENE"
        );
        Ok(())
    }
    fn audio(&mut self, id: &str) -> anyhow::Result<()> {
        anyhow::ensure!(
            !id.is_empty() && id.len() < 512 && !id.contains('\0'),
            "INVALID_ARGUMENT: audio inválido"
        );
        if id != self.project.audio || self.engine.audio_health() != 0 {
            self.engine
                .audio(id, &data_dir().join("tone.wav").to_string_lossy())?;
            self.project.audio = id.into();
        }
        // A changed microphone cannot acknowledge a failed visual source.
        self.awaiting_recovery.insert("audio".into());
        Ok(())
    }
    fn native_graph(
        graph: &Graph,
        bindings: &BTreeMap<String, WindowBinding>,
    ) -> anyhow::Result<Value> {
        let mut value = serde_json::to_value(graph)?;
        for source in value["sources"].as_array_mut().unwrap() {
            if source["spec"]["kind"] == "window" {
                let b = bindings
                    .get(source["id"].as_str().unwrap())
                    .ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE: missing window binding"))?;
                source["window_id"] = json!(b.id);
                source["owner_pid"] = json!(b.pid);
            }
        }
        Ok(value)
    }
    fn sync(
        &mut self,
        graph: Graph,
        bindings: BTreeMap<String, WindowBinding>,
        reconnect: &str,
    ) -> anyhow::Result<()> {
        graph.validate()?;
        self.engine
            .sync_graph(&Self::native_graph(&graph, &bindings)?, reconnect)?;
        self.project.graph = Some(graph);
        self.bindings = bindings;
        self.project.version = 3;
        self.update_legacy();
        Ok(())
    }
    fn update_legacy(&mut self) {
        let spec = self
            .graph()
            .sources
            .iter()
            .find(|s| s.id == "main")
            .map(|s| s.spec.clone());
        self.project.capture_window = matches!(spec, Some(SourceKind::Window { .. }));
        self.project.window = if let Some(SourceKind::Window { window }) = &spec {
            Some(window.clone())
        } else {
            None
        };
        self.project.camera = if let Some(SourceKind::Camera { device_id }) = &spec {
            Some(device_id.clone())
        } else {
            None
        };
        self.window_id = self
            .bindings
            .get("main")
            .map(|b| b.id)
            .filter(|_| self.project.capture_window);
        self.project.overlay = self
            .graph()
            .scene(&self.graph().active_scene)
            .unwrap()
            .layers
            .iter()
            .any(|l| l.source_id == "overlay" && l.layouts.get(self.project.variant).visible);
    }
    fn binding(devices: &Value, id: u32) -> anyhow::Result<(WindowIdentity, WindowBinding)> {
        let identity =
            window_identity(devices, id).ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE"))?;
        let w = devices["windows"]
            .as_array()
            .unwrap()
            .iter()
            .find(|w| w["id"] == id)
            .unwrap();
        Ok((
            identity,
            WindowBinding {
                id,
                pid: w["pid"].as_i64().unwrap_or(0) as i32,
            },
        ))
    }
    fn input(
        &self,
        input: SourceInput,
        bindings: &mut BTreeMap<String, WindowBinding>,
        id: &str,
    ) -> anyhow::Result<SourceKind> {
        Ok(match input {
            SourceInput::Pattern => SourceKind::Pattern,
            SourceInput::Overlay { color } => SourceKind::Overlay { color },
            SourceInput::Camera { device_id } => SourceKind::Camera { device_id },
            SourceInput::Window { window_id } => {
                let (window, b) = Self::binding(&self.engine.devices(), window_id)?;
                bindings.insert(id.into(), b);
                SourceKind::Window { window }
            }
        })
    }
    fn legacy_source(&mut self, input: SourceInput) -> anyhow::Result<()> {
        self.idle()?;
        let mut graph = self.graph().clone();
        let mut bindings = self.bindings.clone();
        bindings.remove("main");
        let spec = self.input(input, &mut bindings, "main")?;
        if let Some(source) = graph.sources.iter_mut().find(|s| s.id == "main") {
            source.spec = spec;
        } else {
            graph.sources.push(VisualSource {
                id: "main".into(),
                name: "Principal".into(),
                spec,
            });
        }
        let scene = graph.active_scene.clone();
        if !graph
            .scene(&scene)?
            .layers
            .iter()
            .any(|l| l.source_id == "main")
        {
            let id = graph.id("layer");
            graph.scene_mut(&scene)?.layers.push(Layer {
                id,
                source_id: "main".into(),
                layouts: Layouts::full(),
            });
        }
        self.sync(graph, bindings, "")?;
        self.awaiting_recovery.insert("main".into());
        Ok(())
    }
    fn apply_project(&mut self, mut p: Project) -> anyhow::Result<()> {
        self.idle()?;
        anyhow::ensure!((1..=3).contains(&p.version), "PROJECT_VERSION_UNSUPPORTED");
        let devices = self.engine.devices();
        let mut bindings = BTreeMap::new();
        let graph = if p.version < 3 {
            anyhow::ensure!(!(p.capture_window && p.camera.is_some()), "INVALID_PROJECT");
            let mut g = Graph::default();
            if p.capture_window {
                let id = resolve_window(&p, &devices)?;
                let (window, b) = Self::binding(&devices, id)?;
                bindings.insert("main".into(), b);
                g.sources[0].spec = SourceKind::Window { window };
            } else if let Some(id) = &p.camera {
                g.sources[0].spec = SourceKind::Camera {
                    device_id: id.clone(),
                };
            }
            g.scenes[0].layers[1].layouts.horizontal.visible = p.overlay;
            g.scenes[0].layers[1].layouts.vertical.visible = p.overlay;
            g
        } else {
            p.graph
                .take()
                .ok_or_else(|| anyhow::anyhow!("INVALID_PROJECT: graph required"))?
        };
        graph.validate()?;
        for source in &graph.sources {
            if let SourceKind::Window { window } = &source.spec {
                if bindings.contains_key(&source.id) {
                    continue;
                }
                let lookup = Project {
                    version: 2,
                    capture_window: true,
                    window: Some(window.clone()),
                    ..Project::default()
                };
                let id = resolve_window(&lookup, &devices)?;
                bindings.insert(source.id.clone(), Self::binding(&devices, id)?.1);
            }
        }
        let old = self.project.clone();
        let old_bindings = self.bindings.clone();
        let result = (|| {
            self.engine.variant(p.variant == Variant::Vertical)?;
            self.audio(&p.audio)?;
            self.project.variant = p.variant;
            self.sync(graph, bindings, "")?;
            Ok::<_, anyhow::Error>(())
        })();
        if let Err(failure) = result {
            let rollback = (|| {
                self.engine.variant(old.variant == Variant::Vertical)?;
                self.audio(&old.audio)?;
                self.project.variant = old.variant;
                self.sync(old.graph.clone().unwrap(), old_bindings, "")?;
                Ok::<_, anyhow::Error>(())
            })();
            self.project = old;
            return Err(match rollback {
                Ok(()) => failure,
                Err(e) => anyhow::anyhow!("ROLLBACK_FAILED: {failure}; {e}"),
            });
        }
        // Loading a project is not a blanket acknowledgement of unresolved faults.
        self.awaiting_recovery.extend(
            self.graph()
                .sources
                .iter()
                .map(|s| s.id.clone())
                .collect::<Vec<_>>(),
        );
        Ok(())
    }
    fn graph_command(&mut self, command: Command) -> anyhow::Result<()> {
        let mut graph = self.graph().clone();
        let mut bindings = self.bindings.clone();
        match command {
            Command::CreateScene { name } => {
                self.idle()?;
                anyhow::ensure!(valid_name(&name), "INVALID_NAME");
                let id = graph.id("scene");
                graph.scenes.push(Scene {
                    id: id.clone(),
                    name,
                    layers: vec![],
                });
                graph.active_scene = id;
            }
            Command::RenameScene { scene_id, name } => {
                anyhow::ensure!(valid_name(&name), "INVALID_NAME");
                graph.scene_mut(&scene_id)?.name = name;
            }
            Command::RemoveScene { scene_id } => {
                self.idle()?;
                graph.scene(&scene_id)?;
                anyhow::ensure!(graph.scenes.len() > 1, "LAST_SCENE");
                graph.scenes.retain(|s| s.id != scene_id);
                if graph.active_scene == scene_id {
                    graph.active_scene = graph.scenes[0].id.clone();
                }
            }
            Command::SelectScene { scene_id } => {
                self.idle()?;
                graph.scene(&scene_id)?;
                graph.active_scene = scene_id;
            }
            Command::AddSource {
                scene_id,
                name,
                source,
            } => {
                self.idle()?;
                anyhow::ensure!(valid_name(&name), "INVALID_NAME");
                graph.scene(&scene_id)?;
                let id = graph.id("source");
                let spec = self.input(source, &mut bindings, &id)?;
                let overlay = matches!(spec, SourceKind::Overlay { .. });
                graph.sources.push(VisualSource {
                    id: id.clone(),
                    name,
                    spec,
                });
                let layer = graph.id("layer");
                let layouts = if overlay {
                    Layouts::overlay()
                } else if graph.scene(&scene_id)?.layers.is_empty() {
                    Layouts::full()
                } else {
                    Layouts::secondary()
                };
                graph.scene_mut(&scene_id)?.layers.push(Layer {
                    id: layer,
                    source_id: id,
                    layouts,
                });
            }
            Command::RemoveSource { source_id } => {
                self.idle()?;
                anyhow::ensure!(
                    graph.sources.iter().any(|s| s.id == source_id),
                    "SOURCE_UNAVAILABLE"
                );
                anyhow::ensure!(
                    !graph
                        .scenes
                        .iter()
                        .any(|s| s.layers.iter().any(|l| l.source_id == source_id)),
                    "SOURCE_IN_USE"
                );
                graph.sources.retain(|s| s.id != source_id);
                bindings.remove(&source_id);
            }
            Command::AddLayer {
                scene_id,
                source_id,
            } => {
                self.idle()?;
                anyhow::ensure!(
                    graph.sources.iter().any(|s| s.id == source_id),
                    "SOURCE_UNAVAILABLE"
                );
                let id = graph.id("layer");
                graph.scene_mut(&scene_id)?.layers.push(Layer {
                    id,
                    source_id,
                    layouts: Layouts::secondary(),
                });
            }
            Command::RemoveLayer { scene_id, layer_id } => {
                self.idle()?;
                let scene = graph.scene_mut(&scene_id)?;
                anyhow::ensure!(
                    scene.layers.iter().any(|l| l.id == layer_id),
                    "LAYER_UNAVAILABLE"
                );
                scene.layers.retain(|l| l.id != layer_id);
            }
            Command::SetTransform {
                scene_id,
                layer_id,
                variant,
                transform,
            } => {
                transform.validate()?;
                let layer = graph
                    .scene_mut(&scene_id)?
                    .layers
                    .iter_mut()
                    .find(|l| l.id == layer_id)
                    .ok_or_else(|| anyhow::anyhow!("LAYER_UNAVAILABLE"))?;
                // Geometry/order edits work during recording. Activation changes must be idle so a cold source cannot enter live output.
                if layer.layouts.get(variant).visible != transform.visible {
                    self.idle()?;
                }
                *layer.layouts.get_mut(variant) = transform;
            }
            Command::SetOverlayColor { source_id, color } => {
                anyhow::ensure!(color <= 0xffffff, "INVALID_COLOR");
                let s = graph
                    .sources
                    .iter_mut()
                    .find(|s| s.id == source_id)
                    .ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE"))?;
                anyhow::ensure!(
                    matches!(s.spec, SourceKind::Overlay { .. }),
                    "SOURCE_KIND_MISMATCH"
                );
                s.spec = SourceKind::Overlay { color };
            }
            _ => unreachable!(),
        }
        self.sync(graph, bindings, "")?;
        let relevant: BTreeSet<_> = self
            .graph()
            .scene(&self.graph().active_scene)?
            .layers
            .iter()
            .filter(|l| l.layouts.get(self.project.variant).visible)
            .map(|l| l.source_id.clone())
            .collect();
        self.recovery
            .pending
            .retain(|id| id == "audio" || id == "output" || relevant.contains(id));
        Ok(())
    }
    pub fn apply(&mut self, command: Command, origin: &str) -> Value {
        self.poll_health();
        if matches!(command, Command::Status) {
            return json!({"ok":true,"state":self.status()});
        }
        if matches!(command, Command::Devices) {
            return json!({"ok":true,"devices":self.engine.devices()});
        }
        if matches!(command, Command::Encoders) {
            return json!({"ok":true,"encoders":self.encoding_status()});
        }
        if matches!(command, Command::OutputCapabilities) {
            return json!({"ok":true,"capabilities":self.output_capabilities()});
        }
        if matches!(command, Command::OutputProfiles) {
            return json!({"ok":true,"store":self.profiles,"configuration":self.output_configuration()});
        }
        if let Command::PreflightOutput { target } = command {
            return match self.preflight(target) {
                Ok(()) => {
                    json!({"ok":true,"preflight":{"ready":true,"target":target,"profile":self.profile(target),
                    "configuration":self.output_configuration(),"network_tested":false,"encoder_initialized":false}})
                }
                Err(e) => command_error(e),
            };
        }
        let label = serde_json::to_value(&command).unwrap()["op"]
            .as_str()
            .unwrap()
            .to_owned();
        let result = (|| -> anyhow::Result<()> {
            match command {
                Command::SetEncoder { encoder } => {
                    self.idle()?;
                    if encoder == RecordingEncoder::Videotoolbox {
                        anyhow::ensure!(
                            self.engine.encoding_info()["videotoolbox_id"].is_string(),
                            "ENCODER_UNAVAILABLE: VideoToolbox hardware is not registered"
                        );
                    }
                    let mut p = self.profile(OutputTarget::Recording).clone();
                    p.encoder = encoder;
                    self.profiles.upsert(p)?;
                }
                Command::UpsertOutputProfile { profile } => {
                    self.idle()?;
                    self.profiles.upsert(profile)?;
                }
                Command::RemoveOutputProfile { id } => {
                    self.idle()?;
                    self.profiles.get(&id)?;
                    anyhow::ensure!(
                        id != self.recording_profile && id != self.streaming_profile,
                        "PROFILE_IN_USE"
                    );
                    self.profiles.profiles.retain(|p| p.id != id);
                }
                Command::SelectOutputProfile { target, profile_id } => {
                    self.idle()?;
                    self.profiles.get(&profile_id)?;
                    match target {
                        OutputTarget::Recording => self.recording_profile = profile_id,
                        OutputTarget::Streaming => self.streaming_profile = profile_id,
                    };
                }
                Command::ConfigureStream { endpoint } => {
                    self.idle()?;
                    endpoint.validate()?;
                    self.stream_endpoint = Some(endpoint);
                }
                Command::SaveOutputProfiles => {
                    use std::{io::Write, os::unix::fs::OpenOptionsExt};
                    let path = data_dir().join("output-profiles.json");
                    let temp = path.with_extension("json.tmp");
                    let mut f = fs::OpenOptions::new()
                        .write(true)
                        .create(true)
                        .truncate(true)
                        .mode(0o600)
                        .open(&temp)?;
                    f.write_all(&serde_json::to_vec_pretty(&self.profiles)?)?;
                    f.sync_all()?;
                    fs::rename(temp, path)?;
                }
                Command::LoadOutputProfiles => {
                    use std::io::Read;
                    self.idle()?;
                    let mut bytes = vec![];
                    fs::File::open(data_dir().join("output-profiles.json"))?
                        .take(65537)
                        .read_to_end(&mut bytes)?;
                    anyhow::ensure!(bytes.len() <= 65536, "PROFILES_TOO_LARGE");
                    let profiles: ProfileStore = serde_json::from_slice(&bytes)
                        .map_err(|_| anyhow::anyhow!("INVALID_PROFILES"))?;
                    profiles.validate()?;
                    if profiles.get(&self.recording_profile).is_err() {
                        self.recording_profile = profiles.profiles[0].id.clone();
                    }
                    if profiles.get(&self.streaming_profile).is_err() {
                        self.streaming_profile = profiles.profiles[0].id.clone();
                    }
                    self.profiles = profiles;
                }
                Command::StartStream => {
                    self.preflight(OutputTarget::Streaming)?;
                    self.engine.start_stream(
                        &self.stream_endpoint.as_ref().unwrap().url(),
                        &serde_json::to_string(self.profile(OutputTarget::Streaming))?,
                    )?;
                    self.output_kind = "streaming".into();
                    self.output_path = None;
                    self.stopping = false;
                }
                Command::RecoverOutput => {
                    self.idle()?;
                    self.engine.reset_output()?;
                    self.recovery.resolve("output");
                }
                Command::SetOverlay { visible } => {
                    let mut graph = self.graph().clone();
                    let scene = graph.active_scene.clone();
                    let l = graph
                        .scene_mut(&scene)?
                        .layers
                        .iter_mut()
                        .find(|l| l.source_id == "overlay")
                        .ok_or_else(|| anyhow::anyhow!("LAYER_UNAVAILABLE"))?;
                    l.layouts.get_mut(self.project.variant).visible = visible;
                    self.sync(graph, self.bindings.clone(), "")?;
                }
                Command::SetVariant { variant } => {
                    self.idle()?;
                    let old = self.project.variant;
                    self.engine.variant(variant == Variant::Vertical)?;
                    self.project.variant = variant;
                    if let Err(e) = self.sync(self.graph().clone(), self.bindings.clone(), "") {
                        self.engine.variant(old == Variant::Vertical)?;
                        self.project.variant = old;
                        self.sync(self.graph().clone(), self.bindings.clone(), "")?;
                        return Err(e);
                    }
                }
                Command::SelectSource { window_id } => {
                    self.legacy_source(window_id.map_or(SourceInput::Pattern, |window_id| {
                        SourceInput::Window { window_id }
                    }))?
                }
                Command::SelectCamera { id } => {
                    self.legacy_source(SourceInput::Camera { device_id: id })?
                }
                Command::SelectAudio { id } => {
                    self.idle()?;
                    self.audio(&id)?;
                }
                Command::ReconnectSource { source_id } => {
                    self.idle()?;
                    anyhow::ensure!(
                        self.graph().sources.iter().any(|s| s.id == source_id),
                        "SOURCE_UNAVAILABLE"
                    );
                    self.sync(self.graph().clone(), self.bindings.clone(), &source_id)?;
                    self.awaiting_recovery.insert(source_id);
                }
                Command::ReconnectSources => {
                    self.idle()?;
                    self.sync(self.graph().clone(), self.bindings.clone(), "*")?;
                    self.engine.audio(
                        &self.project.audio,
                        &data_dir().join("tone.wav").to_string_lossy(),
                    )?;
                    self.engine.reset_output()?;
                    self.recovery.resolve("output");
                    self.awaiting_recovery.extend(
                        self.graph()
                            .sources
                            .iter()
                            .map(|s| s.id.clone())
                            .collect::<Vec<_>>(),
                    );
                    self.awaiting_recovery.insert("audio".into());
                }
                Command::StartRecording => {
                    self.idle()?;
                    self.preflight(OutputTarget::Recording)?;
                    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
                    let path = data_dir()
                        .join("recordings")
                        .join(format!("motive-{stamp}.mkv"));
                    fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(&path)?;
                    if let Err(e) = self.engine.start_output(
                        &path.to_string_lossy(),
                        false,
                        &serde_json::to_string(self.profile(OutputTarget::Recording))?,
                    ) {
                        if fs::metadata(&path).is_ok_and(|m| m.len() == 0) {
                            let _ = fs::remove_file(&path);
                        }
                        return Err(e);
                    }
                    self.output_kind = "recording".into();
                    self.output_path = Some(path.to_string_lossy().into_owned());
                    self.stopping = false;
                }
                Command::StartLocalStream => {
                    self.idle()?;
                    self.source_ready()?;
                    self.engine.start_output(
                        "",
                        true,
                        &serde_json::to_string(self.profile(OutputTarget::Recording))?,
                    )?;
                    self.output_kind = "local_stream".into();
                    self.output_path = None;
                    self.stopping = false;
                }
                Command::StopOutput => {
                    anyhow::ensure!(
                        self.engine.output_state() != 3,
                        "OUTPUT_CONNECTING: OBS 33.0.1 cannot safely cancel its handshake; wait for connection result, then stop or recover"
                    );
                    self.engine.stop_output();
                    self.stopping = self.engine.output_state() != 0;
                }
                Command::SaveProject => {
                    let path = data_dir().join("project.json");
                    let temp = path.with_extension("json.tmp");
                    let bytes = serde_json::to_vec_pretty(&self.project)?;
                    use std::io::Write;
                    let mut file = fs::File::create(&temp)?;
                    file.write_all(&bytes)?;
                    file.sync_all()?;
                    fs::rename(temp, path)?;
                }
                Command::LoadProject => {
                    let file = fs::File::open(data_dir().join("project.json"))?;
                    use std::io::Read;
                    let mut bytes = vec![];
                    file.take(65537).read_to_end(&mut bytes)?;
                    anyhow::ensure!(bytes.len() <= 65536, "PROJECT_TOO_LARGE");
                    self.apply_project(parse_project(&bytes)?)?;
                }
                Command::Snapshot => {
                    let (seq, _, mut pixels) = self.engine.frame();
                    anyhow::ensure!(seq > 0, "PREVIEW_NOT_READY");
                    for p in pixels.as_chunks_mut::<4>().0 {
                        p.swap(0, 2);
                    }
                    image::save_buffer(
                        data_dir().join("evidence/preview.png"),
                        &pixels,
                        self.engine.width,
                        self.engine.height,
                        image::ColorType::Rgba8,
                    )?;
                }
                Command::Shutdown => {
                    self.idle()?;
                    self.shutdown_requested = true;
                }
                Command::SetTestWindow { open } => {
                    self.test_window_request = Some(open);
                }
                Command::Status
                | Command::Devices
                | Command::Encoders
                | Command::OutputCapabilities
                | Command::OutputProfiles
                | Command::PreflightOutput { .. } => unreachable!(),
                graph_command => self.graph_command(graph_command)?,
            }
            Ok(())
        })();
        match result {
            Ok(()) => {
                self.poll_health();
                self.revision += 1;
                self.last_action = format!("{origin} · {label} · revisión {}", self.revision);
                json!({"ok":true,"state":self.status()})
            }
            Err(e) => command_error(e),
        }
    }
}
fn output_failure(code: i32) -> Value {
    if code == 0 {
        return Value::Null;
    }
    let name = match code {
        -1 => "OUTPUT_BAD_PATH",
        -2 => "OUTPUT_CONNECT_FAILED",
        -3 => "OUTPUT_INVALID_STREAM",
        -5 => "OUTPUT_DISCONNECTED",
        -6 => "OUTPUT_UNSUPPORTED",
        -7 => "OUTPUT_NO_SPACE",
        -8 => "OUTPUT_ENCODE_ERROR",
        -9 => "OUTPUT_HDR_DISABLED",
        _ => "OUTPUT_FAILED",
    };
    json!({"code":name,"native_code":code,"recovery":"explicit"})
}
fn command_error(e: anyhow::Error) -> Value {
    let msg = e.to_string();
    let prefix = msg.split(':').next().unwrap_or("");
    let code = if !prefix.is_empty() && prefix.chars().all(|c| c.is_ascii_uppercase() || c == '_') {
        prefix
    } else {
        "OPERATION_FAILED"
    };
    error(code, msg.as_str())
}
fn parse_project(bytes: &[u8]) -> anyhow::Result<Project> {
    let value: Value = serde_json::from_slice(bytes)?;
    let project: Project = serde_json::from_value(value.clone())?;
    if value["graph"].is_object() {
        anyhow::ensure!(
            same_shape(&value["graph"], &serde_json::to_value(&project.graph)?),
            "INVALID_PROJECT: unexpected graph fields"
        );
    }
    Ok(project)
}
fn window_identity(devices: &Value, id: u32) -> Option<WindowIdentity> {
    let w = devices["windows"]
        .as_array()?
        .iter()
        .find(|w| w["id"] == id)?;
    Some(WindowIdentity {
        bundle_id: w["bundle_id"].as_str()?.into(),
        title: w["name"].as_str()?.into(),
    })
}
fn resolve_window(p: &Project, devices: &Value) -> anyhow::Result<u32> {
    let matches: Vec<_> = devices["windows"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|w| {
            if p.version == 1 {
                return w["test"] == true;
            }
            p.window.as_ref().is_some_and(|identity| {
                !identity.bundle_id.is_empty()
                    && w["bundle_id"] == identity.bundle_id
                    && w["name"] == identity.title
            })
        })
        .collect();
    anyhow::ensure!(
        !matches.is_empty(),
        "SOURCE_UNAVAILABLE: vuelve a seleccionar la ventana"
    );
    anyhow::ensure!(
        matches.len() == 1,
        "SOURCE_AMBIGUOUS: selecciona explícitamente una ventana"
    );
    Ok(matches[0]["id"]
        .as_u64()
        .ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE"))? as u32)
}

fn create_tone() -> anyhow::Result<()> {
    // Owned 440 Hz stereo PCM fixture at -24 dBFS. No microphone or output monitoring.
    let samples = 48000u32;
    let bytes = samples * 4;
    let mut wav = Vec::with_capacity(bytes as usize + 44);
    wav.extend(b"RIFF");
    wav.extend((36 + bytes).to_le_bytes());
    wav.extend(b"WAVEfmt ");
    wav.extend(16u32.to_le_bytes());
    wav.extend(1u16.to_le_bytes());
    wav.extend(2u16.to_le_bytes());
    wav.extend(samples.to_le_bytes());
    wav.extend((samples * 4).to_le_bytes());
    wav.extend(4u16.to_le_bytes());
    wav.extend(16u16.to_le_bytes());
    wav.extend(b"data");
    wav.extend(bytes.to_le_bytes());
    for i in 0..samples {
        let v = (2067.0 * (i as f64 * 440.0 * std::f64::consts::TAU / samples as f64).sin()) as i16;
        wav.extend(v.to_le_bytes());
        wav.extend(v.to_le_bytes());
    }
    fs::write(data_dir().join("tone.wav"), wav)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_unbounded_remote_controls() {
        for input in [
            r#"{"op":"start_local_stream","url":"rtmp://example.com/key"}"#,
            r#"{"op":"set_variant","variant":"stretch"}"#,
            r#"{"op":"set_overlay","visible":"yes"}"#,
            r#"{"op":"set_encoder","encoder":"arbitrary_plugin"}"#,
            r#"{"op":"set_encoder","encoder":"x264","path":"/tmp/output"}"#,
            r#"{"op":"encoders","encoder":"x264"}"#,
            r#"{"op":"add_source","scene_id":"scene-1","name":"Invalid","source":{"kind":"pattern","url":"https://example.invalid"}}"#,
            r#"{"op":"set_transform","scene_id":"scene-1","layer_id":"main-layer","variant":"horizontal","transform":{"x":0,"y":0,"width":960,"height":540,"visible":true,"order":0,"secret":"rejected"}}"#,
        ] {
            assert!(
                parse_command(serde_json::from_str(input).unwrap()).is_err(),
                "{input}"
            );
        }
    }
    #[test]
    fn recording_policy_defaults_to_auto_without_changing_v3() {
        assert_eq!(RecordingEncoder::default(), RecordingEncoder::Auto);
        for (name, mode) in [
            ("auto", RecordingEncoder::Auto),
            ("videotoolbox", RecordingEncoder::Videotoolbox),
            ("x264", RecordingEncoder::X264),
        ] {
            let command = parse_command(json!({"op":"set_encoder", "encoder":name})).unwrap();
            assert!(matches!(command, Command::SetEncoder { encoder } if encoder == mode));
            assert_eq!(mode.as_str(), name);
        }
        let document = serde_json::to_value(Project::default()).unwrap();
        assert_eq!(document["version"], 3);
        assert!(document.get("encoder").is_none());
        assert!(document.get("encoding").is_none());
    }
    #[test]
    fn rejects_unknown_fields_in_persisted_unit_source() {
        let mut p = serde_json::to_value(Project::default()).unwrap();
        p["graph"]["sources"][0]["spec"]["url"] = json!("https://example.invalid");
        assert!(parse_project(&serde_json::to_vec(&p).unwrap()).is_err());
    }
    #[test]
    fn project_roundtrip_preserves_variant() {
        let p = Project {
            variant: Variant::Vertical,
            overlay: false,
            ..Project::default()
        };
        let q: Project = serde_json::from_slice(&serde_json::to_vec(&p).unwrap()).unwrap();
        assert_eq!(q.variant, Variant::Vertical);
        assert!(!q.overlay);
    }
    #[test]
    fn window_restore_never_picks_first_or_ambiguous_window() {
        let p = Project {
            capture_window: true,
            window: Some(WindowIdentity {
                bundle_id: "local.fixture".into(),
                title: "Owned".into(),
            }),
            ..Project::default()
        };
        let one = json!({"windows":[{"id":9,"bundle_id":"other","name":"Owned"},
            {"id":11,"bundle_id":"local.fixture","name":"Owned"}]});
        assert_eq!(resolve_window(&p, &one).unwrap(), 11);
        let ambiguous = json!({"windows":[{"id":11,"bundle_id":"local.fixture","name":"Owned"},
            {"id":12,"bundle_id":"local.fixture","name":"Owned"}]});
        assert!(
            resolve_window(&p, &ambiguous)
                .unwrap_err()
                .to_string()
                .starts_with("SOURCE_AMBIGUOUS")
        );
        assert!(resolve_window(&p, &json!({"windows":[]})).is_err());
    }
    #[test]
    fn legacy_project_only_resolves_owned_test_window() {
        let p: Project = serde_json::from_str(r#"{"version":1,"variant":"horizontal","overlay":true,"audio":"none","capture_window":true}"#).unwrap();
        assert!(resolve_window(&p, &json!({"windows":[{"id":9,"test":false}]})).is_err());
        assert_eq!(
            resolve_window(
                &p,
                &json!({"windows":[{"id":9,"test":false},{"id":10,"test":true}]})
            )
            .unwrap(),
            10
        );
    }
}
