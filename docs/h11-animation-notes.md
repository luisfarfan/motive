# H11 — Native animation integration notes

`native/overlays/animation.inc` is an internal, bounded scene-item action runner.
It does not render pixels, encode frames, modify a source's shared properties,
or process audio. The owner creates it **after** libobs/video and official
`obs-transitions` initialization, and destroys it **before** graph destruction
and `obs_shutdown`.

## Contract for the engine owner

- `overlay_animator_create()` allocates eight job slots and registers one
  `obs_add_tick_callback`. `overlay_animator_destroy()` unregisters synchronously,
  restores unfinished items, releases all references and frees the runner.
- `overlay_animation_start(...)` accepts a retained-capable `obs_sceneitem_t`,
  stable scene/layer IDs, a kind, easing and bounded parameters. It returns an
  increasing `operation_id`, returned explicitly by the shared command result. Acceptance queues native initialization on the next
  video tick; it does not claim that pixels have already changed.
- `overlay_animation_cancel(id)` requests cancellation. A running job changes to
  `cancel_pending`; the next native tick restores its baseline and publishes
  `cancelled`. Repeated cancel of a retained terminal operation is an idempotent
  success, leaving its terminal phase unchanged. Unknown/evicted IDs fail.
- `overlay_animation_busy()` includes `running`, `cancel_pending` and terminal
  results awaiting owner acknowledgment (`pending_ack`). Public `running` and
  `pending_ack` booleans distinguish execution from model commit.
- `overlay_animation_state()` returns `available`, `busy`, `clock`, `capacity`,
  `last_operation_id`, `jobs` and the most recent control error. Each job includes
  ID, scene/layer IDs, kind, easing, parameters, phase, normalized progress,
  initialization/start time, elapsed time, baseline/target visibility, native
  transition activity and error. Foundation allocation occurs after copying
  snapshots under the short mutex; queries never advance time or mutate items.
- `overlay_animator_reset()` synchronously cancels unfinished jobs and rearms
  the tick. Call it before replacing/releasing graph items, even during fault
  handling. Retained terminal snapshots contain no OBS references. The eight running/terminal entries are bounded; only acknowledged terminal
  entries may be replaced. At most eight concurrent jobs or unacknowledged
  results are accepted. A full queue returns backpressure; it never discards
  an unseen completion.

The caller must serialize control entry points on the existing owner, invoke
them outside OBS scene/source/draw callbacks, and retain graph ownership during
`start`. Do not wrap these entry points in an OBS scene lock. Block graph edits,
variant changes and Cut/Fade scene switches while any job is busy for the first
increment. Shutdown and health-driven output stop remain allowed. Call
`reset/destroy` before releasing affected graph resources.

Actions address one **layer instance**, not the reusable source. Other layers
of the same source retain their transforms/visibility. Temporary transforms are
not persistent layout edits. On completion, the baseline transform is restored
exactly; incoming actions leave the item visible and outgoing actions hide it.
Cancellation/failure restores the prior visibility and transform. The owner records graph generation, variant, scene, layer and source identity
at acceptance. It applies completed visibility only to that captured target,
then acknowledges the exact operation through `overlay_animation_ack(id)`.
Cancelled/failed receipts are acknowledged without changing desired visibility.
Acknowledgment is an internal owner operation, not an MCP/UI command. Graph
mutation remains blocked until this commit, closing the native-completion versus
owner-poll race. Stale generations never edit a replacement document. The owner
must not rebuild the graph merely to advance an animation.

## Kinds and limits

| Kind | Behavior | Easing |
|---|---|---|
| `fade_in`, `fade_out` | Official per-item `fade_transition` through OBS show/hide API | `linear` only; other values explicitly rejected |
| `slide_in`, `slide_out` | Horizontal motion from/to `baseline.x - distance` (negative enters/exits from the right) | `linear`, quadratic `ease_in`, `ease_out`, `ease_in_out` |
| `scale_in`, `scale_out` | Scale from/to `scale_from` relative to baseline, preserving item anchor | Same four curves |

Duration is 100–10000 ms; distance is finite −1920–1920; `scale_from` is finite
0.1–2.0. IDs must fit 63 UTF-8 bytes. Scaling modifies bounds when bounded,
otherwise the item's scale. A hidden item receiving an outgoing action completes
without flashing it on screen. A visible item receiving an incoming action
replays the requested entrance. A second live operation on the same item is
rejected; operations on distinct items can run concurrently.

Native errors include `INVALID_ANIMATION`, `ANIMATION_EASING_UNSUPPORTED`,
`ANIMATION_BUSY`, `ANIMATION_LIMIT`, `ANIMATION_UNAVAILABLE`,
`ANIMATION_NOT_FOUND`, `ANIMATION_LAYER_UNAVAILABLE`,
`ANIMATION_TRANSITION_UNAVAILABLE`, `ANIMATION_ITEM_BUSY`,
`ANIMATION_INVALID_TRANSFORM`, `ANIMATION_TRANSITION_FAILED`,
`ANIMATION_INTERRUPTED` and `ANIMATION_STALLED`. A fade that remains active beyond
its duration plus 3 seconds fails and restores its baseline; elapsed time alone
never reports a fade complete.

## Thread, clock and lifecycle evidence

Checked against pinned OBS 33.0.1:

- Global tick callbacks run before source ticks and under
  `draw_callbacks_mutex`; add/remove acquire that same mutex. Removing our tick
  outside the animator mutex synchronizes callback completion. [Video tick](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-video.c), [registration](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.c).
- The first native tick anchors the action to `obs_get_video_frame_time()`.
  Position/scale interpolate from that native clock; MCP/UI polling does not
  schedule or finalize frames. OBS's Fade uses its own transition clock and
  reports progress through `obs_transition_get_time` and completion through
  `obs_transition_is_active` becoming false. [Transition implementation](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-source-transition.c).
- Scene-item APIs own visibility transitions and active-child bookkeeping.
  `obs_scene_atomic_update` protects changes with the scene's video/audio locks.
  Existing show/hide transition bindings and durations are retained/restored.
  `obs_transition_set(fade,NULL)` clears child references/flags and signals stop;
  `obs_transition_force_stop` by itself only invokes the stop handler in this
  version and is insufficient for cancellation cleanup. [Scene implementation](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-scene.c).
- Native work uses a local job snapshot outside the animator mutex; accepted
  cancellation is reconciled before publishing completion. Source creation can
  acquire graphics locks, so it also occurs outside the animator mutex. Terminal
  publication clears ownership pointers before the local references are released.

The standalone Objective-C syntax check uses the same pinned headers and ARC,
with `-Wall -Wextra -Werror` (unused external-header parameters exempted). Its
log is `var/evidence/h11-animation-syntax.log`. This is **not** runtime evidence:
the integrating agent must verify encoded fade/slide/scale frames, cancellation,
simultaneous distinct-layer actions, repeated-command rejection, no-client
expiration, graph reset/destruction, and output continuity under the shared
physical-test lock. No device, signed bundle or physical test was used to build
this module.
