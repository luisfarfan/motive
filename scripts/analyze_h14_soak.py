#!/usr/bin/env python3
"""Post-run analysis only. Never contact Motive or analyze a live output.

Requires an operator-approved CPU window, a finalized memory-run report, two
quiescent outputs and a new evidence directory. Uses only the specified
portable bundle's FFmpeg/FFprobe. --plan does not read a run or execute tools.
"""
import argparse
from array import array
import csv
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import traceback

from analyze_h14_memory import analyze as analyze_memory
from h14_soak_helpers import (PCMStats, QuadrantFreshness, Timeline,
                              packet_origin_proof, tail_candidates, tail_status_with_ambiguity)
from verification_paths import verification_paths

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def compact_line(line):
    return dict(part.split('=', 1) for part in line.strip().split('|') if '=' in part)


def fingerprint(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]


class Passes:
    def __init__(self, directory, timeout, report):
        self.directory, self.timeout, self.report = directory, timeout, report

    def run(self, label, arguments, consume):
        log = self.directory / (label + '-stderr.txt')
        entry = {'label': label, 'command': [str(value) for value in arguments],
                 'stderr': str(log), 'timeout_seconds': self.timeout}
        self.report.setdefault('commands', []).append(entry)
        environment = {key: value for key, value in os.environ.items() if not key.startswith('DYLD_')}
        environment['PATH'] = '/usr/bin:/bin'
        with log.open('xb') as errors:
            process = subprocess.Popen(entry['command'], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=errors, env=environment)
            expired = []
            def timeout():
                if process.poll() is None:
                    expired.append(True)
                    process.kill()  # Only this analyzer's own FFmpeg/FFprobe child.
            timer = threading.Timer(self.timeout, timeout)
            timer.start()
            try:
                value = consume(process.stdout)
                code = process.wait(timeout=10)
            finally:
                timer.cancel()
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                entry['returncode'] = process.returncode
                entry['timed_out'] = bool(expired)
        entry['stderr_sha256'] = sha(log)
        if code or expired or log.stat().st_size:
            raise ValueError(f'{label}: media tool failed or emitted an error; see retained stderr')
        return value


def validate_streams(probe, expected_plan):
    dimensions = {'1920x1080': (1920, 1080), '1280x720': (1280, 720)}
    resolution = expected_plan.get('resolution')
    if resolution not in dimensions:
        raise ValueError('Unknown controlled-soak plan resolution')
    width, height = dimensions[resolution]
    fps = expected_plan['fps']
    video = [stream for stream in probe['streams'] if stream['codec_type'] == 'video']
    audio = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
    if len(video) != 1 or len(audio) != 1 or len(probe['streams']) != 2:
        raise ValueError('Expected exactly one video and one audio stream')
    video, audio = video[0], audio[0]
    if (video['codec_name'], video['width'], video['height'], Fraction(video['avg_frame_rate'])) != ('h264', width, height, Fraction(fps)):
        raise ValueError('Video format differs from the controlled soak')
    if (audio['codec_name'], int(audio['sample_rate']), audio['channels']) != ('aac', 48000, 2):
        raise ValueError('Expected AAC 48 kHz stereo')
    return {'codec': 'h264', 'width': width, 'height': height, 'fps': fps}


