#include <obs.h>
#include <graphics/vec4.h>
#include <pthread.h>
#include <stdatomic.h>
#include <math.h>
#include <unistd.h>
#include <util/platform.h>
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <VideoToolbox/VideoToolbox.h>

/* All functions except the frame callback run on the main/GPUI thread.
 * OBS owns render/audio/output threads. No GPUI object crosses that boundary. */
typedef struct visual_source visual_source;
typedef struct visual_scene visual_scene;
typedef struct {
    pthread_mutex_t lock;
    uint8_t *pixels;
    uint32_t width, height;
    char audio_id[512];
    visual_source *visuals[16];visual_scene *scenes[8];size_t visual_count,scene_count;
    atomic_uint_fast64_t audio_seen_ns, audio_frames;
    atomic_uint audio_peak;
    uint64_t sequence, timestamp;
    atomic_uint_fast64_t busy_drops;
    obs_source_t *audio;
    atomic_uint_fast64_t preview_copies;
    obs_output_t *output;
    obs_encoder_t *video_encoder, *audio_encoder;
    atomic_int output_code;
    atomic_bool output_stopped;
    bool vt_loaded, selected_hardware;
    char vt_h264_id[512], selected_encoder[512], fallback_reason[128], vt_unavailable_reason[128];
    char *encoder_inventory;
    char base[4096], error[512];
} motive_engine;

typedef struct { double elapsed; bool overlay; atomic_uint color; } pattern_state;
static void pattern_update(void *data,obs_data_t *settings) { pattern_state *p=data;atomic_store(&p->color,(unsigned)obs_data_get_int(settings,"color")); }
static const char *pattern_name(void *unused) { (void)unused; return "Motive controlled pattern"; }
static void *pattern_create(obs_data_t *settings, obs_source_t *source) {
    (void)source;
    pattern_state *p = calloc(1, sizeof(*p));
    p->overlay = obs_data_get_bool(settings, "overlay");
    pattern_update(p,settings);
    return p;
}
static void pattern_destroy(void *data) { free(data); }
static uint32_t pattern_width(void *data) { return ((pattern_state *)data)->overlay ? 320 : 960; }
static uint32_t pattern_height(void *data) { return ((pattern_state *)data)->overlay ? 72 : 540; }
static void pattern_tick(void *data, float seconds) { ((pattern_state *)data)->elapsed += seconds; }
static void rect(float x, float y, uint32_t w, uint32_t h, float r, float g, float b) {
    gs_effect_t *effect = obs_get_base_effect(OBS_EFFECT_SOLID);
    struct vec4 color; vec4_set(&color,r,g,b,1);
    gs_effect_set_vec4(gs_effect_get_param_by_name(effect, "color"), &color);
    gs_matrix_push();
    gs_matrix_translate3f(x, y, 0);
    while (gs_effect_loop(effect, "Solid")) gs_draw_sprite(NULL, 0, w, h);
    gs_matrix_pop();
}
static void pattern_render(void *data, gs_effect_t *unused) {
    (void)unused;
    pattern_state *p = data;
    if (p->overlay) {
        unsigned color=atomic_load(&p->color);float r=((color>>16)&255)/255.f,g=((color>>8)&255)/255.f,b=(color&255)/255.f;
        rect(0,0,320,72,0.035,0.09,0.12);
        rect(0,0,6,72,r,g,b);
        rect(24,18,180,10,0.85,0.94,0.98);
        rect(24,42,110,6,0.33,0.45,0.52);
        rect(248 + 20*sin(p->elapsed*2),24,24,24,r,g,b);
    } else {
        rect(0,0,960,540,0.055,0.085,0.14);
        rect(0,0,320,150,0.13,0.61,0.53);
        rect(320,0,320,150,0.23,0.36,0.71);
        rect(640,0,320,150,0.78,0.34,0.24);
        rect(40 + fmod(p->elapsed*110,800),230,80,80,0.94,0.95,0.96);
    }
}
static struct obs_source_info pattern_info = {
    .id="motive_pattern", .type=OBS_SOURCE_TYPE_INPUT,
    .output_flags=OBS_SOURCE_VIDEO | OBS_SOURCE_CUSTOM_DRAW,
    .get_name=pattern_name, .create=pattern_create, .destroy=pattern_destroy,
    .get_width=pattern_width, .get_height=pattern_height,
    .video_tick=pattern_tick, .video_render=pattern_render,.update=pattern_update,
};

