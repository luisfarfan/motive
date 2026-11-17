//! Global audio ownership; independent of project v3 and output profiles v1.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const MAX_INPUTS: usize = 8;
pub const MIN_GAIN_DB: f32 = -60.0;
pub const MAX_GAIN_DB: f32 = 24.0;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum AudioSource {
    Tone,
    Microphone { device_id: String },
}
impl AudioSource {
    pub fn device(&self) -> &str {
        match self {
            Self::Tone => "tone",
            Self::Microphone { device_id } => device_id,
        }
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        if let Self::Microphone { device_id } = self {
            anyhow::ensure!(
                !device_id.is_empty()
                    && device_id.len() < 512
                    && !device_id.chars().any(char::is_control)
                    && !["none", "tone", "default"].contains(&device_id.as_str()),
                "INVALID_AUDIO_DEVICE: use an explicit microphone UID"
            );
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AudioInput {
    pub id: String,
    pub name: String,
    pub source: AudioSource,
    pub gain_db: f32,
    pub muted: bool,
}
pub fn validate_gain(gain: f32) -> anyhow::Result<()> {
    anyhow::ensure!(
        gain.is_finite() && (MIN_GAIN_DB..=MAX_GAIN_DB).contains(&gain),
        "INVALID_AUDIO_GAIN: expected finite -60..24 dB"
    );
    Ok(())
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AudioStore {
    pub version: u32,
    pub next_id: u64,
    pub inputs: Vec<AudioInput>,
}
impl Default for AudioStore {
    fn default() -> Self {
        Self {
            version: 1,
            next_id: 1,
            inputs: vec![],
        }
    }
}
impl AudioStore {
    pub fn parse(bytes: &[u8]) -> anyhow::Result<Self> {
        anyhow::ensure!(bytes.len() <= 65536, "AUDIO_STORE_TOO_LARGE");
        let value: serde_json::Value = serde_json::from_slice(bytes)?;
        let store: Self = serde_json::from_value(value.clone())?;
        anyhow::ensure!(
            super::same_shape(&value, &serde_json::to_value(&store)?),
            "INVALID_AUDIO_STORE: unexpected or missing fields"
        );
        store.validate()?;
        Ok(store)
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(self.version == 1, "AUDIO_VERSION_UNSUPPORTED");
        anyhow::ensure!(self.inputs.len() <= MAX_INPUTS, "AUDIO_INPUT_LIMIT");
        anyhow::ensure!(
            self.next_id > 0 && self.next_id < u64::MAX,
            "INVALID_AUDIO_STORE: next_id"
        );
        let mut ids = BTreeSet::new();
        let mut devices = BTreeSet::new();
        for input in &self.inputs {
            let number = input
                .id
                .strip_prefix("audio-")
                .and_then(|n| n.parse::<u64>().ok());
            anyhow::ensure!(
                number.is_some_and(|n| n > 0 && n < self.next_id) && ids.insert(&input.id),
                "INVALID_AUDIO_STORE: input id"
            );
            anyhow::ensure!(crate::scene::valid_name(&input.name), "INVALID_AUDIO_NAME");
            input.source.validate()?;
            validate_gain(input.gain_db)?;
            anyhow::ensure!(
                devices.insert(input.source.device()),
                "AUDIO_DEVICE_DUPLICATE"
            );
        }
        Ok(())
    }
    pub fn input(&self, id: &str) -> anyhow::Result<&AudioInput> {
        self.inputs
            .iter()
            .find(|i| i.id == id)
            .ok_or_else(|| anyhow::anyhow!("AUDIO_INPUT_NOT_FOUND"))
    }
    /// Adding an existing device returns its stable channel; never resets gain/mute.
    pub fn add(&mut self, name: String, source: AudioSource) -> anyhow::Result<String> {
        source.validate()?;
        anyhow::ensure!(crate::scene::valid_name(&name), "INVALID_AUDIO_NAME");
        if let Some(input) = self.inputs.iter().find(|i| i.source == source) {
            return Ok(input.id.clone());
        }
        anyhow::ensure!(self.inputs.len() < MAX_INPUTS, "AUDIO_INPUT_LIMIT");
        anyhow::ensure!(self.next_id < u64::MAX - 1, "AUDIO_INPUT_LIMIT");
        let id = format!("audio-{}", self.next_id);
        self.next_id += 1;
        self.inputs.push(AudioInput {
            id: id.clone(),
            name,
            source,
            gain_db: -6.0,
            muted: false,
        });
        Ok(id)
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AudioPhase {
    Warming,
    Ready,
    Disconnected,
    Failed,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AudioIssueCode {
    DeviceUnavailable,
    MicrophonePermissionDenied,
    AudioNotReady,
    AudioCreateFailed,
    AudioDisconnected,
    AudioStalled,
    AudioStateUnavailable,
    AudioInputClipping,
    AudioMixClipping,
    AudioHeadroomLow,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct AudioLevels {
    pub frames: u64,
    pub timestamp_ns: u64,
    pub age_ms: Option<u64>,
    pub stale: bool,
    pub peak_dbfs: [Option<f32>; 2],
    pub rms_dbfs: [Option<f32>; 2],
    pub input_peak_dbfs: [Option<f32>; 2],
    pub clipped_blocks: u64,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AudioInputRuntime {
    pub id: String,
    pub instance_id: u64,
    pub phase: AudioPhase,
    pub issue: Option<AudioIssueCode>,
    pub levels: AudioLevels,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct AudioRuntime {
    pub available: bool,
    pub instances_created: u64,
    pub inputs: Vec<AudioInputRuntime>,
    pub mix: AudioLevels,
}
#[derive(Clone, Debug, Serialize)]
pub struct AudioIssue {
    pub input_id: Option<String>,
    pub code: AudioIssueCode,
    pub severity: &'static str,
    pub recovery: &'static str,
}
pub type AudioLifecycle = Vec<(String, u64, AudioPhase, Option<AudioIssueCode>)>;
impl AudioRuntime {
    pub fn issues(&self) -> Vec<AudioIssue> {
        let mut issues = vec![];
        if !self.available {
            issues.push(AudioIssue {
                input_id: None,
                code: AudioIssueCode::AudioStateUnavailable,
                severity: "error",
                recovery: "restart_studio",
            });
        }
        for input in &self.inputs {
            if let Some(code) = input.issue {
                issues.push(AudioIssue {
                    input_id: Some(input.id.clone()),
                    code,
                    severity: if input.phase == AudioPhase::Disconnected {
                        "info"
                    } else {
                        "error"
                    },
                    recovery: if input.phase == AudioPhase::Warming {
                        "wait_for_samples"
                    } else {
                        "reconnect_audio_input"
                    },
                });
            }
            if input.levels.clipped_blocks > 0 {
                issues.push(AudioIssue {
                    input_id: Some(input.id.clone()),
                    code: AudioIssueCode::AudioInputClipping,
                    severity: "warning",
                    recovery: "reduce_device_gain",
                });
            }
        }
        if self.mix.clipped_blocks > 0 {
            issues.push(AudioIssue {
                input_id: None,
                code: AudioIssueCode::AudioMixClipping,
                severity: "warning",
                recovery: "reduce_input_gain",
            });
        } else if self.mix.peak_dbfs.iter().flatten().any(|db| *db > -1.0) {
            issues.push(AudioIssue {
                input_id: None,
                code: AudioIssueCode::AudioHeadroomLow,
                severity: "warning",
                recovery: "reduce_input_gain",
            });
        }
        issues
    }
    pub fn ready(&self) -> bool {
        self.available
            && self
                .inputs
                .iter()
                .all(|i| matches!(i.phase, AudioPhase::Ready | AudioPhase::Disconnected))
    }
    pub fn lifecycle(&self) -> AudioLifecycle {
        self.inputs
            .iter()
            .map(|i| (i.id.clone(), i.instance_id, i.phase, i.issue))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_identity_is_unique_and_controls_survive_reuse() {
        let mut store = AudioStore::default();
        let source = AudioSource::Microphone {
            device_id: "test-explicit-uid".into(),
        };
        let id = store.add("Microphone".into(), source.clone()).unwrap();
        store.inputs[0].gain_db = -12.0;
        store.inputs[0].muted = true;
        let original = store.clone();
        assert_eq!(store.add("Again".into(), source).unwrap(), id);
        assert_eq!(store, original);
        store.validate().unwrap();
        store.inputs.push(store.inputs[0].clone());
        store.inputs[1].id = "audio-2".into();
        store.next_id = 3;
        assert!(
            store
                .validate()
                .unwrap_err()
                .to_string()
                .contains("AUDIO_DEVICE_DUPLICATE")
        );
    }
    #[test]
    fn rejects_nonfinite_gain_implicit_devices_and_future_versions() {
        for gain in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -60.1, 24.1] {
            assert!(validate_gain(gain).is_err());
        }
        for id in ["", "default", "none", "tone", "uid\0suffix"] {
            assert!(
                AudioSource::Microphone {
                    device_id: id.into()
                }
                .validate()
                .is_err()
            );
        }
        let mut store = AudioStore::default();
        store.add("Tone".into(), AudioSource::Tone).unwrap();
        let serialized = serde_json::to_vec(&store).unwrap();
        assert_eq!(
            serde_json::from_slice::<AudioStore>(&serialized).unwrap(),
            store
        );
        store.version = 2;
        assert!(store.validate().is_err());
        store.version = 1;
        store.next_id = 1;
        assert!(store.validate().is_err());
    }
    #[test]
    fn persisted_audio_rejects_unit_variant_extras_and_unknown_fields() {
        let mut store = AudioStore::default();
        store.add("Tone".into(), AudioSource::Tone).unwrap();
        let bytes = serde_json::to_vec(&store).unwrap();
        assert_eq!(AudioStore::parse(&bytes).unwrap(), store);
        let mut invalid = serde_json::to_value(store).unwrap();
        invalid["inputs"][0]["source"]["path"] = serde_json::json!("/tmp/arbitrary.wav");
        assert!(AudioStore::parse(&serde_json::to_vec(&invalid).unwrap()).is_err());
        invalid["inputs"][0]["source"]
            .as_object_mut()
            .unwrap()
            .remove("path");
        invalid["monitoring"] = serde_json::json!(true);
        assert!(AudioStore::parse(&serde_json::to_vec(&invalid).unwrap()).is_err());
        assert!(AudioStore::parse(&vec![b' '; 65537]).is_err());
    }
    #[test]
    fn silence_is_ready_but_stalled_capture_is_not_and_clipping_is_a_warning() {
        let mut runtime = AudioRuntime {
            available: true,
            ..AudioRuntime::default()
        };
        runtime.inputs.push(AudioInputRuntime {
            id: "audio-1".into(),
            instance_id: 1,
            phase: AudioPhase::Ready,
            issue: None,
            levels: AudioLevels::default(),
        });
        assert!(runtime.ready());
        runtime.mix.clipped_blocks = 4;
        assert!(runtime.ready());
        assert_eq!(runtime.issues()[0].severity, "warning");
        runtime.inputs[0].phase = AudioPhase::Failed;
        runtime.inputs[0].issue = Some(AudioIssueCode::AudioStalled);
        assert!(!runtime.ready());
        runtime.inputs[0].phase = AudioPhase::Disconnected;
        runtime.inputs[0].issue = Some(AudioIssueCode::AudioDisconnected);
        assert!(runtime.ready());
    }
}
