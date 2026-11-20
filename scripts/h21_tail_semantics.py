"""Interpret the retained dispatch/container classifier using OBS 33.0.1 stop.

The trace is before the output plugin. This does not establish whole-stream
delivery, exact stop_ts inside a bracket, or delivery to an external service.
"""


def interpret_tail(accounting, receiver_interrupted=False):
    result = {'dispatch_accounting_status': accounting['status'],
              'scope': 'Retained terminal dispatches only; not whole-stream delivery.'}
    if receiver_interrupted:
        return dict(result, status='PARTIAL', category='RECEIVER_INTERRUPTED',
                    reason='Intentional receiver loss; incomplete delivery is expected, other losses are not thereby exonerated.')
    if accounting['status'] == 'TRACED_TAIL_PRESENT':
        return dict(result, status='PASS', category='TRACED_TAIL_PRESENT')
    absent = [packet for kind in accounting.get('kinds', {}).values()
              for packet in kind.get('absent', [])]
    if accounting['status'] == 'STOP_BOUNDARY_PACKETS_NOT_DELIVERED' and absent and all(
            packet.get('stop_relation') == 'at_or_after_stop_bracket' and
            'correspondence_failure' not in packet for packet in absent):
        return dict(result, status='PASS', category='OBS_STOP_CUTOFF_COMPATIBLE',
                    reason='All absent dispatches are after the entire stop bracket; OBS mux/RTMP may discard these.')
    if accounting['status'] == 'FAIL':
        return dict(result, status='FAIL', category='UNEXPLAINED_VALID_PACKET_ABSENCE')
    return dict(result, status='INCONCLUSIVE', category='BOUNDARY_OR_METADATA_UNCERTAINTY')
