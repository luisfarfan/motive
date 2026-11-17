use std::{
    ffi::{CStr, CString, c_char, c_void},
    marker::PhantomData,
    rc::Rc,
};

unsafe extern "C" {
    fn motive_create(
        base: *const c_char,
        output_module: *const c_char,
        capture_module: *const c_char,
    ) -> *mut c_void;
    fn motive_destroy(engine: *mut c_void);
    fn motive_error(engine: *mut c_void) -> *const c_char;
    fn motive_version() -> *const c_char;
    fn motive_memory_diagnostics() -> *mut c_char;
    fn motive_frame(engine: *mut c_void, dest: *mut u8, len: usize, timestamp: *mut u64) -> u64;
    fn motive_frame_sequence(engine: *mut c_void) -> u64;
    fn motive_preview_copies(engine: *mut c_void) -> u64;
    fn motive_sync_graph(
        engine: *mut c_void,
        json: *const c_char,
        reconnect: *const c_char,
    ) -> bool;
    fn motive_poll_overlays(engine: *mut c_void);
    fn motive_overlay_state(engine: *mut c_void) -> *mut c_char;
    fn motive_overlay_capabilities(engine: *mut c_void) -> *mut c_char;
    fn motive_update_overlay(
        engine: *mut c_void,
        id: *const c_char,
        definition: *const c_char,
    ) -> bool;
    fn motive_overlay_event(engine: *mut c_void, id: *const c_char, event: *const c_char) -> bool;
    fn motive_overlay_animation_busy(engine: *mut c_void) -> bool;
    fn motive_animate_overlay(
        engine: *mut c_void,
        scene: *const c_char,
        layer: *const c_char,
        animation: *const c_char,
        operation: *mut u64,
    ) -> bool;
    fn motive_cancel_overlay_animation(engine: *mut c_void, operation: u64) -> bool;
    fn motive_ack_overlay_animation(engine: *mut c_void, operation: u64) -> bool;
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
    fn motive_reset_output_target(engine: *mut c_void, target: u32) -> bool;
    fn motive_output_info(engine: *mut c_void, target: u32) -> *mut c_char;
    fn motive_output_packet_trace(engine: *mut c_void, target: u32) -> *mut c_char;
    fn motive_stop_output_target(engine: *mut c_void, target: u32);
    fn motive_total_frames() -> u32;
    fn motive_lagged_frames() -> u32;
    fn motive_busy_drops(engine: *mut c_void) -> u64;
    fn motive_output_state(engine: *mut c_void) -> i32;
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
    fn motive_start_approved_stream(
        engine: *mut c_void,
        url: *const c_char,
        profile: *const c_char,
        credential: *const c_char,
        binding: *const c_char,
    ) -> bool;
    fn motive_destination_credential_status(
        reference: *const c_char,
        binding: *const c_char,
    ) -> i32;
    fn motive_destination_credential_begin_for_view(
        view: *mut c_void,
        metadata: *const c_char,
        request_id: u64,
    ) -> i32;
    fn motive_destination_credential_poll(
        request_id: u64,
        result: *mut NativeCredentialResult,
        consume: bool,
    ) -> bool;
    fn motive_destination_credential_cancel(request_id: u64) -> bool;
    fn motive_destination_credential_busy() -> bool;
    fn motive_encoding_info(engine: *mut c_void) -> *mut c_char;
    fn motive_encoded_frames(engine: *mut c_void) -> u32;
    fn motive_video_skipped_frames() -> u32;
    fn motive_stop_output(engine: *mut c_void);
    fn motive_configure_video(engine: *mut c_void, width: u32, height: u32, fps: u32) -> bool;
    fn motive_video_info(engine: *mut c_void) -> *mut c_char;
    fn motive_invalidate_video(engine: *mut c_void);
    fn motive_devices() -> *mut c_char;
    fn motive_free(value: *mut c_char);
    fn motive_capture_width(engine: *mut c_void) -> u32;
    fn motive_request_permission(kind: i32);
    fn motive_audio_health(engine: *mut c_void) -> i32;
    fn motive_audio_frames(engine: *mut c_void) -> u64;
    fn motive_audio_peak(engine: *mut c_void) -> f32;
    fn motive_close_test_window();
    fn motive_audio_add_target(
        engine: *mut c_void,
        id: *const c_char,
        kind: u32,
        target: *const c_char,
        gain: f32,
        muted: bool,
    ) -> bool;
    fn motive_audio_remove(engine: *mut c_void, id: *const c_char) -> bool;
    fn motive_audio_control(engine: *mut c_void, id: *const c_char, gain: f32, muted: bool)
    -> bool;
    fn motive_audio_state(engine: *mut c_void) -> *mut c_char;
    fn motive_poll_audio(engine: *mut c_void);
    fn motive_audio_disconnect(engine: *mut c_void, id: *const c_char) -> bool;
    fn motive_audio_reconnect(
        engine: *mut c_void,
        id: *const c_char,
        gain: f32,
        muted: bool,
    ) -> bool;
    fn motive_audio_restore_missing_target(
        engine: *mut c_void,
        id: *const c_char,
        kind: u32,
        target: *const c_char,
    ) -> bool;
    fn motive_system_audio_sources(engine: *mut c_void) -> *mut c_char;
    fn motive_audio_rename_id(engine: *mut c_void, old: *const c_char, new: *const c_char) -> bool;
    fn motive_audio_legacy(engine: *mut c_void, device: *const c_char);
}

