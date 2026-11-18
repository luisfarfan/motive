//! Explicit configuration persistence only. Jobs, permits and replay state are
//! intentionally absent. Journals remain separate and are never auto-replayed.
use motive_show_control::{deck::Deck, model::Error, runtime::Config};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::Path,
};
const MAX_BYTES: usize = 1024 * 1024;
#[derive(Clone, Debug, Serialize)]
pub struct WriteReceipt {
    pub document_sha256: String,
    pub bytes: usize,
    pub durable: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct SavedConfiguration {
    pub version: u16,
    pub project_fingerprint: String,
    pub config: Config,
    pub deck: Deck,
}
fn fail() -> Error {
    Error::new(
        "SHOW_CONTROL_STORE",
        "Configuration storage is invalid, unavailable or durability is uncertain",
    )
}
impl SavedConfiguration {
    pub(super) fn validate(&self) -> Result<(), Error> {
        if self.version != 1
            || self.project_fingerprint.len() != 64
            || !self
                .project_fingerprint
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(Error::new(
                "SHOW_CONTROL_STORE_VERSION",
                "Configuration requires v1 and an exact project binding fingerprint",
            ));
        }
        super::bind_deck(self.config.clone(), &self.deck)?;
        Ok(())
    }
    pub(super) fn read(path: &Path) -> Result<Self, Error> {
        private_parent(path)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)
            .map_err(|_| fail())?;
        let metadata = file.metadata().map_err(|_| fail())?;
        if !metadata.is_file()
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.permissions().mode() & 0o777 != 0o600
            || metadata.len() > MAX_BYTES as u64
        {
            return Err(fail());
        }
        let mut bytes = Vec::new();
        file.take((MAX_BYTES + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| fail())?;
        if bytes.len() > MAX_BYTES {
            return Err(fail());
        }
        let configuration: Self = serde_json::from_slice(&bytes).map_err(|_| fail())?;
        configuration.validate()?;
        Ok(configuration)
    }
    pub(super) fn save(&self, path: &Path, session: &str) -> Result<WriteReceipt, Error> {
        self.validate()?;
        let directory = private_parent(path)?;
        if let Ok(metadata) = path.symlink_metadata()
            && (!metadata.is_file()
                || metadata.uid() != unsafe { libc::geteuid() }
                || metadata.permissions().mode() & 0o777 != 0o600)
        {
            return Err(fail());
        }
        let bytes = serde_json::to_vec_pretty(self).map_err(|_| fail())?;
        if bytes.len() > MAX_BYTES {
            return Err(Error::new(
                "SHOW_CONTROL_STORE_LIMIT",
                "Configuration exceeds 1 MiB",
            ));
        }
        // session is a native random identifier, never an RPC path component.
        if session.len() != 32 || !session.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(fail());
        }
        let temporary = path.with_file_name(format!(".configuration-{session}.tmp"));
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&temporary)
            .map_err(|_| fail())?;
        let mut owned = true;
        let result = (|| {
            file.write_all(&bytes).map_err(|_| fail())?;
            file.sync_all().map_err(|_| fail())?;
            fs::rename(&temporary, path).map_err(|_| fail())?;
            owned = false;
            directory.sync_all().map_err(|_| fail())
        })();
        if owned {
            let _ = fs::remove_file(temporary);
        }
        result?;
        Ok(WriteReceipt {
            document_sha256: format!("{:x}", Sha256::digest(&bytes)),
            bytes: bytes.len(),
            durable: true,
        })
    }
}
fn private_parent(path: &Path) -> Result<File, Error> {
    if !path.is_absolute() {
        return Err(fail());
    }
    let parent = path.parent().ok_or_else(fail)?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(parent)
        .map_err(|_| fail())?;
    let metadata = file.metadata().map_err(|_| fail())?;
    if !metadata.is_dir()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.permissions().mode() & 0o777 != 0o700
    {
        return Err(fail());
    }
    Ok(file)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{DirBuilderExt, symlink};
    #[test]
    fn versioned_store_is_private_closed_and_contains_no_resume_authority() {
        let (config, deck) = super::super::tests::inputs();
        let value = SavedConfiguration {
            version: 1,
            project_fingerprint: "a".repeat(64),
            config,
            deck,
        };
        let directory = std::env::temp_dir().join(format!(
            "motive-show-store-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::DirBuilder::new()
            .mode(0o700)
            .create(&directory)
            .unwrap();
        let path = directory.join("configuration.json");
        let receipt = value.save(&path, &"b".repeat(32)).unwrap();
        let saved = fs::read(&path).unwrap();
        assert!(receipt.durable);
        assert_eq!(receipt.bytes, saved.len());
        assert_eq!(
            receipt.document_sha256,
            format!("{:x}", Sha256::digest(&saved))
        );
        assert_eq!(SavedConfiguration::read(&path).unwrap().version, 1);
        assert_eq!(path.metadata().unwrap().permissions().mode() & 0o777, 0o600);
        let mut document = serde_json::to_value(&value).unwrap();
        document["jobs"] = serde_json::json!([]);
        assert!(serde_json::from_value::<SavedConfiguration>(document).is_err());
        let mut wrong = value.clone();
        wrong.version = 2;
        assert!(wrong.save(&path, &"b".repeat(32)).is_err());
        assert_eq!(fs::read(&path).unwrap(), saved);
        fs::remove_file(&path).unwrap();
        let target = directory.join("unrelated");
        fs::write(&target, b"preserve").unwrap();
        symlink(&target, &path).unwrap();
        assert!(value.save(&path, &"b".repeat(32)).is_err());
        assert!(SavedConfiguration::read(&path).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"preserve");
        fs::remove_dir_all(directory).unwrap();
    }
}
