/* Target discovery/control only. The official sck_audio_capture module owns
 * SCStream and forwards its original PTS to libobs. No samples pass here.
 * Requires ScreenCaptureKit.framework; never requests or changes permission. */
#import <ScreenCaptureKit/ScreenCaptureKit.h>

static bool audio_is_system(const audio_input *a) {return a->kind==2 || a->kind==3;}
static const char *audio_fault_name(int fault) {
    static const char *names[]={"","DEVICE_UNAVAILABLE","MICROPHONE_PERMISSION_DENIED",
        "AUDIO_NOT_READY","AUDIO_CREATE_FAILED","AUDIO_DISCONNECTED","AUDIO_STALLED",
        "SCREEN_PERMISSION_DENIED","SYSTEM_AUDIO_UNAVAILABLE","SYSTEM_AUDIO_ENUMERATION_FAILED",
        "APPLICATION_UNAVAILABLE","APPLICATION_AMBIGUOUS","DISPLAY_UNAVAILABLE",
        "SYSTEM_AUDIO_SELF_CAPTURE","SYSTEM_AUDIO_STREAM_STOPPED","SYSTEM_AUDIO_NO_SAMPLES"};
    return fault>=0 && fault<(int)(sizeof(names)/sizeof(names[0]))?names[fault]:"AUDIO_STATE_UNAVAILABLE";
}
static bool audio_target_valid(unsigned kind,const char *target) {
    if(kind>3 || !target || !*target || strlen(target)>=512)return false;
    for(const unsigned char *p=(const unsigned char *)target;*p;p++)if(*p<32 || *p==127)return false;
    if(kind==0)return !strcmp(target,"tone");
    if(kind==1)return strcmp(target,"tone") && strcmp(target,"none") && strcmp(target,"default");
    if(kind==2) {
        if(strlen(target)>=256 || !strchr(target,'.') || target[0]=='.')return false;
        for(size_t i=0;target[i];i++) {
            unsigned char c=target[i];
            if(!((c>='a' && c<='z') || (c>='A' && c<='Z') || (c>='0' && c<='9') || c=='-' || c=='.'))return false;
            if(c=='.' && (!target[i+1] || target[i+1]=='.'))return false;
        }
        return true;
    }
    if(strlen(target)!=36)return false;
    for(size_t i=0;i<36;i++) {
        char c=target[i];
        if(i==8 || i==13 || i==18 || i==23) {if(c!='-')return false;}
        else if(!((c>='0' && c<='9') || (c>='A' && c<='F')))return false;
    }
    return true;
}
static bool system_audio_available(void) {
    if(@available(macOS 13.0,*)) {
        const char *id=NULL;
        for(size_t i=0;obs_enum_input_types(i,&id);i++)if(!strcmp(id,"sck_audio_capture"))return true;
    }
    return false;
}
static NSString *system_display_uuid(CGDirectDisplayID display) {
    CFUUIDRef uuid=CGDisplayCreateUUIDFromDisplayID(display);
    if(!uuid)return nil;
    NSString *result=CFBridgingRelease(CFUUIDCreateString(kCFAllocatorDefault,uuid));
    CFRelease(uuid);return result;
}
static bool system_audio_is_self(NSString *bundle,pid_t pid) {
    NSString *own=NSBundle.mainBundle.bundleIdentifier;
    return pid==getpid() || (own && [bundle isEqualToString:own]);
}
/* A timeout leaves a retained completion block/semaphore until Apple finishes;
 * no callback can access stack storage or native mixer input state. */
