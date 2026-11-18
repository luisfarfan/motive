/* Synthetic admission branches extracted from pinned/patched SCK source,
 * passed through real libobs create/invalid/destruction. No SCK APIs, video
 * reset, audio devices or windows are used. This is not physical capture. */
#include <obs-module.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned destroyed;
static bool missing_window(void) { return @MISSING_WINDOW@; }
static bool failed_screen_output(void)
{ bool did_add_output = false; (void)did_add_output; return @SCREEN_OUTPUT@; }
static bool failed_audio_output(void)
{ bool did_add_output = false; (void)did_add_output; return @AUDIO_OUTPUT@; }
static bool matches(uint32_t window_id, uint32_t expected_window,
                    int64_t owner_pid, int64_t expected_pid)
{ (void)owner_pid; (void)expected_pid; return @WINDOW_MATCH@; }
static const char *name(void *unused) { (void)unused; return "H17 SCK admission contract"; }
static void *create(obs_data_t *settings, obs_source_t *source)
{
    (void)source;
    int scenario = (int)obs_data_get_int(settings, "scenario");
    bool accepted = scenario == 0 ? missing_window() :
        scenario == 1 ? failed_screen_output() : scenario == 2 ? failed_audio_output() :
        matches(scenario == 6 ? 43 : 42, 42, scenario == 7 ? 0 : 100,
                scenario == 3 ? 200 : scenario == 5 ? 0 : 100) ? true : missing_window();
    return accepted ? malloc(1) : NULL;
}
static void destroy(void *data) { destroyed++; free(data); }
static uint32_t dimension(void *unused) { (void)unused; return 16; }
static struct obs_source_info fixture = {
    .id = "h17_sck_admission", .type = OBS_SOURCE_TYPE_INPUT,
    .output_flags = OBS_SOURCE_VIDEO, .get_name = name,
    .create = create, .destroy = destroy, .get_width = dimension, .get_height = dimension,
};
static void barrier(void *unused) { (void)unused; }

int main(void)
{
    if (!obs_startup("en-US", NULL, NULL)) return 2;
    obs_register_source(&fixture);
    unsigned failures = 0, accepted = 0;
    const char *labels[] = {"missing_window", "failed_screen_output", "failed_audio_output",
        "wrong_owner_pid", "matching_identity", "owner_pid_unspecified",
        "wrong_window_id", "owner_unavailable"};
    for (int scenario = 0; scenario < 8; scenario++) {
        obs_data_t *settings = obs_data_create();
        obs_data_set_int(settings, "scenario", scenario);
        obs_source_t *source = obs_source_create_private("h17_sck_admission", labels[scenario], settings);
        obs_data_release(settings);
        if (!source) return 3;
        bool valid = !obs_obj_invalid(source);
        bool expected = scenario == 4 || scenario == 5;
        accepted += valid;
        failures += valid != expected;
        printf("{\"case\":\"%s\",\"valid\":%s,\"expected_valid\":%s}\n",
               labels[scenario], valid ? "true" : "false", expected ? "true" : "false");
        obs_source_release(source);
        obs_queue_task(OBS_TASK_DESTROY, barrier, NULL, true);
    }
    obs_shutdown();
    failures += destroyed != accepted;
    printf("{\"status\":\"%s\",\"failed_cases\":%u,\"accepted\":%u,\"destroyed\":%u}\n",
           failures ? "FAIL" : "PASS", failures, accepted, destroyed);
    return failures ? 1 : 0;
}
