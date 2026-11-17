/* Owned, standalone audio source for H13. It does not capture any content,
 * change devices/volume, or use a network. The AVAudioEngine render callback
 * owns sample position; the UI only observes it and requests fixture modes. */
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#include <stdatomic.h>
#include <math.h>

typedef struct {
    atomic_int mode; // 0 tone, 1 zero buffers, 2 paused engine, 3 pulsed tone
    atomic_uint_fast64_t frames;
    double frequency,rate;
} FixtureSignal;

@interface FixtureView : NSView
@property(nonatomic,assign) FixtureSignal *signal;
@end
@implementation FixtureView
- (void)drawRect:(NSRect)dirty {
    (void)dirty;int mode=atomic_load(&_signal->mode);
    uint64_t frames=atomic_load(&_signal->frames);
    bool pulse=mode==0 || (mode==3 && (frames%(uint64_t)_signal->rate)<(uint64_t)(_signal->rate*0.2));
    [(pulse?[NSColor colorWithRed:0.10 green:0.65 blue:0.35 alpha:1]:[NSColor colorWithWhite:0.08 alpha:1]) setFill];
    NSRectFill(self.bounds);
    NSString *states[] = {@"TONE",@"ZERO BUFFERS",@"ENGINE PAUSED",@"PULSED TONE"};
    NSString *label=[NSString stringWithFormat:@"Motive owned audio fixture\n%@  %.0f Hz  -24 dBFS peak\n%llu rendered frames\nT: tone   Z: zeros   P: pause   B: pulses   S: sequence",
        states[mode],_signal->frequency,(unsigned long long)frames];
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
@end
@implementation FixtureApp
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
    _signal=calloc(1,sizeof(*_signal));_signal->rate=48000;_signal->frequency=997;
    atomic_init(&_signal->mode,1);atomic_init(&_signal->frames,0);
    NSArray<NSString *> *args=NSProcessInfo.processInfo.arguments;
    NSUInteger frequency=[args indexOfObject:@"--frequency"];
    if(frequency!=NSNotFound) {
        if(frequency+1>=args.count)exit(2);
        NSScanner *scanner=[NSScanner scannerWithString:args[frequency+1]];double value=0;
        if(![scanner scanDouble:&value] || !scanner.isAtEnd || !isfinite(value) || value<100 || value>10000)exit(2);
        _signal->frequency=value;
    }
    _engine=[AVAudioEngine new];FixtureSignal *signal=_signal;
    AVAudioFormat *format=[[AVAudioFormat alloc] initStandardFormatWithSampleRate:signal->rate channels:2];
    _node=[[AVAudioSourceNode alloc] initWithFormat:format renderBlock:^OSStatus(BOOL *isSilence,const AudioTimeStamp *timestamp,AVAudioFrameCount count,AudioBufferList *buffers) {
        (void)timestamp;int mode=atomic_load(&signal->mode);
        uint64_t first=atomic_fetch_add(&signal->frames,count);bool silent=true;
        for(AVAudioFrameCount i=0;i<count;i++) {
            uint64_t sample=first+i;
            bool on=mode==0 || (mode==3 && (sample%(uint64_t)signal->rate)<(uint64_t)(signal->rate*0.2));
            float value=on?(float)(0.0630957344*sin(2*M_PI*fmod((double)sample*signal->frequency/signal->rate,1.0))):0;
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
    }];
    printf("{\"event\":\"ready\",\"bundle_id\":\"local.motive.audiofixture\",\"pid\":%d,\"frequency_hz\":%.3f,\"sample_rate\":48000,\"peak_dbfs\":-24}\n",NSProcessInfo.processInfo.processIdentifier,signal->frequency);fflush(stdout);
    if([args containsObject:@"--sequence"])[self startSequence:nil];
    else [self setMode:[args containsObject:@"--paused"]?2:0];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {(void)sender;return YES;}
- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification;[_timer invalidate];[_engine stop];[_engine disconnectNodeOutput:_node];[_engine detachNode:_node];
    // Node block may outlive detach until AVAudioEngine cleanup. Keep its tiny
    // signal allocation until process termination rather than risking UAF.
}
@end
int main(void) {
    @autoreleasepool {NSApplication *app=NSApplication.sharedApplication;[app setActivationPolicy:NSApplicationActivationPolicyRegular];FixtureApp *delegate=[FixtureApp new];app.delegate=delegate;[app run];}
    return 0;
}
