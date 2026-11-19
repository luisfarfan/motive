#!/usr/bin/env python3
"""Capture the app's owned GPUI fixture, never an arbitrary desktop/window.

Requires the root's physical-test lock and a fresh, disposable owner. Records
real dual outputs, closes/reopens the fixture and observes explicit recovery.
No signing, launch, permissions or external streaming. Pixel analysis is separate.
"""
import argparse
import json
import pathlib
import socket
import time
import traceback

import verify_h13_outputs as support
from verify_h13_outputs import Client, Receiver, check, profile, sha, slots, write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]


def select_replacement(client, window, owner_pid, attempts, retry_not_ready=False):
    """One selection, with at most one explicitly requested retry of that identity.

    Preserve rejected admission as evidence. No name matching, delay, retry of
    other errors, or implicit retry in the product is introduced here.
    """
    for attempt in range(2 if retry_not_ready else 1):
        if attempt:
            matches = [w for w in client.call('devices')['devices']['windows']
                       if w.get('id') == window and w.get('pid') == owner_pid and w.get('test')]
            check(len(matches) == 1, 'same owned replacement identity before explicit retry')
        result = client.rpc('tools/call', {'name': 'select_source', 'arguments': {'window_id': window}})
        value = json.loads(result['content'][0]['text'])
        check(type(value.get('ok')) is bool and result.get('isError') == (not value['ok']),
              'selection protocol agrees with native result')
        attempts.append({'attempt': attempt + 1, 'window_id': window, 'owner_pid': owner_pid,
                         'monotonic': time.monotonic(), 'response': value})
        if value['ok'] or value.get('error', {}).get('code') != 'CAPTURE_NOT_READY':
            break
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--record-recovery', action='store_true',
                        help='Record a second bounded dual trial after explicit replacement; retain both media pairs.')
    parser.add_argument('--retry-not-ready-once', action='store_true',
                        help='Explicit test action: reselect the same owned replacement once after CAPTURE_NOT_READY; no delay or other retries.')
    parser.add_argument('--app', type=pathlib.Path, default=support.APP)
    args = parser.parse_args()
    check(10 <= args.seconds <= 120, 'bounded observation interval')
    lock = ROOT.parent / 'motive/var/run/physical-test.lock/OWNER'
    check(lock.is_file() and json.loads(lock.read_text())['worktree'] == str(ROOT), 'root owns lock')
    support.APP = args.app.absolute()
    directory = args.output.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    client, receiver = None, None
    report = {'status': 'FAIL', 'binary_sha256': sha(support.APP), 'samples': [], 'media': [],
              'pixel_freshness': 'NOT_EVALUATED', 'recovery': 'NOT_EVALUATED'}

    def save():
        write_json(directory / 'report.json', report)

    def sample(label):
        state = client.state()
        report['samples'].append({'label': label, 'monotonic': time.monotonic(),
            'sources': state['sources'], 'issues': state['issues'], 'outputs': state['outputs']})
        save()
        return state

    def wait(label, predicate, seconds=20):
        end = time.monotonic() + seconds
        while True:
            state = sample(label)
            if predicate(state):
                return state
            check(time.monotonic() < end, label, issues=state['issues'])
            time.sleep(.25)

    def owned_window():
        deadline = time.monotonic() + 5
        while True:
            candidates = [w for w in client.call('devices')['devices']['windows']
                          if w.get('test') and w['pid'] == report['initial']['pid']
                          and w['name'] == 'Motive — Fuente controlada']
            check(len(candidates) <= 1, 'unambiguous app-owned controlled window', windows=candidates)
            if candidates:
                return candidates[0]['id']
            check(time.monotonic() < deadline, 'owned fixture becomes enumerable')
            time.sleep(.2)

    try:
        client = Client(directory)
        initial = client.state()
        report['initial'] = initial
        check(all(not s['native_busy'] and not s['recovery_required'] for s in slots(initial).values()), 'idle owner')
        check(not initial['audio_mixer']['store']['inputs'], 'empty mixer')
        graph = initial['project']['graph']
        check(len(graph['scenes']) == 1 and {s['id'] for s in graph['sources']} == {'main', 'overlay'}
              and graph['sources'][0]['spec']['kind'] == 'pattern', 'disposable default project')
        client.call('set_test_window', open=True)
        window = owned_window()
        report['window_id'] = window
        client.call('select_source', window_id=window)
        client.call('set_overlay', visible=False)
        client.call('select_audio', id='tone')
        client.call('configure_video', video={'version': 1, 'resolution': 'full_hd1080',
                    'fps': 30, 'coordinate_space': 'design960'})
        for target in ('recording', 'streaming'):
            identifier = f'h14-capture-{target}'
            client.call('upsert_output_profile', profile=profile(identifier, 'videotoolbox', 4000))
            client.call('select_output_profile', target=target, profile_id=identifier)
        wait('first_surface', lambda s: not s['issues'])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        client.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
        receiver = Receiver(directory, 'received', port)
        for target in ('recording', 'streaming'):
            state = client.call('start_output', target=target)['state']
            report['media'].append({'target': target, 'path': str(receiver.path) if target == 'streaming'
                                    else slots(state)[target]['path']})
        wait('both_active', lambda s: all(v['phase'] == 'active' for v in slots(s).values()))
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            state = sample('healthy_capture')
            check(all(v['phase'] == 'active' for v in slots(state).values()), 'dual output continues')
            time.sleep(.5)
        client.call('set_test_window', open=False)
        report['loss_requested_monotonic'] = time.monotonic()
        stopped = wait('controlled_loss', lambda s: all(not v['native_busy'] for v in slots(s).values()), 45)
        report['stopped_after_loss'] = stopped
        check(any('SOURCE_UNAVAILABLE' in i for i in stopped['issues']), 'window loss observed')
        report['receiver_exit'] = receiver.wait()
        client.call('set_test_window', open=True)
        replacement = owned_window()
        report['replacement_window_id'] = replacement
        check(replacement != window, 'new native window identity')
        report['replacement_attempts'] = []
        report['explicit_selection'] = select_replacement(client, replacement, initial['pid'],
            report['replacement_attempts'], args.retry_not_ready_once)
        save()
        selection = report['explicit_selection']
        if not selection['ok']:
            if selection.get('error', {}).get('code') == 'CAPTURE_NOT_READY':
                report['status'] = 'BLOCKED'
                report['recovery'] = 'BLOCKED'
            check(False, 'replacement admission rejected', response=selection)
        for target in ('recording', 'streaming'):
            if slots(client.state())[target]['recovery_required']:
                client.call('recover_output_target', target=target)
        ready = wait('explicit_recovery', lambda s: not s['issues'])
        report['recovered_state'] = ready
        report['recovery'] = 'BUFFER_READY_MEDIA_NOT_RETESTED'
        if args.record_recovery:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            client.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
            receiver = Receiver(directory, 'recovered-received', port)
            for target in ('recording', 'streaming'):
                state = client.call('start_output', target=target)['state']
                report['media'].append({'target': target, 'phase': 'after_recovery',
                    'path': str(receiver.path) if target == 'streaming' else slots(state)[target]['path']})
            wait('recovered_both_active', lambda s: all(v['phase'] == 'active' for v in slots(s).values()))
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                state = sample('recovered_capture')
                check(not state['issues'] and all(v['phase'] == 'active' for v in slots(state).values()),
                      'recovered dual output remains healthy')
                time.sleep(.5)
            for target in ('streaming', 'recording'):
                client.call('stop_output_target', target=target)
                wait('recovered_stop_' + target, lambda s: not slots(s)[target]['native_busy'], 45)
            report['recovery_receiver_exit'] = receiver.wait()
            report['recovery'] = 'DUAL_RECORDED_PIXELS_NOT_EVALUATED'
        report['status'] = 'PARTIAL'
    except BaseException as error:
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        if client:
            try:
                if any(v['native_busy'] for v in slots(client.state()).values()):
                    client.call('cancel_all_outputs')
                    wait('cleanup_quiescence', lambda s: all(not v['native_busy'] for v in slots(s).values()), 45)
                report['final'] = client.state()
            except BaseException as error:
                report['cleanup_error'] = repr(error)
            client.close()
        if receiver and receiver.process.poll() is None:
            receiver.terminate()
        for medium in report['media']:
            path = pathlib.Path(medium['path'])
            if path.is_file():
                medium.update(sha256=sha(path), bytes=path.stat().st_size)
        save()
    print(json.dumps({'output': str(directory), 'status': report['status'], 'error': report.get('error')}))
    return int(report['status'] in ('FAIL', 'BLOCKED'))


if __name__ == '__main__':
    raise SystemExit(main())
