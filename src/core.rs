#[path = "audio.rs"]
pub mod audio;
#[path = "output.rs"]
pub mod output;
#[path = "output_runtime.rs"]
mod output_runtime;
#[path = "overlays/mod.rs"]
pub mod overlays;
#[path = "video.rs"]
pub mod video;
use crate::{
    engine::Engine,
    scene::{
        Graph, Layer, Layouts, Recovery, Scene, SourceInput, SourceKind, Transform,
        TransitionConfig, TransitionPhase, VisualSource, valid_name,
    },
};
use audio::{AudioSource, AudioStore};
use output::{LocalEndpoint, OutputProfile, OutputRegistry, OutputTarget, ProfileStore};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::PathBuf,
};
use video::VideoConfig;
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
    AudioMixer,
    SystemAudioSources,
    DisconnectAudioInput {
        input_id: String,
    },
    ReconnectAudioInput {
        input_id: String,
    },
    SaveAudioMixer,
    LoadAudioMixer,
    AddAudioInput {
        name: String,
        source: AudioSource,
    },
    RemoveAudioInput {
        input_id: String,
    },
    SetAudioGain {
        input_id: String,
        gain_db: f32,
    },
    SetAudioMute {
        input_id: String,
        muted: bool,
    },
    Scenes,
    ConfigureTransition {
        transition: TransitionConfig,
    },
    CancelTransition {
        operation_id: u64,
    },
    Devices,
    Encoders,
    OutputCapabilities,
    Outputs,
    VideoCapabilities,
    ConfigureVideo {
        video: VideoConfig,
    },
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
    CredentialStatus {
        credential_ref: String,
    },
    SelectStreamCredential {
        credential_ref: Option<String>,
    },
    PreflightOutput {
        target: OutputTarget,
    },
    StartStream,
    StartOutput {
        target: OutputTarget,
    },
    StopOutputTarget {
        target: OutputTarget,
    },
    CancelOutputTarget {
        target: OutputTarget,
    },
    RecoverOutputTarget {
        target: OutputTarget,
    },
    CancelAllOutputs,
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
    CancelOutput,
    RequestShutdown,
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
    #[serde(untagged)]
    Overlay(overlays::OverlayCommand),
}
// Applied after read-only queries: once either shutdown phase is reached, no
// queued mutation may reopen an output before the owner dispatches native Quit.
fn admit_shutdown_mutation(
    command: &Command,
    pending: bool,
    requested: bool,
) -> anyhow::Result<()> {
    anyhow::ensure!(
        !(pending || requested)
            || matches!(
                command,
                Command::CancelOutput
                    | Command::CancelOutputTarget { .. }
                    | Command::CancelAllOutputs
                    | Command::RequestShutdown
            ),
        "SHUTDOWN_PENDING: native output must finish before exit"
    );
    Ok(())
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
    if let Command::ConfigureVideo { video } = &command {
        video.validate()?;
    }
    Ok(command)
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Project {
    pub version: u32,
    pub variant: Variant,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub video: Option<VideoConfig>,
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
            video: None,
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
    overlays: overlays::production::State,
    pub engine: Engine,
    audio_mixer: AudioStore,
    observed_audio: Option<audio::AudioLifecycle>,
    profiles: ProfileStore,
    recording_profile: String,
    streaming_profile: String,
    stream_endpoint: Option<LocalEndpoint>,
    stream_credential: Option<String>,
    pub project: Project,
    pub revision: u64,
    pub last_action: String,
    outputs: OutputRegistry,
    pub window_id: Option<u32>,
    pub issues: Vec<String>,
    pub recovery: Recovery,
    pub last_fault: Vec<String>,
    pub source_health: Value,
    bindings: BTreeMap<String, WindowBinding>,
    awaiting_recovery: BTreeSet<String>,
    pub shutdown_requested: bool,
    shutdown_pending: bool,
    pub test_window_request: Option<bool>,
    transition: TransitionConfig,
    observed_transition: Option<(u64, TransitionPhase)>,
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
            overlays: overlays::production::State::new(data_dir())?,
            audio_mixer: AudioStore::default(),
            observed_audio: None,
            profiles: ProfileStore::default(),
            recording_profile: "standard".into(),
            streaming_profile: "standard".into(),
            stream_endpoint: None,
            stream_credential: None,
            project: Project::default(),
            revision: 0,
            last_action: "Estudio iniciado".into(),
            outputs: OutputRegistry::default(),
            window_id: None,
            issues: vec![],
            recovery: Recovery::default(),
            last_fault: vec![],
            source_health: json!([]),
            bindings: BTreeMap::new(),
            awaiting_recovery: BTreeSet::new(),
            shutdown_requested: false,
            shutdown_pending: false,
            test_window_request: None,
            transition: TransitionConfig::default(),
            observed_transition: None,
        };
        p.sync(p.graph().clone(), p.bindings.clone(), "")?;
        Ok(p)
    }
    pub fn graph(&self) -> &Graph {
        self.project.graph.as_ref().expect("validated graph")
    }
    pub fn status(&self) -> Value {
        let outputs = self.output_snapshot();
        let legacy = outputs.legacy_target().map(|target| outputs.get(target));
        let mut stats = self.engine.stats();
        for key in [
            "output_bytes",
            "output_frames",
            "output_dropped_frames",
            "encoded_frames",
        ] {
            stats[key] = legacy.map_or(Value::Null, |slot| json!(slot.stats)[key].clone());
        }
        let mut recovery_sources = self.recovery.pending.clone();
        for target in OutputTarget::ALL {
            if outputs.get(target).recovery_required {
                recovery_sources.insert(format!("output:{}", target.name()));
            }
        }
        // Compatibility alias for clients that only know one output. New
        // consumers use the per-target registry and never acknowledge by alias.
        if outputs.recovery_required() {
            recovery_sources.insert("output".into());
        }
        json!({"pid":std::process::id(),"revision":self.revision,"project":self.project,"audio_mixer":self.audio_mixer_status(),"overlays":self.overlay_status(),"encoding":if legacy.is_some(){self.encoding_status(&outputs)}else{Value::Null},"output_configuration":self.output_configuration(),"issues":self.issues,
            "recovery_required":self.recovery.required() || outputs.recovery_required(),"recovery_sources":recovery_sources,"last_fault":self.last_fault,
            "sources":self.source_health,"window_id":self.window_id,"output":legacy.map_or("multiple", |slot|slot.legacy_state()),
            "output_code":legacy.map(|slot|slot.failure.as_ref().and_then(|f|f.native_code).unwrap_or(0)),
            "transition_configuration":self.transition,"transition":self.engine.scene_state(),
            "output_lifecycle":{"native_busy":outputs.busy(),"cancel_requested":OutputTarget::ALL.iter().any(|t|outputs.get(*t).cancel_requested && outputs.get(*t).native_busy),"cancel_deferred":OutputTarget::ALL.iter().any(|t|outputs.get(*t).cancel_deferred),"shutdown_pending":self.shutdown_pending},
            "output_failure":legacy.and_then(|slot|slot.failure.as_ref()),"output_path":legacy.and_then(|slot|slot.path.as_ref()),
            "output_contract_version":1,"outputs":outputs,
            "last_action":self.last_action,"libobs":self.engine.version(),"width":self.engine.width,"height":self.engine.height,"fps":self.engine.fps,"video":self.video_status(),"stats":stats})
    }

    pub fn layout_dimensions(&self) -> (u32, u32) {
        video::layout_dimensions(self.project.variant)
    }
    fn video_status(&self) -> Value {
        let (width, height) = self.layout_dimensions();
        let mut value = self.engine.video_info();
        value["configuration"] = json!(self.project.video.unwrap_or_default());
        value["layout"] = json!({"width":width,"height":height,"coordinate_space":"design960"});
        value["capture_policy"] = video::capabilities()["capture_policy"].clone();
        value["verification"] = json!("preset_configuration_is_not_decoded_media_verification");
        value
    }
    fn configure_video(
        &mut self,
        configuration: Option<VideoConfig>,
        variant: Variant,
    ) -> anyhow::Result<()> {
        self.idle()?;
        let video = configuration.unwrap_or_default();
        video.validate()?;
        let old = self.project.clone();
        self.engine.configure_video(video, variant)?;
        self.project.video = configuration;
        self.project.variant = variant;
        if let Err(failure) = self.sync(self.graph().clone(), self.bindings.clone(), "") {
            let rollback = (|| {
                self.engine
                    .configure_video(old.video.unwrap_or_default(), old.variant)?;
                self.project = old.clone();
                self.sync(self.graph().clone(), self.bindings.clone(), "")
            })();
            self.project = old;
            if rollback.is_err() {
                self.engine.invalidate_video();
            }
            return Err(match rollback {
                Ok(()) => failure,
                Err(e) => anyhow::anyhow!("ROLLBACK_FAILED: {failure}; {e}"),
            });
        }
        // Window streams renewed at a different FPS must become ready again.
        self.awaiting_recovery.extend(
            self.graph()
                .sources
                .iter()
                .filter(|s| matches!(s.spec, SourceKind::Window { .. }))
                .map(|s| s.id.clone())
                .collect::<Vec<_>>(),
        );
        Ok(())
    }
    fn encoding_status(&self, outputs: &OutputRegistry) -> Value {
        let future_preference = outputs
            .legacy_target()
            .map(|target| self.profile(target).encoder);
        legacy_encoding_status(self.engine.encoding_info(), outputs, future_preference)
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
            "endpoint":self.stream_endpoint,"credential_ref":self.stream_credential,"credentials_supported":true,"automatic_reconnect":false})
    }
    fn output_capabilities(&self) -> Value {
        json!({"encoders":self.engine.encoding_info(),"rate_controls":["cbr"],"bitrate_kbps":{"min":250,"max":20000},
            "keyframe_seconds":{"min":1,"max":10},"frame_reordering":[true,false],
            "canvas":{"width":self.engine.width,"height":self.engine.height,"fps":self.engine.fps,
                "configuration":self.project.video.unwrap_or_default(),"capabilities":video::capabilities(),
                "profile_resolution_configurable":false,"production_resolution_configurable":true,"fps_configurable":true},
            "audio":{"codec":"aac","bitrate_kbps":160,"sample_rate":48000,"channels":2},
            "streaming":{"host":"127.0.0.1","port_min":1024,"path":"/live/motive","transport":["rtmp","rtmps"],
                "rtmps_validation":"system_trust_required; trusted media delivery not yet verified",
                "credentials_supported":true,"credential_storage":"macos_keychain","credential_transport":"rtmps_only",
                "credential_logging":"freeform_obs_logs_suppressed_after_first_use","public_destinations":false},"simultaneous_outputs":2,"targets":["recording","streaming"],"encoder_sharing":false,"composition_shared":true,"output_contract_version":1,"cancel_connecting_supported":false,
                "deferred_cancellation_supported":true,"rtmp_lifecycle":"obs-33.0.1-pinned-joinable-workers"})
    }
    fn preflight(&self, target: OutputTarget) -> anyhow::Result<()> {
        admit_shutdown_mutation(
            &Command::PreflightOutput { target },
            self.shutdown_pending,
            self.shutdown_requested,
        )?;
        anyhow::ensure!(!self.overlays.busy(), "ASSET_IMPORT_BUSY");
        self.scene_quiescent()?;
        let outputs = self.output_snapshot();
        outputs.get(target).can_start()?;
        anyhow::ensure!(
            !(outputs.streaming.native_busy
                && outputs.streaming.kind == Some(output::OutputKind::LocalStream)),
            "OUTPUT_BUSY"
        );
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
            if let Some(reference) = &self.stream_credential {
                let endpoint = self.stream_endpoint.as_ref().unwrap();
                anyhow::ensure!(
                    endpoint.transport == output::Transport::Rtmps,
                    "CREDENTIAL_REQUIRES_TLS"
                );
                let code = self.engine.credential_status(reference, endpoint.port);
                anyhow::ensure!(code == 0, "{}", output::credential_code(code));
            }
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
        if self.engine.video_info()["available"] != true {
            result.push(("video".into(), "VIDEO_RECOVERY_REQUIRED".into()));
        }
        // Preserve the old single-input stop policy for legacy UI/CLI. The new
        // mixer isolates a failed channel and keeps all other channels/output live.
        if let Some(code) = match if self.audio_mixer.inputs.len() <= 1 {
            self.engine.audio_health()
        } else {
            0
        } {
            1 => Some("DEVICE_UNAVAILABLE"),
            2 => Some("MICROPHONE_PERMISSION_DENIED"),
            3 => Some("AUDIO_NOT_READY"),
            6 => Some("AUDIO_STALLED"),
            _ => None,
        } {
            result.push(("audio".into(), code.into()));
        }
        result
    }
    pub fn poll_health(&mut self) {
        self.poll_overlays();
        self.engine.poll_audio();
        let audio = self.engine.audio_state();
        let lifecycle = audio.lifecycle();
        if self.observed_audio.as_ref() != Some(&lifecycle) {
            self.observed_audio = Some(lifecycle);
            self.revision += 1;
        }
        self.engine.poll_scene();
        let transition = self.engine.scene_state();
        let observed = (transition.operation_id, transition.phase);
        if self.observed_transition != Some(observed) {
            self.observed_transition = Some(observed);
            if self.graph().active_scene != transition.current_scene {
                self.project.graph.as_mut().unwrap().active_scene = transition.current_scene;
                self.update_legacy();
                self.retain_active_recovery();
            }
            self.revision += 1;
            if let Some(error) = transition.error {
                self.last_action = format!("{error}: se conserva la escena anterior");
            }
        }
        self.source_health = self.engine.graph_health();
        let faults = self.faults_from(&self.source_health);
        self.issues = faults.iter().map(|(_, c)| c.clone()).collect();
        self.poll_outputs();
        if !faults.is_empty()
            && self.outputs.busy()
            && OutputTarget::ALL
                .iter()
                .any(|t| self.outputs.get(*t).native_busy && !self.outputs.get(*t).cancel_requested)
        {
            self.cancel_all_outputs();
            self.recovery
                .pending
                .extend(faults.iter().map(|(id, _)| id.clone()));
            self.last_fault = self.issues.clone();
            self.revision += 1;
            self.last_action = format!(
                "Fuente perdida: {}. Salidas finalizando.",
                self.issues.join(", ")
            );
        }
        if self.shutdown_pending
            && !self.outputs.busy()
            && self.engine.output_state() == 0
            && !self.overlays.busy()
        {
            self.shutdown_requested = true;
        }
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
        anyhow::ensure!(!self.overlays.busy(), "ASSET_IMPORT_BUSY");
        self.scene_quiescent()?;
        anyhow::ensure!(
            self.engine.output_state() == 0,
            "OUTPUT_BUSY: espera la finalización de la salida"
        );
        Ok(())
    }
    fn scene_quiescent(&self) -> anyhow::Result<()> {
        anyhow::ensure!(!self.engine.overlay_animation_busy(), "ANIMATION_BUSY");
        anyhow::ensure!(
            !self.engine.scene_state().busy(),
            "TRANSITION_BUSY: espera o cancela la transición"
        );
        Ok(())
    }
    fn source_ready(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.engine.video_info()["available"] == true,
            "VIDEO_UNAVAILABLE"
        );
        let audio = self.engine.audio_state();
        anyhow::ensure!(
            audio.ready(),
            "AUDIO_NOT_READY: inspect audio_mixer.issues and reconnect the affected input"
        );
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
    pub fn audio_mixer_status(&self) -> Value {
        let runtime = self.engine.audio_state();
        json!({"store":self.audio_mixer,"issues":runtime.issues(),"runtime":runtime,
            "meter_point":"post_fader_pre_mute","meter_kind":"sample_peak_and_rms",
            "mix_meter_point":"post_fader_post_mute_pre_clamp","monitoring":"off","mix_index":0})
    }
    fn add_audio(&mut self, name: String, source: AudioSource) -> anyhow::Result<String> {
        let mut candidate = self.audio_mixer.clone();
        let id = candidate.add(name, source)?;
        candidate.validate()?;
        if !self.audio_mixer.inputs.iter().any(|i| i.id == id) {
            self.engine.audio_add(
                candidate.input(&id)?,
                &data_dir().join("tone.wav").to_string_lossy(),
            )?;
            self.audio_mixer = candidate;
        }
        Ok(id)
    }
    fn remove_audio(&mut self, id: &str) -> anyhow::Result<()> {
        let input = self.audio_mixer.input(id)?;
        let legacy = input.source.legacy_device() == Some(self.project.audio.as_str());
        self.engine.audio_remove(id)?;
        self.audio_mixer.inputs.retain(|i| i.id != id);
        if legacy {
            self.project.audio = "none".into();
            self.engine.audio_legacy("none")?;
            self.awaiting_recovery.insert("audio".into());
        }
        Ok(())
    }
    fn audio(&mut self, device: &str) -> anyhow::Result<()> {
        anyhow::ensure!(
            !device.is_empty() && device.len() < 512 && !device.contains('\0'),
            "INVALID_ARGUMENT: audio inválido"
        );
        let previous = self
            .audio_mixer
            .inputs
            .iter()
            .find(|i| i.source.legacy_device() == Some(self.project.audio.as_str()))
            .map(|i| i.id.clone());
        let target = self
            .audio_mixer
            .inputs
            .iter()
            .find(|i| i.source.legacy_device() == Some(device))
            .cloned();
        if device != "none" {
            if let Some(input) = target {
                if self
                    .engine
                    .audio_state()
                    .inputs
                    .iter()
                    .any(|r| r.id == input.id && r.phase != audio::AudioPhase::Ready)
                {
                    self.engine.audio_reconnect(&input)?;
                }
            } else {
                let source = if device == "tone" {
                    AudioSource::Tone
                } else {
                    AudioSource::Microphone {
                        device_id: device.into(),
                    }
                };
                // Prepare first: a denied/missing selection must not destroy the
                // previous working source or rewrite its desired identity.
                let id = self.add_audio("Audio principal".into(), source)?;
                let input = self
                    .audio_mixer
                    .inputs
                    .iter_mut()
                    .find(|i| i.id == id)
                    .unwrap();
                input.gain_db = 0.0;
                self.engine.audio_control(input)?;
            }
        }
        if device != self.project.audio
            && let Some(previous) = previous
        {
            self.remove_audio(&previous)?;
        }
        self.project.audio = device.into();
        self.engine.audio_legacy(device)?;
        self.awaiting_recovery.insert("audio".into());
        Ok(())
    }
    fn restore_audio(&mut self, store: AudioStore) -> anyhow::Result<()> {
        self.idle()?;
        store.validate()?;
        let previous = self.audio_mixer.clone();
        let previous_runtime = self.engine.audio_state();
        // Drop obsolete captures, but retain every physical identity shared by
        // the documents. Remap retained IDs through private temporary IDs so a
        // valid permutation cannot collide or create a second physical capture.
        for input in &previous.inputs {
            if !store.inputs.iter().any(|i| i.source == input.source) {
                self.engine.audio_remove(&input.id)?;
            }
        }
        let mut reused = Vec::new();
        for (index, input) in previous.inputs.iter().enumerate() {
            if let Some(target) = store.inputs.iter().find(|i| i.source == input.source) {
                let temp = format!("restore-{index}");
                self.engine.audio_rename_id(&input.id, &temp)?;
                let retry = previous_runtime.inputs.iter().any(|r| {
                    r.id == input.id
                        && matches!(
                            r.phase,
                            audio::AudioPhase::Failed | audio::AudioPhase::Disconnected
                        )
                });
                reused.push((temp, target, retry));
            }
        }
        for (temp, input, retry) in reused {
            self.engine.audio_rename_id(&temp, &input.id)?;
            self.engine.audio_control(input)?;
            if retry {
                let _ = self.engine.audio_reconnect(input);
            }
        }
        for input in &store.inputs {
            if !previous.inputs.iter().any(|i| i.source == input.source)
                && self
                    .engine
                    .audio_add(input, &data_dir().join("tone.wav").to_string_lossy())
                    .is_err()
            {
                self.engine.audio_restore_missing(input)?;
            }
        }
        self.audio_mixer = store;
        let legacy_exists = self
            .audio_mixer
            .inputs
            .iter()
            .any(|i| i.source.legacy_device() == Some(self.project.audio.as_str()));
        self.engine.audio_legacy(if legacy_exists {
            &self.project.audio
        } else {
            "none"
        })?;
        Ok(())
    }
    fn native_graph(
        &self,
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
        self.overlay_native_graph(graph, &mut value)?;
        Ok(value)
    }
    fn sync(
        &mut self,
        graph: Graph,
        bindings: BTreeMap<String, WindowBinding>,
        reconnect: &str,
    ) -> anyhow::Result<()> {
        graph.validate()?;
        if !reconnect.is_empty() {
            self.overlays.invalidate();
        }
        self.engine
            .sync_graph(&self.native_graph(&graph, &bindings)?, reconnect)?;
        self.overlays.graph_replaced();
        self.project.graph = Some(graph);
        self.bindings = bindings;
        self.project.version = if self.project.video.is_some() {
            5
        } else if self.graph().sources.iter().any(|s| s.overlay.is_some()) {
            4
        } else {
            3
        };
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
            source.overlay = None;
        } else {
            graph.sources.push(VisualSource {
                id: "main".into(),
                name: "Principal".into(),
                spec,
                overlay: None,
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
        validate_project_video(&p)?;
        self.overlays.invalidate();
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
        anyhow::ensure!(
            p.version >= 4 || graph.sources.iter().all(|s| s.overlay.is_none()),
            "PROJECT_VERSION_MISMATCH"
        );
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
        let old_audio = self.audio_mixer.clone();
        let old_bindings = self.bindings.clone();
        let result = (|| {
            self.engine
                .configure_video(p.video.unwrap_or_default(), p.variant)?;
            self.audio(&p.audio)?;
            self.project.variant = p.variant;
            self.project.video = p.video;
            self.sync(graph, bindings, "")?;
            Ok::<_, anyhow::Error>(())
        })();
        if let Err(failure) = result {
            let rollback = (|| {
                self.engine
                    .configure_video(old.video.unwrap_or_default(), old.variant)?;
                self.project.audio = old.audio.clone();
                self.restore_audio(old_audio)?;
                self.project.variant = old.variant;
                self.project.video = old.video;
                self.sync(old.graph.clone().unwrap(), old_bindings, "")?;
                Ok::<_, anyhow::Error>(())
            })();
            self.project = old;
            if rollback.is_err() {
                self.engine.invalidate_video();
            }
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
        if let Command::SelectScene { scene_id } = &command {
            self.graph().scene(scene_id)?;
            // Select existing native scenes; do not reconcile capture resources,
            // reset video or touch the running output/encoders.
            anyhow::ensure!(!self.engine.overlay_animation_busy(), "ANIMATION_BUSY");
            return self.engine.switch_scene(scene_id, self.transition);
        }
        self.scene_quiescent()?;
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
                    overlay: None,
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
                anyhow::ensure!(s.overlay.is_none(), "USE_OVERLAY_PROPERTIES");
                s.spec = SourceKind::Overlay { color };
            }
            _ => unreachable!(),
        }
        self.sync(graph, bindings, "")?;
        self.retain_active_recovery();
        Ok(())
    }
    fn retain_active_recovery(&mut self) {
        let relevant: BTreeSet<_> = self
            .graph()
            .scene(&self.graph().active_scene)
            .expect("validated active scene")
            .layers
            .iter()
            .filter(|l| l.layouts.get(self.project.variant).visible)
            .map(|l| l.source_id.clone())
            .collect();
        self.recovery
            .pending
            .retain(|id| id == "audio" || id == "video" || relevant.contains(id));
    }
    pub fn apply(&mut self, command: Command, origin: &str) -> Value {
        self.poll_health();
        if matches!(&command, Command::Overlay(overlay) if !overlay.query())
            && let Err(e) =
                admit_shutdown_mutation(&command, self.shutdown_pending, self.shutdown_requested)
        {
            return command_error(e);
        }
        if let Command::Overlay(command) = command {
            return self.apply_overlay(command, origin);
        }
        if matches!(command, Command::Status) {
            return json!({"ok":true,"state":self.status()});
        }
        if matches!(command, Command::SystemAudioSources) {
            return match self.engine.system_audio_sources() {
                Ok(sources) => {
                    json!({"ok":true,"pid":std::process::id(),"system_audio_sources":sources})
                }
                Err(e) => command_error(e),
            };
        }
        if matches!(command, Command::AudioMixer) {
            return json!({"ok":true,"pid":std::process::id(),"revision":self.revision,"audio_mixer":self.audio_mixer_status()});
        }
        if matches!(command, Command::Scenes) {
            return json!({"ok":true,"revision":self.revision,"scenes":self.graph().scenes,
                "current_scene":self.graph().active_scene,"configuration":self.transition,"transition":self.engine.scene_state()});
        }
        if matches!(command, Command::Devices) {
            return json!({"ok":true,"devices":self.engine.devices()});
        }
        if matches!(command, Command::Encoders) {
            return json!({"ok":true,"encoders":self.encoding_status(&self.output_snapshot())});
        }
        if matches!(command, Command::VideoCapabilities) {
            return json!({"ok":true,"pid":std::process::id(),"capabilities":video::capabilities(),"video":self.video_status()});
        }
        if matches!(command, Command::Outputs) {
            return json!({"ok":true,"pid":std::process::id(),"revision":self.revision,"output_contract_version":1,"outputs":self.output_snapshot()});
        }
        if matches!(command, Command::OutputCapabilities) {
            return json!({"ok":true,"capabilities":self.output_capabilities()});
        }
        if matches!(command, Command::OutputProfiles) {
            return json!({"ok":true,"store":self.profiles,"configuration":self.output_configuration()});
        }
        if let Command::CredentialStatus { credential_ref } = &command {
            if !output::valid_credential_ref(credential_ref) {
                return error(
                    "INVALID_CREDENTIAL_REFERENCE",
                    "Expected an opaque Keychain reference",
                );
            }
            return json!({"ok":true,"credential_ref":credential_ref,"access":output::credential_code(self.engine.credential_status(credential_ref,0))});
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
            admit_shutdown_mutation(&command, self.shutdown_pending, self.shutdown_requested)?;
            match command {
                Command::ConfigureVideo { video } => {
                    self.configure_video(Some(video), self.project.variant)?;
                }
                Command::ConfigureTransition { transition } => {
                    self.scene_quiescent()?;
                    transition.validate()?;
                    self.transition = transition;
                }
                Command::CancelTransition { operation_id } => {
                    self.engine.cancel_scene(operation_id)?
                }
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
                    self.stream_credential = None;
                }
                Command::SelectStreamCredential { credential_ref } => {
                    self.idle()?;
                    if let Some(reference) = &credential_ref {
                        anyhow::ensure!(
                            output::valid_credential_ref(reference),
                            "INVALID_CREDENTIAL_REFERENCE"
                        );
                        let endpoint = self
                            .stream_endpoint
                            .as_ref()
                            .ok_or_else(|| anyhow::anyhow!("ENDPOINT_REQUIRED"))?;
                        anyhow::ensure!(
                            endpoint.transport == output::Transport::Rtmps,
                            "CREDENTIAL_REQUIRES_TLS"
                        );
                        let code = self.engine.credential_status(reference, endpoint.port);
                        anyhow::ensure!(code == 0, "{}", output::credential_code(code));
                    }
                    self.stream_credential = credential_ref;
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
                    self.legacy_start_guard()?;
                    self.start_target(OutputTarget::Streaming, false)?;
                }
                Command::StartOutput { target } => self.start_target(target, false)?,
                Command::StopOutputTarget { target } => self.stop_target(target, false)?,
                Command::CancelOutputTarget { target } => self.stop_target(target, true)?,
                Command::RecoverOutputTarget { target } => self.recover_target(target)?,
                Command::CancelAllOutputs => self.cancel_all_outputs(),
                Command::RecoverOutput => {
                    self.idle()?;
                    if let Some(target) = self.output_snapshot().legacy_recovery_target()? {
                        self.recover_target(target)?;
                    }
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
                    self.configure_video(self.project.video, variant)?;
                }
                Command::SelectSource { window_id } => {
                    self.legacy_source(window_id.map_or(SourceInput::Pattern, |window_id| {
                        SourceInput::Window { window_id }
                    }))?
                }
                Command::SelectCamera { id } => {
                    self.legacy_source(SourceInput::Camera { device_id: id })?
                }
                Command::SaveAudioMixer => {
                    self.audio_mixer.validate()?;
                    let path = data_dir().join("audio-mixer.json");
                    let temp = path.with_extension("json.tmp");
                    use std::io::Write;
                    let mut file = fs::File::create(&temp)?;
                    file.write_all(&serde_json::to_vec_pretty(&self.audio_mixer)?)?;
                    file.sync_all()?;
                    fs::rename(temp, path)?;
                    fs::File::open(data_dir())?.sync_all()?;
                }
                Command::LoadAudioMixer => {
                    use std::io::Read;
                    let mut bytes = vec![];
                    fs::File::open(data_dir().join("audio-mixer.json"))?
                        .take(65537)
                        .read_to_end(&mut bytes)?;
                    self.restore_audio(AudioStore::parse(&bytes)?)?;
                }
                Command::DisconnectAudioInput { input_id } => {
                    self.audio_mixer.input(&input_id)?;
                    self.engine.audio_disconnect(&input_id)?;
                }
                Command::ReconnectAudioInput { input_id } => {
                    let input = self.audio_mixer.input(&input_id)?.clone();
                    self.engine.audio_reconnect(&input)?;
                    if input.source.legacy_device() == Some(self.project.audio.as_str()) {
                        self.awaiting_recovery.insert("audio".into());
                    }
                }
                Command::AddAudioInput { name, source } => {
                    self.idle()?;
                    self.add_audio(name, source)?;
                }
                Command::RemoveAudioInput { input_id } => {
                    self.idle()?;
                    self.remove_audio(&input_id)?;
                }
                Command::SetAudioGain { input_id, gain_db } => {
                    audio::validate_gain(gain_db)?;
                    let mut input = self.audio_mixer.input(&input_id)?.clone();
                    input.gain_db = gain_db;
                    self.engine.audio_control(&input)?;
                    *self
                        .audio_mixer
                        .inputs
                        .iter_mut()
                        .find(|i| i.id == input_id)
                        .unwrap() = input;
                }
                Command::SetAudioMute { input_id, muted } => {
                    let mut input = self.audio_mixer.input(&input_id)?.clone();
                    input.muted = muted;
                    self.engine.audio_control(&input)?;
                    *self
                        .audio_mixer
                        .inputs
                        .iter_mut()
                        .find(|i| i.id == input_id)
                        .unwrap() = input;
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
                    let recover = self.output_snapshot().legacy_recovery_target()?;
                    self.sync(self.graph().clone(), self.bindings.clone(), "*")?;
                    for input in &self.audio_mixer.inputs {
                        self.engine.audio_reconnect(input)?;
                    }
                    self.engine.reset_output()?;
                    if let Some(target) = recover {
                        self.outputs.get_mut(target).recover()?;
                    }
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
                    self.legacy_start_guard()?;
                    self.start_target(OutputTarget::Recording, false)?;
                }
                Command::StartLocalStream => {
                    self.legacy_start_guard()?;
                    self.start_target(OutputTarget::Streaming, true)?;
                }
                Command::StopOutput | Command::CancelOutput => {
                    if let Some(target) = self.output_snapshot().unique_busy()? {
                        self.stop_target(target, matches!(command, Command::CancelOutput))?;
                    }
                }
                Command::RequestShutdown => {
                    self.shutdown_pending = true;
                    self.engine
                        .cancel_scene(self.engine.scene_state().operation_id)?;
                    self.cancel_all_outputs();
                    // Let the owner keep polling an import before dropping its
                    // worker; State::drop must not join a live job on the UI thread.
                    if !self.output_snapshot().busy() && !self.overlays.busy() {
                        self.shutdown_requested = true;
                    }
                }
                Command::SaveProject => {
                    self.scene_quiescent()?;
                    let path = data_dir().join("project.json");
                    let temp = path.with_extension("json.tmp");
                    let bytes = serialize_project(&self.project)?;
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
                    file.take(262145).read_to_end(&mut bytes)?;
                    anyhow::ensure!(bytes.len() <= 262144, "PROJECT_TOO_LARGE");
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
                    self.shutdown_pending = true;
                    self.shutdown_requested = true;
                }
                Command::SetTestWindow { open } => {
                    self.test_window_request = Some(open);
                }
                Command::Status
                | Command::AudioMixer
                | Command::SystemAudioSources
                | Command::Scenes
                | Command::Devices
                | Command::Encoders
                | Command::OutputCapabilities
                | Command::Outputs
                | Command::VideoCapabilities
                | Command::OutputProfiles
                | Command::CredentialStatus { .. }
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
            Err(e) => {
                // Failed preparation still has an observable operation/result.
                self.poll_health();
                let mut response = command_error(e);
                response["revision"] = json!(self.revision);
                response["transition"] = json!(self.engine.scene_state());
                response["audio_mixer"] = self.audio_mixer_status();
                response["outputs"] = json!(self.output_snapshot());
                response
            }
        }
    }
}
fn legacy_encoding_status(
    mut value: Value,
    outputs: &OutputRegistry,
    future_preference: Option<RecordingEncoder>,
) -> Value {
    if let Some(target) = outputs.legacy_target() {
        let slot = outputs.get(target);
        // The FFI supplies inventory only. Its legacy selector cannot see a
        // synchronous start failure retained by Rust without a native code.
        value["selected_id"] = json!(slot.encoding.selected_id);
        value["selected_hardware"] = json!(slot.encoding.selected_hardware);
        value["fallback_reason"] = json!(slot.encoding.fallback_reason);
        value["preference"] = json!(
            slot.profile
                .as_ref()
                .map(|profile| profile.encoder)
                .or(future_preference)
        );
        value["scope"] = json!(format!("selected_{}_profile", target.name()));
    } else {
        for key in [
            "selected_id",
            "selected_hardware",
            "fallback_reason",
            "preference",
        ] {
            value[key] = Value::Null;
        }
        value["scope"] = json!("inventory; inspect outputs for effective encoders");
    }
    value
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
fn validate_project_video(project: &Project) -> anyhow::Result<()> {
    anyhow::ensure!(
        (1..=5).contains(&project.version),
        "PROJECT_VERSION_UNSUPPORTED"
    );
    anyhow::ensure!(
        (project.version == 5) == project.video.is_some(),
        "PROJECT_VERSION_MISMATCH"
    );
    if let Some(video) = project.video {
        video.validate()?;
    }
    Ok(())
}
fn serialize_project(project: &Project) -> anyhow::Result<Vec<u8>> {
    validate_project_video(project)?;
    // Use the same JSON-number representation as status/CLI/MCP. Serializing
    // f32 directly chooses a different decimal spelling than Value's f64 and
    // would make a saved document differ from the acknowledged shared state.
    let bytes = serde_json::to_vec_pretty(&serde_json::to_value(project)?)?;
    anyhow::ensure!(
        bytes.len() <= if project.version >= 4 { 262144 } else { 65536 },
        "PROJECT_TOO_LARGE"
    );
    Ok(bytes)
}
fn parse_project(bytes: &[u8]) -> anyhow::Result<Project> {
    anyhow::ensure!(bytes.len() <= 262144, "PROJECT_TOO_LARGE");
    let value: Value = serde_json::from_slice(bytes)?;
    let project: Project = serde_json::from_value(value.clone())?;
    validate_project_video(&project)?;
    anyhow::ensure!(
        project.version == 5 || value.get("video").is_none(),
        "PROJECT_VERSION_MISMATCH"
    );
    anyhow::ensure!(
        project.version >= 4 || bytes.len() <= 65536,
        "PROJECT_TOO_LARGE"
    );
    anyhow::ensure!(
        project.version >= 4
            || project
                .graph
                .as_ref()
                .is_none_or(|g| g.sources.iter().all(|s| s.overlay.is_none())),
        "PROJECT_VERSION_MISMATCH"
    );
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
    fn shutdown_admission_blocks_queued_starts_in_both_terminal_phases() {
        let commands = [
            json!({"op":"start_recording"}),
            json!({"op":"start_local_stream"}),
            json!({"op":"start_stream"}),
            json!({"op":"start_output","target":"recording"}),
            json!({"op":"start_output","target":"streaming"}),
            json!({"op":"preflight_output","target":"recording"}),
            json!({"op":"set_test_window","open":true}),
            json!({"op":"import_asset","file_name":"queued.png"}),
            json!({"op":"save_project"}),
        ];
        for value in commands {
            let command = parse_command(value.clone()).unwrap();
            assert!(admit_shutdown_mutation(&command, false, false).is_ok());
            // Include requested-only as a defensive terminal snapshot: native
            // Quit must never trust that flag while an accepted start can race it.
            for (pending, requested) in [(true, false), (true, true), (false, true)] {
                let response = command_error(
                    admit_shutdown_mutation(&command, pending, requested).unwrap_err(),
                );
                assert_eq!(response["error"]["code"], "SHUTDOWN_PENDING", "{value}");
            }
        }
        for value in [
            json!({"op":"cancel_output"}),
            json!({"op":"cancel_output_target","target":"recording"}),
            json!({"op":"cancel_output_target","target":"streaming"}),
            json!({"op":"cancel_all_outputs"}),
            json!({"op":"request_shutdown"}),
        ] {
            let command = parse_command(value).unwrap();
            for (pending, requested) in [(true, false), (true, true), (false, true)] {
                assert!(admit_shutdown_mutation(&command, pending, requested).is_ok());
            }
        }
    }
    #[test]
    fn video_projects_are_explicit_and_legacy_coordinates_roundtrip_unchanged() {
        for version in 1..=4 {
            let legacy = Project {
                version,
                ..Project::default()
            };
            let bytes = serialize_project(&legacy).unwrap();
            let value: Value = serde_json::from_slice(&bytes).unwrap();
            assert!(value.get("video").is_none());
            let loaded = parse_project(&bytes).unwrap();
            assert_eq!(loaded.video.unwrap_or_default(), VideoConfig::default());
            assert_eq!(serialize_project(&loaded).unwrap(), bytes);
            let mut extended = value.clone();
            extended["video"] = json!(VideoConfig::default());
            assert!(parse_project(&serde_json::to_vec(&extended).unwrap()).is_err());
            extended["video"] = Value::Null;
            assert!(parse_project(&serde_json::to_vec(&extended).unwrap()).is_err());
        }
        let original = Project::default();
        let graph = serde_json::to_value(&original.graph).unwrap();
        for resolution in [video::Resolution::Hd720, video::Resolution::FullHd1080] {
            for variant in [Variant::Horizontal, Variant::Vertical] {
                let project = Project {
                    version: 5,
                    variant,
                    video: Some(VideoConfig {
                        resolution,
                        fps: 60,
                        ..VideoConfig::default()
                    }),
                    ..original.clone()
                };
                let loaded = parse_project(&serialize_project(&project).unwrap()).unwrap();
                assert_eq!(loaded.video, project.video);
                assert_eq!(loaded.variant, variant);
                assert_eq!(serde_json::to_value(&loaded.graph).unwrap(), graph);
            }
        }
        assert!(
            serialize_project(&Project {
                version: 5,
                ..Project::default()
            })
            .is_err()
        );
        assert!(
            serialize_project(&Project {
                version: 6,
                ..Project::default()
            })
            .is_err()
        );
    }
    #[test]
    fn video_controls_reject_unsupported_or_implicit_configuration() {
        let valid = json!({"op":"configure_video","video":VideoConfig::default()});
        assert!(parse_command(valid.clone()).is_ok());
        for invalid in [json!(true), json!(30.5), json!(59), json!(0), Value::Null] {
            let mut command = valid.clone();
            command["video"]["fps"] = invalid;
            assert!(parse_command(command).is_err());
        }
        for (key, value) in [
            ("version", json!(2)),
            ("resolution", json!("4k")),
            ("coordinate_space", json!("output_pixels")),
            ("width", json!(1920)),
        ] {
            let mut command = valid.clone();
            command["video"][key] = value;
            assert!(parse_command(command).is_err());
        }
        let mut missing = valid;
        missing["video"]
            .as_object_mut()
            .unwrap()
            .remove("coordinate_space");
        assert!(parse_command(missing).is_err());
        assert!(parse_command(json!({"op":"video_capabilities","fps":60})).is_err());
    }
    #[test]
    fn saved_overlay_numbers_equal_the_acknowledged_json_state() {
        let mut project = Project {
            version: 4,
            ..Project::default()
        };
        project.graph.as_mut().unwrap().sources[1].overlay = Some(overlays::Definition::Shape {
            shape: overlays::Shape::Circle,
            width: 64,
            height: 64,
            color: 0xffffff,
            opacity: 0.8,
            border_color: None,
            border_width: 0,
        });
        let bytes = serialize_project(&project).unwrap();
        let saved: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(saved, serde_json::to_value(&project).unwrap());
        assert_eq!(
            serde_json::to_value(parse_project(&bytes).unwrap()).unwrap(),
            saved
        );
    }
    #[test]
    fn overlay_project_v4_roundtrips_beyond_legacy_size_without_silent_v3_extension() {
        let definition = overlays::Definition::Text {
            text: "é".repeat(2048),
            font: overlays::Font::Helvetica,
            size: 8,
            color: 0xffffff,
            opacity: 1.,
            align: overlays::Alignment::Left,
            width: 1920,
            height: 100,
            background: None,
            background_opacity: 0.,
            outline: false,
        };
        definition.validate().unwrap();
        let mut project = Project {
            version: 4,
            ..Project::default()
        };
        let graph = project.graph.as_mut().unwrap();
        graph.sources.clear();
        graph.scenes[0].layers.clear();
        for i in 0..16 {
            graph.sources.push(VisualSource {
                id: format!("source-{i}"),
                name: format!("Text {i}"),
                spec: SourceKind::Overlay { color: 0 },
                overlay: Some(definition.clone()),
            });
        }
        graph.validate().unwrap();
        let bytes = serialize_project(&project).unwrap();
        assert!(bytes.len() > 65536);
        assert_eq!(parse_project(&bytes).unwrap().version, 4);
        project.version = 3;
        assert!(serialize_project(&project).is_err());
        let mut smaller = Project::default();
        smaller.graph.as_mut().unwrap().sources[1].overlay = Some(definition);
        assert!(parse_project(&serde_json::to_vec(&smaller).unwrap()).is_err());
    }
    #[test]
    fn rejects_unbounded_remote_controls() {
        for input in [
            r#"{"op":"start_local_stream","url":"rtmp://example.com/key"}"#,
            r#"{"op":"audio_mixer","path":"/tmp/audio"}"#,
            r#"{"op":"add_audio_input","name":"Tone","source":{"kind":"tone","device_id":"extra"}}"#,
            r#"{"op":"add_audio_input","name":"Mic","source":{"kind":"microphone","device_id":"uid","monitor":true}}"#,
            r#"{"op":"set_audio_mute","input_id":"audio-1","muted":"yes"}"#,
            r#"{"op":"set_audio_gain","input_id":"audio-1","gain_db":null}"#,
            r#"{"op":"set_variant","variant":"stretch"}"#,
            r#"{"op":"set_overlay","visible":"yes"}"#,
            r#"{"op":"set_encoder","encoder":"arbitrary_plugin"}"#,
            r#"{"op":"set_encoder","encoder":"x264","path":"/tmp/output"}"#,
            r#"{"op":"encoders","encoder":"x264"}"#,
            r#"{"op":"configure_transition","transition":{"kind":"fade","duration_ms":500,"queue":true}}"#,
            r#"{"op":"configure_transition","transition":{"kind":"fade"}}"#,
            r#"{"op":"cancel_transition","operation_id":-1}"#,
            r#"{"op":"select_scene","scene_id":"scene-1","duration_ms":500}"#,
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
    #[test]
    fn output_commands_are_targeted_and_closed() {
        for op in [
            "start_output",
            "stop_output_target",
            "cancel_output_target",
            "recover_output_target",
        ] {
            for target in ["recording", "streaming"] {
                assert!(parse_command(json!({"op":op,"target":target})).is_ok());
            }
            for command in [
                json!({"op":op}),
                json!({"op":op,"target":"public"}),
                json!({"op":op,"target":"recording","path":"/tmp/not-a-capability"}),
                json!({"op":op,"target":"streaming","url":"rtmp://example.invalid"}),
            ] {
                assert!(parse_command(command).is_err());
            }
        }
        for op in [
            "outputs",
            "cancel_all_outputs",
            "start_recording",
            "start_stream",
            "stop_output",
            "cancel_output",
        ] {
            assert!(parse_command(json!({"op":op})).is_ok());
            assert!(parse_command(json!({"op":op,"target":"recording"})).is_err());
        }
    }
    #[test]
    fn encoder_projection_follows_failed_target_and_retains_attempt_profile() {
        use output::{NativeOutput, OutputEncoding, OutputKind, OutputStats, OutputVideo};
        let mut outputs = OutputRegistry::default();
        let video = OutputVideo {
            width: 1920,
            height: 1080,
            fps: 30,
        };
        let observation = |state, encoding| NativeOutput {
            state,
            code: 0,
            active_duration_ms: 1000,
            encoding,
            stats: OutputStats::default(),
        };
        outputs.streaming.begin(
            OutputKind::Streaming,
            OutputProfile {
                encoder: RecordingEncoder::Videotoolbox,
                ..OutputProfile::default()
            },
            video.clone(),
            None,
        );
        outputs
            .streaming
            .observe(observation(0, OutputEncoding::default()));
        outputs
            .streaming
            .fail_start(&anyhow::anyhow!("VIDEO_ENCODER_INIT_FAILED"));
        outputs.recording.begin(
            OutputKind::Recording,
            OutputProfile::default(),
            video.clone(),
            Some("owned-recording.mkv".into()),
        );
        let recorded_encoding = OutputEncoding {
            selected_id: Some("obs_x264".into()),
            fallback_reason: Some("VIDEOTOOLBOX_INITIALIZATION_FAILED".into()),
            ..OutputEncoding::default()
        };
        outputs
            .recording
            .observe(observation(1, recorded_encoding.clone()));
        outputs.recording.observe(observation(0, recorded_encoding));
        outputs.last_target = OutputTarget::Recording;
        // Native legacy selection now describes the healthy last recording;
        // Rust still projects the streaming failure, whose native code is null.
        let inventory = json!({
            "available":[{"id":"obs_x264"}], "videotoolbox_id":"hardware.h264",
            "native_logs_suppressed":true, "selected_id":"obs_x264",
            "selected_hardware":false, "fallback_reason":"VIDEOTOOLBOX_INITIALIZATION_FAILED"
        });
        let failed =
            legacy_encoding_status(inventory.clone(), &outputs, Some(RecordingEncoder::X264));
        assert_eq!(outputs.legacy_target(), Some(OutputTarget::Streaming));
        assert!(failed["selected_id"].is_null());
        assert_eq!(failed["selected_hardware"], false);
        assert!(failed["fallback_reason"].is_null());
        assert_eq!(failed["preference"], "videotoolbox");
        assert_eq!(failed["available"], inventory["available"]);
        assert_eq!(failed["videotoolbox_id"], inventory["videotoolbox_id"]);
        assert_eq!(failed["native_logs_suppressed"], true);

        outputs.streaming.recover().unwrap();
        // Changing the next selected profile cannot rewrite the completed
        // recording's requested policy or the fallback that actually occurred.
        let completed = legacy_encoding_status(
            inventory.clone(),
            &outputs,
            Some(RecordingEncoder::Videotoolbox),
        );
        assert_eq!(completed["preference"], "auto");
        assert_eq!(completed["selected_id"], "obs_x264");
        assert_eq!(
            completed["fallback_reason"],
            "VIDEOTOOLBOX_INITIALIZATION_FAILED"
        );

        for (target, kind) in [
            (OutputTarget::Recording, OutputKind::Recording),
            (OutputTarget::Streaming, OutputKind::Streaming),
        ] {
            outputs
                .get_mut(target)
                .begin(kind, OutputProfile::default(), video.clone(), None);
        }
        let multiple = legacy_encoding_status(inventory.clone(), &outputs, None);
        for key in [
            "selected_id",
            "selected_hardware",
            "fallback_reason",
            "preference",
        ] {
            assert!(multiple[key].is_null());
        }
        assert_eq!(multiple["available"], inventory["available"]);
    }
    #[test]
    fn encoder_projection_preserves_future_preference_before_first_attempt() {
        let value = legacy_encoding_status(
            json!({"available":[]}),
            &OutputRegistry::default(),
            Some(RecordingEncoder::X264),
        );
        assert_eq!(value["preference"], "x264");
        assert!(value["selected_id"].is_null());
    }
}
