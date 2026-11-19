/* Admission evidence survives a rejected OBS create callback in source settings.
 * No capture fallback, media clock or automatic retry is introduced here. */
#pragma once
#include <obs.h>
#include <math.h>
#include <stdint.h>

#define MOTIVE_CAPTURE_GEOMETRY_NOT_READY "motive_capture_geometry_not_ready"
#define MOTIVE_CAPTURE_NOT_READY_ERROR \
    "CAPTURE_NOT_READY: macOS no ha publicado dimensiones válidas para esta ventana. Muéstrala y vuelve a seleccionarla."

static inline bool motive_capture_window_geometry_valid(double width, double height)
{
    /* SIZE_MAX rounds up when converted to double on ARM64. Strict comparison
     * excludes that unrepresentable endpoint before the plugin's size_t casts. */
    return isfinite(width) && isfinite(height) && width >= 1.0 && height >= 1.0 &&
           width < (double)SIZE_MAX && height < (double)SIZE_MAX;
}

static inline void motive_capture_reset_admission(obs_data_t *settings)
{
    obs_data_set_bool(settings, MOTIVE_CAPTURE_GEOMETRY_NOT_READY, false);
}

static inline void motive_capture_mark_geometry_not_ready(obs_source_t *source)
{
    obs_data_t *settings = obs_source_get_settings(source);
    obs_data_set_bool(settings, MOTIVE_CAPTURE_GEOMETRY_NOT_READY, true);
    obs_data_release(settings);
}

static inline const char *motive_capture_creation_error(obs_source_t *source)
{
    if (!source) return "SOURCE_CREATE_FAILED";
    obs_data_t *settings = obs_source_get_settings(source);
    bool not_ready = obs_data_get_bool(settings, MOTIVE_CAPTURE_GEOMETRY_NOT_READY);
    obs_data_release(settings);
    return not_ready ? MOTIVE_CAPTURE_NOT_READY_ERROR : "SOURCE_CREATE_FAILED";
}
