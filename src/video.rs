//! One OBS video clock; serialized coordinates retain their legacy design units.
use super::Variant;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Resolution {
    #[default]
    Legacy540,
    Hd720,
    FullHd1080,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CoordinateSpace {
    #[default]
    Design960,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct VideoConfig {
    pub version: u32,
    pub resolution: Resolution,
    pub fps: u32,
    pub coordinate_space: CoordinateSpace,
}
impl Default for VideoConfig {
    fn default() -> Self {
        Self {
            version: 1,
            resolution: Resolution::Legacy540,
            fps: 30,
            coordinate_space: CoordinateSpace::Design960,
        }
    }
}
impl VideoConfig {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(self.version == 1, "VIDEO_VERSION_UNSUPPORTED");
        anyhow::ensure!(matches!(self.fps, 30 | 60), "INVALID_VIDEO_FPS");
        Ok(())
    }
    pub fn dimensions(self, variant: Variant) -> (u32, u32) {
        let (w, h) = match self.resolution {
            Resolution::Legacy540 => (960, 540),
            Resolution::Hd720 => (1280, 720),
            Resolution::FullHd1080 => (1920, 1080),
        };
        if variant == Variant::Vertical {
            (h, w)
        } else {
            (w, h)
        }
    }
}
pub fn layout_dimensions(variant: Variant) -> (u32, u32) {
    VideoConfig::default().dimensions(variant)
}
pub fn capabilities() -> Value {
    json!({"version":1,"resolutions":["legacy540","hd720","full_hd1080"],"fps":[30,60],
        "coordinate_space":"design960","layouts":{"horizontal":{"width":960,"height":540},"vertical":{"width":540,"height":960}},
        "configuration_scope":"production","requires_idle":true,"base_equals_output":true,
        "validation":"new_presets_are_candidates_until_decoded_media_verification",
        "capture_policy":{"camera":{"requested_width":1280,"requested_height":720,"fps":"device_preset","matches_compositor_fps":false},
            "window":{"fps":"requested_from_obs_at_stream_creation","recreate_on_fps_change":true,"source_lifecycle":"release_previous_obs_source_then_wait_destroy_queue",
                "stream_shutdown":"official_sck_stop_is_asynchronous; transient_stream_overlap_not_verified"},
            "frame_cadence":"capture_and_encoded_frame_rates_require_separate_measurement"},
        "overlay_raster":"source_definition_intrinsic_resolution; canvas_scaling_does_not_increase_glyph_or_asset_density",
        "preview":{"transport":"cpu_bgra","resolution":"output","ui_poll_interval_ms":33}})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_presets_preserve_design_space_and_uniform_scale() {
        for resolution in [
            Resolution::Legacy540,
            Resolution::Hd720,
            Resolution::FullHd1080,
        ] {
            for variant in [Variant::Horizontal, Variant::Vertical] {
                let config = VideoConfig {
                    resolution,
                    ..VideoConfig::default()
                };
                let (w, h) = config.dimensions(variant);
                let (lw, lh) = layout_dimensions(variant);
                assert_eq!(w * lh, h * lw);
                assert_eq!(w % 4, 0);
                assert_eq!(h % 2, 0);
            }
        }
        assert!(
            VideoConfig {
                fps: 59,
                ..VideoConfig::default()
            }
            .validate()
            .is_err()
        );
        assert!(
            VideoConfig {
                version: 2,
                ..VideoConfig::default()
            }
            .validate()
            .is_err()
        );
    }
}
