/* H11: one libobs input owns official children and bounded source-local drawing.
 * No device, output, browser, worker clock, or alternate media pipeline is owned
 * here. Definition JSON is parsed only at create/update; ticks use fixed state.
 * Child pixels are composed into one bounded libobs target. Its premultiplied
 * RGBA is multiplied by opacity, including alpha (DrawMultiply alone does not).
 */
#include <sys/stat.h>

enum overlay_native_kind { OV_TEXT, OV_IMAGE, OV_VIDEO, OV_SHAPE, OV_WIDGET };
enum overlay_widget_kind { OV_LOWER_THIRD, OV_COUNTDOWN, OV_ALERT };
typedef struct {
    enum overlay_native_kind kind;
    enum overlay_widget_kind widget;
    uint32_t width, height, intrinsic_width, intrinsic_height;
    uint32_t color, background, accent, border_color;
    double opacity, background_opacity, border_width;
    unsigned size, align;
    bool background_set, border_set, circle, outline, looping;
    uint64_t duration_ms;
    char text[4097], subtitle[4097], font[32], asset_id[128], asset_path[4096];
} overlay_native_config;
typedef struct {
    pthread_mutex_t lock;
    obs_source_t *owner, *children[2];
    overlay_native_config config;
    gs_texrender_t *target;
    gs_effect_t *opacity_effect;
    gs_vertbuffer_t *circle_vertices;
    unsigned child_instances_created;
    bool visible, timer_running, timer_started, initialized, rendered;
    uint64_t timer_remaining_ns, timer_deadline_ns, alert_started_ns, alert_deadline_ns;
    uint64_t fade_started_ns, fade_duration_ns, media_action_ns;
    float fade_from, fade_to;
    int64_t last_timer_second;
    const char *error;
    bool asset_stat_valid;
    struct stat asset_stat;
} overlay_native;

static const char *overlay_opacity_shader =
    "uniform float4x4 ViewProj; uniform texture2d image; uniform float opacity;"
    "sampler_state s { Filter=Linear; AddressU=Clamp; AddressV=Clamp; };"
    "struct V { float4 pos:POSITION; float2 uv:TEXCOORD0; };"
    "V VS(V v) { V o; o.pos=mul(float4(v.pos.xyz,1.0),ViewProj); o.uv=v.uv; return o; }"
    "float4 PS(V v):TARGET { return image.Sample(s,v.uv)*opacity; }"
    "technique Draw { pass { vertex_shader=VS(v); pixel_shader=PS(v); } }";

