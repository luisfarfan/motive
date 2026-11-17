//! Explicit imports from a private inbox; no command accepts a filesystem path.
//!
//! Directory-descriptor-relative, no-follow I/O keeps untrusted names confined.
//! Images are decoded and re-encoded; video is decoded and remuxed into a new
//! container with only admitted tracks. The native consumer receives only a
//! verified managed path. This is not an OS sandbox against another process
//! running as the same user, nor a guarantee against decoder vulnerabilities.
use anyhow::{Context, bail, ensure};
mod staging;
use image::{ImageFormat, ImageReader};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
pub use staging::StagedImport;
use std::{
    collections::BTreeSet,
    ffi::{CString, OsStr},
    fs::File,
    io::{Cursor, Read, Seek, SeekFrom, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{ffi::OsStrExt, fs::MetadataExt, process::CommandExt},
    },
    path::{Component, Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    thread,
    time::{Duration, Instant},
};

pub const MAX_FILE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 512 * 1024 * 1024;
const MAX_ASSETS: usize = 128;
const MAX_INDEX_BYTES: u64 = 128 * 1024;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AssetKind {
    Image,
    Video,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Asset {
    pub id: String,
    pub kind: AssetKind,
    pub width: u32,
    pub height: u32,
    pub bytes: u64,
    pub sha256: String,
    pub duration_ms: Option<u64>,
    pub has_audio: bool,
}
/// Inventory remains readable when an individual managed object needs repair.
/// Rendering and `list_assets` still require every object they use to verify.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AssetStatus {
    pub asset: Asset,
    pub error: Option<String>,
}
impl Asset {
    fn filename(&self) -> String {
        format!(
            "{}.{}",
            self.id,
            match self.kind {
                AssetKind::Image => "png",
                AssetKind::Video => "mkv",
            }
        )
    }
    fn validate(&self) -> anyhow::Result<()> {
        validate_id(&self.id)?;
        ensure!(
            self.id == format!("asset-{}", self.sha256),
            "INVALID_ASSET_STORE"
        );
        ensure!(
            self.bytes > 0 && self.bytes <= MAX_FILE_BYTES,
            "INVALID_ASSET_STORE"
        );
        let valid = match self.kind {
            AssetKind::Image => {
                self.width > 0
                    && self.width <= 2048
                    && self.height > 0
                    && self.height <= 2048
                    && self.duration_ms.is_none()
                    && !self.has_audio
            }
            AssetKind::Video => {
                self.width > 0
                    && self.width <= 1920
                    && self.height > 0
                    && self.height <= 1080
                    && self.duration_ms.is_some_and(|v| v > 0 && v <= 60_000)
            }
        };
        ensure!(valid, "INVALID_ASSET_STORE");
        Ok(())
    }
}
pub fn validate_id(id: &str) -> anyhow::Result<()> {
    ensure!(
        id.len() == 70
            && id.starts_with("asset-")
            && id[6..]
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "INVALID_ASSET_ID"
    );
    Ok(())
}
fn inbox_name(name: &str) -> anyhow::Result<()> {
    ensure!(
        !name.is_empty()
            && name.len() <= 120
            && !name.starts_with('.')
            && name
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_')),
        "INVALID_IMPORT_NAME: use an inbox basename"
    );
    Ok(())
}
#[derive(Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Index {
    version: u32,
    assets: Vec<Asset>,
}
impl Index {
    fn validate(&self) -> anyhow::Result<()> {
        ensure!(self.version == 1, "ASSET_VERSION_UNSUPPORTED");
        ensure!(self.assets.len() <= MAX_ASSETS, "ASSET_QUOTA_EXCEEDED");
        let mut ids = BTreeSet::new();
        let mut total = 0;
        for asset in &self.assets {
            asset.validate()?;
            ensure!(ids.insert(&asset.id), "INVALID_ASSET_STORE: duplicate ID");
            total += asset.bytes;
        }
        ensure!(total <= MAX_TOTAL_BYTES, "ASSET_QUOTA_EXCEEDED");
        Ok(())
    }
}

