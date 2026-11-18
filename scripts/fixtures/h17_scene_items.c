/* Ownership contract against real libobs scenes. No device, video/audio reset,
 * stream, screen capture or GPUI window is opened by this test. */
#include <obs-module.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include "scene-items.h"

static atomic_uint destroyed;
static const char *name(void *unused) { (void)unused; return "H17 ownership fixture"; }
static void *create(obs_data_t *settings, obs_source_t *source)
{ (void)settings; (void)source; return malloc(1); }
static void destroy(void *data) { destroyed++; free(data); }
static uint32_t dimension(void *data) { (void)data; return 16; }
static struct obs_source_info fixture = {
    .id = "h17_ownership", .type = OBS_SOURCE_TYPE_INPUT,
    .output_flags = OBS_SOURCE_VIDEO, .get_name = name,
    .create = create, .destroy = destroy, .get_width = dimension, .get_height = dimension,
};
static bool legacy_detach(obs_scene_t *scene, obs_sceneitem_t *item, void *source)
{
    (void)scene;
    if (obs_sceneitem_get_source(item) == source) obs_sceneitem_remove(item);
    return true;
}
static bool count_item(obs_scene_t *scene, obs_sceneitem_t *item, void *count)
{ (void)scene; (void)item; (*(unsigned *)count)++; return true; }
static void barrier(void *unused) { (void)unused; }

int main(int argc, char **argv)
{
    (void)argv;
    bool legacy = argc > 1, ok = true;
    if (!obs_startup("en-US", NULL, NULL)) return 2;
    obs_register_source(&fixture);
    obs_source_t *capture = obs_source_create_private("h17_ownership", "retired", NULL);
    obs_source_t *other = obs_source_create_private("h17_ownership", "retained", NULL);
    if (!capture || !other || obs_obj_invalid(capture) || obs_obj_invalid(other)) return 3;
    obs_scene_t *scenes[2] = {obs_scene_create_private("one"), obs_scene_create_private("two")};
    obs_sceneitem_t *items[2][3];
    for (unsigned s = 0; s < 2; s++) {
        items[s][0] = obs_scene_add(scenes[s], capture);
        items[s][1] = obs_scene_add(scenes[s], other);
        items[s][2] = obs_scene_add(scenes[s], capture);
        if (legacy) obs_scene_enum_items(scenes[s], legacy_detach, capture);
        else motive_detach_scene_source(items[s], 3, capture);
        unsigned count = 0;
        obs_scene_enum_items(scenes[s], count_item, &count);
        ok &= count == 1 && items[s][0] == NULL && items[s][2] == NULL;
        ok &= obs_sceneitem_get_source(items[s][1]) == other;
        if (!legacy) motive_detach_scene_source(items[s], 3, capture); // idempotent retry
    }
    // Model the recovery-failed branch: no new source/graph is committed.
    obs_source_release(capture);
    // No audio/video threads exist in this contract test; the full multimedia
    // barrier returns false in that configuration. Join the destruction queue.
    obs_queue_task(OBS_TASK_DESTROY, barrier, NULL, true);
    ok &= destroyed == 1; // no hidden strong item reference keeps capture alive
    for (unsigned s = 0; s < 2; s++) {
        if (!legacy) for (unsigned i = 0; i < 3; i++)
            if (items[s][i]) ok &= obs_sceneitem_get_source(items[s][i]) == other;
        obs_scene_release(scenes[s]);
    }
    obs_queue_task(OBS_TASK_DESTROY, barrier, NULL, true);
    obs_source_release(other);
    obs_queue_task(OBS_TASK_DESTROY, barrier, NULL, true);
    ok &= destroyed == 2;
    obs_shutdown();
    printf("{\"status\":\"%s\",\"legacy\":%s,\"destroyed_sources\":%u,\"physical_capture\":false}\n",
           ok ? "PASS" : "FAIL", legacy ? "true" : "false", atomic_load(&destroyed));
    return ok ? 0 : 1;
}
