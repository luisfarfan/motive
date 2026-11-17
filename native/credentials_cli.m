/* Local-only enrollment. No secret-bearing argv, environment or stdin mode. */
#import <Foundation/Foundation.h>
#import <Security/Security.h>
#include <readpassphrase.h>
#include <unistd.h>
#include "credentials.inc"

static NSString *signing_team(NSString *path,NSString *identifier) {
    SecStaticCodeRef code=NULL;CFDictionaryRef info=NULL;
    OSStatus result=SecStaticCodeCreateWithPath((__bridge CFURLRef)[NSURL fileURLWithPath:path],kSecCSDefaultFlags,&code);
    if (!result) result=SecStaticCodeCheckValidity(code,kSecCSDefaultFlags,NULL);
    if (!result) result=SecCodeCopySigningInformation(code,kSecCSSigningInformation,&info);
    NSDictionary *attributes=(__bridge NSDictionary *)info;
    NSString *team=attributes[(__bridge id)kSecCodeInfoTeamIdentifier];
    bool valid=!result && team.length && [attributes[(__bridge id)kSecCodeInfoIdentifier] isEqual:identifier];
    NSString *ret=valid ? [team copy]:nil;
    if (info) CFRelease(info);if (code) CFRelease(code);return ret;
}

static int finish(int code,const char *reference) {
    printf("{\"ok\":%s,\"credential_ref\":\"%s\",\"result\":%d}\n",code ? "false":"true",reference ?: "",code);
    return code ? 1:0;
}
int main(int argc,const char **argv) { @autoreleasepool {
    if (argc<2) { fprintf(stderr,"Use: motive-credentials create PORT | replace REF PORT | delete REF | status REF\nSecrets are read only from /dev/tty with echo disabled. RTMPS loopback binding only.\n");return 2; }
    NSString *op=@(argv[1]);
    bool create=[op isEqual:@"create"],replace=[op isEqual:@"replace"],remove=[op isEqual:@"delete"],status=[op isEqual:@"status"];
    if ((!create && !replace && !remove && !status) || argc!=(replace ? 4:3)) return finish(4,NULL);
    NSString *ref=create ? [@"kc_" stringByAppendingString:NSUUID.UUID.UUIDString.lowercaseString]:@(argv[2]);
    if (!credential_reference_valid(ref.UTF8String)) return finish(4,NULL);
    if (status) return finish(motive_credential_status(ref.UTF8String,0),ref.UTF8String);
    char confirmation[32]={0};
    if (remove) {
        if (!readpassphrase("Delete credential? Type DELETE: ",confirmation,sizeof(confirmation),RPP_REQUIRE_TTY|RPP_ECHO_ON) || strcmp(confirmation,"DELETE")) return finish(2,ref.UTF8String);
        SecKeychainSetUserInteractionAllowed(false);
        return finish(credential_result(SecItemDelete((__bridge CFDictionaryRef)credential_query(ref.UTF8String))),ref.UTF8String);
    }
    char *end=NULL;long port=strtol(argv[create ? 2:3],&end,10);
    if (!end || *end || port<1024 || port>65535) return finish(4,ref.UTF8String);
    char key[514]={0};
    if (!readpassphrase("RTMPS stream key (hidden; stored only in Keychain): ",key,sizeof(key),RPP_REQUIRE_TTY)) return finish(2,ref.UTF8String);
    size_t length=strlen(key);
    bool valid=length>0 && length<=512;
    for (size_t i=0;i<length;i++) valid &= (key[i]>='A' && key[i]<='Z') || (key[i]>='a' && key[i]<='z') || (key[i]>='0' && key[i]<='9') || strchr("_.-",key[i]);
    if (!valid) { credential_clear(key,sizeof(key));return finish(4,ref.UTF8String); }
    NSData *value=[NSData dataWithBytesNoCopy:key length:length freeWhenDone:NO];
    NSData *binding=[[NSString stringWithFormat:@"rtmps:%ld",port] dataUsingEncoding:NSUTF8StringEncoding];
    OSStatus code;
    SecKeychainSetUserInteractionAllowed(false);
    if (replace) {
        NSDictionary *attrs=@{(__bridge id)kSecValueData:value,(__bridge id)kSecAttrGeneric:binding};
        code=SecItemUpdate((__bridge CFDictionaryRef)credential_query(ref.UTF8String),(__bridge CFDictionaryRef)attrs);
    } else {
        // Both paths have stable designated requirements when the bundle is
        // signed. An ad-hoc development build must not enroll real credentials.
        NSString *helper=NSProcessInfo.processInfo.arguments[0].stringByStandardizingPath;
        if (![helper hasPrefix:@"/"]) helper=[NSFileManager.defaultManager.currentDirectoryPath stringByAppendingPathComponent:helper];
        NSString *app=[helper.stringByDeletingLastPathComponent stringByAppendingPathComponent:@"motive"];
        NSString *helper_team=signing_team(helper,@"local.motive.credentials");
        NSString *app_team=signing_team(app,@"local.motive.studio");
        if (!helper_team || ![helper_team isEqual:app_team]) {credential_clear(key,sizeof(key));return finish(6,ref.UTF8String);}
        SecTrustedApplicationRef a=NULL,b=NULL;SecAccessRef access=NULL;
        code=SecTrustedApplicationCreateFromPath(helper.fileSystemRepresentation,&a);
        if (!code) code=SecTrustedApplicationCreateFromPath(app.fileSystemRepresentation,&b);
        if (!code) code=SecAccessCreate(CFSTR("Motive RTMPS credential"),(__bridge CFArrayRef)@[(__bridge id)a,(__bridge id)b],&access);
        if (!code) {
            NSMutableDictionary *attrs=credential_query(ref.UTF8String);
            attrs[(__bridge id)kSecValueData]=value;attrs[(__bridge id)kSecAttrGeneric]=binding;
            attrs[(__bridge id)kSecAttrAccess]=(__bridge id)access;
            attrs[(__bridge id)kSecAttrLabel]=@"Motive RTMPS credential";
            code=SecItemAdd((__bridge CFDictionaryRef)attrs,NULL);
        }
        if (a) CFRelease(a);if (b) CFRelease(b);if (access) CFRelease(access);
    }
    credential_clear(key,sizeof(key));return finish(credential_result(code),ref.UTF8String);
} }
