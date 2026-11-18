#!/usr/bin/env python3
"""One 24-second desktop-audio floor control, never an exclusion acceptance test.

Run ONLY after the principal native take and its analysis are complete, under
the caller's canonical physical lock. The caller supplies the exact normal
Motive PID and its launch log and attests that MOTIVE_TEST_SELF_AUDIO was unset.
Requires idle healthy outputs and an empty mixer. No app restart, build, UI
automation, permissions, global routing/volume changes or automatic retries.

Launches ONLY our prebuilt audio fixture: 2011Hz/-30dBFS --sequence gives
0-8s tone, 8-12s zero buffers, 12-16s paused engine, 16-24s tone. Records an
owned pattern with explicit desktop audio at -6dB; monitoring stays off.
After stop barriers and owned-fixture cleanup, decodes that closed MKV once.
PASS permits consideration of ONE unchanged self-exclusion trial; it neither
runs that trial nor proves exclusion. FAIL/INCONCLUSIVE means no further retry.

Restores the initial runtime project/mixer and exact saved-store bytes/modes,
using the existing load APIs only after same-owner, same-lock idle barriers.
Profiles and output endpoint are never changed. Source instance/counter history
and completed output attempts are observations and cannot be rolled back.
"""
import argparse
import hashlib
import json
import math
import pathlib
import re
import statistics
import subprocess
import time
import traceback

from verify_h10_audio import tonal_amplitudes
from verify_h12_performance import write_project
from verify_h13_outputs import APP, ROOT, Client, check, sha, slots, write_json
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
from verify_h13_self_audio_exclusion import emitter_events
from verify_h13_system_audio import BUNDLE, FIXTURE, analyse_media, db, input_state


class FloorFailure(AssertionError):
    """Measured interference/clipping; original exclusion remains inconclusive."""


def idle(state):
    return all(not s['native_busy'] and not s['recovery_required']
               and s['phase'] == 'idle' for s in slots(state).values())


def guard_owner(client, args, lock, owner_text):
    check(lock.read_text() == owner_text, 'same canonical lock owner')
    state = client.state()
    check(state['pid'] == args.owner_pid, 'same explicit Motive PID')
    check(not state['output_lifecycle']['shutdown_pending'], 'owner not shutting down')
    return state


def wait(client, predicate, seconds=12):
    deadline = time.monotonic()+seconds
    while True:
        state = client.state()
        if predicate(state):
            return state
        check(time.monotonic() < deadline, 'bounded state wait', state=state)
        time.sleep(.1)


def backup_store(path, directory):
    check(not path.is_symlink(), 'store must not be a symlink', path=str(path))
    data = path.read_bytes() if path.exists() else None
    mode = path.stat().st_mode & 0o777 if data is not None else None
    backup = directory/(path.name+'.before')
    if data is not None:
        backup.write_bytes(data); backup.chmod(0o600)
    return {'path': str(path), 'bytes': data, 'mode': mode,
            'backup': str(backup) if data is not None else None,
            'sha256': hashlib.sha256(data).hexdigest() if data is not None else None}


def restore_store(saved):
    path = pathlib.Path(saved['path'])
    if saved['bytes'] is None:
        path.unlink(missing_ok=True)
    else:
        temporary = path.with_suffix('.floor-restore.tmp')
        temporary.write_bytes(saved['bytes']); temporary.chmod(saved['mode']); temporary.replace(path)
    check((path.read_bytes() if path.exists() else None) == saved['bytes'], 'exact store bytes restored', path=str(path))
    if path.exists():
        check(path.stat().st_mode & 0o777 == saved['mode'], 'exact store mode restored', path=str(path))


