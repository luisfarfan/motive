/* Independent, metadata-only observer. Never captures pixels or changes focus.
 * Only the supplied window's metadata and frontmost PID are emitted; no titles,
 * unrelated app names, accessibility permission, or global preferences. */
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#include <errno.h>
#include <limits.h>
#include <unistd.h>

static bool positive(const char *text, unsigned long limit, unsigned long *value) {
    char *end=NULL; errno=0; *value=strtoul(text,&end,10);
    return text[0]>='1' && text[0]<='9' && end && !*end && !errno && *value<=limit;
}
int main(int argc,const char **argv) {
    @autoreleasepool {
        unsigned long pid,window;
        if(argc!=3 || !positive(argv[1],INT_MAX,&pid) || !positive(argv[2],UINT32_MAX,&window)) {
            fprintf(stderr,"Usage: MotiveFocusProbe EXPECTED_PID OWNED_WINDOW_ID\n"); return 2;
        }
        double before=NSProcessInfo.processInfo.systemUptime;
        NSRunningApplication *front=NSWorkspace.sharedWorkspace.frontmostApplication;
        CFArrayRef array=CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow,(CGWindowID)window);
        NSDictionary *match=nil;
        for(NSDictionary *item in (__bridge NSArray *)array) {
            if([item[(__bridge id)kCGWindowNumber] unsignedLongValue]==window) {
                match=@{@"owner_pid":item[(__bridge id)kCGWindowOwnerPID]?:NSNull.null,
                    @"on_screen":item[(__bridge id)kCGWindowIsOnscreen]?:NSNull.null,
                    @"bounds":item[(__bridge id)kCGWindowBounds]?:NSNull.null,
                    @"layer":item[(__bridge id)kCGWindowLayer]?:NSNull.null}; break;
            }
        }
        if(array)CFRelease(array);
        NSDictionary *result=@{@"version":@1,@"observer_pid":@(getpid()),
            @"clock":@"NSProcessInfo.systemUptime",@"before_s":@(before),
            @"after_s":@(NSProcessInfo.processInfo.systemUptime),
            @"expected_pid":@(pid),@"window_id":@(window),
            @"frontmost_pid":front?@(front.processIdentifier):NSNull.null,
            @"frontmost_terminated":front?@((bool)front.terminated):NSNull.null,
            @"window":match?:NSNull.null,@"proves_published_pixels":@NO};
        NSData *json=[NSJSONSerialization dataWithJSONObject:result options:0 error:nil];
        if(!json)return 1;
        fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);
    }
    return 0;
}
