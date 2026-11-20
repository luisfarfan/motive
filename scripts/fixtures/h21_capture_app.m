/* Owned, bounded two-window capture fixture with optional generated audio.
 * No capture, audio input, network, preferences, browser or private API.
 * stdin controls only our windows.
 * Draw counts are producer observations, never evidence of captured pixels. */
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <AVFoundation/AVFoundation.h>
#include <math.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

static double fixtureDeadlineSeconds = 180;
static bool fixtureAudioEnabled;
static atomic_uint_fast64_t fixtureAudioFrames;
static const char *presentationDisplayUUID;

static void emit(NSDictionary *event) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:event options:0 error:nil];
    if (data) { fwrite(data.bytes, 1, data.length, stdout); fputc('\n', stdout); fflush(stdout); }
}

@interface H21View : NSView
@property NSUInteger index;
@property uint64_t tick, draws;
@end
@implementation H21View
- (void)drawRect:(NSRect)dirty {
    (void)dirty; _draws++;
    [(_index == 0 ? [NSColor colorWithRed:0.85 green:0.12 blue:0.12 alpha:1]
                 : [NSColor colorWithRed:0.08 green:0.78 blue:0.78 alpha:1]) setFill];
    NSRectFill(self.bounds);
    if (fixtureAudioEnabled) {
        uint64_t frames=atomic_load(&fixtureAudioFrames);
        [(frames%48000<9600 ? [NSColor colorWithRed:20/255.0 green:210/255.0 blue:65/255.0 alpha:1]
                            : NSColor.blackColor) setFill];
        NSRectFill(NSMakeRect(0,0,self.bounds.size.width*.08,self.bounds.size.height*.12));
    }
    for (unsigned bit=0; bit<16; bit++) {
        [((_tick>>bit)&1 ? NSColor.whiteColor : NSColor.blackColor) setFill];
        NSRectFill(NSMakeRect((0.05+bit*0.055)*self.bounds.size.width,
            0.15*self.bounds.size.height, 0.04*self.bounds.size.width, 0.25*self.bounds.size.height));
    }
    [[NSString stringWithFormat:@"MOTIVE H21 / OWNED WINDOW %lu\n10 Hz counter %llu",
        (unsigned long)_index+1, (unsigned long long)_tick]
        drawInRect:NSMakeRect(20, self.bounds.size.height*0.55, self.bounds.size.width-40, 75)
        withAttributes:@{NSFontAttributeName:[NSFont monospacedSystemFontOfSize:18 weight:NSFontWeightMedium],
                         NSForegroundColorAttributeName:NSColor.whiteColor}];
}
@end

