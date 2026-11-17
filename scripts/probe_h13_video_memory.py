#!/usr/bin/env python3
"""One bounded memory probe: fresh 540p30 -> four videos -> reconcile -> release.

Run only while holding the canonical physical/bundle lock, with a freshly opened
signed Motive from this checkout, a visible studio, empty mixer and idle outputs:
    python3 scripts/probe_h13_video_memory.py --lock-held

The caller captures the app's runtime log separately (created/destroyed sources).
This script never builds/signs/launches/quits the app, opens capture devices or
starts outputs. It generates the H12 1080p30/6s testsrc2 fixture before sampling,
then measures fixed 8s/8s/8s/20s phases, with vmmap summaries BETWEEN phases.
No automatic repeats, RSS success threshold, allocator purge or preview change.

Reuses H12 Sampler/process_sample/import_asset/write_project and their media,
child-count, render and CPU-clock checks. Restores the original runtime project
and exact project.json bytes/mode, removes only its new asset/inbox, and verifies
mixer/profile stores unchanged. Sampler rows during vmmap are retained but are
excluded from phase statistics; vmmap can perturb residency and later phases.
This is a directed diagnostic, not an equivalent repeat of the full H12 suite.
"""
import argparse
import json
import pathlib
import subprocess
import time
import traceback

from h7_support import process_sample
from verify_h11_visuals import import_asset
from verify_h12_performance import Sampler, write_project
from verify_h13_outputs import APP, ROOT, Client, check, sha, write_json


class ProbeClient(Client):
    def wait(self, predicate, timeout=80):
        deadline = time.monotonic() + timeout
        while True:
            state = self.state()
            if predicate(state):
                return state
            check(time.monotonic() < deadline, 'bounded owner wait', state=state)
            time.sleep(.15)


def file_state(path):
    return {'sha256': sha(path), 'mode': path.stat().st_mode & 0o777} if path.exists() else None


def owner(state):
    actual = pathlib.Path(subprocess.check_output(
        ['ps', '-p', str(state['pid']), '-o', 'comm='], text=True).strip())
    check(actual.resolve() == APP.resolve(), 'owner belongs to signed checkout', actual=str(actual))


