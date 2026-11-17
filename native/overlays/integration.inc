/* Owner-thread facade. All rendering and timing remain libobs-owned. */
static char *overlay_json_result(id value) {
    NSData *data=[NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
    return data ? strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String):strdup("{}");
}
static visual_source *overlay_find(motive_engine *e,const char *id) {
    for(size_t i=0;i<e->visual_count;i++)if(!strcmp(e->visuals[i]->id,id)&&e->visuals[i]->extended)return e->visuals[i];
    snprintf(e->error,sizeof(e->error),"OVERLAY_UNAVAILABLE");return NULL;
}
char *motive_overlay_capabilities(motive_engine *e) {
    (void)e;NSMutableDictionary *sources=[NSMutableDictionary dictionary];
    for(NSString *base in @[@"text_ft2_source",@"image_source",@"ffmpeg_source",@"color_source",@"fade_transition"]) {
        const char *latest=obs_get_latest_input_type_id(base.UTF8String);
        if([base isEqualToString:@"fade_transition"])latest="fade_transition";
        sources[base]=@{@"available":latest && obs_get_source_output_flags(latest)!=0?@YES:@NO,@"registered_id":latest?@(latest):[NSNull null]};
    }
    return overlay_json_result(@{@"sources":sources,@"browser":@NO,@"renderer":@"libobs",@"monitoring":@"off"});
}
void motive_poll_overlays(motive_engine *e) {
    if(scene_busy(e))return;
    for(size_t i=0;i<e->scene_count;i++) {visual_scene *scene=e->scenes[i];uint32_t mask=0;
        for(size_t j=0;j<scene->layer_count;j++)if(obs_sceneitem_visible(scene->items[j])) {
            obs_source_t *source=obs_sceneitem_get_source(scene->items[j]);
            for(size_t k=0;k<e->visual_count;k++)if(e->visuals[k]->source==source)mask|=1u<<k;
        }
        scene->visible_mask=mask;
        if(!strcmp(scene->id,e->scene_current))for(size_t k=0;k<e->visual_count;k++){
            visual_source *source=e->visuals[k];bool active=(mask&(1u<<k))!=0;
            if(active&&!source->desired_active)source->active_since=os_gettime_ns();
            if(!active)source->active_since=0;
            source->desired_active=active;
        }
    }
}
char *motive_overlay_state(motive_engine *e) {
    NSMutableArray *sources=[NSMutableArray array];
    for(size_t i=0;i<e->visual_count;i++)if(e->visuals[i]->extended){visual_source *s=e->visuals[i];
        NSMutableDictionary *state=[overlay_source_state(s->source) mutableCopy];
        state[@"id"]=@(s->id);state[@"instance_id"]=@(s->instance_id);[sources addObject:state];
    }
    return overlay_json_result(@{@"sources":sources,@"animations":overlay_animation_state(e->animations)});
}
bool motive_update_overlay(motive_engine *e,const char *id,const char *definition) {
    e->error[0]=0;visual_source *s=overlay_find(e,id);if(!s)return false;
    obs_data_t *settings=obs_data_create();obs_data_set_string(settings,"definition",definition);
    obs_source_update(s->source,settings);obs_data_release(settings);
    free(s->overlay_json);s->overlay_json=strdup(definition);return true;
}
bool motive_overlay_event(motive_engine *e,const char *id,const char *event) {
    e->error[0]=0;visual_source *s=overlay_find(e,id);if(!s)return false;
    if(!overlay_source_event(s->source,event)){snprintf(e->error,sizeof(e->error),"INVALID_OVERLAY_ACTION");return false;}return true;
}
bool motive_overlay_animation_busy(motive_engine *e){return e->animations && overlay_animation_busy(e->animations);}
bool motive_animate_overlay(motive_engine *e,const char *scene,const char *layer,const char *json,uint64_t *operation_id) {
    e->error[0]=0;if(scene_busy(e)){snprintf(e->error,sizeof(e->error),"TRANSITION_BUSY");return false;}
    if(!operation_id){snprintf(e->error,sizeof(e->error),"INVALID_ANIMATION");return false;}
    NSDictionary *a=[NSJSONSerialization JSONObjectWithData:[@(json) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    obs_sceneitem_t *item=NULL;
    for(size_t i=0;i<e->scene_count;i++)if(!strcmp(e->scenes[i]->id,scene))for(size_t j=0;j<e->scenes[i]->layer_count;j++)if(!strcmp(e->scenes[i]->layer_ids[j],layer))item=e->scenes[i]->items[j];
    if(!item){snprintf(e->error,sizeof(e->error),"LAYER_UNAVAILABLE");return false;}
    uint64_t operation=0;
    bool result=overlay_animation_start(e->animations,item,scene,layer,[a[@"kind"] UTF8String],[a[@"easing"] UTF8String],[a[@"duration_ms"] unsignedIntValue],[a[@"distance"] floatValue],[a[@"scale_from"] floatValue],&operation);
    if(!result)snprintf(e->error,sizeof(e->error),"ANIMATION_BUSY_OR_INVALID");else *operation_id=operation;return result;
}
bool motive_ack_overlay_animation(motive_engine *e,uint64_t id) {
    e->error[0]=0;bool result=overlay_animation_ack(e->animations,id);
    if(!result)snprintf(e->error,sizeof(e->error),"ANIMATION_ACK_UNAVAILABLE");return result;
}
bool motive_cancel_overlay_animation(motive_engine *e,uint64_t id) {
    e->error[0]=0;bool result=overlay_animation_cancel(e->animations,id);
    if(!result)snprintf(e->error,sizeof(e->error),"ANIMATION_OPERATION_UNAVAILABLE");return result;
}
