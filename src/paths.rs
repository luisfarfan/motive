//! Resolve the installed app and user data independently of the development checkout.
//! Resolution never creates, migrates or removes user files.
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use std::{
    path::{Path, PathBuf},
    sync::OnceLock,
};

#[derive(Clone, Debug)]
struct RuntimePaths {
    portable: bool,
    contents: PathBuf,
    development_root: PathBuf,
    data: PathBuf,
    recordings: PathBuf,
    diagnostics: PathBuf,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PortableMarker {
    version: u32,
    runtime_layout: String,
}

impl RuntimePaths {
    fn resolve(executable: &Path, home: Option<&Path>, development_root: &Path) -> Result<Self> {
        let contents = executable
            .parent()
            .filter(|p| p.file_name().is_some_and(|n| n == "MacOS"))
            .and_then(Path::parent)
            .filter(|p| p.file_name().is_some_and(|n| n == "Contents"));
        if let Some(contents) = contents {
            let marker = contents.join("Resources/MotivePortable.json");
            // A malformed existing marker is an error, never a silent fallback to .deps.
            match std::fs::read(&marker) {
                Ok(bytes) => {
                    let marker: PortableMarker = serde_json::from_slice(&bytes)
                        .context("PORTABLE_LAYOUT_INVALID: invalid bundle marker")?;
                    ensure!(
                        marker.version == 1 && marker.runtime_layout == "macos-portable-v1",
                        "PORTABLE_LAYOUT_UNSUPPORTED"
                    );
                    let home = home.context("USER_HOME_UNAVAILABLE")?;
                    ensure!(home.is_absolute(), "USER_HOME_INVALID");
                    let contents = contents
                        .canonicalize()
                        .context("PORTABLE_CONTENTS_UNAVAILABLE")?;
                    return Ok(Self {
                        portable: true,
                        contents,
                        development_root: development_root.to_owned(),
                        data: home.join("Library/Application Support/local.motive.studio"),
                        recordings: home.join("Movies/Motive"),
                        diagnostics: home.join("Library/Logs/Motive"),
                    });
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(e).context("PORTABLE_LAYOUT_UNREADABLE"),
            }
        }
        let data = development_root.join("var");
        Ok(Self {
            portable: false,
            contents: development_root.join(".deps/OBS.app/Contents"),
            development_root: development_root.to_owned(),
            recordings: data.join("recordings"),
            diagnostics: data.join("evidence"),
            data,
        })
    }

    fn discover() -> Result<Self> {
        let home = std::env::var_os("HOME").map(PathBuf::from);
        Self::resolve(
            &std::env::current_exe()?,
            home.as_deref(),
            Path::new(env!("CARGO_MANIFEST_DIR")),
        )
    }

    fn module(&self, name: &str, development: &str) -> PathBuf {
        if self.portable {
            self.contents
                .join(format!("PlugIns/{name}.plugin/Contents/MacOS/{name}"))
        } else {
            self.development_root.join(development)
        }
    }

    fn media_tool(&self, name: &str) -> Result<PathBuf> {
        ensure!(
            matches!(name, "ffmpeg" | "ffprobe"),
            "MEDIA_TOOL_UNSUPPORTED"
        );
        if !self.portable {
            return Ok(PathBuf::from(name));
        }
        let path = self.contents.join("MacOS").join(name);
        let resolved = path
            .canonicalize()
            .context("BUNDLED_MEDIA_TOOL_UNAVAILABLE")?;
        ensure!(
            resolved.starts_with(&self.contents),
            "BUNDLED_MEDIA_TOOL_OUTSIDE_APP"
        );
        let metadata = std::fs::metadata(&resolved)?;
        use std::os::unix::fs::PermissionsExt;
        ensure!(
            metadata.is_file() && metadata.permissions().mode() & 0o111 != 0,
            "BUNDLED_MEDIA_TOOL_NOT_EXECUTABLE"
        );
        Ok(resolved)
    }
}

static PATHS: OnceLock<RuntimePaths> = OnceLock::new();

/// Called before CLI/MCP or GUI dispatch so malformed installations fail clearly.
pub fn init() -> Result<()> {
    if PATHS.get().is_none() {
        let paths = RuntimePaths::discover()?;
        let _ = PATHS.set(paths);
    }
    Ok(())
}

fn configured() -> &'static RuntimePaths {
    // Unit tests do not pass through main. They resolve the same deterministic
    // development layout, without writing files or falling back in a portable app.
    PATHS.get_or_init(|| {
        RuntimePaths::discover().expect("runtime paths must initialize before dispatch")
    })
}

pub fn obs_contents() -> PathBuf {
    configured().contents.clone()
}
pub fn output_module() -> PathBuf {
    configured().module("obs-outputs", "target/obs-outputs-h8/obs-outputs.so")
}
pub fn mac_capture_module() -> PathBuf {
    configured().module("mac-capture", "target/mac-capture-h14/mac-capture.so")
}
pub fn data_dir() -> PathBuf {
    configured().data.clone()
}
pub fn recordings_dir() -> PathBuf {
    configured().recordings.clone()
}
pub fn diagnostic_dir() -> PathBuf {
    configured().diagnostics.clone()
}
pub fn media_tool(name: &str) -> Result<PathBuf> {
    configured().media_tool(name)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    fn fixture(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("motive-paths-{}-{name}", std::process::id()));
        std::fs::create_dir_all(root.join("Motive.app/Contents/Resources")).unwrap();
        std::fs::create_dir_all(root.join("Motive.app/Contents/MacOS")).unwrap();
        root
    }

