use std::{
    ffi::{CStr, CString, c_char, c_void},
    marker::PhantomData,
    rc::Rc,
};

unsafe extern "C" {
    fn motive_create(base: *const c_char) -> *mut c_void;
    fn motive_destroy(engine: *mut c_void);
    fn motive_error(engine: *mut c_void) -> *const c_char;
    fn motive_version() -> *const c_char;
    fn motive_frame(engine: *mut c_void, dest: *mut u8, len: usize, timestamp: *mut u64) -> u64;
    fn motive_frame_sequence(engine: *mut c_void) -> u64;
    fn motive_preview_copies(engine: *mut c_void) -> u64;
    fn motive_sync_graph(
        engine: *mut c_void,
        json: *const c_char,
        reconnect: *const c_char,
    ) -> bool;
    fn motive_graph_health(engine: *mut c_void) -> *mut c_char;
    fn motive_poll_scene(engine: *mut c_void);
    fn motive_switch_scene(
        engine: *mut c_void,
        id: *const c_char,
        kind: u32,
        duration: u32,
    ) -> bool;
    fn motive_cancel_scene(engine: *mut c_void, operation: u64) -> bool;
    fn motive_scene_state(engine: *mut c_void) -> *mut c_char;
    fn motive_reset_output(engine: *mut c_void) -> bool;
    fn motive_total_frames() -> u32;
    fn motive_lagged_frames() -> u32;
    fn motive_busy_drops(engine: *mut c_void) -> u64;
    fn motive_output_state(engine: *mut c_void) -> i32;
    fn motive_output_code(engine: *mut c_void) -> i32;
    fn motive_output_bytes(engine: *mut c_void) -> u64;
    fn motive_output_frames(engine: *mut c_void) -> u32;
    fn motive_output_drops(engine: *mut c_void) -> i32;
    fn motive_start_output(
        engine: *mut c_void,
        path: *const c_char,
        local_stream: bool,
        policy: *const c_char,
    ) -> bool;
    fn motive_start_stream(
        engine: *mut c_void,
        url: *const c_char,
        profile: *const c_char,
        credential: *const c_char,
    ) -> bool;
    fn motive_credential_status(reference: *const c_char, port: i32) -> i32;
    fn motive_encoding_info(engine: *mut c_void) -> *mut c_char;
    fn motive_encoded_frames(engine: *mut c_void) -> u32;
    fn motive_video_skipped_frames() -> u32;
    fn motive_stop_output(engine: *mut c_void);
    fn motive_variant(engine: *mut c_void, vertical: bool) -> bool;
    fn motive_devices() -> *mut c_char;
    fn motive_free(value: *mut c_char);
    fn motive_capture_width(engine: *mut c_void) -> u32;
    fn motive_request_permission(kind: i32);
    fn motive_audio_health(engine: *mut c_void) -> i32;
    fn motive_audio_frames(engine: *mut c_void) -> u64;
    fn motive_audio_peak(engine: *mut c_void) -> f32;
    fn motive_close_test_window();
    fn motive_audio(engine: *mut c_void, id: *const c_char, tone_path: *const c_char) -> bool;
}

