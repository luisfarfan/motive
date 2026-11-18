#!/usr/bin/env python3
"""Supervised fixed Motive Goal fixture; no arbitrary content/URL/JS inputs.

Uses the smoke launcher's reviewed inventory/signature/file utilities but never
its red-patch or counter checker. Rendering and IPC observations stay separate.
"""
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid

from run_owned_fixture import (LAB, PIN, canonical_directory, collect_process_logs,
    invoke_supervisor, parser, preview_png, read_json, regular_bytes, require,
    save_json, sha, validate_options, verify_inventory, write_new)


def main(argv=None):
    args = parser().parse_args(argv)
    validate_options(args)
    require(args.generation is not None and args.generation <= 9007199254740991, 'EXPLICIT_SAFE_GENERATION')
    require(re.fullmatch(r'[0-9a-f]{64}', args.expected_sha256) is not None, 'EXPECTED_SHA256')
    root = canonical_directory(args.build_root)
    require(root.is_relative_to(LAB / '.cache'), 'LOCAL_BUILD_REQUIRED')
    matches = []
    for report_path in (LAB / 'evidence').glob('H18-native*-build.json'):
        report = read_json(report_path)
        binaries = report.get('binaries', [])
        if binaries and binaries[0].get('sha256') == args.expected_sha256 and LAB / binaries[0]['path'] == root / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture':
            matches.append((report_path, report))
    require(len(matches) == 1, 'ONE_MATCHING_BUILD_REPORT')
    report_path, build = matches[0]
    require(build.get('profile') == 'owned-goal-bridge' and build.get('status') == 'PASS' and
            build.get('credential_backend') == 'chromium-use-mock-keychain' and build.get('cef', {}).get('sha256') == PIN,
            'PINNED_EPHEMERAL_GOAL_ONLY')
    inventory = verify_inventory(root, build, args.expected_sha256)
    name = 'goal-' + uuid.uuid4().hex
    output = Path(os.path.abspath(args.output_dir or LAB / 'evidence' / ('H18-native-' + name)))
    canonical_directory(output.parent)
    output.mkdir(mode=0o700)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'launcher_sha256': sha(regular_bytes(Path(__file__), 65536)), 'status': 'FAIL', 'scope': 'fixed_owned_goal_fixture', 'native_host_executed': False,
              'native_host_execution_attempted': False, 'expected_executable_sha256': args.expected_sha256,
              'build_report': str(report_path.relative_to(LAB)), 'static_inventory': inventory,
              'credential_backend': build['credential_backend'], 'native_generation': args.generation,
              'sandbox_verified': False, 'third_party_content_allowed': False, 'production_connected': False,
              'requested': {'width': args.width, 'height': args.height, 'fps': args.fps,
                            'duration_ms': args.duration_ms, 'deadline_seconds': args.deadline_seconds,
                            'rss_limit_mib': args.rss_limit_mib}}
    try:
        if args.preflight_only:
            report.update(status='PASS', scope='static_preflight_only')
        else:
            cache = LAB / '.cache' / 'owned-goal-runs'
            cache.mkdir(exist_ok=True)
            canonical_directory(cache)
            private = cache / name
            private.mkdir(mode=0o700)
            fixture, supervision_root = private / 'fixture', private / 'supervisor'
            fixture.mkdir(mode=0o700)
            supervision_root.mkdir(mode=0o700)
            spec = importlib.util.spec_from_file_location('motive_goal_supervisor', LAB / 'poc/browser-host/supervisor.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            report['supervisor_source_sha256'] = sha(regular_bytes(Path(spec.origin), 65536))
            supervisor = module.Supervisor(supervision_root, deadline_seconds=args.deadline_seconds,
                                           rss_limit_kib=args.rss_limit_mib * 1024)
            command = [str(root / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'), '--owned-fixture',
                       str(fixture), str(args.generation), str(args.width), str(args.height), str(args.fps), str(args.duration_ms)]
            report['raw_evidence_root'] = str(private)
            supervision = invoke_supervisor(supervisor, command, report)
            report['supervision'] = supervision
            save_json(output / 'supervision.json', supervision)
            report['diagnostic_streams'] = collect_process_logs(supervision_root, output, supervision)
            phases = []
            for filename in ('frames.json', 'lifecycle.jsonl'):
                if (fixture / filename).exists():
                    data = regular_bytes(fixture / filename, 2 * 1024**2)
                    write_new(output / filename, data)
                    if filename == 'lifecycle.jsonl':
                        phases = [json.loads(row)['phase'] for row in data.splitlines()]
            report['lifecycle_phases'] = phases
            samples = {}
            for sample in ('first', 'visual', 'latest'):
                if not (fixture / (sample + '.bgra')).exists():
                    samples[sample] = {'status': 'NOT_EVALUATED', 'reason': 'sample not produced'}
                    continue
                pixels = regular_bytes(fixture / (sample + '.bgra'), 1920 * 1080 * 4)
                require(len(pixels) == args.width * args.height * 4, 'BGRA_SIZE')
                metadata = read_json(fixture / (sample + '.json'), 65536)
                require(metadata.get('native_executed') is True and metadata.get('generation') == args.generation and
                        (metadata.get('width'), metadata.get('height'), metadata.get('stride')) ==
                        (args.width, args.height, args.width * 4), 'NATIVE_METADATA')
                save_json(output / (sample + '.json'), metadata)
                write_new(output / (sample + '.bgra.gz'), gzip.compress(pixels, mtime=0))
                alpha = pixels[3::4]
                samples[sample] = {'status': 'PASS', 'raw_sha256': sha(pixels), 'raw_bytes': len(pixels),
                    'frame_index': metadata['index'], 'nonzero_alpha_pixels': sum(a > 0 for a in alpha),
                    'transparent_pixels': sum(a == 0 for a in alpha), 'partial_alpha_pixels': sum(0 < a < 255 for a in alpha),
                    'premultiplication_bound': all(max(pixels[i:i+3]) <= pixels[i+3] + 1 for i in range(0, len(pixels), 4)),
                    'metadata': metadata}
                if args.png:
                    data = preview_png(pixels, args.width, args.height)
                    write_new(output / (sample + '.png'), data)
                    samples[sample]['derived_png_sha256'] = sha(data)
            report['samples'] = samples
            required_phases = ['bootstrap_loaded', 'renderer_ready', 'properties_dispatched', 'goal_dispatched', 'visual_active', 'visual_complete']
            ipc = all(phase in phases for phase in required_phases)
            if ipc:
                ipc = [phases.index(p) for p in required_phases] == sorted(phases.index(p) for p in required_phases)
            visual = samples.get('visual', {})
            gates = {'native_ipc_lifecycle': 'PASS' if ipc else 'FAIL',
                     'real_visual_sample': 'PASS' if visual.get('status') == 'PASS' and visual.get('nonzero_alpha_pixels', 0) > 0 and visual.get('premultiplication_bound') else 'FAIL',
                     'visual_transparency': 'PASS' if visual.get('transparent_pixels', 0) > 0 and visual.get('nonzero_alpha_pixels', 0) > 0 else 'FAIL',
                     'completed_transparency': 'PASS' if samples.get('latest', {}).get('status') == 'PASS' and samples['latest'].get('nonzero_alpha_pixels') == 0 else 'FAIL',
                     'orderly_shutdown': 'PASS' if supervision.get('reason') == 'exit' and supervision.get('returncode') == 0 and 'shutdown_return' in phases else 'FAIL',
                     'observed_tree_cleanup': 'PASS' if supervision.get('final_cleanup_observed_tree') is True and supervision.get('final_remaining_observed_pids') == [] else 'FAIL',
                     'semantic_visual_inspection': 'NOT_EVALUATED', 'libobs_draw': 'NOT_EVALUATED', 'os_sandbox': 'NOT_EVALUATED'}
            report['gates'] = gates
            report['status'] = 'PASS' if all(gates[k] == 'PASS' for k in ('native_ipc_lifecycle', 'real_visual_sample', 'visual_transparency', 'completed_transparency', 'orderly_shutdown', 'observed_tree_cleanup')) else 'FAIL'
            report['limits'] = ['Visual state/ack is not a native terminal outcome or libobs draw.',
                                'PNG is derived by unpremultiplying retained real BGRA; inspect content separately.',
                                'Test Keychain backend and observed cleanup do not prove OS confinement.']
    except BaseException as error:
        report['error_type'] = type(error).__name__
        report['status'] = 'FAIL'
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save_json(output / 'report.json', report)
        print(json.dumps({'status': report['status'], 'gates': report.get('gates'), 'report': str(output / 'report.json')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
