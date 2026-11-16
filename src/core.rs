use crate::engine::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
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

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Status,
    Devices,
    SetOverlay { visible: bool },
    SetVariant { variant: Variant },
    SelectSource { window_id: Option<u32> },
    SelectAudio { id: String },
    SelectCamera { id: String },
    ReconnectSources,
    StartRecording,
    StartLocalStream,
    StopOutput,
    SaveProject,
    LoadProject,
    Snapshot,
}

pub fn parse_command(value: Value) -> anyhow::Result<Command> {
    let command: Command = serde_json::from_value(value.clone())?;
    let normalized = serde_json::to_value(&command)?;
    let actual = value
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("Command must be an object"))?;
    let expected = normalized.as_object().unwrap();
    anyhow::ensure!(
        actual.len() == expected.len() && actual.keys().all(|k| expected.contains_key(k)),
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
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WindowIdentity {
    pub bundle_id: String,
    pub title: String,
}
impl Default for Project {
    fn default() -> Self {
        Self {
            version: 2,
            variant: Variant::Horizontal,
            overlay: true,
            audio: "none".into(),
            capture_window: false,
            window: None,
            camera: None,
        }
    }
}

pub struct Production {
    pub engine: Engine,
    pub project: Project,
    pub revision: u64,
    pub last_action: String,
    pub output_kind: String,
    pub output_path: Option<String>,
    pub stopping: bool,
    pub window_id: Option<u32>,
    pub issues: Vec<&'static str>,
    pub recovery_required: bool,
    pub last_fault: Vec<&'static str>,
}

pub fn error(code: &str, message: impl ToString) -> Value {
    json!({"ok":false,"error":{"code":code,"message":message.to_string()}})
}

impl Production {
    pub fn new() -> anyhow::Result<Self> {
        fs::create_dir_all(data_dir().join("recordings"))?;
        fs::create_dir_all(data_dir().join("evidence"))?;
        create_tone()?;
        Ok(Self {
            engine: Engine::new()?,
            project: Project::default(),
            revision: 0,
            last_action: "Estudio iniciado".into(),
            output_kind: "idle".into(),
            output_path: None,
            stopping: false,
            window_id: None,
            issues: vec![],
            recovery_required: false,
            last_fault: vec![],
        })
    }
    pub fn status(&self) -> Value {
        let state = self.engine.output_state();
        let output = if self.engine.output_code() != 0 {
            "error"
        } else if state == 0 {
            "idle"
        } else if self.stopping {
            "stopping"
        } else {
            &self.output_kind
        };
        json!({"pid":std::process::id(),"revision":self.revision,"project":self.project,"issues":self.issues,
            "recovery_required":self.recovery_required,"last_fault":self.last_fault,
            "window_id":self.window_id,"output":output,"output_code":self.engine.output_code(),
            "output_path":self.output_path,"last_action":self.last_action,"libobs":self.engine.version(),
            "width":self.engine.width,"height":self.engine.height,"fps":30,"stats":self.engine.stats()})
    }
    pub fn poll_health(&mut self) {
        let issues = health_issues(self.engine.capture_health(), self.engine.audio_health());
        if !issues.is_empty() && self.engine.output_state() != 0 && !self.stopping {
            self.engine.stop_output();
            self.stopping = true;
            self.recovery_required = true;
            self.last_fault = issues.clone();
            self.revision += 1;
            self.last_action = format!(
                "Fuente perdida: {}. Salida finalizando; reconecta y vuelve a iniciar.",
                issues.join(", ")
            );
        }
        self.issues = issues;
    }
    fn idle(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.engine.output_state() == 0,
            "OUTPUT_BUSY: espera la finalización de la salida"
        );
        Ok(())
    }
    fn source_ready(&self) -> anyhow::Result<()> {
        let issues = health_issues(self.engine.capture_health(), self.engine.audio_health());
        anyhow::ensure!(
            issues.is_empty(),
            "{}: espera una fuente disponible con datos",
            issues.first().unwrap_or(&"SOURCE_UNAVAILABLE")
        );
        anyhow::ensure!(
            !self.recovery_required,
            "RECOVERY_REQUIRED: reconecta las fuentes antes de volver a iniciar"
        );
        Ok(())
    }
    fn audio(&mut self, id: &str) -> anyhow::Result<()> {
        anyhow::ensure!(
            !id.is_empty() && id.len() <= 512,
            "INVALID_ARGUMENT: entrada de audio inválida"
        );
        if id == self.project.audio && self.engine.audio_health() == 0 {
            return Ok(());
        }
        self.engine
            .audio(id, &data_dir().join("tone.wav").to_string_lossy())?;
        self.project.audio = id.to_owned();
        Ok(())
    }
    fn apply_project(&mut self, mut p: Project) -> anyhow::Result<()> {
        self.idle()?;
        anyhow::ensure!(
            p.version == 1 || p.version == 2,
            "PROJECT_VERSION_UNSUPPORTED"
        );
        anyhow::ensure!(
            !(p.capture_window && p.camera.is_some()),
            "INVALID_PROJECT: dos fuentes principales"
        );
        let devices = self.engine.devices();
        let window = if p.capture_window {
            anyhow::ensure!(
                devices["screen_permission"] == true,
                "SCREEN_PERMISSION_DENIED"
            );
            Some(resolve_window(&p, &devices)?)
        } else {
            None
        };
        if let Some(id) = &p.camera {
            anyhow::ensure!(
                devices["camera_permission"] == true,
                "CAMERA_PERMISSION_DENIED"
            );
            anyhow::ensure!(
                devices["cameras"]
                    .as_array()
                    .is_some_and(|a| a.iter().any(|v| v["id"] == *id)),
                "CAMERA_UNAVAILABLE"
            );
        }
        p.version = 2;
        if let Some(id) = window {
            p.window = window_identity(&devices, id);
        }
        if p.audio != "none" && p.audio != "tone" {
            anyhow::ensure!(
                devices["microphone_permission"] == true,
                "MICROPHONE_PERMISSION_DENIED"
            );
            anyhow::ensure!(
                devices["audio"]
                    .as_array()
                    .is_some_and(|a| a.iter().any(|v| v["id"] == p.audio)),
                "DEVICE_UNAVAILABLE"
            );
        }
        // Validate dependencies before mutation; restore previous settings on native failure.
        let old = self.project.clone();
        let old_window = self.window_id;
        let result = (|| {
            self.engine.variant(p.variant == Variant::Vertical)?;
            self.audio(&p.audio)?;
            if let Some(id) = &p.camera {
                self.engine.camera(id, false)?;
            } else {
                self.engine.source(window, false)?;
            }
            Ok::<_, anyhow::Error>(())
        })();
        if let Err(failure) = result {
            let rollback = (|| {
                self.engine.variant(old.variant == Variant::Vertical)?;
                self.audio(&old.audio)?;
                if let Some(id) = &old.camera {
                    self.engine.camera(id, false)?;
                } else {
                    self.engine.source(old_window, false)?;
                }
                Ok::<_, anyhow::Error>(())
            })();
            self.project = old;
            return Err(match rollback {
                Ok(()) => failure,
                Err(e) => anyhow::anyhow!("ROLLBACK_FAILED: {failure}; {e}"),
            });
        }
        self.engine.overlay(p.overlay);
        self.project = p;
        self.window_id = window;
        self.recovery_required = false;
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
        let label = serde_json::to_value(&command).unwrap()["op"]
            .as_str()
            .unwrap()
            .to_owned();
        let result = (|| -> anyhow::Result<()> {
            match command {
                Command::SetOverlay { visible } => {
                    self.engine.overlay(visible);
                    self.project.overlay = visible;
                }
                Command::SetVariant { variant } => {
                    self.idle()?;
                    self.engine.variant(variant == Variant::Vertical)?;
                    self.project.variant = variant;
                }
                Command::SelectSource { window_id } => {
                    self.idle()?;
                    let identity =
                        window_id.and_then(|id| window_identity(&self.engine.devices(), id));
                    self.engine.source(window_id, false)?;
                    self.window_id = window_id;
                    self.project.capture_window = window_id.is_some();
                    self.project.window = identity;
                    self.project.camera = None;
                    self.recovery_required = false;
                }
                Command::SelectAudio { id } => {
                    self.idle()?;
                    self.audio(&id)?;
                    self.recovery_required = false;
                }
                Command::SelectCamera { id } => {
                    self.idle()?;
                    anyhow::ensure!(
                        !id.is_empty() && id.len() < 512,
                        "INVALID_ARGUMENT: cámara inválida"
                    );
                    self.engine.camera(&id, false)?;
                    self.project.camera = Some(id);
                    self.project.capture_window = false;
                    self.project.window = None;
                    self.window_id = None;
                    self.recovery_required = false;
                }
                Command::ReconnectSources => {
                    self.idle()?;
                    if let Some(id) = &self.project.camera {
                        self.engine.camera(id, true)?;
                    } else {
                        self.engine.source(self.window_id, true)?;
                    }
                    self.engine.audio(
                        &self.project.audio,
                        &data_dir().join("tone.wav").to_string_lossy(),
                    )?;
                    self.recovery_required = false;
                }
                Command::StartRecording => {
                    self.idle()?;
                    self.source_ready()?;
                    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
                    let path = data_dir()
                        .join("recordings")
                        .join(format!("motive-{stamp}.mkv"));
                    fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(&path)?;
                    self.engine.start_output(&path.to_string_lossy(), false)?;
                    self.output_kind = "recording".into();
                    self.output_path = Some(path.to_string_lossy().into_owned());
                    self.stopping = false;
                }
                Command::StartLocalStream => {
                    self.idle()?;
                    self.source_ready()?;
                    self.engine.start_output("", true)?;
                    self.output_kind = "local_stream".into();
                    self.output_path = None;
                    self.stopping = false;
                }
                Command::StopOutput => {
                    self.engine.stop_output();
                    self.stopping = self.engine.output_state() != 0;
                }
                Command::SaveProject => {
                    let path = data_dir().join("project.json");
                    let temp = path.with_extension("json.tmp");
                    let bytes = serde_json::to_vec_pretty(&self.project)?;
                    let mut file = fs::File::create(&temp)?;
                    use std::io::Write;
                    file.write_all(&bytes)?;
                    file.sync_all()?;
                    fs::rename(temp, path)?;
                }
                Command::LoadProject => {
                    let bytes = fs::read(data_dir().join("project.json"))?;
                    anyhow::ensure!(bytes.len() <= 16384, "PROJECT_TOO_LARGE");
                    self.apply_project(serde_json::from_slice(&bytes)?)?;
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
                Command::Status | Command::Devices => unreachable!(),
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
                let msg = e.to_string();
                let prefix = msg.split(':').next().unwrap_or("");
                let code = if !prefix.is_empty()
                    && prefix.chars().all(|c| c.is_ascii_uppercase() || c == '_')
                {
                    prefix
                } else {
                    "OPERATION_FAILED"
                };
                error(code, &msg)
            }
        }
    }
}

fn health_issues(video: i32, audio: i32) -> Vec<&'static str> {
    let mut issues = vec![];
    if let Some(code) = match video {
        1 => Some("SOURCE_UNAVAILABLE"),
        2 => Some("CAPTURE_NOT_READY"),
        3 => Some("CAMERA_UNAVAILABLE"),
        4 => Some("CAMERA_PERMISSION_DENIED"),
        5 => Some("SCREEN_PERMISSION_DENIED"),
        _ => None,
    } {
        issues.push(code);
    }
    if let Some(code) = match audio {
        1 => Some("DEVICE_UNAVAILABLE"),
        2 => Some("MICROPHONE_PERMISSION_DENIED"),
        3 => Some("AUDIO_NOT_READY"),
        _ => None,
    } {
        issues.push(code);
    }
    issues
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
        ] {
            assert!(
                parse_command(serde_json::from_str(input).unwrap()).is_err(),
                "{input}"
            );
        }
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
