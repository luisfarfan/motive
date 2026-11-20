/* Instrument contract only: synthetic CMSampleBuffers, no SCStream or capture. */
#import <Foundation/Foundation.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreVideo/CoreVideo.h>
#include "sck-diagnostics.h"
#include <assert.h>

static CMSampleBufferRef sample(int status, int64_t pts) {
    CVPixelBufferRef pixel = NULL;
    NSDictionary *attrs = @{(id)kCVPixelBufferIOSurfacePropertiesKey:@{}};
    assert(CVPixelBufferCreate(kCFAllocatorDefault, 8, 8, kCVPixelFormatType_32BGRA,
                              (CFDictionaryRef)attrs, &pixel) == kCVReturnSuccess);
    CMVideoFormatDescriptionRef format = NULL;
    assert(CMVideoFormatDescriptionCreateForImageBuffer(NULL, pixel, &format) == noErr);
    CMSampleTimingInfo timing = {CMTimeMake(1,30), CMTimeMake(pts,30), kCMTimeInvalid};
    CMSampleBufferRef result = NULL;
    assert(CMSampleBufferCreateReadyWithImageBuffer(NULL, pixel, format, &timing, &result) == noErr);
    CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(result, true);
    CFDictionarySetValue((CFMutableDictionaryRef)CFArrayGetValueAtIndex(attachments,0),
                         SCStreamFrameInfoStatus, (CFNumberRef)@(status));
    CFRelease(format); CVPixelBufferRelease(pixel);
    return result;
}
int main(void) {
    @autoreleasepool {
        motive_sck_diagnostics d;
        motive_sck_diagnostics_init(&d);
        assert(atomic_load(&d.status)==-1 && atomic_load(&d.status_changes)==0);
        int states[] = {SCFrameStatusComplete, SCFrameStatusIdle, SCFrameStatusSuspended,
                        SCFrameStatusSuspended, SCFrameStatusComplete, SCFrameStatusStopped};
        uint64_t suspension_start=0, suspension_seen=0;
        for (unsigned i=0;i<sizeof(states)/sizeof(states[0]);i++) {
            CMSampleBufferRef s=sample(states[i],i);
            motive_sck_diagnostics_sample(&d,s); CFRelease(s);
            assert(atomic_load(&d.status)==states[i]);
            assert(atomic_load(&d.status_last_seen_ns[states[i]])>0);
            if(i==2) suspension_start=atomic_load(&d.status_changed_ns);
            if(i==3) {
                assert(atomic_load(&d.status_changed_ns)==suspension_start);
                suspension_seen=atomic_load(&d.status_last_seen_ns[SCFrameStatusSuspended]);
            }
            if(i==4) {
                assert(atomic_load(&d.status_last_seen_ns[SCFrameStatusSuspended])==suspension_seen);
                assert(atomic_load(&d.status_last_seen_ns[SCFrameStatusComplete])>=suspension_seen);
            }
        }
        assert(atomic_load(&d.callbacks)==6 && atomic_load(&d.status_changes)==5);
        assert(atomic_load(&d.statuses[SCFrameStatusSuspended])==2);
        assert(atomic_load(&d.status_last_seen_ns[SCFrameStatusBlank])==0);
        motive_sck_diagnostics_sample(&d,NULL);
        assert(atomic_load(&d.invalid_samples)==1 && atomic_load(&d.status_changes)==5);
        motive_sck_diagnostics_error(&d,-3817);
        motive_sck_diagnostics_phase(&d,4);
        assert(atomic_load(&d.last_error_code)==-3817 && atomic_load(&d.phase)==4);
        puts("PASS: SCK diagnostic scalar history; no physical/lifetime claim");
    }
    return 0;
}
