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
