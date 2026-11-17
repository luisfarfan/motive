/* macOS login Keychain. Public SecItem APIs, code-signing ACLs; no plaintext
 * persistence, export command or interactive authorization on the engine thread. */
#import <Security/Security.h>
static NSString *const credential_service=@"local.motive.streaming.v1";
static void credential_clear(void *memory,size_t length) {
    volatile unsigned char *p=memory;while (length--) *p++=0;
}
static bool credential_reference_valid(const char *value) {
    if (!value || strlen(value)!=39 || strncmp(value,"kc_",3)) return false;
    for (int i=3;i<39;i++) {
        bool dash=i==11 || i==16 || i==21 || i==26;
        if (dash ? value[i]!='-' : !((value[i]>='0' && value[i]<='9') || (value[i]>='a' && value[i]<='f'))) return false;
    }
    return true;
}
static NSMutableDictionary *credential_query(const char *reference) {
    return [@{(__bridge id)kSecClass:(__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService:credential_service,(__bridge id)kSecAttrAccount:@(reference),
        (__bridge id)kSecAttrSynchronizable:@NO} mutableCopy];
}
static int credential_result(OSStatus code) {
    if (code==errSecSuccess) return 0;
    if (code==errSecItemNotFound) return 1;
    if (code==errSecAuthFailed || code==errSecInteractionNotAllowed || code==errSecUserCanceled) return 2;
    return 3;
}
/* port=0 only probes access; nonzero requires the stored RTMPS binding. */
static int credential_read(const char *reference,int port,CFDataRef *secret) {
    if (!credential_reference_valid(reference)) return 4;
    SecKeychainSetUserInteractionAllowed(false);
    NSMutableDictionary *query=credential_query(reference);
    query[(__bridge id)kSecReturnData]=@YES;
    query[(__bridge id)kSecReturnAttributes]=@YES;
    query[(__bridge id)kSecMatchLimit]=(__bridge id)kSecMatchLimitOne;
    query[(__bridge id)kSecUseAuthenticationUI]=(__bridge id)kSecUseAuthenticationUIFail;
    CFTypeRef found=NULL;
    OSStatus code=SecItemCopyMatching((__bridge CFDictionaryRef)query,&found);
    if (code!=errSecSuccess) return credential_result(code);
    NSDictionary *item=(__bridge NSDictionary *)found;
    NSData *data=item[(__bridge id)kSecValueData];
    NSData *binding=item[(__bridge id)kSecAttrGeneric];
    NSData *expected=[[NSString stringWithFormat:@"rtmps:%d",port] dataUsingEncoding:NSUTF8StringEncoding];
    int result=(!data || data.length<1 || data.length>512) ? 3 : (port && ![binding isEqual:expected] ? 5:0);
    if (!result && secret) *secret=(CFDataRef)CFRetain((__bridge CFTypeRef)data);
    CFRelease(found);return result;
}
int motive_credential_status(const char *reference,int port) {
    @autoreleasepool { return credential_read(reference,port,NULL); }
}
