// Original controlled external-window fixture. No screen or device capture.
#import <AppKit/AppKit.h>
@interface FixtureView : NSView
@property double phase;
@end
@implementation FixtureView
- (void)drawRect:(NSRect)rect {
    [[NSColor colorWithSRGBRed:0.07 green:0.12 blue:0.20 alpha:1] setFill]; NSRectFill(self.bounds);
    NSArray *colors=@[NSColor.systemTealColor,NSColor.systemBlueColor,NSColor.systemOrangeColor];
    for (int i=0;i<3;i++) { [colors[i] setFill]; NSRectFill(NSMakeRect(i*240,0,240,100)); }
    [NSColor.whiteColor setFill]; NSRectFill(NSMakeRect(40+fmod(self.phase*100,550),190,70,70));
    [@"MOTIVE / EXTERNAL WINDOW TEST" drawAtPoint:NSMakePoint(30,330)
        withAttributes:@{NSFontAttributeName:[NSFont boldSystemFontOfSize:25],NSForegroundColorAttributeName:NSColor.whiteColor}];
}
@end
@interface FixtureApp : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSWindow *window;
@end
@implementation FixtureApp
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    NSWindow *window=[[NSWindow alloc] initWithContentRect:NSMakeRect(150,150,720,420)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable backing:NSBackingStoreBuffered defer:NO];
    self.window=window;
    window.title=@"Motive External Fixture"; window.releasedWhenClosed=NO;
    FixtureView *view=[[FixtureView alloc] initWithFrame:NSMakeRect(0,0,720,420)]; window.contentView=view;
    [NSTimer scheduledTimerWithTimeInterval:0.05 repeats:YES block:^(NSTimer *timer) { view.phase+=.05; view.needsDisplay=YES; }];
    [window makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
}
@end
int main(void) { @autoreleasepool {
    NSApplication *app=[NSApplication sharedApplication];
    [app setActivationPolicy:NSApplicationActivationPolicyRegular];
    FixtureApp *delegate=[FixtureApp new]; app.delegate=delegate; [app run];
} return 0; }
