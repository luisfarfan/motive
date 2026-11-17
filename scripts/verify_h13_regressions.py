#!/usr/bin/env python3
"""Serial, unchanged-media-gate H1–H12 regression manifest on the H13 bundle.

Requires the caller's existing canonical H13 (portable: H14) physical/bundle lock and an idle,
disposable pattern/legacy-overlay studio with an empty mixer. This runner does
not build/sign Motive, change macOS permissions, or take/release another lock.
The original suites may create their documented owned fixtures and restart the
same signed app. They retain their full durations and media/error assertions.

Every suite starts a fresh default v3 / 960x540 / 30fps production. Do NOT call
configure_video merely to set this default: that would remove genuine v3/v4
backward-compatibility coverage. Explicit v5 coverage belongs to H13's suites.
The three store files are backed up with bytes/modes before work; restoration
requires both native output slots quiescent. Initial controlled runtime settings
are restored after all suites, with a fresh PID and no automatically started
output. A failure stops the run and preserves evidence; --suite resumes a subset
into a NEW manifest, never edits the failed one.

Physical camera suites require --camera-id, --camera-prepared (controlled content
already confirmed by the owner), and the exact normal macOS granted permissions.
Microphone suites require --microphone-id. Device IDs are never auto-selected.
The H12 native GPUI walkthrough/media decoder remains a separate manual gate.
"""

import argparse
import hashlib
import json
import os
import pathlib
import signal
import stat
import subprocess
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
from regression_reports import primary_acceptance, primary_report_path
VERIFY = verification_paths(ROOT)
APP = VERIFY.app_executable
CLIENT = VERIFY.client_executable
EVIDENCE = ROOT/'var/evidence'
STORES = ('project.json', 'audio-mixer.json', 'output-profiles.json')
LEGACY = ('verify_control.py', 'verify_control_delivery.py', 'verify_h1.py',
          'verify_scenes.py', 'verify.py', 'verify_encoding.py',
          'verify_encoding_fallback.py', 'verify_output_recovery.py',
          'verify_rtmp.py', 'verify_rtmps.py', 'verify_connect_stop.py',
          'verify_vt_stop.py', 'verify_profiles_restart.py', 'verify_h8_lifecycle.py',
          'verify_h8_keychain.py', 'verify_h9_transitions.py', 'verify_h9_faults.py',
          'verify_h10_audio.py', 'verify_h10_mixer.py')
OVERLAYS = ('verify_h11_runtime.py', 'verify_h11_visuals.py', 'verify_h11_lifecycle.py')
PERFORMANCE = ('verify_h12_performance.py',)
ALL = LEGACY + OVERLAYS + PERFORMANCE
CAMERA = {'verify_h1.py', 'verify_scenes.py', 'verify_h9_transitions.py'}
MICROPHONE = {'verify_h1.py', 'verify_h10_audio.py', 'verify_h10_mixer.py'}
SCREEN = CAMERA | {'verify.py', 'verify_h9_faults.py'}


def check(condition, label, **details):
    if not condition:
        raise AssertionError({'check': label, **details})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def assess_retained_primary(suite, entry, directory, expected_app_sha256):
    """Read only this invocation's immutable copy, never a historical alias."""
    assessment = {'status': 'FAIL', 'issues': [], 'path': None, 'sha256': None}
    try:
        relative = primary_report_path(suite, entry['reports'])
        retained = directory/'reports'/suite/relative
        content = retained.read_bytes()
        observed_hash = hashlib.sha256(content).hexdigest()
        assessment.update(path=str(retained), evidence_relative=relative, sha256=observed_hash)
        check(observed_hash == entry['reports'][relative], 'retained primary hash unchanged')
        assessment.update(primary_acceptance(json.loads(content), expected_app_sha256))
    except Exception as error:
        assessment.update(status='FAIL', issues=[{'code': 'PRIMARY_UNAVAILABLE_OR_INVALID',
                                                  'error': repr(error)}])
    return assessment