static bool overlay_number(id value) {
    return [value isKindOfClass:[NSNumber class]] && CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID();
}
static bool overlay_string_copy(id value, char *dest, size_t capacity) {
    if (![value isKindOfClass:[NSString class]]) return false;
    NSData *bytes = [value dataUsingEncoding:NSUTF8StringEncoding];
    if (!bytes || bytes.length >= capacity || memchr(bytes.bytes,0,bytes.length)) return false;
    memcpy(dest,bytes.bytes,bytes.length); dest[bytes.length]=0; return true;
}
static bool overlay_u32(id value, uint32_t *out, uint32_t min, uint32_t max) {
    if (!overlay_number(value)) return false;
    double x=[value doubleValue];
    if (!isfinite(x) || floor(x)!=x || x<min || x>max) return false;
    *out=(uint32_t)x; return true;
}
static bool overlay_unit(id value, double *out) {
    if (!overlay_number(value)) return false;
    double x=[value doubleValue]; if (!isfinite(x) || x<0 || x>1) return false;
    *out=x; return true;
}
static bool overlay_bool(id value, bool *out) {
    if (![value isKindOfClass:[NSNumber class]] || CFGetTypeID((__bridge CFTypeRef)value)!=CFBooleanGetTypeID()) return false;
    *out=[value boolValue]; return true;
}
static bool overlay_parse(obs_data_t *settings, overlay_native_config *c) {
    memset(c,0,sizeof(*c)); c->opacity=1; c->background_opacity=1;
    const char *json=obs_data_get_string(settings,"definition");
    if (!json || strlen(json)>65536) return false;
    NSData *bytes=[NSData dataWithBytes:json length:strlen(json)];
    id raw=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
    if (![raw isKindOfClass:[NSDictionary class]]) return false;
    NSDictionary *d=raw; NSString *kind=d[@"kind"];
    if ([kind isEqual:@"text"]) c->kind=OV_TEXT;
    else if ([kind isEqual:@"image"]) c->kind=OV_IMAGE;
    else if ([kind isEqual:@"video"]) c->kind=OV_VIDEO;
    else if ([kind isEqual:@"shape"]) c->kind=OV_SHAPE;
    else if ([kind isEqual:@"widget"]) c->kind=OV_WIDGET;
    else return false;
    if (c->kind==OV_WIDGET) {
        if (![d[@"widget"] isKindOfClass:[NSDictionary class]]) return false;
        d=d[@"widget"];
        if ([d[@"kind"] isEqual:@"lower_third"]) c->widget=OV_LOWER_THIRD;
        else if ([d[@"kind"] isEqual:@"countdown"]) c->widget=OV_COUNTDOWN;
        else if ([d[@"kind"] isEqual:@"alert"]) c->widget=OV_ALERT;
        else return false;
        if (!overlay_string_copy(d[@"title"],c->text,sizeof(c->text)) ||
            !overlay_string_copy(d[@"subtitle"],c->subtitle,sizeof(c->subtitle)) ||
            !overlay_u32(d[@"background"],&c->background,0,0xffffff) ||
            !overlay_u32(d[@"accent"],&c->accent,0,0xffffff) ||
            !overlay_u32(d[@"color"],&c->color,0,0xffffff)) return false;
        uint32_t duration;
        uint32_t minimum=c->widget==OV_LOWER_THIRD?0:(c->widget==OV_COUNTDOWN?1000:100);
        uint32_t maximum=c->widget==OV_LOWER_THIRD?0:(c->widget==OV_COUNTDOWN?3600000:60000);
        if (!overlay_u32(d[@"duration_ms"],&duration,minimum,maximum)) return false;
        c->duration_ms=duration; c->background_set=true;
        snprintf(c->font,sizeof(c->font),"Helvetica");
    }
    if (!overlay_unit(d[@"opacity"],&c->opacity)) return false;
    if (c->kind==OV_IMAGE || c->kind==OV_VIDEO) {
        if (!overlay_string_copy(d[@"asset_id"],c->asset_id,sizeof(c->asset_id))) return false;
        const char *path=obs_data_get_string(settings,"asset_path");
        if (!path || path[0]!='/' || strlen(path)>=sizeof(c->asset_path)) return false;
        snprintf(c->asset_path,sizeof(c->asset_path),"%s",path);
        int64_t w=obs_data_get_int(settings,"asset_width"),h=obs_data_get_int(settings,"asset_height");
        if (w<1 || h<1 || w>2048 || h>2048) return false;
        if (c->kind==OV_VIDEO && (w>1920 || h>1080)) return false;
        c->intrinsic_width=(uint32_t)w;c->intrinsic_height=(uint32_t)h;
        double scale=fmin(1.0,fmin(1920.0/w,1080.0/h));
        c->width=(uint32_t)fmax(1,floor(w*scale)); c->height=(uint32_t)fmax(1,floor(h*scale));
        if (c->kind==OV_VIDEO && !overlay_bool(d[@"looping"],&c->looping)) return false;
        return true;
    }
    if (!overlay_u32(d[@"width"],&c->width,1,1920) || !overlay_u32(d[@"height"],&c->height,1,1080)) return false;
    if (c->kind==OV_TEXT) {
        uint32_t size;
        if (!overlay_string_copy(d[@"text"],c->text,sizeof(c->text)) ||
            !overlay_string_copy(d[@"font"],c->font,sizeof(c->font)) ||
            (strcmp(c->font,"Helvetica") && strcmp(c->font,"Arial") && strcmp(c->font,"Menlo")) ||
            !overlay_u32(d[@"size"],&size,8,192) ||
            !overlay_u32(d[@"color"],&c->color,0,0xffffff) ||
            !overlay_unit(d[@"background_opacity"],&c->background_opacity) ||
            !overlay_bool(d[@"outline"],&c->outline)) return false;
        c->size=size;
        if ([d[@"align"] isEqual:@"left"]) c->align=0;
        else if ([d[@"align"] isEqual:@"center"]) c->align=1;
        else if ([d[@"align"] isEqual:@"right"]) c->align=2;
        else return false;
        if (d[@"background"] && d[@"background"]!=[NSNull null]) {
            if (!overlay_u32(d[@"background"],&c->background,0,0xffffff)) return false;
            c->background_set=true;
        }
    } else if (c->kind==OV_SHAPE) {
        if ([d[@"shape"] isEqual:@"circle"]) c->circle=true;
        else if (![d[@"shape"] isEqual:@"rectangle"]) return false;
        if (!overlay_u32(d[@"color"],&c->color,0,0xffffff) || !overlay_number(d[@"border_width"])) return false;
        c->border_width=[d[@"border_width"] doubleValue];
        if (!isfinite(c->border_width) || c->border_width<0 || c->border_width>fmin(c->width,c->height)/2.0) return false;
        if (d[@"border_color"] && d[@"border_color"]!=[NSNull null]) {
            if (!overlay_u32(d[@"border_color"],&c->border_color,0,0xffffff)) return false;
            c->border_set=true;
        }
    }
    return true;
}

