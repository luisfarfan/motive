/* Main-thread scene control; libobs owns transition rendering/timing. These
 * callbacks publish only counters, never mutate the graph or call output APIs. */
static void transition_stopped(void *data,calldata_t *cd) {
    (void)cd;transition_events *events=data;atomic_fetch_add(&events->stops,1);
}
static bool scene_busy(motive_engine *e) {return e->scene_phase==SCENE_PREPARING || e->scene_phase==SCENE_RUNNING;}
static visual_scene *scene_find(motive_engine *e,const char *id) {
    for(size_t i=0;i<e->scene_count;i++) if(!strcmp(e->scenes[i]->id,id)) return e->scenes[i];
    return NULL;
}
static void scene_activity(motive_engine *e,uint32_t program,uint32_t warm) {
    uint64_t now=os_gettime_ns();
    for(size_t i=0;i<e->visual_count;i++) {
        visual_source *s=e->visuals[i];s->desired_active=(program&(1u<<i))!=0;s->warming=(warm&(1u<<i))!=0;
        if(!s->desired_active && !s->warming) s->active_since=0;
        else if(!s->active_since) s->active_since=now;
    }
}
static void scene_drop_preparation(motive_engine *e) {
    if(e->scene_target_held) {
        obs_source_dec_active(obs_scene_get_source(e->scene_target_native->scene));e->scene_target_held=false;
    }
}
static bool scene_controls_init(motive_engine *e) {
    const char *ids[]={"cut_transition","fade_transition"};
    for(unsigned i=0;i<2;i++) if(!e->transitions[i]) {
        e->transitions[i]=obs_source_create_private(ids[i],i ? "Motive Fade":"Motive Cut",NULL);
        if(!e->transitions[i]) {snprintf(e->error,sizeof(e->error),"TRANSITION_UNAVAILABLE");return false;}
        signal_handler_connect(obs_source_get_signal_handler(e->transitions[i]),"transition_stop",transition_stopped,&e->transition_events[i]);
    }
    return true;
}
static void scene_controls_release(motive_engine *e) {
    scene_drop_preparation(e);free(e->scene_blocked);e->scene_blocked=NULL;
    for(unsigned i=0;i<2;i++) if(e->transitions[i]) {
        signal_handler_disconnect(obs_source_get_signal_handler(e->transitions[i]),"transition_stop",transition_stopped,&e->transition_events[i]);
        obs_transition_clear(e->transitions[i]);obs_source_release(e->transitions[i]);e->transitions[i]=NULL;
    }
}
static void scene_transition_kind(motive_engine *e,unsigned kind) {
    if(e->transition_index!=kind) {
        obs_source_t *before=e->transitions[e->transition_index],*after=e->transitions[kind];
        obs_transition_swap_begin(after,before);obs_set_output_source(0,after);obs_transition_swap_end(after,before);
        e->transition_index=kind;
    }
    obs_transition_set_size(e->transitions[kind],e->width,e->height);
}
static void scene_controls_sync(motive_engine *e,visual_scene *active) {
    obs_source_t *scene=obs_scene_get_source(active->scene),*transition=e->transitions[e->transition_index];
    // Hold the new graph's active tree across the reference exchange, including
    // capture resources shared with the old scene objects being retired.
    obs_source_inc_active(scene);obs_transition_set(transition,scene);
    obs_transition_set_size(transition,e->width,e->height);obs_set_output_source(0,transition);obs_source_dec_active(scene);
    snprintf(e->scene_current,sizeof(e->scene_current),"%s",active->id);
    e->scene_phase=SCENE_IDLE;e->scene_from[0]=0;e->scene_target[0]=0;e->scene_error[0]=0;e->scene_progress=0;
    e->scene_from_native=NULL;e->scene_target_native=NULL;free(e->scene_blocked);e->scene_blocked=NULL;
}
static NSArray *scene_issues(motive_engine *e,visual_scene *scene,bool preparing) {
    NSMutableArray *issues=[NSMutableArray array];
    if(!scene) return issues;
    for(size_t i=0;i<e->visual_count;i++) if(scene->visible_mask&(1u<<i)) {
        visual_source *s=e->visuals[i];const char *issue=visual_health(s);
        if(!*issue && visual_is_sck(s)) {
            NSString *status=capture_diagnostics(s)[@"sample_status"];
            if([status isEqual:@"suspended"])issue="CAPTURE_SUSPENDED";
            else if([status isEqual:@"blank"])issue="CAPTURE_BLANK";
        }
        if(!*issue && preparing && !strcmp(s->kind,"camera")) {
            frame_watch *w=obs_obj_get_data(s->watch);uint64_t seen=atomic_load(&w->seen_ns),now=os_gettime_ns();
            if(now-seen>500000000ULL || (!s->desired_active && seen<e->scene_prepare_ns)) issue="CAPTURE_NOT_READY";
        }
        if(*issue) [issues addObject:@{@"source_id":@(s->id),@"code":@(issue)}];
    }
    return issues;
}
static void scene_abort(motive_engine *e,enum scene_phase phase,const char *error,NSArray *issues) {
    // Preserve the exact failure observation, even if inventory/permissions
    // recover before the next status request. Only the owner reads/writes it.
    free(e->scene_blocked);e->scene_blocked=NULL;
    if(issues.count) {
        NSData *json=[NSJSONSerialization dataWithJSONObject:issues options:0 error:nil];
        e->scene_blocked=strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
    }
    if(e->scene_phase==SCENE_RUNNING) {
        e->scene_progress=obs_transition_get_time(e->transitions[e->transition_index]);
        obs_source_t *from=obs_scene_get_source(e->scene_from_native->scene);
        obs_source_inc_active(from);obs_transition_set(e->transitions[e->transition_index],from);obs_source_dec_active(from);
    }
    scene_drop_preparation(e);e->scene_phase=phase;
    snprintf(e->scene_error,sizeof(e->scene_error),"%s",error ?: "");
    visual_scene *current=scene_find(e,e->scene_current);scene_activity(e,current ? current->visible_mask:0,0);
}
void motive_poll_scene(motive_engine *e) {
    if(e->scene_phase==SCENE_PREPARING) {
        NSArray *issues=scene_issues(e,e->scene_target_native,true);
        bool hard=false;
        for(NSDictionary *issue in issues) if(![issue[@"code"] isEqual:@"CAPTURE_NOT_READY"]) hard=true;
        if(hard || os_gettime_ns()-e->scene_prepare_ns>8000000000ULL) {
            scene_abort(e,SCENE_FAILED,hard ? "SCENE_TARGET_UNAVAILABLE":"SCENE_PREPARATION_TIMEOUT",issues);return;
        }
        if(issues.count) {e->scene_ready_frame=0;return;}
        if(e->scene_needs_warmup) {
            uint64_t frame=obs_get_video_frame_time();
            if(!e->scene_ready_frame) {e->scene_ready_frame=frame;return;}
            if(frame-e->scene_ready_frame<2*1000000000ULL/30) return;
        }
        scene_transition_kind(e,e->scene_kind);
        e->transition_stop_baseline=atomic_load(&e->transition_events[e->transition_index].stops);
        e->scene_phase=SCENE_RUNNING;
        if(!obs_transition_start(e->transitions[e->transition_index],OBS_TRANSITION_MODE_AUTO,e->scene_duration_ms,obs_scene_get_source(e->scene_target_native->scene))) {
            scene_abort(e,SCENE_FAILED,"TRANSITION_START_FAILED",nil);return;
        }
        // Native transition references now own both active trees. Release our
        // preparation reference only after B has acquired that ownership.
        scene_drop_preparation(e);
        scene_activity(e,e->scene_from_native->visible_mask|e->scene_target_native->visible_mask,0);
    }
    if(e->scene_phase==SCENE_RUNNING) {
        e->scene_progress=obs_transition_get_time(e->transitions[e->transition_index]);
        // OBS dispatches stop signals outside its transition-state lock. After
        // cancellation/restart, a late notification alone cannot identify which
        // operation finished. The locked public getter must also show B moved
        // into A (the native completion step); balance its strong reference.
        obs_source_t *settled=NULL;
        if(atomic_load(&e->transition_events[e->transition_index].stops)!=e->transition_stop_baseline)
            settled=obs_transition_get_source(e->transitions[e->transition_index],OBS_TRANSITION_SOURCE_A);
        bool completed=settled==obs_scene_get_source(e->scene_target_native->scene);
        obs_source_release(settled);
        if(completed) {
            snprintf(e->scene_current,sizeof(e->scene_current),"%s",e->scene_target);
            e->scene_phase=SCENE_COMPLETED;e->scene_progress=1;
            scene_activity(e,e->scene_target_native->visible_mask,0);return;
        }
        // A target-only failure rolls back to the still-healthy previous scene.
        // Fade still requires a healthy origin. Cut must be allowed to leave a
        // failed origin: its completion signal can arrive on the next render,
        // and rolling back here would return to the known-broken scene. Target
        // health remains mandatory; the core bounds its safe-fallback attempt.
        NSArray *target_issues=scene_issues(e,e->scene_target_native,false);
        NSArray *from_issues=scene_issues(e,e->scene_from_native,false);
        if(target_issues.count) scene_abort(e,SCENE_FAILED,"SCENE_TARGET_FAILED",target_issues);
        else if(from_issues.count && e->scene_kind!=0) scene_abort(e,SCENE_FAILED,"SCENE_CURRENT_FAILED",from_issues);
    }
}
bool motive_switch_scene(motive_engine *e,const char *id,unsigned kind,unsigned duration) {
    e->error[0]=0;
    if(kind>1 || (kind==0 && duration!=0) || (kind==1 && (duration<100 || duration>5000))) {snprintf(e->error,sizeof(e->error),"INVALID_TRANSITION");return false;}
    if(scene_busy(e)) {
        if(!strcmp(e->scene_target,id)) return true; // Same pending target is idempotent.
        snprintf(e->error,sizeof(e->error),"TRANSITION_BUSY");return false;
    }
    visual_scene *target=scene_find(e,id),*from=scene_find(e,e->scene_current);
    if(!target || !from) {snprintf(e->error,sizeof(e->error),"SCENE_UNAVAILABLE");return false;}
    if(target==from) return true;
    bool editing=motive_output_state(e)==0 && kind==0;
    if(!editing && !target->visible_mask) {snprintf(e->error,sizeof(e->error),"EMPTY_SCENE");return false;}
    free(e->scene_blocked);e->scene_blocked=NULL;
    e->scene_operation++;e->scene_kind=kind;e->scene_duration_ms=duration;e->scene_progress=0;e->scene_error[0]=0;
    snprintf(e->scene_from,sizeof(e->scene_from),"%s",from->id);snprintf(e->scene_target,sizeof(e->scene_target),"%s",target->id);
    e->scene_from_native=from;e->scene_target_native=target;
    if(editing) {
        // Preserve idle editor selection of empty/cold scenes. Live switching
        // always goes through preparation and the official Cut/Fade start API.
        scene_transition_kind(e,kind);
        obs_source_t *scene=obs_scene_get_source(target->scene);obs_source_inc_active(scene);
        obs_transition_set(e->transitions[kind],scene);obs_source_dec_active(scene);
        snprintf(e->scene_current,sizeof(e->scene_current),"%s",target->id);e->scene_phase=SCENE_COMPLETED;e->scene_progress=1;
        scene_activity(e,target->visible_mask,0);return true;
    }
    e->scene_prepare_ns=os_gettime_ns();e->scene_ready_frame=0;e->scene_needs_warmup=false;
    for(size_t i=0;i<e->visual_count;i++) if((target->visible_mask&(1u<<i)) && !e->visuals[i]->desired_active &&
        (!strcmp(e->visuals[i]->kind,"camera") || visual_is_sck(e->visuals[i]))) e->scene_needs_warmup=true;
    obs_source_inc_active(obs_scene_get_source(target->scene));e->scene_target_held=true;e->scene_phase=SCENE_PREPARING;
    scene_activity(e,from->visible_mask,target->visible_mask);motive_poll_scene(e);
    if(e->scene_phase==SCENE_FAILED) {snprintf(e->error,sizeof(e->error),"%s",e->scene_error);return false;}
    return true;
}
bool motive_cancel_scene(motive_engine *e,uint64_t operation) {
    e->error[0]=0;
    if(operation!=e->scene_operation) {snprintf(e->error,sizeof(e->error),"TRANSITION_OPERATION_MISMATCH");return false;}
    if(scene_busy(e)) scene_abort(e,SCENE_CANCELLED,NULL,nil);
    return true;
}
char *motive_scene_state(motive_engine *e) {
    const char *phases[]={"idle","preparing","running","completed","cancelled","failed"};
    float progress=e->scene_phase==SCENE_RUNNING ? obs_transition_get_time(e->transitions[e->transition_index]):e->scene_progress;
    NSArray *blocked=scene_busy(e) ? scene_issues(e,e->scene_target_native,e->scene_phase==SCENE_PREPARING):@[];
    if(e->scene_phase==SCENE_FAILED && e->scene_blocked)
        blocked=[NSJSONSerialization JSONObjectWithData:[@(e->scene_blocked) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    NSDictionary *state=@{@"operation_id":@(e->scene_operation),@"phase":@(phases[e->scene_phase]),@"current_scene":@(e->scene_current),
        @"from_scene":e->scene_from[0] ? @(e->scene_from):[NSNull null],@"target_scene":e->scene_target[0] ? @(e->scene_target):[NSNull null],
        @"kind":e->scene_kind ? @"fade":@"cut",@"duration_ms":@(e->scene_duration_ms),@"progress":@(fmaxf(0,fminf(1,progress))),
        @"error":e->scene_error[0] ? @(e->scene_error):[NSNull null],@"blocked_sources":blocked,
        @"source_instances_created":@(e->visual_instances),@"scenes_built":@(e->scenes_built)};
    NSData *data=[NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
    return strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
}
