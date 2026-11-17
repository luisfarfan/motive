#!/usr/bin/env python3
"""Explicit self-process memory diagnostics and controlled source lifecycle/soak.

Requires an already-open owner and the caller's canonical physical-test lock.
Never launches/signs/quits Motive, opens devices, requests permissions, dumps
memory or streams externally. All mutations use the shared core through MCP.
Run --plan first. This measures retention and budgets, never proves a leak.
"""
import argparse
import hashlib
import json
import math
import pathlib
import shutil
import socket
import statistics
import subprocess
import time
import traceback

import verify_h13_outputs as support
from verify_h13_outputs import Client, Receiver, check, profile, sha, slots, write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]


def distribution(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    return {'count': len(values), 'min': min(values), 'median': statistics.median(values),
            'p95': values[math.ceil(len(values)*.95)-1], 'max': max(values)} if values else None


def summarize(rows):
    def field(*parts):
        values = []
        for row in rows:
            value = row
            for part in parts:
                value = value.get(part) if isinstance(value, dict) else None
            values.append(value)
        return distribution(values)
    counters = {}
    if len(rows) > 1:
        for name in ['rendered_frames', 'lagged_frames', 'video_skipped_frames',
                     'preview_busy_drops', 'preview_copies']:
            first, last = rows[0]['stats'].get(name), rows[-1]['stats'].get(name)
            counters[name] = {'first': first, 'last': last,
                              'delta': last-first if first is not None and last is not None and last >= first else None,
                              'reset_observed': first is not None and last is not None and last < first}
    outputs = {}
    if len(rows) > 1:
        for target in ('recording', 'streaming'):
            first, last = rows[0]['outputs'][target], rows[-1]['outputs'][target]
            stable = first['attempt_id'] is not None and first['attempt_id'] == last['attempt_id']
            outputs[target] = {'attempt_id': last['attempt_id'], 'stable_attempt': stable, 'deltas': {}}
            for key in ('output_frames', 'output_dropped_frames', 'encoded_frames', 'output_bytes'):
                a, b = first['stats'].get(key), last['stats'].get(key)
                outputs[target]['deltas'][key] = b-a if stable and a is not None and b is not None and b >= a else None
    return {'samples': len(rows), 'cpu_percent_one_core': field('cpu_percent'),
            'rss_bytes': field('memory', 'vm', 'resident_bytes'),
            'physical_footprint_bytes': field('memory', 'vm', 'physical_footprint_bytes'),
            'compressed_bytes': field('memory', 'vm', 'compressed_bytes'),
            'internal_bytes': field('memory', 'vm', 'internal_bytes'),
            'malloc_in_use_bytes': field('memory', 'malloc', 'in_use_bytes'),
            'malloc_allocated_bytes': field('memory', 'malloc', 'allocated_bytes'),
            'native_collection_us': field('memory', 'collection_us'),
            'memory_rpc_ms': field('memory_rpc_ms'), 'status_rpc_ms': field('status_rpc_ms'),
            'counters': counters, 'output_counters': outputs}


def remove_owned_videos(client, source_ids, owned_scene):
    """Remove only tracked sources and their layers in our one owned scene.

    The core deliberately refuses RemoveSource while any scene references it.
    A reference added outside this fixture is a coordination conflict, never
    authority to remove someone else's layer. Partial cleanup can be retried.
    """
    for identifier in list(source_ids):
        graph = client.state()['project']['graph']
        references = [(scene['id'], layer['id']) for scene in graph['scenes']
                      for layer in scene['layers'] if layer['source_id'] == identifier]
        check(all(scene == owned_scene for scene, _ in references),
              'owned source acquired a foreign layer; leave it for review', source_id=identifier)
        for scene, layer in references:
            client.call('remove_layer', scene_id=scene, layer_id=layer)
        if any(source['id'] == identifier for source in graph['sources']):
            client.call('remove_source', source_id=identifier)
        source_ids.remove(identifier)


def cancel_owned_outputs(client, attempts):
    """Spend only our recorded attempt IDs; deferred cancellation handles connect."""
    for target, attempt_id in reversed(list(attempts.items())):
        output = client.state()['outputs'][target]
        check(output['attempt_id'] == attempt_id, 'output attempt changed; do not stop it', target=target)
        if output['native_busy']:
            client.call('cancel_output_target', target=target)


def cpu_interval(previous, current):
    if not previous or not current['cpu']['available'] or not previous['cpu']['available']:
        return None
    elapsed = (current['monotonic_ns']-previous['monotonic_ns'])/1e9
    cpu = sum(current['cpu'][key]-previous['cpu'][key] for key in ('user_seconds', 'system_seconds'))
    return 100*cpu/elapsed if elapsed > 0 and cpu >= 0 else None


def canonical_lock():
    common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
    if not common.is_absolute():
        common = ROOT / common
    return common.resolve().parent / 'var/run/physical-test.lock/OWNER'


def plan(args):
    return {'version': 1, 'mode': args.mode, 'fps': args.fps, 'resolution': '1920x1080',
            'interval_seconds': args.interval, 'baseline_seconds': args.hold,
            'cycles': args.cycles if args.mode != 'observe' else 0,
            'per_cycle': (['four_visible', 'four_hidden'] +
                          (['four_hidden_paused'] if args.pause_hidden else []) +
                          ['removed_settle']) if args.mode != 'observe' else [],
            'soak_seconds': args.soak_seconds if args.mode == 'dual-soak' else 0,
            'scope': 'controlled pattern and four looping silent video decoders; tone for dual outputs',
            'warnings': ['Caller must hold canonical lock and provide the already-open app.',
                         'Generate fixture BEFORE performance sampling; --prepare-fixture does not contact Motive.',
                         'RSS, malloc and physical footprint measure different scopes; no leak verdict.',
                         'Capture callback/media clocks are not proof of pixel freshness or A/V sync.',
                         'No automatic purge, restart, recovery acknowledgement or forced owner quit.']}


def generate_fixture(path):
    check(not path.exists(), 'new fixture destination')
    path.parent.mkdir(parents=True, exist_ok=True)
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
               'testsrc2=size=1920x1080:rate=30', '-t', '6', '-an', '-c:v',
               'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', str(path)]
    subprocess.run(command, check=True, timeout=90)
    write_json(path.with_suffix('.fixture.json'), {'source': 'generated testsrc2; no captured content',
               'command': command, 'file': str(path.resolve()), 'sha256': sha(path)})
    print(json.dumps({'file': str(path.resolve()), 'sha256': sha(path)}))


