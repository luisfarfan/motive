"""Metadata-only host/PCM alignment. Never fit clocks to measured tone edges."""
import math


def align_samples(anchor, packets, frames, sample_count):
    trace = anchor['trace']
    if trace.get('clock') != 'obs.os_gettime_ns' or trace['snapshot_busy']:
        raise ValueError('Fresh named output clock required')
    uncertainty = anchor['after'] - anchor['before']
    if not 0 <= uncertainty <= .05:
        raise ValueError('Clock bracket exceeds 50 ms; no aligned continuity verdict')
    prefix = trace['packets']
    if (not prefix or [p['sequence'] for p in prefix] != list(range(1, len(prefix)+1))
            or trace['summary']['trace_missed_records'] or trace['summary']['trace_overwritten_records']):
        raise ValueError('Complete native packet prefix required')
    native = next(p for p in prefix if p['media_type'] == 'audio')
    actual = packets[0]
    if native['pts'] != native['dts'] or native['size'] != int(actual['size']):
        raise ValueError('First AAC packet metadata differs')
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    counts = [int(f['nb_samples']) for f in frames]
    if (not pts or not all(math.isfinite(v) for v in pts) or sum(counts) != sample_count
            or any(abs(b-a-n/48000) > .0011 for a,b,n in zip(pts,pts[1:],counts))):
        raise ValueError('Decoded PCM/frame timing correspondence is incomplete')
    offset = (anchor['before']+anchor['after'])/2-trace['observed_ns']/1e9
    origin = offset + native['sys_dts_usec']/1e6 + pts[0]-float(actual['pts_time'])
    return {'first_sample_host_s': origin, 'uncertainty_s': uncertainty,
            'first_packet_pts_s': float(actual['pts_time']), 'first_frame_pts_s': pts[0],
            'decoded_frames': len(frames), 'decoded_samples': sample_count,
            'method': 'Bracketing named native query clock + first AAC metadata + every decoded frame/sample count',
            'native_payload_identity': 'NOT_MEASURED', 'clock_fitted_to_signal': False}