static void receive_frame(void *param, struct video_data *frame) {
    motive_engine *e = param;
    if (pthread_mutex_trylock(&e->lock)) { atomic_fetch_add(&e->busy_drops,1); return; }
    for (uint32_t y=0; y<e->height; y++)
        memcpy(e->pixels + y*e->width*4, frame->data[0]+y*frame->linesize[0], e->width*4);
    e->timestamp=frame->timestamp; e->sequence++;
    pthread_mutex_unlock(&e->lock);
}
static void connect_preview(motive_engine *e) {
    struct video_scale_info scale = {.format=VIDEO_FORMAT_BGRA, .width=e->width,
        .height=e->height, .range=VIDEO_RANGE_FULL, .colorspace=VIDEO_CS_709};
    obs_add_raw_video_callback(&scale, receive_frame, e);
}
static bool load_module(motive_engine *e, const char *name) {
    char binary[8192], data[8192]; obs_module_t *module = NULL;
    snprintf(binary,sizeof(binary),"%s/PlugIns/%s.plugin/Contents/MacOS/%s",e->base,name,name);
    snprintf(data,sizeof(data),"%s/PlugIns/%s.plugin/Contents/Resources",e->base,name);
    int code=obs_open_module(&module,binary,data);
    if (code || !obs_init_module(module)) {
        snprintf(e->error,sizeof(e->error),"No se pudo cargar %s (%d)",name,code); return false;
    }
    return true;
}
static int reset_video(motive_engine *e) {
    char graphics[8192];
    snprintf(graphics,sizeof(graphics),"%s/Frameworks/libobs-metal.dylib",e->base);
    struct obs_video_info v = {.graphics_module=graphics,.fps_num=30,.fps_den=1,
        .base_width=e->width,.base_height=e->height,.output_width=e->width,.output_height=e->height,
        .output_format=VIDEO_FORMAT_NV12,.gpu_conversion=true,.colorspace=VIDEO_CS_709,
        .range=VIDEO_RANGE_PARTIAL,.scale_type=OBS_SCALE_BICUBIC};
    return obs_reset_video(&v);
}
static struct obs_source_info watch_info;
static void discover_encoders(motive_engine *e);
void motive_destroy(motive_engine *e);
motive_engine *motive_create(const char *base) {
    motive_engine *e=calloc(1,sizeof(*e));
    pthread_mutex_init(&e->lock,NULL); e->width=960; e->height=540;
    snprintf(e->base,sizeof(e->base),"%s",base);
    [NSApplication sharedApplication];
    if (!obs_startup("en-US",NULL,NULL)) { snprintf(e->error,sizeof(e->error),"obs_startup falló"); return e; }
    char resources[8192];
    snprintf(resources,sizeof(resources),"%s/Frameworks/libobs.framework/Resources",base);
    obs_add_data_path(resources);
    int code=reset_video(e);
    if (code) { snprintf(e->error,sizeof(e->error),"obs_reset_video falló: %d",code); return e; }
    struct obs_audio_info audio={.samples_per_sec=48000,.speakers=SPEAKERS_STEREO};
    if (!obs_reset_audio(&audio)) { snprintf(e->error,sizeof(e->error),"obs_reset_audio falló"); return e; }
    const char *modules[]={"obs-x264","obs-ffmpeg","obs-outputs","mac-capture","mac-avcapture","obs-transitions"};
    for (size_t i=0;i<sizeof(modules)/sizeof(modules[0]);i++) if (!load_module(e,modules[i])) return e;
    // Optional: an unavailable VT module must not prevent x264 recording.
    const char *disable_vt=getenv("MOTIVE_DISABLE_VIDEOTOOLBOX");
    if (disable_vt && !strcmp(disable_vt,"1")) {
        snprintf(e->vt_unavailable_reason,sizeof(e->vt_unavailable_reason),"VIDEOTOOLBOX_DISABLED");
    } else {
        e->vt_loaded=load_module(e,"mac-videotoolbox");
        if (!e->vt_loaded) {
            snprintf(e->vt_unavailable_reason,sizeof(e->vt_unavailable_reason),"VIDEOTOOLBOX_MODULE_UNAVAILABLE");
            e->error[0]=0;
        }
    }
    obs_post_load_modules();
    discover_encoders(e);
    obs_register_source(&pattern_info);
    obs_register_source(&watch_info);
    e->pixels=calloc(e->width*e->height,4);
    connect_preview(e);
    return e;
}
const char *motive_error(motive_engine *e) { return e->error; }
const char *motive_version(void) { return obs_get_version_string(); }
uint64_t motive_frame(motive_engine *e, uint8_t *dest, size_t len, uint64_t *timestamp) {
    pthread_mutex_lock(&e->lock);
    uint64_t seq=e->sequence;
    if (len>=e->width*e->height*4 && e->pixels) {memcpy(dest,e->pixels,e->width*e->height*4);atomic_fetch_add(&e->preview_copies,1);}
    *timestamp=e->timestamp;
    pthread_mutex_unlock(&e->lock); return seq;
}
uint64_t motive_frame_sequence(motive_engine *e) {pthread_mutex_lock(&e->lock);uint64_t seq=e->sequence;pthread_mutex_unlock(&e->lock);return seq;}
uint64_t motive_preview_copies(motive_engine *e) {return atomic_load(&e->preview_copies);}
uint32_t motive_total_frames(void) { return obs_get_total_frames(); }
uint32_t motive_lagged_frames(void) { return obs_get_lagged_frames(); }
uint64_t motive_busy_drops(motive_engine *e) { return atomic_load(&e->busy_drops); }

