#!/usr/bin/env python3
"""Prove SCK desktop excludes Motive's own OS audio using a positive control.

Requires the canonical physical-test lock, a controlled desktop AUDIO
environment and a signed Motive already started with MOTIVE_TEST_SELF_AUDIO=1.
Only an owned pattern is recorded visually. This test does not launch/restart
Motive, build, request permission, change volume/routing or use monitoring.

Required explicit target: --display-uuid UUID_FROM_SYSTEM_AUDIO_SOURCES.
Required scope acknowledgement: --controlled-desktop-audio.
--motive-log is the local stderr log of that exact diagnostic Motive launch;
only fixed diagnostic JSON events are retained, never unrelated log lines.

Phase A: external fixture 997 Hz/-30 dBFS, own Motive emitter 2011 Hz/-30 dBFS.
Phase B: external fixture 2011 Hz/-30 dBFS, same Motive emitter still playing.
The recorded desktop must contain 997 in A, suppress 2011 in A, and contain
2011 in B. Both gates fail closed without fresh player/meter observations.
Afterward the caller must close/restart Motive without the test environment.
"""
import argparse
import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import time

from h7_support import Client, EVIDENCE, ROOT
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
from verify_h10_audio import tonal_amplitude
from verify_h13_system_audio import analyse_media, db, input_state

FIXTURE = ROOT/'target/H13AudioFixture.app/Contents/MacOS/MotiveAudioFixture'
BUNDLE = 'local.motive.audiofixture'


def emitter_events(path, pid):
    # Bound reads, and neither inspect process environments nor retain other
    # application log contents. The explicit path belongs to this test launch.
    with path.open('rb') as stream:
        stream.seek(0, 2)
        end = stream.tell()
        stream.seek(max(0, end-1024*1024))
        lines = stream.read().decode('utf-8', errors='replace').splitlines()
    events = []
    for line in lines:
        if not line.startswith('{"event":"motive_test_self_audio"'):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('pid') == pid:
            events.append(event)
    return events