@interface H21App : NSObject <NSApplicationDelegate, NSWindowDelegate>
@property NSMutableArray<NSWindow *> *windows;
@property NSMutableArray<H21View *> *views;
@property NSTimer *timer;
@property NSTimeInterval started, lastLog;
@property NSUInteger sequence;
@property AVAudioEngine *audioEngine;
@property AVAudioSourceNode *audioNode;
@property NSMutableSet<NSWindow *> *completedFullScreen;
@end
@implementation H21App
- (void)windowWillEnterFullScreen:(NSNotification *)note {
    [_completedFullScreen removeObject:note.object]; [self sample:@"fullscreen_enter_started"];
}
- (void)windowDidEnterFullScreen:(NSNotification *)note {
    [_completedFullScreen addObject:note.object]; [self sample:@"fullscreen_enter_completed"];
}
- (void)windowWillExitFullScreen:(NSNotification *)note {
    [_completedFullScreen removeObject:note.object]; [self sample:@"fullscreen_exit_started"];
}
- (void)windowDidExitFullScreen:(NSNotification *)note {
    [_completedFullScreen removeObject:note.object]; [self sample:@"fullscreen_exit_completed"];
}
- (void)sample:(NSString *)reason {
    NSMutableArray *rows=[NSMutableArray new];
    for (NSUInteger i=0; i<_windows.count; i++) {
        NSWindow *w=_windows[i]; H21View *v=_views[i]; NSDictionary *bounds=nil;
        CFArrayRef array=CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow,(CGWindowID)w.windowNumber);
        for (NSDictionary *item in (__bridge NSArray *)array) {
            if ([item[(__bridge id)kCGWindowOwnerPID] intValue]==getpid()
                && [item[(__bridge id)kCGWindowNumber] integerValue]==w.windowNumber) {
                bounds=item[(__bridge id)kCGWindowBounds]; break;
            }
        }
        if (array) CFRelease(array);
        [rows addObject:@{@"index":@(i), @"window_id":@(w.windowNumber),
            @"bounds":bounds?:[NSNull null], @"visible":@(w.visible),
            @"miniaturized":@(w.miniaturized), @"on_active_space":@(w.onActiveSpace),
            @"native_fullscreen":@((w.styleMask & NSWindowStyleMaskFullScreen)!=0),
            @"fullscreen_transition_complete":@([_completedFullScreen containsObject:w]),
            @"backing_scale":@(w.backingScaleFactor),
            @"draws":@(v.draws), @"tick":@(v.tick)}];
    }
    emit(@{@"event":@"state", @"reason":reason, @"sequence":@(_sequence),
        @"pid":@(getpid()), @"uptime_s":@(NSProcessInfo.processInfo.systemUptime),
        @"active":@(NSApp.active), @"audio_enabled":@(fixtureAudioEnabled),
        @"audio_frames":@(atomic_load(&fixtureAudioFrames)), @"windows":rows});
}
- (void)command:(NSString *)line {
    NSArray *parts=[line componentsSeparatedByString:@" "];
    if (parts.count==1 && [line isEqual:@"quit"]) { [NSApp terminate:nil]; return; }
    if (parts.count!=2 || ![@[@"0",@"1"] containsObject:parts[1]]) {
        emit(@{@"event":@"rejected",@"reason":@"INVALID_COMMAND"}); return;
    }
    NSWindow *w=_windows[[parts[1] integerValue]]; NSString *op=parts[0];
    if ([op isEqual:@"minimize"]) [w miniaturize:nil];
    else if ([op isEqual:@"restore"]) { [w deminiaturize:nil]; [w makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES]; }
    else if ([op isEqual:@"focus"]) { [w makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES]; }
    else if ([op isEqual:@"float"]) { w.level=NSStatusWindowLevel+2; [w orderFrontRegardless]; }
    else if ([op isEqual:@"present"] && presentationDisplayUUID) {
        NSScreen *target=nil;
        for (NSScreen *screen in NSScreen.screens) {
            CGDirectDisplayID display=[screen.deviceDescription[@"NSScreenNumber"] unsignedIntValue];
            CFUUIDRef uuid=CGDisplayCreateUUIDFromDisplayID(display);
            NSString *text=uuid ? CFBridgingRelease(CFUUIDCreateString(NULL,uuid)) : nil;
            if (uuid) CFRelease(uuid);
            if ([text isEqualToString:@(presentationDisplayUUID)]) {target=screen;break;}
        }
        if (!target) {emit(@{@"event":@"rejected",@"reason":@"PRESENTATION_DISPLAY_UNAVAILABLE"});return;}
        w.level=NSNormalWindowLevel;
        [w setFrameOrigin:NSMakePoint(target.visibleFrame.origin.x+80,target.visibleFrame.origin.y+80)];
        [w makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
    }
    else if ([op isEqual:@"fullscreen"]) {
        w.collectionBehavior |= NSWindowCollectionBehaviorFullScreenPrimary;
        [w makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES]; [w toggleFullScreen:nil];
    }
    else if ([op isEqual:@"resize"]) [w setContentSize:NSMakeSize(500,300)];
    else if ([op isEqual:@"cover"]) {
        // Owned surface only: no display-mode, Spaces, Dock or global preference change.
        NSScreen *screen=w.screen;
        if (!screen) {emit(@{@"event":@"rejected",@"reason":@"SCREEN_UNAVAILABLE"}); return;}
        w.styleMask=NSWindowStyleMaskBorderless;
        w.level=NSStatusWindowLevel+1;
        [w setFrame:screen.frame display:YES]; [w orderFrontRegardless];
    }
    else if ([op isEqual:@"close"]) [w close];
    else { emit(@{@"event":@"rejected",@"reason":@"INVALID_COMMAND"}); return; }
    _sequence++; [self sample:line];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification; _started=NSProcessInfo.processInfo.systemUptime;
    if (fixtureAudioEnabled) {
        _audioEngine=[AVAudioEngine new];
        AVAudioFormat *format=[[AVAudioFormat alloc] initStandardFormatWithSampleRate:48000 channels:2];
        _audioNode=[[AVAudioSourceNode alloc] initWithFormat:format renderBlock:^OSStatus(
            BOOL *silence,const AudioTimeStamp *timestamp,AVAudioFrameCount count,AudioBufferList *buffers) {
            (void)timestamp;uint64_t first=atomic_load(&fixtureAudioFrames);bool silent=true;
            for(AVAudioFrameCount i=0;i<count;i++) {
                uint64_t sample=first+i;float value=sample%48000<9600
                    ? (float)(0.04*sin(2*M_PI*fmod((double)sample*997/48000,1.0))) : 0;
                silent &= value==0;
                for(UInt32 channel=0;channel<buffers->mNumberBuffers;channel++)
                    ((float *)buffers->mBuffers[channel].mData)[i]=value;
            }
            atomic_store(&fixtureAudioFrames,first+count);*silence=silent;return noErr;
        }];
        [_audioEngine attachNode:_audioNode];[_audioEngine connect:_audioNode to:_audioEngine.mainMixerNode format:format];
        NSError *error=nil;
        if (![_audioEngine startAndReturnError:&error]) {
            emit(@{@"event":@"failed",@"reason":@"OWNED_AUDIO_START_FAILED",@"code":@(error.code)});
            [NSApp terminate:nil];return;
        }
    }
    _windows=[NSMutableArray new]; _views=[NSMutableArray new]; _completedFullScreen=[NSMutableSet new];
    NSRect area=NSScreen.mainScreen.visibleFrame;
    for (NSUInteger i=0; i<2; i++) {
        NSWindow *w=[[NSWindow alloc] initWithContentRect:NSMakeRect(area.origin.x+60,
            area.origin.y+40+i*270, 600,240) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable
            |NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable backing:NSBackingStoreBuffered defer:NO];
        w.releasedWhenClosed=NO; w.delegate=self;
        w.title=[NSString stringWithFormat:@"Motive H21 owned window %lu",(unsigned long)i+1];
        H21View *v=[[H21View alloc] initWithFrame:w.contentView.bounds]; v.index=i;
        v.autoresizingMask=NSViewWidthSizable|NSViewHeightSizable; w.contentView=v;
        [_windows addObject:w]; [_views addObject:v]; [w makeKeyAndOrderFront:nil];
    }
    [NSApp activateIgnoringOtherApps:YES];
    __weak H21App *weakSelf=self;
    _timer=[NSTimer scheduledTimerWithTimeInterval:1.0/60 repeats:YES block:^(NSTimer *timer) {
        (void)timer; H21App *s=weakSelf; if (!s) return;
        NSTimeInterval now=NSProcessInfo.processInfo.systemUptime;
        for (H21View *v in s.views) {v.tick=(uint64_t)floor((now-s.started)*10); [v setNeedsDisplay:YES];}
        if (now-s.lastLog>=0.25) {s.lastLog=now; [s sample:@"periodic"];}
        if (now-s.started>fixtureDeadlineSeconds) [NSApp terminate:nil];
    }];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0), ^{
        char buffer[128];
        while (fgets(buffer,sizeof buffer,stdin)) {
            NSString *line=[[NSString stringWithUTF8String:buffer] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
            dispatch_async(dispatch_get_main_queue(), ^{[weakSelf command:line];});
        }
    });
    [self sample:@"ready"];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {(void)sender; return NO;}
- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification; [_timer invalidate]; [_audioEngine stop];
}
@end
int main(int argc, char **argv) {
    atomic_init(&fixtureAudioFrames,0);
    bool durationGiven=false;
    for (int i=1;i<argc;i++) {
        if (!strcmp(argv[i],"--audio") && !fixtureAudioEnabled) {fixtureAudioEnabled=true;continue;}
        if (!strcmp(argv[i],"--presentation-display-uuid") && !presentationDisplayUUID && i+1<argc) {
            presentationDisplayUUID=argv[++i];continue;
        }
        if (!strcmp(argv[i],"--seconds") && !durationGiven && i+1<argc) {
            char *end=NULL;long seconds=strtol(argv[++i],&end,10);
            if (!end || *end || seconds<1 || seconds>4200) return 64;
            fixtureDeadlineSeconds=seconds;durationGiven=true;continue;
        }
        return 64;
    }
    @autoreleasepool {
        NSApplication *app=NSApplication.sharedApplication; [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        H21App *delegate=[H21App new]; app.delegate=delegate; [app run];
    }
    return 0;
}