static void output_stopped(void *data,calldata_t *cd);
static void release_output(motive_engine *e) {
    if (e->output) { signal_handler_disconnect(obs_output_get_signal_handler(e->output),"stop",output_stopped,e); obs_output_release(e->output); e->output=NULL; }
    if (e->video_encoder) { obs_encoder_release(e->video_encoder); e->video_encoder=NULL; }
    if (e->audio_encoder) { obs_encoder_release(e->audio_encoder); e->audio_encoder=NULL; }
}
static void output_stopped(void *data, calldata_t *cd) {
    motive_engine *e=data;
    atomic_store(&e->output_code,(int)calldata_int(cd,"code"));
    atomic_store(&e->output_stopped,true);
}
int motive_output_state(motive_engine *e) {
    if (!e->output) return 0;
    if (atomic_load(&e->output_stopped)) return obs_output_active(e->output) ? 2:0;
    return obs_output_active(e->output) ? 1 : 2;
}
int motive_output_code(motive_engine *e) { return atomic_load(&e->output_code); }
uint64_t motive_output_bytes(motive_engine *e) { return e->output ? obs_output_get_total_bytes(e->output) : 0; }
uint32_t motive_output_frames(motive_engine *e) { return e->output ? obs_output_get_total_frames(e->output) : 0; }
int motive_output_drops(motive_engine *e) { return e->output ? obs_output_get_frames_dropped(e->output) : 0; }
#include "encoding.inc"
bool motive_start_output(motive_engine *e,const char *path,bool local_stream,const char *policy) {
    e->error[0]=0;
    if (motive_output_state(e)) { snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY"); return false; }
    if (strcmp(policy,"auto") && strcmp(policy,"videotoolbox") && strcmp(policy,"x264")) {
        snprintf(e->error,sizeof(e->error),"INVALID_ENCODER"); return false;
    }
    release_output(e);
    e->selected_encoder[0]=0;e->fallback_reason[0]=0;e->selected_hardware=false;
    if (!local_stream) return start_recording(e,path,policy);
    obs_data_t *settings=obs_data_create();
    if (local_stream) {
        // Fixed loopback destination. No public destinations or keys in this prototype.
        obs_data_set_string(settings,"url","udp://127.0.0.1:19350?pkt_size=1316");
        obs_data_set_string(settings,"format_name","mpegts");
        obs_data_set_string(settings,"video_encoder","libx264");
        obs_data_set_string(settings,"audio_encoder","aac");
        obs_data_set_string(settings,"video_settings","preset=ultrafast tune=zerolatency");
        obs_data_set_int(settings,"video_bitrate",2500);
        obs_data_set_int(settings,"audio_bitrate",160);
        obs_data_set_int(settings,"gop_size",60);
        e->output=obs_output_create("ffmpeg_output","Local MPEG-TS",settings,NULL);
        if (e->output) {
            obs_output_set_media(e->output,obs_get_video(),obs_get_audio());
            obs_output_set_mixers(e->output,1); // Bit mask: include audio mix 0.
        }
    }
    obs_data_release(settings);
    if (!e->output) { snprintf(e->error,sizeof(e->error),"OUTPUT_UNAVAILABLE"); return false; }
    atomic_store(&e->output_stopped,false); atomic_store(&e->output_code,0);
    signal_handler_connect(obs_output_get_signal_handler(e->output),"stop",output_stopped,e);
    if (!obs_output_start(e->output)) {
        const char *reason=obs_output_get_last_error(e->output);
        snprintf(e->error,sizeof(e->error),"OUTPUT_START_FAILED: %.440s",reason ? reason : "sin detalle");
        release_output(e); atomic_store(&e->output_stopped,true); return false;
    }
    snprintf(e->selected_encoder,sizeof(e->selected_encoder),"libx264 (loopback)");
    return true;
}
void motive_stop_output(motive_engine *e) { if (e->output && !atomic_load(&e->output_stopped)) obs_output_stop(e->output); }
bool motive_variant(motive_engine *e,bool vertical) {
    if (motive_output_state(e)) { snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY"); return false; }
    if (e->width==(vertical ? 540u:960u) && e->height==(vertical ? 960u:540u)) {
        return true;
    }
    release_output(e);
    obs_remove_raw_video_callback(receive_frame,e);
    uint32_t oldw=e->width,oldh=e->height;
    e->width=vertical ? 540:960; e->height=vertical ? 960:540;
    int code=reset_video(e);
    if (code) {
        e->width=oldw;e->height=oldh; connect_preview(e);
        snprintf(e->error,sizeof(e->error),"VIDEO_RESET_FAILED: %d",code); return false;
    }
    // Equal pixel count for the two supported variants; the callback is disconnected.
    memset(e->pixels,0,e->width*e->height*4); e->sequence=0;
    connect_preview(e); return true;
}
// Inventory only: no capture starts until a concrete source is selected.
static NSArray *window_inventory(void) {
    NSMutableArray *items=[NSMutableArray array];
    NSArray *list=CFBridgingRelease(CGWindowListCopyWindowInfo(kCGWindowListOptionAll|kCGWindowListExcludeDesktopElements,kCGNullWindowID));
    for (NSDictionary *w in list) {
        NSString *title=w[(id)kCGWindowName], *owner=w[(id)kCGWindowOwnerName];
        NSNumber *number=w[(id)kCGWindowNumber], *pid=w[(id)kCGWindowOwnerPID];
        if ([w[(id)kCGWindowLayer] intValue]!=0 || !title.length || !number || !pid) continue;
        bool test=[pid intValue]==getpid() && [title isEqualToString:@"Motive — Fuente controlada"];
        // Do not offer the studio itself (recursive capture).
        if ([pid intValue]==getpid() && !test) continue;
        NSRunningApplication *app=[NSRunningApplication runningApplicationWithProcessIdentifier:pid.intValue];
        // Hide WindowManager surfaces, status agents and other accessory overlays.
        if (!app || app.activationPolicy!=NSApplicationActivationPolicyRegular) continue;
        [items addObject:@{@"id":number,@"pid":pid,@"name":title,@"app":owner ?: @"",@"bundle_id":app.bundleIdentifier ?: @"",@"test":@(test)}];
    }
    return [items sortedArrayUsingDescriptors:@[
        [NSSortDescriptor sortDescriptorWithKey:@"app" ascending:YES selector:@selector(localizedCaseInsensitiveCompare:)],
        [NSSortDescriptor sortDescriptorWithKey:@"name" ascending:YES selector:@selector(localizedCaseInsensitiveCompare:)],
        [NSSortDescriptor sortDescriptorWithKey:@"id" ascending:YES]]];
}
static NSDictionary *find_window(uint32_t id) {
    for (NSDictionary *w in window_inventory()) if ([w[@"id"] unsignedIntValue]==id) return w;
    return nil;
}
static NSArray *audio_inventory(void) {
    NSMutableArray *audio=[NSMutableArray array];
    obs_properties_t *props=obs_get_source_properties("coreaudio_input_capture");
    obs_property_t *p=props ? obs_properties_get(props,"device_id") : NULL;
    if (p) for (size_t i=0;i<obs_property_list_item_count(p);i++) {
        const char *id=obs_property_list_item_string(p,i), *name=obs_property_list_item_name(p,i);
        // Pin a physical UID: the system default can silently switch devices.
        if (id && name && strcmp(id,"default") && !obs_property_list_item_disabled(p,i))
            [audio addObject:@{@"id":@(id),@"name":@(name)}];
    }
    if (props) obs_properties_destroy(props);
    return audio;
}
static bool audio_available(const char *id) {
    for (NSDictionary *a in audio_inventory()) if ([a[@"id"] isEqualToString:@(id)]) return true;
    return false;
}
static NSArray *camera_devices(void) {
    return [AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:@[
        AVCaptureDeviceTypeBuiltInWideAngleCamera, AVCaptureDeviceTypeExternal,
        AVCaptureDeviceTypeContinuityCamera, AVCaptureDeviceTypeDeskViewCamera]
        mediaType:AVMediaTypeVideo position:AVCaptureDevicePositionUnspecified].devices;
}
static AVCaptureDevice *find_camera(const char *id) {
    for (AVCaptureDevice *d in camera_devices()) if ([d.uniqueID isEqualToString:@(id)] && d.connected) return d;
    return nil;
}
static NSString *permission_status(AVMediaType type) {
    switch ([AVCaptureDevice authorizationStatusForMediaType:type]) {
        case AVAuthorizationStatusAuthorized: return @"authorized";
        case AVAuthorizationStatusDenied: return @"denied";
        case AVAuthorizationStatusRestricted: return @"restricted";
        default: return @"not_determined";
    }
}
char *motive_devices(void) {
    NSMutableArray *cameras=[NSMutableArray array];
    for (AVCaptureDevice *d in camera_devices()) if (d.connected)
        [cameras addObject:@{@"id":d.uniqueID,@"name":d.localizedName}];
    NSDictionary *object=@{@"windows":window_inventory(),@"audio":audio_inventory(),@"cameras":cameras,
        @"screen_permission":@(CGPreflightScreenCaptureAccess()),
        @"microphone_permission":@([permission_status(AVMediaTypeAudio) isEqualToString:@"authorized"]),
        @"camera_permission":@([permission_status(AVMediaTypeVideo) isEqualToString:@"authorized"]),
        @"microphone_authorization":permission_status(AVMediaTypeAudio),@"camera_authorization":permission_status(AVMediaTypeVideo)};
    NSData *json=[NSJSONSerialization dataWithJSONObject:object options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}
void motive_free(char *value) { free(value); }
#include "graph.inc"
void motive_request_permission(int kind) {
    if (kind==0) CGRequestScreenCaptureAccess();
    else [AVCaptureDevice requestAccessForMediaType:kind==1 ? AVMediaTypeAudio:AVMediaTypeVideo completionHandler:^(BOOL granted) { (void)granted; }];
}
void motive_close_test_window(void) {
    for (NSWindow *w in NSApp.windows) if ([w.title isEqualToString:@"Motive — Fuente controlada"]) [w performClose:nil];
}
static void receive_audio(void *param,obs_source_t *source,const struct audio_data *data,bool muted) {
    (void)source; motive_engine *e=param; float peak=0;
    // libobs supplies resampled planar float in its configured stereo format.
    for (size_t c=0;c<2;c++) if (data->data[c]) {
        const float *samples=(const float *)data->data[c];
        for (size_t i=0;i<data->frames;i++) peak=fmaxf(peak,fabsf(samples[i]));
    }
    atomic_store(&e->audio_peak,muted ? 0:(unsigned)(fminf(peak,1)*1000000));
    atomic_fetch_add(&e->audio_frames,data->frames);
    atomic_store(&e->audio_seen_ns,os_gettime_ns());
}
int motive_audio_health(motive_engine *e) {
    if (!e->audio || !strcmp(e->audio_id,"tone")) return 0;
    if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) return 2;
    if (!audio_available(e->audio_id)) return 1;
    uint64_t seen=atomic_load(&e->audio_seen_ns);
    return seen && os_gettime_ns()-seen<3000000000ULL ? 0:3;
}
uint64_t motive_audio_frames(motive_engine *e) { return atomic_load(&e->audio_frames); }
float motive_audio_peak(motive_engine *e) {
    uint64_t seen=atomic_load(&e->audio_seen_ns);
    return seen && os_gettime_ns()-seen<1000000000ULL ? atomic_load(&e->audio_peak)/1000000.0f:0;
}
bool motive_audio(motive_engine *e,const char *id,const char *tone_path) {
    obs_source_t *source=NULL;
    if (strcmp(id,"none")) {
        obs_data_t *settings=obs_data_create();
        if (!strcmp(id,"tone")) {
            obs_data_set_string(settings,"local_file",tone_path);
            obs_data_set_bool(settings,"is_local_file",true); obs_data_set_bool(settings,"looping",true);
            source=obs_source_create_private("ffmpeg_source","Controlled tone",settings);
        } else {
            if ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]!=AVAuthorizationStatusAuthorized) {
                obs_data_release(settings); snprintf(e->error,sizeof(e->error),"MICROPHONE_PERMISSION_DENIED: autoriza Motive en Ajustes de privacidad"); return false;
            }
            if (!audio_available(id)) { obs_data_release(settings); snprintf(e->error,sizeof(e->error),"DEVICE_UNAVAILABLE: elige un UID explícito de devices"); return false; }
            obs_data_set_string(settings,"device_id",id);
            source=obs_source_create_private("coreaudio_input_capture","Selected microphone",settings);
        }
        obs_data_release(settings);
        if (!source) { snprintf(e->error,sizeof(e->error),"AUDIO_CREATE_FAILED"); return false; }
    }
    if (e->audio) obs_source_remove_audio_capture_callback(e->audio,receive_audio,e);
    atomic_store(&e->audio_seen_ns,0); atomic_store(&e->audio_frames,0); atomic_store(&e->audio_peak,0);
    if (source) obs_source_add_audio_capture_callback(source,receive_audio,e);
    obs_set_output_source(1,source);
    if (e->audio) obs_source_release(e->audio);
    e->audio=source; snprintf(e->audio_id,sizeof(e->audio_id),"%s",id); return true;
}
void motive_destroy(motive_engine *e) {
    if (!e) return;
    if (e->output && motive_output_state(e)) {
        obs_output_force_stop(e->output);
        for (int i=0;i<200 && !atomic_load(&e->output_stopped);i++) usleep(10000);
    }
    release_output(e);
    if (e->pixels) obs_remove_raw_video_callback(receive_frame,e);
    if (obs_initialized()) {
        obs_set_output_source(0,NULL); obs_set_output_source(1,NULL);
        graph_release(e);
        if (e->audio) { obs_source_remove_audio_capture_callback(e->audio,receive_audio,e); obs_source_release(e->audio); }

        obs_shutdown();
    }
    free(e->encoder_inventory);free(e->pixels); pthread_mutex_destroy(&e->lock); free(e);
}

bool motive_reset_output(motive_engine *e) { if(motive_output_state(e)){snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;} release_output(e);atomic_store(&e->output_code,0);return true;}