/* OBS text uses packed ABGR, while the public model uses readable RGB24. */
static uint32_t overlay_obs_color(uint32_t rgb) {
    return 0xff000000u | ((rgb & 0xffu)<<16) | (rgb & 0xff00u) | ((rgb>>16)&0xffu);
}
static obs_data_t *overlay_text_settings(const overlay_native_config *c, const char *text, unsigned size, unsigned width) {
    obs_data_t *s=obs_data_create(),*font=obs_data_create();
    obs_data_set_string(font,"face",c->font); obs_data_set_string(font,"style","");
    obs_data_set_int(font,"size",size); obs_data_set_int(font,"flags",0);
    obs_data_set_obj(s,"font",font); obs_data_release(font);
    obs_data_set_string(s,"text",text); obs_data_set_bool(s,"from_file",false);
    obs_data_set_int(s,"color1",overlay_obs_color(c->color));obs_data_set_int(s,"color2",overlay_obs_color(c->color));
    obs_data_set_bool(s,"outline",c->outline);obs_data_set_bool(s,"drop_shadow",false);
    obs_data_set_bool(s,"word_wrap",false);obs_data_set_bool(s,"antialiasing",true);
    obs_data_set_int(s,"custom_width",width); return s;
}
static unsigned overlay_widget_font(const overlay_native_config *c, unsigned index) {
    if (c->widget==OV_COUNTDOWN) return index ? (unsigned)fmax(24,fmin(192,c->height*.42)) : (unsigned)fmax(16,fmin(48,c->height*.13));
    return (unsigned)fmax(12,fmin(index?30:48,c->height*(index?.19:.29)));
}
static void overlay_timer_text(uint64_t remaining_ns, char *out, size_t capacity) {
    uint64_t seconds=(remaining_ns+999999999ull)/1000000000ull;
    snprintf(out,capacity,"%02llu:%02llu",(unsigned long long)(seconds/60),(unsigned long long)(seconds%60));
}
static obs_source_t *overlay_make_child(overlay_native *o,const char *id,obs_data_t *settings) {
    obs_source_t *child=obs_source_create_private(id,NULL,settings);
    if (child) {
        /* Media is visual-only. Never implicitly join the H10 global mix. */
        obs_source_set_audio_mixers(child,0);obs_source_set_muted(child,true);
        obs_source_set_monitoring_type(child,OBS_MONITORING_TYPE_NONE);
        if (!obs_source_add_active_child(o->owner,child)) {obs_source_release(child);return NULL;}
        o->child_instances_created++;
    }
    return child;
}
static void overlay_set_error(overlay_native *o,const char *error) {
    pthread_mutex_lock(&o->lock);o->error=error;pthread_mutex_unlock(&o->lock);
}
static void overlay_configure_children(overlay_native *o,const overlay_native_config *c,bool initial,bool loop_changed) {
    if (c->kind==OV_TEXT || c->kind==OV_WIDGET) {
        const char *id=NULL;
        if (obs_get_source_output_flags("text_ft2_source_v2")) id=obs_get_latest_input_type_id("text_ft2_source");
        if (!id) {overlay_set_error(o,"OVERLAY_BACKEND_UNAVAILABLE");return;}
        unsigned count=c->kind==OV_TEXT?1:2;
        for (unsigned i=0;i<count;i++) {
            char timer[32];const char *text=i?c->subtitle:c->text;
            if (c->kind==OV_WIDGET && c->widget==OV_COUNTDOWN && i) {
                pthread_mutex_lock(&o->lock);uint64_t remaining=o->timer_remaining_ns;
                if (o->timer_running) {uint64_t now=os_gettime_ns(); remaining=o->timer_deadline_ns>now?o->timer_deadline_ns-now:0;}
                pthread_mutex_unlock(&o->lock);
                overlay_timer_text(remaining,timer,sizeof(timer));text=timer;
            }
            unsigned size=c->kind==OV_TEXT?c->size:overlay_widget_font(c,i);
            /* Natural bounds make left/center/right apply to the complete text
             * block. Newlines are explicit; contain scales oversized blocks.
             * custom_width would reserve the entire box and defeat alignment. */
            obs_data_t *settings=overlay_text_settings(c,text,size,0);
            if (initial) o->children[i]=overlay_make_child(o,id,settings);
            else if (o->children[i]) obs_source_update(o->children[i],settings);
            obs_data_release(settings);
            if (!o->children[i]) overlay_set_error(o,"OVERLAY_BACKEND_UNAVAILABLE");
        }
    } else if (c->kind==OV_IMAGE && initial) {
        obs_data_t *s=obs_data_create();obs_data_set_string(s,"file",c->asset_path);
        obs_data_set_bool(s,"unload",false);obs_data_set_bool(s,"linear_alpha",false);
        o->children[0]=overlay_make_child(o,"image_source",s);obs_data_release(s);
        if (!o->children[0]) overlay_set_error(o,"OVERLAY_BACKEND_UNAVAILABLE");
    } else if (c->kind==OV_VIDEO && (initial || loop_changed)) {
        obs_data_t *s=obs_data_create();obs_data_set_string(s,"local_file",c->asset_path);
        obs_data_set_bool(s,"is_local_file",true);obs_data_set_bool(s,"looping",c->looping);
        obs_data_set_bool(s,"close_when_inactive",false);obs_data_set_bool(s,"restart_on_activate",false);
        obs_data_set_bool(s,"clear_on_media_end",false);obs_data_set_bool(s,"hw_decode",false);
        obs_data_set_bool(s,"seekable",true);obs_data_set_int(s,"speed_percent",100);obs_data_set_bool(s,"log_changes",false);
        if (initial) o->children[0]=overlay_make_child(o,"ffmpeg_source",s);
        else if (o->children[0]) obs_source_update(o->children[0],s);
        obs_data_release(s);
        if (!o->children[0]) overlay_set_error(o,"OVERLAY_BACKEND_UNAVAILABLE");
    }
}
static void overlay_advance_locked(overlay_native *o,uint64_t now) {
    if (o->timer_running) {
        o->timer_remaining_ns=o->timer_deadline_ns>now?o->timer_deadline_ns-now:0;
        if (!o->timer_remaining_ns) o->timer_running=false;
    }
    if (o->config.kind==OV_WIDGET && o->config.widget==OV_ALERT && o->alert_deadline_ns && now>=o->alert_deadline_ns) {
        o->visible=false;o->alert_deadline_ns=0;
    }
}
static float overlay_appearance_locked(overlay_native *o,uint64_t now) {
    if (o->config.kind==OV_WIDGET && o->config.widget==OV_LOWER_THIRD) {
        if (!o->fade_duration_ns || now>=o->fade_started_ns+o->fade_duration_ns) return o->fade_to;
        double t=(double)(now-o->fade_started_ns)/o->fade_duration_ns;
        return o->fade_from+(o->fade_to-o->fade_from)*(float)t;
    }
    if (!o->visible) return 0;
    if (o->config.kind==OV_WIDGET && o->config.widget==OV_ALERT && o->alert_deadline_ns) {
        uint64_t duration=o->alert_deadline_ns-o->alert_started_ns;
        uint64_t ramp=duration/2<300000000ull?duration/2:300000000ull;
        if (!ramp) return 1;
        return (float)fmax(0,fmin(1,fmin((double)(now-o->alert_started_ns)/ramp,(double)(o->alert_deadline_ns>now?o->alert_deadline_ns-now:0)/ramp)));
    }
    return 1;
}
static void overlay_update(void *data,obs_data_t *settings) {
    overlay_native *o=data;overlay_native_config c;
    @autoreleasepool {
        if (!overlay_parse(settings,&c)) {pthread_mutex_lock(&o->lock);o->error="INVALID_OVERLAY_DEFINITION";pthread_mutex_unlock(&o->lock);return;}
    }
    pthread_mutex_lock(&o->lock);
    if (o->initialized && (o->config.kind!=c.kind || strcmp(o->config.asset_id,c.asset_id) || strcmp(o->config.asset_path,c.asset_path) || (c.kind==OV_WIDGET && o->config.widget!=c.widget))) {
        o->error="INVALID_OVERLAY_DEFINITION";pthread_mutex_unlock(&o->lock);return;
    }
    bool initial=!o->initialized,loop_changed=o->config.looping!=c.looping;
    bool text_changed=initial || strcmp(o->config.text,c.text) || strcmp(o->config.subtitle,c.subtitle) || strcmp(o->config.font,c.font) || o->config.size!=c.size || o->config.color!=c.color || o->config.width!=c.width || o->config.height!=c.height || o->config.outline!=c.outline;
    overlay_advance_locked(o,os_gettime_ns());
    if (initial) {
        o->visible=c.kind!=OV_WIDGET || c.widget==OV_COUNTDOWN;
        o->fade_to=o->visible?1:0;o->fade_from=o->fade_to;
        o->timer_remaining_ns=c.duration_ms*1000000ull;o->last_timer_second=-1;
        if (c.kind==OV_IMAGE || c.kind==OV_VIDEO) o->asset_stat_valid=lstat(c.asset_path,&o->asset_stat)==0 && S_ISREG(o->asset_stat.st_mode);
    }
    /* Duration edits are desired configuration only. The existing timer and
     * deadline are preserved until timer_reset, or a start after completion. */
    o->config=c;o->initialized=true;o->error="";
    pthread_mutex_unlock(&o->lock);
    if (initial || text_changed || (c.kind==OV_VIDEO && loop_changed)) overlay_configure_children(o,&c,initial,loop_changed);
}
static const char *overlay_name(void *unused) {(void)unused;return "Motive visual overlay";}
static void overlay_destroy(void *data) {
    overlay_native *o=data;if (!o) return;
    for (unsigned i=0;i<2;i++) if (o->children[i]) {obs_source_remove_active_child(o->owner,o->children[i]);obs_source_release(o->children[i]);}
    obs_enter_graphics();gs_texrender_destroy(o->target);gs_effect_destroy(o->opacity_effect);gs_vertexbuffer_destroy(o->circle_vertices);obs_leave_graphics();
    pthread_mutex_destroy(&o->lock);free(o);
}
static void *overlay_create(obs_data_t *settings,obs_source_t *source) {
    overlay_native *o=calloc(1,sizeof(*o));if (!o) return NULL;
    pthread_mutex_init(&o->lock,NULL);o->owner=source;o->error="";
    obs_enter_graphics();o->target=gs_texrender_create(GS_RGBA,GS_ZS_NONE);
    o->opacity_effect=gs_effect_create(overlay_opacity_shader,"motive-overlay-opacity",NULL);obs_leave_graphics();
    overlay_update(o,settings);
    if (o->config.kind==OV_SHAPE) {
        /* Immutable geometry: reusing OBS's immediate vertex buffer for the
         * outer and inner circle overwrites Metal's earlier queued draw. */
        obs_enter_graphics();gs_render_start(true);
        for (unsigned i=0;i<64;i++) {
            float a=(float)(i*2*M_PI/64),b=(float)((i+1)*2*M_PI/64);
            gs_vertex2f(0,0);gs_vertex2f(cosf(a),sinf(a));gs_vertex2f(cosf(b),sinf(b));
        }
        o->circle_vertices=gs_render_save();obs_leave_graphics();
        if(!o->circle_vertices)overlay_set_error(o,"OVERLAY_RENDER_UNAVAILABLE");
    }
    if (!o->target || !o->opacity_effect) overlay_set_error(o,"OVERLAY_RENDER_UNAVAILABLE");
    return o;
}
static uint32_t overlay_width(void *data) {overlay_native *o=data;pthread_mutex_lock(&o->lock);uint32_t v=o->config.width;pthread_mutex_unlock(&o->lock);return v;}
static uint32_t overlay_height(void *data) {overlay_native *o=data;pthread_mutex_lock(&o->lock);uint32_t v=o->config.height;pthread_mutex_unlock(&o->lock);return v;}
static void overlay_enum(void *data,obs_source_enum_proc_t cb,void *param) {
    overlay_native *o=data;for (unsigned i=0;i<2;i++) if (o->children[i]) cb(o->owner,o->children[i],param);
}
static void overlay_tick(void *data,float seconds) {
    (void)seconds;overlay_native *o=data;overlay_native_config c;bool update_timer=false;uint64_t remaining=0;
    pthread_mutex_lock(&o->lock);overlay_advance_locked(o,os_gettime_ns());
    if (o->config.kind==OV_WIDGET && o->config.widget==OV_COUNTDOWN) {
        remaining=o->timer_remaining_ns;int64_t second=(int64_t)((remaining+999999999ull)/1000000000ull);
        if (second!=o->last_timer_second) {o->last_timer_second=second;c=o->config;update_timer=true;}
    }
    pthread_mutex_unlock(&o->lock);
    if (update_timer && o->children[1]) {
        char text[32];overlay_timer_text(remaining,text,sizeof(text));
        obs_data_t *s=overlay_text_settings(&c,text,overlay_widget_font(&c,1),0);
        obs_source_update(o->children[1],s);obs_data_release(s);
    }
    if (o->target) gs_texrender_reset(o->target);o->rendered=false;
}
/* Straight alpha primitives are accumulated into premultiplied RGBA. */
static void overlay_color(uint32_t rgb,float alpha,struct vec4 *out) {
    vec4_set(out,((rgb>>16)&255)/255.f,((rgb>>8)&255)/255.f,(rgb&255)/255.f,alpha);
}
static void overlay_rect(float x,float y,float w,float h,uint32_t rgb,float alpha) {
    if (w<=0 || h<=0 || alpha<=0) return;
    gs_effect_t *e=obs_get_base_effect(OBS_EFFECT_SOLID);struct vec4 color;overlay_color(rgb,alpha,&color);
    gs_effect_set_vec4(gs_effect_get_param_by_name(e,"color"),&color);
    gs_matrix_push();gs_matrix_translate3f(x,y,0);gs_matrix_scale3f(w,h,1);
    while (gs_effect_loop(e,"Solid")) gs_draw_sprite(NULL,0,1,1);
    gs_matrix_pop();
}
static void overlay_circle(gs_vertbuffer_t *vertices,float cx,float cy,float radius,uint32_t rgb) {
    if (!vertices || radius<=0) return;
    gs_effect_t *e=obs_get_base_effect(OBS_EFFECT_SOLID);struct vec4 color;overlay_color(rgb,1,&color);
    gs_effect_set_vec4(gs_effect_get_param_by_name(e,"color"),&color);
    gs_matrix_push();gs_matrix_translate3f(cx,cy,0);gs_matrix_scale3f(radius,radius,1);
    gs_load_vertexbuffer(vertices);gs_load_indexbuffer(NULL);
    while (gs_effect_loop(e,"Solid")) gs_draw(GS_TRIS,0,192);
    gs_matrix_pop();
}
static void overlay_child_draw(obs_source_t *child,float x,float y,float width,float height,unsigned align,bool center_y) {
    if (!child || width<=0 || height<=0) return;
    uint32_t cw=obs_source_get_width(child),ch=obs_source_get_height(child);
    if (!cw || !ch || cw>32768 || ch>8192) return;
    float scale=fminf(1,fminf(width/cw,height/ch));
    x+=(width-cw*scale)*(align==2?1:(align==1?.5f:0));if (center_y) y+=(height-ch*scale)*.5f;
    gs_matrix_push();gs_matrix_translate3f(x,y,0);gs_matrix_scale3f(scale,scale,1);
    obs_source_video_render(child);gs_matrix_pop();
}
static void overlay_contents(overlay_native *o,const overlay_native_config *c) {
    if (c->kind==OV_TEXT) {
        if (c->background_set) overlay_rect(0,0,c->width,c->height,c->background,(float)c->background_opacity);
        overlay_child_draw(o->children[0],0,0,c->width,c->height,c->align,false);
    } else if (c->kind==OV_IMAGE || c->kind==OV_VIDEO) {
        /* Managed image/video logical size contains the intrinsic aspect ratio. */
        overlay_child_draw(o->children[0],0,0,c->width,c->height,1,true);
    } else if (c->kind==OV_SHAPE) {
        float border=c->border_set?(float)c->border_width:0;
        if (c->circle) {
            float radius=fminf(c->width,c->height)/2;
            overlay_circle(o->circle_vertices,c->width*.5f,c->height*.5f,radius,border?c->border_color:c->color);
            if (border) overlay_circle(o->circle_vertices,c->width*.5f,c->height*.5f,radius-border,c->color);
        } else {
            overlay_rect(0,0,c->width,c->height,border?c->border_color:c->color,1);
            if (border) overlay_rect(border,border,c->width-2*border,c->height-2*border,c->color,1);
        }
    } else {
        overlay_rect(0,0,c->width,c->height,c->background,1);
        float pad=fminf(24,fminf(c->width,c->height)*.12f),inner=fmaxf(1,c->width-pad*2);
        if (c->widget==OV_COUNTDOWN) {
            overlay_rect(c->width*.3f,c->height*.86f,c->width*.4f,fminf(4,c->height*.03f),c->accent,1);
            overlay_child_draw(o->children[0],pad,c->height*.12f,inner,c->height*.20f,1,true);
            overlay_child_draw(o->children[1],pad,c->height*.33f,inner,c->height*.47f,1,true);
        } else {
            overlay_rect(0,0,fminf(6,c->width*.06f),c->height,c->accent,1);
            overlay_child_draw(o->children[0],pad,c->height*.16f,inner,c->height*.38f,0,true);
            overlay_child_draw(o->children[1],pad,c->height*.57f,inner,c->height*.25f,0,true);
        }
    }
}
static void overlay_render(void *data,gs_effect_t *unused) {
    (void)unused;overlay_native *o=data;overlay_native_config c;float appearance;
    pthread_mutex_lock(&o->lock);uint64_t now=os_gettime_ns();overlay_advance_locked(o,now);
    c=o->config;appearance=overlay_appearance_locked(o,now);pthread_mutex_unlock(&o->lock);
    if (!o->target || !o->opacity_effect || !c.width || !c.height || appearance<=0 || c.opacity<=0) return;
    /* This SDR source is deliberately not OBS_SOURCE_SRGB: compose and fade
     * in its declared sRGB space, restoring the caller's framebuffer state. */
    bool previous_srgb=gs_framebuffer_srgb_enabled();gs_enable_framebuffer_srgb(false);
    if (!o->rendered) {
        if (!gs_texrender_begin(o->target,c.width,c.height)) {
            gs_enable_framebuffer_srgb(previous_srgb);overlay_set_error(o,"OVERLAY_RENDER_UNAVAILABLE");return;
        }
        struct vec4 clear;vec4_zero(&clear);gs_clear(GS_CLEAR_COLOR,&clear,0,0);
        gs_ortho(0,c.width,0,c.height,-100,100);
        gs_blend_state_push();gs_enable_blending(true);
        gs_blend_function_separate(GS_BLEND_SRCALPHA,GS_BLEND_INVSRCALPHA,GS_BLEND_ONE,GS_BLEND_INVSRCALPHA);
        overlay_contents(o,&c);gs_blend_state_pop();gs_texrender_end(o->target);o->rendered=true;
    }
    gs_texture_t *texture=gs_texrender_get_texture(o->target);if (!texture) {gs_enable_framebuffer_srgb(previous_srgb);return;}
    gs_blend_state_push();gs_enable_blending(true);gs_blend_function(GS_BLEND_ONE,GS_BLEND_INVSRCALPHA);
    gs_effect_set_texture(gs_effect_get_param_by_name(o->opacity_effect,"image"),texture);
    gs_effect_set_float(gs_effect_get_param_by_name(o->opacity_effect,"opacity"),(float)c.opacity*appearance);
    while (gs_effect_loop(o->opacity_effect,"Draw")) gs_draw_sprite(texture,0,c.width,c.height);
    gs_blend_state_pop();gs_enable_framebuffer_srgb(previous_srgb);
}
static overlay_native *overlay_from_source(obs_source_t *source) {
    if (!source || strcmp(obs_source_get_id(source),"motive_visual")) return NULL;
    return obs_obj_get_data(source);
}
static bool overlay_asset_same(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtimespec.tv_sec==b->st_mtimespec.tv_sec && a->st_mtimespec.tv_nsec==b->st_mtimespec.tv_nsec;
}
/* Owner-thread query: filesystem metadata is never read from render/tick. The
 * asset broker owns full hash validation; this catches removal/replacement. */
