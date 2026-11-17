/* Owned, standalone audio source for H13. It does not capture any content,
 * change devices/volume, or use a network. The AVAudioEngine render callback
 * owns sample position; the UI only observes it and requests fixture modes. */
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#include <stdatomic.h>
#include <math.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>

typedef struct {
    atomic_int mode; // 0 tone, 1 zero buffers, 2 paused engine, 3 pulsed tone
    atomic_uint_fast64_t frames;
    double frequency,rate,amplitude,peak_dbfs;
} FixtureSignal;

@interface FixtureView : NSView
@property(nonatomic,assign) FixtureSignal *signal;
@property(nonatomic,assign) uint64_t drawCount;
@property(nonatomic,assign) uint64_t lastDrawAudioFrame;
@end
@implementation FixtureView
- (void)drawRect:(NSRect)dirty {
    (void)dirty;int mode=atomic_load(&_signal->mode);
    uint64_t frames=atomic_load(&_signal->frames);
    _drawCount++;_lastDrawAudioFrame=frames;
    bool pulse=mode==0 || (mode==3 && (frames%(uint64_t)_signal->rate)<(uint64_t)(_signal->rate*0.2));
    [(pulse?[NSColor colorWithRed:0.10 green:0.65 blue:0.35 alpha:1]:[NSColor colorWithWhite:0.08 alpha:1]) setFill];
    NSRectFill(self.bounds);
    NSString *states[] = {@"TONE",@"ZERO BUFFERS",@"ENGINE PAUSED",@"PULSED TONE"};
    NSString *label=[NSString stringWithFormat:@"Motive owned audio fixture\n%@  %.0f Hz  %.0f dBFS peak\n%llu rendered frames\nT: tone   Z: zeros   P: pause   B: pulses   S: sequence",
        states[mode],_signal->frequency,_signal->peak_dbfs,(unsigned long long)frames];
    [label drawInRect:NSInsetRect(self.bounds,24,28) withAttributes:@{NSFontAttributeName:[NSFont monospacedSystemFontOfSize:19 weight:NSFontWeightMedium],NSForegroundColorAttributeName:NSColor.whiteColor}];
}
@end

