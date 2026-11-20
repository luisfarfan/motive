"""Collect an observed packet origin, not merely an active output signal.

Bounded polling belongs to the verifier. It never delays stop, alters native
packet delivery or substitutes timestamps. Missed/overwritten origins fail closed.
"""
import time


def collect_origin(client, target, attempt, timeout=5, clock=time.monotonic,
                   poll=time.sleep):
    deadline = clock() + timeout
    while True:
        result = client.call('output_diagnostics', target=target)
        if result['output']['attempt_id'] != attempt:
            raise ValueError('Output attempt changed while collecting origin')
        trace = result['packet_trace']
        summary = trace['summary']
        if summary['trace_missed_records'] or summary['trace_overwritten_records']:
            raise ValueError('Packet origin metadata lost; preserve incomplete trace')
        if not trace['snapshot_busy']:
            packets = trace['packets']
            sequences = [p['sequence'] for p in packets]
            if sequences != list(range(1, len(packets) + 1)):
                raise ValueError('Packet origin is not contiguous from sequence 1')
            if {'video', 'audio'} <= {p['media_type'] for p in packets}:
                return result
        if clock() >= deadline:
            raise TimeoutError('No complete audio/video packet origin before deadline')
        poll(0.05)
