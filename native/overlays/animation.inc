/* Bounded per-item actions. OBS remains the renderer/compositor and owns time.
 * Owner entry points must not run inside OBS scene/draw callbacks. The tick
 * never holds the animator mutex while calling OBS or allocating Foundation
 * objects. remove_tick_callback synchronizes teardown before item restoration. */
enum overlay_animation_kind {
    OVERLAY_FADE_IN, OVERLAY_FADE_OUT, OVERLAY_SLIDE_IN,
    OVERLAY_SLIDE_OUT, OVERLAY_SCALE_IN, OVERLAY_SCALE_OUT
};
enum overlay_animation_easing {
    OVERLAY_LINEAR, OVERLAY_EASE_IN, OVERLAY_EASE_OUT, OVERLAY_EASE_IN_OUT
};
enum overlay_animation_phase {
    OVERLAY_ANIMATION_EMPTY, OVERLAY_ANIMATION_RUNNING,
    OVERLAY_ANIMATION_CANCEL_PENDING, OVERLAY_ANIMATION_COMPLETED,
    OVERLAY_ANIMATION_CANCELLED, OVERLAY_ANIMATION_FAILED
};
typedef struct {
    uint64_t operation_id, start_ns, elapsed_ns;
    char scene_id[64], layer_id[64], error[64];
    enum overlay_animation_kind kind;
    enum overlay_animation_easing easing;
    enum overlay_animation_phase phase;
    uint32_t duration_ms;
    float distance, render_distance, scale_from, progress;
    bool initialized, baseline_visible, native_transition_active, pending_ack;
    struct obs_transform_info baseline;
    obs_sceneitem_t *item;
    obs_scene_t *scene;
    obs_source_t *fade, *old_show, *old_hide;
    uint32_t old_show_ms, old_hide_ms;
    obs_source_t *trigger_source;
    char trigger_source_id[64];
    uint64_t trigger_generation;
    bool widget_triggered;
} overlay_animation_job;
typedef struct overlay_animator {
    pthread_mutex_t lock;
    overlay_animation_job jobs[8];
    uint64_t sequence;
    bool stopping, registered;
    char error[64];
} overlay_animator;

static const char *overlay_kind_name(enum overlay_animation_kind kind) {
    static const char *names[]={"fade_in","fade_out","slide_in","slide_out","scale_in","scale_out"};
    return names[kind];
}
static const char *overlay_easing_name(enum overlay_animation_easing easing) {
    static const char *names[]={"linear","ease_in","ease_out","ease_in_out"};
    return names[easing];
}
static const char *overlay_phase_name(enum overlay_animation_phase phase) {
    static const char *names[]={"empty","running","cancel_pending","completed","cancelled","failed"};
    return names[phase];
}
static bool overlay_job_busy(const overlay_animation_job *j) {
    return j->phase==OVERLAY_ANIMATION_RUNNING || j->phase==OVERLAY_ANIMATION_CANCEL_PENDING;
}
/* Terminal results cannot be evicted or crossed by graph edits before the
 * owner commits their model effect and acknowledges this exact operation. */
static bool overlay_job_blocks(const overlay_animation_job *j) {
    return overlay_job_busy(j) || j->pending_ack;
}
static bool overlay_job_in(const overlay_animation_job *j) {
    return j->kind==OVERLAY_FADE_IN || j->kind==OVERLAY_SLIDE_IN || j->kind==OVERLAY_SCALE_IN;
}
static bool overlay_job_fade(const overlay_animation_job *j) {
    return j->kind==OVERLAY_FADE_IN || j->kind==OVERLAY_FADE_OUT;
}
static float overlay_ease(enum overlay_animation_easing easing,float t) {
    switch(easing) {
        case OVERLAY_EASE_IN:return t*t;
        case OVERLAY_EASE_OUT:return 1-(1-t)*(1-t);
        case OVERLAY_EASE_IN_OUT:return t<.5f ? 2*t*t:1-2*(1-t)*(1-t);
        default:return t;
    }
}
static void overlay_job_error(overlay_animation_job *j,const char *code) {
    snprintf(j->error,sizeof(j->error),"%s",code);j->phase=OVERLAY_ANIMATION_FAILED;
}
static void overlay_job_release(overlay_animation_job *j) {
    obs_source_release(j->fade);obs_source_release(j->old_show);obs_source_release(j->old_hide);
    obs_source_release(j->trigger_source);j->trigger_source=NULL;
    if(j->item)obs_sceneitem_release(j->item);
    if(j->scene)obs_scene_release(j->scene);
    j->fade=NULL;j->old_show=NULL;j->old_hide=NULL;j->item=NULL;j->scene=NULL;
}

