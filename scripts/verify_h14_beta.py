#!/usr/bin/env python3
"""Plan or run one H14 acceptance stage against an explicitly identified bundle.

Default is a read-only plan. Execution records process results and immutable
evidence references; exit zero never turns a runner's PARTIAL into beta PASS.
The coordinator does not build/sign, open capture devices, or start RTMPS.
Regressions may restart the same app, as their own documented contract states.
Run stages serially while holding the canonical physical/bundle lock.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from verification_paths import verification_paths
from verification_python import verification_python

ROOT = Path(__file__).resolve().parents[1]
STAGES = ('static', 'regressions', 'memory30', 'memory60-soak',
          'show-control', 'capture', 'output-integrity')
PRODUCT_INPUTS = ('Cargo.toml', 'Cargo.lock', 'build.rs', '.cargo/config.toml',
                  'src', 'native', 'show-control/Cargo.toml', 'show-control/Cargo.lock',
                  'show-control/src', 'show-control/tests',
                  'show-control/examples/packs/matchday.json',
                  'show-control/examples/decks/matchday.json',
                  'scripts/build_obs_outputs.py', 'scripts/build_obs_capture.py')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_binding(context):
    """Bind product inputs, not the evolving verification/docs HEAD, to the build."""
    reference = context.get('compiled_source_commit')
    require(isinstance(reference, str) and reference and not reference.startswith('-'),
            'Build context needs its compiled_source_commit')
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', reference + '^{commit}'],
                                     cwd=ROOT, text=True).strip()
    difference = subprocess.check_output(['git', 'diff', '--no-ext-diff', '--no-textconv',
                                          '--binary', commit, '--', *PRODUCT_INPUTS], cwd=ROOT)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z',
                                        '--', *PRODUCT_INPUTS], cwd=ROOT).split(b'\0')
    extra = {os.fsdecode(name): digest(ROOT / os.fsdecode(name)) for name in untracked if name}
    return {'compiled_commit': commit, 'input_paths': list(PRODUCT_INPUTS),
            'tracked_match': not difference, 'diff_sha256': hashlib.sha256(difference).hexdigest(),
            'untracked_inputs': extra}


def script_hashes():
    return {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'scripts').rglob('*.py')}


def process_inventory():
    output = subprocess.check_output(['ps', '-ww', '-axo', 'pid=,pgid=,comm='], text=True)
    result = []
    for line in output.splitlines():
        fields = line.strip().split(None, 2)
        require(len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit(),
                'Incomplete process identity inventory')
        result.append({'pid': int(fields[0]), 'group': int(fields[1]), 'executable': fields[2]})
    require(bool(result), 'Empty process identity inventory')
    return result


def group_members(groups):
    return [p for p in process_inventory() if p['group'] in groups]


def owner_observation(app):
    reply = subprocess.run([str(app), 'ctl', '{"op":"status"}'],
                           capture_output=True, text=True, timeout=15)
    observed = json.loads(reply.stdout)
    if observed.get('ok'):
        require(reply.returncode == 0, 'Owner returned success with a failed process result')
        state = observed['state']
        actual = subprocess.check_output(['ps', '-p', str(state['pid']), '-o', 'comm='], text=True).strip()
        require(Path(actual).is_absolute() and Path(actual).resolve() == app.resolve(),
                'Owner uses a different executable')
        return state
    require(observed.get('error', {}).get('code') == 'STUDIO_UNAVAILABLE', 'Unknown owner error')
    for entry in process_inventory():
        path = Path(entry['executable'])
        require(not path.is_absolute() or path.resolve() != app.resolve(),
                'Live owner without a responding socket')
    return None


def require_quiescent(state):
    require(set(state['outputs']) == {'recording', 'streaming'}
            and all(slot['native_busy'] is False for slot in state['outputs'].values()),
            'Native output resources remain busy or unknown')
    require(state['overlays']['runtime']['animations']['busy'] is False
            and state['transition']['phase'] not in ('preparing', 'running'),
            'Native visual operation remains pending')
    require(state['destinations']['credential_busy'] is False
            and state['destinations']['reconciliation_pending'] == [],
            'Destination credentials or durable receipts remain pending')
    show = state['show_control']
    if show['configured']:
        require(show['jobs_total'] == len(show['jobs']), 'Truncated Show Control jobs cannot prove quiescence')
        terminal = {'completed', 'simulated', 'rejected', 'failed', 'cancelled', 'timed_out', 'needs_reconciliation'}
        require(all(job['state'] in terminal for job in show['jobs']), 'Show Control job remains pending')


def supervise(process, lock, lock_text, static_app=None):
    """No deadline or signals: a runner owns its cleanup, never the coordinator."""
    while True:
        require(lock.read_text() == lock_text, 'Canonical lock changed while child was active')
        if static_app is not None:
            for entry in process_inventory():
                path = Path(entry['executable'])
                require(not path.is_absolute() or path.resolve() != static_app.resolve(),
                        'Owner appeared while a static command was active')
        result = process.poll()
        if result is not None:
            return result
        time.sleep(.25)


def commands(args, directory):
    """Explicit argv only. Existing runners retain their assertions and timing."""
    python = sys.executable
    app = str(args.app)
    data = str(args.data_root)
    if args.stage == 'static':
        show = str(ROOT / 'show-control/Cargo.toml')
        return [['cargo', 'test', '--locked'],
                ['cargo', 'test', '--locked', '--manifest-path', show],
                ['cargo', 'clippy', '--locked', '--all-targets', '--', '-D', 'warnings'],
                ['cargo', 'clippy', '--locked', '--manifest-path', show,
                 '--all-targets', '--', '-D', 'warnings'],
                ['cargo', 'fmt', '--check'],
                ['cargo', 'fmt', '--manifest-path', show, '--check']]
    script = {'regressions': 'verify_h13_regressions.py',
              'memory30': 'verify_h14_memory.py',
              'memory60-soak': 'verify_h14_memory.py',
              'show-control': 'verify_h14_show_control.py',
              'capture': 'verify_h14_capture.py',
              'output-integrity': 'verify_h14_output_integrity.py'}[args.stage]
    command = [python, str(ROOT / 'scripts' / script), '--lock-held']
    if args.stage == 'regressions':
        if args.verification_python is not None:
            command += ['--verification-python', str(args.verification_python)]
        for suite in args.suite:
            require(suite.endswith('.py') and Path(suite).name == suite,
                    'Regression suite must be a basename accepted by its runner')
            command += ['--suite', suite]
        if args.camera_id:
            command += ['--camera-id', args.camera_id]
        if args.camera_prepared:
            command += ['--camera-prepared']
        if args.microphone_id:
            command += ['--microphone-id', args.microphone_id]
    else:
        command += ['--app', app]
    if args.stage.startswith('memory'):
        require(args.fixture is not None and args.fixture_sha256 is not None,
                'Memory stage requires controlled fixture and expected SHA-256')
        command += ['--store-root', data, '--fixture', str(args.fixture),
                    '--fixture-sha256', args.fixture_sha256, '--pause-hidden',
                    '--output', str(directory / 'media-run'), '--fps',
                    '60' if args.stage == 'memory60-soak' else '30', '--mode',
                    'dual-soak' if args.stage == 'memory60-soak' else 'lifecycle']
        if args.stage == 'memory60-soak':
            command += ['--soak-seconds', '1800']
    elif args.stage == 'show-control':
        command += ['--data-dir', data, '--await-ui-goal',
                    '--output', str(directory / 'media-run')]
    elif args.stage == 'capture':
        command += ['--output', str(directory / 'media-run'), '--seconds', '30']
    elif args.stage == 'output-integrity':
        command += ['--store-root', data, '--encoder', args.encoder,
                    '--mode', args.output_mode, '--ending', args.ending]
        if args.reordering:
            command += ['--reordering']
        if args.ending == 'shutdown':
            command += ['--shutdown-report', str(Path.home() / 'Library/Logs/Motive/last-shutdown.json')]
    return [command]


def execute(args, directory, planned):
    require(args.lock_held, 'Execution requires the already-held canonical lock')
    require(args.build_context is not None, 'Execution requires --build-context provenance')
    require(args.app.is_absolute() and args.app.is_file(), 'Absolute existing Motive executable required')
    require(args.app.name == 'motive' and args.app.parent.name == 'MacOS'
            and args.app.parents[2].suffix == '.app', 'Expected Motive .app executable layout')
    env = dict(os.environ)
    env.update(MOTIVE_TEST_APP=str(args.app.parents[2]), MOTIVE_TEST_DATA_ROOT=str(args.data_root),
               MOTIVE_TEST_RECORDINGS_ROOT=str(args.recordings_root))
    paths = verification_paths(ROOT, environ=env)
    require(paths.app_executable == args.app.resolve(), 'Validated portable executable differs')
    context_bytes = args.build_context.read_bytes()
    context = json.loads(context_bytes)
    require(Path(context['app']).resolve() == args.app.resolve(), 'Context and executable differ')
    require(context['binary_sha256'] == digest(args.app), 'Executable hash differs from build context')
    common = Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
    common = common if common.is_absolute() else ROOT / common
    run = common.resolve().parent / 'var/run'
    lock = run / 'physical-test.lock/OWNER'
    lock_text = lock.read_text()
    require(paths.lock_matches(lock_text), 'Canonical lock is not owned by this H14 worktree')
    directory.mkdir(parents=True, exist_ok=False)
    lease = run / 'h14-acceptance-stage.lock'
    lease_text = json.dumps({'pid': os.getpid(), 'directory': str(directory), 'worktree': str(ROOT),
                             'stage': args.stage, 'token': secrets.token_hex(16)}) + '\n'
    report = {'version': 1, 'stage': args.stage, 'status': 'RUNNING',
              'beta_acceptance': 'NOT_EVALUATED', 'app_sha256': context['binary_sha256'],
              'build_context': context, 'build_context_sha256': hashlib.sha256(context_bytes).hexdigest(),
              'verification_paths': paths.manifest(), 'stage_lease': str(lease),
              'lock_sha256': hashlib.sha256(lock_text.encode()).hexdigest(), 'commands': [],
              'diagnostic_errors': [], 'limits': [
                  'Process completion is not media or beta acceptance.',
                  'Consult unchanged child reports, failures, decoded media and build identities.',
                  'Changed JSON files are unattributed references, not child results or acceptance.',
                  'Process-group inventory covers this coordinator group; runners own any detached children.',
                  'No external streaming, signing, publication or automatic device selection.']}
    # A common-dir lease serializes all worktrees, before any owner query or child.
    # An existing lease is never replaced, including after a previous failure.
    lease.mkdir(mode=0o700)
    active, groups, before = None, [], {}
    child_started, retain_lease = False, True
    try:
        (lease / 'owner.json').write_text(lease_text)
        (lease / 'owner.json').chmod(0o600)
        write_json(directory / 'manifest.json', report)
        require(lock.read_text() == lock_text, 'Canonical lock changed before admission')
        report['source_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        report['source_status'] = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)
        report['source_binding'] = source_binding(context)
        require(report['source_binding']['tracked_match'] and not report['source_binding']['untracked_inputs'],
                'Product inputs differ from the compiled source commit')
        report['script_hashes'] = script_hashes()
        if args.stage == 'regressions':
            report['verification_python'] = verification_python(ROOT, args.suite, args.verification_python)
        state = owner_observation(args.app)
        if args.stage == 'static':
            require(state is None, 'Close Motive normally before static checks to avoid contaminating measurements')
        else:
            require(state is not None, 'Physical stage requires an already-open owner')
            require_quiescent(state)
            require(state['destinations']['selected'] is None,
                    'Deselect external destination before local acceptance')
            report['initial_owner_pid'] = state['pid']
        before = {p: p.stat().st_mtime_ns for p in (ROOT / 'var/evidence').rglob('*.json')}
        for index, command in enumerate(planned):
            require(lock.read_text() == lock_text, 'Canonical lock changed')
            require(digest(args.app) == report['app_sha256'], 'Bundle executable changed')
            # Recheck before every static child, not just before the first Cargo invocation.
            if args.stage == 'static':
                require(owner_observation(args.app) is None, 'Owner appeared during static checks')
            log = directory / f'stage-{index + 1}.log'
            item = {'argv': command, 'log': str(log), 'started_unix_ns': time.time_ns()}
            report['commands'].append(item)
            write_json(directory / 'manifest.json', report)
            with log.open('w') as stream:
                active = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                          stderr=subprocess.STDOUT, start_new_session=True)
                child_started = True
                groups.append(active.pid)
                item.update(pid=active.pid, process_group=active.pid)
                write_json(directory / 'manifest.json', report)
                item['returncode'] = supervise(active, lock, lock_text,
                                                args.app if args.stage == 'static' else None)
                active = None
            item.update(ended_unix_ns=time.time_ns(), log_sha256=digest(log))
            item['remaining_group_members'] = group_members(groups)
            require(not item['remaining_group_members'], 'Child group still has live processes')
            require(item['returncode'] == 0, 'Stage command failed; original log retained')
        report['status'] = 'PROCESS_COMPLETED'
    except BaseException as error:
        report.update(status='PROCESS_FAILED', error=repr(error))
    finally:
        def final_error(section, error):
            report['diagnostic_errors'].append({'section': section, 'error': repr(error)})
            report['status'] = 'PROCESS_FAILED'

        # Every observation is independent. An unreadable artifact must not erase
        # the original failure or prevent writing the rest of the provenance.
        report['evidence'] = []
        try:
            for path in (ROOT / 'var/evidence').rglob('*.json') if child_started else ():
                if path == directory / 'manifest.json':
                    continue
                try:
                    if path.stat().st_mtime_ns != before.get(path):
                        report['evidence'].append({'path': str(path), 'sha256': digest(path),
                                                   'attribution': 'CHANGED_FILE_UNATTRIBUTED'})
                except Exception as error:
                    final_error('evidence:' + str(path), error)
        except Exception as error:
            final_error('evidence_inventory', error)
        try:
            report['final_app_sha256'] = digest(args.app)
            require(report['final_app_sha256'] == report['app_sha256'], 'Executable changed during stage')
        except Exception as error:
            final_error('executable_identity', error)
        for key, observe in (('script_hashes', script_hashes),
                             ('source_binding', lambda: source_binding(context))):
            if key not in report:
                continue
            try:
                report['final_' + key] = observe()
                require(report['final_' + key] == report[key], key + ' changed during stage')
            except Exception as error:
                final_error(key, error)
        try:
            if not child_started:
                # Admission only reads. Do not retain a lease that blocks another
                # owner after rejecting its identity or an already busy operation.
                report['native_barrier'] = 'NOT_REQUIRED_NO_CHILD_STARTED'
                retain_lease = False
            else:
                child_alive = active is not None and active.poll() is None
                if child_alive:
                    report.update(status='CHILD_STILL_RUNNING', active_child_pid=active.pid)
                require(not child_alive, 'Child is still running; no signals sent')
                report['remaining_group_members'] = group_members(groups)
                require(not report['remaining_group_members'], 'Owned child group still has live processes')
                require(lock.read_text() == lock_text, 'Canonical lock changed; final owner observation is unsafe')
                require(report.get('final_app_sha256') == report['app_sha256'], 'Final executable identity is unknown')
                final = owner_observation(args.app)
                if args.stage == 'static':
                    require(final is None, 'Owner appeared during static checks')
                if final is not None:
                    require_quiescent(final)
                    report.update(native_barrier='QUIESCENT_OBSERVED', final_owner_pid=final['pid'])
                else:
                    report['native_barrier'] = 'OWNER_ABSENT_OBSERVED'
                retain_lease = False
        except Exception as error:
            report.update(native_barrier='UNKNOWN_OR_BUSY', barrier_error=repr(error))
            if report['status'] != 'CHILD_STILL_RUNNING':
                report['status'] = 'PROCESS_FAILED'
        report['lease_retained'] = retain_lease
        if retain_lease:
            report['instruction'] = 'Observe child groups and native barriers before any next stage; lease retained.'
        try:
            # Failed report writes retain the lease. Never erase an owner file
            # replaced by another actor, even after our child exited.
            write_json(directory / 'manifest.json', report)
            if not retain_lease:
                owner_file = lease / 'owner.json'
                if owner_file.exists():
                    require(owner_file.read_text() == lease_text, 'Stage lease owner changed')
                    owner_file.unlink()
                lease.rmdir()
        except Exception as error:
            retain_lease = True
            report.update(status='PROCESS_FAILED', lease_retained=True, finalization_error=repr(error))
            try:
                write_json(directory / 'manifest.json', report)
            except Exception as report_error:
                print('Unable to persist final report; inspect retained lease: ' + repr(report_error), file=sys.stderr)
    print(directory / 'manifest.json', flush=True)
    return 0 if report['status'] == 'PROCESS_COMPLETED' and not retain_lease else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--build-context', type=Path)
    parser.add_argument('--data-root', type=Path, default=Path.home() / 'Library/Application Support/local.motive.studio')
    parser.add_argument('--recordings-root', type=Path, default=Path.home() / 'Movies/Motive')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--fixture-sha256')
    parser.add_argument('--suite', action='append', default=[])
    parser.add_argument('--camera-id')
    parser.add_argument('--camera-prepared', action='store_true')
    parser.add_argument('--microphone-id')
    parser.add_argument('--verification-python', type=Path, help='Existing H11/H12 verification venv interpreter; forwarded unchanged to regressions.')
    parser.add_argument('--encoder', choices=('videotoolbox', 'x264'), default='videotoolbox')
    parser.add_argument('--output-mode', choices=('recording', 'streaming', 'dual'), default='dual')
    parser.add_argument('--ending', choices=('stop', 'cancel', 'receiver-loss', 'shutdown'), default='stop')
    parser.add_argument('--reordering', action='store_true')
    args = parser.parse_args()
    directory = (args.output or ROOT / 'var/evidence' / ('h14-beta-' + str(time.time_ns()))).absolute()
    planned = commands(args, directory)
    if not args.execute:
        print(json.dumps({'version': 1, 'stage': args.stage, 'status': 'NOT_EXECUTED',
                          'commands': planned, 'output': str(directory)}, indent=2))
        return 0
    return execute(args, directory, planned)


if __name__ == '__main__':
    raise SystemExit(main())