    #[test]
    fn development_paths_preserve_existing_stores_without_creating_them() {
        let p = RuntimePaths::resolve(
            Path::new("/dev/target/debug/motive"),
            None,
            Path::new("/owned/repo"),
        )
        .unwrap();
        assert_eq!(p.data, Path::new("/owned/repo/var"));
        assert_eq!(p.recordings, Path::new("/owned/repo/var/recordings"));
        assert_eq!(p.media_tool("ffprobe").unwrap(), Path::new("ffprobe"));
        assert!(p.media_tool("../../shell").is_err());
    }

    #[test]
    fn portable_paths_follow_moved_bundle_and_keep_data_outside_it() {
        let root = fixture("portable");
        let contents = root.join("Motive.app/Contents");
        std::fs::write(
            contents.join("Resources/MotivePortable.json"),
            br#"{"version":1,"runtime_layout":"macos-portable-v1"}"#,
        )
        .unwrap();
        let user = root.join("user");
        let p = RuntimePaths::resolve(
            &contents.join("MacOS/motive"),
            Some(&user),
            Path::new("/missing/checkout"),
        )
        .unwrap();
        assert_eq!(p.recordings, user.join("Movies/Motive"));
        assert_eq!(
            p.data,
            user.join("Library/Application Support/local.motive.studio")
        );
        assert!(!user.exists());
        assert_eq!(
            p.module("obs-outputs", "ignored"),
            contents
                .canonicalize()
                .unwrap()
                .join("PlugIns/obs-outputs.plugin/Contents/MacOS/obs-outputs")
        );
        assert!(p.media_tool("ffmpeg").is_err());
        let tool = contents.join("MacOS/ffmpeg");
        std::fs::write(&tool, b"test").unwrap();
        std::fs::set_permissions(&tool, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(
            p.media_tool("ffmpeg").unwrap(),
            tool.canonicalize().unwrap()
        );
        std::fs::remove_file(&tool).unwrap();
        symlink("/bin/sh", &tool).unwrap();
        assert!(p.media_tool("ffmpeg").is_err());
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn malformed_portable_marker_never_uses_development_dependencies() {
        let root = fixture("invalid");
        let contents = root.join("Motive.app/Contents");
        for value in [
            r#"{"version":2,"runtime_layout":"macos-portable-v1"}"#,
            r#"{"version":1,"runtime_layout":"macos-portable-v1","path":"/tmp"}"#,
            "bad json",
        ] {
            std::fs::write(contents.join("Resources/MotivePortable.json"), value).unwrap();
            assert!(
                RuntimePaths::resolve(
                    &contents.join("MacOS/motive"),
                    Some(&root),
                    Path::new("/dev")
                )
                .is_err()
            );
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}
