/* Position only this game's own NSWindow. No fullscreen Space, display mode,
 * application hiding, Dock change or global preference is used. */
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#include <unistd.h>
int h21_game_cover(void *native, const char *uuid) {
    NSWindow *window = (__bridge NSWindow *)native;
    if (![window isKindOfClass:NSWindow.class]) return 0;
    for (NSScreen *screen in NSScreen.screens) {
        CGDirectDisplayID display = [screen.deviceDescription[@"NSScreenNumber"] unsignedIntValue];
        CFUUIDRef value = CGDisplayCreateUUIDFromDisplayID(display);
        if (!value) continue;
        CFStringRef text = CFUUIDCreateString(NULL, value);
        BOOL match = [(__bridge NSString *)text isEqualToString:[NSString stringWithUTF8String:uuid]];
        CFRelease(text); CFRelease(value);
        if (!match) continue;
        window.styleMask = NSWindowStyleMaskBorderless;
        window.level = NSStatusWindowLevel + 2;
        [window setFrame:screen.frame display:YES];
        [window makeKeyAndOrderFront:nil];
        printf("{\"event\":\"ready\",\"pid\":%d,\"window_id\":%ld,\"display_uuid\":\"%s\",\"width\":%.0f,\"height\":%.0f}\n",
            getpid(), (long)window.windowNumber, uuid, screen.frame.size.width, screen.frame.size.height);
        fflush(stdout);
        return 1;
    }
    return 0;
}