#[repr(C)]
struct NativeCredentialResult {
    request_id: u64,
    phase: u32,
    code: i32,
    cancel_requested: u8,
    reserved: [u8; 7],
    credential_ref: [c_char; 40],
}
impl Default for NativeCredentialResult {
    fn default() -> Self {
        Self {
            request_id: 0,
            phase: 0,
            code: 0,
            cancel_requested: 0,
            reserved: [0; 7],
            credential_ref: [0; 40],
        }
    }
}
const _: () = assert!(std::mem::size_of::<NativeCredentialResult>() == 64);

#[derive(serde::Serialize)]
pub struct CredentialEnrollmentResult {
    pub request_id: u64,
    pub phase: &'static str,
    pub code: i32,
    pub terminal: bool,
    pub cancel_requested: bool,
    pub credential_ref: Option<String>,
}

/// Main-thread owner. Rc marker intentionally prevents Send/Sync.
pub struct Engine {
    raw: *mut c_void,
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    _main_thread: PhantomData<Rc<()>>,
}
impl Engine {
    pub fn new() -> anyhow::Result<Self> {
        let path = CString::new(crate::paths::obs_contents().as_os_str().as_encoded_bytes())?;
        let output_module =
            CString::new(crate::paths::output_module().as_os_str().as_encoded_bytes())?;
        let capture_module = CString::new(
            crate::paths::mac_capture_module()
                .as_os_str()
                .as_encoded_bytes(),
        )?;
        anyhow::ensure!(
            [&path, &output_module, &capture_module]
                .iter()
                .all(|p| p.as_bytes().len() < 4096),
            "RUNTIME_PATH_TOO_LONG"
        );
        let raw = unsafe {
            motive_create(
                path.as_ptr(),
                output_module.as_ptr(),
                capture_module.as_ptr(),
            )
        };
        anyhow::ensure!(!raw.is_null(), "No se pudo crear libobs");
        let engine = Self {
            raw,
            width: 960,
            height: 540,
            fps: 30,
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
    fn overlay_json(&self, raw: *mut c_char) -> serde_json::Value {
        if raw.is_null() {
            return serde_json::json!({"available":false});
        }
        let value = serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes())
            .unwrap_or(serde_json::json!({"available":false}));
        unsafe { motive_free(raw) };
        value
    }
    pub fn poll_overlays(&mut self) {
        unsafe { motive_poll_overlays(self.raw) }
    }
    pub fn overlay_state(&self) -> serde_json::Value {
        self.overlay_json(unsafe { motive_overlay_state(self.raw) })
    }
    pub fn overlay_capabilities(&self) -> serde_json::Value {
        self.overlay_json(unsafe { motive_overlay_capabilities(self.raw) })
    }
    pub fn update_overlay(
        &mut self,
        id: &str,
        definition: &crate::core::overlays::Definition,
    ) -> anyhow::Result<()> {
        let id = CString::new(id)?;
        let definition = CString::new(serde_json::to_string(definition)?)?;
        self.checked(unsafe { motive_update_overlay(self.raw, id.as_ptr(), definition.as_ptr()) })
    }
    pub fn overlay_event(&mut self, id: &str, event: &str) -> anyhow::Result<()> {
        let id = CString::new(id)?;
        let event = CString::new(event)?;
        self.checked(unsafe { motive_overlay_event(self.raw, id.as_ptr(), event.as_ptr()) })
    }
    pub fn overlay_animation_busy(&self) -> bool {
        unsafe { motive_overlay_animation_busy(self.raw) }
    }
    pub fn animate_overlay(
        &mut self,
        scene: &str,
        layer: &str,
        animation: &crate::core::overlays::Animation,
    ) -> anyhow::Result<u64> {
        let scene = CString::new(scene)?;
        let layer = CString::new(layer)?;
        let a = CString::new(serde_json::to_string(animation)?)?;
        let mut operation = 0;
        self.checked(unsafe {
            motive_animate_overlay(
                self.raw,
                scene.as_ptr(),
                layer.as_ptr(),
                a.as_ptr(),
                &mut operation,
            )
        })?;
        Ok(operation)
    }
    pub fn ack_overlay_animation(&mut self, operation: u64) -> anyhow::Result<()> {
        self.checked(unsafe { motive_ack_overlay_animation(self.raw, operation) })
    }
    pub fn cancel_overlay_animation(&mut self, operation: u64) -> anyhow::Result<()> {
        self.checked(unsafe { motive_cancel_overlay_animation(self.raw, operation) })
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
    pub fn reset_output_target(
        &mut self,
        target: crate::core::output::OutputTarget,
    ) -> anyhow::Result<()> {
        self.checked(unsafe { motive_reset_output_target(self.raw, target.index()) })
    }
    pub fn output_observation(
        &self,
        target: crate::core::output::OutputTarget,
    ) -> crate::core::output::NativeOutput {
        let raw = unsafe { motive_output_info(self.raw, target.index()) };
        assert!(!raw.is_null(), "native output observation unavailable");
        let value = serde_json::from_slice::<crate::core::output::NativeOutput>(
            unsafe { CStr::from_ptr(raw) }.to_bytes(),
        );
        unsafe { motive_free(raw) };
        let value = value.expect("native output observation contract");
        assert!(value.state <= 4, "native output state contract");
        value
    }
    pub fn stop_output_target(&mut self, target: crate::core::output::OutputTarget) {
        unsafe { motive_stop_output_target(self.raw, target.index()) };
    }
    pub fn output_packet_trace(
        &self,
        target: crate::core::output::OutputTarget,
    ) -> serde_json::Value {
        self.overlay_json(unsafe { motive_output_packet_trace(self.raw, target.index()) })
    }
    fn checked(&self, ok: bool) -> anyhow::Result<()> {
        anyhow::ensure!(
            ok,
            "{}",
            unsafe { CStr::from_ptr(motive_error(self.raw)) }.to_string_lossy()
        );
        Ok(())
    }
    pub fn invalidate_video(&mut self) {
        unsafe { motive_invalidate_video(self.raw) };
    }
    pub fn video_info(&self) -> serde_json::Value {
        self.overlay_json(unsafe { motive_video_info(self.raw) })
    }
    pub fn configure_video(
        &mut self,
        video: crate::core::video::VideoConfig,
        variant: crate::core::Variant,
    ) -> anyhow::Result<()> {
        video.validate()?;
        let (width, height) = video.dimensions(variant);
        self.checked(unsafe { motive_configure_video(self.raw, width, height, video.fps) })?;
        let actual = self.video_info();
        anyhow::ensure!(
            actual["available"] == true
                && actual["width"] == width
                && actual["height"] == height
                && actual["fps_num"] == video.fps
                && actual["fps_den"] == 1,
            "VIDEO_CONFIGURATION_MISMATCH"
        );
        self.width = width;
        self.height = height;
        self.fps = video.fps;
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
    pub fn audio_add(
        &mut self,
        input: &crate::core::audio::AudioInput,
        _tone_path: &str,
    ) -> anyhow::Result<()> {
        let id = CString::new(input.id.as_str())?;
        let target = CString::new(input.source.native_target())?;
        self.checked(unsafe {
            motive_audio_add_target(
                self.raw,
                id.as_ptr(),
                input.source.native_kind(),
                target.as_ptr(),
                input.gain_db,
                input.muted,
            )
        })
    }
    pub fn audio_remove(&mut self, id: &str) -> anyhow::Result<()> {
        let id = CString::new(id)?;
        self.checked(unsafe { motive_audio_remove(self.raw, id.as_ptr()) })
    }
    pub fn audio_control(&mut self, input: &crate::core::audio::AudioInput) -> anyhow::Result<()> {
        let id = CString::new(input.id.as_str())?;
        self.checked(unsafe {
            motive_audio_control(self.raw, id.as_ptr(), input.gain_db, input.muted)
        })
    }
    pub fn audio_state(&self) -> crate::core::audio::AudioRuntime {
        let raw = unsafe { motive_audio_state(self.raw) };
        if raw.is_null() {
            return crate::core::audio::AudioRuntime::default();
        }
        let value =
            serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes()).unwrap_or_default();
        unsafe { motive_free(raw) };
        value
    }
    pub fn system_audio_sources(&self) -> anyhow::Result<crate::core::audio::SystemAudioSources> {
        serde_json::from_value(self.overlay_json(unsafe { motive_system_audio_sources(self.raw) }))
            .map_err(|error| {
                anyhow::anyhow!(
                    "AUDIO_STATE_UNAVAILABLE: invalid native system-audio inventory: {error}"
                )
            })
    }
    pub fn poll_audio(&mut self) {
        unsafe { motive_poll_audio(self.raw) };
    }
    pub fn audio_disconnect(&mut self, id: &str) -> anyhow::Result<()> {
        let id = CString::new(id)?;
        self.checked(unsafe { motive_audio_disconnect(self.raw, id.as_ptr()) })
    }
    pub fn audio_reconnect(
        &mut self,
        input: &crate::core::audio::AudioInput,
    ) -> anyhow::Result<()> {
        let id = CString::new(input.id.as_str())?;
        self.checked(unsafe {
            motive_audio_reconnect(self.raw, id.as_ptr(), input.gain_db, input.muted)
        })
    }
    pub fn audio_restore_missing(
        &mut self,
        input: &crate::core::audio::AudioInput,
    ) -> anyhow::Result<()> {
        let id = CString::new(input.id.as_str())?;
        let target = CString::new(input.source.native_target())?;
        self.checked(unsafe {
            motive_audio_restore_missing_target(
                self.raw,
                id.as_ptr(),
                input.source.native_kind(),
                target.as_ptr(),
            )
        })
    }
    pub fn audio_rename_id(&mut self, old: &str, new: &str) -> anyhow::Result<()> {
        let old = CString::new(old)?;
        let new = CString::new(new)?;
        self.checked(unsafe { motive_audio_rename_id(self.raw, old.as_ptr(), new.as_ptr()) })
    }
    pub fn audio_legacy(&mut self, device: &str) -> anyhow::Result<()> {
        let device = CString::new(device)?;
        unsafe { motive_audio_legacy(self.raw, device.as_ptr()) };
        Ok(())
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
    pub fn memory_diagnostics(&self) -> serde_json::Value {
        let raw = unsafe { motive_memory_diagnostics() };
        if raw.is_null() {
            return serde_json::json!({"version":1,"status":"unavailable"});
        }
        let result = serde_json::from_slice(unsafe { CStr::from_ptr(raw) }.to_bytes())
            .unwrap_or_else(
                |_| serde_json::json!({"version":1,"status":"invalid_native_contract"}),
            );
        unsafe {
            motive_free(raw);
        }
        result
    }
    pub fn destination_credential_status(&self, reference: &str, binding: &str) -> i32 {
        let (Ok(reference), Ok(binding)) = (CString::new(reference), CString::new(binding)) else {
            return 4;
        };
        unsafe { motive_destination_credential_status(reference.as_ptr(), binding.as_ptr()) }
    }
    pub fn destination_credential_busy(&self) -> bool {
        unsafe { motive_destination_credential_busy() }
    }
    /// # Safety
    /// `view` must come from the live owner GPUI window's AppKit raw handle.
    pub unsafe fn begin_destination_credential(
        &mut self,
        view: *mut c_void,
        metadata: &str,
        request_id: u64,
    ) -> anyhow::Result<()> {
        let metadata = CString::new(metadata)?;
        let code = unsafe {
            motive_destination_credential_begin_for_view(view, metadata.as_ptr(), request_id)
        };
        anyhow::ensure!(
            code == 0,
            "{}",
            match code {
                6 => "CREDENTIAL_SIGNED_IDENTITY_REQUIRED",
                7 | 8 => "CREDENTIAL_ENROLLMENT_BUSY",
                9 => "CREDENTIAL_WINDOW_UNAVAILABLE",
                _ => "INVALID_CREDENTIAL_ENROLLMENT",
            }
        );
        Ok(())
    }
    pub fn poll_destination_credential(
        &mut self,
        request_id: u64,
    ) -> Option<CredentialEnrollmentResult> {
        let mut raw = NativeCredentialResult::default();
        if !unsafe { motive_destination_credential_poll(request_id, &mut raw, true) } {
            return None;
        }
        let phase = match raw.phase {
            1 => "awaiting_user",
            2 => "writing",
            3 => "stored",
            4 => "cancelled",
            5 => "failed",
            6 => "stored_after_cancel",
            _ => "unknown",
        };
        let reference = unsafe { CStr::from_ptr(raw.credential_ref.as_ptr()) }
            .to_str()
            .ok()
            .filter(|r| crate::core::output::valid_credential_ref(r))
            .map(str::to_owned);
        Some(CredentialEnrollmentResult {
            request_id: raw.request_id,
            phase,
            code: raw.code,
            terminal: raw.phase >= 3,
            cancel_requested: raw.cancel_requested != 0,
            credential_ref: reference,
        })
    }
    pub fn cancel_destination_credential(&mut self, request_id: u64) {
        unsafe {
            motive_destination_credential_cancel(request_id);
        }
    }
    pub(super) fn start_approved_stream(
        &mut self,
        url: &str,
        profile: &str,
        credential: &str,
        binding: &str,
    ) -> anyhow::Result<()> {
        let (url, profile, credential, binding) = (
            CString::new(url)?,
            CString::new(profile)?,
            CString::new(credential)?,
            CString::new(binding)?,
        );
        self.checked(unsafe {
            motive_start_approved_stream(
                self.raw,
                url.as_ptr(),
                profile.as_ptr(),
                credential.as_ptr(),
                binding.as_ptr(),
            )
        })
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
