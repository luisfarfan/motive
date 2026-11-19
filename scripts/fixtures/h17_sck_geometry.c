/* Exercise the production predicate/settings handoff with real libobs sources.
 * Dimensions are synthetic; no SCK, graphics reset, audio or devices run. */
#include "capture-admission.h"
#include <obs-module.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned accepted, destroyed, after_geometry;
static const char *name(void *unused) { (void)unused; return "H17 geometry contract"; }
static void *create(obs_data_t *settings, obs_source_t *source)
{
    motive_capture_reset_admission(settings);
    double width = obs_data_get_double(settings, "width");
    double height = obs_data_get_double(settings, "height");
    if (!motive_capture_window_geometry_valid(width, height)) {
        motive_capture_mark_geometry_not_ready(source);
        return NULL;
    }
    volatile size_t converted_width = (size_t)width, converted_height = (size_t)height;
    (void)converted_width; (void)converted_height;
    after_geometry++;
    if (obs_data_get_bool(settings, "other_failure")) return NULL;
    accepted++;
    return malloc(1);
}
static void destroy(void *data) { destroyed++; free(data); }
static uint32_t dimension(void *unused) { (void)unused; return 16; }
static struct obs_source_info fixture = {
    .id = "h17_sck_geometry", .type = OBS_SOURCE_TYPE_INPUT,
    .output_flags = OBS_SOURCE_VIDEO, .get_name = name,
    .create = create, .destroy = destroy, .get_width = dimension, .get_height = dimension,
};
static void barrier(void *unused) { (void)unused; }

struct geometry_case {
    const char *label;
    double width, height;
    bool geometry_valid, other_failure;
};

static unsigned run_case(struct geometry_case test, obs_data_t *reused)
{
    obs_data_t *settings = reused ? obs_data_newref(reused) : obs_data_create();
    obs_data_set_double(settings, "width", test.width);
    obs_data_set_double(settings, "height", test.height);
    obs_data_set_bool(settings, "other_failure", test.other_failure);
    // A stale marker in a supplied settings object must never survive create.
    if (!reused) obs_data_set_bool(settings, MOTIVE_CAPTURE_GEOMETRY_NOT_READY, true);
    unsigned before = after_geometry;
    obs_source_t *source = obs_source_create_private("h17_sck_geometry", test.label, settings);
    obs_data_release(settings); // Match graph.inc: caller releases before reading error.
    if (!source) return 1;
    bool valid = !obs_obj_invalid(source);
    bool expected = test.geometry_valid && !test.other_failure;
    const char *error = motive_capture_creation_error(source);
    bool handoff = !strcmp(error, test.geometry_valid ? "SOURCE_CREATE_FAILED" : MOTIVE_CAPTURE_NOT_READY_ERROR);
    bool admission = after_geometry - before == (unsigned)test.geometry_valid;
    obs_data_t *retained = obs_source_get_settings(source);
    bool marker = obs_data_get_bool(retained, MOTIVE_CAPTURE_GEOMETRY_NOT_READY);
    obs_data_release(retained);
    bool pass = valid == expected && handoff && admission && marker == !test.geometry_valid;
    printf("{\"case\":\"%s\",\"status\":\"%s\",\"valid\":%s,\"expected_valid\":%s,"
           "\"error_handoff\":%s,\"post_geometry_reached\":%s,\"marker\":%s}\n",
           test.label, pass ? "PASS" : "FAIL", valid ? "true" : "false", expected ? "true" : "false",
           handoff ? "true" : "false", admission ? "true" : "false", marker ? "true" : "false");
    obs_source_release(source);
    obs_queue_task(OBS_TASK_DESTROY, barrier, NULL, true);
    return !pass;
}

int main(void)
{
    if (!obs_startup("en-US", NULL, NULL)) return 2;
    obs_register_source(&fixture);
    struct geometry_case cases[] = {
        {"zero_both", 0, 0, false, false},
        {"zero_width", 0, 452, false, false},
        {"zero_height", 680, 0, false, false},
        {"negative_width", -1, 452, false, false},
        {"negative_height", 680, -1, false, false},
        {"subpixel_width", 0.5, 452, false, false},
        {"subpixel_height", 680, 0.5, false, false},
        {"nan_width", NAN, 452, false, false},
        {"nan_height", 680, NAN, false, false},
        {"infinite_width", INFINITY, 452, false, false},
        {"infinite_height", 680, INFINITY, false, false},
        {"negative_infinity", -INFINITY, 452, false, false},
        {"size_max_width", (double)SIZE_MAX, 452, false, false},
        {"size_max_height", 680, (double)SIZE_MAX, false, false},
        {"above_size_max", nextafter((double)SIZE_MAX, INFINITY), 452, false, false},
        {"last_representable_size", nextafter((double)SIZE_MAX, 0), 452, true, false},
        {"one_pixel", 1, 1, true, false},
        {"valid_fractional", 1.5, 2.5, true, false},
        {"observed_initial_geometry", 680, 452, true, false},
        {"unrelated_create_failure", 680, 452, true, true},
    };
    unsigned failures = strcmp(motive_capture_creation_error(NULL), "SOURCE_CREATE_FAILED") != 0;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) failures += run_case(cases[i], NULL);
    // Explicitly reuse one settings object across rejection and valid selection.
    obs_data_t *reused = obs_data_create();
    failures += run_case((struct geometry_case){"reused_rejected", 0, 0, false, false}, reused);
    failures += run_case((struct geometry_case){"reused_ready", 680, 452, true, false}, reused);
    obs_data_release(reused);
    obs_shutdown();
    failures += destroyed != accepted;
    printf("{\"status\":\"%s\",\"failed_cases\":%u,\"accepted\":%u,\"destroyed\":%u,"
           "\"post_geometry_entries\":%u,\"physical_capture\":\"NOT_EVALUATED\"}\n",
           failures ? "FAIL" : "PASS", failures, accepted, destroyed, after_geometry);
    return failures ? 1 : 0;
}