def execute(args):
    support.APP = args.app.resolve()
    directory = args.output.resolve()
    check(not directory.exists(), 'new evidence directory')
    directory.mkdir(parents=True)
    report = {'version': 1, 'status': 'FAIL', 'scope': 'measurement_not_leak_verdict',
              'plan': plan(args), 'phases': [], 'media': [], 'cleanup_errors': [],
              'app_sha256': sha(support.APP), 'instrument_sha256': sha(__file__),
              'budgets': {'native_collection_p95_us': args.native_budget_us,
                          'rpc_p95_ms': args.rpc_budget_ms,
                          'physical_footprint_review_bytes': args.footprint_review_mib*1024*1024,
                          'budget_semantics': 'review thresholds, not claims of a leak or universal product acceptance'},
              'gpu_utilization': 'NOT_EVALUATED', 'decoded_freshness': 'NOT_EVALUATED',
              'audio_video_sync': 'NOT_EVALUATED'}
    client = initial = receiver = scene = tone = asset = inbox = None
    owned_asset = changed = owner_validated = stream_configured = False
    source_ids, profiles, started = [], [], {}
    lock = canonical_lock()
    owner_text = lock.read_text()
    check(json.loads(owner_text).get('worktree') == str(ROOT), 'canonical lock belongs to this checkout')
    report['lock'] = {'path': str(lock), 'owner_sha256': hashlib.sha256(owner_text.encode()).hexdigest()}
    previous_memory = None
    previous_phase = None
    samples = (directory / 'samples.jsonl').open('w')

    def save():
        write_json(directory / 'report.json', report)

    def same_lock():
        check(lock.read_text() == owner_text, 'canonical lock unchanged')

    def wait(predicate, seconds=60):
        deadline = time.monotonic()+seconds
        while True:
            same_lock()
            state = client.state()
            check(state['pid'] == initial['pid'], 'same owner')
            if predicate(state):
                return state
            check(time.monotonic() < deadline, 'bounded owner wait')
            time.sleep(.2)

    def sample(label):
        nonlocal previous_memory, previous_phase
        same_lock()
        start = time.monotonic()
        memory = client.call('memory_diagnostics')['memory']
        middle = time.monotonic()
        state = client.state()
        end = time.monotonic()
        check(state['pid'] == initial['pid'] == memory['pid'], 'same process for VM and production')
        check(memory['version'] == 1 and memory['scope'] == 'current_process_only', 'native memory contract')
        interval_cpu = cpu_interval(previous_memory, memory)
        cpu_percent = interval_cpu if previous_phase == label else None
        between_phase_cpu = interval_cpu if previous_phase != label else None
        previous_memory = memory
        previous_phase = label
        row = {'phase': label, 'monotonic': end, 'memory': memory, 'cpu_percent': cpu_percent,
               'between_phase_cpu_percent': between_phase_cpu,
               'memory_rpc_ms': (middle-start)*1000, 'status_rpc_ms': (end-middle)*1000,
               'stats': state['stats'], 'outputs': state['outputs'], 'sources': state['sources'],
               'overlays_runtime': state['overlays']['runtime'], 'transition': state['transition'],
               'issues': state['issues'], 'video': state['video']}
        samples.write(json.dumps(row, separators=(',', ':'))+'\n'); samples.flush()
        check(memory['status'] == 'PASS', 'VM footprint and CPU coverage available; failed sample retained')
        return row

    def phase(label, duration, video_count=None, outputs_active=False):
        start = time.monotonic()
        rows = []
        while True:
            row = sample(label); rows.append(row)
            if video_count is not None:
                videos = [v for v in row['overlays_runtime']['sources'] if v['kind'] == 'video']
                check(len(videos) == video_count, 'expected video child count', sample_label=label)
                check(all(v['audio_mixers'] == 0 and v['child_instances_created'] == 1 for v in videos), 'one silent child per video')
            if outputs_active:
                check(all(row['outputs'][t]['phase'] == 'active' for t in ('recording', 'streaming')), 'dual outputs remain active')
            if time.monotonic()-start >= duration:
                break
            time.sleep(min(args.interval, max(0, duration-(time.monotonic()-start))))
        summary = summarize(rows)
        report['phases'].append({'name': label, 'seconds': time.monotonic()-start,
                                 'summary': summary, 'first': rows[0], 'last': rows[-1]})
        save(); print(json.dumps({'phase': label, 'summary': summary}), flush=True)

    def add_videos():
        for index in range(4):
            response = client.call('create_overlay', scene_id=scene, name=f'H14 memory video {index}',
                definition={'kind': 'video', 'asset_id': asset['id'], 'opacity': 1., 'looping': True})
            identifier = response['result']['source_id']; source_ids.append(identifier)
            layer = support.layer(response['state'], scene, identifier)
            client.call('set_transform', scene_id=scene, layer_id=layer['id'], variant='horizontal',
                        transform={'x': (index%2)*480, 'y': (index//2)*270, 'width': 480,
                                   'height': 270, 'visible': True, 'order': index+1})

    def remove_videos():
        remove_owned_videos(client, source_ids, scene)

    try:
        client = Client(directory)
        initial = client.state(); report['initial'] = initial
        actual = pathlib.Path(subprocess.check_output(['ps', '-p', str(initial['pid']), '-o', 'comm='], text=True).strip()).resolve()
        check(actual == support.APP, 'selected already-open owner executable')
        owner_validated = True
        check('memory_diagnostics' in {t['name'] for t in client.rpc('tools/list')['tools']}, 'explicit native memory query exists')
        check(not initial['output_lifecycle']['shutdown_pending'], 'owner not shutting down')
        if args.mode == 'observe':
            phase('observe_existing_owner', args.soak_seconds)
        else:
            check(all(not s['native_busy'] and not s['recovery_required'] for s in slots(initial).values()), 'idle healthy outputs required')
            check(not initial['audio_mixer']['store']['inputs'], 'empty controlled mixer required')
            check(all(s['spec']['kind'] in ('pattern', 'overlay') and s.get('overlay') is None for s in initial['project']['graph']['sources']), 'disposable controlled initial graph')
            check(initial['output_configuration']['credential_ref'] is None, 'credential-free test configuration')
            check(initial['destinations']['selected'] is None and not initial['destinations']['credential_busy'],
                  'no selected external destination or credential enrollment')
            check(not initial['issues'] and not initial['overlays']['runtime']['animations']['busy']
                  and initial['transition']['phase'] not in ('preparing', 'running'), 'initial production ready and quiescent')
            check(args.fixture and args.fixture_sha256 and sha(args.fixture) == args.fixture_sha256, 'explicit controlled fixture and expected SHA-256 required')
            check(args.fps in (30, 60), 'explicit verified canvas rate')
            changed = True
            client.call('set_variant', variant='horizontal')
            client.call('configure_video', video={'version': 1, 'resolution': 'full_hd1080', 'fps': args.fps, 'coordinate_space': 'design960'})
            imports = args.store_root / 'imports'
            check(imports.is_dir() and not imports.is_symlink() and imports.stat().st_mode & 0o077 == 0, 'private existing managed inbox')
            inbox = imports / ('h14-memory-'+str(time.time_ns())+'.mp4')
            shutil.copyfile(args.fixture, inbox); inbox.chmod(0o600)
            existing = {a['id'] for a in client.call('list_assets')['result']['assets']}
            response = client.call('import_asset', file_name=inbox.name)
            operation = response['result']['import']['operation_id']
            state = wait(lambda s: s['overlays']['import'].get('operation_id') == operation and s['overlays']['import']['phase'] in ('completed', 'failed'), 90)
            check(state['overlays']['import']['phase'] == 'completed', 'controlled import completed')
            asset = state['overlays']['import']['asset']; owned_asset = asset['id'] not in existing
            report['fixture'] = {'file': str(args.fixture.resolve()), 'sha256': args.fixture_sha256, 'asset': asset}
            scene = client.call('create_scene', name='H14 memory controlled')['state']['project']['graph']['active_scene']
            pattern = next((s['id'] for s in initial['project']['graph']['sources'] if s['spec']['kind'] == 'pattern'), None)
            check(pattern is not None, 'existing controlled pattern required')
            client.call('add_layer', scene_id=scene, source_id=pattern)
            phase('baseline_zero_video', args.hold, 0)
            for cycle in range(args.cycles):
                add_videos(); phase(f'cycle_{cycle+1}_visible', args.hold, 4)
                for identifier in source_ids:
                    state = client.state(); layer = support.layer(state, scene, identifier)
                    transform = dict(layer['layouts']['horizontal']); transform['visible'] = False
                    client.call('set_transform', scene_id=scene, layer_id=layer['id'], variant='horizontal', transform=transform)
                phase(f'cycle_{cycle+1}_hidden', args.hold, 4)
                if args.pause_hidden:
                    for identifier in source_ids:
                        client.call('overlay_event', source_id=identifier, event='pause')
                    wait(lambda s: all(next(item for item in s['overlays']['runtime']['sources']
                                           if item['id'] == identifier)['media_state'] == 'paused'
                                       for identifier in source_ids))
                    phase(f'cycle_{cycle+1}_hidden_paused', args.hold, 4)
                remove_videos(); phase(f'cycle_{cycle+1}_released', args.settle, 0)
            if args.mode == 'dual-soak':
                add_videos()
                response = client.call('add_audio_input', name='H14 memory controlled tone', source={'kind': 'tone'})
                tone = next(i['id'] for i in response['state']['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
                client.call('set_audio_gain', input_id=tone, gain_db=-12)
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
                client.call('configure_stream', endpoint={'transport': 'rtmp', 'port': port})
                stream_configured = True
                receiver = Receiver(directory, 'received-loopback', port)
                for target in ('recording', 'streaming'):
                    identifier = 'h14-memory-'+target+'-'+str(time.time_ns())
                    client.call('upsert_output_profile', profile=profile(identifier, 'videotoolbox', 4000)); profiles.append(identifier)
                    client.call('select_output_profile', target=target, profile_id=identifier)
                for target in ('recording', 'streaming'):
                    state = client.call('start_output', target=target)['state']
                    started[target] = state['outputs'][target]['attempt_id']
                    report['media'].append({'target': target, 'path': str(receiver.path) if target == 'streaming' else state['outputs'][target]['path'], 'attempt_id': state['outputs'][target]['attempt_id']})
                    wait(lambda s: s['outputs'][target]['phase'] == 'active')
                    wait(lambda s: s['outputs'][target]['stats']['output_frames'] >= 3)
                    write_json(directory / (target+'-start-packets.json'),
                               client.call('output_diagnostics', target=target))
                phase('dual_soak', args.soak_seconds, 4, True)
        report['status'] = 'PARTIAL'
        report['measurement_completed'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        if client and initial and owner_validated:
            try:
                same_lock()
                check(client.state()['pid'] == initial['pid'], 'same owner during cleanup')
                cancel_owned_outputs(client, started)
                if started:
                    wait(lambda s: all(not slot['native_busy'] for slot in s['outputs'].values()))
                    for target in started:
                        write_json(directory / (target+'-final-packets.json'),
                                   client.call('output_diagnostics', target=target))
                if changed:
                    check(all(not s['native_busy'] for s in client.state()['outputs'].values()), 'native outputs quiescent before source cleanup')
                    remove_videos()
                    if scene:
                        client.call('select_scene', scene_id=initial['project']['graph']['active_scene'])
                        wait(lambda s: s['transition']['phase'] not in ('preparing', 'running')
                             and s['project']['graph']['active_scene'] == initial['project']['graph']['active_scene'])
                        client.call('remove_scene', scene_id=scene)
                    if tone:
                        client.call('remove_audio_input', input_id=tone)
                    for target in ('recording', 'streaming'):
                        if profiles:
                            client.call('select_output_profile', target=target, profile_id=initial['output_configuration'][target+'_profile'])
                    for identifier in profiles:
                        client.call('remove_output_profile', id=identifier)
                    if owned_asset:
                        client.call('remove_asset', asset_id=asset['id'])
                    if inbox:
                        inbox.unlink(missing_ok=True)
                    client.call('configure_video', video=initial['project'].get('video') or support.DEFAULT_VIDEO)
                    client.call('set_variant', variant=initial['project']['variant'])
                    endpoint = initial['output_configuration']['endpoint']
                    if stream_configured and endpoint:
                        client.call('configure_stream', endpoint=endpoint)
                    elif stream_configured:
                        report['cleanup_note'] = 'No unset endpoint API; owned credential-free loopback endpoint remains selected.'
                report['final'] = client.state()
            except BaseException:
                report['cleanup_errors'].append(traceback.format_exc())
                report['status'] = 'FAIL'
                report['cleanup_pending'] = {'sources': source_ids, 'scene': scene, 'asset': asset, 'inbox': str(inbox) if inbox else None, 'profiles': profiles}
        if client:
            try:
                client.close()
            except BaseException:
                report['cleanup_errors'].append(traceback.format_exc())
                report['status'] = 'FAIL'
        if receiver:
            try:
                receiver.wait()
            except subprocess.TimeoutExpired:
                try:
                    receiver.terminate()
                except BaseException:
                    report['cleanup_errors'].append(traceback.format_exc())
                report['cleanup_errors'].append('Owned receiver needed termination after owner stop; media completeness not inferred.')
                report['status'] = 'FAIL'
        samples.close()
        for media in report['media']:
            path = pathlib.Path(media['path'])
            if path.is_file():
                media.update(bytes=path.stat().st_size, sha256=sha(path), decode_status='NOT_EVALUATED')
        report['samples_sha256'] = sha(directory / 'samples.jsonl')
        report['budget_observations'] = {
            'native_collection_p95_exceeded_phases': [p['name'] for p in report['phases'] if p['summary']['native_collection_us'] and p['summary']['native_collection_us']['p95'] > args.native_budget_us],
            'memory_rpc_p95_exceeded_phases': [p['name'] for p in report['phases'] if p['summary']['memory_rpc_ms'] and p['summary']['memory_rpc_ms']['p95'] > args.rpc_budget_ms],
            'footprint_review_exceeded_phases': [p['name'] for p in report['phases'] if p['summary']['physical_footprint_bytes'] and p['summary']['physical_footprint_bytes']['max'] > args.footprint_review_mib*1024*1024],
            'leak_classification': 'INCONCLUSIVE_NO_OWNERSHIP_OR_ALLOCATION_STACK_EVIDENCE'}
        save()
    print(json.dumps({'status': report['status'], 'report': str(directory / 'report.json')}))
    return 0 if report.get('measurement_completed') and not report['cleanup_errors'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--prepare-fixture', type=pathlib.Path)
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--mode', choices=['observe', 'lifecycle', 'dual-soak'], default='lifecycle')
    parser.add_argument('--app', type=pathlib.Path, default=ROOT/'target/Motive.app/Contents/MacOS/motive')
    parser.add_argument('--store-root', type=pathlib.Path, default=ROOT/'var')
    parser.add_argument('--output', type=pathlib.Path)
    parser.add_argument('--fixture', type=pathlib.Path)
    parser.add_argument('--fixture-sha256')
    parser.add_argument('--fps', type=int, choices=[30, 60], default=30)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--hold', type=float, default=20)
    parser.add_argument('--settle', type=float, default=60)
    parser.add_argument('--cycles', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--pause-hidden', action='store_true',
                        help='Measure explicit pause of the four owned hidden videos before removing them.')
    parser.add_argument('--soak-seconds', type=float, default=1800)
    parser.add_argument('--native-budget-us', type=float, default=2000)
    parser.add_argument('--rpc-budget-ms', type=float, default=20)
    parser.add_argument('--footprint-review-mib', type=int, default=1536)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(args), indent=2)); return 0
    if args.prepare_fixture:
        generate_fixture(args.prepare_fixture); return 0
    if not args.lock_held or not args.output:
        parser.error('--lock-held and a new --output are required')
    for name, lo, hi in [('interval', 1, 30), ('hold', 5, 120), ('settle', 5, 300), ('soak_seconds', 5, 3600)]:
        value = getattr(args, name)
        if not math.isfinite(value) or not lo <= value <= hi:
            parser.error(f'{name} must be finite and between {lo} and {hi}')
    if not all(math.isfinite(v) and v > 0 for v in (args.native_budget_us, args.rpc_budget_ms, args.footprint_review_mib)):
        parser.error('diagnostic review budgets must be positive and finite')
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
