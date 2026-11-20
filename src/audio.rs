//! Global audio ownership; independent of project v3 and output profiles v1.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const MAX_INPUTS: usize = 8;
pub const MIN_GAIN_DB: f32 = -60.0;
pub const MAX_GAIN_DB: f32 = 24.0;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum AudioSource {
    Tone,
    Microphone { device_id: String },
    SystemApplication { bundle_id: String },
    SystemDesktop { display_uuid: String },
}
impl AudioSource {
    /// System sources never impersonate a microphone UID.
    pub fn legacy_device(&self) -> Option<&str> {
        match self {
            Self::Tone => Some("tone"),
            Self::Microphone { device_id } => Some(device_id),
            Self::SystemApplication { .. } | Self::SystemDesktop { .. } => None,
        }
    }
    /// Stable FFI discriminants; these are not OBS plugin IDs.
    pub fn native_kind(&self) -> u32 {
        match self {
            Self::Tone => 0,
            Self::Microphone { .. } => 1,
            Self::SystemApplication { .. } => 2,
            Self::SystemDesktop { .. } => 3,
        }
    }
    pub fn native_target(&self) -> &str {
        match self {
            Self::Tone => "tone",
            Self::Microphone { device_id } => device_id,
            Self::SystemApplication { bundle_id } => bundle_id,
            Self::SystemDesktop { display_uuid } => display_uuid,
        }
    }
    pub fn is_system(&self) -> bool {
        matches!(
            self,
            Self::SystemApplication { .. } | Self::SystemDesktop { .. }
        )
    }
    fn overlaps(&self, other: &Self) -> bool {
        self.is_system()
            && other.is_system()
            && (matches!(self, Self::SystemDesktop { .. })
                || matches!(other, Self::SystemDesktop { .. }))
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
        if let Self::SystemApplication { bundle_id } = self {
            anyhow::ensure!(
                !bundle_id.is_empty()
                    && bundle_id.len() < 256
                    && bundle_id.contains('.')
                    && bundle_id.split('.').all(|part| !part.is_empty())
                    && bundle_id
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-'),
                "INVALID_AUDIO_APPLICATION: use an explicit bundle identifier"
            );
        }
        if let Self::SystemDesktop { display_uuid } = self {
            anyhow::ensure!(
                display_uuid.len() == 36
                    && display_uuid.bytes().enumerate().all(|(i, b)| {
                        if matches!(i, 8 | 13 | 18 | 23) {
                            b == b'-'
                        } else {
                            b.is_ascii_digit() || (b'A'..=b'F').contains(&b)
                        }
                    }),
                "INVALID_AUDIO_DISPLAY: use the canonical UUID from system_audio_sources"
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
        anyhow::ensure!(matches!(self.version, 1 | 2), "AUDIO_VERSION_UNSUPPORTED");
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
                input.id.len() < 64
                    && number.is_some_and(|n| {
                        n > 0 && n < self.next_id && input.id == format!("audio-{n}")
                    })
                    && ids.insert(&input.id),
                "INVALID_AUDIO_STORE: input id"
            );
            anyhow::ensure!(crate::scene::valid_name(&input.name), "INVALID_AUDIO_NAME");
            input.source.validate()?;
            anyhow::ensure!(
                self.version >= 2 || !input.source.is_system(),
                "AUDIO_VERSION_UNSUPPORTED: system sources require mixer v2"
            );
            validate_gain(input.gain_db)?;
            anyhow::ensure!(devices.insert(&input.source), "AUDIO_DEVICE_DUPLICATE");
        }
        for (index, input) in self.inputs.iter().enumerate() {
            anyhow::ensure!(
                !self.inputs[index + 1..]
                    .iter()
                    .any(|other| input.source.overlaps(&other.source)),
                "AUDIO_CAPTURE_OVERLAP: desktop and application capture cannot coexist"
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
        anyhow::ensure!(
            !self.inputs.iter().any(|i| source.overlaps(&i.source)),
            "AUDIO_CAPTURE_OVERLAP: desktop and application capture cannot coexist"
        );
        anyhow::ensure!(self.inputs.len() < MAX_INPUTS, "AUDIO_INPUT_LIMIT");
        anyhow::ensure!(self.next_id < u64::MAX - 1, "AUDIO_INPUT_LIMIT");
        let id = format!("audio-{}", self.next_id);
        if source.is_system() {
            self.version = 2;
        }
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
    /// SCK stream exists, but recent packets have not been observed. Not silence.
    AwaitingAudio,
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
    ScreenPermissionDenied,
    SystemAudioUnavailable,
    SystemAudioEnumerationFailed,
    ApplicationUnavailable,
    ApplicationIdentityUnavailable,
    ApplicationAmbiguous,
    DisplayUnavailable,
    SystemAudioSelfCapture,
    SystemAudioStreamStopped,
    SystemAudioNoSamples,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SystemAudioPermission {
    Authorized,
    NotAuthorized,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SystemAudioApplication {
    pub bundle_id: String,
    pub name: String,
    pub running_instances: u32,
    pub selectable: bool,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SystemAudioDisplay {
    pub display_uuid: String,
    pub name: String,
    pub is_main: bool,
    pub selectable: bool,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SystemAudioSources {
    pub available: bool,
    pub permission: SystemAudioPermission,
    pub issue: Option<AudioIssueCode>,
    pub applications: Vec<SystemAudioApplication>,
    pub displays: Vec<SystemAudioDisplay>,
    pub excludes_current_process: bool,
    pub desktop_main_display_only: bool,
    pub overlap_policy: String,
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
pub struct ApplicationIdentityObservation {
    pub checked_ns: u64,
    pub expected_pid: i32,
    pub registered_instances: u32,
    pub observed_pid: i32,
    pub registered_terminated: bool,
    pub pinned_process_present: bool,
    pub pinned_process_terminated: bool,
    pub pinned_bundle_matches: bool,
    #[serde(default)]
    pub process_probe: String,
    #[serde(default)]
    pub process_generation_matches: bool,
    #[serde(default)]
    pub process_executable_matches: bool,
    #[serde(default)]
    pub catalog_absence_observations: u64,
    #[serde(default)]
    pub identity_scope: String,
    pub reason: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AudioInputRuntime {
    pub id: String,
    pub instance_id: u64,
    pub phase: AudioPhase,
    pub issue: Option<AudioIssueCode>,
    pub levels: AudioLevels,
    /// Last identity observation; retained after failure, not a reconnect grant.
    #[serde(default)]
    pub application_identity: Option<ApplicationIdentityObservation>,
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
                    severity: if matches!(
                        input.phase,
                        AudioPhase::Disconnected | AudioPhase::AwaitingAudio
                    ) {
                        "info"
                    } else {
                        "error"
                    },
                    recovery: if matches!(
                        input.phase,
                        AudioPhase::Warming | AudioPhase::AwaitingAudio
                    ) {
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
            && self.inputs.iter().all(|i| {
                matches!(
                    i.phase,
                    AudioPhase::Ready | AudioPhase::AwaitingAudio | AudioPhase::Disconnected
                )
            })
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
        store.version = 3;
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
    fn persisted_audio_ids_are_canonical_and_fit_the_native_registry() {
        let mut store = AudioStore::default();
        store.add("Tone".into(), AudioSource::Tone).unwrap();
        let original = store.clone();
        for invalid in [
            "audio-01".to_owned(),
            "audio-+1".to_owned(),
            format!("audio-{}1", "0".repeat(80)),
            "audio-1\0suffix".to_owned(),
            "audio-١".to_owned(),
            "audio-0".to_owned(),
            "restore-0".to_owned(),
        ] {
            store.inputs[0].id = invalid;
            assert!(
                store
                    .validate()
                    .unwrap_err()
                    .to_string()
                    .contains("INVALID_AUDIO_STORE: input id")
            );
            assert!(AudioStore::parse(&serde_json::to_vec(&store).unwrap()).is_err());
        }
        // Both ordinary generated IDs and the largest allocatable ID round-trip;
        // canonicalization does not renumber an existing valid channel.
        assert_eq!(
            AudioStore::parse(&serde_json::to_vec(&original).unwrap()).unwrap(),
            original
        );
        store.next_id = u64::MAX - 1;
        store.inputs[0].id = format!("audio-{}", u64::MAX - 2);
        assert_eq!(
            AudioStore::parse(&serde_json::to_vec(&store).unwrap()).unwrap(),
            store
        );
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
            application_identity: None,
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
    #[test]
    fn system_capture_promotes_version_and_reuses_identity_without_controls_reset() {
        let mut store = AudioStore::default();
        store.add("Tone".into(), AudioSource::Tone).unwrap();
        assert_eq!(store.version, 1);
        let source = AudioSource::SystemApplication {
            bundle_id: "local.motive.audiofixture".into(),
        };
        let id = store.add("Fixture".into(), source.clone()).unwrap();
        assert_eq!(store.version, 2);
        store.inputs[1].gain_db = -18.0;
        store.inputs[1].muted = true;
        let original = store.clone();
        assert_eq!(store.add("Again".into(), source).unwrap(), id);
        assert_eq!(store, original);
        assert_eq!(
            AudioStore::parse(&serde_json::to_vec(&store).unwrap()).unwrap(),
            store
        );
        store.version = 1;
        assert!(AudioStore::parse(&serde_json::to_vec(&store).unwrap()).is_err());
    }
    #[test]
    fn rejects_overlap_in_both_orders_without_mutation_and_on_restore() {
        let application = AudioSource::SystemApplication {
            bundle_id: "local.motive.audiofixture".into(),
        };
        let desktop = AudioSource::SystemDesktop {
            display_uuid: "00112233-4455-6677-8899-AABBCCDDEEFF".into(),
        };
        for (first, second) in [
            (application.clone(), desktop.clone()),
            (desktop, application),
        ] {
            let mut store = AudioStore::default();
            store.add("First".into(), first).unwrap();
            store.inputs[0].muted = true;
            let original = store.clone();
            assert!(
                store
                    .add("Second".into(), second.clone())
                    .unwrap_err()
                    .to_string()
                    .contains("AUDIO_CAPTURE_OVERLAP")
            );
            assert_eq!(store, original);
            store.inputs.push(AudioInput {
                id: "audio-2".into(),
                name: "Second".into(),
                source: second,
                gain_db: -6.0,
                muted: true,
            });
            store.next_id = 3;
            assert!(
                AudioStore::parse(&serde_json::to_vec(&store).unwrap())
                    .unwrap_err()
                    .to_string()
                    .contains("AUDIO_CAPTURE_OVERLAP")
            );
        }
    }
    #[test]
    fn system_identity_is_typed_explicit_and_has_no_legacy_device() {
        let mut store = AudioStore::default();
        for source in [
            AudioSource::Microphone {
                device_id: "local.motive.audiofixture".into(),
            },
            AudioSource::SystemApplication {
                bundle_id: "local.motive.audiofixture".into(),
            },
            AudioSource::SystemApplication {
                bundle_id: "local.motive.secondfixture".into(),
            },
        ] {
            store.add("Input".into(), source).unwrap();
        }
        store.validate().unwrap();
        assert!(store.inputs[1].source.legacy_device().is_none());
        assert_eq!(store.inputs[1].source.native_kind(), 2);
        for bundle in [
            "",
            "default",
            "123",
            "local..fixture",
            ".local.fixture",
            "local.fixture.",
            "local/fixture",
            "local.fixture\0suffix",
        ] {
            assert!(
                AudioSource::SystemApplication {
                    bundle_id: bundle.into()
                }
                .validate()
                .is_err()
            );
        }
        for uuid in [
            "",
            "main",
            "default",
            "1",
            "00112233-4455-6677-8899-aabbccddeeff",
            "00112233-4455-6677-8899-AABBCCDDEEFG",
        ] {
            assert!(
                AudioSource::SystemDesktop {
                    display_uuid: uuid.into()
                }
                .validate()
                .is_err()
            );
        }
    }
    #[test]
    fn absent_system_packets_are_nonfatal_but_never_claim_measured_silence() {
        let mut runtime = AudioRuntime {
            available: true,
            ..AudioRuntime::default()
        };
        runtime.inputs.push(AudioInputRuntime {
            id: "audio-1".into(),
            instance_id: 1,
            phase: AudioPhase::AwaitingAudio,
            issue: Some(AudioIssueCode::SystemAudioNoSamples),
            application_identity: None,
            levels: AudioLevels {
                stale: true,
                ..AudioLevels::default()
            },
        });
        assert!(runtime.ready());
        assert_eq!(runtime.issues()[0].severity, "info");
        assert_eq!(runtime.issues()[0].recovery, "wait_for_samples");
        assert!(runtime.inputs[0].levels.stale);
        assert_eq!(runtime.inputs[0].levels.frames, 0);
        runtime.inputs[0].phase = AudioPhase::Failed;
        runtime.inputs[0].issue = Some(AudioIssueCode::SystemAudioStreamStopped);
        assert!(!runtime.ready());
        assert_eq!(runtime.issues()[0].recovery, "reconnect_audio_input");
    }

    #[test]
    fn legacy_identity_observation_does_not_claim_os_verification() {
        let observation: ApplicationIdentityObservation =
            serde_json::from_value(serde_json::json!({
                "checked_ns": 42, "expected_pid": 123, "registered_instances": 0,
                "observed_pid": 0, "registered_terminated": false,
                "pinned_process_present": false, "pinned_process_terminated": false,
                "pinned_bundle_matches": false, "reason": "no_registered_instance"
            }))
            .unwrap();
        assert!(observation.process_probe.is_empty());
        assert!(!observation.process_generation_matches);
        assert!(!observation.process_executable_matches);
        assert_eq!(observation.catalog_absence_observations, 0);
    }

    #[test]
    fn unobservable_application_identity_is_a_failed_input() {
        let issue: AudioIssueCode =
            serde_json::from_str("\"APPLICATION_IDENTITY_UNAVAILABLE\"").unwrap();
        assert_eq!(issue, AudioIssueCode::ApplicationIdentityUnavailable);
        let runtime = AudioRuntime {
            available: true,
            inputs: vec![AudioInputRuntime {
                id: "audio-1".into(),
                instance_id: 1,
                phase: AudioPhase::Failed,
                issue: Some(issue),
                application_identity: None,
                levels: AudioLevels::default(),
            }],
            ..AudioRuntime::default()
        };
        assert!(!runtime.ready());
        assert_eq!(runtime.issues()[0].severity, "error");
    }
}
