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
    bool extended,stretch;char definition_kind[32],definition_subkind[32],asset_id[80];char *overlay_json;
    uint32_t window,capture_fps; pid_t owner; uint64_t active_since,instance_id; bool desired_active,warming;
    CGDirectDisplayID display;char display_uuid[64],application[256];
};
static bool visual_is_sck(const visual_source *s) {
    return !strcmp(s->kind,"window") || !strcmp(s->kind,"display") || !strcmp(s->kind,"application");
}
struct visual_scene { obs_scene_t *scene; char id[64]; uint32_t visible_mask; char layer_ids[32][64];obs_sceneitem_t *items[32];size_t layer_count; };
static bool visual_equal(visual_source *s,NSDictionary *d) {
    if (!s->source) return false;
    bool extended=[d[@"overlay"] isKindOfClass:[NSDictionary class]];
    if(s->extended!=extended)return false;
    if(extended && s->stretch!=([d[@"overlay"][@"kind"] isEqual:@"shape"] && [d[@"overlay"][@"shape"] isEqual:@"rectangle"]))return false;
    if(extended && (strcmp(s->definition_kind,[d[@"overlay"][@"kind"] UTF8String]) || strcmp(s->asset_id,[(d[@"overlay"][@"asset_id"]?:@"") UTF8String])))return false;
    NSString *kind=d[@"spec"][@"kind"];
    if (strcmp(s->kind,kind.UTF8String)) return false;
    if(extended && !strcmp(s->definition_kind,"widget") && strcmp(s->definition_subkind,[(d[@"overlay"][@"widget"][@"kind"]?:@"") UTF8String]))return false;
    if ([kind isEqualToString:@"camera"]) return !strcmp(s->device,[d[@"spec"][@"device_id"] UTF8String]);
    if ([kind isEqualToString:@"window"]) return s->window==[d[@"window_id"] unsignedIntValue] && s->owner==[d[@"owner_pid"] intValue];
    if ([kind isEqualToString:@"display"]) return !strcmp(s->display_uuid,[d[@"spec"][@"display_uuid"] UTF8String]);
    if ([kind isEqualToString:@"application"]) return !strcmp(s->display_uuid,[d[@"spec"][@"display_uuid"] UTF8String]) && !strcmp(s->application,[d[@"spec"][@"bundle_id"] UTF8String]);
    return true;
}
static void visual_destroy(visual_source *s) {
    if (!s) return;
    if (s->watch) { obs_source_filter_remove(s->source,s->watch);obs_source_release(s->watch); }
    if (s->source) obs_source_release(s->source);
    free(s->overlay_json);free(s);
}
#include "scene-items.h"
#include "capture-admission.h"
static void release_capture_source(motive_engine *e,visual_source *s) {
    // Detach every layer, then join OBS source destruction before replacement.
    // AVFoundation stops synchronously. Official SCK starts asynchronous stop;
    // the API exposes no completion barrier, so SCStream overlap is unverified.
    for(size_t i=0;i<e->scene_count;i++)
        motive_detach_scene_source(e->scenes[i]->items,e->scenes[i]->layer_count,s->source);
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
    if (visual_is_sck(s)) {
        if (!CGPreflightScreenCaptureAccess()) {snprintf(e->error,sizeof(e->error),"SCREEN_PERMISSION_DENIED");goto fail;}
        if([kind isEqualToString:@"window"]) {
            s->window=[d[@"window_id"] unsignedIntValue]; s->owner=[d[@"owner_pid"] intValue];
            NSDictionary *w=find_window(s->window);
            if (!w || [w[@"pid"] intValue]!=s->owner) {snprintf(e->error,sizeof(e->error),"SOURCE_UNAVAILABLE");goto fail;}
            obs_data_set_int(settings,"type",1);obs_data_set_int(settings,"window",s->window);
            obs_data_set_int(settings,"motive_window_owner_pid",s->owner);
        } else {
            NSString *uuid=d[@"spec"][@"display_uuid"];
            s->display=capture_display(uuid);
            if(!s->display) {snprintf(e->error,sizeof(e->error),"DISPLAY_UNAVAILABLE");goto fail;}
            snprintf(s->display_uuid,sizeof(s->display_uuid),"%s",uuid.UTF8String);
            obs_data_set_string(settings,"display_uuid",s->display_uuid);
            bool application=[kind isEqualToString:@"application"];
            obs_data_set_int(settings,"type",application?2:0);
            if(application) {
                NSString *bundle=d[@"spec"][@"bundle_id"];
                s->owner=capture_application(bundle);
                if(!s->owner) {snprintf(e->error,sizeof(e->error),"APPLICATION_UNAVAILABLE_OR_AMBIGUOUS");goto fail;}
                snprintf(s->application,sizeof(s->application),"%s",bundle.UTF8String);
                obs_data_set_string(settings,"application",s->application);
                obs_data_set_int(settings,"motive_application_owner_pid",s->owner);
            }
        }
        // SCK captures the OBS FPS on stream creation; unchanged updates are a
        // no-op upstream. Retire every old layer/reference before replacing the
        // OBS source, preserving the stable graph ID. SCK shutdown itself is asynchronous.
        for(size_t i=0;i<e->visual_count;i++) {
            visual_source *old=e->visuals[i];
            if(old->source && visual_is_sck(old) && !strcmp(old->id,s->id))
                release_capture_source(e,old);
        }
        obs_wait_for_destroy_queue();s->capture_fps=e->fps;
        type="screen_capture";
        obs_data_set_bool(settings,"show_cursor",false);obs_data_set_bool(settings,"show_hidden_windows",true);
    } else if ([kind isEqualToString:@"camera"]) {
        snprintf(s->device,sizeof(s->device),"%s",[d[@"spec"][@"device_id"] UTF8String]);
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo]!=AVAuthorizationStatusAuthorized) {snprintf(e->error,sizeof(e->error),"CAMERA_PERMISSION_DENIED");goto fail;}
        if (!find_camera(s->device)) {snprintf(e->error,sizeof(e->error),"CAMERA_UNAVAILABLE");goto fail;}
        for(size_t i=0;i<e->visual_count;i++) {
            visual_source *old=e->visuals[i];
            if(old->source && !strcmp(old->kind,"camera") && !strcmp(old->device,s->device))
                release_capture_source(e,old);
        }
        // Also finish destruction from a preceding remove-source command.
        obs_wait_for_destroy_queue();
        type="macos-avcapture";obs_data_set_string(settings,"device",s->device);
        obs_data_set_bool(settings,"use_preset",true);obs_data_set_string(settings,"preset",AVCaptureSessionPreset1280x720.UTF8String);
        obs_data_set_bool(settings,"enable_audio",false);
    } else if ([d[@"overlay"] isKindOfClass:[NSDictionary class]]) {
        s->extended=true;type="motive_visual";
        s->stretch=[d[@"overlay"][@"kind"] isEqual:@"shape"] && [d[@"overlay"][@"shape"] isEqual:@"rectangle"];
        snprintf(s->definition_kind,sizeof(s->definition_kind),"%s",[d[@"overlay"][@"kind"] UTF8String]);
        snprintf(s->definition_subkind,sizeof(s->definition_subkind),"%s",[(d[@"overlay"][@"widget"][@"kind"]?:@"") UTF8String]);
        snprintf(s->asset_id,sizeof(s->asset_id),"%s",[(d[@"overlay"][@"asset_id"]?:@"") UTF8String]);
        NSData *json=[NSJSONSerialization dataWithJSONObject:d[@"overlay"] options:NSJSONWritingSortedKeys error:nil];
        s->overlay_json=strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
        obs_data_set_string(settings,"definition",s->overlay_json);
        obs_data_set_string(settings,"asset_path",[(d[@"asset_path"]?:@"") UTF8String]);
        obs_data_set_int(settings,"asset_width",[d[@"asset_width"] intValue]);obs_data_set_int(settings,"asset_height",[d[@"asset_height"] intValue]);
    } else if ([kind isEqualToString:@"overlay"]) {
        obs_data_set_bool(settings,"overlay",true);obs_data_set_int(settings,"color",[d[@"spec"][@"color"] unsignedIntValue]);
    } else if (![kind isEqualToString:@"pattern"]) {snprintf(e->error,sizeof(e->error),"INVALID_SOURCE_KIND");goto fail;}
    s->source=obs_source_create_private(type,s->id,settings);obs_data_release(settings);
    // OBS retains the settings object even when the plugin's create callback
    // fails. Reject that shell immediately; it cannot ever publish a frame.
    if (!s->source || obs_obj_invalid(s->source)) {
        const char *error=visual_is_sck(s) ? motive_capture_creation_error(s->source):"SOURCE_CREATE_FAILED";
        snprintf(e->error,sizeof(e->error),"%s",error);visual_destroy(s);return NULL;
    }
    s->instance_id=++e->visual_instances;
    // Revalidate the exact application/display after the plugin's independent
    // inventory/start. A restarted application never inherits this selection.
    if(visual_is_sck(s) && strcmp(s->kind,"window") &&
        (capture_display(@(s->display_uuid))!=s->display ||
         (!strcmp(s->kind,"application") && capture_application(@(s->application))!=s->owner))) {
        snprintf(e->error,sizeof(e->error),"CAPTURE_TARGET_CHANGED");visual_destroy(s);return NULL;
    }
    obs_source_set_muted(s->source,true);
    obs_source_set_audio_mixers(s->source,0);
    obs_source_set_monitoring_type(s->source,OBS_MONITORING_TYPE_NONE);
    if ([kind isEqualToString:@"camera"]) {
        s->watch=obs_source_create_private("motive_frame_watch","Camera frame monitor",NULL);
        if (!s->watch) {snprintf(e->error,sizeof(e->error),"FRAME_MONITOR_FAILED");visual_destroy(s);return NULL;}
        obs_source_filter_add(s->source,s->watch);
    }
    return s;
