#!/usr/bin/env python3
"""Run one fixed owned diagnostic, never arbitrary renderer input or URLs."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid
from run_owned_fixture import (LAB, PIN, canonical_directory, collect_process_logs,
    collect_samples, invoke_supervisor, parser, read_json, regular_bytes, require,
    save_json, sha, validate_options, verify_inventory, write_new)
MODES = {'static':1, 'hidden':2, 'slow':3, 'crash':4, 'slow-consumer':5}


def classify(mode, diagnostic, phases, frames, samples, supervision):
    names = [p['phase'] for p in phases]
    latest = samples.get('latest', {})
    stamps = [s[1] for s in frames.get('samples', [])]
    gaps = [(b-a)/1e6 for a,b in zip(stamps, stamps[1:])]
    expected_code = 42 if mode == 'crash' else 0
    gates = {'native_frame': 'PASS' if latest.get('status') == 'PASS' else 'FAIL',
             'alpha_pixels': latest.get('alpha', {}).get('status', 'NOT_EVALUATED'),
             'fixture_ready': 'PASS' if diagnostic.get('fixture_ready') else 'FAIL',
             'native_shutdown': 'PASS' if supervision.get('reason') == 'exit' and supervision.get('returncode') == expected_code and 'shutdown_return' in names else 'FAIL',
             'generation_revoked': 'PASS' if diagnostic.get('revocation_confirmed') is True else 'FAIL',
             'observed_cleanup': 'PASS' if supervision.get('final_cleanup_observed_tree') is True and supervision.get('final_remaining_observed_pids') == [] else 'FAIL'}
    observations = {'maximum_observed_paint_gap_ms': max(gaps, default=None),
                    'accepted_mailbox_paints': frames.get('paints'), 'acquired': frames.get('acquired'),
                    'coalesced': frames.get('coalesced'), 'busy': frames.get('onpaint_busy'),
                    'expected_host_exit_code': expected_code, 'host_healthy_exit': mode != 'crash' and supervision.get('returncode') == 0}
    if mode == 'static':
        gates['static_single_js_paint'] = 'PASS' if diagnostic.get('static_painted') and names.count('static_painted_once') == 1 and latest.get('counter', {}).get('value_modulo_256') == 1 else 'FAIL'
    elif mode == 'hidden':
        begin = next((p['observed_ns'] for p in phases if p['phase'] == 'hidden_settled'), None)
        end = next((p['observed_ns'] for p in phases if p['phase'] == 'hidden_end'), None)
        during = sum(begin < stamp < end for stamp in stamps) if begin is not None and end is not None else None
        before_after = begin is not None and end is not None and any(t < begin for t in stamps) and any(t > end for t in stamps)
        gates['hidden_stops_osr_and_resumes'] = 'PASS' if diagnostic.get('hidden_finished') and diagnostic.get('hidden_settled') and diagnostic.get('hidden_baseline_callbacks') == diagnostic.get('hidden_end_callbacks') and during == 0 and before_after else 'FAIL'
        observations.update(accepted_samples_while_hidden_after_settle=during, document_visibility_events=[n for n in names if n in ('document_hidden','document_visible')])
    elif mode == 'slow':
        delta = diagnostic.get('slow_end_ns', 0) - diagnostic.get('slow_begin_ns', 0)
        gates['fixed_500ms_js_block_observed'] = 'PASS' if 450_000_000 <= delta <= 2_000_000_000 and max(gaps, default=0) >= 400 else 'FAIL'
        observations['slow_phase_observed_ms'] = delta / 1e6
    elif mode == 'crash':
        gates['controlled_renderer_error'] = 'PASS' if diagnostic.get('crash_requested') is True and diagnostic.get('renderer_terminated') is True and diagnostic.get('renderer_decoded_exit_code') == 86 and all(n in names for n in ('renderer_exit_requested','renderer_error_observed','frame_generation_revoked')) else 'FAIL'
        observations['expected_controlled_error_not_healthy'] = True
    elif mode == 'slow-consumer':
        gates['coalescing_under_100ms_consumer_delay'] = 'PASS' if frames.get('configured_consumer_delay_ms') == 100 and frames.get('coalesced', 0) > 0 and frames.get('paints', 0) > frames.get('acquired', 0) > 1 else 'FAIL'
        observations['consumer_duration_includes_deliberate_delay'] = True
    return {'status':'PASS' if all(value == 'PASS' for value in gates.values()) else 'FAIL', 'gates':gates, 'observations':observations}


def main(argv=None):
    options = parser()
    options.add_argument('--mode', required=True, choices=MODES)
    args = options.parse_args(argv)
    validate_options(args)
    require(args.generation is not None and args.generation <= 9007199254740991, 'EXPLICIT_SAFE_GENERATION')
    require(args.duration_ms == 5000 and args.deadline_seconds == 10 and args.rss_limit_mib <= 2048, 'FIXED_SHORT_DIAGNOSTIC_BUDGET')
    require(re.fullmatch(r'[0-9a-f]{64}', args.expected_sha256) is not None, 'EXPECTED_SHA256')
    root = canonical_directory(args.build_root)
    require(root.is_relative_to(LAB / '.cache'), 'LOCAL_BUILD_REQUIRED')
    matches = []
    for path in (LAB / 'evidence').glob('H18-native*-build.json'):
        build = read_json(path)
        records = build.get('binaries', [])
        if records and records[0].get('sha256') == args.expected_sha256 and LAB / records[0]['path'] == root / 'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture':
            matches.append((path,build))
    require(len(matches) == 1, 'ONE_MATCHING_BUILD')
    build_path, build = matches[0]
    require(build.get('profile') == 'owned-diagnostic-' + args.mode and build.get('diagnostic_profile') == args.mode and build.get('status') == 'PASS' and build.get('cef', {}).get('sha256') == PIN and build.get('credential_backend') == 'chromium-use-mock-keychain', 'FIXED_DIAGNOSTIC_PROFILE')
    inventory = verify_inventory(root, build, args.expected_sha256)
    run_id = args.mode + '-' + uuid.uuid4().hex
    output = Path(os.path.abspath(args.output_dir or LAB / 'evidence' / ('H18-native-' + run_id)))
    canonical_directory(output.parent)
    output.mkdir(mode=0o700)
    report = {'status':'FAIL','started_utc':datetime.now(timezone.utc).isoformat(),'mode':args.mode,
              'native_host_executed':False,'native_host_execution_attempted':False,
              'scope':'one short fixed owned native diagnostic, not full performance acceptance',
              'expected_executable_sha256':args.expected_sha256,'static_inventory':inventory,
              'build_report':str(build_path.relative_to(LAB)),'build_report_sha256':sha(regular_bytes(build_path,2*1024**2)),
              'launcher_sha256':sha(regular_bytes(Path(__file__),65536)),
              'credential_backend':build['credential_backend'],'native_generation':args.generation,
              'production_connected':False,'sandbox_verified':False,'third_party_content_allowed':False,
              'requested':{'width':args.width,'height':args.height,'fps':args.fps,'duration_ms':5000,'deadline_seconds':10,'rss_limit_mib':args.rss_limit_mib}}
    try:
        if args.preflight_only:
            report.update(status='PASS',scope='static_preflight_only')
        else:
            cache = LAB / '.cache/owned-diagnostic-runs'
            cache.mkdir(exist_ok=True)
            canonical_directory(cache)
            private = cache / run_id
            private.mkdir(mode=0o700)
            fixture, supervisor_root = private / 'fixture', private / 'supervisor'
            fixture.mkdir(mode=0o700);supervisor_root.mkdir(mode=0o700)
            path = LAB / 'poc/browser-host/supervisor.py'
            spec = importlib.util.spec_from_file_location('motive_diagnostic_supervisor',path)
            module = importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            report['supervisor_sha256']=sha(regular_bytes(path,65536))
            supervisor = module.Supervisor(supervisor_root,deadline_seconds=10,rss_limit_kib=args.rss_limit_mib*1024)
            command = [str(root/'MotiveBrowserFixture.app/Contents/MacOS/MotiveBrowserFixture'),'--owned-fixture',str(fixture),str(args.generation),str(args.width),str(args.height),str(args.fps),'5000']
            report['raw_evidence_root']=str(private)
            supervision = invoke_supervisor(supervisor,command,report)
            report['supervision']=supervision;save_json(output/'supervision.json',supervision)
            report['diagnostic_streams']=collect_process_logs(supervisor_root,output,supervision)
            samples = collect_samples(fixture,output,args.width,args.height,args.generation,args.png)
            report['samples']=samples
            diagnostic,frames,phases={},{},[]
            for name in ('frames.json','diagnostic.json','lifecycle.jsonl'):
                if (fixture/name).exists():
                    data=regular_bytes(fixture/name,2*1024**2);write_new(output/name,data)
                    if name=='frames.json':frames=json.loads(data)
                    elif name=='diagnostic.json':diagnostic=json.loads(data)
                    else:phases=[json.loads(row) for row in data.splitlines()]
            report.update(classify(args.mode,diagnostic,phases,frames,samples,supervision))
            report.update(diagnostic=diagnostic,lifecycle_phases=[p['phase'] for p in phases])
            report['limits']=['Controlled renderer _exit(86) is process-failure recovery, not a memory-corruption test.',
                              'Retained crash pixels are offline evidence; the native generation is revoked.',
                              'Three-buffer residency is a contract bound, not observed total Chromium memory.',
                              'No libobs draw, OS sandbox acceptance or 70-second benchmark acceptance.']
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__)
        raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save_json(output/'report.json',report)
        print(json.dumps({'status':report['status'],'mode':args.mode,'gates':report.get('gates'),'report':str(output/'report.json')}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
