#import <AppKit/AppKit.h>
#include <stdatomic.h>
#include <stdbool.h>

/* Public AppKit termination policy. No libobs, GPUI state, main-thread waits,
 * method replacement, private selectors, or private delegate class knowledge.
 * GPUI's on_app_quit is a non-cancellable final notification (200 ms timeout);
 * media shutdown must finish before that notification is allowed to run.
 * AppKit: https://developer.apple.com/documentation/appkit/nsapplicationdelegate
 * Supported request paths: app menu, Cmd-Q, window close and ordinary Dock Quit.
 * Forced process termination and logout/shutdown behavior are not guaranteed.
 * Pinned GPUI macOS 0.3.12 delegate audit: delegate reads for menus and system
 * observers dispatch selectors; teardown reads framework-specific state from
 * the original identity, hence restoration before the final quit request. */
static atomic_bool quit_requested;
static atomic_bool quit_authorized;

@interface MotiveTerminationDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) id<NSApplicationDelegate> originalDelegate;
@end

@implementation MotiveTerminationDelegate
- (BOOL)respondsToSelector:(SEL)selector {
    return [super respondsToSelector:selector] || [self.originalDelegate respondsToSelector:selector];
}
- (id)forwardingTargetForSelector:(SEL)selector {
    if ([self.originalDelegate respondsToSelector:selector]) return self.originalDelegate;
    return [super forwardingTargetForSelector:selector];
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    if (atomic_load(&quit_authorized)) return NSTerminateNow;
    atomic_store(&quit_requested,true);
    // Cancel this native attempt. The owner can display a non-blocking GPUI
    // confirmation, finalize outputs, then make a new authorized quit request.
    return NSTerminateCancel;
}
@end

// NSApplication's delegate is not retained. Keep both proxy and original alive
// through termination; other framework objects can retain their delegate target.
static MotiveTerminationDelegate *termination_delegate;

bool motive_lifecycle_install(void) {
    if (![NSThread isMainThread] || !NSApp) return false;
    if (termination_delegate) return NSApp.delegate==termination_delegate;
    id<NSApplicationDelegate> original=NSApp.delegate;
    if (!original) return false;
    MotiveTerminationDelegate *next=[MotiveTerminationDelegate new];
    next.originalDelegate=original;
    atomic_store(&quit_requested,false);atomic_store(&quit_authorized,false);
    NSApp.delegate=next;
    if (NSApp.delegate!=next) return false;
    termination_delegate=next;
    return true;
}
bool motive_lifecycle_take_quit_request(void) {
    return atomic_exchange(&quit_requested,false);
}
bool motive_lifecycle_allow_quit(void) {
    if (![NSThread isMainThread] || !NSApp || !termination_delegate) return false;
    // Fail closed if another subsystem replaced the delegate. Do not bypass an
    // unknown termination policy. A repeated authorization remains idempotent.
    if (atomic_load(&quit_authorized)) return NSApp.delegate==termination_delegate.originalDelegate;
    if (NSApp.delegate!=termination_delegate || !termination_delegate.originalDelegate) return false;
    // Restore the framework's original identity before its shutdown/cleanup.
    // Forwarded runtime callbacks have always executed with that original self.
    NSApp.delegate=termination_delegate.originalDelegate;
    if (NSApp.delegate!=termination_delegate.originalDelegate) return false;
    atomic_store(&quit_authorized,true);
    return true;
}
