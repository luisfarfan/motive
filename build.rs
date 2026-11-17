use std::{env, path::PathBuf};
fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let obs = root.join(".deps/OBS.app/Contents/Frameworks");
    if !obs.join("libobs.framework/libobs").exists() {
        panic!("Falta OBS 33.0.1. Ejecuta python3 scripts/bootstrap.py");
    }
    assert!(
        std::process::Command::new("python3")
            .arg(root.join("scripts/build_obs_outputs.py"))
            .status()
            .expect("build OBS output module")
            .success()
    );
    cc::Build::new()
        .define(
            "MOTIVE_RTMP_MODULE",
            Some(
                format!(
                    "\"{}\"",
                    root.join("target/obs-outputs-h8/obs-outputs.so").display()
                )
                .as_str(),
            ),
        )
        .file("native/engine.m")
        .include(root.join(".deps/obs-studio-33.0.1/libobs"))
        .include(root.join(".deps/simde-0.8.2"))
        .include("native")
        .flag("-Wno-deprecated-declarations")
        .flag("-fobjc-arc")
        .compile("motive_obs_bridge");
    println!("cargo:rustc-link-search=framework={}", obs.display());
    for framework in [
        "libobs",
        "Foundation",
        "AppKit",
        "CoreGraphics",
        "AVFoundation",
        "VideoToolbox",
        "Security",
    ] {
        println!("cargo:rustc-link-lib=framework={framework}");
    }
    println!("cargo:rustc-link-arg=-Wl,-rpath,{}", obs.display());
    println!("cargo:rerun-if-changed=native");
    println!("cargo:rerun-if-changed=scripts/build_obs_outputs.py");
}
