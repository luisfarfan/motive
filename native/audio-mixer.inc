/* Only libobs sums audio, applies volume/mute and timestamps audio actions.
 * Global output channels 1..8 feed mix 0, independently of video channel 0.
 * Callbacks only measure/copy bounded metrics; they never modify audio samples. */
typedef struct {
    obs_source_t *source;
    pthread_t thread;
    atomic_bool stop;
} tone_generator;
static void *tone_run(void *param) {
    tone_generator *tone=param;
    const uint64_t start=os_gettime_ns();uint64_t frames=0;
    float samples[480];
    // A source fixture, not a mixer. Sample position determines phase and PTS;
    // scheduling never accumulates timestamps from MCP/UI or repeated sleeps.
    while(!atomic_load(&tone->stop)) {
        uint64_t now=os_gettime_ns();
        // Skip elapsed blocks after a scheduler stall/sleep instead of bursting
        // old samples into OBS. The sample clock/phase remain anchored to start.
        if(now>start+frames*1000000000ULL/48000+1000000000ULL)
            frames=((now-start)/10000000ULL)*480;
        uint64_t timestamp=start+frames*1000000000ULL/48000;
        os_sleepto_ns(timestamp);
        if(atomic_load(&tone->stop))break;
        for(size_t i=0;i<480;i++) samples[i]=0.0630957344f*sinf((float)((frames+i)%48000)*2*M_PI*440/48000);
        struct obs_source_audio audio={.data={(const uint8_t *)samples,(const uint8_t *)samples},
            .frames=480,.speakers=SPEAKERS_STEREO,.format=AUDIO_FORMAT_FLOAT_PLANAR,
            .samples_per_sec=48000,.timestamp=timestamp};
        obs_source_output_audio(tone->source,&audio);frames+=480;
    }
    return NULL;
}
static const char *tone_name(void *unused) {(void)unused;return "Motive controlled 440 Hz tone";}
static void *tone_create(obs_data_t *settings,obs_source_t *source) {
    (void)settings;tone_generator *tone=calloc(1,sizeof(*tone));tone->source=source;
    if(pthread_create(&tone->thread,NULL,tone_run,tone)) {free(tone);return NULL;}
    return tone;
}
static void tone_destroy(void *data) {
    tone_generator *tone=data;atomic_store(&tone->stop,true);pthread_join(tone->thread,NULL);free(tone);
}
static struct obs_source_info tone_info={.id="motive_audio_tone",.type=OBS_SOURCE_TYPE_INPUT,
    .output_flags=OBS_SOURCE_AUDIO,.get_name=tone_name,.create=tone_create,.destroy=tone_destroy};

typedef struct {
    pthread_mutex_t lock;
    uint64_t frames, seen_ns, timestamp, clipped_blocks;
    float peak[2], rms[2], input_peak[2];
} audio_metrics;
struct audio_input {
    char id[64],device[512];
    obs_source_t *source;
    obs_volmeter_t *meter;
    audio_metrics metrics;
    uint64_t instance,created_ns;
    unsigned slot;
    int fault;
    bool disconnected;
};
struct audio_mix_meter { audio_metrics metrics; };

