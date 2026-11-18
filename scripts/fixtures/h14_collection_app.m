/* Owned H14 publication experiment. No capture, audio, network, preferences,
 * private APIs or offscreen snapshots. A/B differs ONLY in collectionBehavior.
 * A new process is required for each arm. drawRect and CG metadata are not
 * evidence that WindowServer published fresh pixels to ScreenCaptureKit. */
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#include <math.h>
#include <unistd.h>

static NSString *collectionArm;
static void emit(NSDictionary *event) {
    NSData *json=[NSJSONSerialization dataWithJSONObject:event options:0 error:nil];
    if(json) { fwrite(json.bytes,1,json.length,stdout); fputc('\n',stdout); fflush(stdout); }
}

@interface H14CollectionView : NSView
@property(nonatomic) uint64_t tick;
@property(nonatomic) uint64_t drawCount;
@property(nonatomic) uint64_t lastDrawTick;
@end
@implementation H14CollectionView
- (void)drawRect:(NSRect)dirty {
    (void)dirty; _drawCount++; _lastDrawTick=_tick;
    [[NSColor colorWithRed:0.07 green:0.16 blue:0.24 alpha:1] setFill]; NSRectFill(self.bounds);
    // 16-bit little-endian pixel counter; leftmost block is bit 0. Geometry is
    // fixed in AppKit points and logged with the window's backingScaleFactor.
    for(unsigned bit=0;bit<16;bit++) {
        [((_tick>>bit)&1 ? NSColor.whiteColor:NSColor.blackColor) setFill];
        NSRectFill(NSMakeRect(24+bit*36,24,30,48));
    }
    NSString *text=[NSString stringWithFormat:@"H14 / OWNED COLLECTION FIXTURE\ntick %llu\n10 Hz content · 30 Hz draw requests",
        (unsigned long long)_tick];
    [text drawInRect:NSMakeRect(24,100,632,115) withAttributes:@{
        NSFontAttributeName:[NSFont monospacedSystemFontOfSize:20 weight:NSFontWeightMedium],
        NSForegroundColorAttributeName:NSColor.whiteColor}];
}
@end

