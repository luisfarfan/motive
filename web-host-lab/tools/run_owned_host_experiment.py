#!/usr/bin/env python3
"""Explicit short 1/3/5-host experiment; one owned smoke widget per CEF host.

Never run by automatic verification. This is not the frozen 60-second benchmark
matrix, shared-host testing, third-party execution or OS sandbox acceptance.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import uuid

import run_owned_fixture as fixture


class AggregateBudget:
    """RSS emergency stop over the latest observations of every launched host."""
    def __init__(self, hosts, limit_kib):
        fixture.require(hosts in (1, 3, 5) and 1 <= limit_kib <= 2 * 1024**2, 'AGGREGATE_BUDGET')
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.latest = {}
        self.peak_kib = 0
        self.peak_footprint_bytes = None
        self.limit_kib = limit_kib
        self.triggered = False
        self.samples = []

    def observe(self, host, sample):
        with self.lock:
            now = time.monotonic_ns()
            footprint = sample.get('resource_usage', {}).get('phys_footprint_bytes')
            self.latest[host] = (sample['rss_kib'], now, footprint)
            total = sum(row[0] for row in self.latest.values())
            footprints = [row[2] for row in self.latest.values()]
            footprint_total = sum(footprints) if all(value is not None for value in footprints) else None
            if footprint_total is not None:
                self.peak_footprint_bytes = max(self.peak_footprint_bytes or 0, footprint_total)
            self.peak_kib = max(self.peak_kib, total)
            self.samples.append({'monotonic_ns': now, 'reporting_host': host,
                                 'latest_observed_tree_rss_kib': total,
                                 'latest_observed_tree_phys_footprint_bytes': footprint_total,
                                 'oldest_observation_age_ns': now - min(row[1] for row in self.latest.values()),
                                 'observed_hosts': len(self.latest)})
            if total > self.limit_kib:
                self.triggered = True
                self.cancel.set()

    def finished(self, host):
        with self.lock:
            self.latest.pop(host, None)


def summarize_hosts(hosts, wall_ns):
    cpu_ns, cpu_intervals, roles = 0, 0, {}
    for host in hosts:
        resource = host.get('supervision', {}).get('resource_measurements', {})
        cpu_ns += resource.get('observed_cpu_delta_ns', 0)
        cpu_intervals += resource.get('valid_cpu_intervals', 0)
        for role, count in resource.get('observed_process_roles', {}).items():
            roles[role] = roles.get(role, 0) + count
    return {'observed_process_roles': roles,
            'observed_unique_processes': sum(h.get('supervision', {}).get('observed_processes', 0) for h in hosts),
            'observed_cpu_delta_ns': cpu_ns if cpu_intervals else None,
            'valid_host_cpu_intervals': cpu_intervals,
            'launch_to_join_wall_ns': wall_ns,
            'observed_cpu_percent_over_launch_to_join_one_core': 100 * cpu_ns / wall_ns if cpu_intervals and wall_ns else None,
            'gpu_percent': None}


def distribution(values):
    values = sorted(values)
    return {'count': len(values), 'median': statistics.median(values) if values else None,
            'p95_nearest_rank': values[max(0, (95 * len(values) + 99) // 100 - 1)] if values else None}


def run_host(index, args, build_root, private, output, supervisor_module, budget, barrier):
    host_private, host_output = private / f'host-{index}', output / f'host-{index}'
    report = {'host': index, 'native_host_executed': False, 'native_host_execution_attempted': False,
              'raw_evidence_root': str(host_private)}
    output_created = False
    try:
        host_private.mkdir(mode=0o700)
        host_output.mkdir(mode=0o700)
        output_created = True
        root, supervisor_root = host_private / 'fixture', host_private / 'supervisor'
        root.mkdir(mode=0o700); supervisor_root.mkdir(mode=0o700)
        supervisor = supervisor_module.Supervisor(supervisor_root, deadline_seconds=args.deadline_seconds,
            rss_limit_kib=args.rss_limit_mib * 1024, interval_seconds=args.sample_interval_ms / 1000)
        generation = (args.generation if args.generation is not None else time.monotonic_ns()) + index
        command = [str(build_root / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'),
                   '--owned-fixture', str(root), str(generation), str(args.width), str(args.height), str(args.fps), str(args.duration_ms)]
        barrier.wait(timeout=3)
        if budget.cancel.is_set():
            report.update(status='FAIL', error='experiment cancelled before launch')
        else:
            report['launch_requested_monotonic_ns'] = time.monotonic_ns()
            supervision = fixture.invoke_supervisor(supervisor, command, report,
                cancelled=budget.cancel.is_set, on_sample=lambda sample: budget.observe(index, sample))
            report['supervision'] = supervision
            fixture.save_json(host_output / 'supervision.json', supervision)
            report['diagnostic_streams'] = fixture.collect_process_logs(supervisor_root, host_output, supervision)
            samples = fixture.collect_samples(root, host_output, args.width, args.height, generation, args.png)
            report.update(samples=samples, **fixture.classify(supervision, samples))
            report['native_generation'] = generation
            resource_samples = [s['resource_usage'] for s in supervision.get('samples', []) if 'resource_usage' in s]
            report['retained_sample_statistics'] = {
                'scope': 'retained per-host intervals; includes startup and shutdown, no warmup subtraction',
                'cpu_percent_one_core': distribution([s['cpu_percent_one_core'] for s in resource_samples
                                                      if s['cpu_percent_one_core'] is not None]),
                'cpu_complete_observed_identity_intervals_percent_one_core': distribution([
                    s['cpu_percent_one_core'] for s in resource_samples
                    if s['cpu_observed_identity_coverage_complete'] and s['cpu_percent_one_core'] is not None]),
                'phys_footprint_bytes': distribution([s['phys_footprint_bytes'] for s in resource_samples
                                                     if s['phys_footprint_bytes'] is not None])}
            for name in ('frames.json', 'lifecycle.jsonl'):
                if (root / name).exists():
                    fixture.write_new(host_output / name, fixture.regular_bytes(root / name, 2 * 1024**2))
            if report['gates']['orderly_shutdown'] == 'FAIL' or report['gates']['observed_tree_cleanup'] == 'FAIL':
                budget.cancel.set()
    except BaseException as error:
        budget.cancel.set()
        barrier.abort()
        report.update(status='FAIL', error_type=type(error).__name__)
    finally:
        budget.finished(index)
        if output_created:
            fixture.save_json(host_output / 'report.json', report)
    return report


def parser():
    result = fixture.parser()
    result.description = __doc__
    result.add_argument('--hosts', type=int, choices=(1, 3, 5), required=True)
    result.add_argument('--sample-interval-ms', type=int, choices=(100, 250, 500), default=250)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    output, output_created = None, False
    report = {'status': 'FAIL', 'scope': 'short_owned_host_scaling_experiment',
              'topology': 'one owned smoke widget per independent CEF host', 'requested_hosts': args.hosts,
              'native_host_execution_attempted': False, 'production_connected': False, 'sandbox_verified': False}
    try:
        fixture.validate_options(args)
        fixture.require(args.generation is None or args.generation + args.hosts < 2**64, 'GENERATION')
        build_root, report_path, build_report = fixture.match_build_report(args.build_root, args.expected_sha256)
        report['static_inventory'] = fixture.verify_inventory(build_root, build_report, args.expected_sha256)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
        output = Path(os.path.abspath(args.output_dir or fixture.LAB / 'evidence' / ('H18-owned-hosts-' + run_id)))
        fixture.canonical_directory(output.parent)
        output.mkdir(mode=0o700)
        output_created = True
        report.update(run_id=run_id, build_report=str(report_path.relative_to(fixture.LAB)),
                      build_report_sha256=fixture.sha(fixture.regular_bytes(report_path, 2 * 1024**2)),
                      expected_executable_sha256=args.expected_sha256, credential_backend=build_report.get('credential_backend'),
                      requested={'width': args.width, 'height': args.height, 'fps': args.fps, 'duration_ms': args.duration_ms,
                                 'deadline_seconds': args.deadline_seconds, 'sample_interval_ms': args.sample_interval_ms,
                                 'aggregate_rss_limit_mib': args.rss_limit_mib},
                      collector_sha256={str(path.relative_to(fixture.LAB)): fixture.sha(fixture.regular_bytes(path, 1024**2))
                          for path in (Path(__file__).resolve(), Path(fixture.__file__).resolve(), fixture.LAB / 'poc/browser-host/supervisor.py')})
        if args.preflight_only:
            report.update(status='PASS', scope='static_preflight_only')
        else:
            cache = fixture.LAB / '.cache' / 'owned-fixture-runs'
            cache.mkdir(exist_ok=True)
            fixture.canonical_directory(cache)
            private = cache / run_id
            private.mkdir(mode=0o700)
            spec = importlib.util.spec_from_file_location('motive_experiment_supervisor', fixture.LAB / 'poc/browser-host/supervisor.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            budget = AggregateBudget(args.hosts, args.rss_limit_mib * 1024)
            barrier = threading.Barrier(args.hosts)
            started = time.monotonic_ns()
            report['native_host_execution_attempted'] = True
            with ThreadPoolExecutor(max_workers=args.hosts) as executor:
                futures = [executor.submit(run_host, i, args, build_root, private, output, module, budget, barrier)
                           for i in range(1, args.hosts + 1)]
                try:
                    hosts = [future.result() for future in futures]
                except BaseException:
                    budget.cancel.set()
                    barrier.abort()
                    raise
            wall_ns = time.monotonic_ns() - started
            report.update(hosts=hosts, summary=summarize_hosts(hosts, wall_ns),
                          aggregate_rss={'peak_latest_observed_tree_rss_kib': budget.peak_kib,
                                         'peak_latest_observed_tree_phys_footprint_bytes': budget.peak_footprint_bytes,
                                         'limit_kib': budget.limit_kib, 'emergency_triggered': budget.triggered,
                                         'samples': budget.samples})
            statuses = {host['status'] for host in hosts}
            operational_failure = any(host.get('gates', {}).get(gate) == 'FAIL' for host in hosts
                                      for gate in ('frame_delivery', 'alpha_pixels', 'orderly_shutdown', 'observed_tree_cleanup'))
            measured = all(host.get('supervision', {}).get('resource_measurements', {}).get('valid_cpu_intervals', 0) > 0
                           for host in hosts)
            report['status'] = ('FAIL' if 'FAIL' in statuses or budget.triggered or operational_failure else
                                ('PASS' if statuses == {'PASS'} and measured else 'PARTIAL'))
            report['benchmark_acceptance'] = 'NOT_EVALUATED'
            report['limits'] = ['Short diagnostic run; no 10s warmup, 60s steady-state trials, repetitions or soak.',
                'Each CEF host may create multiple helpers; reported roles/process totals are measured, not assumed.',
                'Aggregate RSS combines latest asynchronous observations; sample ages are retained and transient peaks may be missed.',
                'Emergency RSS limit applies across all hosts; polling can observe an overshoot before cancellation.',
                'Physical footprint aggregates latest per-host observations, not simultaneous pages or the sum of independent host peaks.',
                'CPU excludes short-lived/unobserved intervals and supervisor overhead; GPU remains null.',
                'No OBS comparison, shared-host topology, libobs texture or OS confinement claim.']
        fixture.save_json(output / 'report.json', report)
        print(json.dumps({'status': report['status'], 'report': str(output / 'report.json'),
                          'summary': report.get('summary')}, indent=2))
        return 0 if report['status'] == 'PASS' else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        report['error'] = {'type': type(error).__name__, 'code': str(error)[:512]}
        if output_created and not (output / 'report.json').exists():
            fixture.save_json(output / 'report.json', report)
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
