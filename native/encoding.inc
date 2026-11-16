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
    NSDictionary *info=@{@"available":available,@"videotoolbox_loaded":@(e->vt_loaded),
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
static bool prepare_recording_video(motive_engine *e,const char *path,const char *id) {
    obs_data_t *settings=obs_data_create();
    obs_data_set_string(settings,"path",path);
    e->output=obs_output_create("ffmpeg_muxer","Local recording",settings,NULL);
    obs_data_release(settings);
    if (!e->output) {snprintf(e->error,sizeof(e->error),"OUTPUT_UNAVAILABLE");return false;}
    obs_data_t *v=obs_encoder_defaults(id);
    if (!v) v=obs_data_create();
    obs_data_set_int(v,"bitrate",2500);obs_data_set_string(v,"rate_control","CBR");
    obs_data_set_int(v,"keyint_sec",2);obs_data_set_string(v,"profile","high");
    if (!strcmp(id,"obs_x264")) obs_data_set_string(v,"preset","veryfast");
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

static bool start_recording(motive_engine *e,const char *path,const char *policy) {
    bool automatic=!strcmp(policy,"auto");
    bool use_vt=strcmp(policy,"x264") && e->vt_h264_id[0];
    if (!automatic && !strcmp(policy,"videotoolbox") && !use_vt) {
        snprintf(e->error,sizeof(e->error),"ENCODER_UNAVAILABLE: %s",e->vt_unavailable_reason);
        return false;
    }
    if (automatic && !use_vt)
        snprintf(e->fallback_reason,sizeof(e->fallback_reason),"%s",e->vt_unavailable_reason);
    const char *id=use_vt ? e->vt_h264_id:"obs_x264";
    bool ready=prepare_recording_video(e,path,id);
    if (!ready && automatic && use_vt && strncmp(e->error,"VIDEO_ENCODER_",14)==0) {
        snprintf(e->fallback_reason,sizeof(e->fallback_reason),"VIDEOTOOLBOX_INITIALIZATION_FAILED");
        release_output(e);
        e->error[0]=0;use_vt=false;id="obs_x264";
        ready=prepare_recording_video(e,path,id);
    }
    if (!ready) {release_output(e);return false;}
    obs_data_t *a=obs_data_create();obs_data_set_int(a,"bitrate",160);
    e->audio_encoder=obs_audio_encoder_create("ffmpeg_aac","AAC",a,0,NULL);obs_data_release(a);
    if (!e->audio_encoder) {snprintf(e->error,sizeof(e->error),"AUDIO_ENCODER_UNAVAILABLE");release_output(e);return false;}
    obs_encoder_set_audio(e->audio_encoder,obs_get_audio());
    obs_output_set_audio_encoder(e->output,e->audio_encoder,0);
    atomic_store(&e->output_stopped,false);atomic_store(&e->output_code,0);
    signal_handler_connect(obs_output_get_signal_handler(e->output),"stop",output_stopped,e);
    if (!obs_output_start(e->output)) {
        snprintf(e->error,sizeof(e->error),"OUTPUT_START_FAILED: %.440s",obs_output_get_last_error(e->output) ?: "see local OBS log");
        release_output(e);atomic_store(&e->output_stopped,true);return false;
    }
    snprintf(e->selected_encoder,sizeof(e->selected_encoder),"%s",id);
    e->selected_hardware=use_vt;
    return true;
}
