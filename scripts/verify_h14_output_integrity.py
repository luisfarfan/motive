#!/usr/bin/env python3
"""One controlled H14 encoder/output finalization experiment.

Requires an already running signed app and the caller's physical-test lock.
Never launches/signs the app or opens devices. Only the generated pattern and
controlled libobs tone are accepted. Run --plan first for the bounded A/B matrix.
All original counters, packet metadata and media remain unchanged. Missing tail
packets are reported individually; a decode PASS is not a frame-delivery PASS.
"""

import argparse
import array
import bisect
import json
import math
import pathlib
import socket
import subprocess
import time
import traceback

import verify_h13_outputs as support
from verify_h13_outputs import Client, Receiver, check, run, sha, slots, write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIDEO = {'version': 1, 'resolution': 'full_hd1080', 'fps': 30,
         'coordinate_space': 'design960'}


def plan():
    cases = []
    for encoder in ('videotoolbox', 'x264'):
        for reorder in (False, True):
            for mode in ('recording', 'streaming', 'dual'):
                cases.append({'encoder': encoder, 'reordering': reorder,
                              'mode': mode, 'ending': 'stop'})
    cases.extend({'encoder': 'videotoolbox', 'reordering': False,
                  'mode': 'dual', 'ending': ending}
                 for ending in ('cancel', 'receiver-loss', 'shutdown'))
    return {'version': 1, 'cases': cases,
            'execution': 'serial, one invocation per case; shutdown last with a fresh disposable owner',
            'acceptance': 'NOT_EVALUATED'}


def store_identity(directory):
    result = {}
    for name in ('project.json', 'audio-mixer.json', 'output-profiles.json'):
        path = directory / name
        result[name] = ({'sha256': sha(path), 'mode': path.stat().st_mode & 0o777}
                        if path.exists() else None)
    return result


def process_exists(pid):
    return subprocess.run(['ps', '-p', str(pid), '-o', 'pid='],
                          capture_output=True).returncode == 0


def trace_for(client, target):
    result = client.call('output_diagnostics', target=target)
    check(result['packet_trace']['version'] == 1, 'packet trace version')
    check(result['packet_trace']['scope'] == 'before_output_plugin', 'trace is dispatch only')
    return result


