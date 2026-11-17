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
}