def analyze_floor(samples, sequence_offset, observations, input_id):
    """Fixed predeclared windows; no selection after inspecting their values."""
    stages = {}
    for name, start, end in [('positive_before', 2, 6), ('zero_buffers', 9, 11),
                             ('engine_paused', 13, 15), ('positive_after', 18, 22)]:
        lo, hi = round((sequence_offset+start)*48000), round((sequence_offset+end)*48000)
        check(0 <= lo < hi <= len(samples), 'complete predeclared PCM interval', stage=name)
        chunk = samples[lo:hi]
        amplitudes = {f: tonal_amplitudes(chunk, f) for f in (997, 2011)}
        windows = [{'fixture_seconds': start+i*.1, 'media_seconds': (lo+i*4800)/48000,
                    'a997': amplitudes[997][i], 'a2011': amplitudes[2011][i]}
                   for i in range(len(amplitudes[2011]))]
        measured = [row for row in observations if start <= row['fixture_seconds'] <= end]
        levels = [input_state(row['state'], input_id) for row in measured]
        fresh = (len(levels) >= 5 and all(v['phase'] == 'ready' and not v['levels']['stale']
                 and v['levels']['age_ms'] is not None and v['levels']['age_ms'] < 500 for v in levels)
                 and all(b['levels']['frames'] > a['levels']['frames'] for a, b in zip(levels, levels[1:])))
        stages[name] = {'windows': windows, 'native_samples': len(levels), 'fresh_callbacks': fresh,
                        'a2011': math.sqrt(sum(v*v for v in amplitudes[2011])/len(windows))}
    positive = [stages[name]['a2011'] for name in ('positive_before', 'positive_after')]
    reference = min(positive)  # Conservative floor limit, never a louder chosen window.
    calibrated = all(value > .006 and abs(db(value)-(-36)) < 1.5 for value in positive)
    calibrated &= abs(db(positive[1]/max(positive[0], 1e-15))) < 1.5
    threshold = reference*10**(-45/20)
    violations = []
    for name in ('zero_buffers', 'engine_paused'):
        for window in stages[name]['windows']:
            if window['a2011'] >= threshold or window['a997'] >= reference*.01:
                violations.append({'stage': name, **window})
    fresh = all(stage['fresh_callbacks'] for stage in stages.values())
    result = 'INCONCLUSIVE' if not calibrated or not fresh else 'FAIL' if violations else 'PASS'
    return {'result': result, 'positive_calibrated': calibrated, 'fresh_callbacks': fresh,
            'stages': stages, 'reference_amplitude': reference,
            'negative_2011_relative_db': -45, 'negative_2011_max_amplitude': threshold,
            'negative_997_max_fraction': .01, 'violations': violations,
            'interpretation': 'A quiet floor permits one unchanged exclusion trial; it does not prove exclusion.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-pid', required=True, type=int)
    parser.add_argument('--display-uuid', required=True)
    parser.add_argument('--motive-log', required=True, type=pathlib.Path)
    parser.add_argument('--normal-launch-confirmed', required=True, action='store_true',
                        help='Caller confirms this exact owner was launched with MOTIVE_TEST_SELF_AUDIO unset.')
    parser.add_argument('--controlled-desktop-audio', required=True, action='store_true')
    parser.add_argument('--lock-held', required=True, action='store_true')
    args = parser.parse_args()
    directory = ROOT/'var/evidence'/f'h13-self-audio-floor-{time.time_ns()}'
    directory.mkdir(); print(directory, flush=True)
    report = {'ok': False, 'result': 'INCONCLUSIVE', 'repeat_exclusion_eligible': False,
              'directory': str(directory), 'owner_pid': args.owner_pid,
              'scope': 'One desktop floor control; no Motive emitter; not GPUI or exclusion acceptance.',
              'normal_launch': {'caller_confirmed_unset': True, 'log': str(args.motive_log),
                                'limit': 'Caller provenance plus fixed diagnostic log events; no process environment inspection.'},
              'limits': ['No source attribution for unrelated desktop content.',
                         'Missing callbacks are not measured silence.',
                         'A quiet interval does not guarantee the later environment stays quiet.']}
    client = fixture = initial = lock = None
    owner_text = None
    backups, observations = [], []
    changed = False
    attempt = None

    def save():
        write_json(directory/'report.json', report)

    def stop_fixture():
        if fixture and fixture.poll() is None:
            fixture.terminate()
            try:
                fixture.wait(timeout=8)
            except subprocess.TimeoutExpired:
                fixture.kill(); fixture.wait(timeout=5)
        if fixture:
            report['fixture_returncode'] = fixture.returncode

    try:
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        common = common if common.is_absolute() else ROOT/common
        lock = common.resolve().parent/'var/run/physical-test.lock/OWNER'
        owner_text = lock.read_text()
        check(VERIFY.lock_matches(owner_text), 'canonical verification lock')
        report['shared_lock'] = {'path': str(lock), 'owner': owner_text}
        check(APP.is_file() and FIXTURE.is_file() and args.motive_log.is_file(), 'existing bundle, fixture and explicit log required')
        signature = subprocess.run(['codesign', '--verify', str(APP.parents[2])], capture_output=True, text=True, timeout=30)
        check(signature.returncode == 0, 'signed existing Motive', stderr=signature.stderr)
        report.update(app_sha256=sha(APP), fixture_sha256=sha(FIXTURE), script_sha256=sha(__file__),
                      bundle_limit='Development Frameworks symlink; no strict portable/notarized claim.')
        client = Client(directory)
        initial = guard_owner(client, args, lock, owner_text)
        actual = pathlib.Path(subprocess.check_output(['ps', '-p', str(args.owner_pid), '-o', 'comm='], text=True).strip())
        check(actual.resolve() == APP.resolve(), 'explicit owner belongs to checkout')
        check(idle(initial) and not initial['issues'] and not initial['recovery_required'], 'healthy idle owner')
        check(not initial['audio_mixer']['store']['inputs'] and initial['project']['audio'] == 'none', 'empty mixer and no legacy audio')
        importing = initial['overlays']['import']
        check(not initial['overlays']['runtime']['animations']['busy']
              and (importing is None or importing.get('phase') in ('completed', 'failed'))
              and initial['transition']['phase'] not in ('preparing', 'running'), 'quiescent production')
        check(not emitter_events(args.motive_log, args.owner_pid), 'normal owner: diagnostic emitter must be absent')
        inventory = client.call('system_audio_sources')['system_audio_sources']
        check(inventory['available'] and inventory['permission'] == 'authorized', 'existing normal screen permission')
        check(any(d['display_uuid'] == args.display_uuid and d['is_main'] and d['selectable'] for d in inventory['displays']), 'explicit selectable main display')
        check(not any(a['bundle_id'] == BUNDLE for a in inventory['applications']), 'no existing fixture instance')
        check(subprocess.run(['pgrep', '-f', re.escape(str(FIXTURE))], capture_output=True).returncode == 1, 'no existing owned fixture process')
        report['initial'] = initial
        report['initial_profiles'] = client.call('output_profiles')['store']
        report['inventory'] = inventory
        for name in ('project.json', 'audio-mixer.json', 'output-profiles.json'):
            backups.append(backup_store(VERIFY.data_root/name, directory))
        report['stores_before'] = [{k: v for k, v in item.items() if k != 'bytes'} for item in backups]
        save()

        changed = True
        client.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        scene = client.call('create_scene', name='H13 desktop floor control')['state']['project']['graph']['active_scene']
        client.call('add_source', scene_id=scene, name='Owned floor pattern', source={'kind': 'pattern'})
        state = client.call('add_audio_input', name='Explicit desktop floor',
                            source={'kind': 'system_desktop', 'display_uuid': args.display_uuid})['state']
        ident = state['audio_mixer']['store']['inputs'][0]['id']
        client.call('set_audio_gain', input_id=ident, gain_db=-6)
        stdout, stderr = directory/'fixture.jsonl', directory/'fixture.stderr.log'
        command = [str(FIXTURE), '--frequency', '2011', '--peak-dbfs', '-30', '--sequence']
        with stdout.open('xb') as out, stderr.open('xb') as err:
            fixture = subprocess.Popen(command, stdout=out, stderr=err)
        report['fixture'] = {'pid': fixture.pid, 'command': command, 'stdout': str(stdout), 'stderr': str(stderr)}
        deadline = time.monotonic()+8
        while True:
            check(fixture.poll() is None, 'owned fixture alive')
            events = [json.loads(line) for line in stdout.read_text().splitlines() if line.endswith('}')]
            sequence = next((e for e in events if e['event'] == 'sequence'), None)
            ready = next((e for e in events if e['event'] == 'ready'), None)
            if sequence and ready:
                break
            check(time.monotonic() < deadline, 'fixture startup deadline'); time.sleep(.05)
        check(ready['pid'] == fixture.pid and ready['bundle_id'] == BUNDLE and ready['frequency_hz'] == 2011
              and ready['peak_dbfs'] == -30, 'exact owned fixture identity and stimulus')
        sequence_start = sequence['uptime_seconds']
        check(0 <= time.monotonic()-sequence_start < 2, 'fixture clock agrees with local monotonic clock')
        report['fixture'].update(ready=ready, sequence_start=sequence_start)
        wait(client, lambda s: input_state(s, ident)['phase'] == 'ready', seconds=2)
        request = time.monotonic()
        started = client.call('start_output', target='recording')['state']
        attempt = slots(started)['recording']['attempt_id']
        started = wait(client, lambda s: slots(s)['recording']['phase'] == 'active', seconds=3)
        origin = time.monotonic()
        check(origin < sequence_start+1.8, 'setup retained every predeclared positive window')
        report['start'] = {'request_monotonic': request, 'ack_monotonic': origin, 'state': started,
                           'fixture_to_media_seconds': sequence_start-origin,
                           'timing_limit': 'Owner ACK-to-media origin is approximate; windows have >=1s boundary margins.'}
        instance = input_state(started, ident)['instance_id']
        with (directory/'observations.jsonl').open('x') as stream:
            while time.monotonic() < sequence_start+24:
                state = guard_owner(client, args, lock, owner_text)
                row = {'fixture_seconds': time.monotonic()-sequence_start, 'state': state}
                observations.append(row); stream.write(json.dumps(row, separators=(',', ':'))+'\n'); stream.flush()
                audio = state['audio_mixer']; item = input_state(state, ident)
                check(slots(state)['recording']['phase'] == 'active' and slots(state)['recording']['attempt_id'] == attempt
                      and slots(state)['streaming']['phase'] == 'idle', 'only owned recording active')
                check(not state['issues'] and not state['recovery_required'], 'core remains healthy')
                check(state['transition']['source_instances_created'] == started['transition']['source_instances_created'],
                      'no visual source recreation during the control')
                check(len(audio['store']['inputs']) == 1 and audio['monitoring'] == 'off'
                      and audio['store']['inputs'][0]['source'] == {'kind': 'system_desktop', 'display_uuid': args.display_uuid}
                      and audio['store']['inputs'][0]['gain_db'] == -6 and not audio['store']['inputs'][0]['muted'], 'unchanged desktop controls')
                check(item['instance_id'] == instance, 'same desktop instance')
                if item['levels']['clipped_blocks'] or audio['runtime']['mix']['clipped_blocks']:
                    raise FloorFailure('Native clipping: unsuitable floor; stop without retry')
                check(fixture.poll() is None, 'owned fixture stayed alive')
                time.sleep(min(.25, max(0, sequence_start+24-time.monotonic())))
        client.call('stop_output_target', target='recording')
        report['stopped'] = wait(client, idle, seconds=30)
        stop_fixture()  # Never leave the later pulse sequence playing during decode.
        check(not emitter_events(args.motive_log, args.owner_pid), 'normal owner stayed without diagnostic emitter')
        events = [json.loads(line) for line in stdout.read_text().splitlines() if line.endswith('}')]
        report['fixture_mode_events'] = [e for e in events if e['event'] == 'mode']
        for mode, boundary in ((1, 8), (2, 12), (0, 16)):
            check(any(e['mode'] == mode and abs(e['uptime_seconds']-sequence_start-boundary) < .5
                      for e in report['fixture_mode_events']), 'fixture delivered prescribed mode boundary', mode=mode)
        media, samples = analyse_media(pathlib.Path(slots(started)['recording']['path']), directory/'decoded')
        report['media'] = media
        report['analysis'] = analyze_floor(samples, sequence_start-origin, observations, ident)
        report['result'] = report['analysis']['result']
    except FloorFailure:
        report['result'] = 'FAIL'; report['error'] = traceback.format_exc()
    except BaseException:
        report['result'] = 'INCONCLUSIVE'; report['error'] = traceback.format_exc()
    finally:
        errors = []
        try:
            stop_fixture()
        except BaseException as failure:
            errors.append('owned fixture: '+repr(failure))
        safe = runtime_restored = False
        if client and initial and changed:
            try:
                state = guard_owner(client, args, lock, owner_text)
                recording = slots(state)['recording']
                if recording['native_busy']:
                    check(attempt is not None and recording['attempt_id'] == attempt, 'only stop our recording attempt')
                    client.call('stop_output_target', target='recording')
                state = wait(client, lambda s: all(not x['native_busy'] for x in slots(s).values()), seconds=30)
                check(state['pid'] == args.owner_pid and lock.read_text() == owner_text, 'same owner/lock after stop barrier')
                check(slots(state)['streaming']['phase'] == 'idle', 'no unrelated stream to stop')
                if slots(state)['recording']['recovery_required']:
                    check(slots(state)['recording']['attempt_id'] == attempt, 'only recover our recording failure')
                    client.call('recover_output_target', target='recording')
                safe = idle(client.state())
                check(safe, 'safe idle restore barrier')
                write_project(VERIFY.data_root / 'project.json', initial['project']); client.call('load_project')
                write_project(VERIFY.data_root / 'audio-mixer.json', initial['audio_mixer']['store']); client.call('load_audio_mixer')
                client.call('configure_transition', transition=initial['transition_configuration'])
                final = guard_owner(client, args, lock, owner_text)
                check(final['project'] == initial['project'] and final['audio_mixer']['store'] == initial['audio_mixer']['store'], 'exact runtime stores restored')
                check(client.call('output_profiles')['store'] == report['initial_profiles']
                      and final['output_configuration'] == initial['output_configuration'], 'profiles and output configuration unchanged')
                report['restored_runtime'] = final
                runtime_restored = True
            except BaseException as failure:
                errors.append('runtime restore: '+repr(failure))
        # A successful earlier idle check is not a durable permission to write:
        # load/restore may fail or the owner/lock may change in the meantime.
        safe = False
        if client and initial and changed:
            try:
                state = guard_owner(client, args, lock, owner_text)
                importing = state['overlays']['import']
                check(idle(state) and not state['overlays']['runtime']['animations']['busy']
                      and state['transition']['phase'] not in ('preparing', 'running')
                      and (importing is None or importing.get('phase') in ('completed', 'failed')),
                      'fresh same-owner quiescent disk restore barrier')
                safe = True
            except BaseException as failure:
                errors.append('disk restore barrier: '+repr(failure))
        if safe:
            for saved in backups:
                try:
                    check(lock.read_text() == owner_text, 'same lock before restoring each file')
                    restore_store(saved)
                except BaseException as failure:
                    errors.append('disk restore: '+repr(failure))
                    safe = False
                    break
            report['exact_disk_restore'] = not errors
        if changed and (not safe or not runtime_restored):
            report['cleanup_pending'] = {'reason': 'Runtime or same-owner quiescent disk restore incomplete; backups retained; do not retry.',
                                         'runtime_restored': runtime_restored, 'disk_restore_barrier_valid': safe}
        if client:
            try:
                client.close()
            except BaseException as failure:
                errors.append('client close: '+repr(failure))
        if errors:
            report['cleanup_errors'] = errors; report['result'] = 'INCONCLUSIVE'
        report['ok'] = report['result'] == 'PASS' and runtime_restored and safe and not errors
        report['repeat_exclusion_eligible'] = report['ok']
        report['next_action'] = ('One unchanged self-exclusion trial may be scheduled by the owner; never automatic.'
                                 if report['ok'] else 'NO-GO: preserve evidence and do not repeat exclusion.')
        save(); print(directory/'report.json', flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