fail:
    obs_data_release(settings);free(s);return NULL;
}
static NSDictionary *capture_diagnostics(visual_source *s) {
    if(!s->source || !visual_is_sck(s))return nil;
    calldata_t params;calldata_init(&params);
    NSDictionary *result=nil;
    if(proc_handler_call(obs_source_get_proc_handler(s->source),"motive_capture_diagnostics",&params)) {
        const char *text=calldata_string(&params,"json");
        if(text)result=[NSJSONSerialization JSONObjectWithData:[@(text) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    }
    calldata_free(&params);
    return result;
}
static const char *visual_health(visual_source *s) {
    if(!s->source) return !strcmp(s->kind,"camera") ? "CAMERA_UNAVAILABLE":"SOURCE_UNAVAILABLE";
    if(s->extended)return overlay_source_health(s->source);
    if (visual_is_sck(s)) {
        if (!CGPreflightScreenCaptureAccess()) return "SCREEN_PERMISSION_DENIED";
        if(!strcmp(s->kind,"window")) {
            NSDictionary *w=find_window(s->window);
            if (!w || [w[@"pid"] intValue]!=s->owner) return "SOURCE_UNAVAILABLE";
        } else {
            if(capture_display(@(s->display_uuid))!=s->display)return "DISPLAY_UNAVAILABLE";
            if(!strcmp(s->kind,"application") && capture_application(@(s->application))!=s->owner)
                return "APPLICATION_UNAVAILABLE_OR_AMBIGUOUS";
        }
        NSDictionary *capture=capture_diagnostics(s);
        if([capture[@"user_stopped"] boolValue])return "CAPTURE_USER_STOPPED";
        if([capture[@"phase"] isEqual:@"failed"])return "CAPTURE_SESSION_FAILED";
        if([capture[@"sample_status"] isEqual:@"stopped"])return "CAPTURE_STOPPED";
        // Idle or absent buffers alone cannot distinguish static content from
        // an occluded producer. Expose their age/status without inventing loss.
    } else if (!strcmp(s->kind,"camera")) {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo]!=AVAuthorizationStatusAuthorized) return "CAMERA_PERMISSION_DENIED";
        if (!find_camera(s->device)) return "CAMERA_UNAVAILABLE";
        frame_watch *w=obs_obj_get_data(s->watch);uint64_t seen=atomic_load(&w->seen_ns),now=os_gettime_ns();
        if (now-s->active_since>4000000000ULL && (!seen || now-seen>3000000000ULL)) return "CAMERA_STALLED";
        if (!seen) return "CAPTURE_NOT_READY";
    }
    return obs_source_get_width(s->source) && obs_source_get_height(s->source) ? "":"CAPTURE_NOT_READY";
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
    if(overlay_animation_busy(e->animations)){snprintf(e->error,sizeof(e->error),"ANIMATION_BUSY");return false;}
    if (scene_busy(e)) {snprintf(e->error,sizeof(e->error),"TRANSITION_BUSY");return false;}
    if (!scene_controls_init(e)) return false;
    NSDictionary *graph=[NSJSONSerialization JSONObjectWithData:[@(json) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    NSArray *sources=graph[@"sources"], *scenes=graph[@"scenes"];
    if (!graph || sources.count>16 || scenes.count<1 || scenes.count>8) {snprintf(e->error,sizeof(e->error),"INVALID_GRAPH");return false;}
    visual_source *next[16]={0};visual_scene *built[8]={0};bool reused[16]={0},enabled[16]={0};size_t source_count=0,scene_count=0;
    for (NSDictionary *d in sources) {
        visual_source *s=NULL;
        for (size_t i=0;i<e->visual_count;i++) if (!strcmp(e->visuals[i]->id,[d[@"id"] UTF8String]) && visual_equal(e->visuals[i],d)
            && (!visual_is_sck(e->visuals[i]) || e->visuals[i]->capture_fps==e->fps)
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
            size_t index=s->layer_count++;s->items[index]=item;snprintf(s->layer_ids[index],sizeof(s->layer_ids[index]),"%s",[layer[@"id"] UTF8String]);
            NSDictionary *t=layer[@"layouts"][orientation];struct vec2 pos,bounds,scale;
            if ([t[@"visible"] boolValue])
                for(size_t i=0;i<source_count;i++) if(next[i]==source) {
                    s->visible_mask|=1u<<i;
                    if ([d[@"id"] isEqual:graph[@"active_scene"]]) enabled[i]=true;
                }
            float factor=motive_design_scale(e);
            vec2_set(&pos,[t[@"x"] floatValue]*factor,[t[@"y"] floatValue]*factor);vec2_set(&bounds,[t[@"width"] floatValue]*factor,[t[@"height"] floatValue]*factor);vec2_set(&scale,1,1);
            obs_sceneitem_defer_update_begin(item);
            obs_sceneitem_set_scale(item,&scale);obs_sceneitem_set_alignment(item,OBS_ALIGN_TOP|OBS_ALIGN_LEFT);
            obs_sceneitem_set_bounds_type(item,source->stretch?OBS_BOUNDS_STRETCH:OBS_BOUNDS_SCALE_INNER);obs_sceneitem_set_bounds_alignment(item,0);
            obs_sceneitem_set_bounds(item,&bounds);obs_sceneitem_set_pos(item,&pos);
            obs_sceneitem_set_visible(item,[t[@"visible"] boolValue]);obs_sceneitem_defer_update_end(item);
        }
    }
    if (!active) {snprintf(e->error,sizeof(e->error),"SCENE_UNAVAILABLE");goto fail;}
    // Only scalar settings after staging succeeded. Overlay updates preserve its clock.
    for (size_t i=0;i<source_count;i++) if (!next[i]->extended && !strcmp(next[i]->kind,"overlay")) {
        obs_data_t *settings=obs_data_create();obs_data_set_bool(settings,"overlay",true);
        obs_data_set_int(settings,"color",[sources[i][@"spec"][@"color"] unsignedIntValue]);obs_source_update(next[i]->source,settings);obs_data_release(settings);
    }
    for(size_t i=0;i<source_count;i++) if(next[i]->extended) {
        NSData *json=[NSJSONSerialization dataWithJSONObject:sources[i][@"overlay"] options:NSJSONWritingSortedKeys error:nil];
        const char *definition=[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String;
        if(strcmp(next[i]->overlay_json,definition)){obs_data_t *settings=obs_data_create();obs_data_set_string(settings,"definition",definition);obs_source_update(next[i]->source,settings);obs_data_release(settings);free(next[i]->overlay_json);next[i]->overlay_json=strdup(definition);}
    }
    for(size_t i=0;i<source_count;i++) {
        if(enabled[i] && !next[i]->desired_active) next[i]->active_since=os_gettime_ns();
        if(!enabled[i]) next[i]->active_since=0;
        next[i]->desired_active=enabled[i];
    }
    overlay_animator_reset(e->animations);
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
        NSDictionary *capture=capture_diagnostics(s);
        uint64_t captured=capture ? [capture[@"last_surface_ns"] unsignedLongLongValue]:0;
        if(captured)seen=captured;
        uint64_t now=os_gettime_ns();
        NSString *notice=@"";
        if(capture && captured && now>captured && now-captured>3000000000ULL)notice=@"NO_RECENT_CAPTURE_BUFFER";
        if([capture[@"sample_status"] isEqual:@"suspended"])notice=@"CAPTURE_SUSPENDED";
        else if([capture[@"sample_status"] isEqual:@"stopped"])notice=@"CAPTURE_STOPPED";
        else if([capture[@"sample_status"] isEqual:@"blank"])notice=@"CAPTURE_BLANK";
        [states addObject:@{@"id":@(s->id),@"active":@(active),@"issue":@(issue),
            @"warming":@(s->warming),@"instance_id":@(s->instance_id),@"kind":@(s->kind),
            @"width":@(s->source ? obs_source_get_width(s->source):0),@"height":@(s->source ? obs_source_get_height(s->source):0),
            @"capture_fps_requested":s->capture_fps ? @(s->capture_fps):[NSNull null],
            @"capture_fps_measured":capture ? capture[@"surface_fps_lifetime"]:[NSNull null],
            @"frames":capture ? capture[@"surface_samples"]:@(w ? atomic_load(&w->frames):0),
            @"capture_diagnostics":capture ?: [NSNull null],@"freshness_notice":notice,
            @"content_freshness":@"not_inferred_from_timestamps",
            @"frame_age_ms":seen && now>=seen ? @((now-seen)/1000000):[NSNull null]}];
    }
    NSData *data=[NSJSONSerialization dataWithJSONObject:states options:0 error:nil];
    return strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
}
uint32_t motive_capture_width(motive_engine *e) {
    for(size_t i=0;i<e->visual_count;i++) if(e->visuals[i]->source && !strcmp(e->visuals[i]->id,"main") && strcmp(e->visuals[i]->kind,"pattern"))return obs_source_get_width(e->visuals[i]->source);
    return 0;
}
