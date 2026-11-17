//! Bounded recording metadata on a worker, never media validation on the owner.
//! Only Motive-generated basenames inside the configured recording directory
//! are admitted. No source, capture, encoder or media clock is owned here.
use crate::core::output::{OutputPhase, OutputRuntime};
use serde::Serialize;
use std::{
    ffi::{CStr, CString},
    fs::File,
    os::{
        fd::{AsRawFd, FromRawFd, IntoRawFd},
        unix::ffi::OsStrExt,
    },
    path::{Component, Path, PathBuf},
    sync::mpsc::{self, Receiver, TryRecvError},
    time::{SystemTime, UNIX_EPOCH},
};

pub const SCAN_LIMIT: usize = 1024;
pub const DISPLAY_LIMIT: usize = 100;

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct LibraryError {
    pub code: &'static str,
}
impl std::fmt::Display for LibraryError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.code)
    }
}
impl std::error::Error for LibraryError {}
fn error(code: &'static str) -> LibraryError {
    LibraryError { code }
}
type Result<T> = std::result::Result<T, LibraryError>;

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RecordingState {
    Writing,
    Finalizing,
    Error,
    ClosedUnverified,
}

#[derive(Clone, Debug, Serialize)]
pub struct Recording {
    pub id: String,
    pub bytes: u64,
    pub modified_unix_ms: Option<u64>,
    pub state: RecordingState,
    pub failure_code: Option<String>,
    pub attempt_id: Option<u64>,
    pub media_verified: bool,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ScanPhase {
    Idle,
    Scanning,
    Ready,
    Error,
}

#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub version: u8,
    pub directory: String,
    pub phase: ScanPhase,
    pub error: Option<LibraryError>,
    pub observed_unix_ms: Option<u64>,
    pub scan_limit: usize,
    pub display_limit: usize,
    pub scanned_entries: usize,
    pub omitted_entries: usize,
    pub truncated: bool,
    pub items: Vec<Recording>,
}

#[derive(Clone, Debug)]
struct FileEntry {
    id: String,
    bytes: u64,
    modified_unix_ms: Option<u64>,
}
#[derive(Default)]
struct Scan {
    entries: Vec<FileEntry>,
    observed_unix_ms: Option<u64>,
    scanned_entries: usize,
    omitted_entries: usize,
    truncated: bool,
}

pub struct Library {
    directory: PathBuf,
    pending: Option<Receiver<Result<Scan>>>,
    scan: Scan,
    phase: ScanPhase,
    error: Option<LibraryError>,
}
impl Library {
    pub fn new() -> Self {
        Self::at(crate::paths::recordings_dir())
    }
    fn at(directory: PathBuf) -> Self {
        Self {
            directory,
            pending: None,
            scan: Scan::default(),
            phase: ScanPhase::Idle,
            error: None,
        }
    }
    pub fn busy(&self) -> bool {
        self.pending.is_some()
    }

    /// Admission belongs to Production, which rejects this during shutdown.
    /// A worker owns only its path and metadata; dropping this object never
    /// joins it on the UI thread. Normal shutdown must poll until !busy().
    pub fn refresh(&mut self) -> Result<()> {
        if self.busy() {
            return Err(error("RECORDING_SCAN_BUSY"));
        }
        let directory = self.directory.clone();
        let (send, receive) = mpsc::channel();
        std::thread::Builder::new()
            .name("motive-recordings".into())
            .spawn(move || {
                let _ = send.send(scan_directory(&directory));
            })
            .map_err(|_| error("RECORDING_SCAN_UNAVAILABLE"))?;
        self.pending = Some(receive);
        self.phase = ScanPhase::Scanning;
        self.error = None;
        Ok(())
    }

    pub fn poll(&mut self) {
        let Some(receiver) = &self.pending else {
            return;
        };
        let result = match receiver.try_recv() {
            Ok(result) => result,
            Err(TryRecvError::Empty) => return,
            Err(TryRecvError::Disconnected) => Err(error("RECORDING_SCAN_UNAVAILABLE")),
        };
        self.pending = None;
        match result {
            Ok(scan) => {
                self.scan = scan;
                self.phase = ScanPhase::Ready;
                self.error = None;
            }
            Err(error) => {
                self.phase = ScanPhase::Error;
                self.error = Some(error);
            }
        }
    }

