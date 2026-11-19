//! Capture control/observation only. libobs/SCK retain all media ownership.
use crate::{
    core::Variant,
    scene::{Graph, SourceKind},
};
use serde::Serialize;
use serde_json::Value;

/// A fallback must already exist and cover the canvas without any capture.
/// Selecting it never creates a camera/SCK resource or broadens capture scope.
pub fn validate_safe_scene(graph: &Graph, variant: Variant, id: &str) -> anyhow::Result<()> {
    let scene = graph.scene(id)?;
    let (width, height) = crate::core::video::layout_dimensions(variant);
    let mut covered = false;
    for layer in &scene.layers {
        let source = graph
            .sources
            .iter()
            .find(|s| s.id == layer.source_id)
            .ok_or_else(|| anyhow::anyhow!("SOURCE_UNAVAILABLE"))?;
        anyhow::ensure!(
            matches!(
                source.spec,
                SourceKind::Pattern | SourceKind::Overlay { .. }
            ),
            "UNSAFE_CAPTURE_FALLBACK: use a pattern and local overlays only"
        );
        let t = layer.layouts.get(variant);
        if matches!(source.spec, SourceKind::Pattern)
            && t.visible
            && t.x <= 0.0
            && t.y <= 0.0
            && t.x + t.width >= width as f32
            && t.y + t.height >= height as f32
        {
            covered = true;
        }
    }
    anyhow::ensure!(
        covered,
        "UNSAFE_CAPTURE_FALLBACK: a visible pattern must cover the canvas"
    );
    Ok(())
}

pub fn confirmed_failure(source: &Value) -> bool {
    matches!(
        source["kind"].as_str(),
        Some("window" | "display" | "application")
    ) && matches!(
        delivery(source),
        Delivery::Unavailable
            | Delivery::Blank
            | Delivery::Suspended
            | Delivery::Stopped
            | Delivery::UserStopped
            | Delivery::Failed
    )
}

pub fn validate_display(uuid: &str) -> anyhow::Result<()> {
    anyhow::ensure!(
        uuid.len() == 36
            && uuid.bytes().enumerate().all(|(i, c)| {
                if [8, 13, 18, 23].contains(&i) {
                    c == b'-'
                } else {
                    c.is_ascii_digit() || (b'A'..=b'F').contains(&c)
                }
            }),
        "INVALID_DISPLAY_IDENTITY: select the exact display UUID from devices"
    );
    Ok(())
}

pub fn validate_application(bundle: &str) -> anyhow::Result<()> {
    anyhow::ensure!(
        bundle.len() < 256
            && bundle.contains('.')
            && bundle.split('.').all(|s| !s.is_empty())
            && bundle
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-'),
        "INVALID_APPLICATION_IDENTITY"
    );
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Delivery {
    Inactive,
    Unavailable,
    Unobserved,
    Starting,
    Receiving,
    StaticOrUnobserved,
    Blank,
    Suspended,
    Stopped,
    UserStopped,
    Failed,
}

/// A scalar assessment of SCK delivery, never a claim about pixel freshness.
/// Age alone cannot establish a stall; neither can OBS render/output counters.
pub fn delivery(source: &Value) -> Delivery {
    if source["active"] != true {
        return Delivery::Inactive;
    }
    let d = &source["capture_diagnostics"];
    if d["user_stopped"] == true {
        return Delivery::UserStopped;
    }
    if d["sample_status"] == "stopped" {
        return Delivery::Stopped;
    }
    if d["phase"] == "failed" {
        return Delivery::Failed;
    }
    if source["issue"]
        .as_str()
        .is_some_and(|s| !s.is_empty() && s != "CAPTURE_NOT_READY")
    {
        return Delivery::Unavailable;
    }
    if !d.is_object() {
        return Delivery::Unobserved;
    }
    match d["sample_status"].as_str() {
        Some("suspended") => Delivery::Suspended,
        Some("blank") => Delivery::Blank,
        Some("idle") => Delivery::StaticOrUnobserved,
        Some("complete" | "started") if d["surface_samples"].as_u64().unwrap_or(0) > 0 => {
            match d["surface_age_ms"].as_f64() {
                Some(age) if age.is_finite() && (0.0..=3000.0).contains(&age) => {
                    Delivery::Receiving
                }
                _ => Delivery::StaticOrUnobserved,
            }
        }
        _ => Delivery::Starting,
    }
}

pub fn start_blocker(source: &Value) -> Option<&'static str> {
    match delivery(source) {
        Delivery::Suspended => Some("CAPTURE_SUSPENDED"),
        Delivery::Blank => Some("CAPTURE_BLANK"),
        Delivery::Stopped => Some("CAPTURE_STOPPED"),
        Delivery::UserStopped => Some("CAPTURE_USER_STOPPED"),
        Delivery::Failed => Some("CAPTURE_SESSION_FAILED"),
        // Availability/readiness remains checked by the existing native graph.
        _ => None,
    }
}

