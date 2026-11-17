//! Bounded local observations. These files do not certify muxer delivery.
use anyhow::{Result, ensure};
use std::{
    fs,
    io::Write,
    os::unix::fs::OpenOptionsExt,
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};

pub fn write_shutdown(directory: &Path, snapshot: &serde_json::Value) -> Result<()> {
    let bytes = serde_json::to_vec(snapshot)?;
    ensure!(bytes.len() <= 1024 * 1024, "DIAGNOSTIC_SIZE_LIMIT");
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let temporary = directory.join(format!(".shutdown-{}-{nonce}.tmp", std::process::id()));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&temporary)?;
    let result = (|| -> Result<()> {
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, directory.join("last-shutdown.json"))?;
        fs::File::open(directory)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    #[test]
    fn shutdown_snapshot_replaces_link_without_writing_its_target() {
        let dir = std::env::temp_dir().join(format!(
            "motive-diagnostic-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&dir).unwrap();
        let target = dir.join("untouched");
        fs::write(&target, "original").unwrap();
        symlink(&target, dir.join("last-shutdown.json")).unwrap();
        write_shutdown(
            &dir,
            &serde_json::json!({"version":1,"delivery_verified":false}),
        )
        .unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "original");
        assert_eq!(
            fs::metadata(dir.join("last-shutdown.json"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        assert!(
            !fs::symlink_metadata(dir.join("last-shutdown.json"))
                .unwrap()
                .file_type()
                .is_symlink()
        );
        fs::remove_dir_all(dir).unwrap();
    }
}