pub struct AssetCatalog {
    root: PathBuf,
    assets: File,
    imports: File,
}
impl AssetCatalog {
    pub fn new(root: PathBuf) -> anyhow::Result<Self> {
        let directory = open_directory_chain(&root)?;
        let assets = subdirectory(&directory, "assets")?;
        let imports = subdirectory(&directory, "imports")?;
        ensure_private_directory(&assets)?;
        ensure_private_directory(&imports)?;
        let this = Self {
            root,
            assets,
            imports,
        };
        this.load()?;
        Ok(this)
    }
    /// Returns metadata only, never the original inbox name or file contents.
    pub fn list(&self) -> anyhow::Result<Vec<Asset>> {
        let _lock = self.lock()?;
        let index = self.load()?;
        for asset in &index.assets {
            self.verify(asset)?;
        }
        Ok(index.assets)
    }
    pub fn inventory(&self) -> anyhow::Result<Vec<AssetStatus>> {
        let _lock = self.lock()?;
        Ok(self
            .load()?
            .assets
            .into_iter()
            .map(|asset| {
                let error = self.verify(&asset).err().map(|e| e.to_string());
                AssetStatus { asset, error }
            })
            .collect())
    }
    pub fn get(&self, id: &str) -> anyhow::Result<Asset> {
        validate_id(id)?;
        let _lock = self.lock()?;
        let asset = self
            .load()?
            .assets
            .into_iter()
            .find(|a| a.id == id)
            .context("ASSET_UNAVAILABLE")?;
        self.verify(&asset)?;
        Ok(asset)
    }
    pub fn resolve(&self, id: &str) -> anyhow::Result<PathBuf> {
        let asset = self.get(id)?;
        // Verify every named directory still refers to the anchored directory.
        // Native OBS requires a path; another same-UID process is not isolated.
        let root = open_directory_chain(&self.root)?;
        let directory = open_at(&root, "assets", libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        ensure!(same_file(&directory, &self.assets)?, "ASSET_ROOT_CHANGED");
        let path = self.root.join("assets").join(asset.filename());
        ensure!(
            path.canonicalize().context("ASSET_UNAVAILABLE")? == path,
            "ASSET_ROOT_CHANGED"
        );
        Ok(path)
    }
    pub fn import(&self, file_name: &str) -> anyhow::Result<Asset> {
        inbox_name(file_name)?;
        let _lock = self.lock()?;
        let mut index = self.load()?;
        let mut input = open_at(
            &self.imports,
            file_name,
            libc::O_RDONLY | libc::O_NONBLOCK,
            0,
        )
        .context("ASSET_IMPORT_UNAVAILABLE")?;
        let before = input.metadata().context("ASSET_IMPORT_UNAVAILABLE")?;
        ensure!(
            before.is_file() && before.nlink() == 1,
            "UNSAFE_ASSET_FILE: regular single-link inbox copy required"
        );
        ensure!(
            before.len() > 0 && before.len() <= MAX_FILE_BYTES,
            "ASSET_SIZE_LIMIT"
        );
        let mut bytes = Vec::new();
        Read::by_ref(&mut input)
            .take(MAX_FILE_BYTES + 1)
            .read_to_end(&mut bytes)
            .context("ASSET_IMPORT_FAILED")?;
        let after = input.metadata().context("ASSET_IMPORT_UNAVAILABLE")?;
        ensure!(
            bytes.len() as u64 == before.len()
                && before.len() == after.len()
                && before.mtime() == after.mtime()
                && before.mtime_nsec() == after.mtime_nsec()
                && before.ctime() == after.ctime()
                && before.ctime_nsec() == after.ctime_nsec(),
            "ASSET_CHANGED_DURING_IMPORT"
        );
        let (mut asset, encoded) = match image::guess_format(&bytes) {
            Ok(format @ (ImageFormat::Png | ImageFormat::Jpeg | ImageFormat::WebP)) => {
                sanitize_image(bytes, format)?
            }
            _ => self.sanitize_video(&bytes)?,
        };
        ensure!(
            !encoded.is_empty() && encoded.len() as u64 <= MAX_FILE_BYTES,
            "ASSET_SIZE_LIMIT"
        );
        asset.sha256 = format!("{:x}", Sha256::digest(&encoded));
        asset.id = format!("asset-{}", asset.sha256);
        asset.bytes = encoded.len() as u64;
        if let Some(existing) = index.assets.iter().find(|a| a.id == asset.id) {
            ensure!(*existing == asset, "INVALID_ASSET_STORE");
            // Explicitly importing the same authorized bytes is also recovery:
            // repair only the verified content-addressed object, without changing
            // its identity/metadata or requiring deletion of scene references.
            if self.verify(existing).is_err() {
                self.atomic_write(&existing.filename(), &encoded)?;
                self.verify(existing)?;
            }
            return Ok(existing.clone());
        }
        index.assets.push(asset.clone());
        index.validate()?;
        // Any unreferenced orphan with this hash can be replaced by verified bytes.
        self.atomic_write(&asset.filename(), &encoded)?;
        self.save(&index)?;
        Ok(asset)
    }
    /// Caller supplies references from every scene, including inactive scenes.
    pub fn remove(&self, id: &str, referenced: &BTreeSet<String>) -> anyhow::Result<()> {
        validate_id(id)?;
        ensure!(!referenced.contains(id), "ASSET_IN_USE");
        let _lock = self.lock()?;
        let mut index = self.load()?;
        let asset = index
            .assets
            .iter()
            .find(|a| a.id == id)
            .cloned()
            .context("ASSET_UNAVAILABLE")?;
        index.assets.retain(|a| a.id != id);
        // Commit metadata first; a crash leaves only an unreferenced orphan.
        self.save(&index)?;
        unlink_at(&self.assets, &asset.filename())?;
        self.assets.sync_all().context("ASSET_WRITE_FAILED")?;
        Ok(())
    }
    fn lock(&self) -> anyhow::Result<File> {
        let file = open_at(
            &self.assets,
            ".lock",
            libc::O_RDWR | libc::O_CREAT | libc::O_NONBLOCK,
            0o600,
        )?;
        ensure!(
            file.metadata()?.is_file() && file.metadata()?.nlink() == 1,
            "UNSAFE_ASSET_STORE"
        );
        // Production serializes controls. This also prevents another process
        // from modifying the same catalog concurrently; never block the owner.
        ensure!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0,
            "ASSET_BUSY"
        );
        Ok(file)
    }
    fn load(&self) -> anyhow::Result<Index> {
        let mut file = match open_at_io(
            &self.assets,
            "index.json",
            libc::O_RDONLY | libc::O_NONBLOCK,
            0,
        ) {
            Ok(file) => file,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Index {
                    version: 1,
                    assets: vec![],
                });
            }
            Err(_) => bail!("UNSAFE_ASSET_STORE"),
        };
        ensure!(
            file.metadata()?.is_file() && file.metadata()?.nlink() == 1,
            "UNSAFE_ASSET_STORE"
        );
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(MAX_INDEX_BYTES + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() as u64 <= MAX_INDEX_BYTES,
            "ASSET_STORE_TOO_LARGE"
        );
        let index: Index = serde_json::from_slice(&bytes).context("INVALID_ASSET_STORE")?;
        index.validate()?;
        Ok(index)
    }
    fn save(&self, index: &Index) -> anyhow::Result<()> {
        index.validate()?;
        self.atomic_write("index.json", &serde_json::to_vec_pretty(index)?)
    }
    fn verify(&self, asset: &Asset) -> anyhow::Result<()> {
        let mut file = open_at(
            &self.assets,
            &asset.filename(),
            libc::O_RDONLY | libc::O_NONBLOCK,
            0,
        )
        .context("ASSET_UNAVAILABLE")?;
        let metadata = file.metadata()?;
        ensure!(
            metadata.is_file() && metadata.nlink() == 1 && metadata.len() == asset.bytes,
            "ASSET_CORRUPT"
        );
        let mut hash = Sha256::new();
        let mut buffer = [0_u8; 64 * 1024];
        let mut count = 0;
        loop {
            let n = file.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            count += n as u64;
            ensure!(count <= MAX_FILE_BYTES, "ASSET_CORRUPT");
            hash.update(&buffer[..n]);
        }
        ensure!(
            count == asset.bytes && format!("{:x}", hash.finalize()) == asset.sha256,
            "ASSET_CORRUPT"
        );
        Ok(())
    }
    fn atomic_write(&self, name: &str, bytes: &[u8]) -> anyhow::Result<()> {
        let mut temp = Temporary::new(&self.assets)?;
        temp.file.write_all(bytes).context("ASSET_WRITE_FAILED")?;
        temp.file.sync_all().context("ASSET_WRITE_FAILED")?;
        let source = CString::new(temp.name.as_str())?;
        let destination = CString::new(name)?;
        ensure!(
            unsafe {
                libc::renameat(
                    self.assets.as_raw_fd(),
                    source.as_ptr(),
                    self.assets.as_raw_fd(),
                    destination.as_ptr(),
                )
            } == 0,
            "ASSET_WRITE_FAILED"
        );
        temp.published = true;
        self.assets.sync_all().context("ASSET_WRITE_FAILED")?;
        Ok(())
    }
    fn sanitize_video(&self, bytes: &[u8]) -> anyhow::Result<(Asset, Vec<u8>)> {
        let mov = bytes.len() >= 12 && &bytes[4..8] == b"ftyp";
        let webm = bytes.starts_with(&[0x1a, 0x45, 0xdf, 0xa3]);
        ensure!(
            mov || webm,
            "ASSET_FORMAT_UNSUPPORTED: PNG JPEG WebP MP4 MOV or WebM required"
        );
        let mut input = Temporary::new(&self.assets)?;
        input.file.write_all(bytes)?;
        input.file.seek(SeekFrom::Start(0))?;
        let input_path = format!("/dev/fd/{}", input.file.as_raw_fd());
        let format = if mov { "mov" } else { "matroska,webm" };
        let mut args = vec![
            "-v",
            "error",
            "-max_alloc",
            "33554432",
            "-threads",
            "1",
            "-max_pixels",
            "2073600",
            "-protocol_whitelist",
            "file",
            "-codec_whitelist",
            "h264,vp8,vp9,aac,opus,vorbis",
            "-format_whitelist",
            format,
            "-f",
            if mov { "mov" } else { "matroska" },
            "-max_streams",
            "8",
            "-probesize",
            "16777216",
            "-analyzeduration",
            "5000000",
        ];
        if mov {
            args.extend(["-enable_drefs", "0", "-use_absolute_path", "0"]);
        }
        let mut probe = Command::new("ffprobe");
        probe.args(&args).args(["-count_frames", "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration", "-of", "json", "-i", &input_path]);
        let result = run_bounded(&mut probe, &[&input.file], 30)?;
        let info: serde_json::Value =
            serde_json::from_slice(&result).context("ASSET_VIDEO_INVALID")?;
        let streams = info["streams"].as_array().context("ASSET_VIDEO_INVALID")?;
        ensure!(streams.len() <= 8, "ASSET_VIDEO_LIMIT");
        let videos: Vec<_> = streams
            .iter()
            .filter(|s| s["codec_type"] == "video")
            .collect();
        let audios: Vec<_> = streams
            .iter()
            .filter(|s| s["codec_type"] == "audio")
            .collect();
        ensure!(
            videos.len() == 1 && audios.len() <= 1,
            "ASSET_VIDEO_TRACK_LIMIT"
        );
        let video = videos[0];
        let width = video["width"].as_u64().unwrap_or(0);
        let height = video["height"].as_u64().unwrap_or(0);
        let duration: f64 = info["format"]["duration"]
            .as_str()
            .unwrap_or("")
            .parse()
            .context("ASSET_VIDEO_INVALID")?;
        let fps = ratio(video["avg_frame_rate"].as_str().unwrap_or(""))?;
        let frames: u64 = video["nb_read_frames"]
            .as_str()
            .unwrap_or("")
            .parse()
            .context("ASSET_VIDEO_INVALID")?;
        ensure!(
            width > 0
                && width <= 1920
                && height > 0
                && height <= 1080
                && duration.is_finite()
                && duration > 0.
                && duration <= 60.
                && fps > 0.
                && fps <= 60.
                && frames > 0
                && frames <= 3600,
            "ASSET_VIDEO_LIMIT"
        );
        ensure!(
            ["h264", "vp8", "vp9"].contains(&video["codec_name"].as_str().unwrap_or(""))
                && audios
                    .iter()
                    .all(|a| ["aac", "opus", "vorbis"]
                        .contains(&a["codec_name"].as_str().unwrap_or(""))),
            "ASSET_VIDEO_CODEC_UNSUPPORTED"
        );
        // Decode validated streams and reject decoder warnings/errors. ffprobe's
        // frame count alone can skip corrupt packets while returning success.
        input.file.seek(SeekFrom::Start(0))?;
        let mut decode = Command::new("ffmpeg");
        decode
            .args(["-nostdin", "-xerror", "-err_detect", "explode"])
            .args(&args)
            .args([
                "-i",
                &input_path,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-f",
                "null",
                "-",
            ]);
        run_bounded(&mut decode, &[&input.file], 30)?;
        input.file.seek(SeekFrom::Start(0))?;
        let mut output = Temporary::new(&self.assets)?;
        let output_path = format!("/dev/fd/{}", output.file.as_raw_fd());
        let mut remux = Command::new("ffmpeg");
        remux.args(["-nostdin", "-y"]).args(&args).args([
            "-i",
            &input_path,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-map_metadata",
            "-1",
            "-map_metadata:s",
            "-1",
            "-map_chapters",
            "-1",
            "-c",
            "copy",
            "-fflags",
            "+bitexact",
            "-f",
            "matroska",
            &output_path,
        ]);
        run_bounded(&mut remux, &[&input.file, &output.file], 10)?;
        ensure!(
            output.file.metadata()?.len() <= MAX_FILE_BYTES,
            "ASSET_SIZE_LIMIT"
        );
        output.file.seek(SeekFrom::Start(0))?;
        let mut encoded = Vec::new();
        Read::by_ref(&mut output.file)
            .take(MAX_FILE_BYTES + 1)
            .read_to_end(&mut encoded)?;
        Ok((
            Asset {
                id: String::new(),
                kind: AssetKind::Video,
                width: width as u32,
                height: height as u32,
                bytes: 0,
                sha256: String::new(),
                duration_ms: Some((duration * 1000.).ceil() as u64),
                has_audio: !audios.is_empty(),
            },
            encoded,
        ))
    }
}
fn ratio(value: &str) -> anyhow::Result<f64> {
    let (n, d) = value.split_once('/').context("ASSET_VIDEO_INVALID")?;
    let result = n.parse::<f64>().context("ASSET_VIDEO_INVALID")?
        / d.parse::<f64>().context("ASSET_VIDEO_INVALID")?;
    ensure!(result.is_finite(), "ASSET_VIDEO_INVALID");
    Ok(result)
}
fn sanitize_image(bytes: Vec<u8>, format: ImageFormat) -> anyhow::Result<(Asset, Vec<u8>)> {
    let mut reader = ImageReader::with_format(Cursor::new(&bytes), format);
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(2048);
    limits.max_image_height = Some(2048);
    limits.max_alloc = Some(64 * 1024 * 1024);
    reader.limits(limits);
    let decoded = reader.decode().context("ASSET_IMAGE_INVALID")?;
    ensure!(
        decoded.width() > 0 && decoded.height() > 0,
        "ASSET_IMAGE_INVALID"
    );
    let mut encoded = Cursor::new(Vec::new());
    decoded
        .write_to(&mut encoded, ImageFormat::Png)
        .context("ASSET_IMAGE_INVALID")?;
    Ok((
        Asset {
            id: String::new(),
            kind: AssetKind::Image,
            width: decoded.width(),
            height: decoded.height(),
            bytes: 0,
            sha256: String::new(),
            duration_ms: None,
            has_audio: false,
        },
        encoded.into_inner(),
    ))
}
fn c_name(value: &OsStr) -> std::io::Result<CString> {
    CString::new(value.as_bytes())
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "NUL"))
}
fn open_at_io(parent: &File, name: &str, flags: i32, mode: libc::mode_t) -> std::io::Result<File> {
    let name = c_name(OsStr::new(name))?;
    // No-follow applies to the final path component; every parent is already
    // held by a no-follow directory descriptor. O_NONBLOCK avoids FIFO hangs.
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            mode as libc::c_uint,
        )
    };
    if fd < 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
