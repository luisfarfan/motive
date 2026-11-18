/* Borrowed scene items must be invalidated before OBS releases them. A failed
 * capture replacement leaves the committed graph in place for explicit retry. */
#pragma once
#include <obs.h>
#include <stddef.h>

static inline void motive_detach_scene_source(obs_sceneitem_t **items, size_t count,
                                             obs_source_t *source)
{
    for (size_t i = 0; i < count; i++) {
        obs_sceneitem_t *item = items[i];
        if (item && obs_sceneitem_get_source(item) == source) {
            items[i] = NULL;
            obs_sceneitem_remove(item);
        }
    }
}