static SCShareableContent *system_audio_content(int *fault) {
    *fault=0;
    if(!CGPreflightScreenCaptureAccess()) {*fault=7;return nil;}
    if(!system_audio_available()) {*fault=8;return nil;}
    dispatch_semaphore_t completed=dispatch_semaphore_create(0);
    __block SCShareableContent *result=nil;
    __block NSError *enumeration_error=nil;
    // Match the official application enumeration (visible windows only).
    [SCShareableContent getShareableContentExcludingDesktopWindows:YES onScreenWindowsOnly:YES
        completionHandler:^(SCShareableContent *content,NSError *error) {
            result=content;enumeration_error=error;dispatch_semaphore_signal(completed);
        }];
    if(dispatch_semaphore_wait(completed,dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC))) {*fault=9;return nil;}
    if(enumeration_error || !result) {*fault=CGPreflightScreenCaptureAccess()?9:7;return nil;}
    return result;
}
static int system_audio_resolve(audio_input *a) {
    int fault=0;SCShareableContent *content=system_audio_content(&fault);
    if(!content)return fault;
    CGDirectDisplayID main=CGMainDisplayID();bool display_found=false;
    for(SCDisplay *display in content.displays)if(display.displayID==main)display_found=true;
    if(!display_found)return 12;
    if(a->kind==3) {
        if(![system_display_uuid(main) isEqualToString:@(a->device)])return 12;
        a->system_display=main;a->application_pid=0;return 0;
    }
    NSString *bundle=@(a->device);pid_t pid=0;size_t matches=0;
    for(SCRunningApplication *application in content.applications)if([application.bundleIdentifier isEqualToString:bundle]) {
        if(system_audio_is_self(bundle,application.processID))return 13;
        matches++;pid=application.processID;
    }
    if(!matches)return 10;
    if(matches!=1)return 11;
    NSArray<NSRunningApplication *> *running=[NSRunningApplication runningApplicationsWithBundleIdentifier:bundle];
    if(running.count!=1)return running.count?11:10;
    if(running.firstObject.processIdentifier!=pid || running.firstObject.terminated)return 10;
    a->application_pid=pid;a->system_display=main;return 0;
}
static int system_audio_target_health(const audio_input *a) {
    if(atomic_load(&a->system_stopped))return 14;
    if(!CGPreflightScreenCaptureAccess())return 7;
    if(a->system_display!=CGMainDisplayID() || !CGDisplayIsActive(a->system_display))return 12;
    if(a->kind==3)return [system_display_uuid(a->system_display) isEqualToString:@(a->device)]?0:12;
    NSString *bundle=@(a->device);
    NSArray<NSRunningApplication *> *running=[NSRunningApplication runningApplicationsWithBundleIdentifier:bundle];
    if(running.count!=1)return running.count?11:10;
    NSRunningApplication *app=running.firstObject;
    if(app.terminated || app.processIdentifier!=a->application_pid)return 10;
    return system_audio_is_self(bundle,app.processIdentifier)?13:0;
}
static void system_audio_stopped(void *param,calldata_t *unused) {
    (void)unused;
    // In pinned OBS 33.0.1, post-create update_properties means stream stopped.
    // Do not inspect plugin-private memory or enumerate properties in callback.
    atomic_store(&((audio_input *)param)->system_stopped,true);
}
char *motive_system_audio_sources(motive_engine *e) {
    (void)e;
    bool available=system_audio_available();int fault=0;
    SCShareableContent *content=system_audio_content(&fault);
    NSMutableArray *applications=[NSMutableArray array],*displays=[NSMutableArray array];
    NSMutableDictionary<NSString *,NSMutableDictionary *> *by_bundle=[NSMutableDictionary dictionary];
    if(content) {
        for(SCRunningApplication *application in content.applications) {
            NSString *bundle=application.bundleIdentifier;
            if(!bundle.length || !application.applicationName.length || system_audio_is_self(bundle,application.processID))continue;
            NSMutableDictionary *entry=by_bundle[bundle];
            if(!entry) {
                entry=[@{@"bundle_id":bundle,@"name":application.applicationName,@"running_instances":@0,@"selectable":@YES} mutableCopy];
                by_bundle[bundle]=entry;
            }
            entry[@"running_instances"]=@([entry[@"running_instances"] unsignedIntValue]+1);
        }
        for(NSString *bundle in [[by_bundle allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
            NSMutableDictionary *entry=by_bundle[bundle];
            NSArray *running=[NSRunningApplication runningApplicationsWithBundleIdentifier:bundle];
            unsigned count=MAX([entry[@"running_instances"] unsignedIntValue],(unsigned)running.count);
            entry[@"running_instances"]=@(count);
            entry[@"selectable"]=@((bool)(count==1 && audio_target_valid(2,bundle.UTF8String)));
            [applications addObject:entry];
        }
        for(SCDisplay *display in content.displays) {
            NSString *uuid=system_display_uuid(display.displayID);if(!uuid)continue;
            bool main=display.displayID==CGMainDisplayID();
            [displays addObject:@{@"display_uuid":uuid,@"name":[NSString stringWithFormat:@"Display %u",display.displayID],
                @"is_main":@(main),@"selectable":@(main)}];
        }
    }
    NSDictionary *state=@{@"available":@(available),@"permission":CGPreflightScreenCaptureAccess()?@"authorized":@"not_authorized",
        @"issue":fault?@(audio_fault_name(fault)):[NSNull null],@"applications":applications,@"displays":displays,
        @"excludes_current_process":@YES,@"desktop_main_display_only":@YES,@"overlap_policy":@"reject_desktop_with_application"};
    NSData *json=[NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
    return strdup([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
}
