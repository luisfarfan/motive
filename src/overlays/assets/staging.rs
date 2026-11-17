//! Native picker capability only. No serialized command accepts this path.
use super::*;
use std::{fs::OpenOptions, os::unix::fs::OpenOptionsExt};

/// Own the private copy until the core's import worker reports a terminal result.
/// Dropping a cancelled/failed UI request also removes its copy, never the original.
pub struct StagedImport {
    directory: File,
    file: File,
    name: String,
}
impl StagedImport {
    pub fn file_name(&self) -> &str {
        &self.name
    }
}
impl Drop for StagedImport {
    fn drop(&mut self) {
        if let Ok(current) = open_at(
            &self.directory,
            &self.name,
            libc::O_RDONLY | libc::O_NONBLOCK,
            0,
        ) && same_file(&current, &self.file).unwrap_or(false)
        {
            let _ = unlink_at(&self.directory, &self.name);
        }
    }
}
impl AssetCatalog {
    /// Call only with the path returned by the native, user-operated file picker.
    /// The selected file is read once, with a bounded copy and no final symlink.
    /// This is not isolation from other processes running as the same user.
    pub fn stage_selected_file(&self, selected: &Path) -> anyhow::Result<StagedImport> {
        ensure!(selected.is_absolute(), "ASSET_SELECTION_UNAVAILABLE");
        let mut input = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(selected)
            .context("ASSET_SELECTION_UNAVAILABLE")?;
        let before = input.metadata().context("ASSET_SELECTION_UNAVAILABLE")?;
        ensure!(before.is_file(), "UNSAFE_ASSET_FILE: select a regular file");
        ensure!(
            before.len() > 0 && before.len() <= MAX_FILE_BYTES,
            "ASSET_SIZE_LIMIT"
        );
        let directory = self
            .imports
            .try_clone()
            .context("ASSET_IMPORT_UNAVAILABLE")?;
        let name = format!(
            "picked-{}-{}",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let file = open_at(
            &directory,
            &name,
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        let mut staged = StagedImport {
            directory,
            file,
            name,
        };
        let copied = std::io::copy(
            &mut Read::by_ref(&mut input).take(MAX_FILE_BYTES + 1),
            &mut staged.file,
        )
        .context("ASSET_COPY_FAILED")?;
        let after = input.metadata().context("ASSET_SELECTION_UNAVAILABLE")?;
        ensure!(
            copied == before.len()
                && copied <= MAX_FILE_BYTES
                && before.len() == after.len()
                && before.mtime() == after.mtime()
                && before.mtime_nsec() == after.mtime_nsec()
                && before.ctime() == after.ctime()
                && before.ctime_nsec() == after.ctime_nsec(),
            "ASSET_CHANGED_DURING_IMPORT"
        );
        staged.file.sync_all().context("ASSET_COPY_FAILED")?;
        Ok(staged)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::overlays::assets::tests::Fixture;
    use std::{fs, os::unix::fs::symlink};

    #[test]
    fn picker_copy_import_repair_and_cleanup_preserve_original() {
        let f = Fixture::new();
        let catalog = f.catalog();
        let original = f.0.join("selected.png");
        image::RgbaImage::from_pixel(12, 8, image::Rgba([8, 32, 55, 90]))
            .save(&original)
            .unwrap();
        let bytes = fs::read(&original).unwrap();
        let staged = catalog.stage_selected_file(&original).unwrap();
        let copy = f.0.join("imports").join(staged.file_name());
        assert_eq!(fs::metadata(&copy).unwrap().mode() & 0o777, 0o600);
        let asset = catalog.import(staged.file_name()).unwrap();
        fs::remove_file(catalog.resolve(&asset.id).unwrap()).unwrap();
        assert!(catalog.list().is_err());
        assert!(catalog.inventory().unwrap()[0].error.is_some());
        assert_eq!(catalog.import(staged.file_name()).unwrap(), asset);
        assert!(catalog.inventory().unwrap()[0].error.is_none());
        drop(staged);
        assert!(!copy.exists());
        assert_eq!(fs::read(&original).unwrap(), bytes);
    }
    #[test]
    fn picker_rejects_symlink_fifo_directory_empty_and_oversized_without_copies() {
        let f = Fixture::new();
        let catalog = f.catalog();
        let file = f.0.join("original");
        fs::write(&file, b"data").unwrap();
        let link = f.0.join("link");
        symlink(&file, &link).unwrap();
        assert!(catalog.stage_selected_file(&link).is_err());
        let fifo = f.0.join("fifo");
        let name = CString::new(fifo.as_os_str().as_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o600) }, 0);
        assert!(catalog.stage_selected_file(&fifo).is_err());
        assert!(catalog.stage_selected_file(&f.0).is_err());
        File::create(&file).unwrap();
        assert!(catalog.stage_selected_file(&file).is_err());
        File::create(&file)
            .unwrap()
            .set_len(MAX_FILE_BYTES + 1)
            .unwrap();
        assert!(catalog.stage_selected_file(&file).is_err());
        assert_eq!(fs::read_dir(f.0.join("imports")).unwrap().count(), 0);
    }
    #[test]
    fn cleanup_does_not_remove_a_replaced_inbox_entry() {
        let f = Fixture::new();
        let catalog = f.catalog();
        let original = f.0.join("original");
        fs::write(&original, b"authorized bytes").unwrap();
        let staged = catalog.stage_selected_file(&original).unwrap();
        let copy = f.0.join("imports").join(staged.file_name());
        fs::remove_file(&copy).unwrap();
        fs::write(&copy, b"replacement").unwrap();
        drop(staged);
        assert_eq!(fs::read(copy).unwrap(), b"replacement");
    }
}