fn open_at(parent: &File, name: &str, flags: i32, mode: libc::mode_t) -> anyhow::Result<File> {
    open_at_io(parent, name, flags, mode).context("UNSAFE_ASSET_PATH")
}
fn subdirectory(parent: &File, name: &str) -> anyhow::Result<File> {
    let name_c = CString::new(name)?;
    let made = unsafe { libc::mkdirat(parent.as_raw_fd(), name_c.as_ptr(), 0o700) };
    if made != 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::AlreadyExists {
        bail!("ASSET_DIRECTORY_UNAVAILABLE");
    }
    open_at(parent, name, libc::O_RDONLY | libc::O_DIRECTORY, 0)
}
fn open_directory_chain(path: &Path) -> anyhow::Result<File> {
    ensure!(path.is_absolute(), "UNSAFE_ASSET_ROOT");
    let mut current = File::open("/").context("ASSET_DIRECTORY_UNAVAILABLE")?;
    for component in path.components() {
        match component {
            Component::RootDir => {}
            Component::Normal(name) => {
                let name = name.to_str().context("UNSAFE_ASSET_ROOT")?;
                current = subdirectory(&current, name)?;
            }
            _ => bail!("UNSAFE_ASSET_ROOT"),
        }
    }
    Ok(current)
}
fn ensure_private_directory(directory: &File) -> anyhow::Result<()> {
    let metadata = directory.metadata()?;
    ensure!(
        metadata.uid() == unsafe { libc::geteuid() } && metadata.mode() & 0o077 == 0,
        "ASSET_DIRECTORY_PERMISSIONS: managed directories must be private"
    );
    Ok(())
}
fn same_file(a: &File, b: &File) -> std::io::Result<bool> {
    let a = a.metadata()?;
    let b = b.metadata()?;
    Ok(a.dev() == b.dev() && a.ino() == b.ino())
}
fn unlink_at(parent: &File, name: &str) -> anyhow::Result<()> {
    let name = CString::new(name)?;
    let result = unsafe { libc::unlinkat(parent.as_raw_fd(), name.as_ptr(), 0) };
    ensure!(
        result == 0 || std::io::Error::last_os_error().kind() == std::io::ErrorKind::NotFound,
        "ASSET_REMOVE_FAILED"
    );
    Ok(())
}
struct Temporary<'a> {
    directory: &'a File,
    name: String,
    file: File,
    published: bool,
}
impl<'a> Temporary<'a> {
    fn new(directory: &'a File) -> anyhow::Result<Self> {
        let name = format!(
            ".import-{}-{}",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let file = open_at(
            directory,
            &name,
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        Ok(Self {
            directory,
            name,
            file,
            published: false,
        })
    }
}
impl Drop for Temporary<'_> {
    fn drop(&mut self) {
        if !self.published {
            let _ = unlink_at(self.directory, &self.name);
        }
    }
}
fn drain<R: Read>(mut input: R) -> std::io::Result<(Vec<u8>, bool)> {
    let mut bytes = Vec::new();
    let mut buffer = [0; 8192];
    let mut overflow = false;
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        if bytes.len() + n <= 128 * 1024 {
            bytes.extend_from_slice(&buffer[..n]);
        } else {
            overflow = true;
        }
    }
    Ok((bytes, overflow))
}
struct ImportProcess {
    child: Child,
    reaped: bool,
}
impl Drop for ImportProcess {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
fn run_bounded(command: &mut Command, files: &[&File], seconds: u64) -> anyhow::Result<Vec<u8>> {
    let descriptors: Vec<_> = files.iter().map(|f| f.as_raw_fd()).collect();
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // Only async-signal-safe descriptor flags are touched after fork. The child
    // opens these already-authorized descriptors, never a caller-controlled path.
    unsafe {
        command.pre_exec(move || {
            for fd in &descriptors {
                if libc::fcntl(*fd, libc::F_SETFD, 0) == -1 {
                    return Err(std::io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }
    let mut process = ImportProcess {
        child: command.spawn().context("ASSET_TOOL_UNAVAILABLE")?,
        reaped: false,
    };
    let out = process.child.stdout.take().unwrap();
    let err = process.child.stderr.take().unwrap();
    let stdout = thread::spawn(move || drain(out));
    let stderr = thread::spawn(move || drain(err));
    let deadline = Instant::now() + Duration::from_secs(seconds);
    let mut timeout = false;
    let status = loop {
        if let Some(status) = process.child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline {
            timeout = true;
            let _ = process.child.kill();
            break process.child.wait()?;
        }
        thread::sleep(Duration::from_millis(10));
    };
    process.reaped = true;
    let (out, overflow) = stdout
        .join()
        .map_err(|_| anyhow::anyhow!("ASSET_IMPORT_FAILED"))??;
    let (err, err_overflow) = stderr
        .join()
        .map_err(|_| anyhow::anyhow!("ASSET_IMPORT_FAILED"))??;
    ensure!(!timeout, "ASSET_VALIDATION_TIMEOUT");
    // Do not expose decoder stderr: metadata/file content is untrusted and can
    // contain control characters, paths or secrets from an authorized upload.
    ensure!(
        status.success() && err.is_empty() && !overflow && !err_overflow,
        "ASSET_VIDEO_INVALID"
    );
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        os::unix::fs::{PermissionsExt, symlink},
    };

    pub(super) struct Fixture(pub(super) PathBuf);
    impl Fixture {
        pub(super) fn new() -> Self {
            let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
                "motive-assets-{}-{}",
                std::process::id(),
                TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
        pub(super) fn catalog(&self) -> AssetCatalog {
            AssetCatalog::new(self.0.clone()).unwrap()
        }
        fn png(&self, name: &str, width: u32, height: u32) {
            image::RgbaImage::from_pixel(width, height, image::Rgba([20, 80, 140, 97]))
                .save_with_format(self.0.join("imports").join(name), ImageFormat::Png)
                .unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn image_content_alpha_identity_and_references_survive_restore() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        fixture.png("misleading.jpg", 16, 9);
        let asset = catalog.import("misleading.jpg").unwrap();
        assert_eq!(
            (asset.kind, asset.width, asset.height),
            (AssetKind::Image, 16, 9)
        );
        assert_eq!(catalog.import("misleading.jpg").unwrap(), asset);
        let restored = fixture.catalog();
        assert_eq!(restored.list().unwrap(), std::slice::from_ref(&asset));
        let path = restored.resolve(&asset.id).unwrap();
        assert_eq!(
            image::open(&path).unwrap().to_rgba8().get_pixel(0, 0).0,
            [20, 80, 140, 97]
        );
        assert!(
            restored
                .remove(&asset.id, &BTreeSet::from([asset.id.clone()]))
                .unwrap_err()
                .to_string()
                .starts_with("ASSET_IN_USE")
        );
        assert!(path.exists());
        restored.remove(&asset.id, &BTreeSet::new()).unwrap();
        assert!(!path.exists());
        assert!(restored.list().unwrap().is_empty());
    }
    #[test]
    fn jpeg_and_webp_are_decoded_then_stored_as_png() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        for (name, format) in [
            ("photo.bin", ImageFormat::Jpeg),
            ("web.bin", ImageFormat::WebP),
        ] {
            image::RgbImage::from_pixel(12, 7, image::Rgb([15, 90, 220]))
                .save_with_format(fixture.0.join("imports").join(name), format)
                .unwrap();
            let asset = catalog.import(name).unwrap();
            let path = catalog.resolve(&asset.id).unwrap();
            assert_eq!(
                image::guess_format(&fs::read(path).unwrap()).unwrap(),
                ImageFormat::Png
            );
            assert_eq!((asset.width, asset.height), (12, 7));
        }
    }
    #[test]
    fn arbitrary_paths_links_and_special_files_never_enter_catalog() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        for name in [
            "",
            "/etc/passwd",
            "../secret",
            "sub/file.png",
            "sub\\file.png",
            ".hidden",
            "a%2fb",
            "a\n.png",
            "a\0.png",
        ] {
            assert!(catalog.import(name).is_err(), "{name:?}");
        }
        let outside = fixture.0.join("outside");
        fs::write(&outside, b"private fixture").unwrap();
        symlink(&outside, fixture.0.join("imports/link.png")).unwrap();
        assert!(catalog.import("link.png").is_err());
        fs::hard_link(&outside, fixture.0.join("imports/hard.png")).unwrap();
        assert!(catalog.import("hard.png").is_err());
        let fifo = CString::new(fixture.0.join("imports/pipe.png").as_os_str().as_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o600) }, 0);
        assert!(catalog.import("pipe.png").is_err());
        assert_eq!(fs::read(outside).unwrap(), b"private fixture");
        assert!(catalog.list().unwrap().is_empty());
    }
    #[test]
    fn parent_symlinks_and_nonprivate_directories_are_rejected() {
        let fixture = Fixture::new();
        let outside = Fixture::new();
        symlink(&outside.0, fixture.0.join("imports")).unwrap();
        assert!(AssetCatalog::new(fixture.0.clone()).is_err());
        let link = fixture.0.join("linked-root");
        symlink(&outside.0, &link).unwrap();
        assert!(AssetCatalog::new(link.join("nested")).is_err());
        assert!(!outside.0.join("nested").exists());
        fs::remove_file(fixture.0.join("imports")).unwrap();
        fs::create_dir(fixture.0.join("imports")).unwrap();
        fs::set_permissions(fixture.0.join("imports"), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(AssetCatalog::new(fixture.0.clone()).is_err());
    }
    #[test]
    fn damaged_oversized_and_oversized_dimension_imports_leave_no_records() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        fs::write(
            fixture.0.join("imports/broken.png"),
            b"\x89PNG\r\n\x1a\ninvalid",
        )
        .unwrap();
        assert!(catalog.import("broken.png").is_err());
        fs::write(fixture.0.join("imports/fake.png"), b"not an image").unwrap();
        assert!(catalog.import("fake.png").is_err());
        fixture.png("wide.png", 2049, 1);
        assert!(catalog.import("wide.png").is_err());
        let huge = File::create(fixture.0.join("imports/huge.png")).unwrap();
        huge.set_len(MAX_FILE_BYTES + 1).unwrap();
        assert!(
            catalog
                .import("huge.png")
                .unwrap_err()
                .to_string()
                .starts_with("ASSET_SIZE_LIMIT")
        );
        assert!(catalog.list().unwrap().is_empty());
    }
    #[test]
    fn managed_tampering_missing_data_and_symlinks_are_not_resolved() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        fixture.png("ok.png", 5, 5);
        let asset = catalog.import("ok.png").unwrap();
        let path = catalog.resolve(&asset.id).unwrap();
        let original = fs::read(&path).unwrap();
        let mut changed = original.clone();
        changed[20] ^= 1;
        fs::write(&path, changed).unwrap();
        assert!(catalog.resolve(&asset.id).is_err());
        fs::remove_file(&path).unwrap();
        assert!(catalog.resolve(&asset.id).is_err());
        let outside = fixture.0.join("original");
        fs::write(&outside, &original).unwrap();
        symlink(&outside, &path).unwrap();
        assert!(catalog.resolve(&asset.id).is_err());
        catalog.remove(&asset.id, &BTreeSet::new()).unwrap();
        assert_eq!(fs::read(outside).unwrap(), original);
    }
    #[test]
    fn explicit_identical_reimport_repairs_bytes_without_changing_references() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        fixture.png("recover.png", 9, 6);
        let asset = catalog.import("recover.png").unwrap();
        let path = catalog.resolve(&asset.id).unwrap();
        let index = fs::read(fixture.0.join("assets/index.json")).unwrap();
        let references = BTreeSet::from([asset.id.clone()]);
        let original = fs::read(&path).unwrap();
        fs::remove_file(&path).unwrap();
        assert!(catalog.resolve(&asset.id).is_err());
        assert_eq!(catalog.import("recover.png").unwrap(), asset);
        assert_eq!(fs::read(&path).unwrap(), original);
        fs::write(&path, b"damaged").unwrap();
        assert!(catalog.resolve(&asset.id).is_err());
        assert_eq!(catalog.import("recover.png").unwrap(), asset);
        assert_eq!(fs::read(&path).unwrap(), original);
        assert_eq!(
            fs::read(fixture.0.join("assets/index.json")).unwrap(),
            index
        );
        assert!(catalog.remove(&asset.id, &references).is_err());
        assert_eq!(catalog.get(&asset.id).unwrap(), asset);
    }
    #[test]
    fn metadata_versions_ids_quotas_and_locking_are_enforced() {
        let fixture = Fixture::new();
        let catalog = fixture.catalog();
        for id in [
            "../../path",
            "asset-/tmp/a",
            "asset-short",
            &format!("asset-{}", "A".repeat(64)),
        ] {
            assert!(catalog.get(id).is_err());
        }
        for bytes in [
            br#"{"version":2,"assets":[]}"#.as_slice(),
            br#"{"version":1,"assets":[],"path":"/etc/passwd"}"#,
        ] {
            fs::write(fixture.0.join("assets/index.json"), bytes).unwrap();
            assert!(catalog.list().is_err());
        }
        fs::remove_file(fixture.0.join("assets/index.json")).unwrap();
        let _lock = catalog.lock().unwrap();
        assert!(
            catalog
                .list()
                .unwrap_err()
                .to_string()
                .starts_with("ASSET_BUSY")
        );
        let make = |number: u64, bytes| {
            let sha256 = format!("{number:064x}");
            Asset {
                id: format!("asset-{sha256}"),
                kind: AssetKind::Image,
                width: 1,
                height: 1,
                bytes,
                sha256,
                duration_ms: None,
                has_audio: false,
            }
        };
        assert!(
            Index {
                version: 1,
                assets: (0..129).map(|n| make(n, 1)).collect()
            }
            .validate()
            .is_err()
        );
        assert!(
            Index {
                version: 1,
                assets: (0..9).map(|n| make(n, MAX_FILE_BYTES)).collect()
            }
            .validate()
            .is_err()
        );
    }
}
