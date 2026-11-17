/* Test-only OS playback, deliberately outside OBS and its monitoring path.
 * Root bridge calls start once after successful engine initialization and stop
 * on teardown. Default is inert. No serialized settings, paths, CLI/MCP command,
 * audio-session category, device selection, or global volume is involved.
 * AVAudioPlayer owns playback timing; the timer below only observes its meter.
 */
#import <AVFoundation/AVFoundation.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static AVAudioPlayer *motive_self_audio_player;
static NSTimer *motive_self_audio_timer;

static void self_audio_u16(uint8_t *p,uint16_t value) {p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8);}
static void self_audio_u32(uint8_t *p,uint32_t value) {
    p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8);p[2]=(uint8_t)(value>>16);p[3]=(uint8_t)(value>>24);
}
static NSData *motive_self_audio_wave(void) {
    const uint32_t frames=48000,channels=2,bytes=frames*channels*2;
    NSMutableData *wave=[NSMutableData dataWithLength:44+bytes];uint8_t *data=wave.mutableBytes;
    memcpy(data,"RIFF",4);self_audio_u32(data+4,36+bytes);memcpy(data+8,"WAVEfmt ",8);
    self_audio_u32(data+16,16);self_audio_u16(data+20,1);self_audio_u16(data+22,channels);
    self_audio_u32(data+24,48000);self_audio_u32(data+28,48000*channels*2);
    self_audio_u16(data+32,channels*2);self_audio_u16(data+34,16);
    memcpy(data+36,"data",4);self_audio_u32(data+40,bytes);
    for(uint32_t frame=0;frame<frames;frame++) {
        int16_t sample=(int16_t)lround(32767.0*0.03162277660168379*sin(2*M_PI*2011.0*frame/48000.0));
        for(uint32_t channel=0;channel<channels;channel++)self_audio_u16(data+44+(frame*channels+channel)*2,(uint16_t)sample);
    }
    return wave;
}
static void motive_self_audio_observe(const char *phase) {
    AVAudioPlayer *player=motive_self_audio_player;
    [player updateMeters];
    double peak=player?[player peakPowerForChannel:0]:-160;
    double rms=player?[player averagePowerForChannel:0]:-160;
    fprintf(stderr,"{\"event\":\"motive_test_self_audio\",\"phase\":\"%s\",\"pid\":%d,\"uptime_seconds\":%.6f,\"playing\":%s,\"position_seconds\":%.6f,\"frequency_hz\":2011,\"source_peak_dbfs\":-30,\"player_peak_dbfs\":%.4f,\"player_rms_dbfs\":%.4f}\n",
        phase,getpid(),NSProcessInfo.processInfo.systemUptime,player.playing?"true":"false",player.currentTime,
        isfinite(peak)?peak:-160,isfinite(rms)?rms:-160);
    fflush(stderr);
}
static bool motive_self_audio_fixture_start(void) {
    const char *enabled=getenv("MOTIVE_TEST_SELF_AUDIO");
    if(!enabled || strcmp(enabled,"1"))return true;
    if(motive_self_audio_player)return motive_self_audio_player.playing;
    NSError *error=nil;
    AVAudioPlayer *player=[[AVAudioPlayer alloc] initWithData:motive_self_audio_wave() fileTypeHint:AVFileTypeWAVE error:&error];
    player.numberOfLoops=-1;player.volume=1;player.meteringEnabled=YES;
    if(!player || ![player prepareToPlay] || ![player play]) {
        fprintf(stderr,"{\"event\":\"motive_test_self_audio\",\"phase\":\"failed\",\"pid\":%d,\"code\":\"SELF_AUDIO_FIXTURE_START_FAILED\"}\n",getpid());
        fflush(stderr);return false;
    }
    motive_self_audio_player=player;
    motive_self_audio_observe("started");
    motive_self_audio_timer=[NSTimer scheduledTimerWithTimeInterval:0.5 repeats:YES block:^(NSTimer *timer) {
        (void)timer;motive_self_audio_observe("playing");
    }];
    return true;
}
static void motive_self_audio_fixture_stop(void) {
    [motive_self_audio_timer invalidate];motive_self_audio_timer=nil;
    if(motive_self_audio_player) {
        [motive_self_audio_player stop];motive_self_audio_observe("stopped");motive_self_audio_player=nil;
    }
}