    /// Pure projection of cached disk metadata and the current output owner.
    /// Old files and files from previous processes remain unverified. No inode,
    /// extension, byte count or successful stop is treated as a decode receipt.
    pub fn snapshot(&self, output: &OutputRuntime) -> Snapshot {
        let items = self
            .scan
            .entries
            .iter()
            .map(|entry| {
                let owns = output
                    .path
                    .as_deref()
                    .is_some_and(|p| Path::new(p) == self.directory.join(&entry.id));
                let state = if owns && output.native_busy {
                    if output.cancel_requested
                        || output.phase == OutputPhase::Stopping
                        || output.failure.is_some()
                    {
                        RecordingState::Finalizing
                    } else {
                        RecordingState::Writing
                    }
                } else if owns && (output.failure.is_some() || output.recovery_required) {
                    RecordingState::Error
                } else {
                    RecordingState::ClosedUnverified
                };
                Recording {
                    id: entry.id.clone(),
                    bytes: entry.bytes,
                    modified_unix_ms: entry.modified_unix_ms,
                    state,
                    failure_code: if owns {
                        output.failure.as_ref().map(|f| f.code.clone())
                    } else {
                        None
                    },
                    attempt_id: if owns { output.attempt_id } else { None },
                    media_verified: false,
                }
            })
            .collect();
        Snapshot {
            version: 1,
            directory: self.directory.to_string_lossy().into_owned(),
            phase: self.phase,
            error: self.error.clone(),
            observed_unix_ms: self.scan.observed_unix_ms,
            scan_limit: SCAN_LIMIT,
            display_limit: DISPLAY_LIMIT,
            scanned_entries: self.scan.scanned_entries,
            omitted_entries: self.scan.omitted_entries,
            truncated: self.scan.truncated,
            items,
        }
    }
}

fn valid_id(id: &str) -> bool {
    let Some(stamp) = id
        .strip_prefix("motive-")
        .and_then(|s| s.strip_suffix(".mkv"))
    else {
        return false;
    };
    (1..=24).contains(&stamp.len()) && stamp.bytes().all(|b| b.is_ascii_digit())
}

/// Open every directory component without following symbolic links. Only a
/// trusted configured absolute directory reaches this function; API clients
/// never provide a directory or a filesystem path.
fn open_directory(directory: &Path) -> Result<File> {
    if !directory.is_absolute() {
        return Err(error("RECORDINGS_DIRECTORY_INVALID"));
    }
    let mut parent = File::open("/").map_err(|_| error("RECORDINGS_DIRECTORY_UNAVAILABLE"))?;
    for component in directory.components() {
        let Component::Normal(name) = component else {
            if component == Component::RootDir {
                continue;
            }
            return Err(error("RECORDINGS_DIRECTORY_INVALID"));
        };
        let name =
            CString::new(name.as_bytes()).map_err(|_| error("RECORDINGS_DIRECTORY_INVALID"))?;
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY
                    | libc::O_DIRECTORY
                    | libc::O_NOFOLLOW
                    | libc::O_CLOEXEC
                    | libc::O_NONBLOCK,
            )
        };
        if fd < 0 {
            return Err(error("RECORDINGS_DIRECTORY_UNAVAILABLE"));
        }
        parent = unsafe { File::from_raw_fd(fd) };
    }
    Ok(parent)
}

struct Directory(*mut libc::DIR);
impl Drop for Directory {
    fn drop(&mut self) {
        unsafe {
            libc::closedir(self.0);
        }
    }
}

