//! Opt-in H17 measurements from GPUI's own profiler, separate from libobs.
//! No timers, state queries, media clocks, paths, or user content are added.
use gpui_kit::{
    Window,
    profiler::{FrameDurationSnapshot, InputLatencySnapshot},
};
use serde_json::json;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub(super) struct Profile {
    started: Instant,
    sampled: Instant,
    frames: FrameDurationSnapshot,
    input: InputLatencySnapshot,
    heartbeat_us: Vec<u64>,
    heartbeat_overflow: u64,
    preview_updates: u64,
    notifications_without_preview: u64,
}

impl Profile {
    pub(super) fn new(window: &Window) -> Option<Self> {
        (std::env::var("MOTIVE_UI_PROFILE").as_deref() == Ok("1")).then(|| Self {
            started: Instant::now(),
            sampled: Instant::now(),
            frames: window.frame_duration_snapshot(),
            input: window.input_latency_snapshot(),
            heartbeat_us: Vec::with_capacity(128),
            heartbeat_overflow: 0,
            preview_updates: 0,
            notifications_without_preview: 0,
        })
    }

    pub(super) fn heartbeat(&mut self, elapsed: Duration, preview_updated: bool) {
        self.preview_updates += u64::from(preview_updated);
        self.notifications_without_preview += u64::from(!preview_updated);
        // Sampling may stop when hidden; never retain an unbounded history.
        if self.heartbeat_us.len() < 128 {
            self.heartbeat_us.push(elapsed.as_micros() as u64);
        } else {
            self.heartbeat_overflow += 1;
        }
    }

    pub(super) fn sample(&mut self, window: &Window) {
        if self.sampled.elapsed() < Duration::from_secs(1) {
            return;
        }
        let now = Instant::now();
        let frames = window.frame_duration_snapshot();
        let input = window.input_latency_snapshot();
        // The library exposes HDR histograms; use its samples rather than
        // substituting the heartbeat, libobs render time, or RPC latency.
        macro_rules! interval {
            ($current:expr, $previous:expr) => {{
                let mut delta = $current.clone();
                if delta.subtract(&$previous).is_err() {
                    json!({"status":"FAIL", "reason":"histogram_discontinuity"})
                } else if delta.is_empty() {
                    json!({"status":"NOT_EVALUATED", "samples":0})
                } else {
                    json!({"status":"PASS", "samples":delta.len(),
                        "p50_us":delta.value_at_quantile(0.50) as f64 / 1000.,
                        "p95_us":delta.value_at_quantile(0.95) as f64 / 1000.,
                        "max_us":delta.max() as f64 / 1000.})
                }
            }};
        }
        self.heartbeat_us.sort_unstable();
        let heartbeats = self.heartbeat_us.len();
        let heartbeat = if heartbeats == 0 {
            json!({"status":"NOT_EVALUATED", "samples":0})
        } else {
            json!({"status":if self.heartbeat_overflow == 0 {"PASS"}else{"PARTIAL"},
                "samples":heartbeats,"dropped_samples":self.heartbeat_overflow,
                "p50_us":self.heartbeat_us[(heartbeats - 1) / 2],
                "p95_us":self.heartbeat_us[(heartbeats * 95).div_ceil(100) - 1],
                "max_us":self.heartbeat_us[heartbeats - 1]})
        };
        eprintln!(
            "MOTIVE_UI_PROFILE {}",
            json!({
                "version":1,"pid":std::process::id(),
                "backend":if cfg!(feature="gpui-fast") {"gpui-fast"}else{"gpui-pre"},
                "elapsed_seconds":now.duration_since(self.started).as_secs_f64(),
                "interval_seconds":now.duration_since(self.sampled).as_secs_f64(),
                "wall_unix_seconds":SystemTime::now().duration_since(UNIX_EPOCH).ok().map(|d|d.as_secs_f64()),
                "draw":interval!(frames.draw_duration_histogram,self.frames.draw_duration_histogram),
                "dirty_to_present":interval!(frames.dirty_to_present_histogram,self.frames.dirty_to_present_histogram),
                "animating_present_interval":interval!(frames.present_interval_histogram,self.frames.present_interval_histogram),
                "input_to_frame":interval!(input.latency_histogram,self.input.latency_histogram),
                "input_mid_draw_excluded":input.mid_draw_events_dropped.saturating_sub(self.input.mid_draw_events_dropped),
                "preview_updates":self.preview_updates,
                "notifications_without_preview":self.notifications_without_preview,
                "heartbeat":heartbeat
            })
        );
        self.frames = frames;
        self.input = input;
        self.sampled = now;
        self.heartbeat_us.clear();
        self.heartbeat_overflow = 0;
        self.preview_updates = 0;
        self.notifications_without_preview = 0;
    }
}
