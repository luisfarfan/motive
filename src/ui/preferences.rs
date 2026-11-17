//! Presentation preferences only. Project, output and audio settings stay in Production.
use serde::{Deserialize, Serialize};
#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Preferences {
    pub version: u32,
    pub dark: bool,
    pub safe_margin: bool,
}
impl Preferences {
    pub fn load() -> Self {
        std::fs::read(crate::core::data_dir().join("ui-preferences.json"))
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Self>(&bytes).ok())
            .filter(|p| p.version == 1)
            .unwrap_or(Self {
                version: 1,
                ..Self::default()
            })
    }
    pub fn save(&self) -> anyhow::Result<()> {
        use std::io::Write;
        use std::os::unix::fs::OpenOptionsExt;
        let dir = crate::core::data_dir();
        std::fs::create_dir_all(&dir)?;
        let temp = dir.join("ui-preferences.json.tmp");
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(&temp)?;
        f.write_all(&serde_json::to_vec_pretty(self)?)?;
        f.sync_all()?;
        std::fs::rename(temp, dir.join("ui-preferences.json"))?;
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::Preferences;
    #[test]
    fn presentation_schema_rejects_multimedia_state() {
        assert!(
            serde_json::from_str::<Preferences>(
                r#"{"version":1,"dark":true,"safe_margin":false,"stream_key":"no"}"#
            )
            .is_err()
        );
    }
}