static const char *overlay_source_health(obs_source_t *source) {
    overlay_native *o=overlay_from_source(source);if (!o) return "INVALID_OVERLAY_SOURCE";
    pthread_mutex_lock(&o->lock);overlay_native_config c=o->config;const char *error=o->error;
    bool initial_valid=o->asset_stat_valid;uint64_t media_action=o->media_action_ns;struct stat initial=o->asset_stat;pthread_mutex_unlock(&o->lock);
    if (error && *error) return error;
    if (!o->target || !o->opacity_effect) return "OVERLAY_RENDER_UNAVAILABLE";
    if ((c.kind==OV_TEXT && !o->children[0]) || (c.kind==OV_WIDGET && (!o->children[0] || !o->children[1]))) return "OVERLAY_BACKEND_UNAVAILABLE";
    if (c.kind==OV_IMAGE || c.kind==OV_VIDEO) {
        struct stat current;if (lstat(c.asset_path,&current)!=0) return "ASSET_MISSING";
        if (!S_ISREG(current.st_mode) || !initial_valid || !overlay_asset_same(&initial,&current)) return "ASSET_CHANGED";
        if (c.kind==OV_VIDEO && o->children[0]) {
            enum obs_media_state media=obs_source_media_get_state(o->children[0]);
            if(media==OBS_MEDIA_STATE_ERROR)return "ASSET_DECODE_FAILED";
            // Explicit stop/EOF is a healthy empty visual. Play/restart may clear
            // its previous async frame; give only those commands bounded grace.
            if(media==OBS_MEDIA_STATE_STOPPED || media==OBS_MEDIA_STATE_ENDED)return "";
            if(media_action && os_gettime_ns()-media_action<3000000000ULL)return "";
        }
        if (!o->children[0] || !obs_source_get_width(o->children[0]) || !obs_source_get_height(o->children[0])) return "ASSET_NOT_READY";
    }
    /* FT2 draws glyph vertices from its fixed atlas, not a texture the size of
     * the text block. The wrapper target remains bounded to the declared box. */
    for (unsigned i=0;i<2;i++) if (o->children[i] && (obs_source_get_width(o->children[i])>32768 || obs_source_get_height(o->children[i])>8192)) return "OVERLAY_RENDER_LIMIT";
    return "";
}
static const char *overlay_media_state(enum obs_media_state state) {
    switch (state) {
    case OBS_MEDIA_STATE_PLAYING:return "playing";case OBS_MEDIA_STATE_OPENING:return "opening";
    case OBS_MEDIA_STATE_BUFFERING:return "buffering";case OBS_MEDIA_STATE_PAUSED:return "paused";
    case OBS_MEDIA_STATE_STOPPED:return "stopped";case OBS_MEDIA_STATE_ENDED:return "ended";
    case OBS_MEDIA_STATE_ERROR:return "error";default:return "none";
    }
}
static NSDictionary *overlay_source_state(obs_source_t *source) {
    overlay_native *o=overlay_from_source(source);if (!o) return @{};
    const char *health=overlay_source_health(source);
    pthread_mutex_lock(&o->lock);uint64_t now=os_gettime_ns();overlay_advance_locked(o,now);
    overlay_native_config c=o->config;float appearance=overlay_appearance_locked(o,now);
    const char *kind=c.kind==OV_TEXT?"text":c.kind==OV_IMAGE?"image":c.kind==OV_VIDEO?"video":c.kind==OV_SHAPE?"shape":"widget";
    const char *phase=o->visible?"visible":"hidden";uint64_t remaining=0;
    if (c.kind==OV_WIDGET && c.widget==OV_LOWER_THIRD && o->fade_duration_ns && now<o->fade_started_ns+o->fade_duration_ns) phase=o->fade_to>o->fade_from?"showing":"hiding";
    if (c.kind==OV_WIDGET && c.widget==OV_COUNTDOWN) {remaining=o->timer_remaining_ns/1000000ull;phase=o->timer_running?"running":(!o->timer_remaining_ns?"completed":(o->timer_started?"paused":"idle"));}
    if (c.kind==OV_WIDGET && c.widget==OV_ALERT && o->alert_deadline_ns) {remaining=(o->alert_deadline_ns>now?o->alert_deadline_ns-now:0)/1000000ull;phase=appearance<1?(now-o->alert_started_ns<300000000ull?"showing":"hiding"):"visible";}
    uint64_t instances=o->child_instances_created;
    pthread_mutex_unlock(&o->lock);
    NSMutableDictionary *result=[@{@"kind":@(kind),@"visible":appearance>0?@YES:@NO,@"phase":@(phase),@"remaining_ms":@(remaining),
        @"appearance_opacity":@(appearance),@"effective_opacity":@(appearance*c.opacity),@"child_instances_created":@(instances),
        @"width":@(c.width),@"height":@(c.height),@"intrinsic_width":@(c.intrinsic_width),@"intrinsic_height":@(c.intrinsic_height),
        @"framebuffer_estimate_bytes":@((uint64_t)c.width*c.height*8),
        @"text_atlas_estimate_bytes":@((uint64_t)(c.kind==OV_TEXT?1:(c.kind==OV_WIDGET?2:0))*2048*2048*2),
        @"health":@(health)} mutableCopy];
    if (c.kind==OV_WIDGET) result[@"widget_kind"]=@(c.widget==OV_LOWER_THIRD?"lower_third":c.widget==OV_COUNTDOWN?"countdown":"alert");
    if (c.kind==OV_VIDEO && o->children[0]) {
        result[@"media_state"]=@(overlay_media_state(obs_source_media_get_state(o->children[0])));
        result[@"media_time_ms"]=@(obs_source_media_get_time(o->children[0]));result[@"media_duration_ms"]=@(obs_source_media_get_duration(o->children[0]));
        result[@"audio_mixers"]=@(obs_source_get_audio_mixers(o->children[0]));
    }
    return result;
}
static bool overlay_source_event(obs_source_t *source,const char *event) {
    overlay_native *o=overlay_from_source(source);if (!o || !event) return false;
    pthread_mutex_lock(&o->lock);uint64_t now=os_gettime_ns();overlay_advance_locked(o,now);overlay_native_config c=o->config;
    bool accepted=false;bool media=false;
    if (!strcmp(event,"show") || !strcmp(event,"hide") || (!strcmp(event,"trigger") && c.kind==OV_WIDGET && c.widget!=OV_COUNTDOWN)) {
        bool show=strcmp(event,"hide")!=0;
        if (c.kind==OV_WIDGET && c.widget==OV_LOWER_THIRD) {
            o->fade_from=overlay_appearance_locked(o,now);o->fade_to=show?1:0;o->fade_started_ns=now;
            o->fade_duration_ns=fabsf(o->fade_to-o->fade_from)<.00001f?0:300000000ull;
        } else if (c.kind==OV_WIDGET && c.widget==OV_ALERT) {
            o->alert_started_ns=now;o->alert_deadline_ns=show?now+c.duration_ms*1000000ull:0;
        }
        o->visible=show;accepted=true;
    } else if (c.kind==OV_WIDGET && c.widget==OV_COUNTDOWN) {
        if (!strcmp(event,"timer_start")) {
            if (!o->timer_remaining_ns) o->timer_remaining_ns=c.duration_ms*1000000ull;
            o->timer_started=true;o->timer_running=true;o->timer_deadline_ns=now+o->timer_remaining_ns;accepted=true;
        } else if (!strcmp(event,"timer_stop")) {o->timer_running=false;accepted=true;}
        else if (!strcmp(event,"timer_reset")) {o->timer_started=false;o->timer_running=false;o->timer_remaining_ns=c.duration_ms*1000000ull;o->last_timer_second=-1;accepted=true;}
    } else if (c.kind==OV_VIDEO && (!strcmp(event,"play") || !strcmp(event,"pause") || !strcmp(event,"restart") || !strcmp(event,"stop"))) {media=true;accepted=o->children[0]!=NULL;if(accepted && strcmp(event,"stop") && strcmp(event,"pause"))o->media_action_ns=now;}
    pthread_mutex_unlock(&o->lock);
    if (media && accepted) {
        if (!strcmp(event,"play")) {
            enum obs_media_state state=obs_source_media_get_state(o->children[0]);
            if(state==OBS_MEDIA_STATE_STOPPED || state==OBS_MEDIA_STATE_ENDED || state==OBS_MEDIA_STATE_NONE)
                obs_source_media_restart(o->children[0]);
            else obs_source_media_play_pause(o->children[0],false);
        }
        else if (!strcmp(event,"pause")) obs_source_media_play_pause(o->children[0],true);
        else if (!strcmp(event,"restart")) obs_source_media_restart(o->children[0]);
        else obs_source_media_stop(o->children[0]);
    }
    return accepted;
}
static struct obs_source_info overlay_source_info = {
    .id="motive_visual",.type=OBS_SOURCE_TYPE_INPUT,.output_flags=OBS_SOURCE_VIDEO|OBS_SOURCE_CUSTOM_DRAW,
    .get_name=overlay_name,.create=overlay_create,.destroy=overlay_destroy,.update=overlay_update,
    .get_width=overlay_width,.get_height=overlay_height,.video_tick=overlay_tick,.video_render=overlay_render,
    .enum_active_sources=overlay_enum,.enum_all_sources=overlay_enum,
};