def probe_media(tools, passes, path, directory, expected_plan):
    probe = passes.run('streams', [tools['ffprobe'], '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', path], lambda stdout: json.load(stdout))
    save(directory / 'streams.json', probe)
    expected_video = validate_streams(probe, expected_plan)
    fps = expected_plan['fps']
    frames_path = directory / 'frames.jsonl'
    frames = Timeline(1.5 / fps)
    frame_types = {}
    def frame_consumer(stdout):
        with frames_path.open('x') as output:
            for raw in stdout:
                row = compact_line(raw.decode('utf-8'))
                if 'pict_type' not in row:
                    continue  # Side-data-only line, not an additional decoded frame.
                frames.add(row.get('best_effort_timestamp_time'))
                kind = row['pict_type']
                frame_types[kind] = frame_types.get(kind, 0) + 1
                output.write(json.dumps(row, separators=(',', ':')) + '\n')
    passes.run('frames', [tools['ffprobe'], '-v', 'error', '-threads', '2', '-select_streams', 'v:0',
        '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time,pkt_dts_time,duration_time,pict_type,key_frame',
        '-of', 'compact=p=0:nk=0', path], frame_consumer)

    timelines = {kind: {'pts': Timeline(1.5 / fps if kind == 'video' else .023),
                        'dts': Timeline(1.5 / fps if kind == 'video' else .023)} for kind in ('video', 'audio')}
    first, pts = {kind: [] for kind in timelines}, {kind: array('d') for kind in timelines}
    packets_path = directory / 'packets.jsonl'
    def packet_consumer(stdout):
        with packets_path.open('x') as output:
            for raw in stdout:
                row = compact_line(raw.decode('utf-8'))
                kind = row.get('codec_type')
                if kind not in timelines:
                    continue
                output.write(json.dumps(row, separators=(',', ':')) + '\n')
                for field in ('pts', 'dts'):
                    timelines[kind][field].add(row.get(field + '_time'))
                if row.get('pts_time') not in (None, 'N/A'):
                    pts[kind].append(float(row['pts_time']))
                if len(first[kind]) < 8:
                    first[kind].append(row)
    passes.run('packets', [tools['ffprobe'], '-v', 'error', '-show_packets', '-show_entries',
        'packet=codec_type,stream_index,pts_time,dts_time,duration_time,size,flags',
        '-of', 'compact=p=0:nk=0', path], packet_consumer)
    return {'probe': probe, 'expected_video': expected_video,
            'frames': frames.result(), 'frame_types': frame_types,
            'packet_timelines': {kind: {field: value.result() for field, value in fields.items()}
                                 for kind, fields in timelines.items()},
            'artifacts': {str(p.name): sha(p) for p in (frames_path, packets_path)}}, first, pts


def read_frame(stdout, size):
    data = bytearray()
    while len(data) < size:
        block = stdout.read(size - len(data))
        if not block:
            break
        data.extend(block)
    if data and len(data) != size:
        raise ValueError('Partial decoded gray frame')
    return bytes(data)


