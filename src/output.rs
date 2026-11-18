//! Output definitions are separate from project-v3 scenes and runtime selection.
use super::RecordingEncoder;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub fn valid_credential_ref(reference: &str) -> bool {
    reference.len() == 39
        && reference.starts_with("kc_")
        && reference.bytes().enumerate().skip(3).all(|(i, b)| {
            if [11, 16, 21, 26].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

pub fn credential_code(code: i32) -> &'static str {
    match code {
        0 => "available",
        1 => "CREDENTIAL_MISSING",
        2 => "CREDENTIAL_ACCESS_DENIED",
        4 => "INVALID_CREDENTIAL_REFERENCE",
        5 => "CREDENTIAL_BINDING_MISMATCH",
        _ => "KEYCHAIN_UNAVAILABLE",
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OutputTarget {
    Recording,
    Streaming,
}
impl OutputTarget {
    pub const ALL: [Self; 2] = [Self::Recording, Self::Streaming];
    pub fn index(self) -> u32 {
        match self {
            Self::Recording => 0,
            Self::Streaming => 1,
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::Recording => "recording",
            Self::Streaming => "streaming",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OutputPhase {
    #[default]
    Idle,
    Starting,
    Connecting,
    Active,
    Stopping,
    Error,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OutputKind {
    Recording,
    Streaming,
    LocalStream,
}
impl OutputKind {
    pub fn name(self) -> &'static str {
        match self {
            Self::Recording => "recording",
            Self::Streaming => "streaming",
            Self::LocalStream => "local_stream",
        }
    }
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OutputStats {
    pub output_bytes: u64,
    pub output_frames: u32,
    pub output_dropped_frames: i32,
    pub encoded_frames: Option<u32>,
}
/// Dispatch observations from official libobs callbacks, not delivery receipts.
/// Missing disk/network/decode counts remain unavailable until independently
/// measured; a successful native stop does not verify the resulting file.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OutputDiagnostics {
    pub version: u8,
    pub packet_observer_available: bool,
    pub observed_video_packets: Option<u64>,
    pub observed_audio_packets: Option<u64>,
    pub trace_capacity: u32,
    pub trace_retained_records: u32,
    pub trace_overwritten_records: u64,
    pub trace_missed_records: u64,
    pub stop_requested_ns: Option<u64>,
    pub stop_call_returned_ns: Option<u64>,
    pub stop_signal_ns: Option<u64>,
    pub quiescent_observed_ns: Option<u64>,
    pub stop_to_quiescence_ms: Option<u64>,
    pub frames_written: Option<u64>,
    pub frames_received: Option<u64>,
    pub frames_decoded: Option<u64>,
    pub delivery_verified: bool,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OutputEncoding {
    pub selected_id: Option<String>,
    pub selected_hardware: bool,
    pub fallback_reason: Option<String>,
    #[serde(default)]
    pub preference: Option<RecordingEncoder>,
}
/// A native observation is not a command acknowledgement. State 0 is emitted
/// only after the per-output OBS/H8 barrier, including the RTMP worker check.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeOutput {
    pub state: u8,
    pub code: i32,
    pub active_duration_ms: u64,
    pub encoding: OutputEncoding,
    pub stats: OutputStats,
    #[serde(default)]
    pub diagnostics: Option<OutputDiagnostics>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct OutputFailure {
    pub code: String,
    pub native_code: Option<i32>,
    pub recovery: &'static str,
}
pub fn native_failure(code: i32) -> Option<OutputFailure> {
    let name = match code {
        0 => return None,
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
    Some(OutputFailure {
        code: name.into(),
        native_code: Some(code),
        recovery: "explicit",
    })
}
#[derive(Clone, Debug, Serialize)]
pub struct OutputVideo {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
}
#[derive(Clone, Debug, Serialize)]
pub struct OutputRuntime {
    pub target: OutputTarget,
    pub attempt_id: Option<u64>,
    pub kind: Option<OutputKind>,
    pub phase: OutputPhase,
    pub native_busy: bool,
    pub cancel_requested: bool,
    pub cancel_deferred: bool,
    pub recovery_required: bool,
    pub failure: Option<OutputFailure>,
    pub profile: Option<OutputProfile>,
    pub video: Option<OutputVideo>,
    pub encoding: OutputEncoding,
    pub path: Option<String>,
    pub stats: OutputStats,
    pub diagnostics: Option<OutputDiagnostics>,
    pub active_duration_ms: u64,
    #[serde(skip)]
    pub native_state: u8,
}
impl OutputRuntime {
    fn new(target: OutputTarget) -> Self {
        Self {
            target,
            attempt_id: None,
            kind: None,
            phase: OutputPhase::Idle,
            native_busy: false,
            cancel_requested: false,
            cancel_deferred: false,
            recovery_required: false,
            failure: None,
            profile: None,
            video: None,
            encoding: OutputEncoding::default(),
            path: None,
            stats: OutputStats::default(),
            diagnostics: None,
            active_duration_ms: 0,
            native_state: 0,
        }
    }
    pub fn can_start(&self) -> anyhow::Result<()> {
        anyhow::ensure!(!self.native_busy, "OUTPUT_BUSY");
        anyhow::ensure!(!self.recovery_required, "RECOVERY_REQUIRED");
        anyhow::ensure!(
            self.attempt_id != Some(u64::MAX),
            "OUTPUT_ATTEMPT_EXHAUSTED"
        );
        Ok(())
    }
    pub fn begin(
        &mut self,
        kind: OutputKind,
        profile: OutputProfile,
        video: OutputVideo,
        path: Option<String>,
    ) {
        let attempt_id = Some(self.attempt_id.unwrap_or(0) + 1);
        *self = Self {
            attempt_id,
            kind: Some(kind),
            phase: OutputPhase::Starting,
            native_busy: true,
            native_state: 4,
            profile: Some(profile),
            video: Some(video),
            path,
            ..Self::new(self.target)
        };
    }
    pub fn observe(&mut self, observation: NativeOutput) -> bool {
        let previous = (
            self.phase,
            self.native_busy,
            self.failure.clone(),
            self.cancel_deferred,
        );
        self.native_state = observation.state;
        self.native_busy = observation.state != 0;
        self.active_duration_ms = observation.active_duration_ms;
        self.stats = observation.stats;
        self.diagnostics = observation.diagnostics;
        self.encoding = observation.encoding;
        self.encoding.preference = self.profile.as_ref().map(|p| p.encoder);
        if let Some(failure) = native_failure(observation.code) {
            self.failure = Some(failure);
            self.recovery_required = true;
        }
        self.cancel_deferred = self.cancel_requested && observation.state == 3;
        self.phase = if !self.native_busy {
            if self.recovery_required {
                OutputPhase::Error
            } else {
                OutputPhase::Idle
            }
        } else if self.recovery_required || (self.cancel_requested && observation.state != 3) {
            OutputPhase::Stopping
        } else {
            match observation.state {
                1 => OutputPhase::Active,
                2 => OutputPhase::Stopping,
                3 => OutputPhase::Connecting,
                _ => OutputPhase::Starting,
            }
        };
        previous
            != (
                self.phase,
                self.native_busy,
                self.failure.clone(),
                self.cancel_deferred,
            )
    }
    pub fn request_cancel(&mut self) {
        if self.native_busy {
            self.cancel_requested = true;
            self.cancel_deferred = self.native_state == 3;
            if !self.cancel_deferred {
                self.phase = OutputPhase::Stopping;
            }
        }
    }
    pub fn fail_start(&mut self, error: &anyhow::Error) {
        // Never retain an arbitrary plugin message (it may contain credentials).
        let message = error.to_string();
        let prefix = message.split(':').next().unwrap_or("");
        let code =
            if !prefix.is_empty() && prefix.chars().all(|c| c.is_ascii_uppercase() || c == '_') {
                prefix
            } else {
                "OUTPUT_START_FAILED"
            };
        self.failure = Some(OutputFailure {
            code: code.into(),
            native_code: None,
            recovery: "explicit",
        });
        self.recovery_required = true;
        self.phase = if self.native_busy {
            OutputPhase::Stopping
        } else {
            OutputPhase::Error
        };
    }
    pub fn recover(&mut self) -> anyhow::Result<()> {
        anyhow::ensure!(!self.native_busy, "OUTPUT_BUSY");
        self.failure = None;
        self.recovery_required = false;
        self.cancel_requested = false;
        self.cancel_deferred = false;
        self.phase = OutputPhase::Idle;
        Ok(())
    }
    pub fn legacy_state(&self) -> &'static str {
        match self.phase {
            OutputPhase::Idle => "idle",
            OutputPhase::Error => "error",
            OutputPhase::Connecting if self.cancel_requested => "cancel_pending",
            OutputPhase::Connecting => "connecting",
            OutputPhase::Stopping => "stopping",
            OutputPhase::Starting => "starting",
            OutputPhase::Active => self.kind.map_or("idle", OutputKind::name),
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct OutputRegistry {
    pub recording: OutputRuntime,
    pub streaming: OutputRuntime,
    #[serde(skip)]
    pub last_target: OutputTarget,
}
impl Default for OutputRegistry {
    fn default() -> Self {
        Self {
            recording: OutputRuntime::new(OutputTarget::Recording),
            streaming: OutputRuntime::new(OutputTarget::Streaming),
            last_target: OutputTarget::Recording,
        }
    }
}
impl OutputRegistry {
    pub fn get(&self, target: OutputTarget) -> &OutputRuntime {
        match target {
            OutputTarget::Recording => &self.recording,
            OutputTarget::Streaming => &self.streaming,
        }
    }
    pub fn get_mut(&mut self, target: OutputTarget) -> &mut OutputRuntime {
        match target {
            OutputTarget::Recording => &mut self.recording,
            OutputTarget::Streaming => &mut self.streaming,
        }
    }
    pub fn busy(&self) -> bool {
        self.recording.native_busy || self.streaming.native_busy
    }
    pub fn recovery_required(&self) -> bool {
        self.recording.recovery_required || self.streaming.recovery_required
    }
    pub fn legacy_target(&self) -> Option<OutputTarget> {
        let relevant: Vec<_> = OutputTarget::ALL
            .into_iter()
            .filter(|t| {
                let slot = self.get(*t);
                slot.native_busy || slot.recovery_required
            })
            .collect();
        match relevant.as_slice() {
            [] => Some(self.last_target),
            [target] => Some(*target),
            _ => None,
        }
    }
    pub fn unique_busy(&self) -> anyhow::Result<Option<OutputTarget>> {
        let busy: Vec<_> = OutputTarget::ALL
            .into_iter()
            .filter(|t| self.get(*t).native_busy)
            .collect();
        anyhow::ensure!(busy.len() <= 1, "OUTPUT_TARGET_REQUIRED");
        Ok(busy.first().copied())
    }
    pub fn legacy_recovery_target(&self) -> anyhow::Result<Option<OutputTarget>> {
        anyhow::ensure!(!self.busy(), "OUTPUT_BUSY");
        let failed: Vec<_> = OutputTarget::ALL
            .into_iter()
            .filter(|t| self.get(*t).recovery_required)
            .collect();
        anyhow::ensure!(failed.len() <= 1, "OUTPUT_TARGET_REQUIRED");
        Ok(failed.first().copied())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RateControl {
    Cbr,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum OutputWarningCode {
    FrameReorderingTailRisk,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct OutputWarning {
    pub code: OutputWarningCode,
    pub message: &'static str,
    pub recommendation: &'static str,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OutputProfile {
    pub id: String,
    pub encoder: RecordingEncoder,
    pub bitrate_kbps: u32,
    pub rate_control: RateControl,
    pub keyframe_seconds: u32,
    pub frame_reordering: bool,
}
impl Default for OutputProfile {
    fn default() -> Self {
        Self {
            id: "standard".into(),
            encoder: RecordingEncoder::Auto,
            bitrate_kbps: 2500,
            rate_control: RateControl::Cbr,
            keyframe_seconds: 2,
            frame_reordering: false,
        }
    }
}
impl OutputProfile {
    /// Saved profiles retain their setting, but unsafe modes cannot start.
    pub fn warnings(&self) -> Vec<OutputWarning> {
        if self.frame_reordering {
            vec![OutputWarning {
                code: OutputWarningCode::FrameReorderingTailRisk,
                message: "Este perfil no puede iniciar: el reordenamiento produjo saltos de video y pérdida de audio al finalizar.",
                recommendation: "Desactiva el reordenamiento y aplica el perfil. El ajuste guardado se conserva hasta que lo cambies explícitamente.",
            }]
        } else {
            Vec::new()
        }
    }
    pub fn validate_for_output(&self) -> anyhow::Result<()> {
        self.validate()?;
        anyhow::ensure!(
            !self.frame_reordering,
            "FRAME_REORDERING_UNSUPPORTED: Desactiva el reordenamiento y aplica el perfil antes de iniciar la salida"
        );
        Ok(())
    }
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            !self.id.is_empty()
                && self.id.len() <= 48
                && self
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"-_".contains(&b)),
            "INVALID_PROFILE: invalid id"
        );
        anyhow::ensure!(
            (250..=20000).contains(&self.bitrate_kbps),
            "INVALID_PROFILE: bitrate must be 250..20000 kbps"
        );
        anyhow::ensure!(
            (1..=10).contains(&self.keyframe_seconds),
            "INVALID_PROFILE: keyframes must be 1..10 seconds"
        );
        Ok(())
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProfileStore {
    pub version: u32,
    pub profiles: Vec<OutputProfile>,
}
impl Default for ProfileStore {
    fn default() -> Self {
        Self {
            version: 1,
            profiles: vec![OutputProfile::default()],
        }
    }
}
impl ProfileStore {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.version == 1 && !self.profiles.is_empty() && self.profiles.len() <= 16,
            "INVALID_PROFILES: version 1 and 1..16 profiles required"
        );
        let mut ids = BTreeSet::new();
        for p in &self.profiles {
            p.validate()?;
            anyhow::ensure!(ids.insert(&p.id), "INVALID_PROFILES: duplicate id");
        }
        Ok(())
    }
    pub fn get(&self, id: &str) -> anyhow::Result<&OutputProfile> {
        self.profiles
            .iter()
            .find(|p| p.id == id)
            .ok_or_else(|| anyhow::anyhow!("PROFILE_UNAVAILABLE"))
    }
    pub fn upsert(&mut self, profile: OutputProfile) -> anyhow::Result<()> {
        profile.validate()?;
        if let Some(old) = self.profiles.iter_mut().find(|p| p.id == profile.id) {
            *old = profile;
        } else {
            anyhow::ensure!(self.profiles.len() < 16, "PROFILE_LIMIT");
            self.profiles.push(profile);
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Transport {
    Rtmp,
    Rtmps,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalEndpoint {
    pub transport: Transport,
    pub port: u16,
}
impl LocalEndpoint {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.port >= 1024,
            "INVALID_ENDPOINT: use an unprivileged loopback port"
        );
        Ok(())
    }
    pub fn url(&self) -> String {
        let scheme = match self.transport {
            Transport::Rtmp => "rtmp",
            Transport::Rtmps => "rtmps",
        };
        format!("{scheme}://127.0.0.1:{}/live", self.port)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn observation(state: u8, code: i32, frames: u32) -> NativeOutput {
        NativeOutput {
            state,
            code,
            active_duration_ms: u64::from(frames) * 33,
            encoding: OutputEncoding::default(),
            diagnostics: None,
            stats: OutputStats {
                output_frames: frames,
                encoded_frames: Some(frames),
                ..OutputStats::default()
            },
        }
    }
    fn begin(slot: &mut OutputRuntime) {
        slot.can_start().unwrap();
        let kind = if slot.target == OutputTarget::Recording {
            OutputKind::Recording
        } else {
            OutputKind::Streaming
        };
        slot.begin(
            kind,
            OutputProfile::default(),
            OutputVideo {
                width: 1920,
                height: 1080,
                fps: 30,
            },
            None,
        );
    }
    #[test]
    fn failure_and_recovery_are_local_to_one_output() {
        let mut registry = OutputRegistry::default();
        begin(&mut registry.recording);
        registry.recording.observe(observation(1, 0, 120));
        assert!(registry.streaming.can_start().is_ok());
        begin(&mut registry.streaming);
        registry.streaming.observe(observation(1, 0, 90));
        assert!(registry.unique_busy().is_err());
        registry.streaming.observe(observation(2, -5, 100));
        assert_eq!(registry.streaming.phase, OutputPhase::Stopping);
        assert!(registry.streaming.recover().is_err());
        assert!(registry.streaming.can_start().is_err());
        assert_eq!(registry.recording.phase, OutputPhase::Active);
        registry.streaming.observe(observation(0, -5, 100));
        assert_eq!(registry.streaming.phase, OutputPhase::Error);
        assert_eq!(registry.legacy_target(), None);
        assert_eq!(
            registry.unique_busy().unwrap(),
            Some(OutputTarget::Recording)
        );
        assert!(registry.legacy_recovery_target().is_err());
        registry.streaming.recover().unwrap();
        assert_eq!(registry.streaming.stats.output_frames, 100);
        assert_eq!(registry.recording.stats.output_frames, 120);
        begin(&mut registry.streaming);
        assert_eq!(registry.streaming.attempt_id, Some(2));
        assert_eq!(registry.recording.attempt_id, Some(1));
    }
    #[test]
    fn deferred_cancel_remains_busy_until_native_worker_barrier() {
        let mut slot = OutputRuntime::new(OutputTarget::Streaming);
        begin(&mut slot);
        slot.observe(observation(3, 0, 0));
        for _ in 0..6 {
            slot.request_cancel();
        }
        assert_eq!(slot.phase, OutputPhase::Connecting);
        assert!(slot.cancel_requested && slot.cancel_deferred && slot.native_busy);
        assert_eq!(slot.legacy_state(), "cancel_pending");
        assert!(slot.recover().is_err());
        slot.observe(observation(1, 0, 1));
        assert_eq!(slot.phase, OutputPhase::Stopping);
        assert!(!slot.cancel_deferred);
        slot.observe(observation(2, 0, 2));
        assert!(slot.native_busy);
        slot.observe(observation(0, 0, 2));
        assert_eq!(slot.phase, OutputPhase::Idle);
        assert!(!slot.native_busy);
        begin(&mut slot);
        assert!(!slot.cancel_requested && !slot.cancel_deferred);
    }
    #[test]
    fn native_failure_during_connect_cannot_claim_terminal_state() {
        let mut slot = OutputRuntime::new(OutputTarget::Streaming);
        begin(&mut slot);
        slot.observe(observation(3, -2, 0));
        assert_eq!(slot.phase, OutputPhase::Stopping);
        assert!(slot.native_busy && slot.recovery_required);
        assert!(slot.recover().is_err());
        slot.observe(observation(0, -2, 0));
        assert_eq!(slot.phase, OutputPhase::Error);
        assert_eq!(slot.failure.as_ref().unwrap().native_code, Some(-2));
        slot.recover().unwrap();
        assert!(!slot.recovery_required);
    }
    #[test]
    fn multiple_faults_require_target_and_failed_start_is_structured() {
        let mut registry = OutputRegistry::default();
        for target in OutputTarget::ALL {
            let slot = registry.get_mut(target);
            begin(slot);
            slot.observe(observation(0, 0, 0));
            slot.fail_start(&anyhow::anyhow!("OUTPUT_START_FAILED: secret-response"));
            assert!(slot.can_start().is_err());
        }
        assert!(registry.legacy_recovery_target().is_err());
        assert_eq!(registry.legacy_target(), None);
        let serialized = serde_json::to_string(&registry).unwrap();
        assert!(!serialized.contains("secret-response"));
        assert!(!serialized.contains("last_target"));
        registry.recording.recover().unwrap();
        assert_eq!(
            registry.legacy_recovery_target().unwrap(),
            Some(OutputTarget::Streaming)
        );
    }
    #[test]
    fn credential_references_are_opaque_and_cannot_encode_urls() {
        assert!(valid_credential_ref(
            "kc_12345678-1234-1234-1234-123456abcdef"
        ));
        for value in [
            "",
            "rtmps://localhost/key",
            "kc_12345678-1234-1234-1234-123456abcdeF",
            "kc_1234567811234-1234-1234-123456abcdef",
            "key\nsecret",
        ] {
            assert!(!valid_credential_ref(value));
        }
    }
    #[test]
    fn bounded_profiles_and_versioned_roundtrip() {
        let mut store = ProfileStore::default();
        store.validate().unwrap();
        let mut p = OutputProfile {
            bitrate_kbps: 0,
            ..OutputProfile::default()
        };
        assert!(store.upsert(p.clone()).is_err());
        p.bitrate_kbps = 4000;
        p.keyframe_seconds = 0;
        assert!(store.upsert(p.clone()).is_err());
        p.keyframe_seconds = 1;
        p.id = "../../secret".into();
        assert!(store.upsert(p.clone()).is_err());
        p.id = "local-test".into();
        store.upsert(p).unwrap();
        let restored: ProfileStore =
            serde_json::from_slice(&serde_json::to_vec(&store).unwrap()).unwrap();
        restored.validate().unwrap();
        assert_eq!(restored.profiles, store.profiles);
        store.profiles.push(store.profiles[0].clone());
        assert!(store.validate().is_err());
        store.version = 2;
        assert!(store.validate().is_err());
    }
    #[test]
    fn default_avoids_reordering_without_migrating_saved_v1_profiles() {
        assert!(!OutputProfile::default().frame_reordering);
        assert!(OutputProfile::default().warnings().is_empty());
        OutputProfile::default().validate_for_output().unwrap();
        let saved = serde_json::json!({"version":1,"profiles":[{
            "id":"saved","encoder":"auto","bitrate_kbps":4000,
            "rate_control":"cbr","keyframe_seconds":2,"frame_reordering":true
        }]});
        let restored: ProfileStore = serde_json::from_value(saved.clone()).unwrap();
        restored.validate().unwrap();
        assert_eq!(serde_json::to_value(&restored).unwrap(), saved);
        let warnings = restored.profiles[0].warnings();
        assert_eq!(warnings.len(), 1);
        assert_eq!(warnings[0].code, OutputWarningCode::FrameReorderingTailRisk);
        assert_eq!(
            serde_json::to_value(warnings).unwrap()[0]["code"],
            "FRAME_REORDERING_TAIL_RISK"
        );
        for encoder in [
            RecordingEncoder::Auto,
            RecordingEncoder::Videotoolbox,
            RecordingEncoder::X264,
        ] {
            let mut p = restored.profiles[0].clone();
            p.encoder = encoder;
            assert!(!p.warnings().is_empty());
            assert!(
                p.validate_for_output()
                    .unwrap_err()
                    .to_string()
                    .starts_with("FRAME_REORDERING_UNSUPPORTED:")
            );
            p.frame_reordering = false;
            assert!(p.warnings().is_empty());
            p.validate_for_output().unwrap();
        }
    }
    #[test]
    fn endpoints_never_accept_urls_credentials_or_public_hosts() {
        let e = LocalEndpoint {
            transport: Transport::Rtmp,
            port: 19351,
        };
        e.validate().unwrap();
        assert_eq!(e.url(), "rtmp://127.0.0.1:19351/live");
        for field in ["host", "url", "key", "password", "credential_ref"] {
            let mut v = serde_json::to_value(&e).unwrap();
            v[field] = serde_json::json!("secret");
            assert!(serde_json::from_value::<LocalEndpoint>(v).is_err());
        }
        assert!(LocalEndpoint { port: 0, ..e }.validate().is_err());
    }
}
