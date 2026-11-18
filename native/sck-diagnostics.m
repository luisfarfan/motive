#import <Foundation/Foundation.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreVideo/CoreVideo.h>
#include <util/platform.h>
#include "sck-diagnostics.h"

/* Callback observations are individually atomic. A query is not an atomic
 * snapshot of the stream, and presentation timestamps are observations of the
 * OBS tick, never a replacement media clock or proof of pixel freshness. */
static id age_ms(uint64_t now, uint64_t then) {
    return then && now >= then ? @((now-then)/1000000.0) : [NSNull null];
}
static void diagnostics_query(void *data, calldata_t *params) {
    motive_sck_diagnostics *d=data;
    uint64_t now=os_gettime_ns(), surfaces=atomic_load(&d->surfaces);
    uint64_t first=atomic_load(&d->first_surface_ns), last=atomic_load(&d->last_surface_ns);
    int status=atomic_load(&d->status),phase=atomic_load(&d->phase);
    NSArray *statuses=@[@"complete",@"idle",@"blank",@"suspended",@"started",@"stopped"];
    NSArray *phases=@[@"created",@"starting",@"running",@"stopping",@"failed"];
    NSMutableDictionary *counts=[NSMutableDictionary dictionary];
    for (unsigned i=0;i<6;i++) counts[statuses[i]]=@(atomic_load(&d->statuses[i]));
    NSDictionary *snapshot=@{
        @"version":@1,@"instrument":@"obs33_sck_callback_and_tick",
        @"phase":phase>=0 && phase<5 ? phases[phase]:@"unknown",
        @"sample_status":status>=0 && status<6 ? statuses[status]:@"unknown",
        @"status_counts":counts,@"created_ns":@(atomic_load(&d->created_ns)),
        @"callbacks":@(atomic_load(&d->callbacks)),@"surface_samples":@(surfaces),
        @"last_callback_ns":@(atomic_load(&d->last_callback_ns)),
        @"callback_age_ms":age_ms(now,atomic_load(&d->last_callback_ns)),
        @"last_surface_ns":@(last),@"surface_age_ms":age_ms(now,last),
        @"last_pts_ns":@(atomic_load(&d->last_pts_ns)),
        @"surface_id":@(atomic_load(&d->surface_id)),
        @"surface_fps_lifetime":surfaces>1 && last>first ? @((surfaces-1)*1e9/(last-first)):[NSNull null],
        @"consumed_surface_samples":@(atomic_load(&d->presentations)),
        @"last_consumed_surface_ns":@(atomic_load(&d->last_presentation_ns)),
        @"consumption_age_ms":age_ms(now,atomic_load(&d->last_presentation_ns)),
        @"consumed_surface_id":@(atomic_load(&d->presented_surface_id)),
        @"consumed_pts_hint_ns":@(atomic_load(&d->presented_pts_ns)),
        @"texture_bind_attempts":@(atomic_load(&d->texture_bind_attempts)),
        @"renders_with_texture":@(atomic_load(&d->renders)),
        @"last_render_ns":@(atomic_load(&d->last_render_ns)),
        @"missing_images":@(atomic_load(&d->missing_images)),
        @"invalid_samples":@(atomic_load(&d->invalid_samples)),
        @"pts_repeats":@(atomic_load(&d->pts_repeats)),
        @"pts_regressions":@(atomic_load(&d->pts_regressions)),
        @"errors":@(atomic_load(&d->errors)),
        @"last_error_code":@(atomic_load(&d->last_error_code)),
        @"last_error_ns":@(atomic_load(&d->last_error_ns)),
        @"pixels_verified":@NO,@"snapshot_atomic":@NO
    };
    NSData *json=[NSJSONSerialization dataWithJSONObject:snapshot options:0 error:nil];
    NSString *text=[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    calldata_set_string(params,"json",text.UTF8String);
    [text release];
}
void motive_sck_diagnostics_init(motive_sck_diagnostics *d) {
    /* calloc owns zero initialization; explicit init for every atomic object. */
#define INIT(field) atomic_init(&d->field,0)
    INIT(created_ns);INIT(callbacks);INIT(last_callback_ns);INIT(surfaces);
    INIT(first_surface_ns);INIT(last_surface_ns);INIT(presentations);INIT(last_presentation_ns);
    INIT(texture_bind_attempts);INIT(renders);INIT(last_render_ns);
    INIT(missing_images);INIT(invalid_samples);INIT(pts_repeats);INIT(pts_regressions);
    INIT(errors);INIT(last_error_ns);INIT(last_error_code);INIT(surface_id);INIT(presented_surface_id);
    INIT(phase);
#undef INIT
    atomic_init(&d->last_pts_ns,-1);atomic_init(&d->presented_pts_ns,-1);atomic_init(&d->status,-1);
    for(unsigned i=0;i<6;i++)atomic_init(&d->statuses[i],0);
    atomic_store(&d->created_ns,os_gettime_ns());
}
void motive_sck_diagnostics_register(motive_sck_diagnostics *d,obs_source_t *source) {
    // OBS can retain a source whose create callback failed. Register only after
    // successful capture creation so its proc never retains a freed context.
    proc_handler_add(obs_source_get_proc_handler(source),"void motive_capture_diagnostics(out string json)",diagnostics_query,d);
}
void motive_sck_diagnostics_phase(motive_sck_diagnostics *d,int phase) {
    atomic_store(&d->phase,phase);
}
void motive_sck_diagnostics_error(motive_sck_diagnostics *d,int64_t code) {
    atomic_fetch_add(&d->errors,1);atomic_store(&d->last_error_code,code);
    atomic_store(&d->last_error_ns,os_gettime_ns());
}
void motive_sck_diagnostics_sample(motive_sck_diagnostics *d,CMSampleBufferRef sample) {
    uint64_t now=os_gettime_ns();atomic_fetch_add(&d->callbacks,1);
    atomic_store(&d->last_callback_ns,now);
    if(!sample || !CMSampleBufferIsValid(sample)) {
        atomic_fetch_add(&d->invalid_samples,1);return;
    }
    CFArrayRef attachments=CMSampleBufferGetSampleAttachmentsArray(sample,false);
    int status=-1;
    if(attachments && CFArrayGetCount(attachments)>0) {
        CFDictionaryRef entry=CFArrayGetValueAtIndex(attachments,0);
        CFTypeRef value=entry ? CFDictionaryGetValue(entry,SCStreamFrameInfoStatus):NULL;
        if(value && CFGetTypeID(value)==CFNumberGetTypeID())CFNumberGetValue(value,kCFNumberIntType,&status);
    }
    atomic_store(&d->status,status);
    if(status>=0 && status<6)atomic_fetch_add(&d->statuses[status],1);
    CMTime pts=CMSampleBufferGetPresentationTimeStamp(sample);
    if(CMTIME_IS_NUMERIC(pts) && pts.timescale>0) {
        int64_t ns=CMTimeConvertScale(pts,1000000000,kCMTimeRoundingMethod_Default).value;
        int64_t prior=atomic_exchange(&d->last_pts_ns,ns);
        if(prior>=0 && ns==prior)atomic_fetch_add(&d->pts_repeats,1);
        if(prior>=0 && ns<prior)atomic_fetch_add(&d->pts_regressions,1);
    }
    CVPixelBufferRef buffer=CMSampleBufferGetImageBuffer(sample);
    IOSurfaceRef surface=buffer ? CVPixelBufferGetIOSurface(buffer):NULL;
    if(!surface) {atomic_fetch_add(&d->missing_images,1);return;}
    uint64_t count=atomic_fetch_add(&d->surfaces,1);
    if(!count)atomic_store(&d->first_surface_ns,now);
    atomic_store(&d->surface_id,IOSurfaceGetID(surface));atomic_store(&d->last_surface_ns,now);
}
void motive_sck_diagnostics_present(motive_sck_diagnostics *d,IOSurfaceRef surface) {
    if(!surface)return;
    atomic_fetch_add(&d->presentations,1);atomic_store(&d->last_presentation_ns,os_gettime_ns());
    atomic_store(&d->presented_surface_id,IOSurfaceGetID(surface));
    /* The callback can publish another surface concurrently: explicitly a hint. */
    atomic_store(&d->presented_pts_ns,atomic_load(&d->last_pts_ns));
}
void motive_sck_diagnostics_render(motive_sck_diagnostics *d) {
    atomic_fetch_add(&d->renders,1);atomic_store(&d->last_render_ns,os_gettime_ns());
}