/* All item mutations run under its scene's official video+audio lock. Normal
 * progress/cancellation runs only in the media tick. reset/destroy restore
 * synchronously after unregistering that tick, before the caller replaces a graph. */
static void overlay_job_restore(void *param,obs_scene_t *scene) {
    overlay_animation_job *j=param;
    if(!j->initialized)return;
    // set() clears transition children/flags and emits transition_stop, balancing
    // the active child registered by OBS's scene-item transition implementation.
    // force_stop() alone only emits a signal in OBS 33.0.1; it is insufficient.
    if(j->fade)obs_transition_set(j->fade,NULL);
    j->native_transition_active=false;
    if(obs_sceneitem_get_scene(j->item)!=scene) {
        overlay_job_error(j,"ANIMATION_LAYER_UNAVAILABLE");return;
    }
    obs_sceneitem_set_transition(j->item,true,NULL);
    obs_sceneitem_set_transition(j->item,false,NULL);
    bool visible=j->phase==OVERLAY_ANIMATION_COMPLETED ? overlay_job_in(j):j->baseline_visible;
    if(!visible)obs_sceneitem_set_visible(j->item,false);
    obs_sceneitem_set_info2(j->item,&j->baseline);
    if(visible)obs_sceneitem_set_visible(j->item,true);
    obs_sceneitem_set_transition(j->item,true,j->old_show);
    obs_sceneitem_set_transition(j->item,false,j->old_hide);
    obs_sceneitem_set_transition_duration(j->item,true,j->old_show_ms);
    obs_sceneitem_set_transition_duration(j->item,false,j->old_hide_ms);
}
static void overlay_job_finish(overlay_animation_job *j,enum overlay_animation_phase phase) {
    j->phase=phase;j->pending_ack=true;
    if(phase==OVERLAY_ANIMATION_COMPLETED)j->progress=1;
    if(phase==OVERLAY_ANIMATION_CANCELLED)j->error[0]=0;
    if(j->scene)obs_scene_atomic_update(j->scene,overlay_job_restore,j);
    // Cancellation restores animation geometry; an already-triggered widget
    // continues its documented lifecycle. End attribution at this exact op.
    if(j->widget_triggered)overlay_animated_trigger_end(j->trigger_source,j->operation_id);
}
static bool overlay_job_trigger(overlay_animation_job *j) {
    if(!j->trigger_source || j->widget_triggered)return true;
    if(!overlay_animated_trigger_begin(j->trigger_source,j->operation_id,j->trigger_generation)) {
        overlay_job_error(j,"WIDGET_CHANGED_BEFORE_TRIGGER");return false;
    }
    j->widget_triggered=true;return true;
}
static bool overlay_job_initialize(overlay_animation_job *j,uint64_t now) {
    obs_source_t *show=obs_sceneitem_get_transition(j->item,true);
    obs_source_t *hide=obs_sceneitem_get_transition(j->item,false);
    if((show && obs_transition_is_active(show)) || (hide && obs_transition_is_active(hide))) {
        overlay_job_error(j,"ANIMATION_ITEM_BUSY");return false;
    }
    obs_sceneitem_get_info2(j->item,&j->baseline);
    if(!isfinite(j->baseline.pos.x) || !isfinite(j->baseline.pos.y) ||
       !isfinite(j->baseline.bounds.x) || !isfinite(j->baseline.bounds.y) ||
       !isfinite(j->baseline.scale.x) || !isfinite(j->baseline.scale.y)) {
        overlay_job_error(j,"ANIMATION_INVALID_TRANSFORM");return false;
    }
    j->baseline_visible=obs_sceneitem_visible(j->item);
    j->old_show=obs_source_get_ref(show);j->old_hide=obs_source_get_ref(hide);
    j->old_show_ms=obs_sceneitem_get_transition_duration(j->item,true);
    j->old_hide_ms=obs_sceneitem_get_transition_duration(j->item,false);
    j->initialized=true;j->start_ns=now;
    if(!overlay_job_in(j) && !j->baseline_visible) {
        j->phase=OVERLAY_ANIMATION_COMPLETED;j->progress=1;return true;
    }
    // Existing show/hide transitions must not accidentally run alongside this
    // action. Strong references above allow exact restoration on every exit.
    obs_sceneitem_set_transition(j->item,true,NULL);
    obs_sceneitem_set_transition(j->item,false,NULL);
    if(overlay_job_fade(j)) {
        bool visible=overlay_job_in(j);
        obs_sceneitem_set_visible(j->item,!visible);
        obs_sceneitem_set_transition(j->item,visible,j->fade);
        obs_sceneitem_set_transition_duration(j->item,visible,j->duration_ms);
        obs_sceneitem_set_visible(j->item,visible);
        j->native_transition_active=obs_transition_is_active(j->fade);
        if(!j->native_transition_active) {
            overlay_job_error(j,"ANIMATION_TRANSITION_FAILED");return false;
        }
    }
    return true;
}
typedef struct { overlay_animation_job *job;uint64_t now; } overlay_tick_context;
static void overlay_job_advance(void *param,obs_scene_t *scene) {
    overlay_tick_context *ctx=param;overlay_animation_job *j=ctx->job;
    if(obs_sceneitem_get_scene(j->item)!=scene) {
        overlay_job_error(j,"ANIMATION_LAYER_UNAVAILABLE");return;
    }
    if(j->phase==OVERLAY_ANIMATION_CANCEL_PENDING) {
        j->phase=OVERLAY_ANIMATION_CANCELLED;return;
    }
    if(!j->initialized && !overlay_job_initialize(j,ctx->now))return;
    if(!overlay_job_busy(j))return;
    j->elapsed_ns=ctx->now>j->start_ns ? ctx->now-j->start_ns:0;
    float t=fminf(1,(float)((double)j->elapsed_ns/(j->duration_ms*1000000.0)));
    if(overlay_job_fade(j)) {
        if(!overlay_job_trigger(j))return;
        // Source lifetime alone is not completion: both OBS transition clocks
        // must actually stop. Queries never advance or finish the action.
        j->progress=fminf(1,fmaxf(0,obs_transition_get_time(j->fade)));
        j->native_transition_active=obs_transition_is_active(j->fade);
        if(!j->native_transition_active) {
            if(j->progress>=1)j->phase=OVERLAY_ANIMATION_COMPLETED;
            else overlay_job_error(j,"ANIMATION_INTERRUPTED");
        } else if(j->elapsed_ns>(uint64_t)(j->duration_ms+3000)*1000000ULL) {
            overlay_job_error(j,"ANIMATION_STALLED");
        }
        return;
    }
    j->progress=t;float eased=overlay_ease(j->easing,t);
    bool incoming=overlay_job_in(j);
    if(j->kind==OVERLAY_SLIDE_IN || j->kind==OVERLAY_SLIDE_OUT) {
        struct vec2 pos=j->baseline.pos;
        pos.x-=j->render_distance*(incoming ? 1-eased:eased);
        obs_sceneitem_set_pos(j->item,&pos);
    } else {
        float factor=incoming ? j->scale_from+(1-j->scale_from)*eased:1+(j->scale_from-1)*eased;
        if(j->baseline.bounds_type!=OBS_BOUNDS_NONE) {
            struct vec2 bounds=j->baseline.bounds;
            bounds.x*=factor;bounds.y*=factor;obs_sceneitem_set_bounds(j->item,&bounds);
        } else {
            struct vec2 scale=j->baseline.scale;
            scale.x*=factor;scale.y*=factor;obs_sceneitem_set_scale(j->item,&scale);
        }
    }
    if(!overlay_job_trigger(j))return;
    obs_sceneitem_set_visible(j->item,true);
    if(t>=1)j->phase=OVERLAY_ANIMATION_COMPLETED;
}
static void overlay_animator_tick(void *param,float seconds) {
    (void)seconds;overlay_animator *a=param;uint64_t now=obs_get_video_frame_time();
    for(size_t i=0;i<8;i++) {
        pthread_mutex_lock(&a->lock);
        overlay_animation_job local=a->jobs[i];
        pthread_mutex_unlock(&a->lock);
        if(!overlay_job_busy(&local))continue;
        overlay_tick_context ctx={.job=&local,.now=now};
        obs_scene_atomic_update(local.scene,overlay_job_advance,&ctx);
        if(!overlay_job_busy(&local))overlay_job_finish(&local,local.phase);
        pthread_mutex_lock(&a->lock);
        // A request arriving during native work must not be overwritten. If
        // completion won the media tick but cancel was already accepted, undo
        // that completion before publishing the actual cancelled state.
        if(a->jobs[i].phase==OVERLAY_ANIMATION_CANCEL_PENDING && local.phase!=OVERLAY_ANIMATION_CANCELLED) {
            if(overlay_job_busy(&local))local.phase=OVERLAY_ANIMATION_CANCEL_PENDING;
            else {
                pthread_mutex_unlock(&a->lock);
                overlay_job_finish(&local,OVERLAY_ANIMATION_CANCELLED);
                pthread_mutex_lock(&a->lock);
            }
        }
        a->jobs[i]=local;
        if(!overlay_job_busy(&local)) {
            a->jobs[i].item=NULL;a->jobs[i].scene=NULL;a->jobs[i].fade=NULL;
            a->jobs[i].old_show=NULL;a->jobs[i].old_hide=NULL;
            a->jobs[i].trigger_source=NULL;
        }
        pthread_mutex_unlock(&a->lock);
        if(!overlay_job_busy(&local))overlay_job_release(&local);
    }
}
static overlay_animator *overlay_animator_create(void) {
    overlay_animator *a=calloc(1,sizeof(*a));
    if(!a)return NULL;
    if(pthread_mutex_init(&a->lock,NULL)) {free(a);return NULL;}
    obs_add_tick_callback(overlay_animator_tick,a);a->registered=true;return a;
}
static void overlay_animator_clear(overlay_animator *a,bool rearm) {
    pthread_mutex_lock(&a->lock);a->stopping=true;pthread_mutex_unlock(&a->lock);
    // Never acquire the OBS draw-callback mutex while holding our mutex.
    if(a->registered)obs_remove_tick_callback(overlay_animator_tick,a);
    a->registered=false;
    for(size_t i=0;i<8;i++) {
        overlay_animation_job local=a->jobs[i];
        if(overlay_job_busy(&local))overlay_job_finish(&local,OVERLAY_ANIMATION_CANCELLED);
        overlay_job_release(&local);
        pthread_mutex_lock(&a->lock);a->jobs[i]=local;pthread_mutex_unlock(&a->lock);
    }
    if(rearm) {
        obs_add_tick_callback(overlay_animator_tick,a);a->registered=true;
        pthread_mutex_lock(&a->lock);a->stopping=false;pthread_mutex_unlock(&a->lock);
    }
}
static void overlay_animator_reset(overlay_animator *a) {if(a)overlay_animator_clear(a,true);}
static void overlay_animator_destroy(overlay_animator *a) {
    if(!a)return;
    overlay_animator_clear(a,false);pthread_mutex_destroy(&a->lock);free(a);
}
static bool overlay_animation_busy(overlay_animator *a) {
    if(!a)return false;
    pthread_mutex_lock(&a->lock);bool busy=false;
    for(size_t i=0;i<8;i++)busy|=overlay_job_blocks(&a->jobs[i]);
    pthread_mutex_unlock(&a->lock);return busy;
}
static int overlay_animation_slot(overlay_animator *a,obs_sceneitem_t *item,const char *scene,const char *layer) {
    int slot=-1;uint64_t oldest=UINT64_MAX;
    for(size_t i=0;i<8;i++) {
        overlay_animation_job *j=&a->jobs[i];
        if(overlay_job_blocks(j)) {
            if(j->item==item || (!strcmp(j->scene_id,scene) && !strcmp(j->layer_id,layer))) {
                snprintf(a->error,sizeof(a->error),"ANIMATION_BUSY");return -1;
            }
        } else if(j->operation_id<oldest) {oldest=j->operation_id;slot=(int)i;}
    }
    if(slot<0)snprintf(a->error,sizeof(a->error),"ANIMATION_LIMIT");
    return slot;
}
static bool overlay_animation_start(overlay_animator *a,obs_sceneitem_t *item,const char *scene_id,
    const char *layer_id,const char *kind,const char *easing,uint32_t duration_ms,float distance,
    float scale_from,float design_scale,uint64_t *id,obs_source_t *trigger_source,const char *trigger_source_id) {
    if(!a)return false;
    int k=-1,e=-1;
    if(kind)for(int i=0;i<6;i++)if(!strcmp(kind,overlay_kind_name(i)))k=i;
    if(easing)for(int i=0;i<4;i++)if(!strcmp(easing,overlay_easing_name(i)))e=i;
    bool valid=item && scene_id && *scene_id && strlen(scene_id)<64 && layer_id && *layer_id &&
        strlen(layer_id)<64 && k>=0 && e>=0 && duration_ms>=100 && duration_ms<=10000 &&
        isfinite(distance) && fabsf(distance)<=1920 && isfinite(scale_from) &&
        scale_from>=.1f && scale_from<=2 && isfinite(design_scale) && design_scale>=1 && design_scale<=2 && id;
    pthread_mutex_lock(&a->lock);
    if(!valid || (k<=OVERLAY_FADE_OUT && e!=OVERLAY_LINEAR)) {
        snprintf(a->error,sizeof(a->error),"%s",valid ? "ANIMATION_EASING_UNSUPPORTED":"INVALID_ANIMATION");
        pthread_mutex_unlock(&a->lock);return false;
    }
    if(a->stopping || a->sequence==UINT64_MAX) {
        snprintf(a->error,sizeof(a->error),"ANIMATION_UNAVAILABLE");pthread_mutex_unlock(&a->lock);return false;
    }
    int slot=overlay_animation_slot(a,item,scene_id,layer_id);
    pthread_mutex_unlock(&a->lock);
    if(slot<0)return false;
    overlay_animation_job next={.kind=k,.easing=e,.phase=OVERLAY_ANIMATION_RUNNING,
        .duration_ms=duration_ms,.distance=distance,.render_distance=distance*design_scale,.scale_from=scale_from};
    if(trigger_source) {
        if(!overlay_job_in(&next) || !trigger_source_id || !*trigger_source_id || strlen(trigger_source_id)>=64 ||
            obs_sceneitem_get_source(item)!=trigger_source || !overlay_animated_trigger_prepare(trigger_source,&next.trigger_generation)) {
            pthread_mutex_lock(&a->lock);snprintf(a->error,sizeof(a->error),"INVALID_ANIMATED_WIDGET");pthread_mutex_unlock(&a->lock);return false;
        }
        next.trigger_source=obs_source_get_ref(trigger_source);
        if(!next.trigger_source) {
            pthread_mutex_lock(&a->lock);snprintf(a->error,sizeof(a->error),"ANIMATION_SOURCE_UNAVAILABLE");pthread_mutex_unlock(&a->lock);return false;
        }
        snprintf(next.trigger_source_id,sizeof(next.trigger_source_id),"%s",trigger_source_id);
    }
    next.scene=obs_scene_get_ref(obs_sceneitem_get_scene(item));
    if(next.scene) {next.item=item;obs_sceneitem_addref(item);}
    if(next.scene && overlay_job_fade(&next))
        next.fade=obs_source_create_private("fade_transition","Motive item fade",NULL);
    // Creating the official Fade can acquire the graphics lock: never do it
    // under our mutex, since the video tick also needs that mutex.
    pthread_mutex_lock(&a->lock);
    if(!next.scene || (overlay_job_fade(&next) && !next.fade)) {
        snprintf(a->error,sizeof(a->error),"%s",!next.scene ? "ANIMATION_LAYER_UNAVAILABLE":"ANIMATION_TRANSITION_UNAVAILABLE");
        slot=-1;
    } else if(a->stopping || a->sequence==UINT64_MAX) {
        snprintf(a->error,sizeof(a->error),"ANIMATION_UNAVAILABLE");slot=-1;
    } else slot=overlay_animation_slot(a,item,scene_id,layer_id);
    if(slot>=0) {
        next.operation_id=++a->sequence;
        snprintf(next.scene_id,sizeof(next.scene_id),"%s",scene_id);
        snprintf(next.layer_id,sizeof(next.layer_id),"%s",layer_id);
        a->jobs[slot]=next;a->error[0]=0;*id=next.operation_id;
    }
    pthread_mutex_unlock(&a->lock);
    if(slot<0)overlay_job_release(&next);
    return slot>=0;
}
static bool overlay_animation_cancel(overlay_animator *a,uint64_t id) {
    if(!a || !id)return false;
    pthread_mutex_lock(&a->lock);bool found=false;
    if(!a->stopping)for(size_t i=0;i<8;i++)if(a->jobs[i].operation_id==id) {
        found=true;
        if(a->jobs[i].phase==OVERLAY_ANIMATION_RUNNING)a->jobs[i].phase=OVERLAY_ANIMATION_CANCEL_PENDING;
        break;
    }
    snprintf(a->error,sizeof(a->error),"%s",found ? "":"ANIMATION_NOT_FOUND");
    pthread_mutex_unlock(&a->lock);return found;
}
static int overlay_job_order(const void *left,const void *right) {
    uint64_t a=((const overlay_animation_job *)left)->operation_id,b=((const overlay_animation_job *)right)->operation_id;
    return (a>b)-(a<b);
}
static bool overlay_animation_ack(overlay_animator *a,uint64_t id) {
    if(!a || !id)return false;
    pthread_mutex_lock(&a->lock);bool found=false;
    if(!a->stopping)for(size_t i=0;i<8;i++)if(a->jobs[i].operation_id==id) {
        if(!overlay_job_busy(&a->jobs[i])) {a->jobs[i].pending_ack=false;found=true;}
        break;
    }
    snprintf(a->error,sizeof(a->error),"%s",found ? "":"ANIMATION_ACK_UNAVAILABLE");
    pthread_mutex_unlock(&a->lock);return found;
}
static NSDictionary *overlay_animation_state(overlay_animator *a) {
    if(!a)return @{@"available":@NO,@"busy":@NO,@"jobs":@[],@"error":@"ANIMATION_UNAVAILABLE"};
    overlay_animation_job snapshots[8];char error[64];uint64_t sequence;bool stopping;
    pthread_mutex_lock(&a->lock);
    memcpy(snapshots,a->jobs,sizeof(snapshots));memcpy(error,a->error,sizeof(error));sequence=a->sequence;stopping=a->stopping;
    pthread_mutex_unlock(&a->lock);
    qsort(snapshots,8,sizeof(snapshots[0]),overlay_job_order);
    NSMutableArray *jobs=[NSMutableArray array];bool busy=false,running=false,pending_ack=false;
    for(size_t i=0;i<8;i++) {
        overlay_animation_job *j=&snapshots[i];if(!j->operation_id)continue;
        busy|=overlay_job_blocks(j);running|=overlay_job_busy(j);pending_ack|=j->pending_ack;
        [jobs addObject:@{@"operation_id":@(j->operation_id),@"scene_id":@(j->scene_id),@"layer_id":@(j->layer_id),
            @"kind":@(overlay_kind_name(j->kind)),@"easing":@(overlay_easing_name(j->easing)),
            @"phase":@(overlay_phase_name(j->phase)),@"progress":@(j->progress),@"duration_ms":@(j->duration_ms),
            @"distance":@(j->distance),@"scale_from":@(j->scale_from),@"started":@(j->initialized),
            @"start_ns":j->initialized ? @(j->start_ns):[NSNull null],@"elapsed_ms":@(j->elapsed_ns/1000000),
            @"target_visible":@(overlay_job_in(j)),@"baseline_visible":j->initialized ? @(j->baseline_visible):[NSNull null],
            @"native_transition_active":@(j->native_transition_active),@"pending_ack":@(j->pending_ack),
            @"trigger_source_id":j->trigger_source_id[0]?@(j->trigger_source_id):[NSNull null],@"widget_triggered":@(j->widget_triggered),
            @"error":j->error[0] ? @(j->error):[NSNull null]}];
    }
    return @{@"available":stopping?@NO:@YES,@"busy":@(busy),@"running":@(running),@"pending_ack":@(pending_ack),@"clock":@"obs_video_time",@"capacity":@8,
        @"last_operation_id":@(sequence),@"jobs":jobs,@"error":error[0] ? @(error):[NSNull null]};
}
