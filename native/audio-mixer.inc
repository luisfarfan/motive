/* Only libobs sums audio, applies volume/mute and timestamps audio actions.
 * Global output channels 1..8 feed mix 0, independently of video channel 0.
 * Callbacks only measure/copy bounded metrics; they never modify audio samples. */

/* Diagnostic only: set MOTIVE_TEST_AUDIO_TRACE=1 before starting Motive.
 * Off by default; never persists and never contains PCM, device IDs or paths.
 * One process-wide ring is bounded to 2048 records / <=384 KiB, plus a <=24 KiB
 * owner stack batch. Capture stops after 65536 accepted records per process.
 * Producers never wait, allocate, format or perform I/O: a busy/full ring loses
 * diagnostic records and exposes separate contention/overflow counters.
 *
 * The owner drains JSONL to stderr in motive_audio_state / audio_mix_stop:
 * event=motive_test_audio_trace, version=1, phase=enabled|blocks|summary.
 * blocks[].point is tone_schedule, source_pre_fader_pre_mute, or
 * mix_post_fader_post_mute_pre_clamp. All clocks are os_gettime_ns() nanoseconds.
 * pts_ns is unchanged OBS PTS; seen_ns is wake/callback entry; done_ns is only
 * the tone's return from obs_source_output_audio. observed_frame_offset counts
 * samples at that observation point (tone offset is its sample-clock position).
 * Tone deadline_ns is its publication deadline, schedule_lateness_ns is wake
 * minus that deadline, and lateness_ns remains wake minus PTS (normally negative
 * with lookahead). This keeps delivery scheduling distinct from sample time.
 * frames is per-channel. sum_squares / rms / peak are linear, channels_present
 * identifies valid channels; nonfinite_samples makes invalid data explicit.
 * source energy examines at most 8192 frames per callback; measured_frames and
 * metrics_complete disclose any larger block without extra unbounded work.
 * Output records can arrive in a different order from seen_ns: the tone record
 * is enqueued AFTER its synchronous source callback, so compare PTS/offsets.
 * Capture/measurement overhead can perturb timing; this is a localization aid,
 * not production timing evidence. Lost records never imply missing PCM.
 */
#define AUDIO_TRACE_CAPACITY 2048
#define AUDIO_TRACE_BATCH 128
#define AUDIO_TRACE_BUDGET 65536
typedef struct {
    uint64_t sequence,pts_ns,seen_ns,done_ns,observed_frame_offset,deadline_ns;
    double sum_squares[2],peak[2];
    uint32_t frames,measured_frames,nonfinite_samples;
    unsigned char point,channels_present,muted;
    char id[64];
} audio_trace_record;
_Static_assert(sizeof(audio_trace_record)<=192,"audio diagnostic ring memory bound");
static struct {
    atomic_flag lock;
    atomic_bool capturing;
    atomic_uint_fast64_t contention,overflow;
    bool initialized,enabled;
    uint64_t written,read,reported_contention,reported_overflow;
    bool reported_budget;
    audio_trace_record records[AUDIO_TRACE_CAPACITY];
} audio_trace={.lock=ATOMIC_FLAG_INIT};

