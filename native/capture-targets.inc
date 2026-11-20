/* Exact target discovery/control. The official mac-capture plugin owns SCStream.
 * This file never requests permission, captures pixels, or picks a default. */
static NSString *capture_display_uuid(CGDirectDisplayID display) {
    CFUUIDRef uuid=CGDisplayCreateUUIDFromDisplayID(display);
    if(!uuid)return nil;
    NSString *value=CFBridgingRelease(CFUUIDCreateString(kCFAllocatorDefault,uuid));
    CFRelease(uuid);return value;
}
static CGDirectDisplayID capture_display(NSString *uuid) {
    if(![uuid isKindOfClass:NSString.class] || uuid.length!=36)return 0;
    CFUUIDRef value=CFUUIDCreateFromString(kCFAllocatorDefault,(__bridge CFStringRef)uuid);
    if(!value)return 0;
    CGDirectDisplayID display=CGDisplayGetDisplayIDFromUUID(value);CFRelease(value);
    return display && CGDisplayIsActive(display) && [capture_display_uuid(display) isEqual:uuid]?display:0;
}
static pid_t capture_application(NSString *bundle) {
    if(![bundle isKindOfClass:NSString.class] || !bundle.length)return 0;
    NSArray<NSRunningApplication *> *apps=[NSRunningApplication runningApplicationsWithBundleIdentifier:bundle];
    if(apps.count!=1 || apps.firstObject.terminated || apps.firstObject.processIdentifier==getpid())return 0;
    return apps.firstObject.processIdentifier;
}
/* Owner-thread observations of one previously admitted process. The catalog
 * remains strict at admission; an absent entry is not OS process death. */
typedef struct {
    uint64_t checked_ns,catalog_absence_observations;
    unsigned registered_instances;
    pid_t registered_pid;
    enum motive_process_probe process_probe;
    enum motive_application_identity_health health;
    bool generation_matches,executable_matches,pinned_bundle_conflict;
} capture_application_identity;
static void observe_capture_application(NSString *bundle,const motive_process_identity *pin,
                                        capture_application_identity *observation) {
    NSArray<NSRunningApplication *> *running=bundle.length && pin->pid>0?
        [NSRunningApplication runningApplicationsWithBundleIdentifier:bundle]:@[];
    NSRunningApplication *pinned=pin->pid>0?
        [NSRunningApplication runningApplicationWithProcessIdentifier:pin->pid]:nil;
    motive_process_identity current;
    observation->checked_ns=os_gettime_ns();
    observation->registered_instances=(unsigned)running.count;
    observation->registered_pid=running.firstObject?running.firstObject.processIdentifier:0;
    observation->process_probe=motive_process_observe(pin->pid,&current);
    observation->generation_matches=observation->process_probe==MOTIVE_PROCESS_OBSERVED &&
        motive_process_same_generation(pin,&current);
    observation->executable_matches=observation->process_probe==MOTIVE_PROCESS_OBSERVED &&
        !strcmp(pin->executable,current.executable);
    observation->pinned_bundle_conflict=pinned.bundleIdentifier.length &&
        ![pinned.bundleIdentifier isEqualToString:bundle];
    observation->health=motive_application_identity_check(pin,observation->process_probe,&current,
        observation->registered_instances,observation->registered_pid,observation->pinned_bundle_conflict);
    if(observation->health==MOTIVE_APPLICATION_MATCHES && !running.count)
        observation->catalog_absence_observations++;
}
static NSDictionary *capture_application_identity_json(const motive_process_identity *pin,
                                                        const capture_application_identity *observation) {
    return @{@"checked_ns":@(observation->checked_ns),@"expected_pid":@(pin->pid),
        @"registered_instances":@(observation->registered_instances),@"registered_pid":@(observation->registered_pid),
        @"process_probe":observation->process_probe==MOTIVE_PROCESS_OBSERVED?@"observed":
            observation->process_probe==MOTIVE_PROCESS_ABSENT?@"absent":@"unobserved",
        @"process_generation_matches":@(observation->generation_matches),
        @"process_executable_matches":@(observation->executable_matches),
        @"pinned_bundle_conflict":@(observation->pinned_bundle_conflict),
        @"catalog_absence_observations":@(observation->catalog_absence_observations),
        @"health":observation->health==MOTIVE_APPLICATION_MATCHES?@"matches":
            observation->health==MOTIVE_APPLICATION_CHANGED?@"changed":
            observation->health==MOTIVE_APPLICATION_AMBIGUOUS?@"ambiguous":@"unobserved",
        @"scope":@"admitted_pid_birth_uid_and_executable_path; catalog_absence_is_not_process_death"};
}
static NSArray *capture_displays(void) {
    NSMutableArray *result=[NSMutableArray array];
    for(NSScreen *screen in NSScreen.screens) {
        CGDirectDisplayID display=[screen.deviceDescription[@"NSScreenNumber"] unsignedIntValue];
        NSString *uuid=capture_display_uuid(display);
        if(!uuid || !capture_display(uuid))continue;
        CGRect bounds=CGDisplayBounds(display);
        [result addObject:@{@"display_uuid":uuid,@"name":screen.localizedName?:@"Pantalla",
            @"bounds":@{@"x":@(bounds.origin.x),@"y":@(bounds.origin.y),@"width":@(bounds.size.width),@"height":@(bounds.size.height)},
            @"width":@(CGDisplayPixelsWide(display)),@"height":@(CGDisplayPixelsHigh(display))}];
    }
    return result;
}
static NSArray *capture_applications(NSArray *windows,NSArray *displays) {
    NSMutableDictionary *bundles=[NSMutableDictionary dictionary];
    for(NSDictionary *window in windows) {
        NSString *bundle=window[@"bundle_id"];
        if(bundle.length && capture_application(bundle))bundles[bundle]=window[@"app"];
    }
    NSMutableArray *result=[NSMutableArray array];
    for(NSString *bundle in [[bundles allKeys] sortedArrayUsingSelector:@selector(compare:)])
        for(NSDictionary *display in displays)
            [result addObject:@{@"bundle_id":bundle,@"display_uuid":display[@"display_uuid"],
                @"name":[NSString stringWithFormat:@"%@ · %@",bundles[bundle],display[@"name"]]}];
    return result;
}