def correlate_tail(initial_trace, final_trace, packets):
    """Match unchanged native PTS against container PTS with a measured origin.

    Each media origin is established from its first actual packet, only when
    the initial trace retains the complete beginning. Quantization allowance is
    1.1 ms for MKV/FLV millisecond timestamps; it is not a missing-frame tolerance.
    """
    summary = final_trace['summary']
    result = {'status': 'INCONCLUSIVE', 'raw_dispatch_video_packets':
              summary['observed_video_packets'], 'raw_dispatch_audio_packets':
              summary['observed_audio_packets'], 'kinds': {}}
    if initial_trace['snapshot_busy'] or final_trace['snapshot_busy']:
        result['reason'] = 'trace_snapshot_busy'
        return result
    if summary.get('quiescent_observed_ns') is None:
        result['reason'] = 'terminal_quiescence_not_observed'
        return result
    if initial_trace['summary']['trace_missed_records'] or initial_trace['summary']['trace_overwritten_records']:
        result['reason'] = 'beginning_of_trace_not_complete'
        return result
    initial_sequences = [p['sequence'] for p in initial_trace['packets']]
    if not initial_sequences or initial_sequences != list(range(1, len(initial_sequences) + 1)):
        result['reason'] = 'beginning_of_trace_not_complete'
        return result
    records = final_trace['packets']
    sequences = [p['sequence'] for p in records]
    result['tail_sequence_contiguous'] = all(b == a + 1 for a, b in zip(sequences, sequences[1:]))
    if not records or not result['tail_sequence_contiguous']:
        result['reason'] = 'missing_tail_metadata'
        return result
    # The observer increments its sequence and media counter before trying the
    # trace lock. Losing the final callback therefore leaves a contiguous but
    # incomplete tail. Only a quiescent snapshot whose last retained sequence
    # reaches the unchanged dispatch counters can establish the tail endpoint.
    observed = summary['observed_video_packets'] + summary['observed_audio_packets']
    result['tail_reaches_dispatch_endpoint'] = sequences[-1] == observed
    if not result['tail_reaches_dispatch_endpoint']:
        result['reason'] = 'missing_terminal_metadata'
        return result
    classified = []
    for kind in ('video', 'audio'):
        first_native = next((p for p in initial_trace['packets'] if p['media_type'] == kind), None)
        actual = [p for p in packets if p['codec_type'] == kind and 'pts_time' in p]
        if first_native is None or not actual:
            result['kinds'][kind] = {'status': 'INCONCLUSIVE', 'reason': 'missing_origin'}
            classified.append('INCONCLUSIVE')
            continue
        origin = float(actual[0]['pts_time']) - first_native['pts'] * first_native['timebase_num'] / first_native['timebase_den']
        container_pts = sorted(float(p['pts_time']) for p in actual)
        used_container_indices = set()
        matches, absent = [], []
        for packet in (p for p in records if p['media_type'] == kind):
            expected = packet['pts'] * packet['timebase_num'] / packet['timebase_den'] + origin
            index = bisect.bisect_left(container_pts, expected)
            lower = bisect.bisect_left(container_pts, expected - .0011)
            upper = bisect.bisect_right(container_pts, expected + .0011)
            available = [i for i in range(lower, upper) if i not in used_container_indices]
            matched_index = min(available, key=lambda i: abs(container_pts[i]-expected), default=None)
            nearby = container_pts[max(0, index-1):index+1]
            delta = min((abs(p-expected) for p in nearby), default=math.inf)
            item = {'sequence': packet['sequence'], 'native_pts': packet['pts'],
                    'container_pts_expected_s': expected, 'closest_delta_s': delta,
                    'sys_dts_usec': packet['sys_dts_usec']}
            if matched_index is not None:
                # A single container packet cannot certify two dispatches.
                used_container_indices.add(matched_index)
                item['container_packet_index'] = matched_index
                matches.append(item)
            else:
                if delta <= .0011:
                    item['correspondence_failure'] = 'container_packet_already_matched'
                stop_lo, stop_hi = summary['stop_requested_ns'], summary['stop_call_returned_ns']
                if stop_lo is None or stop_hi is None:
                    category = 'no_normal_stop_bracket'
                elif packet['sys_dts_usec'] < stop_lo // 1000:
                    category = 'before_stop_bracket'
                elif packet['sys_dts_usec'] >= (stop_hi + 999) // 1000:
                    category = 'at_or_after_stop_bracket'
                else:
                    category = 'inside_stop_bracket'
                item['stop_relation'] = category
                absent.append(item)
        status = ('ALL_TRACED_PACKETS_PRESENT' if not absent else
                  'DOCUMENTED_STOP_CUTOFF_COMPATIBLE' if all(p['stop_relation'] == 'at_or_after_stop_bracket' for p in absent) else
                  'UNEXPLAINED_PRE_STOP_ABSENCE' if any(p['stop_relation'] == 'before_stop_bracket' for p in absent) else
                  'INCONCLUSIVE')
        result['kinds'][kind] = {'status': status, 'origin_offset_s': origin,
            'quantization_tolerance_s': .0011, 'matched': matches, 'absent': absent}
        classified.append(status)
    result['status'] = ('FAIL' if 'UNEXPLAINED_PRE_STOP_ABSENCE' in classified else
        'INCONCLUSIVE' if 'INCONCLUSIVE' in classified else
        'STOP_BOUNDARY_PACKETS_NOT_DELIVERED' if 'DOCUMENTED_STOP_CUTOFF_COMPATIBLE' in classified else
        'TRACED_TAIL_PRESENT')
    return result