fn scan_directory(directory: &Path) -> Result<Scan> {
    let file = open_directory(directory)?;
    let fd = file.into_raw_fd();
    let raw = unsafe { libc::fdopendir(fd) };
    if raw.is_null() {
        unsafe {
            libc::close(fd);
        }
        return Err(error("RECORDINGS_DIRECTORY_UNAVAILABLE"));
    }
    let directory = Directory(raw);
    let mut scan = Scan::default();
    loop {
        unsafe {
            *libc::__error() = 0;
        }
        let entry = unsafe { libc::readdir(directory.0) };
        if entry.is_null() {
            if unsafe { *libc::__error() } != 0 {
                return Err(error("RECORDING_SCAN_FAILED"));
            }
            break;
        }
        let bytes = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) };
        if matches!(bytes.to_bytes(), b"." | b"..") {
            continue;
        }
        if scan.scanned_entries == SCAN_LIMIT {
            scan.truncated = true;
            break;
        }
        scan.scanned_entries += 1;
        let Ok(id) = bytes.to_str() else {
            scan.omitted_entries += 1;
            continue;
        };
        if !valid_id(id) {
            scan.omitted_entries += 1;
            continue;
        }
        let mut stat: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstatat(fd, bytes.as_ptr(), &mut stat, libc::AT_SYMLINK_NOFOLLOW) } != 0
            || stat.st_mode & libc::S_IFMT != libc::S_IFREG
            || stat.st_nlink != 1
            || stat.st_size < 0
        {
            scan.omitted_entries += 1;
            continue;
        }
        let modified = u64::try_from(stat.st_mtime)
            .ok()
            .and_then(|seconds| seconds.checked_mul(1000))
            .and_then(|ms| ms.checked_add(u64::try_from(stat.st_mtime_nsec).ok()? / 1_000_000));
        scan.entries.push(FileEntry {
            id: id.into(),
            bytes: stat.st_size as u64,
            modified_unix_ms: modified,
        });
    }
    scan.entries.sort_by(|a, b| {
        b.modified_unix_ms
            .cmp(&a.modified_unix_ms)
            .then_with(|| b.id.cmp(&a.id))
    });
    if scan.entries.len() > DISPLAY_LIMIT {
        scan.truncated = true;
        scan.omitted_entries += scan.entries.len() - DISPLAY_LIMIT;
        scan.entries.truncate(DISPLAY_LIMIT);
    }
    scan.observed_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|d| u64::try_from(d.as_millis()).ok());
    Ok(scan)
}