static void audio_metrics_init(audio_metrics *m) { pthread_mutex_init(&m->lock,NULL); }
static void audio_flow(void *param,obs_source_t *source,const struct audio_data *data,bool muted) {
    (void)source;(void)muted;audio_metrics *m=&((audio_input *)param)->metrics;
    pthread_mutex_lock(&m->lock);
    m->frames+=data->frames;m->seen_ns=os_gettime_ns();m->timestamp=data->timestamp;
    pthread_mutex_unlock(&m->lock);
}
static void audio_levels(void *param,const float magnitude[MAX_AUDIO_CHANNELS],
                         const float peak[MAX_AUDIO_CHANNELS],const float input_peak[MAX_AUDIO_CHANNELS]) {
    audio_metrics *m=&((audio_input *)param)->metrics;
    pthread_mutex_lock(&m->lock);
    bool clipped=false;
    for (size_t c=0;c<2;c++) {
        m->rms[c]=obs_db_to_mul(magnitude[c]);m->peak[c]=obs_db_to_mul(peak[c]);
        m->input_peak[c]=obs_db_to_mul(input_peak[c]);
        clipped |= m->input_peak[c]>=1.0f;
    }
    if (clipped) m->clipped_blocks++;
    pthread_mutex_unlock(&m->lock);
}
static void mix_levels(void *param,size_t mix_idx,struct audio_data *data) {
    (void)mix_idx;audio_metrics *m=&((audio_mix_meter *)param)->metrics;
    float peaks[2]={0},rms[2]={0};bool clipped=false;
    for (size_t c=0;c<2;c++) if (data->data[c]) {
        const float *samples=(const float *)data->data[c];double sum=0;
        for (size_t i=0;i<data->frames;i++) {
            float v=samples[i];peaks[c]=fmaxf(peaks[c],fabsf(v));sum+=(double)v*v;
        }
        rms[c]=data->frames ? sqrt(sum/data->frames):0;
        clipped |= peaks[c]>=1.0f;
    }
    pthread_mutex_lock(&m->lock);
    m->frames+=data->frames;m->seen_ns=os_gettime_ns();m->timestamp=data->timestamp;
    memcpy(m->peak,peaks,sizeof(peaks));memcpy(m->rms,rms,sizeof(rms));
    if (clipped) m->clipped_blocks++;
    pthread_mutex_unlock(&m->lock);
}
static void audio_mix_start(motive_engine *e) {
    e->mix_meter=calloc(1,sizeof(*e->mix_meter));audio_metrics_init(&e->mix_meter->metrics);
    struct audio_convert_info conversion={.samples_per_sec=48000,.format=AUDIO_FORMAT_FLOAT_PLANAR,
        .speakers=SPEAKERS_STEREO,.allow_clipping=true};
    // Observe the native sum BEFORE libobs' output clamp. Encoders retain their
    // normal clamped conversion; this observer does not alter the output path.
    obs_add_raw_audio_callback(0,&conversion,mix_levels,e->mix_meter);
}
static audio_input *audio_find(motive_engine *e,const char *id) {
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i] && !strcmp(e->audio_inputs[i]->id,id)) return e->audio_inputs[i];
    return NULL;
}
static void audio_detach(audio_input *a) {
    obs_set_output_source(a->slot+1,NULL);
    if (a->source) obs_source_remove_audio_capture_callback(a->source,audio_flow,a);
    if (a->meter) {obs_volmeter_destroy(a->meter);a->meter=NULL;}
    if (a->source) {obs_source_release(a->source);a->source=NULL;}
}
static void audio_release(audio_input *a) {
    audio_detach(a);pthread_mutex_destroy(&a->metrics.lock);free(a);
}
static void audio_mix_stop(motive_engine *e) {
    if (e->mix_meter) {
        obs_remove_raw_audio_callback(0,mix_levels,e->mix_meter);
        pthread_mutex_destroy(&e->mix_meter->metrics.lock);free(e->mix_meter);e->mix_meter=NULL;
    }
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i]) {audio_release(e->audio_inputs[i]);e->audio_inputs[i]=NULL;}
}
static bool audio_attach(motive_engine *e,audio_input *a,const char *tone_path,float gain,bool muted) {
    (void)tone_path;
    obs_data_t *settings=obs_data_create();
    if (!strcmp(a->device,"tone")) {
        a->source=obs_source_create_private("motive_audio_tone",a->id,settings);
    } else {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) {
            obs_data_release(settings);a->fault=2;snprintf(e->error,sizeof(e->error),"MICROPHONE_PERMISSION_DENIED");return false;
        }
        if (!audio_available(a->device)) {
            obs_data_release(settings);a->fault=1;snprintf(e->error,sizeof(e->error),"DEVICE_UNAVAILABLE");return false;
        }
        obs_data_set_string(settings,"device_id",a->device);
        a->source=obs_source_create_private("coreaudio_input_capture",a->id,settings);
    }
    obs_data_release(settings);
    if (!a->source) {a->fault=4;snprintf(e->error,sizeof(e->error),"AUDIO_CREATE_FAILED");return false;}
    a->meter=obs_volmeter_create(OBS_FADER_LOG);
    if (!a->meter) {audio_detach(a);a->fault=4;snprintf(e->error,sizeof(e->error),"AUDIO_CREATE_FAILED");return false;}
    obs_source_set_monitoring_type(a->source,OBS_MONITORING_TYPE_NONE);
    obs_source_set_audio_mixers(a->source,1);
    obs_source_set_volume(a->source,obs_db_to_mul(gain));
    obs_source_set_muted(a->source,muted);
    obs_volmeter_set_peak_meter_type(a->meter,SAMPLE_PEAK_METER);
    obs_volmeter_add_callback(a->meter,audio_levels,a);
    obs_volmeter_attach_source(a->meter,a->source);
    obs_source_add_audio_capture_callback(a->source,audio_flow,a);
    a->created_ns=os_gettime_ns();a->instance=++e->audio_instances;a->fault=0;a->disconnected=false;
    obs_set_output_source(a->slot+1,a->source);
    return true;
}
bool motive_audio_add(motive_engine *e,const char *id,const char *device,const char *tone_path,float gain,bool muted) {
    if (audio_find(e,id)) {snprintf(e->error,sizeof(e->error),"AUDIO_ID_EXISTS");return false;}
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i] && !strcmp(e->audio_inputs[i]->device,device)) {
        snprintf(e->error,sizeof(e->error),"AUDIO_DEVICE_DUPLICATE");return false;
    }
    size_t slot=0;while(slot<8 && e->audio_inputs[slot]) slot++;
    if (slot==8) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_LIMIT");return false;}
    audio_input *a=calloc(1,sizeof(*a));a->slot=(unsigned)slot;
    snprintf(a->id,sizeof(a->id),"%s",id);snprintf(a->device,sizeof(a->device),"%s",device);
    audio_metrics_init(&a->metrics);
    if (!audio_attach(e,a,tone_path,gain,muted)) {audio_release(a);return false;}
    e->audio_inputs[slot]=a;return true;
}
bool motive_audio_remove(motive_engine *e,const char *id) {
    audio_input *a=audio_find(e,id);
    if (!a) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_NOT_FOUND");return false;}
    e->audio_inputs[a->slot]=NULL;audio_release(a);obs_wait_for_destroy_queue();return true;
}
bool motive_audio_control(motive_engine *e,const char *id,float gain,bool muted) {
    audio_input *a=audio_find(e,id);
    if (!a) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_NOT_FOUND");return false;}
    if (a->source) {obs_source_set_volume(a->source,obs_db_to_mul(gain));obs_source_set_muted(a->source,muted);}
    return true;
}
bool motive_audio_disconnect(motive_engine *e,const char *id) {
    audio_input *a=audio_find(e,id);
    if(!a) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_NOT_FOUND");return false;}
    audio_detach(a);a->disconnected=true;a->fault=0;
    obs_wait_for_destroy_queue();return true;
}
bool motive_audio_reconnect(motive_engine *e,const char *id,float gain,bool muted) {
    audio_input *a=audio_find(e,id);
    if(!a) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_NOT_FOUND");return false;}
    audio_detach(a);
    // The old physical session must finish destruction before reopening its UID.
    obs_wait_for_destroy_queue();
    pthread_mutex_lock(&a->metrics.lock);
    a->metrics.frames=0;a->metrics.seen_ns=0;a->metrics.timestamp=0;a->metrics.clipped_blocks=0;
    memset(a->metrics.peak,0,sizeof(a->metrics.peak));memset(a->metrics.rms,0,sizeof(a->metrics.rms));
    memset(a->metrics.input_peak,0,sizeof(a->metrics.input_peak));
    pthread_mutex_unlock(&a->metrics.lock);a->disconnected=false;
    return audio_attach(e,a,"",gain,muted);
}
// Restore retains unavailable desired inputs, with explicit failure, so the user
// can reconnect that same stable ID later. This never substitutes a device.
bool motive_audio_restore_missing(motive_engine *e,const char *id,const char *device) {
    if(audio_find(e,id))return false;
    size_t slot=0;while(slot<8 && e->audio_inputs[slot])slot++;
    if(slot==8)return false;
    audio_input *a=calloc(1,sizeof(*a));a->slot=(unsigned)slot;
    snprintf(a->id,sizeof(a->id),"%s",id);snprintf(a->device,sizeof(a->device),"%s",device);
    audio_metrics_init(&a->metrics);
    a->fault=!strncmp(e->error,"MICROPHONE_PERMISSION_DENIED",28)?2:!strncmp(e->error,"AUDIO_CREATE_FAILED",19)?4:1;
    e->audio_inputs[slot]=a;return true;
}
bool motive_audio_rename_id(motive_engine *e,const char *old_id,const char *new_id) {
    audio_input *a=audio_find(e,old_id);
    if(!a || audio_find(e,new_id))return false;
    snprintf(a->id,sizeof(a->id),"%s",new_id);return true;
}
static int audio_health(audio_input *a) {
    if (a->fault) return a->fault;
    if (a->disconnected) return 5;
    if (strcmp(a->device,"tone")) {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) return 2;
        if (!audio_available(a->device)) return 1;
    }
    pthread_mutex_lock(&a->metrics.lock);uint64_t seen=a->metrics.seen_ns;pthread_mutex_unlock(&a->metrics.lock);
    return seen && os_gettime_ns()-seen<3000000000ULL ? 0:3;
}
void motive_poll_audio(motive_engine *e) {
    for(size_t i=0;i<8;i++) if(e->audio_inputs[i]) {
        audio_input *a=e->audio_inputs[i];if(a->disconnected || a->fault)continue;
        int health=audio_health(a);
        if(health==3 && os_gettime_ns()-a->created_ns<4000000000ULL)continue;
        if(health) {
            a->fault=health==3?6:health;
            if(a->source)obs_source_set_audio_mixers(a->source,0);
            // Release the failed capture too: the official CoreAudio plugin has
            // its own reconnect worker, which must not silently resume a latched
            // Motive input or hold a revoked capture behind a silent mixer mask.
            audio_detach(a);
        }
    }
}
static id audio_db(float value) { return value>0 && isfinite(value) ? @(20*log10f(value)):[NSNull null]; }
static NSDictionary *audio_metrics_json(audio_metrics *m) {
    pthread_mutex_lock(&m->lock);
    uint64_t age=m->seen_ns ? (os_gettime_ns()-m->seen_ns)/1000000:0;
    bool stale=!m->seen_ns || age>=1000;
    float p0=stale?0:m->peak[0],p1=stale?0:m->peak[1];
    float r0=stale?0:m->rms[0],r1=stale?0:m->rms[1];
    NSDictionary *v=@{@"frames":@(m->frames),@"timestamp_ns":@(m->timestamp),@"age_ms":m->seen_ns?@(age):[NSNull null],
        @"stale":@(stale),@"peak_dbfs":@[audio_db(p0),audio_db(p1)],@"rms_dbfs":@[audio_db(r0),audio_db(r1)],
        @"input_peak_dbfs":@[audio_db(stale?0:m->input_peak[0]),audio_db(stale?0:m->input_peak[1])],
        @"clipped_blocks":@(m->clipped_blocks)};
    pthread_mutex_unlock(&m->lock);return v;
}
char *motive_audio_state(motive_engine *e) {
    NSMutableArray *inputs=[NSMutableArray array];
    const char *codes[]={"","DEVICE_UNAVAILABLE","MICROPHONE_PERMISSION_DENIED","AUDIO_NOT_READY","AUDIO_CREATE_FAILED","AUDIO_DISCONNECTED","AUDIO_STALLED"};
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i]) {
        audio_input *a=e->audio_inputs[i];int health=audio_health(a);
        [inputs addObject:@{@"id":@(a->id),@"instance_id":@(a->instance),@"issue":health?@(codes[health]):[NSNull null],
            @"phase":health==0?@"ready":health==3?@"warming":health==5?@"disconnected":@"failed",
            @"levels":audio_metrics_json(&a->metrics)}];
    }
    NSDictionary *state=@{@"available":@YES,@"inputs":inputs,@"instances_created":@(e->audio_instances),
        @"mix":e->mix_meter?audio_metrics_json(&e->mix_meter->metrics):@{}};
    NSData *json=[NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}
/* Compatibility stats read the global mix. The legacy selector's device is
 * owned by the same registry; there is never a second physical capture. */
int motive_audio_health(motive_engine *e) {
    for(size_t i=0;i<8;i++) if(e->audio_inputs[i] && !strcmp(e->audio_inputs[i]->device,e->audio_id)) return audio_health(e->audio_inputs[i]);
    return 0;
}
uint64_t motive_audio_frames(motive_engine *e) {
    if(!e->mix_meter)return 0;audio_metrics *m=&e->mix_meter->metrics;
    pthread_mutex_lock(&m->lock);uint64_t frames=m->frames;pthread_mutex_unlock(&m->lock);return frames;
}
float motive_audio_peak(motive_engine *e) {
    if(!e->mix_meter)return 0;audio_metrics *m=&e->mix_meter->metrics;
    pthread_mutex_lock(&m->lock);float peak=fmaxf(m->peak[0],m->peak[1]);pthread_mutex_unlock(&m->lock);return fminf(peak,1.0f);
}
void motive_audio_legacy(motive_engine *e,const char *device) {snprintf(e->audio_id,sizeof(e->audio_id),"%s",device);}