static void audio_trace_push(audio_trace_record record) {
    if(!atomic_load_explicit(&audio_trace.capturing,memory_order_relaxed))return;
    if(atomic_flag_test_and_set_explicit(&audio_trace.lock,memory_order_acquire)) {
        atomic_fetch_add_explicit(&audio_trace.contention,1,memory_order_relaxed);return;
    }
    if(audio_trace.written>=AUDIO_TRACE_BUDGET) {
        atomic_store_explicit(&audio_trace.capturing,false,memory_order_relaxed);
    } else if(audio_trace.written-audio_trace.read>=AUDIO_TRACE_CAPACITY) {
        atomic_fetch_add_explicit(&audio_trace.overflow,1,memory_order_relaxed);
    } else {
        record.sequence=audio_trace.written+1;
        audio_trace.records[audio_trace.written++%AUDIO_TRACE_CAPACITY]=record;
        if(audio_trace.written==AUDIO_TRACE_BUDGET)
            atomic_store_explicit(&audio_trace.capturing,false,memory_order_relaxed);
    }
    atomic_flag_clear_explicit(&audio_trace.lock,memory_order_release);
}
static id audio_trace_number(double value) {return isfinite(value)?@(value):[NSNull null];}
static void audio_trace_log_owner(NSDictionary *event) {
    NSData *json=[NSJSONSerialization dataWithJSONObject:event options:0 error:nil];
    if(json) {
        NSMutableData *line=[json mutableCopy];[line appendBytes:"\n" length:1];
        // One stdio call keeps other libobs log writes out of the JSON line.
        fwrite(line.bytes,1,line.length,stderr);
    }
}
static void audio_trace_start_owner(void) {
    if(audio_trace.initialized)return;
    audio_trace.initialized=true;
    const char *setting=getenv("MOTIVE_TEST_AUDIO_TRACE");
    audio_trace.enabled=setting && !strcmp(setting,"1");
    if(!audio_trace.enabled)return;
    atomic_store_explicit(&audio_trace.capturing,true,memory_order_relaxed);
    @autoreleasepool {
        audio_trace_log_owner(@{@"event":@"motive_test_audio_trace",@"version":@1,@"phase":@"enabled",
            @"pid":@(getpid()),@"clock":@"os_gettime_ns",@"sample_rate":@48000,
            @"capacity":@(AUDIO_TRACE_CAPACITY),@"ring_bytes":@(sizeof(audio_trace.records)),
            @"record_budget":@(AUDIO_TRACE_BUDGET),@"pcm_logged":@NO});
    }
}
static void audio_trace_drain_owner(const char *reason,unsigned batches) {
    if(!audio_trace.enabled)return;
    // Only the core owner drains. Copy under the try-lock, then immediately
    // release it before Foundation allocation or stderr I/O.
    for(unsigned batch=0;batch<batches;batch++) {
        audio_trace_record records[AUDIO_TRACE_BATCH];size_t count=0;
        if(atomic_flag_test_and_set_explicit(&audio_trace.lock,memory_order_acquire))return;
        while(count<AUDIO_TRACE_BATCH && audio_trace.read<audio_trace.written)
            records[count++]=audio_trace.records[audio_trace.read++%AUDIO_TRACE_CAPACITY];
        uint64_t queued=audio_trace.written-audio_trace.read,written=audio_trace.written;
        atomic_flag_clear_explicit(&audio_trace.lock,memory_order_release);
        uint64_t contention=atomic_load_explicit(&audio_trace.contention,memory_order_relaxed);
        uint64_t overflow=atomic_load_explicit(&audio_trace.overflow,memory_order_relaxed);
        bool exhausted=written>=AUDIO_TRACE_BUDGET;
        if(!count && contention==audio_trace.reported_contention && overflow==audio_trace.reported_overflow &&
            exhausted==audio_trace.reported_budget)return;
        @autoreleasepool {
            NSMutableArray *blocks=[NSMutableArray arrayWithCapacity:count];
            for(size_t i=0;i<count;i++) {
                audio_trace_record *r=&records[i];
                NSString *point=r->point==0?@"tone_schedule":r->point==1?
                    @"source_pre_fader_pre_mute":@"mix_post_fader_post_mute_pre_clamp";
                NSMutableDictionary *block=[@{@"sequence":@(r->sequence),@"point":point,@"id":@(r->id),
                    @"pts_ns":@(r->pts_ns),@"seen_ns":@(r->seen_ns),@"frames":@(r->frames),
                    @"observed_frame_offset":@(r->observed_frame_offset),
                    @"muted":@((bool)r->muted),@"channels_present":@(r->channels_present),
                    @"nonfinite_samples":@(r->nonfinite_samples)} mutableCopy];
                if(r->point==0) {
                    block[@"done_ns"]=@(r->done_ns);
                    block[@"deadline_ns"]=@(r->deadline_ns);
                    block[@"schedule_lateness_ns"]=@((int64_t)r->seen_ns-(int64_t)r->deadline_ns);
                    block[@"lateness_ns"]=@((int64_t)r->seen_ns-(int64_t)r->pts_ns);
                } else {
                    block[@"measured_frames"]=@(r->measured_frames);
                    block[@"metrics_complete"]=@((bool)(r->measured_frames==r->frames && !r->nonfinite_samples));
                    NSMutableArray *energy=[NSMutableArray arrayWithCapacity:2];
                    NSMutableArray *rms=[NSMutableArray arrayWithCapacity:2];
                    NSMutableArray *peak=[NSMutableArray arrayWithCapacity:2];
                    for(unsigned c=0;c<2;c++) {
                        bool present=(r->channels_present&(1u<<c))!=0;
                        [energy addObject:present?audio_trace_number(r->sum_squares[c]):[NSNull null]];
                        [rms addObject:present && r->measured_frames?audio_trace_number(sqrt(r->sum_squares[c]/r->measured_frames)):[NSNull null]];
                        [peak addObject:present?audio_trace_number(r->peak[c]):[NSNull null]];
                    }
                    block[@"sum_squares"]=energy;block[@"rms"]=rms;block[@"peak"]=peak;
                }
                [blocks addObject:block];
            }
            audio_trace_log_owner(@{@"event":@"motive_test_audio_trace",@"version":@1,
                @"phase":count?@"blocks":@"summary",@"pid":@(getpid()),@"reason":@(reason),
                @"drained_ns":@(os_gettime_ns()),@"accepted_records":@(written),@"queued_records":@(queued),
                @"dropped_contention":@(contention),@"dropped_overflow":@(overflow),
                @"budget_exhausted":@(exhausted),@"blocks":blocks});
        }
        audio_trace.reported_contention=contention;audio_trace.reported_overflow=overflow;
        audio_trace.reported_budget=exhausted;
        if(!queued)return;
    }
}