@interface FixtureApp : NSObject <NSApplicationDelegate>
@property(nonatomic,strong) NSWindow *window;
@property(nonatomic,strong) FixtureView *view;
@property(nonatomic,strong) AVAudioEngine *engine;
@property(nonatomic,strong) AVAudioSourceNode *node;
@property(nonatomic,strong) NSTimer *timer;
@property(nonatomic,assign) FixtureSignal *signal;
@property(nonatomic,assign) BOOL sequence;
@property(nonatomic,assign) NSTimeInterval sequenceStart;
@property(nonatomic,assign) NSTimeInterval lastDrawLog;
@property(nonatomic,assign) int snapshotDirectoryFD;
@property(nonatomic,assign) uint64_t snapshotCount;
@property(nonatomic,assign) uint64_t snapshotBytes;
@property(nonatomic,assign) NSTimeInterval nextSnapshot;
@property(nonatomic,assign) BOOL snapshotsStopped;
@end
@implementation FixtureApp
- (void)snapshotEvent:(NSDictionary *)event {
    NSData *json=[NSJSONSerialization dataWithJSONObject:event options:0 error:nil];
    if(json) {fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);fflush(stdout);}
}
- (void)stopSnapshots:(NSString *)reason error:(int)error {
    _snapshotsStopped=YES;
    [self snapshotEvent:@{@"event":@"snapshot_stopped",@"reason":reason,@"errno":@(error),
        @"count":@(_snapshotCount),@"bytes":@(_snapshotBytes)}];
}
- (void)snapshotIfDue:(NSTimeInterval)now {
    if(_snapshotDirectoryFD<0 || _snapshotsStopped || now<_nextSnapshot)return;
    // At most 1 Hz normally and 5 Hz for the eight-second pulse section, which
    // samples the 200 ms pulse. Hard caps bound diagnostic CPU/disk use.
    int mode=atomic_load(&_signal->mode);
    _nextSnapshot=now+(mode==3?0.2:1.0);
    if(_snapshotCount>=120 || _snapshotBytes>=32*1024*1024) {
        [self stopSnapshots:@"diagnostic_limit" error:0];return;
    }
    uint64_t requested=atomic_load(&_signal->frames),draws_before=_view.drawCount;
    NSBitmapImageRep *bitmap=[_view bitmapImageRepForCachingDisplayInRect:_view.bounds];
    if(!bitmap) {[self stopSnapshots:@"bitmap_unavailable" error:0];return;}
    // This renders the actual NSView into an offscreen bitmap. It deliberately
    // does NOT claim to inspect WindowServer's published backing surface. The
    // extra draw may itself affect publication; log that intervention explicitly.
    [_view cacheDisplayInRect:_view.bounds toBitmapImageRep:bitmap];
    uint64_t drawn=_view.lastDrawAudioFrame;
    NSData *png=[bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    if(!png || !png.length || png.length>4*1024*1024 || _snapshotBytes+png.length>32*1024*1024) {
        [self stopSnapshots:@"snapshot_size_limit" error:0];return;
    }
    uint64_t index=++_snapshotCount;
    NSString *filename=[NSString stringWithFormat:@"local-view-%04llu-audio-%012llu.png",(unsigned long long)index,(unsigned long long)drawn];
    int fd=openat(_snapshotDirectoryFD,filename.fileSystemRepresentation,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0) {[self stopSnapshots:@"snapshot_create_failed" error:errno];return;}
    const uint8_t *bytes=png.bytes;size_t offset=0;int failed=0;
    while(offset<png.length) {
        ssize_t count=write(fd,bytes+offset,png.length-offset);
        if(count<0 && errno==EINTR)continue;
        if(count<=0) {failed=count<0?errno:EIO;break;}
        offset+=(size_t)count;
    }
    if(close(fd) && !failed)failed=errno;
    if(failed) {[self stopSnapshots:@"snapshot_write_failed" error:failed];return;}
    _snapshotBytes+=png.length;
    NSColor *background=[[bitmap colorAtX:MIN(8,bitmap.pixelsWide-1) y:bitmap.pixelsHigh/2]
        colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
    id rgb=background?@[@(background.redComponent),@(background.greenComponent),@(background.blueComponent)]:[NSNull null];
    [self snapshotEvent:@{@"event":@"snapshot",@"file":filename,@"index":@(index),
        @"uptime_before":@(now),@"uptime_after":@(NSProcessInfo.processInfo.systemUptime),
        @"audio_frame_requested":@(requested),@"audio_frame_drawn":@(drawn),@"mode":@(mode),
        @"draw_count_before":@(draws_before),@"draw_count_after":@(_view.drawCount),
        @"background_rgb":rgb,@"pixel_width":@(bitmap.pixelsWide),@"pixel_height":@(bitmap.pixelsHigh),
        @"png_bytes":@(png.length),@"redraws_view":@YES,@"proves_windowserver_publication":@NO,
        @"window_visible":@((bool)_window.visible),@"occlusion_visible":@((bool)(_window.occlusionState & NSWindowOcclusionStateVisible))}];
}
- (void)setMode:(int)mode {
    int previous=atomic_exchange(&_signal->mode,mode);
    if(mode==2) [_engine pause];
    else if(!_engine.running) {
        NSError *error=nil;
        if(![_engine startAndReturnError:&error]) {
            fprintf(stderr,"fixture audio engine failed: %s\n",error.localizedDescription.UTF8String);
            [NSApp terminate:nil];return;
        }
    }
    if(previous!=mode) {
        printf("{\"event\":\"mode\",\"mode\":%d,\"uptime_seconds\":%.6f,\"frames\":%llu}\n",mode,
            NSProcessInfo.processInfo.systemUptime,(unsigned long long)atomic_load(&_signal->frames));fflush(stdout);
    }
}
- (void)manual:(NSMenuItem *)sender {_sequence=NO;[self setMode:(int)sender.tag];}
- (void)startSequence:(id)sender {
    (void)sender;_sequence=YES;_sequenceStart=NSProcessInfo.processInfo.systemUptime;[self setMode:0];
    printf("{\"event\":\"sequence\",\"uptime_seconds\":%.6f}\n",_sequenceStart);fflush(stdout);
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    _snapshotDirectoryFD=-1;
    _signal=calloc(1,sizeof(*_signal));_signal->rate=48000;_signal->frequency=997;_signal->peak_dbfs=-24;
    atomic_init(&_signal->mode,1);atomic_init(&_signal->frames,0);
    NSArray<NSString *> *args=NSProcessInfo.processInfo.arguments;
    NSUInteger snapshot=[args indexOfObject:@"--snapshot-dir"];
    if(snapshot!=NSNotFound) {
        if(snapshot+1>=args.count)exit(2);
        NSString *directory=args[snapshot+1];struct stat info;
        if(!directory.isAbsolutePath || lstat(directory.fileSystemRepresentation,&info) || !S_ISDIR(info.st_mode)) {
            fprintf(stderr,"snapshot-dir must be an existing absolute directory, not a symlink\n");exit(2);
        }
        _snapshotDirectoryFD=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        if(_snapshotDirectoryFD<0) {fprintf(stderr,"unable to open snapshot directory\n");exit(2);}
        [self snapshotEvent:@{@"event":@"snapshots_enabled",@"normal_hz":@1,@"pulse_hz":@5,
            @"max_snapshots":@120,@"max_total_bytes":@(32*1024*1024),
            @"method":@"NSView cacheDisplay into local bitmap",
            @"limitation":@"Extra redraw may influence publication; local bitmap does not prove WindowServer or SCK freshness."}];
    }
    NSUInteger frequency=[args indexOfObject:@"--frequency"];
    if(frequency!=NSNotFound) {
        if(frequency+1>=args.count)exit(2);
        NSScanner *scanner=[NSScanner scannerWithString:args[frequency+1]];double value=0;
        if(![scanner scanDouble:&value] || !scanner.isAtEnd || !isfinite(value) || value<100 || value>10000)exit(2);
        _signal->frequency=value;
    }
    NSUInteger level=[args indexOfObject:@"--peak-dbfs"];
    if(level!=NSNotFound) {
        if(level+1>=args.count)exit(2);
        NSScanner *scanner=[NSScanner scannerWithString:args[level+1]];double value=0;
        if(![scanner scanDouble:&value] || !scanner.isAtEnd || !isfinite(value) || value < -60 || value > -12)exit(2);
        _signal->peak_dbfs=value;
    }
    _signal->amplitude=pow(10,_signal->peak_dbfs/20);
    _engine=[AVAudioEngine new];FixtureSignal *signal=_signal;
    AVAudioFormat *format=[[AVAudioFormat alloc] initStandardFormatWithSampleRate:signal->rate channels:2];
    _node=[[AVAudioSourceNode alloc] initWithFormat:format renderBlock:^OSStatus(BOOL *isSilence,const AudioTimeStamp *timestamp,AVAudioFrameCount count,AudioBufferList *buffers) {
        (void)timestamp;int mode=atomic_load(&signal->mode);
        uint64_t first=atomic_fetch_add(&signal->frames,count);bool silent=true;
        for(AVAudioFrameCount i=0;i<count;i++) {
            uint64_t sample=first+i;
            bool on=mode==0 || (mode==3 && (sample%(uint64_t)signal->rate)<(uint64_t)(signal->rate*0.2));
            float value=on?(float)(signal->amplitude*sin(2*M_PI*fmod((double)sample*signal->frequency/signal->rate,1.0))):0;
            silent &= value==0;
            for(UInt32 channel=0;channel<buffers->mNumberBuffers;channel++)((float *)buffers->mBuffers[channel].mData)[i]=value;
        }
        *isSilence=silent;return noErr;
    }];
    [_engine attachNode:_node];[_engine connect:_node to:_engine.mainMixerNode format:format];
    _engine.mainMixerNode.outputVolume=1;
    _window=[[NSWindow alloc] initWithContentRect:NSMakeRect(160,160,680,240)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable backing:NSBackingStoreBuffered defer:NO];
    _window.title=@"Motive controlled audio fixture";
    _view=[[FixtureView alloc] initWithFrame:_window.contentView.bounds];_view.signal=signal;
    _window.contentView=_view;[_window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
    NSMenu *menu=[NSMenu new];NSMenuItem *root=[NSMenuItem new];[menu addItem:root];NSMenu *actions=[NSMenu new];root.submenu=actions;
    NSString *titles[]={@"Tone",@"Zero buffers",@"Pause engine",@"Pulses"};NSString *keys[]={@"t",@"z",@"p",@"b"};
    for(int i=0;i<4;i++) {NSMenuItem *item=[[NSMenuItem alloc] initWithTitle:titles[i] action:@selector(manual:) keyEquivalent:keys[i]];item.target=self;item.tag=i;[actions addItem:item];}
    NSMenuItem *sequence=[[NSMenuItem alloc] initWithTitle:@"Start sequence" action:@selector(startSequence:) keyEquivalent:@"s"];sequence.target=self;[actions addItem:sequence];
    [actions addItem:[NSMenuItem separatorItem]];[actions addItemWithTitle:@"Quit fixture" action:@selector(terminate:) keyEquivalent:@"q"];NSApp.mainMenu=menu;
    __weak FixtureApp *weakSelf=self;
    _timer=[NSTimer scheduledTimerWithTimeInterval:1.0/30 repeats:YES block:^(NSTimer *timer) {
        (void)timer;FixtureApp *strong=weakSelf;if(!strong)return;
        if(strong.sequence) {
            double elapsed=NSProcessInfo.processInfo.systemUptime-strong.sequenceStart;
            int mode=elapsed<8?0:elapsed<12?1:elapsed<16?2:elapsed<24?0:elapsed<32?3:0;
            if(mode!=atomic_load(&strong.signal->mode))[strong setMode:mode];
        }
        [strong.view setNeedsDisplay:YES];
        // Ask AppKit to perform the real draw now, including while another
        // application is frontmost. This is not proof WindowServer/SCK delivers
        // it: the bounded observations below distinguish those failure layers.
        [strong.view displayIfNeeded];
        double now=NSProcessInfo.processInfo.systemUptime;
        if(now-strong.lastDrawLog>=1) {
            strong.lastDrawLog=now;
            printf("{\"event\":\"drawing\",\"uptime_seconds\":%.6f,\"draw_count\":%llu,\"last_draw_audio_frame\":%llu,\"audio_frames\":%llu,\"window_visible\":%s,\"occlusion_visible\":%s}\n",
                now,(unsigned long long)strong.view.drawCount,(unsigned long long)strong.view.lastDrawAudioFrame,
                (unsigned long long)atomic_load(&strong.signal->frames),strong.window.visible?"true":"false",
                (strong.window.occlusionState & NSWindowOcclusionStateVisible)?"true":"false");fflush(stdout);
        }
        [strong snapshotIfDue:now];
    }];
    printf("{\"event\":\"ready\",\"bundle_id\":\"local.motive.audiofixture\",\"pid\":%d,\"frequency_hz\":%.3f,\"sample_rate\":48000,\"peak_dbfs\":%.3f}\n",NSProcessInfo.processInfo.processIdentifier,signal->frequency,signal->peak_dbfs);fflush(stdout);
    if([args containsObject:@"--sequence"])[self startSequence:nil];
    else [self setMode:[args containsObject:@"--paused"]?2:0];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {(void)sender;return YES;}
- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification;[_timer invalidate];[_engine stop];[_engine disconnectNodeOutput:_node];[_engine detachNode:_node];
    if(_snapshotDirectoryFD>=0) {close(_snapshotDirectoryFD);_snapshotDirectoryFD=-1;}
    // Node block may outlive detach until AVAudioEngine cleanup. Keep its tiny
    // signal allocation until process termination rather than risking UAF.
}
@end
int main(void) {
    @autoreleasepool {NSApplication *app=NSApplication.sharedApplication;[app setActivationPolicy:NSApplicationActivationPolicyRegular];FixtureApp *delegate=[FixtureApp new];app.delegate=delegate;[app run];}
    return 0;
}
