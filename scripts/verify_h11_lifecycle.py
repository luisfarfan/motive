#!/usr/bin/env python3
"""Real signed-app H11 restore/resource recovery gate; requires exclusive lock.

Uses only fixtures created here. Existing project/mixer/profile files are backed
up and restored byte-for-byte. No physical devices or external network access.
"""
import hashlib
import json
import pathlib
import subprocess
import time

from h7_support import Client, EVIDENCE, EXE, ROOT, media, assert_project_format
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
from verify_h11_visuals import fixture_png, import_asset, sources


def ctl(op, **args):
    p = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **args})],
                       capture_output=True, text=True, timeout=12)
    return json.loads(p.stdout)


def stop_app(c):
    state = c.state()
    assert state['output'] == 'idle'
    pid = state['pid']
    c.call('shutdown')
    c.close()
    end = time.monotonic()+15
    while subprocess.run(['kill', '-0', str(pid)], capture_output=True).returncode == 0:
        assert time.monotonic() < end, 'Owned app did not exit'
        time.sleep(.1)


def launch(run):
    start = time.monotonic()
    subprocess.run(['open', '-n', '--stdout', str(run/'restore.runtime.log'),
                    '--stderr', str(run/'restore.stderr.log'), str(VERIFY.app_bundle)], check=True)
    while True:
        state = ctl('status')
        if state['ok']:
            return Client(), time.monotonic()-start
        assert time.monotonic()-start < 20, state
        time.sleep(.15)


def widget(kind):
    return {'kind': 'widget', 'widget': {'kind': kind, 'title': 'Lifecycle Áé',
            'subtitle': 'Owned fixture', 'width': 480, 'height': 140,
            'background': 0x112233, 'accent': 0x33e8b5, 'color': 0xffffff,
            'opacity': 1., 'duration_ms': 0 if kind == 'lower_third' else 3000}}