pub fn annotate(health: &mut Value) {
    for source in health.as_array_mut().into_iter().flatten() {
        if matches!(
            source["kind"].as_str(),
            Some("window" | "display" | "application")
        ) {
            source["capture_delivery"] = serde_json::to_value(delivery(source)).unwrap();
            source["automatic_restart"] = Value::Bool(false);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn fallback_cannot_reveal_capture_or_leave_canvas_uncovered() {
        let mut graph = Graph::default();
        let id = graph.active_scene.clone();
        assert!(validate_safe_scene(&graph, Variant::Horizontal, &id).is_ok());
        assert!(validate_safe_scene(&graph, Variant::Vertical, &id).is_ok());
        graph
            .sources
            .iter_mut()
            .find(|s| s.id == "main")
            .unwrap()
            .spec = SourceKind::Display {
            display_uuid: "00000000-0000-0000-0000-00000000000A".into(),
        };
        assert!(validate_safe_scene(&graph, Variant::Horizontal, &id).is_err());
        graph
            .sources
            .iter_mut()
            .find(|s| s.id == "main")
            .unwrap()
            .spec = SourceKind::Pattern;
        graph
            .scene_mut(&id)
            .unwrap()
            .layers
            .iter_mut()
            .find(|l| l.source_id == "main")
            .unwrap()
            .layouts
            .horizontal
            .width = 959.0;
        assert!(validate_safe_scene(&graph, Variant::Horizontal, &id).is_err());
    }

    #[test]
    fn uncertain_age_never_triggers_fallback() {
        let mut source = json!({"kind":"window","active":true,"capture_diagnostics":{
            "sample_status":"idle","surface_age_ms":999999}});
        assert!(!confirmed_failure(&source));
        source["capture_diagnostics"]["sample_status"] = json!("suspended");
        assert!(confirmed_failure(&source));
        source["active"] = json!(false);
        assert!(!confirmed_failure(&source));
    }

    #[test]
    fn renders_do_not_make_a_suspended_or_old_capture_healthy() {
        let mut s = json!({"active":true,"issue":"","capture_diagnostics":{
            "phase":"running","sample_status":"suspended","surface_samples":467,
            "surface_age_ms":15400,"renders_with_texture":905}});
        assert_eq!(delivery(&s), Delivery::Suspended);
        assert_eq!(start_blocker(&s), Some("CAPTURE_SUSPENDED"));
        s["capture_diagnostics"]["sample_status"] = json!("complete");
        assert_eq!(delivery(&s), Delivery::StaticOrUnobserved);
        assert_eq!(start_blocker(&s), None);
        s["capture_diagnostics"]["surface_age_ms"] = json!(12);
        assert_eq!(delivery(&s), Delivery::Receiving);
    }

    #[test]
    fn static_content_and_inactive_sources_are_not_faults() {
        let mut s = json!({"active":true,"capture_diagnostics":{"phase":"running",
            "sample_status":"idle","surface_age_ms":3600000}});
        assert_eq!(delivery(&s), Delivery::StaticOrUnobserved);
        assert_eq!(start_blocker(&s), None);
        s["active"] = json!(false);
        s["capture_diagnostics"]["sample_status"] = json!("suspended");
        assert_eq!(delivery(&s), Delivery::Inactive);
        assert_eq!(start_blocker(&s), None);
    }

    #[test]
    fn terminal_user_intent_wins_over_stale_complete_sample() {
        let mut s = json!({"active":true,"capture_diagnostics":{"phase":"failed",
            "sample_status":"complete","surface_samples":500,"surface_age_ms":1,
            "user_stopped":true}});
        assert_eq!(delivery(&s), Delivery::UserStopped);
        assert_eq!(start_blocker(&s), Some("CAPTURE_USER_STOPPED"));
        s["capture_diagnostics"]["user_stopped"] = json!(false);
        assert_eq!(delivery(&s), Delivery::Failed);
        s["capture_diagnostics"] = Value::Null;
        assert_eq!(delivery(&s), Delivery::Unobserved);
    }

    #[test]
    fn identity_rejects_defaults_paths_and_noncanonical_displays() {
        assert!(validate_display("00000000-0000-0000-0000-00000000000A").is_ok());
        for s in [
            "",
            "main",
            "default",
            "00000000-0000-0000-0000-00000000000a",
        ] {
            assert!(validate_display(s).is_err());
        }
        assert!(validate_application("local.motive.fixture").is_ok());
        for s in [
            "",
            "default",
            "local..app",
            "/Applications/App.app",
            "local.app\0",
        ] {
            assert!(validate_application(s).is_err());
        }
    }
}