def idle(state):
    check(set(state['outputs']) == {'recording', 'streaming'}, 'two output slots')
    check(all(not slot['native_busy'] for slot in state['outputs'].values()), 'outputs idle')
    check(not state['output_lifecycle']['shutdown_pending'], 'not shutting down')
    check(not state['audio_mixer']['store']['inputs'], 'mixer stays empty')
    check((state['width'], state['height'], state['fps']) == (960, 540, 30), 'unchanged 540p30')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', required=True, action='store_true')
    parser.parse_args()
    stamp = time.time_ns()
    directory = ROOT / 'var/evidence' / f'h13-video-memory-{stamp}'
    directory.mkdir(parents=True)
    report = {'ok': False, 'result': 'FAIL', 'directory': str(directory),
              'phases': [], 'operations': [], 'vmmap': [],
              'scope': 'One idle 540p30 source-lifecycle diagnostic; no output encoders or physical capture.',
              'limits': ['RSS is not private physical footprint or a leak diagnosis.',
                         '20Hz target sampling can miss short peaks; retain actual intervals.',
                         'vmmap is outside measured phases but can perturb residency and later phases.',
                         'A source destruction log is after plugin destruction but before all OBS async resource frees.',
                         'No memory budget gate; ok means probe invariants and cleanup completed.']}
    c = sampler = original = disk = asset = inbox = None
    owned_asset = owned_inbox = changed = False
    lock = lock_owner = None
    project = ROOT / 'var/project.json'
    stores = [ROOT / 'var/audio-mixer.json', ROOT / 'var/output-profiles.json']
    store_before = {}
    print(directory, flush=True)
    try:
        common = pathlib.Path(subprocess.check_output(
            ['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
        common = common if common.is_absolute() else ROOT / common
        lock = common.resolve().parent / 'var/run/physical-test.lock/OWNER'
        lock_owner = lock.read_text()
        check('H13' in lock_owner and str(ROOT) in lock_owner, 'canonical lock belongs to checkout')
        report['shared_lock'] = {'path': str(lock), 'owner': lock_owner}
        signed = subprocess.run(['codesign', '--verify', '--verbose=2', str(APP.parents[2])],
                                capture_output=True, text=True, timeout=45)
        report['codesign'] = {'code': signed.returncode, 'stderr': signed.stderr}
        check(signed.returncode == 0, 'signed existing bundle')
        report['bundle_limit'] = 'Normal signature verification; dev Frameworks absolute symlink is not --strict portable.'
        report['app_sha256'] = sha(APP)
        report['scripts'] = {name: sha(ROOT / 'scripts' / name) for name in
                             ('probe_h13_video_memory.py', 'verify_h12_performance.py',
                              'verify_h11_visuals.py', 'verify_h13_outputs.py', 'h7_support.py')}
        c = ProbeClient(directory)
        original = c.state(); owner(original); idle(original)
        check(not original['issues'] and not original['recovery_required'], 'healthy initial state')
        check(all(s['spec']['kind'] in ('pattern', 'overlay') and s.get('overlay') is None
                  for s in original['project']['graph']['sources']), 'controlled initial sources')
        check(not original['overlays']['runtime']['sources'], 'no creative source at startup')
        check(all(s['attempt_id'] is None for s in original['outputs'].values()), 'fresh owner: no output attempts')
        check(original['transition']['source_instances_created'] == len(original['project']['graph']['sources']),
              'fresh owner: no previous visual instances')
        report['initial'] = original
        report['launch_time'] = subprocess.check_output(
            ['ps', '-p', str(original['pid']), '-o', 'lstart='], text=True).strip()
        disk = (project.read_bytes(), project.stat().st_mode & 0o777) if project.exists() else (None, None)
        report['project_disk_before'] = {'exists': disk[0] is not None, 'mode': disk[1]}
        if disk[0] is not None:
            backup = directory / 'project-before.json'
            backup.write_bytes(disk[0]); backup.chmod(0o600)
            report['project_disk_before'].update(path=str(backup), sha256=sha(backup))
        store_before = {str(p): file_state(p) for p in stores}
        report['stores_before'] = store_before

        fixture = directory / f'owned-1080p-{stamp}.mp4'
        command = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                   'testsrc2=size=1920x1080:rate=30', '-t', '6', '-c:v', 'libx264',
                   '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', str(fixture)]
        subprocess.run(command, check=True, timeout=60)
        report['fixture'] = {'command': command, 'path': str(fixture), 'sha256': sha(fixture)}
        existing = {a['id'] for a in c.call('list_assets')['result']['assets']}
        inbox = ROOT / 'var/imports' / fixture.name
        check(not inbox.exists(), 'unique owned inbox path')
        owned_inbox = True
        asset = import_asset(c, fixture)['asset']; owned_asset = asset['id'] not in existing
        report['asset'] = asset
        sampler = Sampler(original['pid'])

        def operation(label, fn):
            check(lock.read_text() == lock_owner, 'canonical lock unchanged')
            lo = time.monotonic(); result = fn(); hi = time.monotonic(); time.sleep(.1)
            report['operations'].append({'label': label, 'start_monotonic': lo, 'end_monotonic': hi,
                                         'milliseconds': (hi-lo)*1000, **sampler.interval(lo, hi+.1)})
            return result

        def phase(label, expected_count, seconds):
            ps_before, _ = process_sample(original['pid'])
            lo = time.monotonic(); before = c.state(); snapshots = []
            while time.monotonic() - lo < seconds:
                time.sleep(.5); state = c.state(); snapshots.append(state)
                check(state['pid'] == original['pid'], 'same owner'); idle(state)
                videos = [s for s in state['overlays']['runtime']['sources'] if s['kind'] == 'video']
                check(len(videos) == expected_count, 'expected video source count')
                check(all(v['audio_mixers'] == 0 and v['child_instances_created'] == 1 for v in videos),
                      'one silent child per video')
                check(not state['issues'] and all(v['health'] == '' for v in videos),
                      'no source runtime errors', issues=state['issues'], videos=videos)
            hi = time.monotonic(); end = snapshots[-1]
            check(end['stats']['rendered_frames'] - before['stats']['rendered_frames'] > seconds*20,
                  'H12 render-progress gate')
            ps_after, _ = process_sample(original['pid'])
            rows = [r for r in sampler.rows if lo <= r['monotonic'] <= hi]
            cpu = rows[-1]['cpu_total_s'] - rows[0]['cpu_total_s']
            check(abs(cpu - (ps_after-ps_before)) < .3, 'H12 CPU time-unit cross-check')
            values = {'label': label, 'start_monotonic': lo, 'end_monotonic': hi, 'seconds': hi-lo,
                      'cpu_seconds_libproc': cpu, 'cpu_seconds_ps': ps_after-ps_before,
                      'all': sampler.interval(lo, hi), 'steady_after_2s': sampler.interval(lo+2, hi),
                      'render_lag_delta': end['stats']['lagged_frames'] - before['stats']['lagged_frames'],
                      'before': before, 'snapshots': snapshots,
                      'media_times_ms': {v['id']: sorted({s['media_time_ms'] for snap in snapshots
                                        for s in snap['overlays']['runtime']['sources'] if s['id'] == v['id']})
                                         for v in videos},
                      'estimated_visual_bytes': sum(s.get('framebuffer_estimate_bytes', 0) +
                                                    s.get('text_atlas_estimate_bytes', 0)
                                                    for s in end['overlays']['runtime']['sources'])}
            report['phases'].append(values)
            check(all(len(positions) >= 2 for positions in values['media_times_ms'].values()),
                  'each video media clock advances', media_times_ms=values['media_times_ms'])
            print(label, values['all'], 'lag', values['render_lag_delta'], flush=True)
            write_json(directory / 'report.json', report)

        def boundary(label):
            check(lock.read_text() == lock_owner, 'canonical lock unchanged before vmmap')
            state = c.state(); owner(state); idle(state)
            check(state['pid'] == original['pid'], 'same owner before vmmap')
            lo = time.monotonic()
            result = subprocess.run(['vmmap', '-summary', str(original['pid'])],
                                    capture_output=True, text=True, timeout=45)
            hi = time.monotonic()
            path = directory / f'{label}-vmmap-summary.txt'
            path.write_text(result.stdout)
            (directory / f'{label}-vmmap-stderr.txt').write_text(result.stderr)
            report['vmmap'].append({'label': label, 'start_monotonic': lo, 'end_monotonic': hi,
                                    'seconds': hi-lo, 'path': str(path), 'sha256': sha(path),
                                    'exit_code': result.returncode, 'state_before': state,
                                    'state_after': c.state(), 'included_in_phase_metrics': False})
            check(result.returncode == 0 and 'Physical footprint:' in result.stdout,
                  'vmmap summary acquired without elevation')
            print('vmmap', label, f'{hi-lo:.2f}s', flush=True)
            write_json(directory / 'report.json', report)

        changed = True
        scene = operation('create_scene', lambda: c.call('create_scene', name='H13 memory probe'))['state']['project']['graph']['active_scene']
        phase('zero_video', 0, 8); boundary('baseline')
        ids = []
        for n in range(4):
            result = operation(f'create_video_{n+1}', lambda: c.call('create_overlay', scene_id=scene,
                name=f'Owned video {n+1}', definition={'kind': 'video', 'asset_id': asset['id'], 'opacity': 1., 'looping': True}))
            sid = result['result']['source_id']; ids.append(sid)
            layer = next(l for s in result['state']['project']['graph']['scenes'] if s['id'] == scene
                         for l in s['layers'] if l['source_id'] == sid)
            c.call('set_transform', scene_id=scene, layer_id=layer['id'], variant='horizontal',
                   transform={'x': (n % 2)*480, 'y': (n // 2)*270, 'width': 480, 'height': 270, 'visible': True, 'order': n})
        phase('four_visible', 4, 8); boundary('four-visible')
        before = c.state(); replacement = json.loads(json.dumps(before['project']))
        mapping = {sid: f'h13-memory-replacement-{n}' for n, sid in enumerate(ids)}
        for source in replacement['graph']['sources']:
            source['id'] = mapping.get(source['id'], source['id'])
        for item in replacement['graph']['scenes']:
            for layer in item['layers']:
                layer['source_id'] = mapping.get(layer['source_id'], layer['source_id'])
        write_project(project, replacement)
        operation('reconcile_four_replacement_video_ids', lambda: c.call('load_project'))
        after = c.state(); report['reconcile'] = {'before': before, 'after': after}
        check({s['instance_id'] for s in before['overlays']['runtime']['sources']}.isdisjoint(
              {s['instance_id'] for s in after['overlays']['runtime']['sources']}), 'H12 replacement identity gate')
        phase('four_reconciled', 4, 8); boundary('four-reconciled')
        operation('restore_original_project', lambda: (write_project(project, original['project']), c.call('load_project')))
        phase('released_settling', 0, 20); boundary('released-20s')
        check(c.state()['project'] == original['project'], 'original runtime project restored')
        check(sha(APP) == report['app_sha256'], 'bundle unchanged')
        report['ok'] = True; report['result'] = 'PROBE_COMPLETED_NOT_A_MEMORY_BUDGET_PASS'
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        errors = []
        # Independent reporting/close steps still run on failure. All runtime
        # and file mutations require the same owner, lock and quiescent state.
        cleanup_safe = False
        if sampler:
            try:
                sampler.close(); report['process_samples'] = sampler.rows
                report['cpu_nanoseconds_per_mach_tick'] = sampler.ns_per_tick
            except BaseException as error:
                errors.append(f'sampler: {error}')
        if c and original:
            try:
                check(lock.read_text() == lock_owner, 'same lock during cleanup')
                state = c.wait(lambda s: s['overlays']['import'] is None or
                               s['overlays']['import'].get('phase') in ('completed', 'failed'))
                check(lock.read_text() == lock_owner, 'same lock after import wait')
                check(state['pid'] == original['pid'], 'same owner during cleanup')
                owner(state); idle(state); cleanup_safe = True
                if changed:
                    write_project(project, original['project']); c.call('load_project')
                if owned_asset:
                    c.call('remove_asset', asset_id=asset['id'])
                report['final'] = c.state()
            except BaseException as error:
                errors.append(f'runtime cleanup: {error}')
        if disk is not None and cleanup_safe:
            try:
                if disk[0] is None:
                    project.unlink(missing_ok=True)
                else:
                    temporary = project.with_suffix('.memory-restore.tmp')
                    temporary.write_bytes(disk[0]); temporary.chmod(disk[1]); temporary.replace(project)
                report['project_disk_restored'] = (project.read_bytes() == disk[0] if disk[0] is not None else not project.exists())
                check(report['project_disk_restored'], 'exact project bytes restored')
            except BaseException as error:
                errors.append(f'project cleanup: {error}')
        if owned_inbox and cleanup_safe:
            try:
                inbox.unlink(missing_ok=True)
            except BaseException as error:
                errors.append(f'inbox cleanup: {error}')
        if not cleanup_safe and (disk is not None or owned_inbox or changed):
            report['cleanup_pending'] = {
                'reason': 'Same owner, canonical lock, idle outputs and terminal import were not confirmed; files preserved.',
                'project_path': str(project), 'inbox_path': str(inbox) if owned_inbox else None,
                'runtime_project_needs_restore': changed, 'original_disk': report.get('project_disk_before')}
        if store_before:
            try:
                report['stores_after'] = {str(p): file_state(p) for p in stores}
                check(report['stores_after'] == store_before, 'mixer/profile stores unchanged')
            except BaseException as error:
                errors.append(f'stores: {error}')
        if c:
            try:
                c.close()
            except BaseException as error:
                errors.append(f'client cleanup: {error}')
        if errors:
            report['cleanup_errors'] = errors; report['ok'] = False; report['result'] = 'FAIL'
        write_json(directory / 'report.json', report)
    print(json.dumps({'ok': report['ok'], 'result': report['result'], 'report': str(directory / 'report.json')}), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
