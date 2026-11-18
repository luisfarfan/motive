/* Bounded metadata only. Never retain encoded packet data or mutate timestamps.
 * OBS owns packet delivery; this observer runs before the output plugin. */
#define MOTIVE_OUTPUT_TRACE_CAPACITY 256
typedef struct {
    uint64_t sequence, observed_ns, size;
    int64_t pts, dts, dts_usec, sys_dts_usec;
    int32_t timebase_num, timebase_den;
    uint32_t track;
    bool video, keyframe;
} output_packet_record;
typedef struct {
    atomic_flag guard;
    atomic_uint_fast64_t sequence, video_packets, audio_packets, missed, overwritten;
    atomic_uint retained;
    uint32_t next;
    output_packet_record records[MOTIVE_OUTPUT_TRACE_CAPACITY];
} output_packet_trace;
static void output_trace_init(output_packet_trace *trace) {
    trace->guard=(atomic_flag)ATOMIC_FLAG_INIT;
    atomic_init(&trace->sequence,0);
    atomic_init(&trace->video_packets,0);
    atomic_init(&trace->audio_packets,0);
    atomic_init(&trace->missed,0);
    atomic_init(&trace->overwritten,0);
    atomic_init(&trace->retained,0);
    trace->next=0;
}
/* Only the owner calls reset, after the output/worker/callback barrier. */
static void output_trace_reset(output_packet_trace *trace) {
    atomic_store(&trace->sequence,0);
    atomic_store(&trace->video_packets,0);
    atomic_store(&trace->audio_packets,0);
    atomic_store(&trace->missed,0);
    atomic_store(&trace->overwritten,0);
    atomic_store(&trace->retained,0);
    trace->next=0;
    atomic_flag_clear_explicit(&trace->guard,memory_order_release);
}
