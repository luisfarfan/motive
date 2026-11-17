#include <obs.h>
#include <obs-audio-controls.h>
#include <graphics/vec4.h>
#include <pthread.h>
#include <stdatomic.h>
#include <math.h>
#include <unistd.h>
#include <util/platform.h>
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <VideoToolbox/VideoToolbox.h>

/* Control entry points run on the main/GPUI owner. OBS owns rendering, mixing
 * and output threads; source/media callbacks only publish bounded observations.
 * The controlled tone has a sample-clocked producer. No GPUI object crosses
 * any of these thread boundaries. */
typedef struct audio_input audio_input;
typedef struct audio_mix_meter audio_mix_meter;
typedef struct visual_source visual_source;
typedef struct visual_scene visual_scene;
typedef struct overlay_animator overlay_animator;
enum scene_phase { SCENE_IDLE, SCENE_PREPARING, SCENE_RUNNING, SCENE_COMPLETED, SCENE_CANCELLED, SCENE_FAILED };
typedef struct { atomic_uint_fast64_t stops; } transition_events;
/* Embedded slots never move: OBS signal userdata remains valid until the
 * per-output worker barrier and disconnection of both handlers. */
typedef struct {
    obs_output_t *output;
    obs_service_t *service;
    obs_encoder_t *video_encoder,*audio_encoder;
    bool network_output,legacy_udp,selected_hardware;
    atomic_bool output_started,output_stopped;
    atomic_int output_code;
    atomic_uint_fast64_t started_ns,stopped_ns;
    void *output_activity;
    uint64_t bytes;
    uint32_t frames,encoded_frames;
    int drops;
    char selected_encoder[512],fallback_reason[128];
} output_slot;
typedef struct {
    pthread_mutex_t lock;
    uint8_t *pixels;
    uint32_t width, height, fps;
    bool video_ready, preview_connected;
    char video_failure[128];
    char audio_id[512];
    audio_input *audio_inputs[8];uint64_t audio_instances;
    audio_mix_meter *mix_meter;
    overlay_animator *animations;
    visual_source *visuals[16];visual_scene *scenes[8];size_t visual_count,scene_count;
    obs_source_t *transitions[2];unsigned transition_index;
    transition_events transition_events[2];uint64_t transition_stop_baseline;
    enum scene_phase scene_phase;uint64_t scene_operation,visual_instances,scenes_built;
    char scene_current[64],scene_from[64],scene_target[64],scene_error[64];
    char *scene_blocked;
    unsigned scene_kind,scene_duration_ms;float scene_progress;
    uint64_t scene_prepare_ns,scene_ready_frame;bool scene_needs_warmup,scene_target_held;
    visual_scene *scene_from_native,*scene_target_native;
    uint64_t sequence, timestamp;
    atomic_uint_fast64_t busy_drops;
    atomic_uint_fast64_t preview_copies;
    output_slot outputs[2];
    unsigned last_output;
    bool rtmp_loaded,vt_loaded;
    char vt_h264_id[512],vt_unavailable_reason[128];
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
    if (!e->video_ready || !e->pixels || e->preview_connected) return;
    struct video_scale_info scale = {.format=VIDEO_FORMAT_BGRA, .width=e->width,
        .height=e->height, .range=VIDEO_RANGE_FULL, .colorspace=VIDEO_CS_709};
    obs_add_raw_video_callback(&scale, receive_frame, e);
    e->preview_connected=true;
}
static bool load_module(motive_engine *e, const char *name) {
    char binary[8192], data[8192]; obs_module_t *module = NULL;
    snprintf(binary,sizeof(binary),"%s/PlugIns/%s.plugin/Contents/MacOS/%s",e->base,name,name);
    if (!strcmp(name,"obs-outputs")) snprintf(binary,sizeof(binary),"%s",MOTIVE_RTMP_MODULE);
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
    struct obs_video_info v = {.graphics_module=graphics,.fps_num=e->fps,.fps_den=1,
        .base_width=e->width,.base_height=e->height,.output_width=e->width,.output_height=e->height,
        .output_format=VIDEO_FORMAT_NV12,.gpu_conversion=true,.colorspace=VIDEO_CS_709,
        .range=VIDEO_RANGE_PARTIAL,.scale_type=OBS_SCALE_BICUBIC};
    return obs_reset_video(&v);
}
static struct obs_source_info watch_info;
static struct obs_source_info tone_info;
static struct obs_source_info overlay_source_info;
static overlay_animator *overlay_animator_create(void);
static bool overlay_animation_busy(overlay_animator *a);
#include "credentials.inc"
// Native plugins may log a server's reply containing the stream key. Once a
// credential is used, suppress free-form OBS logs for the process lifetime;
// structured error codes/metrics remain available. Never keep a redaction list
// of secrets or rely on plugins always sanitizing messages.
static atomic_bool protect_obs_logs;
static log_handler_t previous_log_handler;
static void *previous_log_context;
static void private_log(int level,const char *format,va_list args,void *unused) {
    (void)unused;
    if (!atomic_load(&protect_obs_logs) && previous_log_handler)
        previous_log_handler(level,format,args,previous_log_context);
}
#include "local-service.inc"
static void discover_encoders(motive_engine *e);
static void audio_mix_start(motive_engine *e);
static void audio_mix_stop(motive_engine *e);
#include "self-audio-fixture.inc"
void motive_destroy(motive_engine *e);
motive_engine *motive_create(const char *base) {
    motive_engine *e=calloc(1,sizeof(*e));
    for (unsigned i=0;i<2;i++) {
        atomic_init(&e->outputs[i].output_started,false);
        atomic_init(&e->outputs[i].output_stopped,true);
        atomic_init(&e->outputs[i].output_code,0);
        atomic_init(&e->outputs[i].started_ns,0);
        atomic_init(&e->outputs[i].stopped_ns,0);
    }
    pthread_mutex_init(&e->lock,NULL); e->width=960; e->height=540; e->fps=30;
    snprintf(e->base,sizeof(e->base),"%s",base);
    [NSApplication sharedApplication];
    base_get_log_handler(&previous_log_handler,&previous_log_context);
    base_set_log_handler(private_log,NULL);
    if (!obs_startup("en-US",NULL,NULL)) { snprintf(e->error,sizeof(e->error),"obs_startup falló"); return e; }
    char resources[8192];
    snprintf(resources,sizeof(resources),"%s/Frameworks/libobs.framework/Resources",base);
    obs_add_data_path(resources);
    int code=reset_video(e);
    if (code) { snprintf(e->error,sizeof(e->error),"obs_reset_video falló: %d",code); return e; }
    e->video_ready=true;
    struct obs_audio_info audio={.samples_per_sec=48000,.speakers=SPEAKERS_STEREO};
    if (!obs_reset_audio(&audio)) { snprintf(e->error,sizeof(e->error),"obs_reset_audio falló"); return e; }
    const char *modules[]={"obs-x264","obs-ffmpeg","obs-outputs","mac-capture","mac-avcapture","obs-transitions","image-source","text-freetype2"};
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
    obs_register_service(&local_service_info);
    e->rtmp_loaded=obs_get_output_flags("rtmp_output")!=0;
    discover_encoders(e);
    obs_register_source(&pattern_info);
    obs_register_source(&watch_info);
    obs_register_source(&tone_info);
    obs_register_source(&overlay_source_info);
    e->animations=overlay_animator_create();
    e->pixels=calloc((size_t)e->width*e->height,4);
    if (!e->pixels) {snprintf(e->error,sizeof(e->error),"VIDEO_BUFFER_ALLOCATION_FAILED");return e;}
    connect_preview(e);
    audio_mix_start(e);
    if(!motive_self_audio_fixture_start())snprintf(e->error,sizeof(e->error),"SELF_AUDIO_FIXTURE_START_FAILED");
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

#include "output-slots.inc"
#include "encoding.inc"

/* Config changes are owner-only and require quiescent output workers. Reserve
 * before mutation; OBS reset can destroy video before returning failure. */
bool motive_configure_video(motive_engine *e,uint32_t width,uint32_t height,uint32_t fps) {
    e->error[0]=0;
    if (e->scene_phase==SCENE_PREPARING || e->scene_phase==SCENE_RUNNING) {snprintf(e->error,sizeof(e->error),"TRANSITION_BUSY");return false;}
    if (overlay_animation_busy(e->animations)) {snprintf(e->error,sizeof(e->error),"ANIMATION_BUSY");return false;}
    if (motive_output_state(e)) {snprintf(e->error,sizeof(e->error),"OUTPUT_BUSY");return false;}
    uint32_t wide=width>height ? width:height,shorter=width>height ? height:width;
    if (!((wide==960 && shorter==540) || (wide==1280 && shorter==720) || (wide==1920 && shorter==1080)) || (fps!=30 && fps!=60)) {
        snprintf(e->error,sizeof(e->error),"INVALID_VIDEO_CONFIGURATION");return false;
    }
    if (e->video_ready && e->width==width && e->height==height && e->fps==fps) {e->video_failure[0]=0;return true;}
    if ((size_t)width>SIZE_MAX/height/4) {snprintf(e->error,sizeof(e->error),"VIDEO_BUFFER_ALLOCATION_FAILED");return false;}
    uint8_t *next=calloc((size_t)width*height,4);
    if (!next) {snprintf(e->error,sizeof(e->error),"VIDEO_BUFFER_ALLOCATION_FAILED");return false;}
    release_outputs(e);
    if (e->preview_connected) {obs_remove_raw_video_callback(receive_frame,e);e->preview_connected=false;}
    uint32_t oldw=e->width,oldh=e->height,oldfps=e->fps;
    e->video_ready=false;e->width=width;e->height=height;e->fps=fps;
    int code=reset_video(e);
    if (code) {
        e->width=oldw;e->height=oldh;e->fps=oldfps;
        int rollback=reset_video(e);
        e->video_ready=rollback==OBS_VIDEO_SUCCESS;
        free(next);
        if (e->video_ready) connect_preview(e);
        snprintf(e->video_failure,sizeof(e->video_failure),rollback ? "VIDEO_ROLLBACK_FAILED: reset=%d rollback=%d":"VIDEO_RESET_FAILED: reset=%d rollback=%d",code,rollback);
        snprintf(e->error,sizeof(e->error),"%s",e->video_failure);return false;
    }
    pthread_mutex_lock(&e->lock);
    uint8_t *old=e->pixels;e->pixels=next;e->sequence=0;e->timestamp=0;
    pthread_mutex_unlock(&e->lock);
    free(old);e->video_ready=true;e->video_failure[0]=0;
    connect_preview(e);return true;
}
void motive_invalidate_video(motive_engine *e) {
    if(e->preview_connected) {obs_remove_raw_video_callback(receive_frame,e);e->preview_connected=false;}
    e->video_ready=false;
    snprintf(e->video_failure,sizeof(e->video_failure),"VIDEO_RECOVERY_REQUIRED");
}
char *motive_video_info(motive_engine *e) {
    struct obs_video_info v={0};bool available=e->video_ready && obs_get_video_info(&v);
    NSDictionary *state=@{@"available":@(available),@"width":available ? @(v.output_width):[NSNull null],
        @"height":available ? @(v.output_height):[NSNull null],@"fps":available ? @((double)v.fps_num/v.fps_den):[NSNull null],
        @"fps_num":available ? @(v.fps_num):[NSNull null],@"fps_den":available ? @(v.fps_den):[NSNull null],
        @"base_width":available ? @(v.base_width):[NSNull null],@"base_height":available ? @(v.base_height):[NSNull null],
        @"preview_connected":@(e->preview_connected),@"error":e->video_failure[0] ? @(e->video_failure):[NSNull null]};
    NSData *json=[NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}
static float motive_design_scale(motive_engine *e) {return (float)e->width/(e->width>e->height ? 960.f:540.f);}
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
#include "overlays/sources.inc"
#include "overlays/animation.inc"
#include "graph.inc"
#include "overlays/integration.inc"
void motive_request_permission(int kind) {
    if (kind==0) CGRequestScreenCaptureAccess();
    else [AVCaptureDevice requestAccessForMediaType:kind==1 ? AVMediaTypeAudio:AVMediaTypeVideo completionHandler:^(BOOL granted) { (void)granted; }];
}
void motive_close_test_window(void) {
    for (NSWindow *w in NSApp.windows) if ([w.title isEqualToString:@"Motive — Fuente controlada"]) [w performClose:nil];
}
#include "audio-mixer.inc"
void motive_destroy(motive_engine *e) {
    if (!e) return;
    motive_self_audio_fixture_stop();
    if (motive_output_state(e)) {
        // Normal shutdown is rejected/deferred by Production until quiescent.
        // An abnormal owner drop must not free memory still used by workers or
        // join a network handshake on the UI thread. Process exit reclaims it.
        return;
    }
    release_outputs(e);
    if (e->preview_connected) obs_remove_raw_video_callback(receive_frame,e);
    if (obs_initialized()) {
        obs_set_output_source(0,NULL);
        audio_mix_stop(e);
        overlay_animator_destroy(e->animations);e->animations=NULL;
        graph_release(e);


        obs_shutdown();
    }
    free(e->encoder_inventory);free(e->pixels); pthread_mutex_destroy(&e->lock); free(e);
}