/// Main-thread owner. Rc marker intentionally prevents Send/Sync.
pub struct Engine {
    raw: *mut c_void,
    pub width: u32,
    pub height: u32,
    _main_thread: PhantomData<Rc<()>>,
}
impl Engine {
    pub fn new() -> anyhow::Result<Self> {
        let path = CString::new(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/.deps/OBS.app/Contents"
        ))?;
        let raw = unsafe { motive_create(path.as_ptr()) };
        anyhow::ensure!(!raw.is_null(), "No se pudo crear libobs");
        let engine = Self {
            raw,
            width: 960,
            height: 540,
            _main_thread: PhantomData,
        };
        let error = unsafe { CStr::from_ptr(motive_error(raw)) }.to_string_lossy();
        anyhow::ensure!(error.is_empty(), "{error}");
        Ok(engine)
    }
    pub fn version(&self) -> String {
        unsafe { CStr::from_ptr(motive_version()) }
            .to_string_lossy()
            .into_owned()
    }
    pub fn frame(&self) -> (u64, u64, Vec<u8>) {
        let mut pixels = vec![0; self.width as usize * self.height as usize * 4];
        let mut timestamp = 0;
        let sequence =
            unsafe { motive_frame(self.raw, pixels.as_mut_ptr(), pixels.len(), &mut timestamp) };
        (sequence, timestamp, pixels)
    }
    pub fn frame_if_new(&self, previous: u64) -> Option<(u64, u64, Vec<u8>)> {
        let sequence = unsafe { motive_frame_sequence(self.raw) };
        (sequence > 0 && sequence != previous).then(|| self.frame())
    }
    pub fn sync_graph(&mut self, graph: &serde_json::Value, reconnect: &str) -> anyhow::Result<()> {
        let graph = CString::new(serde_json::to_string(graph)?)?;
        let reconnect = CString::new(reconnect)?;
        self.checked(unsafe { motive_sync_graph(self.raw, graph.as_ptr(), reconnect.as_ptr()) })
    }
    pub fn graph_health(&self) -> serde_json::Value {
        let raw = unsafe { motive_graph_health(self.raw) };
        if raw.is_null() {
            return serde_json::json!([]);
        }
        let value =
            serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes()).unwrap_or_default();
        unsafe { motive_free(raw) };
        value
    }
    pub fn poll_scene(&mut self) {
        unsafe { motive_poll_scene(self.raw) };
    }
    pub fn scene_state(&self) -> crate::scene::TransitionState {
        let raw = unsafe { motive_scene_state(self.raw) };
        assert!(!raw.is_null(), "native scene state unavailable");
        let value = serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes());
        unsafe { motive_free(raw) };
        value.expect("native scene state contract")
    }
    pub fn switch_scene(
        &mut self,
        id: &str,
        config: crate::scene::TransitionConfig,
    ) -> anyhow::Result<()> {
        config.validate()?;
        let id = CString::new(id)?;
        let kind = match config.kind {
            crate::scene::TransitionKind::Cut => 0,
            crate::scene::TransitionKind::Fade => 1,
        };
        self.checked(unsafe {
            motive_switch_scene(self.raw, id.as_ptr(), kind, config.duration_ms)
        })
    }
    pub fn cancel_scene(&mut self, operation: u64) -> anyhow::Result<()> {
        self.checked(unsafe { motive_cancel_scene(self.raw, operation) })
    }
    pub fn reset_output(&mut self) -> anyhow::Result<()> {
        self.checked(unsafe { motive_reset_output(self.raw) })
    }
    fn checked(&self, ok: bool) -> anyhow::Result<()> {
        anyhow::ensure!(
            ok,
            "{}",
            unsafe { CStr::from_ptr(motive_error(self.raw)) }.to_string_lossy()
        );
        Ok(())
    }
    pub fn variant(&mut self, vertical: bool) -> anyhow::Result<()> {
        self.checked(unsafe { motive_variant(self.raw, vertical) })?;
        (self.width, self.height) = if vertical { (540, 960) } else { (960, 540) };
        Ok(())
    }
    pub fn devices(&self) -> serde_json::Value {
        let raw = unsafe { motive_devices() };
        if raw.is_null() {
            return serde_json::json!({});
        }
        let value =
            serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes()).unwrap_or_default();
        unsafe { motive_free(raw) };
        value
    }
    pub fn audio(&mut self, id: &str, tone_path: &str) -> anyhow::Result<()> {
        let id = CString::new(id)?;
        let path = CString::new(tone_path)?;
        self.checked(unsafe { motive_audio(self.raw, id.as_ptr(), path.as_ptr()) })
    }
    pub fn encoding_info(&self) -> serde_json::Value {
        let raw = unsafe { motive_encoding_info(self.raw) };
        if raw.is_null() {
            return serde_json::json!({});
        }
        let value =
            serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes()).unwrap_or_default();
        unsafe { motive_free(raw) };
        value
    }
    pub fn start_output(&mut self, path: &str, stream: bool, policy: &str) -> anyhow::Result<()> {
        let path = CString::new(path)?;
        let policy = CString::new(policy)?;
        self.checked(unsafe {
            motive_start_output(self.raw, path.as_ptr(), stream, policy.as_ptr())
        })
    }
    pub fn credential_status(&self, reference: &str, port: u16) -> i32 {
        let Ok(reference) = CString::new(reference) else {
            return 4;
        };
        unsafe { motive_credential_status(reference.as_ptr(), i32::from(port)) }
    }
    pub fn start_stream(
        &mut self,
        url: &str,
        profile: &str,
        credential: Option<&str>,
    ) -> anyhow::Result<()> {
        let url = CString::new(url)?;
        let profile = CString::new(profile)?;
        let credential = CString::new(credential.unwrap_or_default())?;
        self.checked(unsafe {
            motive_start_stream(
                self.raw,
                url.as_ptr(),
                profile.as_ptr(),
                credential.as_ptr(),
            )
        })
    }
    pub fn stop_output(&mut self) {
        unsafe { motive_stop_output(self.raw) };
    }
    pub fn output_state(&self) -> i32 {
        unsafe { motive_output_state(self.raw) }
    }
    pub fn output_code(&self) -> i32 {
        unsafe { motive_output_code(self.raw) }
    }
    pub fn audio_health(&self) -> i32 {
        unsafe { motive_audio_health(self.raw) }
    }
    pub fn request_permission(&self, kind: i32) {
        unsafe { motive_request_permission(kind) };
    }
    pub fn close_test_window(&self) {
        unsafe { motive_close_test_window() };
    }
    pub fn stats(&self) -> serde_json::Value {
        unsafe {
            serde_json::json!({"rendered_frames":motive_total_frames(),"lagged_frames":motive_lagged_frames(),"preview_busy_drops":motive_busy_drops(self.raw),"preview_copies":motive_preview_copies(self.raw),"output_bytes":motive_output_bytes(self.raw),"output_frames":motive_output_frames(self.raw),"output_dropped_frames":motive_output_drops(self.raw),"encoded_frames":motive_encoded_frames(self.raw),"video_skipped_frames":motive_video_skipped_frames(),"capture_width":motive_capture_width(self.raw),"audio_frames":motive_audio_frames(self.raw),"audio_peak":motive_audio_peak(self.raw)})
        }
    }
}
impl Drop for Engine {
    fn drop(&mut self) {
        unsafe { motive_destroy(self.raw) };
    }
}
