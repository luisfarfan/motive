/* Motive observations for the pinned official OBS ScreenCaptureKit module.
 * No media copies, timers, capture reconstruction or rendering changes. */
#pragma once
#include <stdatomic.h>
#include <stdint.h>
#include <obs-module.h>
#include <CoreMedia/CMSampleBuffer.h>
#include <IOSurface/IOSurface.h>

typedef struct {
    atomic_uint_fast64_t created_ns, callbacks, last_callback_ns;
    atomic_uint_fast64_t surfaces, first_surface_ns, last_surface_ns;
    atomic_uint_fast64_t presentations, last_presentation_ns;
    atomic_uint_fast64_t texture_bind_attempts, renders, last_render_ns;
    atomic_uint_fast64_t missing_images, invalid_samples, pts_repeats, pts_regressions;
    atomic_uint_fast64_t statuses[6], errors, last_error_ns;
    atomic_uint_fast64_t status_last_seen_ns[6], status_changed_ns, status_changes;
    atomic_int_fast64_t last_pts_ns, presented_pts_ns, last_error_code;
    atomic_uint_fast32_t surface_id, presented_surface_id;
    atomic_int status, phase;
    atomic_bool user_stopped;
} motive_sck_diagnostics;

void motive_sck_diagnostics_init(motive_sck_diagnostics *d);
void motive_sck_diagnostics_register(motive_sck_diagnostics *d, obs_source_t *source);
void motive_sck_diagnostics_sample(motive_sck_diagnostics *d, CMSampleBufferRef sample);
void motive_sck_diagnostics_present(motive_sck_diagnostics *d, IOSurfaceRef surface);
void motive_sck_diagnostics_render(motive_sck_diagnostics *d);
void motive_sck_diagnostics_error(motive_sck_diagnostics *d, int64_t code);
void motive_sck_diagnostics_phase(motive_sck_diagnostics *d, int phase);