typedef struct {
    obs_source_t *source;
    pthread_t thread;
    atomic_bool stop;
    char trace_id[64];
} tone_generator;
static void *tone_run(void *param) {
    tone_generator *tone=param;
    const uint64_t start=os_gettime_ns();uint64_t frames=0;
    const uint64_t lookahead_ns=20000000ULL;
    float samples[480];
    // A source fixture, not a mixer. Sample position determines phase and PTS;
    // scheduling never accumulates timestamps from MCP/UI or repeated sleeps.
    // This deterministic source can prepare future samples: publish 20 ms ahead
    // so the libobs 1024-frame reader has a full block despite scheduler jitter
    // and its alignment against 480-frame source packets. Initially publish only
    // 3 x 480 frames, then one block per 10 ms. PTS/phase remain unchanged;
    // libobs owns queuing, mixing and the output clock. No global buffering change.
    while(!atomic_load(&tone->stop)) {
        // Divide exact 480-frame blocks first, avoiding frames*1e9 overflow
        // after a few days of continuous capture.
        uint64_t now=os_gettime_ns();
        // Skip elapsed blocks after a scheduler stall/sleep instead of bursting
        // old samples into OBS. The sample clock/phase remain anchored to start.
        if(now>start+(frames/480)*10000000ULL+1000000000ULL)
            frames=((now-start)/10000000ULL)*480;
        uint64_t timestamp=start+(frames/480)*10000000ULL;
        uint64_t deadline=timestamp>start+lookahead_ns?timestamp-lookahead_ns:start;
        os_sleepto_ns(deadline);
        if(atomic_load(&tone->stop))break;
        bool tracing=atomic_load_explicit(&audio_trace.capturing,memory_order_relaxed);
        uint64_t wake_ns=tracing?os_gettime_ns():0;
        for(size_t i=0;i<480;i++) samples[i]=0.0630957344f*sinf((float)((frames+i)%48000)*2*M_PI*440/48000);
        struct obs_source_audio audio={.data={(const uint8_t *)samples,(const uint8_t *)samples},
            .frames=480,.speakers=SPEAKERS_STEREO,.format=AUDIO_FORMAT_FLOAT_PLANAR,
            .samples_per_sec=48000,.timestamp=timestamp};
        obs_source_output_audio(tone->source,&audio);
        if(tracing) {
            audio_trace_record record={.point=0,.pts_ns=timestamp,.seen_ns=wake_ns,
                .done_ns=os_gettime_ns(),.observed_frame_offset=frames,.frames=480,
                .deadline_ns=deadline};
            memcpy(record.id,tone->trace_id,sizeof(record.id));audio_trace_push(record);
        }
        frames+=480;
    }
    return NULL;
}
static const char *tone_name(void *unused) {(void)unused;return "Motive controlled 440 Hz tone";}
static void *tone_create(obs_data_t *settings,obs_source_t *source) {
    (void)settings;tone_generator *tone=calloc(1,sizeof(*tone));tone->source=source;
    snprintf(tone->trace_id,sizeof(tone->trace_id),"%s",obs_source_get_name(source));
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
    unsigned kind;
    pid_t application_pid;
    uint64_t identity_checked_ns;
    unsigned identity_instances;
    pid_t identity_observed_pid;
    bool identity_terminated,identity_pinned_present,identity_pinned_terminated,identity_bundle_matches;
    const char *identity_reason;
    CGDirectDisplayID system_display;
    atomic_bool system_stopped;
    obs_source_t *source;
    obs_volmeter_t *meter;
    audio_metrics metrics;
    uint64_t instance,created_ns;
    unsigned slot;
    int fault;
    bool disconnected;
};
struct audio_mix_meter { audio_metrics metrics; };

