/* Minimal local endpoint adapter using the public libobs service API.
 * Encoding, RTMP transport and TLS remain the official obs-outputs module.
 * No platform catalog/updater, authentication or secret-bearing settings. */
static const char *local_service_name(void *unused) { (void)unused;return "Motive loopback receiver"; }
static void *local_service_create(obs_data_t *settings,obs_service_t *service) {
    (void)service;obs_data_addref(settings);return settings;
}
static void local_service_destroy(void *data) {obs_data_release(data);}
static const char *local_service_protocol(void *data) {
    return !strncmp(obs_data_get_string(data,"server"),"rtmps://",8) ? "RTMPS":"RTMP";
}
static const char *local_service_connect_info(void *data,uint32_t type) {
    if (type==OBS_SERVICE_CONNECT_INFO_SERVER_URL) return obs_data_get_string(data,"server");
    if (type==OBS_SERVICE_CONNECT_INFO_STREAM_ID) return "motive";
    return NULL;
}
static bool local_service_can_connect(void *data) {
    const char *url=obs_data_get_string(data,"server");
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