def ctl(op, *, expect=True, **args):
    result = subprocess.run([str(APP), 'ctl', json.dumps({'op': op, **args})],
                            capture_output=True, text=True, timeout=15)
    response = json.loads(result.stdout)
    if expect:
        check(response.get('ok') is True, 'core command', op=op, response=response)
    return response


def state():
    return ctl('status')['state']


def quiescent(value):
    check(value.get('output_contract_version') == 1, 'H13 output registry available')
    check(set(value['outputs']) == {'recording', 'streaming'}, 'exact two output slots')
    return all(not slot['native_busy'] for slot in value['outputs'].values())


def owner(value):
    actual = pathlib.Path(subprocess.check_output(
        ['ps', '-p', str(value['pid']), '-o', 'comm='], text=True).strip())
    check(actual.resolve() == APP.resolve(), 'owner belongs to this signed bundle', actual=str(actual))


def wait(predicate, seconds=90):
    deadline = time.monotonic()+seconds
    while True:
        current = state()
        owner(current)
        if predicate(current):
            return current
        check(time.monotonic() < deadline, 'native lifecycle timeout', state=current)
        time.sleep(.15)


def stop_app():
    current = state()
    owner(current)
    check(quiescent(current), 'restart only after both output barriers', state=current)
    ctl('request_shutdown')
    deadline = time.monotonic()+20
    while subprocess.run(['kill', '-0', str(current['pid'])], capture_output=True).returncode == 0:
        check(time.monotonic() < deadline, 'owned app shutdown completed')
        time.sleep(.1)


def launch(directory, label):
    subprocess.run(['open', '-n', '--stdout', str(directory/(label+'.runtime.log')),
                    '--stderr', str(directory/(label+'.stderr.log')), str(APP.parents[2])], check=True)
    deadline = time.monotonic()+20
    while True:
        result = ctl('status', expect=False)
        if result.get('ok'):
            current = result['state']
            owner(current)
            return current
        check(time.monotonic() < deadline, 'signed studio startup', response=result)
        time.sleep(.2)


def restoration_owner(directory, report):
    """Recover a suite that exited between its owned shutdown and reopen.

    An unavailable socket alone never proves the native workers have ended.
    Reopen only after an exact executable inventory proves the owner absent;
    a live but unresponsive process must leave the backups untouched.
    """
    response = ctl('status', expect=False)
    if response.get('ok'):
        owner(response['state'])
        return response['state']
    check(response.get('error', {}).get('code') == 'STUDIO_UNAVAILABLE',
          'cleanup owner query has a known unavailable response', response=response)
    lock = report['shared_lock']
    check(pathlib.Path(lock['path']).read_text() == lock['owner'],
          'same canonical lock owner before cleanup reopen')
    check(digest(APP) == report['app_sha256'] and digest(CLIENT) == report['client_sha256'],
          'binaries unchanged before cleanup reopen')
    processes = subprocess.check_output(['ps', '-ww', '-axo', 'pid=,comm='], text=True)
    live = []
    for line in processes.splitlines():
        fields = line.strip().split(None, 1)
        check(len(fields) == 2 and fields[0].isdigit(), 'complete process inventory', line=line)
        executable = pathlib.Path(fields[1])
        if executable.is_absolute() and executable.resolve() == APP.resolve():
            live.append(int(fields[0]))
    report['cleanup_unavailable_owner'] = {'response': response, 'live_owned_pids': live}
    check(not live, 'unresponsive signed owner is not safe to restart', pids=live)
    current = launch(directory, 'cleanup-reopen')
    check(quiescent(current), 'cleanup reopened with quiescent native slots', state=current)
    report['cleanup_reopened_pid'] = current['pid']
    return current


def store_snapshot(directory):
    result = {}
    directory.mkdir()
    for name in STORES:
        path = VERIFY.data_root/name
        check(not path.is_symlink(), 'store must not be a symlink', name=name)
        if not path.exists():
            result[name] = None
            continue
        check(path.is_file(), 'regular store file', name=name)
        content = path.read_bytes()
        backup = directory/name
        backup.write_bytes(content)
        backup.chmod(0o600)
        result[name] = {'path': str(backup), 'sha256': digest(backup),
                        'mode': stat.S_IMODE(path.stat().st_mode)}
    return result


