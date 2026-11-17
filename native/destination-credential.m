/* Native secure entry and login-Keychain storage. No libobs or GPUI calls.
 * NSSecureTextField/NSAlert are AppKit-owned; SecItemAdd runs off the main thread.
 * Plaintext never crosses the C bridge, argv, environment, JSON or a log. */
#import <AppKit/AppKit.h>
#import <Security/Security.h>
#include <stdatomic.h>
#include <string.h>
#include "destination-credential.h"

static NSString *const destination_credential_service = @"local.motive.streaming.v1";
static atomic_bool destination_credential_work;
static uint64_t last_request_id;

static void destination_clear(void *bytes, size_t count) {
    volatile unsigned char *p = bytes; while (count--) *p++ = 0;
}
static bool destination_reference_valid(const char *reference) {
    if (!reference || strnlen(reference, 40) != 39 || strncmp(reference, "kc_", 3)) return false;
    for (int i = 3; i < 39; ++i) {
        bool dash = i == 11 || i == 16 || i == 21 || i == 26;
        if (dash ? reference[i] != '-' : !((reference[i] >= '0' && reference[i] <= '9') || (reference[i] >= 'a' && reference[i] <= 'f'))) return false;
    }
    return true;
}
static int destination_keychain_result(OSStatus code) {
    if (code == errSecSuccess) return 0;
    if (code == errSecItemNotFound) return 1;
    if (code == errSecAuthFailed || code == errSecInteractionNotAllowed || code == errSecUserCanceled) return 2;
    return 3;
}
static bool destination_ascii(NSString *text, NSString *allowed, NSUInteger minimum, NSUInteger maximum) {
    if (![text isKindOfClass:NSString.class] || text.length < minimum || text.length > maximum) return false;
    return [text rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:allowed] invertedSet]].location == NSNotFound;
}
static NSDictionary *destination_binding(const char *binding) {
    if (!binding || strnlen(binding, 1025) > 1024) return nil;
    NSData *bytes = [[NSString stringWithUTF8String:binding] dataUsingEncoding:NSUTF8StringEncoding];
    if (!bytes) return nil;
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
    if (![value isKindOfClass:NSDictionary.class] || value.count != 6) return nil;
    NSSet *keys = [NSSet setWithArray:@[@"version", @"destination_id", @"protocol", @"host", @"port", @"application"]];
    if (![[NSSet setWithArray:value.allKeys] isEqual:keys] || ![value[@"version"] isEqual:@2] || ![value[@"protocol"] isEqual:@"rtmps"]) return nil;
    if (!destination_ascii(value[@"destination_id"], @"abcdefghijklmnopqrstuvwxyz0123456789-_", 1, 48)) return nil;
    if (!destination_ascii(value[@"host"], @"abcdefghijklmnopqrstuvwxyz0123456789-.:", 1, 253)) return nil;
    NSNumber *port = value[@"port"];
    if (![port isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)port) == CFBooleanGetTypeID()
        || port.doubleValue != port.unsignedIntValue || port.unsignedIntValue < 1 || port.unsignedIntValue > 65535) return nil;
    NSString *path = value[@"application"];
    if (!destination_ascii(path, @"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./", 2, 256) || ![path hasPrefix:@"/"]) return nil;
    NSArray<NSString *> *segments = [[path substringFromIndex:1] componentsSeparatedByString:@"/"];
    if (segments.count > 8) return nil;
    for (NSString *segment in segments) if (!segment.length || segment.length > 64 || [segment isEqual:@"."] || [segment isEqual:@".."]) return nil;
    return value;
}
static NSMutableDictionary *destination_query(const char *reference) {
    return [@{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService: destination_credential_service,
        (__bridge id)kSecAttrAccount: @(reference),
        (__bridge id)kSecAttrSynchronizable: @NO} mutableCopy];
}
int motive_destination_credential_read(const char *reference, const char *binding, CFDataRef *secret) {
    @autoreleasepool {
        if (secret) *secret = NULL;
        if (!destination_reference_valid(reference) || !destination_binding(binding)) return 4;
        NSMutableDictionary *query = destination_query(reference);
        query[(__bridge id)kSecReturnData] = @YES;
        query[(__bridge id)kSecReturnAttributes] = @YES;
        query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
        query[(__bridge id)kSecUseAuthenticationUI] = (__bridge id)kSecUseAuthenticationUIFail;
        // Match H8's non-interactive legacy-login-Keychain behavior. This is
        // process-local policy, not a change to macOS permissions or trust.
        SecKeychainSetUserInteractionAllowed(false);
        CFTypeRef found = NULL;
        OSStatus code = SecItemCopyMatching((__bridge CFDictionaryRef)query, &found);
        if (code) return destination_keychain_result(code);
        NSDictionary *item = (__bridge NSDictionary *)found;
        NSData *data = item[(__bridge id)kSecValueData];
        NSData *actual = item[(__bridge id)kSecAttrGeneric];
        NSData *expected = [[NSString stringWithUTF8String:binding] dataUsingEncoding:NSUTF8StringEncoding];
        int result = (![data isKindOfClass:NSData.class] || data.length < 1 || data.length > 512) ? 3 : (![actual isEqual:expected] ? 5 : 0);
        if (!result && secret) *secret = (CFDataRef)CFRetain((__bridge CFTypeRef)data);
        CFRelease(found); return result;
    }
}
int motive_destination_credential_status(const char *reference, const char *binding) {
    return motive_destination_credential_read(reference, binding, NULL);
}
static bool destination_signed_identity(void) {
    SecCodeRef code = NULL; CFDictionaryRef information = NULL;
    OSStatus result = SecCodeCopySelf(kSecCSDefaultFlags, &code);
    if (!result) result = SecCodeCheckValidity(code, kSecCSDefaultFlags, NULL);
    if (!result) result = SecCodeCopySigningInformation(code, kSecCSSigningInformation, &information);
    NSDictionary *attributes = (__bridge NSDictionary *)information;
    NSString *team = attributes[(__bridge id)kSecCodeInfoTeamIdentifier];
    bool valid = !result && [team isKindOfClass:NSString.class] && team.length
        && [attributes[(__bridge id)kSecCodeInfoIdentifier] isEqual:@"local.motive.studio"];
    if (information) CFRelease(information); if (code) CFRelease(code); return valid;
}

