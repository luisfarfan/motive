/* Two independent encoder/output owners on the same OBS production. */
static bool start_profile(motive_engine *,output_slot *,const char *,const char *,bool,const char *);

/* Official OBS packet callback: synchronous before the output plugin sees the
 * packet. Counts dispatch, never successful disk/network delivery. The try-lock
 * drops trace metadata rather than ever waiting for an owner/UI snapshot. */
static void output_packet_observed(obs_output_t *output,struct encoder_packet *packet,
                                   struct encoder_packet_time *timing,void *data) {
    (void)output;(void)timing;
    output_slot *s=data;output_packet_trace *trace=&s->packet_trace;
    if(!packet)return;
    uint64_t sequence=atomic_fetch_add(&trace->sequence,1)+1;
    bool video=packet->type==OBS_ENCODER_VIDEO;
    atomic_fetch_add(video ? &trace->video_packets:&trace->audio_packets,1);
    if(atomic_flag_test_and_set_explicit(&trace->guard,memory_order_acquire)) {
        atomic_fetch_add(&trace->missed,1);return;
    }
    output_packet_record record={.sequence=sequence,.observed_ns=os_gettime_ns(),
        .size=packet->size,.pts=packet->pts,.dts=packet->dts,
        .dts_usec=packet->dts_usec,.sys_dts_usec=packet->sys_dts_usec,
        .timebase_num=packet->timebase_num,.timebase_den=packet->timebase_den,
        .track=(uint32_t)packet->track_idx,.video=video,.keyframe=packet->keyframe};
    trace->records[trace->next]=record;
    trace->next=(trace->next+1)%MOTIVE_OUTPUT_TRACE_CAPACITY;
    unsigned retained=atomic_load(&trace->retained);
    if(retained<MOTIVE_OUTPUT_TRACE_CAPACITY)atomic_store(&trace->retained,retained+1);
    else atomic_fetch_add(&trace->overwritten,1);
    atomic_flag_clear_explicit(&trace->guard,memory_order_release);
}
static id output_optional_ns(uint64_t value) {return value ? @(value):[NSNull null];}
static NSDictionary *output_diagnostic_summary(output_slot *s) {
    output_packet_trace *trace=&s->packet_trace;
    uint64_t stop=atomic_load(&s->stopped_ns);
    return @{@"version":@1,@"packet_observer_available":@(!s->legacy_udp),
        @"observed_video_packets":s->legacy_udp ? [NSNull null]:@(atomic_load(&trace->video_packets)),
        @"observed_audio_packets":s->legacy_udp ? [NSNull null]:@(atomic_load(&trace->audio_packets)),
        @"trace_capacity":@(MOTIVE_OUTPUT_TRACE_CAPACITY),
        @"trace_retained_records":@(atomic_load(&trace->retained)),
        @"trace_overwritten_records":@(atomic_load(&trace->overwritten)),
        @"trace_missed_records":@(atomic_load(&trace->missed)),
        @"stop_requested_ns":output_optional_ns(s->stop_requested_ns),
        @"stop_call_returned_ns":output_optional_ns(s->stop_returned_ns),
        @"stop_signal_ns":output_optional_ns(stop),
        @"quiescent_observed_ns":output_optional_ns(s->quiescent_ns),
        @"stop_to_quiescence_ms":s->stop_requested_ns && s->quiescent_ns>=s->stop_requested_ns ?
            @((s->quiescent_ns-s->stop_requested_ns)/1000000):[NSNull null],
        @"frames_written":[NSNull null],@"frames_received":[NSNull null],@"frames_decoded":[NSNull null],
        @"delivery_verified":@NO};
}
char *motive_output_packet_trace(motive_engine *e,unsigned target) {
    if(target>1)return NULL;
    output_slot *s=&e->outputs[target];output_packet_trace *trace=&s->packet_trace;
    output_packet_record records[MOTIVE_OUTPUT_TRACE_CAPACITY];unsigned retained=0;
    bool busy=atomic_flag_test_and_set_explicit(&trace->guard,memory_order_acquire);
    if(!busy) {
        retained=atomic_load(&trace->retained);
        unsigned first=(trace->next+MOTIVE_OUTPUT_TRACE_CAPACITY-retained)%MOTIVE_OUTPUT_TRACE_CAPACITY;
        for(unsigned i=0;i<retained;i++)records[i]=trace->records[(first+i)%MOTIVE_OUTPUT_TRACE_CAPACITY];
        atomic_flag_clear_explicit(&trace->guard,memory_order_release);
    }
    NSMutableArray *packets=[NSMutableArray arrayWithCapacity:retained];
    for(unsigned i=0;i<retained;i++) {
        output_packet_record p=records[i];
        [packets addObject:@{@"sequence":@(p.sequence),@"observed_ns":@(p.observed_ns),
            @"media_type":p.video ? @"video":@"audio",@"track":@(p.track),@"size":@(p.size),
            @"pts":@(p.pts),@"dts":@(p.dts),@"dts_usec":@(p.dts_usec),@"sys_dts_usec":@(p.sys_dts_usec),
            @"timebase_num":@(p.timebase_num),@"timebase_den":@(p.timebase_den),@"keyframe":@(p.keyframe)}];
    }
    NSDictionary *info=@{@"version":@1,@"scope":@"before_output_plugin",
        @"capacity":@(MOTIVE_OUTPUT_TRACE_CAPACITY),@"snapshot_busy":@(busy),
        @"summary":output_diagnostic_summary(s),@"packets":packets};
    NSData *json=[NSJSONSerialization dataWithJSONObject:info options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}

static void output_started(void *data,calldata_t *cd) {
    (void)cd;output_slot *s=data;
    atomic_store(&s->started_ns,os_gettime_ns());
    atomic_store(&s->output_started,true);
}
static void output_stopped(void *data,calldata_t *cd) {
    output_slot *s=data;
    atomic_store(&s->stopped_ns,os_gettime_ns());
    atomic_store(&s->output_code,(int)calldata_int(cd,"code"));
    atomic_store(&s->output_stopped,true);
}
static void end_output_activity(output_slot *s) {
    if (!s->output_activity) return;
    [[NSProcessInfo processInfo] endActivity:(__bridge id)s->output_activity];
    CFRelease(s->output_activity);s->output_activity=NULL;
}
static void begin_output_activity(output_slot *s) {
    if (s->output_activity) return;
    id activity=[[NSProcessInfo processInfo] beginActivityWithOptions:
        NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical
        reason:@"Motive media output"];
    s->output_activity=(void *)CFBridgingRetain(activity);
}
static void capture_output_metrics(output_slot *s) {
    if (s->output) {
        uint64_t bytes=obs_output_get_total_bytes(s->output);
        uint32_t frames=obs_output_get_total_frames(s->output);
        int drops=obs_output_get_frames_dropped(s->output);
        if(bytes>s->bytes)s->bytes=bytes;
        if(frames>s->frames)s->frames=frames;
        if(drops>s->drops)s->drops=drops;
    }
    if(s->video_encoder) {
        uint32_t frames=obs_encoder_get_encoded_frames(s->video_encoder);
        if(frames>s->encoded_frames)s->encoded_frames=frames;
    }
}
/* 0 quiescent; 1 active; 2 draining; 3 connecting; 4 starting.
 * A stop signal never substitutes for the OBS + H8 worker barrier. */
static int output_slot_state(output_slot *s) {
    if (!s->output) return 0;
    capture_output_metrics(s);
    if(s->network_output) {
        calldata_t state;calldata_init(&state);
        bool known=proc_handler_call(obs_output_get_proc_handler(s->output),"get_thread_state",&state);
        bool connecting=calldata_bool(&state,"connecting");
        bool workers=calldata_bool(&state,"workers_active");calldata_free(&state);
        if(!known || connecting)return 3;
        if(atomic_load(&s->output_stopped) && workers)return 2;
    }
    if(atomic_load(&s->output_stopped)) {
        if(obs_output_active(s->output))return 2;
        if(!s->quiescent_ns)s->quiescent_ns=os_gettime_ns();
        end_output_activity(s);return 0;
    }
    if(!atomic_load(&s->output_started))return s->network_output ? 3:4;
    return obs_output_active(s->output) ? 1:2;
}
int motive_output_state(motive_engine *e) {
    int result=0;
    for(unsigned i=0;i<2;i++) {
        int state=output_slot_state(&e->outputs[i]);
        if(state==3)return 3;
        if(state==2)result=2;
        else if(state && !result)result=1;
    }
    return result;
}
static output_slot *legacy_output_slot(motive_engine *e) {
    unsigned relevant=0,index=e->last_output;
    for(unsigned i=0;i<2;i++) {
        if(output_slot_state(&e->outputs[i]) || atomic_load(&e->outputs[i].output_code)) {
            relevant++;index=i;
        }
    }
    return &e->outputs[relevant==1 ? index:e->last_output];
}
/* Only call after the barrier, or during synchronous preparation rollback
 * before obs_output_start accepted ownership of any worker. */
static void release_output_slot(output_slot *s) {
    capture_output_metrics(s);
    if(s->output) {
        if(s->packet_observer_registered) {
            obs_output_remove_packet_callback(s->output,output_packet_observed,s);
            s->packet_observer_registered=false;
        }
        signal_handler_disconnect(obs_output_get_signal_handler(s->output),"start",output_started,s);
        signal_handler_disconnect(obs_output_get_signal_handler(s->output),"stop",output_stopped,s);
        obs_output_release(s->output);s->output=NULL;
    }
    if(s->service){obs_service_release(s->service);s->service=NULL;}
    if(s->video_encoder){obs_encoder_release(s->video_encoder);s->video_encoder=NULL;}
    if(s->audio_encoder){obs_encoder_release(s->audio_encoder);s->audio_encoder=NULL;}
    end_output_activity(s);
}
static void release_outputs(motive_engine *e) {
    for(unsigned i=0;i<2;i++)release_output_slot(&e->outputs[i]);
}
static bool prepare_output_slot(motive_engine *e,unsigned target,bool legacy) {
    output_slot *s=&e->outputs[target];
    e->error[0]=0;
    if(output_slot_state(s) || (legacy && motive_output_state(e)) ||
       (!legacy && e->outputs[1].legacy_udp && output_slot_state(&e->outputs[1]))) {
        snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;
    }
    release_output_slot(s);e->last_output=target;
    s->bytes=0;s->frames=0;s->encoded_frames=0;s->drops=0;
    output_trace_reset(&s->packet_trace);
    s->stop_requested_ns=0;s->stop_returned_ns=0;s->quiescent_ns=0;
    s->network_output=target==1 && !legacy;s->legacy_udp=legacy;
    s->selected_encoder[0]=0;s->fallback_reason[0]=0;s->selected_hardware=false;
    atomic_store(&s->output_started,false);atomic_store(&s->output_stopped,true);
    atomic_store(&s->output_code,0);atomic_store(&s->started_ns,0);atomic_store(&s->stopped_ns,0);
    return true;
}
void motive_stop_output_target(motive_engine *e,unsigned target) {
    if(target>1)return;
    output_slot *s=&e->outputs[target];
    // Deferred cancellation remains the owner's policy. Never force/join a
    // handshake, and never prevent stopping the other independent output.
    if(s->output && !atomic_load(&s->output_stopped) && output_slot_state(s)!=3) {
        bool first=!s->stop_requested_ns;
        if(first)s->stop_requested_ns=os_gettime_ns();
        obs_output_stop(s->output);
        if(first)s->stop_returned_ns=os_gettime_ns();
    }
}
void motive_stop_output(motive_engine *e) {
    for(unsigned i=0;i<2;i++)motive_stop_output_target(e,i);
}
bool motive_reset_output_target(motive_engine *e,unsigned target) {
    if(target>1){snprintf(e->error,sizeof(e->error),"INVALID_OUTPUT_TARGET");return false;}
    output_slot *s=&e->outputs[target];
    if(output_slot_state(s)){snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;}
    release_output_slot(s);atomic_store(&s->output_code,0);return true;
}
bool motive_reset_output(motive_engine *e) {
    if(motive_output_state(e)){snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;}
    for(unsigned i=0;i<2;i++)motive_reset_output_target(e,i);
    return true;
}
int motive_output_code(motive_engine *e) {return atomic_load(&legacy_output_slot(e)->output_code);}
uint64_t motive_output_bytes(motive_engine *e) {output_slot *s=legacy_output_slot(e);capture_output_metrics(s);return s->bytes;}
uint32_t motive_output_frames(motive_engine *e) {output_slot *s=legacy_output_slot(e);capture_output_metrics(s);return s->frames;}
int motive_output_drops(motive_engine *e) {output_slot *s=legacy_output_slot(e);capture_output_metrics(s);return s->drops;}

char *motive_output_info(motive_engine *e,unsigned target) {
    if(target>1)return NULL;
    output_slot *s=&e->outputs[target];int state=output_slot_state(s);
    capture_output_metrics(s);
    uint64_t start=atomic_load(&s->started_ns),stop=atomic_load(&s->stopped_ns);
    uint64_t end=stop ? stop:os_gettime_ns();
    NSDictionary *info=@{@"state":@(state),@"code":@(atomic_load(&s->output_code)),
        @"active_duration_ms":@(start && end>=start ? (end-start)/1000000:0),
        @"diagnostics":output_diagnostic_summary(s),
        @"stats":@{@"output_bytes":@(s->bytes),@"output_frames":@(s->frames),
            @"output_dropped_frames":@(s->drops),@"encoded_frames":s->legacy_udp ? [NSNull null]:@(s->encoded_frames)},
        @"encoding":@{@"selected_id":s->selected_encoder[0] ? @(s->selected_encoder):[NSNull null],
            @"selected_hardware":@(s->selected_hardware),
            @"fallback_reason":s->fallback_reason[0] ? @(s->fallback_reason):[NSNull null]}};
    NSData *json=[NSJSONSerialization dataWithJSONObject:info options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}

bool motive_start_stream(motive_engine *e,const char *url,const char *profile,const char *credential) {
    if(!e->rtmp_loaded){snprintf(e->error,sizeof(e->error),"SERVICE_UNAVAILABLE");return false;}
    if(!prepare_output_slot(e,1,false))return false;
    return start_profile(e,&e->outputs[1],url,profile,true,credential);
}
bool motive_start_output(motive_engine *e,const char *path,bool local_stream,const char *profile) {
    unsigned target=local_stream ? 1:0;
    if(!prepare_output_slot(e,target,local_stream))return false;
    output_slot *s=&e->outputs[target];
    if(!local_stream)return start_profile(e,s,path,profile,false,NULL);
    obs_data_t *settings=obs_data_create();
    obs_data_set_string(settings,"url","udp://127.0.0.1:19350?pkt_size=1316");
    obs_data_set_string(settings,"format_name","mpegts");
    obs_data_set_string(settings,"video_encoder","libx264");
    obs_data_set_string(settings,"audio_encoder","aac");
    obs_data_set_string(settings,"video_settings","preset=ultrafast tune=zerolatency");
    obs_data_set_int(settings,"video_bitrate",2500);obs_data_set_int(settings,"audio_bitrate",160);
    obs_data_set_int(settings,"gop_size",60);
    s->output=obs_output_create("ffmpeg_output","Local MPEG-TS",settings,NULL);obs_data_release(settings);
    if(!s->output){snprintf(e->error,sizeof(e->error),"OUTPUT_UNAVAILABLE");return false;}
    obs_output_set_media(s->output,obs_get_video(),obs_get_audio());obs_output_set_mixers(s->output,1);
    signal_handler_connect(obs_output_get_signal_handler(s->output),"start",output_started,s);
    signal_handler_connect(obs_output_get_signal_handler(s->output),"stop",output_stopped,s);
    atomic_store(&s->output_stopped,false);begin_output_activity(s);
    if(!obs_output_start(s->output)) {
        snprintf(e->error,sizeof(e->error),"OUTPUT_START_FAILED");
        release_output_slot(s);atomic_store(&s->output_stopped,true);return false;
    }
    snprintf(s->selected_encoder,sizeof(s->selected_encoder),"libx264 (loopback)");return true;
}