@interface H14CollectionApp : NSObject <NSApplicationDelegate>
@property(nonatomic,strong) NSWindow *window;
@property(nonatomic,strong) H14CollectionView *view;
@property(nonatomic,strong) NSTimer *timer;
@property(nonatomic) NSTimeInterval started;
@property(nonatomic) NSTimeInterval lastLog;
@property(nonatomic) NSUInteger initialBehavior;
@end
@implementation H14CollectionApp
- (void)sample:(NSString *)reason {
    NSWindow *window=_window;
    // The query is restricted to our exact window number; discard any result
    // whose owner PID/number differs. No window titles or other app data logged.
    CFArrayRef array=CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow,
        (CGWindowID)window.windowNumber);
    NSDictionary *own=nil;
    for(NSDictionary *item in (__bridge NSArray *)array) {
        if([item[(__bridge id)kCGWindowOwnerPID] intValue]==getpid()
            && [item[(__bridge id)kCGWindowNumber] integerValue]==window.windowNumber) {
            own=@{@"on_screen":item[(__bridge id)kCGWindowIsOnscreen]?:[NSNull null],
                @"layer":item[(__bridge id)kCGWindowLayer]?:[NSNull null],
                @"alpha":item[(__bridge id)kCGWindowAlpha]?:[NSNull null],
                @"bounds":item[(__bridge id)kCGWindowBounds]?:[NSNull null]}; break;
        }
    }
    if(array)CFRelease(array);
    emit(@{@"event":@"window_state",@"reason":reason,@"arm":collectionArm,
        @"uptime_seconds":@(NSProcessInfo.processInfo.systemUptime),
        @"pid":@(getpid()),@"window_id":@(window.windowNumber),
        @"window_class":NSStringFromClass(window.class),@"view_class":NSStringFromClass(_view.class),
        @"initial_collection_behavior":@(_initialBehavior),@"collection_behavior":@(window.collectionBehavior),
        @"window_level":@(window.level),@"style_mask":@(window.styleMask),
        @"appkit_frame":@{@"width":@(window.frame.size.width),@"height":@(window.frame.size.height)},
        @"appkit_content":@{@"width":@(_view.bounds.size.width),@"height":@(_view.bounds.size.height)},
        @"window_visible":@((bool)window.visible),@"window_occlusion_visible":@((bool)(window.occlusionState & NSWindowOcclusionStateVisible)),
        @"on_active_space":@((bool)window.onActiveSpace),@"miniaturized":@((bool)window.miniaturized),
        @"key_window":@((bool)window.keyWindow),@"hides_on_deactivate":@((bool)window.hidesOnDeactivate),
        @"opaque":@((bool)window.opaque),@"sharing_type":@(window.sharingType),
        @"backing_scale":@(window.backingScaleFactor),@"view_layer_backed":@((bool)_view.wantsLayer),
        @"app_active":@((bool)NSApp.active),@"app_hidden":@((bool)NSApp.hidden),
        @"app_occlusion_visible":@((bool)(NSApp.occlusionState & NSApplicationOcclusionStateVisible)),
        @"tick_requested":@(_view.tick),@"tick_drawn":@(_view.lastDrawTick),@"draw_count":@(_view.drawCount),
        @"cg_own_window_metadata":own?:[NSNull null],@"proves_published_pixels":@NO});
}
- (void)changed:(NSNotification *)notification {[self sample:notification.name];}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification; _started=NSProcessInfo.processInfo.systemUptime;
    _window=[[NSWindow alloc] initWithContentRect:NSMakeRect(160,160,680,240)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable
        backing:NSBackingStoreBuffered defer:NO];
    _initialBehavior=_window.collectionBehavior;
    if([collectionArm isEqual:@"join-all"]) {
        NSWindowCollectionBehavior exclusive=NSWindowCollectionBehaviorPrimary
            |NSWindowCollectionBehaviorAuxiliary|NSWindowCollectionBehaviorCanJoinAllApplications;
        _window.collectionBehavior=(_window.collectionBehavior & ~exclusive)
            |NSWindowCollectionBehaviorCanJoinAllApplications;
    }
    _window.title=@"Motive H14 owned collection fixture";
    _view=[[H14CollectionView alloc] initWithFrame:_window.contentView.bounds]; _window.contentView=_view;
    NSNotificationCenter *center=NSNotificationCenter.defaultCenter;
    for(NSNotificationName name in @[NSWindowDidChangeOcclusionStateNotification,
        NSWindowDidBecomeKeyNotification,NSWindowDidResignKeyNotification,
        NSWindowDidMiniaturizeNotification,NSWindowDidDeminiaturizeNotification,
        NSWindowDidChangeScreenNotification]) [center addObserver:self selector:@selector(changed:) name:name object:_window];
    for(NSNotificationName name in @[NSApplicationDidBecomeActiveNotification,
        NSApplicationDidResignActiveNotification,NSApplicationDidChangeOcclusionStateNotification])
        [center addObserver:self selector:@selector(changed:) name:name object:NSApp];
    NSMenu *menu=[NSMenu new]; NSMenuItem *root=[NSMenuItem new]; [menu addItem:root];
    root.submenu=[NSMenu new]; [root.submenu addItemWithTitle:@"Quit fixture" action:@selector(terminate:) keyEquivalent:@"q"]; NSApp.mainMenu=menu;
    [_window makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
    __weak H14CollectionApp *weakSelf=self;
    _timer=[NSTimer scheduledTimerWithTimeInterval:1.0/30 repeats:YES block:^(NSTimer *timer) {
        (void)timer; H14CollectionApp *strong=weakSelf; if(!strong)return;
        NSTimeInterval now=NSProcessInfo.processInfo.systemUptime;
        strong.view.tick=(uint64_t)floor((now-strong.started)*10);
        [strong.view setNeedsDisplay:YES]; [strong.view displayIfNeeded];
        if(now-strong.lastLog>=1) {strong.lastLog=now; [strong sample:@"periodic"];}
    }];
    emit(@{@"event":@"ready",@"pid":@(getpid()),@"window_id":@(_window.windowNumber),
        @"bundle_id":NSBundle.mainBundle.bundleIdentifier?:[NSNull null],@"arm":collectionArm,
        @"content_hz":@10,@"draw_request_hz":@30,@"audio":@NO,@"capture":@NO,
        @"offscreen_snapshots":@NO,@"global_preferences_changed":@NO,
        @"counter":@{@"bits":@16,@"least_significant_bit":@"left",@"x":@24,@"y":@24,
            @"step_points":@36,@"width_points":@30,@"height_points":@48,@"coordinate_origin":@"bottom_left"}});
    [self sample:@"ready"];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {(void)sender;return YES;}
- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification; [_timer invalidate]; [NSNotificationCenter.defaultCenter removeObserver:self];
}
@end
int main(void) {
    @autoreleasepool {
        NSArray<NSString *> *args=NSProcessInfo.processInfo.arguments;
        if(args.count!=3 || ![args[1] isEqual:@"--collection-arm"]
            || ![@[@"default",@"join-all"] containsObject:args[2]]) {
            fprintf(stderr,"Usage: MotiveCollectionFixture --collection-arm default|join-all\n"); return 2;
        }
        collectionArm=args[2]; NSApplication *app=NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        H14CollectionApp *delegate=[H14CollectionApp new]; app.delegate=delegate; [app run];
    }
    return 0;
}
