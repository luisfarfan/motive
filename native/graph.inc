/* Visual resources retain one strong source reference each. Scenes own their
 * items. Reconciliation stages new resources/scenes before publishing output 0;
 * unchanged capture sources keep identity and clock across graph edits. */
typedef struct { atomic_uint_fast64_t seen_ns, frames; } frame_watch;
static void *watch_create(obs_data_t *settings,obs_source_t *source) {
    (void)settings;(void)source;return calloc(1,sizeof(frame_watch));
}
static struct obs_source_frame *watch_frame(void *data,struct obs_source_frame *frame) {
    frame_watch *w=data;
    if (frame) { atomic_store(&w->seen_ns,os_gettime_ns()); atomic_fetch_add(&w->frames,1); }
    return frame;
}
static struct obs_source_info watch_info={.id="motive_frame_watch",.type=OBS_SOURCE_TYPE_FILTER,
    .output_flags=OBS_SOURCE_ASYNC_VIDEO,.get_name=pattern_name,.create=watch_create,
    .destroy=free,.filter_video=watch_frame};
struct visual_source {
    obs_source_t *source,*watch;
    char id[64],kind[16],device[512];
    uint32_t window; pid_t owner; uint64_t active_since,instance_id; bool desired_active,warming;
};
struct visual_scene { obs_scene_t *scene; char id[64]; uint32_t visible_mask; };
static bool visual_equal(visual_source *s,NSDictionary *d) {
    if (!s->source) return false;
    NSString *kind=d[@"spec"][@"kind"];
    if (strcmp(s->kind,kind.UTF8String)) return false;
    if ([kind isEqualToString:@"camera"]) return !strcmp(s->device,[d[@"spec"][@"device_id"] UTF8String]);
    if ([kind isEqualToString:@"window"]) return s->window==[d[@"window_id"] unsignedIntValue] && s->owner==[d[@"owner_pid"] intValue];
    return true;
}
static void visual_destroy(visual_source *s) {
    if (!s) return;
    if (s->watch) { obs_source_filter_remove(s->source,s->watch);obs_source_release(s->watch); }
    if (s->source) obs_source_release(s->source);
    free(s);
}
static bool detach_camera_item(obs_scene_t *scene,obs_sceneitem_t *item,void *source) {
    (void)scene;
    if(obs_sceneitem_get_source(item)==source) obs_sceneitem_remove(item);
    return true;
}
static void release_camera_session(motive_engine *e,visual_source *s) {
    // AVFoundation cannot reliably start a second session for the same device
    // while the old session is being destroyed. Detach every layer, then wait
    // for OBS's destroy queue (the official module synchronously stops AV capture).
    for(size_t i=0;i<e->scene_count;i++)
        obs_scene_enum_items(e->scenes[i]->scene,detach_camera_item,s->source);
    if(s->watch) {obs_source_filter_remove(s->source,s->watch);obs_source_release(s->watch);s->watch=NULL;}
    obs_source_release(s->source);s->source=NULL;
    obs_wait_for_destroy_queue();
}
static visual_source *visual_create(motive_engine *e,NSDictionary *d) {
    visual_source *s=calloc(1,sizeof(*s));
    NSString *kind=d[@"spec"][@"kind"];
    snprintf(s->id,sizeof(s->id),"%s",[d[@"id"] UTF8String]);
    snprintf(s->kind,sizeof(s->kind),"%s",kind.UTF8String);
    obs_data_t *settings=obs_data_create(); const char *type="motive_pattern";
    if ([kind isEqualToString:@"window"]) {
        s->window=[d[@"window_id"] unsignedIntValue]; s->owner=[d[@"owner_pid"] intValue];
        if (!CGPreflightScreenCaptureAccess()) {snprintf(e->error,sizeof(e->error),"SCREEN_PERMISSION_DENIED");goto fail;}
        NSDictionary *w=find_window(s->window);
        if (!w || [w[@"pid"] intValue]!=s->owner) {snprintf(e->error,sizeof(e->error),"SOURCE_UNAVAILABLE");goto fail;}
        type="screen_capture";obs_data_set_int(settings,"type",1);obs_data_set_int(settings,"window",s->window);
        obs_data_set_bool(settings,"show_cursor",false);obs_data_set_bool(settings,"show_hidden_windows",true);
    } else if ([kind isEqualToString:@"camera"]) {
        snprintf(s->device,sizeof(s->device),"%s",[d[@"spec"][@"device_id"] UTF8String]);
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo]!=AVAuthorizationStatusAuthorized) {snprintf(e->error,sizeof(e->error),"CAMERA_PERMISSION_DENIED");goto fail;}
        if (!find_camera(s->device)) {snprintf(e->error,sizeof(e->error),"CAMERA_UNAVAILABLE");goto fail;}
        for(size_t i=0;i<e->visual_count;i++) {
            visual_source *old=e->visuals[i];
            if(old->source && !strcmp(old->kind,"camera") && !strcmp(old->device,s->device))
                release_camera_session(e,old);
        }
        // Also finish destruction from a preceding remove-source command.
        obs_wait_for_destroy_queue();
        type="macos-avcapture";obs_data_set_string(settings,"device",s->device);
        obs_data_set_bool(settings,"use_preset",true);obs_data_set_string(settings,"preset",AVCaptureSessionPreset1280x720.UTF8String);
        obs_data_set_bool(settings,"enable_audio",false);
    } else if ([kind isEqualToString:@"overlay"]) {
        obs_data_set_bool(settings,"overlay",true);obs_data_set_int(settings,"color",[d[@"spec"][@"color"] unsignedIntValue]);
    } else if (![kind isEqualToString:@"pattern"]) {snprintf(e->error,sizeof(e->error),"INVALID_SOURCE_KIND");goto fail;}
    s->source=obs_source_create_private(type,s->id,settings);obs_data_release(settings);
    if (!s->source) {snprintf(e->error,sizeof(e->error),"SOURCE_CREATE_FAILED");visual_destroy(s);return NULL;}
    s->instance_id=++e->visual_instances;
    obs_source_set_muted(s->source,true);
    if ([kind isEqualToString:@"camera"]) {
        s->watch=obs_source_create_private("motive_frame_watch","Camera frame monitor",NULL);
        if (!s->watch) {snprintf(e->error,sizeof(e->error),"FRAME_MONITOR_FAILED");visual_destroy(s);return NULL;}
        obs_source_filter_add(s->source,s->watch);
    }
    return s;
