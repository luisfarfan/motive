/* Minimal loopback adapter. RTMP and TLS remain the official obs-outputs module.
 * Settings carry an opaque reference; plaintext is resolved only in native
 * memory and never serialized into obs_data, project files or Rust responses. */
struct local_service { obs_data_t *settings; char *key; size_t key_size; };
static const char *local_service_name(void *unused) { (void)unused;return "Motive loopback receiver"; }
static void *local_service_create(obs_data_t *settings,obs_service_t *service) {
    (void)service;
    struct local_service *data=calloc(1,sizeof(*data));
    const char *ref=obs_data_get_string(settings,"credential_ref");
    if (*ref) {
        const char *url=obs_data_get_string(settings,"server");char *end=NULL;
        const char *prefix="rtmps://127.0.0.1:";
        if (strncmp(url,prefix,strlen(prefix))) {free(data);return NULL;}
        long port=strtol(url+strlen(prefix),&end,10);
        if (port<1024 || port>65535 || !end || strcmp(end,"/live")) {free(data);return NULL;}
        CFDataRef secret=NULL;
        if (credential_read(ref,(int)port,&secret)) {free(data);return NULL;}
        data->key_size=(size_t)CFDataGetLength(secret)+1;
        data->key=calloc(1,data->key_size);memcpy(data->key,CFDataGetBytePtr(secret),data->key_size-1);
        CFRelease(secret);atomic_store(&protect_obs_logs,true);
    }
    obs_data_addref(settings);data->settings=settings;return data;
}
static void local_service_destroy(void *opaque) {
    struct local_service *data=opaque;
    if (data->key) {credential_clear(data->key,data->key_size);free(data->key);}
    obs_data_release(data->settings);free(data);
}
static const char *local_service_protocol(void *opaque) {
    struct local_service *data=opaque;
    return !strncmp(obs_data_get_string(data->settings,"server"),"rtmps://",8) ? "RTMPS":"RTMP";
}
static const char *local_service_connect_info(void *opaque,uint32_t type) {
    struct local_service *data=opaque;
    if (type==OBS_SERVICE_CONNECT_INFO_SERVER_URL) return obs_data_get_string(data->settings,"server");
    if (type==OBS_SERVICE_CONNECT_INFO_STREAM_ID) return data->key ?: "motive";
    return NULL;
}
static bool local_service_can_connect(void *opaque) {
    struct local_service *data=opaque;
    const char *url=obs_data_get_string(data->settings,"server");
    const char *prefix=!strncmp(url,"rtmps://",8) ? "rtmps://127.0.0.1:":"rtmp://127.0.0.1:";
    if (strncmp(url,prefix,strlen(prefix))) return false;
    char *end=NULL;long port=strtol(url+strlen(prefix),&end,10);
    return port>=1024 && port<=65535 && end && !strcmp(end,"/live");
}
static struct obs_service_info local_service_info={
    .id="motive_local_service",.get_name=local_service_name,.create=local_service_create,
    .destroy=local_service_destroy,.get_protocol=local_service_protocol,
    .get_connect_info=local_service_connect_info,.can_try_to_connect=local_service_can_connect
};