@interface MotiveDestinationEnrollment : NSObject
@property(nonatomic, strong) NSAlert *alert;
@property(nonatomic, strong) NSSecureTextField *field;
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) NSData *binding;
@property(nonatomic, strong) NSString *reference;
@property(nonatomic) uint64_t requestID;
@property(nonatomic) uint32_t phase;
@property(nonatomic) int code;
@property(nonatomic) BOOL cancelRequested;
- (void)pasteCredential:(id)sender;
@end
@implementation MotiveDestinationEnrollment
- (void)pasteCredential:(id)sender {
    // GPUI's application menu need not contain Edit/Paste. Route this local
    // button/key equivalent straight to this secure field's AppKit editor.
    // AppKit owns clipboard access; never fetch/copy clipboard text here.
    if(!NSThread.isMainThread || self.phase!=MOTIVE_CREDENTIAL_AWAITING_USER
        || self.cancelRequested || !self.field || self.field.window!=self.alert.window)return;
    NSText *editor=self.field.currentEditor;
    if(!editor && [self.alert.window makeFirstResponder:self.field])editor=self.field.currentEditor;
    if(editor.isFieldEditor)[editor paste:sender];
}
@end
static MotiveDestinationEnrollment *enrollment;

static NSView *destination_secure_accessory(MotiveDestinationEnrollment *state) {
    NSView *accessory=[[NSView alloc] initWithFrame:NSMakeRect(0,0,400,66)];
    state.field=[[NSSecureTextField alloc] initWithFrame:NSMakeRect(0,36,400,28)];
    state.field.placeholderString=@"Clave de transmisión";
    state.field.accessibilityLabel=@"Clave de transmisión segura";
    [accessory addSubview:state.field];
    NSButton *paste=[NSButton buttonWithTitle:@"Pegar" target:state action:@selector(pasteCredential:)];
    paste.frame=NSMakeRect(300,0,100,28);
    paste.keyEquivalent=@"v";paste.keyEquivalentModifierMask=NSEventModifierFlagCommand;
    paste.accessibilityLabel=@"Pegar en la clave de transmisión segura";
    paste.toolTip=@"Pegar desde el portapapeles (⌘V)";
    [accessory addSubview:paste];
    return accessory;
}

