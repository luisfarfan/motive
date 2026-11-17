/* Official OBS VideoToolbox module; Apple API is used only for discovery.
 * No private encoder structs, custom compression session or media clock. */
static void discover_encoders(motive_engine *e) {
    CFArrayRef apple_list=NULL;
    if (e->vt_loaded) VTCopyVideoEncoderList(NULL,&apple_list);
    NSMutableDictionary *hardware=[NSMutableDictionary dictionary];
    if (apple_list) {
        for (NSDictionary *entry in (__bridge NSArray *)apple_list) {
            NSString *id=entry[(__bridge NSString *)kVTVideoEncoderList_EncoderID];
            if (id) hardware[id]=entry[(__bridge NSString *)kVTVideoEncoderList_IsHardwareAccelerated] ?: @NO;
        }
    }
    NSMutableArray *items=[NSMutableArray array];
    const char *id=NULL;
    for (size_t i=0;obs_enum_encoder_types(i,&id);i++) {
        const char *codec=obs_get_encoder_codec(id);
        if (obs_get_encoder_type(id)!=OBS_ENCODER_VIDEO || !codec || strcmp(codec,"h264")) continue;
        bool hw=[hardware[@(id)] boolValue];
        bool supported=hw || !strcmp(id,"obs_x264");
        [items addObject:@{@"id":@(id),@"name":@(obs_encoder_get_display_name(id)),
            @"codec":@(codec),@"hardware":@(hw),@"selectable":@(supported)}];
        if (hw && (!e->vt_h264_id[0] || strcmp(id,e->vt_h264_id)<0))
            snprintf(e->vt_h264_id,sizeof(e->vt_h264_id),"%s",id);
    }
    if (apple_list) CFRelease(apple_list);
    if (!e->vt_h264_id[0] && !e->vt_unavailable_reason[0])
        snprintf(e->vt_unavailable_reason,sizeof(e->vt_unavailable_reason),"VIDEOTOOLBOX_HARDWARE_UNAVAILABLE");
    NSData *json=[NSJSONSerialization dataWithJSONObject:items options:0 error:nil];
    e->encoder_inventory=strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}