def video_pixels(tools, passes, path, directory, fps, expected_frames, freeze_seconds):
    hashes_path, csv_path = directory / 'video.framemd5', directory / 'quadrant-pixels.csv'
    freshness = QuadrantFreshness()
    count = 0
    headers = ['index', 'pts_s', 'full_md5'] + [f'q{i}_{field}' for i in range(4) for field in ('md5', 'mad', 'fraction')]
    def consume(stdout):
        nonlocal count
        with (directory / 'frames.jsonl').open() as timestamps, csv_path.open('x', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            while frame := read_frame(stdout, 128 * 72):
                line = timestamps.readline()
                if not line:
                    raise ValueError('More raw frames than FFprobe frames')
                row = json.loads(line)
                pts = float(row['best_effort_timestamp_time'])
                value = freshness.add(frame, pts, 1 / fps)
                writer.writerow([count, pts, value['full_md5']] + [field for quadrant in value['quadrants']
                    for field in (quadrant['md5'], quadrant['mad_from_reference'], quadrant['changed_probe_fraction'])])
                count += 1
            if timestamps.readline():
                raise ValueError('Fewer raw frames than FFprobe frames')
    passes.run('video-full-decode', [tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror', '-threads', '2',
        '-filter_complex_threads', '1', '-i', path, '-filter_complex',
        '[0:v:0]scale=128:72:flags=area,format=gray,split=2[hash][pixels]',
        '-map', '[hash]', '-an', '-c:v', 'rawvideo', '-threads:v', '1', '-fps_mode', 'passthrough',
        '-f', 'framemd5', hashes_path, '-map', '[pixels]', '-an', '-c:v', 'rawvideo', '-threads:v', '1',
        '-fps_mode', 'passthrough', '-f', 'rawvideo', 'pipe:1'], consume)
    verified = 0
    with hashes_path.open() as official, csv_path.open() as calculated:
        rows = csv.DictReader(calculated)
        for line in official:
            if not line.strip() or line.startswith('#'):
                continue
            fields = [field.strip() for field in line.split(',')]
            row = next(rows, None)
            if row is None or len(fields) != 6 or fields[0] != '0' or fields[-1] != row['full_md5']:
                raise ValueError('Official framemd5 and streamed pixels disagree')
            verified += 1
        if next(rows, None) is not None or verified != expected_frames or count != expected_frames:
            raise ValueError('Full decoded frame/hash count mismatch')
    result = freshness.finish()
    result.update({'full_decode': True, 'frames': count, 'official_framemd5_verified_frames': verified,
                   'nominal_last_frame_duration_s': 1 / fps, 'freeze_review_seconds': freeze_seconds,
                   'artifacts': {p.name: sha(p) for p in (hashes_path, csv_path)}})
    result['status'] = 'PASS' if all(q['meaningful']['changing_pairs'] > 0
        and q['meaningful']['longest_constant_run']['seconds'] < freeze_seconds for q in result['quadrants']) else 'FAIL'
    result['limits'] = ['All decoded frames examined, but gray downscaling and a 144-pixel probe per quadrant lose detail.',
        'Exact hashes can change due to codec noise; meaningful-change runs are reported separately.',
        '30 fps fixture on a 60 fps canvas legitimately repeats frames; no duplicate frames were removed.']
    return result


def audio_pcm(tools, passes, path, directory, duration):
    windows_path, tones_path = directory / 'pcm-100ms.jsonl', directory / 'tone-1s.jsonl'
    selected = set(range(2, max(3, int(duration) - 1), 60)) | {max(2, int(duration) // 2), max(2, int(duration) - 2)}
    with windows_path.open('x') as windows, tones_path.open('x') as tones:
        emit = lambda file: lambda value: file.write(json.dumps(value, separators=(',', ':')) + '\n')
        statistics = PCMStats(emit(windows), emit(tones), tone_seconds=selected)
        def consume(stdout):
            while block := stdout.read(48000 * 2 * 4):
                statistics.feed(block)
            return statistics.finish()
        result = passes.run('audio-full-decode', [tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror',
            '-threads', '2', '-i', path, '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le', '-f', 'f32le', 'pipe:1'], consume)
    expected = .0630957344 * 10 ** (-12 / 20)
    differences = [20 * math.log10(max(channel['440'], 1e-20) / expected)
                   for window in result['tone_windows'] for channel in window['channels']]
    result['controlled_tone'] = {'frequency_hz': 440, 'source_peak': .0630957344,
        'gain_db': -12, 'expected_peak': expected, 'measured_peak_error_db': differences,
        'review_tolerance_db': 2., 'selected_decoded_second_offsets': sorted(selected),
        'limit': 'One-second spectral windows, not continuous pitch tracking or A/V synchronization'}
    result['gates'] = {'full_decode': True, 'decoded_samples_present': result['frames_per_channel'] > 0,
        'no_nonfinite_samples': all(c['nonfinite_samples'] == 0 for c in result['channel_statistics']),
        'no_clipping': all(c['samples_abs_ge_0_999'] == 0 for c in result['channel_statistics']),
        'continuous_controlled_tone': all(c['full_windows_below_minus80_dbfs'] == 0 for c in result['channel_statistics']),
        'tone_windows_within_2db_of_nominal': bool(differences) and all(abs(value) <= 2 for value in differences)}
    result['status'] = 'PASS' if all(result['gates'].values()) else 'FAIL'
    result['artifacts'] = {p.name: sha(p) for p in (windows_path, tones_path)}
    return result


def correlate(run, medium, first, pts):
    paths = [run / (medium['target'] + suffix) for suffix in ('-start-packets.json', '-final-packets.json')]
    if not all(path.is_file() for path in paths):
        return {'status': 'INCONCLUSIVE', 'reason': 'initial_or_final_trace_missing'}
    beginning, ending = [json.loads(path.read_text()) for path in paths]
    initial, final = beginning['packet_trace'], ending['packet_trace']
    result = {'trace_hashes': {path.name: sha(path) for path in paths},
              'native_final': ending.get('output'), 'origin_proof': packet_origin_proof(initial, first)}
    if any(value.get('output', {}).get('attempt_id') != medium['attempt_id'] for value in (beginning, ending)):
        return {**result, 'status': 'INCONCLUSIVE', 'reason': 'trace_attempt_mismatch'}
    if result['origin_proof']['status'] != 'MATCHED_METADATA_PREFIX':
        return {**result, 'status': 'INCONCLUSIVE', 'reason': 'initial_packet_origin_unproven'}
    candidates, counts = tail_candidates(initial, final, first, pts)
    # Existing classifier is unchanged. It receives the actual first packet,
    # all tolerance candidates and exact nearest PTS neighbors for every tail entry.
    from verify_h14_output_integrity import correlate_tail
    result['classification'] = correlate_tail(initial, final, candidates)
    result['candidate_counts'] = counts
    result['candidate_scope'] = 'first packets plus exact nearest/tolerance neighbors derived from all actual PTS'
    result.update(tail_status_with_ambiguity(result['classification']['status'], counts))
    return result


def plan():
    return {'status': 'NOT_RUN', 'requires': ['completed report', 'both output barriers quiescent',
        'operator-approved CPU window', 'new output directory', 'portable B3 tools', 'test Python with Pillow for existing correlator'],
        'command': 'TEST_PYTHON scripts/analyze_h14_soak.py --postrun-approved --run RUN_DIRECTORY --bundle /absolute/Motive.app --capture-support-commit ceb40ce --output NEW_DIRECTORY',
        'passes_per_medium': ['ffprobe streams', 'ffprobe all decoded frames', 'ffprobe all packets',
            'full video decode: 128x72 gray + framemd5 + four independent quadrant hash/motion runs',
            'full stereo PCM decode: <=1-second reads, 100ms RMS/peak/silence and selected 1s spectral windows'],
        'defaults': {'timeout_per_pass_seconds': 1200, 'freeze_review_seconds': 1.,
            'video_gap_s': '1.5/canvas_fps; no tail removal', 'aac_gap_s': .023,
            'silence_rms_dbfs': -80, 'clipping_absolute_sample': .999, 'tone_amplitude_review_db': 2},
        'limits': ['No live source/app/IPC access; never rewrites source reports or media.',
            'A/V sync NOT_EVALUATED: continuous tone and silent video have no shared identifiable event.',
            'Native encoded/dispatched/output counters remain separate from actual packet/frame counts.',
            'Original FAIL/PARTIAL and unproven delivery are retained; media checks are not beta acceptance.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--postrun-approved', action='store_true')
    parser.add_argument('--run', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--capture-support-commit', help='Operator-declared source commit at capture process start; never inferred from current HEAD')
    parser.add_argument('--timeout-per-pass', type=int, default=1200)
    parser.add_argument('--freeze-seconds', type=float, default=1.)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    if not args.postrun_approved or not all((args.run, args.bundle, args.output)):
        parser.error('Explicit --postrun-approved, --run, --bundle and new --output are required')
    if not 30 <= args.timeout_per_pass <= 7200 or not math.isfinite(args.freeze_seconds) or not .1 <= args.freeze_seconds <= 5:
        parser.error('Invalid bounded timeout/freeze review threshold')
    if args.capture_support_commit and not re.fullmatch(r'[0-9a-f]{7,40}', args.capture_support_commit):
        parser.error('Capture support commit must be a hexadecimal commit ID')
    if importlib.util.find_spec('PIL') is None:
        parser.error('Existing correlator imports Pillow; use the already-installed test Python, without installing packages')
    run, out = args.run.resolve(strict=True), args.output.resolve()
    source = run / 'report.json'
    original = json.loads(source.read_text())
    if (not original.get('measurement_completed') or 'final' not in original
            or any(slot['native_busy'] for slot in original['final']['outputs'].values())):
        parser.error('Run is not finalized with quiescent outputs; no media tool was started')
    if original['plan']['mode'] != 'dual-soak' or {m['target'] for m in original['media']} != {'recording', 'streaming'} or len(original['media']) != 2:
        parser.error('Expected the two-media controlled dual-soak report')
    paths = verification_paths(ROOT, environ={'MOTIVE_TEST_APP': str(args.bundle.resolve()),
        'MOTIVE_TEST_DATA_ROOT': str(Path.home() / 'Library/Application Support/local.motive.studio'),
        'MOTIVE_TEST_RECORDINGS_ROOT': str(Path.home() / 'Movies/Motive')})
    if sha(paths.app_executable) != original['app_sha256']:
        parser.error('Specified bundle differs from the measured executable')
    tools = {name: (paths.app_bundle / 'Contents/MacOS' / name).resolve(strict=True) for name in ('ffmpeg', 'ffprobe')}
    if any(not path.is_relative_to(paths.app_bundle) or not os.access(path, os.X_OK) for path in tools.values()):
        parser.error('Media tools must be executable and contained in the same portable bundle')
    out.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'status': 'PARTIAL', 'source_status': original['status'],
        'source_report_sha256': sha(source), 'analyzer_sha256': sha(Path(__file__)),
        'helper_sha256': sha(ROOT / 'scripts/h14_soak_helpers.py'),
        'app_sha256': original['app_sha256'], 'tools': {k: {'path': str(v), 'sha256': sha(v)} for k, v in tools.items()},
        'media': [], 'audio_video_sync': 'NOT_EVALUATED', 'beta_acceptance': 'NOT_EVALUATED',
        'full_output_delivery': 'NOT_INFERRED_FROM_NATIVE_COUNTERS', 'plan': plan(),
        'analysis_python': {'executable': sys.executable, 'version': sys.version},
        'media_tool_environment': {'PATH': '/usr/bin:/bin', 'DYLD_overrides': False},
        'capture_support_provenance': {'declared_start_commit': args.capture_support_commit,
            'reported_harness_sha256': original['instrument_sha256'],
            'basis': 'Operator declaration plus repository source hashes; not an introspection of the terminated Python interpreter',
            'limit': 'Already-imported capture modules were not reloaded when later harness path changes were committed.'}}
    try:
        if args.capture_support_commit:
            hashes = {}
            for name in ('verify_h14_memory.py', 'verify_h13_outputs.py', 'h7_support.py', 'verify_h11_visuals.py'):
                value = subprocess.check_output(['/usr/bin/git', 'show', args.capture_support_commit + ':scripts/' + name], cwd=ROOT)
                hashes[name] = hashlib.sha256(value).hexdigest()
            result['capture_support_provenance']['source_hashes_at_start_commit'] = hashes
            if hashes['verify_h14_memory.py'] != original['instrument_sha256']:
                raise ValueError('Declared capture commit does not match the recorded harness hash')
        memory = analyze_memory(run)
        save(out / 'memory-analysis.json', memory)
        result['memory_derivation_sha256'] = sha(out / 'memory-analysis.json')
        for medium in original['media']:
            row = {'target': medium['target'], 'status': 'FAIL', 'attempt_id': medium['attempt_id'],
                   'status_scope': 'Decoded format, cadence, pixels and PCM controls only; delivery and A/V are separate'}
            result['media'].append(row)
            directory = out / medium['target']
            directory.mkdir()
            try:
                path = Path(medium['path']).resolve(strict=True)
                before = fingerprint(path)
                row.update(path=str(path), bytes=path.stat().st_size, sha256=sha(path))
                if row['sha256'] != medium['sha256'] or row['bytes'] != medium['bytes']:
                    raise ValueError('Finalized media hash/size changed')
                passes = Passes(directory, args.timeout_per_pass, row)
                fps = original['plan']['fps']
                row['metadata'], first, pts = probe_media(tools, passes, path, directory, original['plan'])
                row['pixels'] = video_pixels(tools, passes, path, directory, fps,
                    row['metadata']['frames']['count'], args.freeze_seconds)
                duration = float(row['metadata']['probe']['format']['duration'])
                row['pcm'] = audio_pcm(tools, passes, path, directory, duration)
                row['delivery'] = correlate(run, medium, first, pts)
                native = row['delivery'].get('native_final') or {}
                count = row['metadata']['frames']['count']
                row['raw_counter_differences'] = {key + '_minus_decoded_frames': native['stats'][key] - count
                    for key in ('output_frames', 'encoded_frames') if key in native.get('stats', {})}
                frame_times = row['metadata']['frames']
                packet_times = row['metadata']['packet_timelines']
                row['gates'] = {
                    'all_frame_pts_present_and_increasing': not frame_times['missing'] and not frame_times['non_increasing'],
                    'all_frame_gaps_within_1_5_periods': not frame_times['gaps_over_limit'],
                    'all_packet_pts_dts_present_and_increasing': all(not t['missing'] and not t['non_increasing']
                        for values in packet_times.values() for t in values.values()),
                    'continuous_aac': not packet_times['audio']['pts']['gaps_over_limit'],
                    'reordering_disabled_no_b_frames': row['metadata']['frame_types'].get('B', 0) == 0,
                    'all_quadrants_content_changes': row['pixels']['status'] == 'PASS',
                    'pcm_controls': row['pcm']['status'] == 'PASS',
                    'requested_soak_span': frame_times['last_s'] - frame_times['first_s'] + 1 / fps >= original['plan']['soak_seconds'],
                    'media_unchanged': fingerprint(path) == before}
                row['status'] = 'PASS' if all(row['gates'].values()) else 'FAIL'
            except Exception as error:
                row.update(error=repr(error), traceback=traceback.format_exc())
            save(out / 'analysis.json', result)
        if sha(source) != result['source_report_sha256']:
            raise ValueError('Source report changed during analysis')
        if original['status'] == 'FAIL' or any(row['status'] == 'FAIL' or row.get('delivery', {}).get('status') == 'FAIL' for row in result['media']):
            result['status'] = 'FAIL'
        result['limits'] = plan()['limits']
    except Exception as error:
        result.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    save(out / 'analysis.json', result)
    print(json.dumps({'status': result['status'], 'output': str(out),
                      'media': [{'target': row['target'], 'status': row['status']} for row in result['media']]}))
    return int(result['status'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