static void destination_release_ui(MotiveDestinationEnrollment *state) {
    state.field.stringValue = @"";
    state.field = nil; state.alert = nil; state.window = nil;
}
static void destination_store_secret(MotiveDestinationEnrollment *state, char *key, size_t length) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        @autoreleasepool {
            NSString *reference = [@"kc_" stringByAppendingString:NSUUID.UUID.UUIDString.lowercaseString];
            SecTrustedApplicationRef application = NULL; SecAccessRef access = NULL;
            OSStatus code = SecTrustedApplicationCreateFromPath(NULL, &application);
            if (!code) code = SecAccessCreate(CFSTR("Motive approved RTMPS destination"), (__bridge CFArrayRef)@[(__bridge id)application], &access);
            if (!code) {
                NSMutableDictionary *attributes = destination_query(reference.UTF8String);
                attributes[(__bridge id)kSecValueData] = [NSData dataWithBytesNoCopy:key length:length freeWhenDone:NO];
                attributes[(__bridge id)kSecAttrGeneric] = state.binding;
                attributes[(__bridge id)kSecAttrAccess] = (__bridge id)access;
                attributes[(__bridge id)kSecAttrLabel] = @"Motive approved RTMPS destination";
                attributes[(__bridge id)kSecUseAuthenticationUI] = (__bridge id)kSecUseAuthenticationUIFail;
                SecKeychainSetUserInteractionAllowed(false);
                code = SecItemAdd((__bridge CFDictionaryRef)attributes, NULL);
            }
            destination_clear(key, 513); free(key);
            if (access) CFRelease(access); if (application) CFRelease(application);
            int result = destination_keychain_result(code);
            dispatch_async(dispatch_get_main_queue(), ^{
                state.code = result;
                if (!result) {
                    state.reference = reference;
                    state.phase = state.cancelRequested ? MOTIVE_CREDENTIAL_STORED_AFTER_CANCEL : MOTIVE_CREDENTIAL_STORED;
                } else state.phase = MOTIVE_CREDENTIAL_FAILED;
                // No deletion after late cancellation: surface the created
                // reference so the owner can reconcile it explicitly.
                atomic_store(&destination_credential_work, false);
            });
        }
    });
}

int motive_destination_credential_begin_for_view(void *opaqueView, const char *requestJSON, uint64_t requestID) {
    @autoreleasepool {
        if (![NSThread isMainThread] || !NSApp || !opaqueView) return 9;
        id object = (__bridge id)opaqueView;
        if (![object isKindOfClass:NSView.class]) return 9;
        NSView *view = object;
        NSWindow *window = view.window;
        if (!window || ![NSApp.windows containsObject:window]
            || !(view == window.contentView || [view isDescendantOf:window.contentView])) return 9;
        return motive_destination_credential_begin((__bridge void *)window, requestJSON, requestID);
    }
}

