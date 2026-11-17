#!/usr/bin/env python3
"""Real H11 import worker / H13 shutdown overlap, on an already running app.

Run only under the caller's existing canonical H13 physical/bundle lock:
  python3 scripts/verify_h13_import_shutdown.py --lock-held --clip PATH

PATH must be an existing, controlled 1080p clip inside this worktree's
var/evidence (a ~20-second performance fixture is suitable). No media is
generated. The script copies it to one private, uniquely named inbox file,
imports that basename through the real CLI, then requests shutdown only after
observing its operation running. All commands and their latency are retained.

PASS requires running in the shutdown response, a responsive subsequent running
snapshot, shutdown_pending, and actual owner PID exit. Each successful command
while the worker is running must finish within one second. Fast imports that
leave no observable overlap are INCONCLUSIVE (exit 2), never a simulated pass.
FAIL exits 1. No app launch, build, signal, kill, production hook, or artificial
worker delay is used. CLI child timeout cannot terminate the studio owner.

Cleanup removes only this run's inbox copy, after proving the import and both
outputs inactive or the signed owner absent. An active/unresponsive owner leaves
the copy for manual cleanup. Managed assets are retained, including deduplicated
ones; no catalog/store is rewritten. App exit may hide the final import receipt:
this test proves shutdown responsiveness, not unobserved import success.
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import time
import traceback


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT/'target/Motive.app/Contents/MacOS/motive'
STORES = ('project.json', 'audio-mixer.json', 'output-profiles.json')


def check(condition, message, **details):
    if not condition:
        raise AssertionError({'check': message, **details})


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def write_report(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def file_metadata(path):
    check(not path.is_symlink(), 'no symlink metadata target', path=str(path))
    if not path.exists():
        return None
    check(path.is_file(), 'regular file', path=str(path))
    return {'sha256': sha(path), 'bytes': path.stat().st_size,
            'mode': stat.S_IMODE(path.stat().st_mode)}


def running_import(state, operation=None):
    value = state['overlays']['import']
    return (isinstance(value, dict) and value.get('phase') == 'running'
            and (operation is None or value.get('operation_id') == operation))


def outputs_idle(state):
    check(state.get('output_contract_version') == 1, 'H13 output registry')
    check(set(state['outputs']) == {'recording', 'streaming'}, 'exact two slots')
    return all(not slot['native_busy'] for slot in state['outputs'].values())


def alive(pid):
    try:
        os.kill(pid, 0)  # Existence query only; never sends a signal.
        return True
    except ProcessLookupError:
        return False


def owner(state, expected_pid=None):
    if expected_pid is not None:
        check(state['pid'] == expected_pid, 'same production owner', state=state)
    process = subprocess.run(['ps', '-p', str(state['pid']), '-o', 'comm='],
                             capture_output=True, text=True, timeout=5)
    check(process.returncode == 0 and pathlib.Path(process.stdout.strip()).resolve() == APP.resolve(),
          'owner belongs to the signed H13 bundle', process=process.stdout)


def owned_pids():
    rows = subprocess.check_output(['ps', '-ww', '-axo', 'pid=,comm='], text=True, timeout=5)
    result = []
    for row in rows.splitlines():
        fields = row.strip().split(None, 1)
        check(len(fields) == 2 and fields[0].isdigit(), 'complete process inventory')
        path = pathlib.Path(fields[1])
        if path.is_absolute() and path.resolve() == APP.resolve():
            result.append(int(fields[0]))
    return result


class CLI:
    def __init__(self, directory):
        self.stream = (directory/'operations.jsonl').open('w')

    def call(self, op, **arguments):
        request = {'op': op, **arguments}
        entry = {'transport': 'cli', 'request': request, 'request_monotonic': time.monotonic()}
        try:
            result = subprocess.run([str(APP), 'ctl', json.dumps(request)],
                                    capture_output=True, text=True, timeout=16)
            entry.update(returncode=result.returncode, stderr=result.stderr,
                         response=json.loads(result.stdout))
            check(result.returncode == (0 if entry['response'].get('ok') else 1),
                  'CLI exit code agrees with response', response=entry['response'])
            return entry['response'], time.monotonic()-entry['request_monotonic']
        except BaseException as error:
            entry['error'] = repr(error)
            raise
        finally:
            entry['response_monotonic'] = time.monotonic()
            entry['seconds'] = entry['response_monotonic']-entry['request_monotonic']
            self.stream.write(json.dumps(entry, separators=(',', ':'))+'\n')
            self.stream.flush()

    def state(self):
        response, seconds = self.call('status')
        check(response.get('ok'), 'core status available', response=response)
        return response['state'], seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--clip', type=pathlib.Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=90,
                        help='Maximum wait for the existing owner to finish; 10..120 seconds')
    args = parser.parse_args()
    if not args.lock_held:
        parser.error('--lock-held must attest existing canonical H13 lock ownership')
    if not 10 <= args.timeout_seconds <= 120:
        parser.error('--timeout-seconds must be between 10 and 120')
    directory = ROOT/'var/evidence'/f'h13-import-shutdown-{time.time_ns()}'
    directory.mkdir(parents=True)
    report = {'ok': False, 'outcome': 'FAIL', 'run': str(directory), 'arguments':
              {**vars(args), 'clip': str(args.clip)}, 'cleanup_errors': [],
              'post_shutdown_running_queries': 0, 'queries': [],
              'acceptance': 'Real import overlap, owner-thread responsiveness and actual owner exit; not an unobserved terminal import receipt.'}
    print(directory, flush=True)
    client = CLI(directory)
    inbox_copy = copy_identity = pid = lock = lock_owner = None
    try:
        common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        common = common if common.is_absolute() else ROOT/common
        lock = common.resolve().parent/'var/run/physical-test.lock/OWNER'
        lock_owner = lock.read_text()
        check('H13' in lock_owner and str(ROOT) in lock_owner, 'canonical lock belongs to this H13 worktree')
        report['lock'] = {'path': str(lock), 'owner': lock_owner}
        report['app_sha256'] = sha(APP)
        signed = subprocess.run(['codesign', '--verify', str(APP.parents[2])], capture_output=True, text=True, timeout=30)
        report['codesign'] = {'returncode': signed.returncode, 'stderr': signed.stderr}
        check(signed.returncode == 0, 'signed bundle verifies')
        clip = args.clip.resolve(strict=True)
        check(not args.clip.is_symlink() and clip.is_relative_to((ROOT/'var/evidence').resolve()),
              'explicit controlled clip is inside this worktree evidence', clip=str(clip))
        report['clip'] = {'path': str(clip), **file_metadata(clip)}
        check(0 < report['clip']['bytes'] <= 64*1024*1024, 'clip fits normal asset import quota')
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(clip)],
                               capture_output=True, text=True, timeout=30, check=True)
        report['clip_probe'] = json.loads(probe.stdout)
        video = [s for s in report['clip_probe']['streams'] if s['codec_type'] == 'video']
        check(len(video) == 1 and (video[0]['width'], video[0]['height']) == (1920, 1080), 'controlled 1080p video')
        check(0 < float(report['clip_probe']['format']['duration']) <= 60, 'normal clip duration limit')
        initial, _ = client.state()
        owner(initial)
        pid = initial['pid']
        report['initial'] = initial
        check(outputs_idle(initial) and initial['output'] == 'idle'
              and not initial['recovery_required'] and not initial['issues'], 'healthy idle production')
        check(not initial['output_lifecycle']['shutdown_pending'] and initial['overlays']['import'] is None,
              'fresh app without prior import or shutdown')
        check(initial['project']['version'] == 3 and 'video' not in initial['project']
              and (initial['width'], initial['height'], initial['fps']) == (960, 540, 30), 'fresh default v3 canvas')
        check(not initial['audio_mixer']['store']['inputs'], 'fresh empty mixer')
        check(all(s.get('overlay') is None and s['spec']['kind'] in ('pattern', 'overlay')
                  for s in initial['project']['graph']['sources']), 'controlled pattern and legacy overlay only')
        check(initial['output_configuration']['credential_ref'] is None, 'no credential in test production')
        report['stores_before'] = {name: file_metadata(ROOT/'var'/name) for name in STORES}
        report['catalog_before'] = file_metadata(ROOT/'var/assets/index.json')
        inbox = ROOT/'var/imports'
        check(inbox.is_dir() and not inbox.is_symlink() and inbox.stat().st_mode & 0o077 == 0,
              'normal private app-created inbox')
        inbox_copy = inbox/f'h13-shutdown-{time.time_ns()}{clip.suffix.lower()}'
        with inbox_copy.open('xb') as output, clip.open('rb') as source:
            metadata = os.fstat(output.fileno())
            copy_identity = (metadata.st_dev, metadata.st_ino)
            os.chmod(inbox_copy, 0o600)
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        metadata = inbox_copy.stat()
        copy_identity = (metadata.st_dev, metadata.st_ino)
        check(metadata.st_nlink == 1 and sha(inbox_copy) == report['clip']['sha256'], 'owned byte-for-byte inbox copy')
        report['inbox_copy'] = str(inbox_copy)
        check(lock.read_text() == lock_owner and sha(APP) == report['app_sha256'], 'same lock and binary before import')
        imported, elapsed = client.call('import_asset', file_name=inbox_copy.name)
        check(imported.get('ok'), 'real import accepted', response=imported)
        operation = imported['result']['import']['operation_id']
        report.update(operation_id=operation, import_response=imported, import_command_seconds=elapsed)
        check(elapsed < 1, 'import enqueue remains responsive', seconds=elapsed)
        before, seconds = client.state()
        owner(before, pid)
        report['before_shutdown'] = before
        check(before['overlays']['import'].get('operation_id') == operation, 'same import before shutdown')
        check(before['overlays']['import']['phase'] != 'failed', 'real import did not fail before shutdown',
              import_state=before['overlays']['import'])
        if not running_import(before, operation):
            report.update(outcome='INCONCLUSIVE', reason='Import finished before request_shutdown; no shutdown was requested.')
            return
        check(seconds < 1, 'status responds while import runs', seconds=seconds)
        check(lock.read_text() == lock_owner, 'same lock owner before shutdown')
        requested_at = time.monotonic()
        requested, seconds = client.call('request_shutdown')
        report.update(shutdown_response=requested, shutdown_command_seconds=seconds,
                      shutdown_requested_monotonic=requested_at)
        check(requested.get('ok'), 'shutdown request accepted', response=requested)
        request_state = requested['state']
        check(request_state['pid'] == pid and outputs_idle(request_state), 'shutdown request targets same idle owner')
        check(request_state['overlays']['import'].get('operation_id') == operation, 'same import at shutdown')
        check(request_state['overlays']['import']['phase'] != 'failed', 'real import did not fail at shutdown',
              import_state=request_state['overlays']['import'])
        overlap = running_import(request_state, operation)
        report['running_at_shutdown_response'] = overlap
        check(request_state['output_lifecycle']['shutdown_pending'], 'shutdown becomes pending')
        check(seconds < 1, 'shutdown request remains responsive', seconds=seconds)
        deadline = requested_at+args.timeout_seconds
        while alive(pid):
            check(time.monotonic() < deadline, 'owner exits after import worker completes; no forced termination', pid=pid)
            response, seconds = client.call('status')
            row = {'monotonic': time.monotonic(), 'seconds': seconds, 'response': response}
            report['queries'].append(row)
            if response.get('ok'):
                current = response['state']
                check(current['pid'] == pid and outputs_idle(current), 'same owner and idle outputs during shutdown')
                check(current['output_lifecycle']['shutdown_pending'], 'shutdown remains pending')
                operation_state = current['overlays']['import']
                check(operation_state.get('operation_id') == operation, 'stable real import operation')
                check(operation_state['phase'] != 'failed', 'real import did not fail', import_state=operation_state)
                if running_import(current, operation):
                    report['post_shutdown_running_queries'] += 1
                    check(seconds < 1, 'owner thread answers while draining import', seconds=seconds)
                else:
                    report['terminal_import_observed'] = operation_state
            else:
                code = response.get('error', {}).get('code')
                # Server reports TIMEOUT also when its response channel closes
                # during owner teardown. Accept that boundary only after the
                # import's real terminal receipt was already observed, never as
                # proof that an unobserved/running worker finished.
                check(code == 'STUDIO_UNAVAILABLE' or
                      (code == 'TIMEOUT' and 'terminal_import_observed' in report),
                      'unavailable only at observed terminal owner exit', response=response)
                check(seconds < 1, 'closing owner did not block CLI query', seconds=seconds)
                report['terminal_control_boundary'] = row
            write_report(directory/'report.json', report)
            time.sleep(.05)
        report.update(owner_exited=True, shutdown_to_exit_seconds=time.monotonic()-requested_at,
                      catalog_after=file_metadata(ROOT/'var/assets/index.json'))
        if not overlap:
            report.update(outcome='INCONCLUSIVE', reason='Import ended between the pre-shutdown query and the shutdown response.')
        elif report['post_shutdown_running_queries'] == 0:
            report.update(outcome='INCONCLUSIVE', reason='No post-request running snapshot; insufficient observable overlap to prove owner-thread responsiveness.')
        else:
            report.update(outcome='PASS')
    except BaseException as error:
        report.update(outcome='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally:
        if inbox_copy is not None and copy_identity is not None:
            try:
                check(lock.read_text() == lock_owner, 'same canonical lock for inbox cleanup')
                if pid is not None and alive(pid):
                    response, _ = client.call('status')
                    if response.get('ok'):
                        current = response['state']
                        owner(current, pid)
                        check(outputs_idle(current) and not running_import(current), 'inbox cleanup only after native/import inactivity')
                    else:
                        check(response.get('error', {}).get('code') == 'STUDIO_UNAVAILABLE' and not owned_pids(),
                              'owner exited between existence and cleanup query', response=response)
                else:
                    check(not owned_pids(), 'no signed studio process before offline inbox cleanup')
                check(not inbox_copy.is_symlink(), 'owned inbox copy was not replaced by symlink')
                metadata = inbox_copy.stat()
                check((metadata.st_dev, metadata.st_ino) == copy_identity and metadata.st_nlink == 1,
                      'same single-link owned inbox file')
                inbox_copy.unlink()
                report['inbox_removed'] = True
            except BaseException as error:
                report['cleanup_errors'].append(repr(error))
                report['retained_inbox'] = str(inbox_copy)
        try:
            if 'stores_before' in report:
                report['stores_after'] = {name: file_metadata(ROOT/'var'/name) for name in STORES}
                check(report['stores_before'] == report['stores_after'], 'project, mixer and output stores unchanged')
            if 'app_sha256' in report:
                report['final_app_sha256'] = sha(APP)
                check(report['final_app_sha256'] == report['app_sha256'], 'signed binary unchanged')
        except BaseException as error:
            report['cleanup_errors'].append(repr(error))
        if report['cleanup_errors']:
            report['outcome'] = 'FAIL'
        report['ok'] = report['outcome'] == 'PASS'
        report['finished_monotonic'] = time.monotonic()
        client.stream.close()
        write_report(directory/'report.json', report)
        print(json.dumps({'outcome': report['outcome'], 'report': str(directory/'report.json')}), flush=True)
        # Even the early INCONCLUSIVE path must have a distinct nonzero exit.
        raise SystemExit({'PASS': 0, 'FAIL': 1, 'INCONCLUSIVE': 2}[report['outcome']])


if __name__ == '__main__':
    main()
