/* Approved external RTMPS service. libobs owns TLS, transport and encoding.
 * This service is registered separately from H8's strict loopback service.
 * No plaintext key is serialized into obs_data or returned to Rust. */
#include "destination-credential.h"
static bool approved_service_url_matches(const char *url,const char *binding) {
    if(!url || !binding || strnlen(url,1025)>1024 || strnlen(binding,1025)>1024)return false;
    NSData *bytes=[[NSString stringWithUTF8String:binding] dataUsingEncoding:NSUTF8StringEncoding];
    if(!bytes)return false;
    NSDictionary *value=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
    if(![value isKindOfClass:NSDictionary.class] || ![value[@"protocol"] isEqual:@"rtmps"])return false;
    NSString *host=value[@"host"],*application=value[@"application"];NSNumber *port=value[@"port"];
    if(![host isKindOfClass:NSString.class] || ![application isKindOfClass:NSString.class] || ![port isKindOfClass:NSNumber.class])return false;
    NSString *authority=[host containsString:@":"] ? [NSString stringWithFormat:@"[%@]",host]:host;
    NSString *expected=[NSString stringWithFormat:@"rtmps://%@:%@%@",authority,port,application];
    return [expected isEqualToString:@(url)];
}
static const char *approved_service_name(void *unused) {(void)unused;return "Motive approved RTMPS destination";}
static void *approved_service_create(obs_data_t *settings,obs_service_t *service) {
    (void)service;
    const char *url=obs_data_get_string(settings,"server");
    const char *binding=obs_data_get_string(settings,"destination_binding");
    const char *reference=obs_data_get_string(settings,"credential_ref");
    if(!approved_service_url_matches(url,binding))return NULL;
    CFDataRef secret=NULL;
    if(motive_destination_credential_read(reference,binding,&secret))return NULL;
    struct local_service *data=calloc(1,sizeof(*data));
    if(!data){CFRelease(secret);return NULL;}
    data->key_size=(size_t)CFDataGetLength(secret)+1;
    data->key=calloc(1,data->key_size);
    if(!data->key){CFRelease(secret);free(data);return NULL;}
    memcpy(data->key,CFDataGetBytePtr(secret),data->key_size-1);CFRelease(secret);
    // Remote replies may contain secrets. Keep OBS free-form logs suppressed
    // for the rest of this process, including after a failed connection.
    atomic_store(&protect_obs_logs,true);
    obs_data_addref(settings);data->settings=settings;return data;
}
static bool approved_service_can_connect(void *opaque) {
    struct local_service *data=opaque;
    return data && data->key && approved_service_url_matches(
        obs_data_get_string(data->settings,"server"),
        obs_data_get_string(data->settings,"destination_binding"));
}
static struct obs_service_info approved_service_info={
    .id="motive_approved_service",.get_name=approved_service_name,.create=approved_service_create,
    .destroy=local_service_destroy,.get_protocol=local_service_protocol,
    .get_connect_info=local_service_connect_info,.can_try_to_connect=approved_service_can_connect
};