fail:
    obs_data_release(settings);free(s);return NULL;
}
static const char *visual_health(visual_source *s) {
    if(!s->source) return "CAMERA_UNAVAILABLE";
    if (!strcmp(s->kind,"window")) {
        if (!CGPreflightScreenCaptureAccess()) return "SCREEN_PERMISSION_DENIED";
        NSDictionary *w=find_window(s->window);
        if (!w || [w[@"pid"] intValue]!=s->owner) return "SOURCE_UNAVAILABLE";
    } else if (!strcmp(s->kind,"camera")) {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo]!=AVAuthorizationStatusAuthorized) return "CAMERA_PERMISSION_DENIED";
        if (!find_camera(s->device)) return "CAMERA_UNAVAILABLE";
        frame_watch *w=obs_obj_get_data(s->watch);uint64_t seen=atomic_load(&w->seen_ns),now=os_gettime_ns();
        if (now-s->active_since>4000000000ULL && (!seen || now-seen>3000000000ULL)) return "CAMERA_STALLED";
        if (!seen) return "CAPTURE_NOT_READY";
    }
    return obs_source_get_width(s->source) ? "":"CAPTURE_NOT_READY";
}
#include "scene-switch.inc"
static void graph_release(motive_engine *e) {
    scene_controls_release(e);
    for (size_t i=0;i<e->scene_count;i++) {obs_scene_release(e->scenes[i]->scene);free(e->scenes[i]);}
    for (size_t i=0;i<e->visual_count;i++) visual_destroy(e->visuals[i]);
    e->scene_count=0;e->visual_count=0;
}
bool motive_sync_graph(motive_engine *e,const char *json,const char *reconnect_id) {
    e->error[0]=0;
    if (scene_busy(e)) {snprintf(e->error,sizeof(e->error),"TRANSITION_BUSY");return false;}
    if (!scene_controls_init(e)) return false;
    NSDictionary *graph=[NSJSONSerialization JSONObjectWithData:[@(json) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    NSArray *sources=graph[@"sources"], *scenes=graph[@"scenes"];
    if (!graph || sources.count>16 || scenes.count<1 || scenes.count>8) {snprintf(e->error,sizeof(e->error),"INVALID_GRAPH");return false;}
    visual_source *next[16]={0};visual_scene *built[8]={0};bool reused[16]={0},enabled[16]={0};size_t source_count=0,scene_count=0;
    for (NSDictionary *d in sources) {
        visual_source *s=NULL;
        for (size_t i=0;i<e->visual_count;i++) if (!strcmp(e->visuals[i]->id,[d[@"id"] UTF8String]) && visual_equal(e->visuals[i],d)
            && strcmp(reconnect_id,"*") && strcmp(reconnect_id,e->visuals[i]->id)) {s=e->visuals[i];reused[i]=true;break;}
        if (!s) s=visual_create(e,d);
        if (!s) goto fail;
        next[source_count++]=s;
    }
    visual_scene *active=NULL;
    for (NSDictionary *d in scenes) {
        visual_scene *s=calloc(1,sizeof(*s));snprintf(s->id,sizeof(s->id),"%s",[d[@"id"] UTF8String]);
        s->scene=obs_scene_create_private(s->id);built[scene_count++]=s;
        if (!s->scene) {snprintf(e->error,sizeof(e->error),"SCENE_CREATE_FAILED");goto fail;}
        e->scenes_built++;
        if ([d[@"id"] isEqual:graph[@"active_scene"]]) active=s;
        NSString *orientation=e->width>e->height ? @"horizontal":@"vertical";
        NSArray *layers=[d[@"layers"] sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a,NSDictionary *b){
            NSComparisonResult order=[a[@"layouts"][orientation][@"order"] compare:b[@"layouts"][orientation][@"order"]];
            return order==NSOrderedSame ? [a[@"id"] compare:b[@"id"]]:order;
        }];
        for (NSDictionary *layer in layers) {
            visual_source *source=NULL;
            for (size_t i=0;i<source_count;i++) if (!strcmp(next[i]->id,[layer[@"source_id"] UTF8String])) {source=next[i];break;}
            if (!source) {snprintf(e->error,sizeof(e->error),"INVALID_LAYER_REFERENCE");goto fail;}
            obs_sceneitem_t *item=obs_scene_add(s->scene,source->source);
            if (!item) {snprintf(e->error,sizeof(e->error),"LAYER_CREATE_FAILED");goto fail;}
            NSDictionary *t=layer[@"layouts"][orientation];struct vec2 pos,bounds,scale;
            if ([t[@"visible"] boolValue])
                for(size_t i=0;i<source_count;i++) if(next[i]==source) {
                    s->visible_mask|=1u<<i;
                    if ([d[@"id"] isEqual:graph[@"active_scene"]]) enabled[i]=true;
                }
            vec2_set(&pos,[t[@"x"] floatValue],[t[@"y"] floatValue]);vec2_set(&bounds,[t[@"width"] floatValue],[t[@"height"] floatValue]);vec2_set(&scale,1,1);
            obs_sceneitem_defer_update_begin(item);
            obs_sceneitem_set_scale(item,&scale);obs_sceneitem_set_alignment(item,OBS_ALIGN_TOP|OBS_ALIGN_LEFT);
            obs_sceneitem_set_bounds_type(item,OBS_BOUNDS_SCALE_INNER);obs_sceneitem_set_bounds_alignment(item,0);
            obs_sceneitem_set_bounds(item,&bounds);obs_sceneitem_set_pos(item,&pos);
            obs_sceneitem_set_visible(item,[t[@"visible"] boolValue]);obs_sceneitem_defer_update_end(item);
        }
    }
    if (!active) {snprintf(e->error,sizeof(e->error),"SCENE_UNAVAILABLE");goto fail;}
    // Only scalar settings after staging succeeded. Overlay updates preserve its clock.
    for (size_t i=0;i<source_count;i++) if (!strcmp(next[i]->kind,"overlay")) {
        obs_data_t *settings=obs_data_create();obs_data_set_bool(settings,"overlay",true);
        obs_data_set_int(settings,"color",[sources[i][@"spec"][@"color"] unsignedIntValue]);obs_source_update(next[i]->source,settings);obs_data_release(settings);
    }
    for(size_t i=0;i<source_count;i++) {
        if(enabled[i] && !next[i]->desired_active) next[i]->active_since=os_gettime_ns();
        if(!enabled[i]) next[i]->active_since=0;
        next[i]->desired_active=enabled[i];
    }
    scene_controls_sync(e,active);
    for (size_t i=0;i<e->scene_count;i++) {obs_scene_release(e->scenes[i]->scene);free(e->scenes[i]);}
    for (size_t i=0;i<e->visual_count;i++) if (!reused[i]) visual_destroy(e->visuals[i]);
    memcpy(e->visuals,next,sizeof(next));memcpy(e->scenes,built,sizeof(built));e->visual_count=source_count;e->scene_count=scene_count;
    return true;
fail:
    for (size_t i=0;i<scene_count;i++) {if (built[i]->scene) obs_scene_release(built[i]->scene);free(built[i]);}
    for (size_t i=0;i<source_count;i++) {bool old=false;for(size_t j=0;j<e->visual_count;j++) if(next[i]==e->visuals[j]) old=true;if(!old) visual_destroy(next[i]);}
    return false;
}
char *motive_graph_health(motive_engine *e) {
    NSMutableArray *states=[NSMutableArray array];
    for(size_t i=0;i<e->visual_count;i++) {
        visual_source *s=e->visuals[i];bool active=s->desired_active;
        // Health follows the committed graph, including cold sources whose OBS
        // activation is still asynchronous. Never call them ready by omission.
        const char *issue=active ? visual_health(s):"";
        frame_watch *w=s->watch ? obs_obj_get_data(s->watch):NULL;uint64_t seen=w ? atomic_load(&w->seen_ns):0;
        uint64_t now=os_gettime_ns();
        [states addObject:@{@"id":@(s->id),@"active":@(active),@"issue":@(issue),
            @"warming":@(s->warming),@"instance_id":@(s->instance_id),@"width":@(s->source ? obs_source_get_width(s->source):0),@"frames":@(w ? atomic_load(&w->frames):0),
            @"frame_age_ms":seen ? @((now-seen)/1000000):[NSNull null]}];
    }
    NSData *data=[NSJSONSerialization dataWithJSONObject:states options:0 error:nil];
    return strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
}
uint32_t motive_capture_width(motive_engine *e) {
    for(size_t i=0;i<e->visual_count;i++) if(e->visuals[i]->source && !strcmp(e->visuals[i]->id,"main") && strcmp(e->visuals[i]->kind,"pattern"))return obs_source_get_width(e->visuals[i]->source);
    return 0;
}