def observed_emitter(path, pid):
    events = emitter_events(path, pid)
    assert events, 'No diagnostic emitter events for this Motive PID'
    latest = events[-1]
    assert latest['phase'] == 'playing' and latest['playing'], latest
    assert 0 <= time.monotonic()-latest['uptime_seconds'] < 2.5, dict(stale_emitter=latest)
    assert latest['frequency_hz'] == 2011 and latest['source_peak_dbfs'] == -30
    assert -32 < latest['player_peak_dbfs'] < -28, latest
    assert -37 < latest['player_rms_dbfs'] < -29, latest
    return latest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display-uuid', required=True)
    parser.add_argument('--motive-log', required=True, type=pathlib.Path)
    parser.add_argument('--controlled-desktop-audio', action='store_true')
    parser.add_argument('--lock-dir', type=pathlib.Path)
    args = parser.parse_args()
    if not args.controlled_desktop_audio:
        parser.error('Desktop captures audio broadly; use --controlled-desktop-audio only when the environment is controlled')
    run = EVIDENCE/f'h13-self-audio-exclusion-{time.time_ns()}'
    run.mkdir(parents=True)
    report = dict(ok=False, run=str(run), stages=[], fixture_runs=[],
        scope='Controlled desktop audio; owned generated pattern video; no microphone, tone or monitoring input',
        diagnostic_emitter_cleanup='Caller must restart Motive without MOTIVE_TEST_SELF_AUDIO after this run')
    client = fixture = None
    initial = None
    desktop = scene = source = None

    def save():
        if client:
            report['mcp'] = client.ops
        (run/'report.json').write_text(json.dumps(report, indent=2))

    def launch(frequency):
        nonlocal fixture
        number = len(report['fixture_runs'])
        stdout = run/f'fixture-{number}-{frequency}.jsonl'
        stderr = run/f'fixture-{number}-{frequency}.stderr.log'
        with stdout.open('xb') as out, stderr.open('xb') as err:
            fixture = subprocess.Popen([str(FIXTURE), '--frequency', str(frequency), '--peak-dbfs', '-30'], stdout=out, stderr=err)
        record = dict(pid=fixture.pid, frequency=frequency, peak_dbfs=-30, stdout=str(stdout), stderr=str(stderr))
        report['fixture_runs'].append(record)
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            assert fixture.poll() is None, record
            for line in stdout.read_text().splitlines():
                if not line.endswith('}'):
                    continue
                event = json.loads(line)
                if event.get('event') == 'ready':
                    assert event['pid'] == fixture.pid and event['bundle_id'] == BUNDLE
                    assert event['frequency_hz'] == frequency and event['peak_dbfs'] == -30
                    record['ready'] = event
                    return
            time.sleep(.1)
        raise AssertionError(dict(fixture_start_timeout=record))

    def stop_fixture():
        if fixture and fixture.poll() is None:
            fixture.terminate()
            fixture.wait(timeout=8)

    try:
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        if not common.is_absolute(): common = ROOT/common
        lock = args.lock_dir or common.resolve().parent/'var/run/physical-test.lock'
        owner = (lock/'OWNER').read_text()
        assert VERIFY.lock_matches(owner)
        report['shared_lock'] = dict(path=str(lock.resolve()), owner=owner)
        client = Client()
        initial = client.state()
        report['initial'] = initial
        assert initial['output'] == 'idle' and not initial['audio_mixer']['store']['inputs'], 'Idle studio and empty mixer required'
        report['emitter_before'] = observed_emitter(args.motive_log, initial['pid'])
        binary = VERIFY.app_executable
        report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        report['fixture_sha256'] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        # Preserve the signature checks for both layouts. The development
        # bundle links local frameworks; portable closure/notarization have
        # separate gates and cannot be inferred from this signature result.
        signature = subprocess.run(['codesign', '--verify', str(VERIFY.app_bundle)], capture_output=True, text=True)
        assert signature.returncode == 0, signature.stderr
        report['signature_verified'] = True
        strict = subprocess.run(['codesign', '--verify', '--strict', str(VERIFY.app_bundle)], capture_output=True, text=True)
        report['strict_bundle_validation'] = dict(returncode=strict.returncode, stderr=strict.stderr,
            limitation=('Portable signature result only; dependency closure, notarization and second-Mac validation are separate gates'
                        if VERIFY.portable else
                        'Local development bundle uses external pinned OBS Frameworks symlink; not portable/notarized'))
        inventory = client.call('system_audio_sources')['system_audio_sources']
        assert inventory['available'] and inventory['permission'] == 'authorized', inventory
        assert any(d['display_uuid'] == args.display_uuid and d['is_main'] and d['selectable'] for d in inventory['displays']), inventory['displays']
        assert not any(a['bundle_id'] == BUNDLE for a in inventory['applications']), 'Another fixture exists; do not capture or stop it'
        report['inventory'] = inventory
        launch(997)
        state = client.call('add_audio_input', name='Owned desktop exclusion test', source=dict(kind='system_desktop', display_uuid=args.display_uuid))['state']
        assert len(state['audio_mixer']['store']['inputs']) == 1
        desktop = state['audio_mixer']['store']['inputs'][0]['id']
        client.wait(lambda s: input_state(s, desktop)['phase'] == 'ready')
        scene = client.call('create_scene', name='H13 owned exclusion pattern')['state']['project']['graph']['active_scene']
        before = {s['id'] for s in client.state()['project']['graph']['sources']}
        graph = client.call('add_source', scene_id=scene, name='H13 exclusion pattern', source=dict(kind='pattern'))['state']['project']['graph']
        source = next(s['id'] for s in graph['sources'] if s['id'] not in before)
        client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
        start = client.call('start_recording')['state']
        report['start'] = start
        origin = time.monotonic()
        instance = input_state(start, desktop)['instance_id']

        def hold(name):
            stage = dict(name=name, start=time.monotonic()-origin, samples=[])
            report['stages'].append(stage)
            deadline = time.monotonic()+6.3
            while time.monotonic() < deadline:
                time.sleep(.25)
                state = client.state()
                assert state['pid'] == initial['pid'] and state['output'] == 'recording'
                assert len(state['audio_mixer']['store']['inputs']) == 1
                assert state['audio_mixer']['store']['inputs'][0]['source'] == dict(kind='system_desktop', display_uuid=args.display_uuid)
                assert input_state(state, desktop)['instance_id'] == instance
                assert state['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0
                assert state['transition']['source_instances_created'] == start['transition']['source_instances_created']
                stage['samples'].append(dict(seconds=time.monotonic()-origin, state=state, emitter=observed_emitter(args.motive_log, initial['pid'])))
            stage['end'] = time.monotonic()-origin
            assert len({round(v['emitter']['position_seconds'], 3) for v in stage['samples']}) >= 2, 'Own emitter clock did not advance during this phase'
            save()

        hold('external_997_own_2011')
        stop_fixture()
        launch(2011)
        client.wait(lambda s: input_state(s, desktop)['phase'] == 'ready')
        hold('external_2011_positive_control')
        report['stop'] = client.stop()
        assert report['stop']['end']['output'] == 'idle' and report['stop']['end']['output_code'] == 0
        media, samples = analyse_media(pathlib.Path(start['output_path']), run/'decoded')
        report['media'] = media
        report['active_counter_delta'] = {key: report['stop']['end']['stats'][key]-start['stats'][key]
            for key in ('lagged_frames', 'video_skipped_frames', 'rendered_frames')}
        report['max_output_dropped_frames'] = max(v['state']['stats']['output_dropped_frames'] for stage in report['stages'] for v in stage['samples'])
        for stage in report['stages']:
            # Analyse several complete interior seconds, avoiding startup,
            # process relaunch and encoder/mute boundaries.
            windows = []
            for seconds in (stage['start']+1, stage['start']+2, stage['start']+3, stage['start']+4):
                block = samples[round(seconds*48000):round((seconds+1)*48000)]
                assert len(block) == 48000
                windows.append(dict(a997=tonal_amplitude(block, 997), a2011=tonal_amplitude(block, 2011),
                    rms_dbfs=db(math.sqrt(sum(x*x for x in block)/len(block)))))
            stage['decoded_windows'] = windows
            stage['a997'] = statistics.median(v['a997'] for v in windows)
            stage['a2011'] = statistics.median(v['a2011'] for v in windows)
        negative, positive = report['stages']
        assert negative['a997'] > .006, negative['decoded_windows']
        assert positive['a2011'] > .006, positive['decoded_windows']
        # Equal source level and unchanged desktop gain calibrate sensitivity at
        # 2011 Hz. Do not infer exclusion from a silent/broken capture path.
        assert abs(db(negative['a997']/positive['a2011'])) < 1.5
        report['own_2011_suppression_db'] = db(negative['a2011']/positive['a2011'])
        assert report['own_2011_suppression_db'] < -45, report['own_2011_suppression_db']
        assert positive['a997'] < negative['a997']*.01, positive['decoded_windows']
        events = emitter_events(args.motive_log, initial['pid'])
        observed = [e for e in events if e.get('phase') == 'playing' and origin <= e['uptime_seconds'] <= origin+report['stages'][-1]['end']]
        assert len(observed) >= 15 and all(e['playing'] for e in observed)
        assert len({round(e['position_seconds'], 3) for e in observed}) >= 2
        assert max(b['uptime_seconds']-a['uptime_seconds'] for a, b in zip(observed, observed[1:])) < 2
        report['emitter_observations'] = observed
        assert report['active_counter_delta']['lagged_frames'] == 0 and report['active_counter_delta']['video_skipped_frames'] == 0 and report['max_output_dropped_frames'] == 0, report['active_counter_delta']
        report['ok'] = True
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        save()
        try:
            if client:
                if client.state()['output'] not in ('idle', 'error'): client.stop()
                if client.state()['output'] == 'idle':
                    client.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
                    if initial: client.call('select_scene', scene_id=initial['project']['graph']['active_scene'])
                    if scene: client.call('remove_scene', scene_id=scene)
                    if source: client.call('remove_source', source_id=source)
                    if desktop: client.call('remove_audio_input', input_id=desktop)
                    if initial: client.call('configure_transition', transition=initial['transition_configuration'])
        except BaseException as error:
            report['cleanup_error'] = repr(error)
            report['ok'] = False
        try:
            stop_fixture()
        except BaseException as error:
            report['fixture_cleanup_error'] = repr(error)
            report['ok'] = False
        save()
        if client:
            try: client.close()
            except BaseException as error:
                report['mcp_cleanup_error'] = repr(error)
                report['ok'] = False
                save()
        print(run/'report.json', flush=True)


if __name__ == '__main__':
    main()
