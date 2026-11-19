#!/usr/bin/env python3
"""Supervise only the pinned, compiled, Motive-owned multi-widget fixture.

No URL, package, script, arbitrary binary, credential or Production argument.
Native execution is explicit. Tests and preflight never launch a browser.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
import uuid

from run_owned_fixture import (LAB, PIN, VIEWPORTS, canonical_directory, collect_process_logs,
    invoke_supervisor, parse_json, preview_png, read_json, regular_bytes, require, save_json,
    sha, verify_inventory, write_new)
from h19_metrics import resource_window, frame_window

SCENARIOS = {'steady', 'static', 'mixed', 'lifecycle', 'crash', 'goal', 'security', 'slow', 'hidden', 'resize', 'events', 'slow-consumer'}


def validate_options(args):
    require(args.instances in (1, 3, 5), 'INSTANCE_COUNT')
    require(args.scenario in SCENARIOS, 'FIXED_SCENARIO')
    require(args.scenario != 'lifecycle' or (args.instances == 3 and args.duration_ms >= 25000), 'LIFECYCLE_THREE_INITIAL_WIDGETS')
    require((args.width, args.height) in VIEWPORTS and args.fps in (30, 60), 'FIXED_VIEWPORT')
    require(1000 <= args.duration_ms <= 600000, 'FIXTURE_DURATION')
    require(math.isfinite(args.deadline_seconds) and args.duration_ms / 1000 < args.deadline_seconds <= 720, 'DEADLINE')
    require(64 <= args.rss_limit_mib <= 2048, 'RSS_LIMIT')
    require(args.generation is None or 1 <= args.generation <= 2**53 - 1000, 'JS_SAFE_GENERATION')
    require(re.fullmatch('[0-9a-f]{64}', args.expected_sha256) is not None, 'BUILD_HASH')


def match_build(args):
    root = canonical_directory(args.build_root)
    require(root.is_relative_to(LAB / '.cache'), 'LOCAL_BUILD_REQUIRED')
    executable = root / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'
    matches = []
    for path in sorted((LAB / 'evidence').glob('H19-native*-build.json')):
        report = read_json(path)
        binaries = report.get('binaries', [])
        if binaries and binaries[0].get('sha256') == args.expected_sha256 and LAB / binaries[0]['path'] == executable:
            require(report.get('status') == 'PASS' and report.get('cef', {}).get('sha256') == PIN, 'PINNED_BUILD')
            require(str(report.get('profile', '')).startswith('owned-multi'), 'OWNED_MULTI_PROFILE')
            require(report.get('credential_backend') == 'chromium-use-mock-keychain', 'LAB_TEST_BACKEND_REQUIRED')
            matches.append((path, report))
    require(len(matches) == 1, 'ONE_MATCHING_H19_BUILD')
    path, report = matches[0]
    return root, path, report, verify_inventory(root, report, args.expected_sha256)


class OwnedCanary:
    """Own loopback-only listener. If occupied, refuse to launch any probe.

    Count connections without reading/logging request data. No external routing.
    Zero connections proves only no observed hit at this canary, never OS egress.
    """
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind(('127.0.0.1', 18719))
            self.socket.listen(8)
            self.socket.settimeout(.1)
        except BaseException:
            self.socket.close()
            raise
        self.connections = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            connection.close()

    def close(self):
        self.stop.set()
        self.socket.close()
        self.thread.join(timeout=1)
        require(not self.thread.is_alive(), 'OWNED_CANARY_CLEANUP')


def collect_instance(fixture, output, item, png, goal=False):
    identity = tuple(item[k] for k in ('instance', 'generation', 'epoch'))
    require(all(type(n) is int and n > 0 for n in identity), 'INSTANCE_IDENTITY')
    name = 'instance-%d-g%d-e%d' % identity
    directory = canonical_directory(fixture / name)
    require(directory.parent == fixture, 'INSTANCE_ROOT')
    destination = output / name
    destination.mkdir(mode=0o700)
    result = {'identity': list(identity), 'manifest': item, 'samples': {}}
    for label in ('first', 'latest', 'visual'):
        pixels_path, metadata_path = directory / (label + '.bgra'), directory / (label + '.json')
        if not pixels_path.exists() or not metadata_path.exists():
            continue
        metadata = read_json(metadata_path, 65536)
        pixels = regular_bytes(pixels_path, 1920 * 1080 * 4)
        require(tuple(metadata.get(k) for k in ('instance', 'generation', 'epoch')) == identity, 'FRAME_IDENTITY_MIX')
        width, height = metadata['width'], metadata['height']
        require((width, height) in VIEWPORTS and metadata['stride'] == width * 4 and len(pixels) == width * height * 4, 'FRAME_DIMENSIONS')
        require((width, height) == (item['width'], item['height']), 'MANIFEST_DIMENSIONS')
        alphas = pixels[3::4]
        premultiplied = all(max(pixels[i:i+3]) <= pixels[i+3] + 1 for i in range(0, len(pixels), 4))
        alpha = {'zero_pixels': alphas.count(0), 'opaque_pixels': alphas.count(255),
                 'partial_pixels': len(alphas) - alphas.count(0) - alphas.count(255),
                 'premultiplied_bound': premultiplied}
        compressed = gzip.compress(pixels, compresslevel=6, mtime=0)
        write_new(destination / (label + '.bgra.gz'), compressed)
        save_json(destination / (label + '.json'), metadata)
        result['samples'][label] = {'metadata': metadata, 'raw_sha256': sha(pixels), 'raw_bytes': len(pixels),
                                   'gzip_sha256': sha(compressed), 'alpha': alpha}
        if not goal:
            marker = tuple(pixels[(40*width+108)*4:(40*width+108)*4+4])
            expected = (192, 64, identity[0]*32, 255)
            result['samples'][label]['instance_marker'] = {'observed_bgra': marker, 'expected_bgra': expected,
                'status': 'PASS' if marker == expected else 'NOT_EVALUATED' if marker == (0, 0, 0, 0) and label == 'first' else 'FAIL'}
        if png and label in ('latest', 'visual'):
            write_new(destination / (label + '.png'), preview_png(pixels, width, height))
    for filename in ('frames.json', 'lifecycle.jsonl', 'diagnostic.json'):
        path = directory / filename
        if path.exists():
            write_new(destination / filename, regular_bytes(path, 16 * 1024**2))
    if (directory / 'frames.json').exists():
        telemetry = read_json(directory / 'frames.json', 16 * 1024**2)
        result['telemetry'] = {k: v for k, v in telemetry.items() if k != 'samples'}
        stats = telemetry.get('accounting_v2', {})
        categories = ('pending', 'leased', 'coalesced', 'consumed', 'released_unconsumed', 'invalidated_close', 'revoked_generation', 'stale')
        result['paint_conservation'] = {'accepted': stats.get('paints'),
            'classified': sum(stats.get(key, 0) for key in categories), 'categories': list(categories)}
        result['paint_conservation']['status'] = 'PASS' if stats and stats['paints'] == result['paint_conservation']['classified'] else 'FAIL'
        rows = telemetry.get('samples', [])
        if rows:
            result['native_active_frames'] = frame_window(telemetry, rows[0][2], rows[-1][2] + 1)
        start, close = item.get('created_ns'), item.get('closed_ns')
        if start and close and close - start >= 70_000_000_000:
            result['native_steady_frames'] = frame_window(telemetry, start + 10_000_000_000, start + 70_000_000_000)
        elif start and close and close > start + 10_000_000_000:
            # Duration scheduling may begin before OnAfterCreated. Report actual
            # steady observation span, never silently stretch it to sixty seconds.
            result['native_steady_frames'] = frame_window(telemetry, start + 10_000_000_000, close)
    result['frame_delivery'] = bool(result['samples'].get('latest'))
    result['identity_validated'] = True
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--instances', type=int, default=1)
    p.add_argument('--scenario', choices=sorted(SCENARIOS), default='steady')
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--height', type=int, default=360)
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--duration-ms', type=int, default=72000)
    p.add_argument('--deadline-seconds', type=float, default=85)
    p.add_argument('--rss-limit-mib', type=int, default=2048)
    p.add_argument('--generation', type=int)
    p.add_argument('--png', action='store_true')
    p.add_argument('--preflight-only', action='store_true')
    p.add_argument('--memory-regions', action='store_true', help='One bounded metadata-only diagnostic; not a steady performance trial')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    report = {'status': 'FAIL', 'native_host_executed': False, 'native_host_execution_attempted': False,
              'third_party_content_allowed': False, 'production_connected': False, 'sandbox_verified': False}
    output = None
    output_created = False
    canary = None
    try:
        validate_options(args)
        build, build_path, build_report, inventory = match_build(args)
        output = Path(os.path.abspath(args.output_dir))
        canonical_directory(output.parent)
        require(output.is_relative_to(LAB / 'evidence'), 'LAB_EVIDENCE_REQUIRED')
        output.mkdir(mode=0o700)
        output_created = True
        report.update(scope='owned_cef_multi_widget_lab', static_inventory=inventory,
                      build_report=str(build_path.relative_to(LAB)), build_report_sha256=sha(regular_bytes(build_path, 2*1024**2)),
                      expected_executable_sha256=args.expected_sha256, credential_backend=build_report['credential_backend'],
                      requested={k: getattr(args, k) for k in ('instances', 'scenario', 'width', 'height', 'fps', 'duration_ms', 'deadline_seconds', 'rss_limit_mib')},
                      collector_sha256={p: sha(regular_bytes(LAB / p, 2*1024**2)) for p in
                        ('tools/run_h19_multi.py', 'tools/h19_metrics.py', 'poc/browser-host/supervisor.py')})
        if args.preflight_only:
            report.update(status='PASS', scope='static_preflight_only')
        else:
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
            cache = LAB / '.cache/h19-owned-runs'
            cache.mkdir(exist_ok=True)
            canonical_directory(cache)
            private = cache / run_id
            private.mkdir(mode=0o700)
            fixture, supervisor_root = private / 'fixture', private / 'supervisor'
            fixture.mkdir(mode=0o700)
            supervisor_root.mkdir(mode=0o700)
            if args.scenario == 'security':
                write_new(fixture / 'sandbox-decoy', b'MOTIVE_H19_OWNED_DECOY_NO_SECRET\n')
                canary = OwnedCanary()
            generation = args.generation or time.monotonic_ns() // 1000
            executable = build / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'
            command = [str(executable), '--owned-multi', str(fixture), str(generation), str(args.width),
                       str(args.height), str(args.fps), str(args.duration_ms), str(args.instances), args.scenario]
            spec = importlib.util.spec_from_file_location('h19_owned_supervisor', LAB / 'poc/browser-host/supervisor.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            supervisor = module.Supervisor(supervisor_root, deadline_seconds=args.deadline_seconds,
                rss_limit_kib=args.rss_limit_mib*1024, interval_seconds=.25, sample_capacity=4096, inspect_roles=True)
            report.update(native_generation=generation, raw_evidence_root=str(private), run_id=run_id)
            memory_regions = []
            def sample_hook(sample):
                if args.memory_regions and not memory_regions and sample['elapsed_ms'] >= 3000 and sample['phase'] == 'running':
                    from h19_memory_regions import inspect_owned_regions
                    probe = {'trigger_elapsed_ms': sample['elapsed_ms'], 'processes': []}
                    memory_regions.append(probe)
                    for process in sample['resource_usage']['processes'][:16]:
                        row = inspect_owned_regions(module, (process['pid'], process['birth']))
                        row['role'] = process['role']
                        probe['processes'].append(row)
            supervision = invoke_supervisor(supervisor, command, report, on_sample=sample_hook)
            if args.memory_regions:
                save_json(output / 'memory-regions.json', memory_regions)
                report['memory_regions_diagnostic'] = True
            if canary:
                canary.close()
                report['owned_loopback_canary'] = {'bound': True, 'accepted_connections': canary.connections, 'connections': canary.connections, 'closed': True,
                    'scope': 'own fixed loopback endpoint only; zero hits is not OS egress denial'}
                canary = None
            payload = (json.dumps(supervision, separators=(',', ':'), allow_nan=False)+'\n').encode()
            zipped = gzip.compress(payload, compresslevel=6, mtime=0)
            write_new(output / 'supervision.json.gz', zipped)
            report['supervision_sha256'] = sha(payload)
            report['supervision_gzip_sha256'] = sha(zipped)
            report['supervision'] = {k: v for k, v in supervision.items() if k != 'samples'}
            report['resources'] = {name: resource_window(supervision.get('samples', []), lo, hi) for name, lo, hi in
                [('startup_warmup', 0, 10000), ('steady', 10000, min(70000, args.duration_ms)),
                 ('last_10_seconds', max(0, args.duration_ms-10000), args.duration_ms)]}
            report['diagnostic_streams'] = collect_process_logs(supervisor_root, output, supervision)
            for filename in ('lifecycle.jsonl', 'instances.json', 'security.json'):
                if (fixture / filename).exists():
                    write_new(output / filename, regular_bytes(fixture / filename, 16*1024**2))
            manifest = read_json(fixture / 'instances.json', 16*1024**2)
            entries = manifest['instances']
            require(type(entries) is list and 1 <= len(entries) <= 256, 'INSTANCE_MANIFEST')
            require(manifest.get('configured_widgets') == args.instances and manifest.get('scenario') == args.scenario, 'MANIFEST_SCENARIO')
            require(set(range(1, args.instances+1)).issubset({item['instance'] for item in entries}), 'MISSING_INITIAL_WIDGET')
            identities = [tuple(item[k] for k in ('instance', 'generation', 'epoch')) for item in entries]
            require(len(set(identities)) == len(identities), 'DUPLICATE_INSTANCE_GENERATION')
            goal = 'goal' in build_report.get('profile', '')
            frame_entries = []
            for item in entries:
                epochs = item.get('epochs', [])
                if epochs:
                    for epoch in epochs:
                        frame_item = dict(item)
                        frame_item.update({key: epoch[key] for key in ('epoch', 'width', 'height', 'first_paint_ns', 'first_nontransparent_paint_ns')})
                        frame_item.update(browser_created_ns=item['created_ns'], browser_closed_ns=item['closed_ns'],
                                          created_ns=epoch['started_ns'], closed_ns=epoch['ended_ns'],
                                          timing_scope='frame_epoch', epoch_record=epoch)
                        frame_entries.append(frame_item)
                else:
                    frame_entries.append(item)
            report['instances'] = [collect_instance(fixture, output, item, args.png, goal) for item in frame_entries]
            healthy_exit = supervision.get('reason') == 'exit' and supervision.get('returncode') == 0
            cleanup = supervision.get('final_cleanup_observed_tree') is True and supervision.get('final_remaining_observed_pids') == []
            memory = supervision.get('peak_tree_rss_kib', 2**63) <= args.rss_limit_mib*1024
            paints = all(item['frame_delivery'] for item in report['instances'])
            native_closed = all(item.get('closed') is True and item.get('closed_ns', 0) > 0 for item in entries)
            failures_expected = not any(item.get('failed') for item in entries) or args.scenario in ('crash', 'lifecycle')
            conservation = all(item.get('paint_conservation', {}).get('status') == 'PASS' for item in report['instances'])
            markers = goal or all(item['samples'].get('latest', {}).get('instance_marker', {}).get('status') == 'PASS' for item in report['instances'])
            report['gates'] = {'native_exit': 'PASS' if healthy_exit else 'FAIL', 'observed_cleanup': 'PASS' if cleanup else 'FAIL',
                'rss_budget': 'PASS' if memory else 'FAIL', 'per_generation_frames': 'PASS' if paints else 'FAIL',
                'frame_identity': 'PASS', 'instance_pixel_markers': 'NOT_EVALUATED' if goal else 'PASS' if markers else 'FAIL',
                'paint_conservation': 'PASS' if conservation else 'FAIL',
                'native_final_close': 'PASS' if native_closed else 'FAIL',
                'unexpected_instance_failure': 'PASS' if failures_expected else 'FAIL',
                'third_party_isolation': 'BLOCKED', 'production_keychain': 'BLOCKED', 'libobs': 'NOT_EVALUATED'}
            report['status'] = 'PASS' if healthy_exit and cleanup and memory and paints and conservation and markers and native_closed and failures_expected else 'FAIL'
            report['limits'] = ['PASS is the scoped owned native run, never global H19 acceptance.',
                'Mock Keychain is an explicit Chromium test backend, not a production fix.',
                'Frame acquisition is not audiovisual output FPS. No CEF timestamp is PTS.',
                'Python and native clocks are analyzed separately.',
                'Only observed PID/birth identities are proven cleaned; this is not hostile process confinement.']
        save_json(output / 'report.json', report)
        print(json.dumps({'status': report['status'], 'gates': report.get('gates'), 'report': str(output / 'report.json')}, indent=2))
        return 0 if report['status'] == 'PASS' else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['error'] = {'type': type(error).__name__, 'code': str(error)[:512]}
        if output_created and not (output / 'report.json').exists():
            save_json(output / 'report.json', report)
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 1
    finally:
        if canary:
            canary.close()


if __name__ == '__main__':
    raise SystemExit(main())
