#!/usr/bin/env python3
"""Build or measure isolated release GPUI backends on the controlled default scene.

run requires the canonical physical lock and starts only a fresh development
owner. No devices, captured windows, user stores, outputs, or synthetic UI events.
The result is a measurement, never automatic Fast adoption or visual acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time

from verify_h14_collection import Client, ROOT, default_owner, digest, lock, process_identity
from verify_h14_memory import cpu_interval, distribution, summarize

NATIVE_MODULES = {
    'mac-capture':'target/mac-capture-h14/mac-capture.so',
    'obs-outputs':'target/obs-outputs-h8/obs-outputs.so',
    'libobs':'.deps/OBS.app/Contents/Frameworks/libobs.framework/libobs',
}


def save(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def inputs():
    files = [ROOT/'Cargo.toml', ROOT/'Cargo.lock', ROOT/'build.rs',
             ROOT/'show-control/Cargo.toml']
    for folder in ('src', 'native', 'show-control/src'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    files.extend([ROOT/'scripts/build_obs_capture.py', ROOT/'scripts/build_obs_outputs.py'])
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}


def prepare(args):
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    target = ROOT/'target'/('h17-gpui-'+args.variant)
    features = 'ui-profiler' if args.variant == 'a' else 'ui-profiler,gpui-fast'
    command = ['cargo', 'build', '--locked', '--release', '--features', features,
               '--target-dir', str(target)]
    before = inputs()
    with (out/'build.log').open('x') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=log)
    after = inputs()
    manifest = {'version': 1, 'status': 'FAIL', 'variant': args.variant,
                'backend': 'gpui-pre' if args.variant == 'a' else 'gpui-fast',
                'command': command, 'exit_code': result.returncode,
                'source_before': before, 'source_after': after,
                'rustc': subprocess.check_output(['rustc', '-Vv'], text=True),
                'machine': subprocess.check_output(['uname', '-m'], text=True).strip(),
                'os': subprocess.check_output(['sw_vers'], text=True)}
    if result.returncode or before != after:
        manifest['status'] = 'FAIL' if result.returncode else 'BLOCKED'
        manifest['reason'] = 'build failure' if result.returncode else 'source changed during compilation'
        save(out/'build-binding.json', manifest)
        raise RuntimeError(manifest['reason'])
    app = out/('Motive-GPUI-'+args.variant.upper()+'.app')
    contents = app/'Contents'
    (contents/'MacOS').mkdir(parents=True)
    shutil.copy2(target/'release/motive', contents/'MacOS/motive')
    shutil.copy2(ROOT/'.deps/OBS.app/Contents/MacOS/obs-ffmpeg-mux', contents/'MacOS/obs-ffmpeg-mux')
    (contents/'Frameworks').symlink_to(ROOT/'.deps/OBS.app/Contents/Frameworks', target_is_directory=True)
    with (contents/'Info.plist').open('xb') as output:
        plistlib.dump({'CFBundleIdentifier':'local.motive.studio', 'CFBundleName':'Motive',
                      'CFBundleExecutable':'motive','CFBundlePackageType':'APPL',
                      'CFBundleShortVersionString':'0.1.0','CFBundleVersion':'H17-GPUI-'+args.variant,
                      'LSMinimumSystemVersion':'15.0','NSHighResolutionCapable':True,
                      'LSAppNapIsDisabled':True}, output)
    subprocess.run(['codesign','--force','--sign','-',str(app)], check=True, capture_output=True)
    manifest.update(status='PASS', app=str(app), binary_sha256=digest(contents/'MacOS/motive'),
                    native_modules={name:digest(ROOT/path) for name,path in NATIVE_MODULES.items()})
    save(out/'build-binding.json',manifest)
    print(json.dumps({'status':manifest['status'],'app':str(app),'binary_sha256':manifest['binary_sha256']}))


def run(args):
    ownership = lock()
    assert subprocess.run(['pgrep','-x','motive'],capture_output=True).returncode == 1, 'Existing Motive owner'
    assert not (ROOT/'var/run/motive.sock').exists(), 'Existing control socket'
    app = args.app.resolve(strict=True)
    assert not (app/'Contents/Resources/MotivePortable.json').exists(), 'Only isolated development layout'
    manifest = json.loads((app.parent/'build-binding.json').read_text())
    binary = app/'Contents/MacOS/motive'
    assert manifest['status'] == 'PASS' and manifest['binary_sha256'] == digest(binary), 'Build binding mismatch'
    assert manifest['native_modules'] == {name:digest(ROOT/path) for name,path in NATIVE_MODULES.items()}, 'Native modules changed after build'
    out = args.output.absolute()
    out.mkdir(parents=True,exist_ok=False)
    save(out/'build-binding.json',manifest)
    env = {key:value for key,value in os.environ.items()
           if not key.startswith(('DYLD_', 'GPUI_', 'MOTIVE_UI_'))}
    env.update(MOTIVE_UI_PROFILE='1',MOTIVE_UI_SIZE='1024x780')
    rows, owner, client = [], None, None
    report = {'version':1,'status':'FAIL','scope':args.workload+'_preview_no_outputs',
              'backend':manifest['backend'],'binary_sha256':manifest['binary_sha256'],
              'seconds_requested':args.seconds,'warmup_seconds':5,'ui_size':'1024x780',
              'lock':ownership,'cleanup_errors':[]}
    log_path = out/'owner.log'
    with log_path.open('x') as log:
        try:
            owner = subprocess.Popen([str(binary)],cwd='/',env=env,stdout=log,stderr=log)
            for _ in range(100):
                assert owner.poll() is None, 'Owner exited during startup'
                try:
                    client = Client(app,owner.pid,out)
                    default_owner(client.state())
                    break
                except (OSError,ValueError):
                    time.sleep(.1)
            else:
                raise RuntimeError('Owner startup timeout')
            report['process'] = process_identity(owner.pid,binary)
            time.sleep(5)
            offset = log_path.stat().st_size
            started = time.monotonic()
            wall_offset = time.time()-started
            if args.workload == 'four-videos':
                assert args.fixture and args.fixture_sha256
                assert digest(args.fixture) == args.fixture_sha256, 'Controlled fixture identity'
                command = ['python3', str(ROOT/'scripts/verify_h14_memory.py'), '--lock-held',
                           '--app', str(binary), '--store-root', str(ROOT/'var'),
                           '--output', str(out/'lifecycle'), '--mode', 'lifecycle',
                           '--fixture', str(args.fixture), '--fixture-sha256', args.fixture_sha256,
                           '--fps', '60', '--cycles', '3', '--interval', '1', '--hold', '10', '--settle', '10']
                with (out/'lifecycle.log').open('x') as suite_log:
                    result = subprocess.run(command,cwd=ROOT,env=env,stdout=suite_log,stderr=suite_log,timeout=240)
                report['lifecycle_exit'] = result.returncode
                lifecycle = json.loads((out/'lifecycle/report.json').read_text())
                report['lifecycle'] = lifecycle
                assert result.returncode == 0 and lifecycle.get('measurement_completed'), 'Lifecycle failed; retain its report'
                assert not lifecycle['cleanup_errors'], 'Lifecycle cleanup incomplete'
            else:
                previous = client.call('memory_diagnostics')['memory']
                while time.monotonic()-started < args.seconds:
                    time.sleep(.5)
                    before = time.monotonic()
                    memory = client.call('memory_diagnostics')['memory']
                    middle = time.monotonic()
                    state = client.state()
                    after = time.monotonic()
                    default_owner(state)
                    assert not state['issues'], 'Controlled scene has a source issue'
                    assert memory['pid'] == owner.pid and memory['status'] == 'PASS'
                    rows.append({'monotonic':after,'memory':memory,'cpu_percent':cpu_interval(previous,memory),
                                 'memory_rpc_ms':(middle-before)*1000,'status_rpc_ms':(after-middle)*1000,
                                 'stats':state['stats'],'outputs':state['outputs']})
                    previous = memory
            report['seconds_observed'] = time.monotonic()-started
            report['wall_offset_drift_seconds'] = (time.time()-time.monotonic())-wall_offset
            with log_path.open('rb') as source:
                source.seek(offset)
                raw_lines = source.read().split(b'\n')[:-1]
            profile = [json.loads(line[len(b'MOTIVE_UI_PROFILE '):]) for line in raw_lines
                       if line.startswith(b'MOTIVE_UI_PROFILE ')]
            # The first row can straddle warmup. Retain it, exclude from summary.
            report['ui_profile'] = profile
            usable = profile[1:]
            assert usable and all(r['pid']==owner.pid and r['backend']==manifest['backend'] for r in usable)
            kinds = ('draw','dirty_to_present','animating_present_interval','input_to_frame','heartbeat')
            assert all(r[kind]['status'] != 'FAIL' for r in usable for kind in kinds), 'Profiler histogram discontinuity'
            assert all(r['draw']['status'] == 'PASS' and r['heartbeat']['status'] == 'PASS'
                       for r in usable), 'Profiler draw/heartbeat coverage incomplete or samples dropped'
            report['ui_summary'] = {kind:{metric:distribution(r[kind].get(metric) for r in usable)
                for metric in ('samples','p50_us','p95_us','max_us')}
                for kind in ('draw','dirty_to_present','input_to_frame','heartbeat')}
            report['summary'] = summarize(rows)
            if args.workload == 'four-videos':
                assert abs(report['wall_offset_drift_seconds']) < .1, 'Wall clock changed during phase correlation'
                report['ui_by_phase'] = {}
                for phase in lifecycle['phases']:
                    begin = phase['first']['monotonic']+wall_offset
                    end = phase['last']['monotonic']+wall_offset
                    selected = [r for r in usable if r['wall_unix_seconds']-r['interval_seconds'] >= begin
                                and r['wall_unix_seconds'] <= end]
                    assert selected, 'No complete GPUI interval inside lifecycle phase '+phase['name']
                    report['ui_by_phase'][phase['name']] = {
                        'intervals':len(selected), 'rows':selected,
                        'draw_p95_us_by_interval':distribution(r['draw'].get('p95_us') for r in selected),
                        'heartbeat_p95_us_by_interval':distribution(r['heartbeat'].get('p95_us') for r in selected)}
            report['status'] = 'PASS'
        except Exception as error:
            report['error'] = str(error)
        finally:
            if owner and owner.poll() is None and client:
                try:
                    client.call('request_shutdown')
                    owner.wait(timeout=25)
                except Exception as error:
                    report['cleanup_errors'].append(str(error))
            report['owner_exit'] = owner.poll() if owner else None
            if report['cleanup_errors'] or report['owner_exit'] != 0:
                report['status'] = 'FAIL'
            report['samples'] = rows
            save(out/'report.json',report)
    print(json.dumps({key:value for key,value in report.items() if key not in ('samples','ui_profile','lock','summary','ui_summary')}))
    return int(report['status'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--variant',choices=['a','b'],required=True)
    build.add_argument('--output',type=Path,required=True)
    measure = commands.add_parser('run')
    measure.add_argument('--app',type=Path,required=True)
    measure.add_argument('--output',type=Path,required=True)
    measure.add_argument('--seconds',type=float,default=30)
    measure.add_argument('--workload',choices=['pattern','four-videos'],default='pattern')
    measure.add_argument('--fixture',type=Path)
    measure.add_argument('--fixture-sha256')
    args = parser.parse_args()
    if args.command == 'prepare':
        return prepare(args)
    if args.workload == 'four-videos' and not (args.fixture and args.fixture_sha256):
        parser.error('four-videos requires an explicit generated fixture and its SHA-256')
    if not 10 <= args.seconds <= 120:
        parser.error('Bounded measurement requires 10–120 seconds')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