def analyze(record, directory):
    path = pathlib.Path(record['path'])
    result = {'status': 'FAIL', 'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
    record['analysis'] = result
    probe = json.loads(run('ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                          '-show_format', '-of', 'json', str(path), timeout=300))
    result['probe'] = probe
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    check((video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) ==
          ('h264', 1920, 1080, '30/1'), 'actual requested video', stream=video)
    check((audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2),
          'actual AAC stereo', stream=audio)
    decode = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'],
                            capture_output=True, timeout=300)
    result['decode'] = {'returncode': decode.returncode, 'stderr': decode.stderr.decode()}
    check(decode.returncode == 0 and not decode.stderr, 'full decode', result=result['decode'])
    frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time,pkt_dts_time,pict_type,key_frame',
        '-of', 'json', str(path), timeout=300))['frames']
    packets = json.loads(run('ffprobe', '-v', 'error', '-show_packets', '-show_entries',
        'packet=codec_type,pts_time,dts_time,duration_time,size,flags', '-of', 'json', str(path), timeout=300))['packets']
    timeline = directory / (record['target'] + '-timestamps.json')
    write_json(timeline, {'frames': frames, 'packets': packets})
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    gaps = [b-a for a, b in zip(pts, pts[1:])]
    check(gaps and min(gaps) > 0, 'positive decoded PTS')
    result['timeline'] = {'path': str(timeline), 'sha256': sha(timeline), 'decoded_frames': len(frames),
        'first_pts_s': pts[0], 'last_pts_s': pts[-1], 'max_gap_s': max(gaps),
        'all_gaps_over_50ms': [{'index': i+1, 'gap_s': gap} for i, gap in enumerate(gaps) if gap > .05],
        'b_frames': sum(f.get('pict_type') == 'B' for f in frames)}
    result['packet_counts'] = {k: sum(p['codec_type'] == k for p in packets) for k in ('video', 'audio')}
    result['native_final'] = record.get('native_final')
    if record.get('native_final'):
        result['raw_counter_differences'] = {
            'output_frames_minus_decoded': record['native_final']['stats']['output_frames'] - len(frames),
            'encoded_frames_minus_decoded': record['native_final']['stats']['encoded_frames'] - len(frames)}
    result['packet_timestamps'] = {}
    timestamp_gates = []
    for kind in ('video', 'audio'):
        values = [p for p in packets if p['codec_type'] == kind]
        missing = [i for i, p in enumerate(values) if 'dts_time' not in p]
        known = [float(p['dts_time']) for p in values if 'dts_time' in p]
        result['packet_timestamps'][kind] = {'missing_dts_indices': missing,
            'known_dts_strictly_increasing': all(b > a for a, b in zip(known, known[1:])),
            'first_known_dts_s': known[0] if known else None, 'last_known_dts_s': known[-1] if known else None}
        prefix = missing == list(range(len(missing)))
        permitted_prefix = (kind == 'video' and 'matroska' in probe['format']['format_name'] and
            result['timeline']['b_frames'] > 0 and prefix and len(missing) <= video.get('has_b_frames', 0))
        timestamp_gates.append((not missing or permitted_prefix) and len(known) >= 2 and
                               result['packet_timestamps'][kind]['known_dts_strictly_increasing'])
    audio_pts = [float(p['pts_time']) for p in packets if p['codec_type'] == 'audio']
    audio_gaps = [b-a for a, b in zip(audio_pts, audio_pts[1:])]
    check(audio_gaps and min(audio_gaps) > 0, 'positive AAC PTS')
    result['max_aac_gap_s'] = max(audio_gaps)
    pcm = array.array('f', run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn',
        '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-', timeout=300))
    check(pcm, 'decoded PCM present')
    result['pcm'] = {'samples': len(pcm), 'peak': max(abs(x) for x in pcm),
        'saturated_samples': sum(abs(x) >= .999 for x in pcm),
        'rms': math.sqrt(sum(x*x for x in pcm)/len(pcm))}
    result['gates'] = {'full_decode': True, 'strict_video_cadence': max(gaps) <= .05,
        'complete_known_dts_except_initial_mkv_reorder_prefix': all(timestamp_gates),
        'continuous_aac': max(audio_gaps) <= .023,
        'no_unexpected_clipping': result['pcm']['saturated_samples'] == 0,
        'reordering_disabled_has_no_b_frames': record['reordering'] or result['timeline']['b_frames'] == 0}
    result['tail_accounting'] = (correlate_tail(record['initial_trace'], record['final_trace'], packets)
        if record.get('final_trace') else {'status': 'INCONCLUSIVE', 'reason': 'terminal_trace_unavailable'})
    result['status'] = 'PASS' if all(result['gates'].values()) else 'FAIL'
    result['acceptance'] = 'NOT_EVALUATED'
    result['expected_partial'] = record['expected_partial']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--app', type=pathlib.Path, default=support.APP)
    parser.add_argument('--store-root', type=pathlib.Path, default=ROOT / 'var')
    parser.add_argument('--shutdown-report', type=pathlib.Path)
    parser.add_argument('--encoder', choices=('videotoolbox', 'x264'), default='videotoolbox')
    parser.add_argument('--reordering', action='store_true')
    parser.add_argument('--mode', choices=('recording', 'streaming', 'dual'), default='dual')
    parser.add_argument('--ending', choices=('stop', 'cancel', 'receiver-loss', 'shutdown'), default='stop')
    parser.add_argument('--seconds', type=float, default=8)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(), indent=2));return
    if not args.lock_held:
        parser.error('--lock-held requires the caller to own the canonical lock')
    if not math.isfinite(args.seconds) or not 4 <= args.seconds <= 120:
        parser.error('--seconds must be finite and between 4 and 120')
    if args.ending == 'receiver-loss' and args.mode == 'recording':
        parser.error('receiver-loss needs streaming or dual')
    if args.ending == 'shutdown' and args.shutdown_report is None:
        parser.error('shutdown requires --shutdown-report pointing to this owner private terminal report')
    support.APP = args.app.resolve()
    directory = ROOT / 'var/evidence' / ('h14-output-integrity-' + str(time.time_ns()))
    directory.mkdir(parents=True)
    report = {'version': 1, 'status': 'FAIL', 'acceptance': 'NOT_EVALUATED',
        'arguments': {k: str(v) if isinstance(v, pathlib.Path) else v for k, v in vars(args).items()},
        'app_sha256': sha(support.APP), 'script_sha256': sha(__file__), 'media': [], 'samples': [],
        'stores_before': store_identity(args.store_root), 'limits': [
            'Packet callback observes dispatch before output plugin, not confirmed delivery.',
            'A 256-record tail cannot prove every frame from an arbitrarily long session.',
            'Intentional receiver loss preserves partial media and does not certify clean finalization.',
            'No physical capture or GPUI acceptance is covered by this generated fixture.']}
    client = receiver = initial = tone = None
    profiles = []
    changed = False
    targets = ('recording', 'streaming') if args.mode == 'dual' else (args.mode,)
    def save():write_json(directory / 'report.json', report)
    def sample():
        state = client.state()
        report['samples'].append({'monotonic': time.monotonic(), 'outputs': state['outputs'], 'stats': state['stats']})
        check(not state['issues'], 'shared source health', issues=state['issues'])
        return state
    def wait(predicate, timeout=50):
        deadline = time.monotonic() + timeout
        while True:
            state = sample()
            if predicate(state):return state
            check(time.monotonic() < deadline, 'bounded native wait', outputs=state['outputs'])
            time.sleep(.1)
    print(directory, flush=True)
    try:
        client = Client(directory)
        initial = client.state();report['initial'] = initial
        check(all(not o['native_busy'] and not o['recovery_required'] for o in slots(initial).values()), 'idle healthy owner')
        check(not initial['audio_mixer']['store']['inputs'], 'empty mixer required')
        check(all(s['spec']['kind'] in ('pattern', 'overlay') and s.get('overlay') is None
                  for s in initial['project']['graph']['sources']), 'disposable controlled pattern only')
        check(initial['output_configuration']['credential_ref'] is None, 'credential-free loopback only')
        actual = pathlib.Path(run('ps', '-p', str(initial['pid']), '-o', 'comm=').decode().strip())
        check(actual.resolve() == support.APP, 'owner belongs to selected bundle')
        check('output_diagnostics' in {t['name'] for t in client.rpc('tools/list')['tools']}, 'H14 diagnostics available')
        changed = True
        client.call('set_variant', variant='horizontal')
        client.call('configure_video', video=VIDEO)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0));port = listener.getsockname()[1]
        if 'streaming' in targets:
            client.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
            receiver = Receiver(directory, 'received-rtmp', port)
        state = client.call('add_audio_input', name='H14 controlled 440 Hz', source={'kind': 'tone'})['state']
        tone = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
        client.call('set_audio_gain', input_id=tone, gain_db=-12)
        prepared_profiles = {}
        for target in targets:
            identifier = 'h14-' + target + '-' + str(time.time_ns())
            value = {'id': identifier, 'encoder': args.encoder, 'bitrate_kbps': 4000,
                     'rate_control': 'cbr', 'keyframe_seconds': 1, 'frame_reordering': args.reordering}
            client.call('upsert_output_profile', profile=value);profiles.append(identifier)
            client.call('select_output_profile', target=target, profile_id=identifier)
            prepared_profiles[target] = value
        # Configuration is immutable while either output is busy. Prepare both
        # independent profiles before beginning the first native output.
        # Adding a tone is asynchronous: a valid input can still be warming.
        # Observe real samples instead of racing the output's audio preflight.
        report['audio_ready_state'] = wait(lambda s: not s['audio_mixer']['issues'] and
            any(i['id'] == tone and i['phase'] == 'ready' and i['levels']['frames'] > 0
                for i in s['audio_mixer']['runtime']['inputs']), timeout=10)
        for target in targets:
            value = prepared_profiles[target]
            state = client.call('start_output', target=target)['state']
            item = slots(state)[target]
            record = {'target': target, 'attempt_id': item['attempt_id'], 'reordering': args.reordering,
                      'path': str(receiver.path) if target == 'streaming' else item['path'],
                      'expected_partial': args.ending == 'receiver-loss' and target == 'streaming'}
            report['media'].append(record)
            wait(lambda s: slots(s)[target]['phase'] == 'active')
            deadline = time.monotonic() + 4
            while True:
                traced = trace_for(client, target)
                trace = traced['packet_trace']
                if {'video', 'audio'} <= {p['media_type'] for p in trace['packets']}:
                    record['initial_trace'] = trace;break
                check(time.monotonic() < deadline, 'initial packet trace received')
                time.sleep(.05)
            check(traced['output']['profile'] == value, 'effective independent profile')
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            state = sample()
            check(all(slots(state)[t]['phase'] == 'active' for t in targets), 'all requested outputs active')
            time.sleep(.2)
        report['before_stop'] = sample();report['stop_request_monotonic'] = time.monotonic();save()
        if args.ending == 'shutdown':
            client.call('request_shutdown')
            deadline = time.monotonic() + 60
            while process_exists(initial['pid']):
                check(time.monotonic() < deadline, 'normal owner shutdown deadline')
                time.sleep(.1)
            report['owner_exit_observed_monotonic'] = time.monotonic()
            terminal = json.loads(args.shutdown_report.read_text())
            check(terminal['version'] == 1 and terminal['pid'] == initial['pid'], 'terminal report belongs to owner')
            report['shutdown_report'] = terminal
            for record in report['media']:
                output = terminal['outputs'][record['target']]
                check(output['attempt_id'] == record['attempt_id'] and not output['native_busy'], 'terminal attempt barrier')
                check(not output['failure'] and not output['recovery_required'], 'normal shutdown has no native error')
                record['native_final'] = output
                record['final_trace'] = terminal['packet_traces'][record['target']]
        else:
            if args.ending == 'receiver-loss':
                report['receiver_terminated_returncode'] = receiver.terminate()
                state = wait(lambda s: slots(s)['streaming']['recovery_required'] and not slots(s)['streaming']['native_busy'])
                if 'recording' in targets:
                    check(slots(state)['recording']['phase'] == 'active', 'recording survives receiver failure')
                    client.call('stop_output_target', target='recording')
            elif args.ending == 'cancel':
                client.call('cancel_all_outputs')
            else:
                for target in targets:
                    client.call('stop_output_target', target=target)
                    state = wait(lambda s: not slots(s)[target]['native_busy'])
                    if args.mode == 'dual' and target == 'recording':
                        check(slots(state)['streaming']['phase'] == 'active', 'streaming survives recording stop')
            state = wait(lambda s: all(not slots(s)[t]['native_busy'] for t in targets))
            report['quiescent_observed_monotonic'] = time.monotonic();report['final'] = state
            for record in report['media']:
                traced = trace_for(client, record['target'])
                record['native_final'] = traced['output'];record['final_trace'] = traced['packet_trace']
                check(record['native_final']['attempt_id'] == record['attempt_id'], 'same terminal attempt')
                check(bool(record['native_final']['failure']) == record['expected_partial'], 'expected native finalization result')
        if receiver:
            report['receiver_returncode'] = receiver.wait()
        report['execution_status'] = 'PASS';save()
    except BaseException as error:
        report['error'] = repr(error);report['traceback'] = traceback.format_exc()
    finally:
        errors = []
        if client and changed and initial and process_exists(initial['pid']):
            try:
                client.call('cancel_all_outputs')
                state = wait(lambda s: all(not o['native_busy'] for o in slots(s).values()))
                for target in ('recording', 'streaming'):
                    if slots(state)[target]['recovery_required']:
                        client.call('recover_output_target', target=target)
                if tone:client.call('remove_audio_input', input_id=tone)
                for target in ('recording', 'streaming'):
                    client.call('select_output_profile', target=target,
                                profile_id=initial['output_configuration'][target + '_profile'])
                for identifier in profiles:client.call('remove_output_profile', id=identifier)
                client.call('configure_video', video=initial['project'].get('video') or {**VIDEO, 'resolution': 'legacy540'})
                client.call('set_variant', variant=initial['project']['variant'])
                endpoint = initial['output_configuration']['endpoint']
                if endpoint:client.call('configure_stream', endpoint=endpoint)
                else:report['retained_loopback_endpoint'] = {'transport': 'rtmp', 'port': port}
                report['cleanup_state'] = client.state()
            except BaseException as error:errors.append(repr(error))
        if receiver and receiver.process.poll() is None:
            try:receiver.terminate()
            except BaseException as error:errors.append(repr(error))
        if client:
            try:client.close()
            except BaseException as error:errors.append(repr(error))
        report['cleanup_errors'] = errors
        report['stores_after'] = store_identity(args.store_root)
        report['stores_unchanged'] = report['stores_before'] == report['stores_after']
        report['final_app_sha256'] = sha(support.APP)
        save()
    for record in report['media']:
        try:analyze(record, directory)
        except BaseException as error:
            record.setdefault('analysis', {})['error'] = repr(error)
        save()
    report['functional_status'] = ('PASS' if not report.get('error') and not report['cleanup_errors'] and
        report['stores_unchanged'] and report['app_sha256'] == report['final_app_sha256'] and
        report['media'] and all(m.get('analysis', {}).get('status') == 'PASS' for m in report['media']) else 'FAIL')
    report['tail_accounting_statuses'] = [m.get('analysis', {}).get('tail_accounting', {}).get('status', 'INCONCLUSIVE') for m in report['media']]
    unexpected_count = any(m.get('analysis', {}).get('raw_counter_differences', {}).get('output_frames_minus_decoded', 0) != 0
                           for m in report['media'])
    report['status'] = ('FAIL' if report['functional_status'] == 'FAIL' or 'FAIL' in report['tail_accounting_statuses'] else
        'PARTIAL' if unexpected_count or any(s != 'TRACED_TAIL_PRESENT' for s in report['tail_accounting_statuses']) or
            any(m['expected_partial'] for m in report['media']) else 'PASS')
    save();print(json.dumps({'status': report['status'], 'report': str(directory / 'report.json'),
                            'tail_accounting_statuses': report['tail_accounting_statuses'],
                            'acceptance': report['acceptance']}, indent=2))
    raise SystemExit({'PASS': 0, 'PARTIAL': 2, 'FAIL': 1}[report['status']])


if __name__ == '__main__':main()