char *motive_encoding_info(motive_engine *e) {
    NSArray *available=e->encoder_inventory ? [NSJSONSerialization JSONObjectWithData:
        [@(e->encoder_inventory) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil]:@[];
    NSDictionary *info=@{@"available":available,@"rtmp_available":@(e->rtmp_loaded),@"videotoolbox_loaded":@(e->vt_loaded),
        @"native_logs_suppressed":@(atomic_load(&protect_obs_logs)),
        @"videotoolbox_id":e->vt_h264_id[0] ? @(e->vt_h264_id):[NSNull null],
        @"unavailable_reason":e->vt_unavailable_reason[0] ? @(e->vt_unavailable_reason):[NSNull null],
        @"selected_id":e->selected_encoder[0] ? @(e->selected_encoder):[NSNull null],
        @"selected_hardware":@(e->selected_hardware),
        @"fallback_reason":e->fallback_reason[0] ? @(e->fallback_reason):[NSNull null]};
    NSData *json=[NSJSONSerialization dataWithJSONObject:info options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}

uint32_t motive_encoded_frames(motive_engine *e) {
    return e->video_encoder ? obs_encoder_get_encoded_frames(e->video_encoder):0;
}
uint32_t motive_video_skipped_frames(void) { return video_output_get_skipped_frames(obs_get_video()); }

/* Initialize only the video encoder before attaching AAC. In OBS 33.0.1 the
 * flags argument is ignored; unattached audio encoders are skipped. This makes
 * auto fallback specific to video initialization, before a mux helper starts.
 * A disk/mux/audio error must never silently retry or overwrite a partial file. */
static bool prepare_encoded_video(motive_engine *e,const char *path,const char *id,obs_data_t *profile,bool stream,const char *credential) {
    obs_data_t *settings=obs_data_create();
    obs_data_set_string(settings,"path",path);
    if (stream) {
        obs_data_set_int(settings,"max_shutdown_time_sec",3);
        obs_data_set_bool(settings,"dyn_bitrate",false);
    }
    e->output=obs_output_create(stream ? "rtmp_output":"ffmpeg_muxer",stream ? "Local RTMP":"Local recording",settings,NULL);
    obs_data_release(settings);
    if (!e->output) {snprintf(e->error,sizeof(e->error),"OUTPUT_UNAVAILABLE");return false;}
    if (stream) {
        calldata_t state;calldata_init(&state);
        bool supported=proc_handler_call(obs_output_get_proc_handler(e->output),"get_thread_state",&state);
        calldata_free(&state);
        if (!supported) {snprintf(e->error,sizeof(e->error),"RTMP_LIFECYCLE_UNAVAILABLE");return false;}
        obs_data_t *service=obs_data_create();
        obs_data_set_string(service,"server",path);
        obs_data_set_string(service,"credential_ref",credential ?: "");
        e->service=obs_service_create("motive_local_service","Local receiver",service,NULL);
        obs_data_release(service);
        if (!e->service) {snprintf(e->error,sizeof(e->error),"SERVICE_UNAVAILABLE");return false;}
        obs_output_set_service(e->output,e->service);
        obs_output_set_reconnect_settings(e->output,0,1);
    }
    obs_data_t *v=obs_encoder_defaults(id);
    if (!v) v=obs_data_create();
    obs_data_set_int(v,"bitrate",obs_data_get_int(profile,"bitrate_kbps"));obs_data_set_string(v,"rate_control","CBR");
    obs_data_set_int(v,"keyint_sec",obs_data_get_int(profile,"keyframe_seconds"));obs_data_set_string(v,"profile","high");
    bool reorder=obs_data_get_bool(profile,"frame_reordering");
    if (!strcmp(id,"obs_x264")) {
        obs_data_set_string(v,"preset","veryfast");
        if (!reorder) obs_data_set_int(v,"bf",0);
    } else obs_data_set_bool(v,"bframes",reorder);
    e->video_encoder=obs_video_encoder_create(id,"Motive H264",v,NULL);
    obs_data_release(v);
    if (!e->video_encoder) {snprintf(e->error,sizeof(e->error),"VIDEO_ENCODER_UNAVAILABLE");return false;}
    obs_encoder_set_video(e->video_encoder,obs_get_video());
    obs_output_set_video_encoder(e->output,e->video_encoder);
    if (!obs_output_initialize_encoders(e->output,0)) {
        const char *reason=obs_output_get_last_error(e->output);
        snprintf(e->error,sizeof(e->error),"VIDEO_ENCODER_INIT_FAILED: %.420s",reason ?: "see local OBS log");
        return false;
    }
    return true;
}

static bool start_encoded(motive_engine *e,const char *path,obs_data_t *profile,bool stream,const char *credential) {
    const char *policy=obs_data_get_string(profile,"encoder");
    bool automatic=!strcmp(policy,"auto");
    bool use_vt=strcmp(policy,"x264") && e->vt_h264_id[0];
    if (!automatic && !strcmp(policy,"videotoolbox") && !use_vt) {
        snprintf(e->error,sizeof(e->error),"ENCODER_UNAVAILABLE: %s",e->vt_unavailable_reason);
        return false;
    }
    if (automatic && !use_vt)
        snprintf(e->fallback_reason,sizeof(e->fallback_reason),"%s",e->vt_unavailable_reason);
    const char *id=use_vt ? e->vt_h264_id:"obs_x264";
    bool ready=prepare_encoded_video(e,path,id,profile,stream,credential);
    if (!ready && automatic && use_vt && strncmp(e->error,"VIDEO_ENCODER_",14)==0) {
        snprintf(e->fallback_reason,sizeof(e->fallback_reason),"VIDEOTOOLBOX_INITIALIZATION_FAILED");
        release_output(e);
        e->error[0]=0;use_vt=false;id="obs_x264";
        ready=prepare_encoded_video(e,path,id,profile,stream,credential);
    }
    if (!ready) {release_output(e);return false;}
    obs_data_t *a=obs_data_create();obs_data_set_int(a,"bitrate",160);
    e->audio_encoder=obs_audio_encoder_create("ffmpeg_aac","AAC",a,0,NULL);obs_data_release(a);
    if (!e->audio_encoder) {snprintf(e->error,sizeof(e->error),"AUDIO_ENCODER_UNAVAILABLE");release_output(e);return false;}
    obs_encoder_set_audio(e->audio_encoder,obs_get_audio());
    obs_output_set_audio_encoder(e->output,e->audio_encoder,0);
    atomic_store(&e->output_stopped,false);atomic_store(&e->output_code,0);
    atomic_store(&e->output_started,false);
    e->network_output=stream;
    signal_handler_connect(obs_output_get_signal_handler(e->output),"start",output_started,e);
    signal_handler_connect(obs_output_get_signal_handler(e->output),"stop",output_stopped,e);
    if (!obs_output_start(e->output)) {
        snprintf(e->error,sizeof(e->error),"OUTPUT_START_FAILED");
        release_output(e);atomic_store(&e->output_stopped,true);return false;
    }
    snprintf(e->selected_encoder,sizeof(e->selected_encoder),"%s",id);
    e->selected_hardware=use_vt;
    return true;
}

static bool start_profile(motive_engine *e,const char *path,const char *json,bool stream,const char *credential) {
    obs_data_t *p=obs_data_create_from_json(json);
    const char *encoder=obs_data_get_string(p,"encoder");
    long long bitrate=obs_data_get_int(p,"bitrate_kbps"),keyint=obs_data_get_int(p,"keyframe_seconds");
    bool valid=p && bitrate>=250 && bitrate<=20000 && keyint>=1 && keyint<=10 &&
        !strcmp(obs_data_get_string(p,"rate_control"),"cbr") &&
        (!strcmp(encoder,"auto") || !strcmp(encoder,"videotoolbox") || !strcmp(encoder,"x264"));
    if (!valid) {obs_data_release(p);snprintf(e->error,sizeof(e->error),"INVALID_PROFILE");return false;}
    bool ok=start_encoded(e,path,p,stream,credential);obs_data_release(p);return ok;
}
bool motive_start_stream(motive_engine *e,const char *url,const char *json,const char *credential) {
    e->error[0]=0;
    if (motive_output_state(e)) {snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;}
    if (!e->rtmp_loaded) {snprintf(e->error,sizeof(e->error),"SERVICE_UNAVAILABLE");return false;}
    release_output(e);
    e->selected_encoder[0]=0;e->fallback_reason[0]=0;e->selected_hardware=false;
    return start_profile(e,url,json,true,credential);
}