/// A local UI action obtains this on a background worker. The descriptor stays
/// alive through dispatch to Finder. Revealing is not opening or validating media.
/// This does not claim to sandbox another process with the same user's authority.
pub struct RevealCapability {
    path: PathBuf,
    _file: File,
    _directory: File,
}
impl RevealCapability {
    pub fn path(&self) -> &Path {
        &self.path
    }
}
pub fn prepare_reveal(id: &str) -> Result<RevealCapability> {
    prepare_reveal_in(&crate::paths::recordings_dir(), id)
}
fn prepare_reveal_in(directory: &Path, id: &str) -> Result<RevealCapability> {
    if !valid_id(id) {
        return Err(error("INVALID_RECORDING_ID"));
    }
    let parent = open_directory(directory)?;
    let name = CString::new(id).map_err(|_| error("INVALID_RECORDING_ID"))?;
    let mut before: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::fstatat(
            parent.as_raw_fd(),
            name.as_ptr(),
            &mut before,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
        || before.st_mode & libc::S_IFMT != libc::S_IFREG
        || before.st_nlink != 1
    {
        return Err(error("RECORDING_UNSAFE_ENTRY"));
    }
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_EVTONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(error("RECORDING_UNAVAILABLE"));
    }
    let file = unsafe { File::from_raw_fd(fd) };
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd, &mut stat) } != 0
        || stat.st_mode & libc::S_IFMT != libc::S_IFREG
        || stat.st_nlink != 1
        || stat.st_dev != before.st_dev
        || stat.st_ino != before.st_ino
    {
        return Err(error("RECORDING_UNSAFE_ENTRY"));
    }
    Ok(RevealCapability {
        path: directory.join(id),
        _file: file,
        _directory: parent,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::output::{OutputFailure, OutputRegistry};
    use std::{fs, os::unix::fs::symlink};

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let base = std::env::temp_dir().canonicalize().unwrap().join(format!(
                "motive-recordings-{}-{}",
                std::process::id(),
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            fs::create_dir(&base).unwrap();
            Self(base)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn only_generated_basenames_can_be_revealed() {
        let f = Fixture::new();
        fs::write(f.0.join("motive-123.mkv"), b"not yet validated media").unwrap();
        assert!(prepare_reveal_in(&f.0, "motive-123.mkv").is_ok());
        for id in [
            "../motive-123.mkv",
            "/tmp/motive-123.mkv",
            "motive-1/2.mkv",
            "motive-1.mkv\0",
            "secret.txt",
            "motive-.mkv",
            "motive-12.MKV",
        ] {
            assert_eq!(
                prepare_reveal_in(&f.0, id).err().unwrap().code,
                "INVALID_RECORDING_ID"
            );
        }
    }

    #[test]
    fn symlinks_hardlinks_and_nonregular_entries_are_rejected() {
        let f = Fixture::new();
        fs::write(f.0.join("private"), b"untouched").unwrap();
        symlink(f.0.join("private"), f.0.join("motive-1.mkv")).unwrap();
        fs::hard_link(f.0.join("private"), f.0.join("motive-2.mkv")).unwrap();
        fs::create_dir(f.0.join("motive-3.mkv")).unwrap();
        let fifo = CString::new(f.0.join("motive-4.mkv").as_os_str().as_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o600) }, 0);
        let scan = scan_directory(&f.0).unwrap();
        assert!(scan.entries.is_empty());
        for id in [
            "motive-1.mkv",
            "motive-2.mkv",
            "motive-3.mkv",
            "motive-4.mkv",
        ] {
            assert!(prepare_reveal_in(&f.0, id).is_err());
        }
        assert_eq!(fs::read(f.0.join("private")).unwrap(), b"untouched");
        symlink(&f.0, f.0.join("alias")).unwrap();
        assert!(scan_directory(&f.0.join("alias")).is_err());
        assert!(prepare_reveal_in(&f.0.join("alias"), "motive-1.mkv").is_err());
    }

    #[test]
    fn scan_and_display_limits_are_explicit() {
        let f = Fixture::new();
        for i in 0..SCAN_LIMIT + 8 {
            fs::write(f.0.join(format!("motive-{i}.mkv")), []).unwrap();
        }
        let scan = scan_directory(&f.0).unwrap();
        assert_eq!(scan.scanned_entries, SCAN_LIMIT);
        assert_eq!(scan.entries.len(), DISPLAY_LIMIT);
        assert!(scan.truncated);
    }

    #[test]
    fn filesystem_presence_does_not_claim_media_completion() {
        let f = Fixture::new();
        fs::write(f.0.join("motive-123.mkv"), b"incomplete").unwrap();
        let mut library = Library::at(f.0.clone());
        library.scan = scan_directory(&f.0).unwrap();
        let mut output = OutputRegistry::default().recording;
        output.path = Some(f.0.join("motive-123.mkv").to_string_lossy().into_owned());
        output.attempt_id = Some(1);
        output.native_busy = true;
        output.phase = OutputPhase::Active;
        assert_eq!(
            library.snapshot(&output).items[0].state,
            RecordingState::Writing
        );
        output.cancel_requested = true;
        assert_eq!(
            library.snapshot(&output).items[0].state,
            RecordingState::Finalizing
        );
        output.failure = Some(OutputFailure {
            code: "OUTPUT_NO_SPACE".into(),
            native_code: Some(-7),
            recovery: "explicit",
        });
        assert_eq!(
            library.snapshot(&output).items[0].state,
            RecordingState::Finalizing
        );
        output.native_busy = false;
        assert_eq!(
            library.snapshot(&output).items[0].state,
            RecordingState::Error
        );
        output.failure = None;
        output.cancel_requested = false;
        output.phase = OutputPhase::Idle;
        let snapshot = library.snapshot(&output);
        assert_eq!(snapshot.items[0].state, RecordingState::ClosedUnverified);
        assert!(!snapshot.items[0].media_verified);
        output.path = Some(f.0.join("motive-456.mkv").to_string_lossy().into_owned());
        output.native_busy = true;
        output.phase = OutputPhase::Active;
        assert_eq!(
            library.snapshot(&output).items[0].state,
            RecordingState::ClosedUnverified
        );
    }

    #[test]
    fn worker_is_single_and_poll_drains_shutdown_barrier() {
        let f = Fixture::new();
        let mut library = Library::at(f.0.clone());
        library.refresh().unwrap();
        assert!(library.busy());
        assert_eq!(library.refresh().unwrap_err().code, "RECORDING_SCAN_BUSY");
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while library.busy() {
            assert!(std::time::Instant::now() < deadline);
            library.poll();
            std::thread::yield_now();
        }
        assert_eq!(
            library.snapshot(&OutputRegistry::default().recording).phase,
            ScanPhase::Ready
        );
    }
}