def replace_store(name, content, mode=0o600):
    path = VERIFY.data_root/name
    check(not path.is_symlink(), 'store must not become a symlink', name=name)
    if content is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_name(name+'.h13-restore-'+str(os.getpid()))
    try:
        with temporary.open('xb') as stream:
            os.chmod(temporary, mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def restore_stores(saved):
    current = state()
    owner(current)
    check(quiescent(current), 'store restore requires quiescent native slots', state=current)
    for name, snapshot in saved.items():
        content = None if snapshot is None else pathlib.Path(snapshot['path']).read_bytes()
        if snapshot is not None:
            check(hashlib.sha256(content).hexdigest() == snapshot['sha256'], 'backup bytes unchanged', name=name)
        replace_store(name, content, 0o600 if snapshot is None else snapshot['mode'])
        path = VERIFY.data_root/name
        check(not path.exists() if snapshot is None else
              digest(path) == snapshot['sha256'] and stat.S_IMODE(path.stat().st_mode) == snapshot['mode'],
              'store bytes/mode restored', name=name)


def device_requirements(args, suites):
    devices = ctl('devices')['devices']
    if CAMERA.intersection(suites):
        check(args.camera_prepared, 'owner confirmed controlled camera content')
        matches = [item for item in devices['cameras'] if item['id'] == args.camera_id]
        check(len(matches) == 1 and devices['camera_permission'], 'explicit camera available and authorized', matches=matches)
    if MICROPHONE.intersection(suites):
        matches = [item for item in devices['audio'] if item['id'] == args.microphone_id]
        check(len(matches) == 1 and devices['microphone_permission'], 'explicit microphone available and authorized', matches=matches)
    if SCREEN.intersection(suites):
        check(devices['screen_permission'], 'normal macOS screen permission required')
    return devices


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--camera-id')
    parser.add_argument('--camera-prepared', action='store_true')
    parser.add_argument('--microphone-id')
    parser.add_argument('--stage', choices=('all', 'legacy', 'overlays', 'performance'), default='all')
    parser.add_argument('--suite', choices=ALL, action='append')
    args = parser.parse_args()
    suites = list(dict.fromkeys(args.suite or {'all': ALL, 'legacy': LEGACY,
                   'overlays': OVERLAYS, 'performance': PERFORMANCE}[args.stage]))
    if not args.lock_held:
        parser.error('--lock-held attests that the caller already owns the canonical physical/bundle lock')
    if CAMERA.intersection(suites) and (not args.camera_id or not args.camera_prepared):
        parser.error('camera suites require --camera-id and --camera-prepared')
    if MICROPHONE.intersection(suites) and not args.microphone_id:
        parser.error('microphone suites require --microphone-id')
    directory = EVIDENCE/('h13-regressions-'+str(time.time_ns()))
    directory.mkdir(parents=True)
    report = {'ok': False, 'run': str(directory), 'arguments': vars(args), 'suites': [],
              'verification_paths': VERIFY.manifest(),
              'planned_suites': suites, 'cleanup_errors': [],
              'limits': ['Native GPUI gestures and H12 walkthrough are separate manual gates.',
                         'No physical hot-unplug or simulated permission denial.',
                         'Fresh default v3/540p30 per suite; H11 still exercises real v4.',
                         'A fresh final PID restores controlled runtime settings; ephemeral attempt history resets.']}
    saved = initial = profiles = None
    changed = False
    print(directory, flush=True)
    try:
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        common = common if common.is_absolute() else ROOT/common
        lock = common.resolve().parent/'var/run/physical-test.lock/OWNER'
        lock_owner = lock.read_text()
        check(VERIFY.lock_matches(lock_owner), 'canonical lock belongs to this verification worktree')
        report['shared_lock'] = {'path': str(lock), 'owner': lock_owner}
        verified = subprocess.run(['codesign', '--verify', '--verbose=2', str(APP.parents[2])],
                                  capture_output=True, text=True, timeout=60)
        report['codesign'] = vars(verified)
        check(verified.returncode == 0, 'signed bundle verification', stderr=verified.stderr)
        report['app_sha256'], report['client_sha256'] = digest(APP), digest(CLIENT)
        # Signing changes bytes but not the Mach-O build UUID. Legacy clients
        # must come from the same build as the signed owner.
        uuids = {str(path): subprocess.check_output(['dwarfdump', '--uuid', str(path)], text=True).split()[:3]
                 for path in (APP, CLIENT)}
        check(uuids[str(APP)] == uuids[str(CLIENT)] and len(uuids[str(APP)]) == 3,
              'legacy client and bundle are the same build', uuids=uuids)
        report['build_uuids'] = uuids
        report['commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        report['script_hashes'] = {p.name: digest(p) for p in (ROOT/'scripts').glob('*.py')}
        initial = state()
        owner(initial)
        check(quiescent(initial) and not initial['recovery_required'] and not initial['issues'], 'healthy idle initial state')
        check(not initial['audio_mixer']['store']['inputs'], 'empty initial mixer')
        check(all(source['spec']['kind'] in ('pattern', 'overlay') and source.get('overlay') is None
                  for source in initial['project']['graph']['sources']), 'disposable controlled sources only')
        check(initial['output_configuration']['credential_ref'] is None, 'no existing credential reference')
        if VERIFY.portable:
            check(initial['destinations']['selected'] is None
                  and not initial['destinations']['credential_busy']
                  and not initial['destinations']['reconciliation_pending'],
                  'portable regression owner has no selected destination or pending credentials')
            check(not initial['show_control']['configured'],
                  'portable regression owner has no configured Show Control session')
        report['initial'], report['devices'] = initial, device_requirements(args, suites)
        profiles = ctl('output_profiles')['store']
        report['initial_profiles'] = profiles
        saved = store_snapshot(directory/'stores-before')
        report['stores_before'] = saved
        for name in suites:
            check(lock.read_text() == lock_owner, 'same canonical lock owner')
            check(digest(APP) == report['app_sha256'] and digest(CLIENT) == report['client_sha256'], 'binaries unchanged')
            entry = {'suite': name, 'reports': {}}
            report['suites'].append(entry)
            changed = True
            stop_app()
            current = launch(directory, name)
            check(quiescent(current) and current['output'] == 'idle' and not current['recovery_required'], 'fresh idle studio')
            check((current['width'], current['height'], current['fps']) == (960, 540, 30), 'real default canvas')
            check(current['project']['version'] == 3 and 'video' not in current['project'], 'real legacy v3 prerequisite')
            check(not current['audio_mixer']['store']['inputs'], 'fresh empty mixer')
            entry['prepared'] = current
            device_requirements(args, [name])
            if name == 'verify.py':
                ctl('set_test_window', open=True)
                deadline = time.monotonic()+10
                while not any(window.get('test') for window in ctl('devices')['devices']['windows']):
                    check(time.monotonic() < deadline, 'owned source window appears')
                    time.sleep(.15)
            if name == 'verify_h11_visuals.py':
                ctl('set_encoder', encoder='x264')  # Same explicit H12 visual-suite policy.
            options = []
            if name in CAMERA:
                options += ['--camera-id', args.camera_id]
            if name in MICROPHONE:
                options += ['--microphone-id', args.microphone_id]
            if name == 'verify_h11_runtime.py':
                options += ['--transport', 'both']
            if name == 'verify_h11_visuals.py':
                options += ['--with-video']
            python = str(ROOT/'var/verify-python/bin/python') if name in OVERLAYS+PERFORMANCE else 'python3'
            timeout = 900 if name in OVERLAYS+PERFORMANCE else 420
            before = {p: p.stat().st_mtime_ns for p in EVIDENCE.rglob('*.json')}
            started = time.monotonic()
            write_json(directory/'manifest.json', report)
            try:
                with (directory/(name+'.log')).open('w') as log:
                    process = subprocess.Popen([python, str(ROOT/'scripts'/name), *options], cwd=ROOT,
                                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    entry['process_group'] = process.pid
                    try:
                        entry['exit_code'] = process.wait(timeout=timeout)
                    except BaseException:
                        # Only this verifier's new process group: includes its
                        # MCP/FFmpeg children, never the LaunchServices owner.
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            process.wait(timeout=8)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=8)
                        raise
            except subprocess.TimeoutExpired as error:
                entry.update(exit_code=124, error=str(error))
            finally:
                entry['seconds'] = time.monotonic()-started
                for path in EVIDENCE.rglob('*.json'):
                    if directory in path.parents or path.stat().st_mtime_ns == before.get(path):
                        continue
                    relative = path.relative_to(EVIDENCE)
                    retained = directory/'reports'/name/relative
                    retained.parent.mkdir(parents=True, exist_ok=True)
                    retained.write_bytes(path.read_bytes())
                    entry['reports'][str(relative)] = digest(retained)
                write_json(directory/'manifest.json', report)
            entry['primary_acceptance'] = assess_retained_primary(name, entry, directory, report['app_sha256'])
            write_json(directory/'manifest.json', report)
            entry['after'] = state()
            owner(entry['after'])
            check(quiescent(entry['after']), 'suite leaves both native slots quiescent', suite=name)
            restore_stores(saved)
            print(name, entry['exit_code'], round(entry['seconds'], 1), flush=True)
            check(entry['exit_code'] == 0, 'original suite passed', suite=name)
            check(entry['primary_acceptance']['status'] == 'PASS',
                  'fresh primary acknowledges success without reported cleanup failure',
                  suite=name, primary_acceptance=entry['primary_acceptance'])
        report['suites_passed'] = True
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        if changed and saved is not None:
            try:
                current = restoration_owner(directory, report)
                report['before_cleanup'] = current
                if not quiescent(current):
                    ctl('cancel_all_outputs')
                    wait(quiescent)
                # Keep failed output history in the report; restart only after
                # all workers finish, then restore the controlled initial state.
                stop_app()
                launch(directory, 'restoration')
                for name, value, command in (
                    ('project.json', initial['project'], 'load_project'),
                    ('audio-mixer.json', initial['audio_mixer']['store'], 'load_audio_mixer'),
                    ('output-profiles.json', profiles, 'load_output_profiles')):
                    check(quiescent(state()), 'runtime restore requires quiescence')
                    replace_store(name, (json.dumps(value)+'\n').encode())
                    ctl(command)
                for target in ('recording', 'streaming'):
                    ctl('select_output_profile', target=target,
                        profile_id=initial['output_configuration'][target+'_profile'])
                if initial['output_configuration']['endpoint'] is not None:
                    ctl('configure_stream', endpoint=initial['output_configuration']['endpoint'])
                ctl('configure_transition', transition=initial['transition_configuration'])
                restored = state()
                check(restored['project'] == initial['project'], 'initial runtime project restored')
                check(restored['audio_mixer']['store'] == initial['audio_mixer']['store'], 'initial mixer restored')
                check(ctl('output_profiles')['store'] == profiles, 'initial profiles restored')
                check(restored['output_configuration'] == initial['output_configuration'], 'initial output selection restored')
                report['restored'] = restored
            except BaseException as error:
                report['cleanup_errors'].append(repr(error))
            # A failed runtime restore must not prevent byte restoration if the
            # owner is still available and both native barriers are satisfied.
            try:
                restore_stores(saved)
                report['stores_restored'] = True
            except BaseException as error:
                report['cleanup_errors'].append(repr(error))
        report['final_app_sha256'] = digest(APP) if APP.exists() else None
        report['final_client_sha256'] = digest(CLIENT) if CLIENT.exists() else None
        report['ok'] = (report.get('suites_passed', False) and not report.get('error') and
                        not report['cleanup_errors'] and report.get('stores_restored', False) and
                        report.get('app_sha256') == report['final_app_sha256'] and
                        report.get('client_sha256') == report['final_client_sha256'])
        write_json(directory/'manifest.json', report)
    print(directory/'manifest.json', flush=True)
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