#include "system-audio.inc"

static void audio_metrics_init(audio_metrics *m) { pthread_mutex_init(&m->lock,NULL); }
static void audio_flow(void *param,obs_source_t *source,const struct audio_data *data,bool muted) {
    if(!data || !data->frames)return;
    (void)source;audio_input *input=param;audio_metrics *m=&input->metrics;
    bool tracing=atomic_load_explicit(&audio_trace.capturing,memory_order_relaxed);
    uint64_t seen=tracing?os_gettime_ns():0,offset;
    char trace_id[64]={0};
    pthread_mutex_lock(&m->lock);
    offset=m->frames;
    if(tracing)memcpy(trace_id,input->id,sizeof(trace_id));
    m->frames+=data->frames;m->seen_ns=tracing?seen:os_gettime_ns();m->timestamp=data->timestamp;
    pthread_mutex_unlock(&m->lock);
    if(tracing) {
        audio_trace_record record={.point=1,.pts_ns=data->timestamp,.seen_ns=seen,
            .observed_frame_offset=offset,.frames=data->frames,.muted=muted,
            .measured_frames=data->frames<8192?data->frames:8192};
        memcpy(record.id,trace_id,sizeof(record.id));
        for(unsigned c=0;c<2;c++) if(data->data[c]) {
            record.channels_present|=1u<<c;
            const float *samples=(const float *)data->data[c];
            for(uint32_t i=0;i<record.measured_frames;i++) {
                double value=samples[i];
                if(!isfinite(value)) {record.nonfinite_samples++;continue;}
                record.sum_squares[c]+=value*value;
                record.peak[c]=fmax(record.peak[c],fabs(value));
            }
        }
        audio_trace_push(record);
    }
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
    bool tracing=atomic_load_explicit(&audio_trace.capturing,memory_order_relaxed);
    audio_trace_record record={.point=2,.pts_ns=data->timestamp,.frames=data->frames,
        .measured_frames=data->frames,.seen_ns=tracing?os_gettime_ns():0};
    float peaks[2]={0},rms[2]={0};bool clipped=false;
    for (size_t c=0;c<2;c++) if (data->data[c]) {
        const float *samples=(const float *)data->data[c];double sum=0;
        for (size_t i=0;i<data->frames;i++) {
            float v=samples[i];peaks[c]=fmaxf(peaks[c],fabsf(v));sum+=(double)v*v;
            if(tracing && !isfinite(v))record.nonfinite_samples++;
        }
        rms[c]=data->frames ? sqrt(sum/data->frames):0;
        clipped |= peaks[c]>=1.0f;
        if(tracing) {record.channels_present|=1u<<c;record.sum_squares[c]=sum;record.peak[c]=peaks[c];}
    }
    pthread_mutex_lock(&m->lock);
    record.observed_frame_offset=m->frames;
    m->frames+=data->frames;m->seen_ns=os_gettime_ns();m->timestamp=data->timestamp;
    memcpy(m->peak,peaks,sizeof(peaks));memcpy(m->rms,rms,sizeof(rms));
    if (clipped) m->clipped_blocks++;
    pthread_mutex_unlock(&m->lock);
    if(tracing) {memcpy(record.id,"mix-0",6);audio_trace_push(record);}
}
static void audio_mix_start(motive_engine *e) {
    audio_trace_start_owner();
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
    if (a->source && audio_is_system(a))
        signal_handler_disconnect(obs_source_get_signal_handler(a->source),"update_properties",system_audio_stopped,a);
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
    audio_trace_drain_owner("mixer_stop",AUDIO_TRACE_CAPACITY/AUDIO_TRACE_BATCH);
}
static bool audio_attach(motive_engine *e,audio_input *a,const char *tone_path,float gain,bool muted) {
    (void)tone_path;
    obs_data_t *settings=obs_data_create();
    if (a->kind==0) {
        a->source=obs_source_create_private("motive_audio_tone",a->id,settings);
    } else if (a->kind==1) {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) {
            obs_data_release(settings);a->fault=2;snprintf(e->error,sizeof(e->error),"MICROPHONE_PERMISSION_DENIED");return false;
        }
        if (!audio_available(a->device)) {
            obs_data_release(settings);a->fault=1;snprintf(e->error,sizeof(e->error),"DEVICE_UNAVAILABLE");return false;
        }
        obs_data_set_string(settings,"device_id",a->device);
        a->source=obs_source_create_private("coreaudio_input_capture",a->id,settings);
    } else {
        int fault=system_audio_resolve(a);
        if(fault) {obs_data_release(settings);a->fault=fault;snprintf(e->error,sizeof(e->error),"%s",audio_fault_name(fault));return false;}
        obs_data_set_int(settings,"type",a->kind==2?1:0);
        if(a->kind==2)obs_data_set_string(settings,"application",a->device);
        atomic_store(&a->system_stopped,false);
        a->source=obs_source_create_private("sck_audio_capture",a->id,settings);
        if(a->source) {
            signal_handler_connect(obs_source_get_signal_handler(a->source),"update_properties",system_audio_stopped,a);
            // Close target exit/relaunch races around the official plugin's
            // own enumeration. Never silently accept a different process.
            fault=system_audio_target_health(a);
            if(fault) {obs_data_release(settings);audio_detach(a);a->fault=fault;snprintf(e->error,sizeof(e->error),"%s",audio_fault_name(fault));return false;}
        }
    }
    obs_data_release(settings);
    // OBS preserves source settings even when the plugin's create returned
    // NULL. A non-NULL obs_source_t alone is not proof of successful creation.
    if (!a->source || obs_obj_invalid(a->source)) {audio_detach(a);a->fault=4;snprintf(e->error,sizeof(e->error),"AUDIO_CREATE_FAILED");return false;}
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
bool motive_audio_add_target(motive_engine *e,const char *id,unsigned kind,const char *device,float gain,bool muted) {
    if(!audio_target_valid(kind,device) || !id || !*id || strlen(id)>=64 || !isfinite(gain) || gain < -60 || gain > 24) {
        snprintf(e->error,sizeof(e->error),"INVALID_AUDIO_TARGET");return false;
    }
    if (audio_find(e,id)) {snprintf(e->error,sizeof(e->error),"AUDIO_ID_EXISTS");return false;}
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i]) {
        audio_input *existing=e->audio_inputs[i];
        if(existing->kind==kind && !strcmp(existing->device,device)) {
            snprintf(e->error,sizeof(e->error),"AUDIO_DEVICE_DUPLICATE");return false;
        }
        if(kind>=2 && audio_is_system(existing) && (kind==3 || existing->kind==3)) {
            snprintf(e->error,sizeof(e->error),"AUDIO_CAPTURE_OVERLAP");return false;
        }
    }
    size_t slot=0;while(slot<8 && e->audio_inputs[slot]) slot++;
    if (slot==8) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_LIMIT");return false;}
    audio_input *a=calloc(1,sizeof(*a));a->slot=(unsigned)slot;a->kind=kind;
    atomic_init(&a->system_stopped,false);
    snprintf(a->id,sizeof(a->id),"%s",id);snprintf(a->device,sizeof(a->device),"%s",device);
    audio_metrics_init(&a->metrics);
    if (!audio_attach(e,a,"",gain,muted)) {audio_release(a);return false;}
    e->audio_inputs[slot]=a;return true;
}
bool motive_audio_add(motive_engine *e,const char *id,const char *device,const char *tone_path,float gain,bool muted) {
    (void)tone_path;
    return motive_audio_add_target(e,id,device && !strcmp(device,"tone")?0:1,device,gain,muted);
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
bool motive_audio_restore_missing_target(motive_engine *e,const char *id,unsigned kind,const char *device) {
    if(!audio_target_valid(kind,device) || !id || !*id || strlen(id)>=64)return false;
    if(audio_find(e,id))return false;
    for(size_t i=0;i<8;i++)if(e->audio_inputs[i]) {
        audio_input *other=e->audio_inputs[i];
        if((other->kind==kind && !strcmp(other->device,device)) ||
           (kind>=2 && audio_is_system(other) && (kind==3 || other->kind==3)))return false;
    }
    size_t slot=0;while(slot<8 && e->audio_inputs[slot])slot++;
    if(slot==8)return false;
    audio_input *a=calloc(1,sizeof(*a));a->slot=(unsigned)slot;a->kind=kind;
    atomic_init(&a->system_stopped,false);
    snprintf(a->id,sizeof(a->id),"%s",id);snprintf(a->device,sizeof(a->device),"%s",device);
    audio_metrics_init(&a->metrics);
    a->fault=kind>=2?8:1;
    for(int fault=1;fault<=14;fault++)if(!strcmp(e->error,audio_fault_name(fault))) {a->fault=fault;break;}
    e->audio_inputs[slot]=a;return true;
}
bool motive_audio_restore_missing(motive_engine *e,const char *id,const char *device) {
    return motive_audio_restore_missing_target(e,id,device && !strcmp(device,"tone")?0:1,device);
}
bool motive_audio_rename_id(motive_engine *e,const char *old_id,const char *new_id) {
    // Restore uses private "restore-N" IDs before assigning canonical "audio-N"
    // IDs. Reject malformed/truncatable names before touching a retained capture.
    // Rust's CString bridge separately rejects embedded NUL bytes.
    if(!old_id || !*old_id || strlen(old_id)>=64 || !new_id || !*new_id || strlen(new_id)>=64) {
        snprintf(e->error,sizeof(e->error),"INVALID_AUDIO_ID");return false;
    }
    for(const unsigned char *p=(const unsigned char *)new_id;*p;p++) {
        if(!((*p>='a' && *p<='z') || (*p>='A' && *p<='Z') || (*p>='0' && *p<='9') || *p=='-')) {
            snprintf(e->error,sizeof(e->error),"INVALID_AUDIO_ID");return false;
        }
    }
    audio_input *a=audio_find(e,old_id);
    if(!a) {snprintf(e->error,sizeof(e->error),"AUDIO_INPUT_NOT_FOUND");return false;}
    if(audio_find(e,new_id)) {snprintf(e->error,sizeof(e->error),"AUDIO_ID_EXISTS");return false;}
    pthread_mutex_lock(&a->metrics.lock);
    snprintf(a->id,sizeof(a->id),"%s",new_id);
    pthread_mutex_unlock(&a->metrics.lock);return true;
}
static int audio_health(audio_input *a) {
    if (a->fault) return a->fault;
    if (a->disconnected) return 5;
    if(audio_is_system(a)) {
        int fault=system_audio_target_health(a);
        if(fault)return fault;
    } else if (a->kind==1) {
        if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) return 2;
        if (!audio_available(a->device)) return 1;
    }
    pthread_mutex_lock(&a->metrics.lock);uint64_t seen=a->metrics.seen_ns;pthread_mutex_unlock(&a->metrics.lock);
    uint64_t limit=audio_is_system(a)?1000000000ULL:3000000000ULL;
    return seen && os_gettime_ns()-seen<limit ? 0:audio_is_system(a)?15:3;
}
void motive_poll_audio(motive_engine *e) {
    for(size_t i=0;i<8;i++) if(e->audio_inputs[i]) {
        audio_input *a=e->audio_inputs[i];if(a->disconnected || a->fault)continue;
        int health=audio_health(a);
        // SCK may stop delivering buffers while an application is silent.
        // No packet is not a measured zero and is not proof of stream failure.
        if(health==15)continue;
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
    // Copy under the callback lock; Foundation allocation/formatting stays on
    // the owner AFTER unlocking, never delaying the media callback on JSON work.
    pthread_mutex_lock(&m->lock);
    uint64_t frames=m->frames,seen=m->seen_ns,timestamp=m->timestamp,clipped=m->clipped_blocks;
    float peak[2],rms[2],input_peak[2];
    memcpy(peak,m->peak,sizeof(peak));memcpy(rms,m->rms,sizeof(rms));memcpy(input_peak,m->input_peak,sizeof(input_peak));
    pthread_mutex_unlock(&m->lock);
    uint64_t age=seen ? (os_gettime_ns()-seen)/1000000:0;
    bool stale=!seen || age>=1000;
    float p0=stale?0:peak[0],p1=stale?0:peak[1];
    float r0=stale?0:rms[0],r1=stale?0:rms[1];
    return @{@"frames":@(frames),@"timestamp_ns":@(timestamp),@"age_ms":seen?@(age):[NSNull null],
        @"stale":@(stale),@"peak_dbfs":@[audio_db(p0),audio_db(p1)],@"rms_dbfs":@[audio_db(r0),audio_db(r1)],
        @"input_peak_dbfs":@[audio_db(stale?0:input_peak[0]),audio_db(stale?0:input_peak[1])],
        @"clipped_blocks":@(clipped)};
}
char *motive_audio_state(motive_engine *e) {
    audio_trace_drain_owner("mixer_query",2);
    NSMutableArray *inputs=[NSMutableArray array];
    for (size_t i=0;i<8;i++) if (e->audio_inputs[i]) {
        audio_input *a=e->audio_inputs[i];int health=audio_health(a);
        [inputs addObject:@{@"id":@(a->id),@"instance_id":@(a->instance),@"issue":health?@(audio_fault_name(health)):[NSNull null],
            @"phase":health==0?@"ready":health==3?@"warming":health==5?@"disconnected":health==15?@"awaiting_audio":@"failed",
            @"levels":audio_metrics_json(&a->metrics),
            @"application_identity":a->kind==2?@{
                @"checked_ns":@(a->identity_checked_ns),@"expected_pid":@(a->application_pid),
                @"registered_instances":@(a->identity_instances),@"observed_pid":@(a->identity_observed_pid),
                @"registered_terminated":@(a->identity_terminated),
                @"pinned_process_present":@(a->identity_pinned_present),
                @"pinned_process_terminated":@(a->identity_pinned_terminated),
                @"pinned_bundle_matches":@(a->identity_bundle_matches),
                @"reason":a->identity_reason?@(a->identity_reason):@"not_checked"
            }:(id)NSNull.null}];
    }
    NSDictionary *state=@{@"available":@YES,@"inputs":inputs,@"instances_created":@(e->audio_instances),
        @"mix":e->mix_meter?audio_metrics_json(&e->mix_meter->metrics):@{}};
    NSData *json=[NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}
/* Compatibility stats read the global mix. The legacy selector's device is
 * owned by the same registry; there is never a second physical capture. */
int motive_audio_health(motive_engine *e) {
    for(size_t i=0;i<8;i++) if(e->audio_inputs[i] && !audio_is_system(e->audio_inputs[i]) && !strcmp(e->audio_inputs[i]->device,e->audio_id)) return audio_health(e->audio_inputs[i]);
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