int motive_destination_credential_begin(void *opaqueWindow, const char *requestJSON, uint64_t requestID) {
    @autoreleasepool {
        if (![NSThread isMainThread] || !NSApp || !opaqueWindow) return 9;
        if (atomic_load(&destination_credential_work)) return 7;
        if (enrollment) return 8;
        if (!requestID || requestID <= last_request_id || !requestJSON || strnlen(requestJSON, 4097) > 4096) return 4;
        NSWindow *window = (__bridge NSWindow *)opaqueWindow;
        if (![NSApp.windows containsObject:window] || !window.visible || window.attachedSheet) return 9;
        NSData *requestBytes = [[NSString stringWithUTF8String:requestJSON] dataUsingEncoding:NSUTF8StringEncoding];
        if (!requestBytes) return 4;
        NSDictionary *request = [NSJSONSerialization JSONObjectWithData:requestBytes options:0 error:nil];
        if (![request isKindOfClass:NSDictionary.class] || request.count != 2
            || ![[NSSet setWithArray:request.allKeys] isEqual:[NSSet setWithArray:@[@"name", @"binding"]]]) return 4;
        NSString *name = request[@"name"], *binding = request[@"binding"];
        if (![name isKindOfClass:NSString.class] || !name.length || name.length > 160
            || [name rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound
            || ![binding isKindOfClass:NSString.class]) return 4;
        NSDictionary *destination = destination_binding(binding.UTF8String);
        if (!destination) return 4;
        if (!destination_signed_identity()) return 6;
        MotiveDestinationEnrollment *state = [MotiveDestinationEnrollment new];
        state.requestID = requestID; state.phase = MOTIVE_CREDENTIAL_AWAITING_USER;
        state.window = window; state.binding = [binding dataUsingEncoding:NSUTF8StringEncoding];
        state.alert = [NSAlert new]; state.alert.messageText = @"Guardar credencial de transmisión";
        NSString *host = destination[@"host"];
        NSString *authority = [host containsString:@":"] ? [NSString stringWithFormat:@"[%@]", host] : host;
        state.alert.informativeText = [NSString stringWithFormat:@"%@\nDestino: %@ · rtmps://%@:%@%@\nLa clave se guarda únicamente en el llavero de macOS. Esta acción no inicia una transmisión.", name, destination[@"destination_id"], authority, destination[@"port"], destination[@"application"]];
        [state.alert addButtonWithTitle:@"Guardar en Llavero"]; [state.alert addButtonWithTitle:@"Cancelar"];
        state.alert.accessoryView = destination_secure_accessory(state);
        enrollment = state; last_request_id = requestID; atomic_store(&destination_credential_work, true);
        [state.alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse response) {
            if (state.cancelRequested || response != NSAlertFirstButtonReturn) {
                state.cancelRequested = YES; state.phase = MOTIVE_CREDENTIAL_CANCELLED; state.code = 2;
                destination_release_ui(state); atomic_store(&destination_credential_work, false); return;
            }
            // Only the native field/string sees plaintext. AppKit may retain
            // internal copies; wiping our C buffer is not a zero-copy promise.
            NSString *secret = state.field.stringValue;
            NSUInteger length = [secret lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
            char *key = calloc(1, 513);
            bool valid = key && length > 0 && length <= 512 && [secret getCString:key maxLength:513 encoding:NSUTF8StringEncoding];
            for (NSUInteger i = 0; valid && i < length; ++i) {
                unsigned char c = key[i];
                valid = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || (c && strchr("-_.~", c));
            }
            destination_release_ui(state); secret = nil;
            if (!valid) {
                if (key) { destination_clear(key, 513); free(key); }
                state.phase = MOTIVE_CREDENTIAL_FAILED; state.code = 4; atomic_store(&destination_credential_work, false); return;
            }
            state.phase = MOTIVE_CREDENTIAL_WRITING;
            destination_store_secret(state, key, length);
        }];
        [state.alert.window makeFirstResponder:state.field];
        return 0;
    }
}
bool motive_destination_credential_poll(uint64_t requestID, motive_destination_credential_result *result, bool consume) {
    if (![NSThread isMainThread] || !result || !enrollment || enrollment.requestID != requestID) return false;
    memset(result, 0, sizeof(*result)); result->request_id = requestID;
    result->phase = enrollment.phase; result->code = enrollment.code; result->cancel_requested = enrollment.cancelRequested;
    if (enrollment.reference) snprintf(result->credential_ref, sizeof(result->credential_ref), "%s", enrollment.reference.UTF8String);
    if (consume && !atomic_load(&destination_credential_work)) enrollment = nil;
    return true;
}
bool motive_destination_credential_cancel(uint64_t requestID) {
    if (![NSThread isMainThread] || !enrollment || enrollment.requestID != requestID) return false;
    if (!atomic_load(&destination_credential_work)) return true;
    enrollment.cancelRequested = YES;
    if (enrollment.phase == MOTIVE_CREDENTIAL_AWAITING_USER) {
        [enrollment.window endSheet:enrollment.alert.window returnCode:NSAlertSecondButtonReturn];
    }
    return true;
}
bool motive_destination_credential_busy(void) { return atomic_load(&destination_credential_work); }
