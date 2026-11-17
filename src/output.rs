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
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RateControl {
    Cbr,
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
            frame_reordering: true,
        }
    }
}
impl OutputProfile {
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