def main():
    run = EVIDENCE/('h11-lifecycle-'+str(time.time_ns()))
    run.mkdir(parents=True)
    report = {'ok': False, 'run': str(run)}
    c = None
    original = None
    owned_asset = None
    asset_path = None
    asset_backup = None
    recording = False
    saved = {}
    try:
        c = Client()
        original = c.state()
        assert original['output'] == 'idle' and not original['audio_mixer']['store']['inputs']
        assert all(s.get('overlay') is None and s['spec']['kind'] in ('pattern', 'overlay')
                   for s in original['project']['graph']['sources'])
        for name in ('project.json', 'audio-mixer.json', 'output-profiles.json'):
            path = VERIFY.data_root/name
            saved[name] = path.read_bytes() if path.exists() else None
        project_path = VERIFY.data_root / 'project.json'
        fixture = run/('restore-'+run.name+'.png')
        fixture_png(fixture)
        before_assets = {a['id'] for a in c.call('list_assets')['result']['assets']}
        asset = import_asset(c, fixture)['asset']
        if asset['id'] not in before_assets:
            owned_asset = asset['id']
        asset_path = VERIFY.data_root/'assets'/(asset['id']+'.png')
        asset_backup = asset_path.read_bytes()
        scene = c.call('create_scene', name='H11 lifecycle')['state']['project']['graph']['active_scene']
        image_id = c.call('create_overlay', scene_id=scene, name='Restored managed image',
                          definition={'kind': 'image', 'asset_id': asset['id'], 'opacity': 1.})['result']['source_id']
        widget_id = c.call('create_overlay', scene_id=scene, name='Subtype restore',
                           definition=widget('lower_third'))['result']['source_id']
        other = c.call('create_scene', name='Reused managed image')['state']['project']['graph']['active_scene']
        c.call('add_layer', scene_id=other, source_id=image_id)
        c.call('select_scene', scene_id=scene)
        c.call('add_audio_input', name='Persistence tone', source={'kind': 'tone'})
        state = c.wait(lambda s: not s['issues'])
        tone = state['audio_mixer']['store']['inputs'][0]['id']
        c.call('set_audio_gain', input_id=tone, gain_db=0)
        c.call('set_audio_mute', input_id=tone, muted=False)
        mixer = c.call('save_audio_mixer')['state']['audio_mixer']['store']
        c.call('save_output_profiles')
        profiles = c.call('output_profiles')['store']
        c.call('save_project')
        desired = json.loads(project_path.read_text())
        assert_project_format(desired, 4, original['project'].get('video'))
        report['desired'] = desired
        initial_sources = sources(c.state())
        assert len([s for s in initial_sources.values() if s['id'] == image_id]) == 1
        # Same stable ID with a different widget kind must recreate only that
        # resource, never commit a definition the native wrapper cannot execute.
        changed = json.loads(json.dumps(desired))
        next(s for s in changed['graph']['sources'] if s['id'] == widget_id)['overlay'] = widget('countdown')
        project_path.write_text(json.dumps(changed))
        c.call('load_project')
        replaced = c.wait(lambda s: sources(s)[widget_id]['widget_kind'] == 'countdown' and not s['issues'])
        assert sources(replaced)[widget_id]['instance_id'] != initial_sources[widget_id]['instance_id']
        assert sources(replaced)[image_id]['instance_id'] == initial_sources[image_id]['instance_id']
        assert replaced['audio_mixer']['store'] == mixer
        report['subtype_restored'] = replaced
        c.call('save_project')
        desired = json.loads(project_path.read_text())
        report['operations_before_restart'] = c.ops
        old_pid = c.state()['pid']
        stop_app(c)
        c = None
        c, elapsed = launch(run)
        assert c.state()['pid'] != old_pid
        c.call('load_audio_mixer')
        c.call('load_output_profiles')
        c.call('load_project')
        restored = c.wait(lambda s: not s['issues'] and not s['recovery_required'])
        assert restored['project'] == desired
        assert restored['audio_mixer']['store'] == mixer
        assert c.call('output_profiles')['store'] == profiles
        assert sources(restored)[widget_id]['phase'] == 'idle', sources(restored)[widget_id]
        report.update({'startup_seconds': elapsed, 'restored': restored})
        c.call('start_recording')
        recording = True
        first = c.wait(lambda s: s['output'] == 'recording')
        time.sleep(3)
        # Move the exact owned managed resource aside. No arbitrary path can be
        # selected through the public control protocol.
        missing = run/'temporarily-missing.png'
        asset_path.rename(missing)
        failed = c.wait(lambda s: s['output'] == 'idle' and s['recovery_required'], timeout=15)
        recording = False
        assert any('ASSET_MISSING' in issue for issue in failed['issues']), failed
        report['missing_resource_state'] = failed
        report['finalized_after_missing'] = media(first['output_path'], minimum=2)
        denied = c.call('start_recording', expect=False)
        report['blocked_restart'] = denied
        repaired = import_asset(c, fixture)['asset']
        assert repaired['id'] == asset['id']
        stale_instance = sources(failed)[image_id]['instance_id']
        c.call('reconnect_source', source_id=image_id)
        recovered = c.wait(lambda s: not s['issues'] and not s['recovery_required'])
        assert sources(recovered)[image_id]['instance_id'] != stale_instance
        assert sources(recovered)[widget_id]['instance_id'] == sources(restored)[widget_id]['instance_id']
        assert recovered['audio_mixer']['store'] == mixer
        report['recovered'] = recovered
        c.call('start_recording')
        recording = True
        second = c.wait(lambda s: s['output'] == 'recording')
        time.sleep(3)
        c.stop()
        recording = False
        report['recovered_media'] = media(second['output_path'], minimum=2)
        c.call('save_project')
        # Legacy project restores without introducing v4 fields; independent
        # mixer and output profiles retain their versioned contracts.
        legacy_project = json.loads(json.dumps(original['project']))
        legacy_project['version'] = 3
        legacy_project.pop('video', None)
        project_path.write_text(json.dumps(legacy_project))
        legacy = c.call('load_project')['state']
        assert legacy['project'] == legacy_project and legacy['project']['version'] == 3
        legacy_size = (960, 540) if legacy_project['variant'] == 'horizontal' else (540, 960)
        assert (legacy['width'], legacy['height'], legacy['fps']) == (*legacy_size, 30)
        assert legacy['audio_mixer']['store'] == mixer and c.call('output_profiles')['store'] == profiles
        report['legacy_restored'] = legacy
        # Large v4 documents must remain controllable through BOTH real clients.
        # Request framing stays64KiB; a duplicated status graph can exceed it.
        large_scene = c.call('create_scene', name='Bounded large document')['state']['project']['graph']['active_scene']
        large_ids = []
        for i in range(14):
            definition = {'kind': 'text', 'text': 'é'*2048, 'font': 'Helvetica',
                          'size': 8, 'color': 0xffffff, 'opacity': 1., 'align': 'left',
                          'width': 1920, 'height': 100, 'background': None,
                          'background_opacity': 0., 'outline': False}
            large_ids.append(c.call('create_overlay', scene_id=large_scene,
                                    name='Bounded text '+str(i), definition=definition)['result']['source_id'])
        c.call('save_project')
        assert project_path.stat().st_size > 65536
        large_cli = ctl('status')
        assert large_cli['ok'] and len(json.dumps(large_cli, ensure_ascii=False).encode()) > 65536
        large_mcp = c.state()
        assert large_mcp['project'] == large_cli['state']['project']
        identity = {identifier: sources(large_mcp)[identifier]['instance_id'] for identifier in large_ids}
        large_restored = c.call('load_project')['state']
        assert large_restored['project'] == large_mcp['project']
        assert {identifier: sources(large_restored)[identifier]['instance_id'] for identifier in large_ids} == identity
        report['large_document'] = {'file_bytes': project_path.stat().st_size,
                                  'cli_response_bytes': len(json.dumps(large_cli, ensure_ascii=False).encode()),
                                  'sources': len(large_mcp['project']['graph']['sources']),
                                  'identities_preserved': identity, 'cli_mcp_agree': True}
        report['ok'] = True
    except BaseException as failure:
        report['error'] = repr(failure)
        raise
    finally:
        errors = []
        def cleanup(action):
            try:
                action()
            except Exception as error:
                errors.append(repr(error))
        if asset_path and asset_backup and not asset_path.exists():
            cleanup(lambda: asset_path.write_bytes(asset_backup))
        if c:
            if recording:
                cleanup(c.stop)
            if original:
                cleanup(lambda: (VERIFY.data_root / 'project.json').write_text(json.dumps(original['project'])))
                cleanup(lambda: c.call('load_project'))
                for entry in c.state()['audio_mixer']['store']['inputs']:
                    cleanup(lambda: c.call('remove_audio_input', input_id=entry['id']))
            if owned_asset:
                cleanup(lambda: c.call('remove_asset', asset_id=owned_asset))
            report['operations_after_restart'] = c.ops
            cleanup(c.close)
        for name, contents in saved.items():
            path = VERIFY.data_root/name
            cleanup(lambda: path.write_bytes(contents) if contents is not None else path.unlink(missing_ok=True))
        if errors:
            report['cleanup_errors'] = errors
            report['ok'] = False
        report['app_sha256'] = hashlib.sha256((VERIFY.app_executable).read_bytes()).hexdigest()
        (run/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'ok': report['ok'], 'report': str(run/'report.json')}), flush=True)
    assert report['ok'], report.get('cleanup_errors')


if __name__ == '__main__':
    main()
