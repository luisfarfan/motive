#!/usr/bin/env python3
"""Serial H13 performance / encoder-tail evidence on an existing signed app.

The caller MUST already own the shared physical-device/bundle lock. --lock-held
is that explicit attestation; this script does not invent a second lock, launch
or build an app, change privacy settings, or transmit outside loopback.

performance: ABBA = single MKV / dual MKV+RTMP / dual / single, identical profile,
fixture and steady duration. --fps accepts 30 and/or 60. --fixture video adds one
owned looping H11 1080p clip, generated/imported BEFORE any measured phase.
tail: independent ABBA = reordering on/off/off/on, single MKV, VT then x264,
6.10/6.10/6.33/6.33 seconds. Do not conflate these two independent variables.

Native queries run at 2 Hz; the H12 libproc Sampler runs independently at 20 Hz.
All media decoding runs AFTER sampling/cleanup. CPU/RSS describe Motive, not the
receiver/mux helper or the whole host. No CPU/RSS pass budget is invented.
Functional acceptance retains the explicit historical <150 ms final PTS limit;
strict all-frame cadence is a SEPARATE reported gate, never hidden by that limit.
This is a new, unexecuted instrument until a retained report proves otherwise.

Requires disposable pattern/legacy-overlay state, empty mixer, healthy idle
outputs and no credentials. No store is saved. Cleanup removes owned fixture
objects and restores settings; graph ID counters/project v5 migration remain.
If no endpoint was configured, the test loopback endpoint remains (no unset API).
"""

import argparse
import array
import json
import math
import pathlib
import socket
import statistics
import subprocess
import time
import traceback

from h7_support import process_sample, profile
from verify_h11_visuals import import_asset
from verify_h12_performance import Sampler
from verify_h13_outputs import (APP, ROOT, DEFAULT_VIDEO, TARGETS, Client,
                                Receiver, check, layer, run, sha, slots, write_json)


class BenchClient(Client):
    def wait(self, predicate, timeout=50):
        deadline = time.monotonic() + timeout
        while True:
            state = self.state()
            if predicate(state):
                return state
            check(time.monotonic() < deadline, 'native state timeout', state=state)
            time.sleep(.1)


def percentile(values, quantile):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, math.ceil(quantile*len(ordered))-1)]


def process_interval(sampler, lo, hi):
    rows = [r for r in sampler.rows if lo <= r['monotonic'] <= hi]
    check(len(rows) >= 2, 'at least two process samples', lo=lo, hi=hi)
    cpu = [r['cpu_percent'] for r in rows if r['cpu_percent'] is not None]
    gaps = [b['monotonic']-a['monotonic'] for a, b in zip(rows, rows[1:])]
    return {**sampler.interval(lo, hi),
            'cpu_p95_percent': percentile(cpu, .95), 'cpu_max_percent': max(cpu),
            'cpu_mean_percent': 100*(rows[-1]['cpu_total_s']-rows[0]['cpu_total_s']) /
                                (rows[-1]['monotonic']-rows[0]['monotonic']),
            'cpu_seconds': rows[-1]['cpu_total_s']-rows[0]['cpu_total_s'],
            'rss_p95_mib': percentile([r['rss_mib'] for r in rows], .95),
            'threads_max': max(r['threads'] for r in rows),
            'sampling_interval_p95_s': percentile(gaps, .95),
            'sampling_interval_max_s': max(gaps),
            'observed_hz': (len(rows)-1)/(rows[-1]['monotonic']-rows[0]['monotonic'])}


def native_delta(before, after):
    shared = {key: after['stats'][key]-before['stats'][key] for key in
              ('rendered_frames', 'lagged_frames', 'video_skipped_frames',
               'preview_copies', 'preview_busy_drops')}
    targets = {}
    for target in TARGETS:
        a, b = slots(before)[target], slots(after)[target]
        check(a['attempt_id'] == b['attempt_id'], 'stable attempt in measured interval', target=target)
        targets[target] = {key: None if a['stats'][key] is None or b['stats'][key] is None
                          else b['stats'][key]-a['stats'][key] for key in a['stats']}
        targets[target]['active_duration_ms'] = b['active_duration_ms']-a['active_duration_ms']
    return {'shared': shared, 'outputs': targets}


def analyze_media(record, directory):
    """Keep complete PTS/DTS evidence, including every final gap and B frame."""
    path = pathlib.Path(record['path'])
    result = {'path': str(path), 'functional_ok': False, 'sha256': sha(path),
              'bytes': path.stat().st_size}
    record['analysis'] = result
    fps = record['fps']
    probe = json.loads(run('ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                           '-show_format', '-of', 'json', str(path), timeout=600))
    result['probe'] = probe
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    check((video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) ==
          ('h264', 1920, 1080, f'{fps}/1'), 'H264 1080p requested FPS', stream=video)
    check((audio['codec_name'], audio['sample_rate'], audio['channels']) ==
          ('aac', '48000', 2), 'AAC stereo 48k', stream=audio)
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                              '-f', 'null', '-'], capture_output=True, timeout=900)
    result['full_decode'] = {'returncode': decoded.returncode, 'stderr': decoded.stderr.decode()}
    check(decoded.returncode == 0 and not decoded.stderr, 'full media decode', result=result['full_decode'])
    frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time,pkt_dts_time,duration_time,pkt_duration_time,key_frame,pict_type',
        '-of', 'json', str(path), timeout=600))['frames']
    packets = json.loads(run('ffprobe', '-v', 'error', '-show_packets', '-show_entries',
        'packet=codec_type,pts_time,dts_time,duration_time,flags', '-of', 'json', str(path), timeout=600))['packets']
    timeline = directory / (record['label'] + '-timestamps.json')
    write_json(timeline, {'frames': frames, 'packets': packets})
    result['timestamps'] = {'path': str(timeline), 'sha256': sha(timeline)}
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    check(len(pts) >= record['seconds']*fps*.85, 'decoded frame count', frames=len(pts))
    gaps = [b-a for a, b in zip(pts, pts[1:])]
    limit = 1.5/fps
    result['video'] = {'frames': len(pts), 'first_pts': pts[0], 'last_pts': pts[-1],
        'max_interior_gap_s': max(gaps[:-4]), 'max_gap_s': max(gaps), 'last_four_gaps_s': gaps[-4:],
        'all_gaps_over_cadence_limit': [{'frame': i+1, 'seconds': gap} for i, gap in enumerate(gaps) if gap > limit],
        'strict_cadence_limit_s': limit, 'b_frames': sum(f.get('pict_type') == 'B' for f in frames),
        'last_second_frames': [f for f in frames if float(f['best_effort_timestamp_time']) >= pts[-1]-1]}
    result['gates'] = {'positive_video_pts': min(gaps) > 0,
        'interior_cadence': max(gaps[:-4]) <= limit,
        'historical_tail_below_150ms': max(gaps) < .15,
        'strict_all_frame_cadence': max(gaps) <= limit,
        'reordering_disabled_has_no_b_frames': record['reordering'] or result['video']['b_frames'] == 0}
    ends = {}
    result['packet_timelines'] = {}
    for kind in ('video', 'audio'):
        values = [p for p in packets if p['codec_type'] == kind]
        missing_pts = [i for i, p in enumerate(values) if 'pts_time' not in p]
        missing_dts = [i for i, p in enumerate(values) if 'dts_time' not in p]
        depth = video.get('has_b_frames', 0) if kind == 'video' else 0
        check(type(depth) is int and depth >= 0, 'reported reorder depth', depth=depth)
        prefix_only = missing_dts == list(range(len(missing_dts)))
        summary = {'packets': len(values), 'missing_pts_packet_indices': missing_pts,
            'missing_dts_packet_indices': missing_dts, 'reported_reorder_depth': depth,
            'missing_dts_is_initial_prefix': prefix_only, 'inferred_dts_count': 0,
            'known_dts_count': len(values)-len(missing_dts)}
        result['packet_timelines'][kind] = summary
        check(len(values) >= 2 and not missing_pts, 'complete packet PTS', kind=kind, timeline=summary)
        packet_pts = [float(p['pts_time']) for p in values]
        check(all(math.isfinite(p) for p in packet_pts), 'finite packet PTS', kind=kind)
        # Matroska can omit only the decoder's initial reordering prefix. The
        # actual stream depth bounds the exception; no DTS is synthesized and
        # missing interior/tail DTS (or any missing audio DTS) still fails.
        matroska = 'matroska' in probe.get('format', {}).get('format_name', '').split(',')
        allowed_prefix = (kind == 'video' and matroska and depth > 0 and
                          result['video']['b_frames'] > 0 and prefix_only and len(missing_dts) <= depth)
        check(not missing_dts or allowed_prefix, 'DTS absent only in bounded initial reorder prefix',
              kind=kind, timeline=summary)
        known_dts = [(i, float(p['dts_time'])) for i, p in enumerate(values) if 'dts_time' in p]
        check(len(known_dts) >= 2 and all(math.isfinite(d) for _, d in known_dts),
              'finite known packet DTS', kind=kind, timeline=summary)
        dts = [d for _, d in known_dts]
        summary['known_dts_strictly_increasing'] = all(b > a for a, b in zip(dts, dts[1:]))
        check(summary['known_dts_strictly_increasing'], 'monotonic known packet DTS', kind=kind)
        fallback = 1/fps if kind == 'video' else 1024/48000
        ends[kind] = max(float(p['pts_time']) + float(p.get('duration_time', fallback)) for p in values)
        summary.update(first_pts=min(packet_pts), first_dts=dts[0] if not missing_dts else None,
            first_known_dts_packet_index=known_dts[0][0], first_known_dts=dts[0], last_dts=dts[-1],
            presentation_end_s=ends[kind], durations_inferred=sum('duration_time' not in p for p in values))
        if kind == 'audio':
            audio_pts = [float(p['pts_time']) for p in values]
            audio_gaps = [b-a for a, b in zip(audio_pts, audio_pts[1:])]
            result['packet_timelines'][kind]['max_gap_s'] = max(audio_gaps)
            result['gates']['continuous_aac'] = min(audio_gaps) > 0 and max(audio_gaps) <= .023
    # Compare one actual channel with its native per-channel meter. Generic
    # stereo -> mono downmix sums these identical channels with +3.01 dB gain.
    pcm = array.array('f', run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn',
                              '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-', timeout=600))
    rms = [math.sqrt(sum(x*x for x in pcm[i:i+960])/960)
           for i in range(0, len(pcm)-959, 960)][5:-5]
    peak = max(abs(x) for x in pcm)
    expected = 10**(-30/20)/math.sqrt(2)  # -24 dBFS peak tone, input gain -6 dB.
    errors_db = [20*math.log10(max(v, 1e-12)/expected) for v in rms]
    result['audio'] = {'decoded_channel': 'left; pan=mono|c0=c0; no summing or normalization',
        'decoded_samples': len(pcm), 'duration_s': len(pcm)/48000,
        'rms_min': min(rms), 'rms_max': max(rms), 'peak': peak,
        'expected_channel_rms': expected, 'max_abs_rms_error_db': max(map(abs, errors_db)),
        'out_of_range_blocks': [{'start_seconds': (i+5)*.02, 'error_db': e}
                               for i, e in enumerate(errors_db) if abs(e) >= 1],
        'packet_av_end_delta_s': ends['audio']-ends['video'],
        'last_100ms_rms': math.sqrt(sum(x*x for x in pcm[-4800:])/4800),
        'end_note': 'Packet durations included; AAC priming/padding mean this is not a drift measurement.'}
    result['gates']['continuous_unclipped_tone'] = (
        peak < .1 and all(abs(e) < 1 for e in errors_db))
    # Preserve a moving pattern strip even with the optional H11 clip at top right.
    strip = run('ffmpeg', '-nostdin', '-v', 'error', '-ss', '0.3', '-i', str(path), '-t', '1',
        '-vf', 'scale=960:540:flags=area,format=rgb24,crop=960:1:0:270',
        '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-', timeout=600)
    centers = []
    for i in range(0, len(strip), 960*3):
        row = strip[i:i+960*3]
        white = [x for x in range(960) if min(row[x*3:x*3+3]) > 215]
        check(len(white) >= 60, 'controlled pattern square visible')
        centers.append(statistics.mean(white))
    advances = sum(abs(b-a) > .3 for a, b in zip(centers, centers[1:]))
    result['motion'] = {'centroids': centers, 'advances': advances}
    result['gates']['real_pattern_motion'] = len(centers) >= fps*.9 and advances >= .9*(len(centers)-1)
    # Keep a decoded last-second frame checksum list, plus the full original clip.
    tail = directory / (record['label'] + '-last-second.framemd5')
    tail.write_bytes(run('ffmpeg', '-nostdin', '-v', 'error', '-sseof', '-1', '-i', str(path),
                         '-an', '-f', 'framemd5', '-', timeout=600))
    result['tail_frame_checksums'] = str(tail)
    required = {k: v for k, v in result['gates'].items() if k != 'strict_all_frame_cadence'}
    check(all(required.values()), 'functional media gates', gates=required)
    result['functional_ok'] = True


class Benchmark:
    def __init__(self, args, directory, report):
        self.args, self.directory, self.report = args, directory, report
        self.c = self.initial = self.sampler = None
        self.changed = False
        self.scene = self.tone = self.asset = self.video_source = None
        self.owned_asset = False
        self.inbox = None
        self.profiles, self.receivers = {}, []
        self.observations = (directory / 'observations.jsonl').open('w')

    def snapshot(self):
        state = self.c.state()
        self.observations.write(json.dumps({'monotonic': time.monotonic(), 'state': state})+'\n')
        self.observations.flush()
        check(state['pid'] == self.initial['pid'], 'same running owner')
        check(not state['issues'] and not state['recovery_required'], 'healthy production', state=state)
        check(state['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0, 'no native clipping')
        return state

    def open(self):
        check(APP.is_file(), 'existing bundle required')
        signature = subprocess.run(['codesign', '--verify', '--verbose=2', str(APP.parents[2])],
                                   capture_output=True, text=True, timeout=60)
        self.report['codesign_verify'] = vars(signature)
        check(signature.returncode == 0, 'signed bundle verification', stderr=signature.stderr)
        strict = subprocess.run(['codesign', '--verify', '--strict', str(APP.parents[2])],
                                capture_output=True, text=True, timeout=60)
        self.report['codesign_strict'] = {**vars(strict), 'acceptance_gate': False,
            'note': 'Development bundle may retain an absolute Frameworks symlink into .deps/OBS.app; this is not a portable/notarized bundle test.'}
        self.report.update(app=str(APP), app_sha256=sha(APP), script_sha256=sha(__file__),
            commit=run('git', '-C', str(ROOT), 'rev-parse', 'HEAD').decode().strip(),
            git_status=run('git', '-C', str(ROOT), 'status', '--short').decode(),
            ffmpeg=run('ffmpeg', '-version').decode().splitlines()[0],
            helper_sha256={name: sha(ROOT/'scripts'/name) for name in
                ('h7_support.py', 'verify_h12_performance.py', 'verify_h13_outputs.py')})
        self.c = BenchClient(self.directory)
        self.initial = self.c.state()
        self.report['initial'] = self.initial
        actual = pathlib.Path(run('ps', '-p', str(self.initial['pid']), '-o', 'comm=').decode().strip())
        check(actual.resolve() == APP.resolve(), 'owner belongs to signed checkout', actual=str(actual))
        check(all(not s['native_busy'] and not s['recovery_required'] for s in slots(self.initial).values()),
              'healthy idle outputs required')
        check(not self.initial['issues'] and not self.initial['recovery_required'], 'healthy initial production')
        check(not self.initial['audio_mixer']['store']['inputs'], 'empty controlled mixer required')
        check(self.initial['output_configuration']['credential_ref'] is None, 'no credential fixture')
        graph = self.initial['project']['graph']
        check(all(s['spec']['kind'] in ('pattern', 'overlay') and s.get('overlay') is None
                  for s in graph['sources']), 'only controlled pattern/legacy sources')
        check(not self.initial['overlays']['runtime']['animations']['busy'] and
              self.initial['transition']['phase'] not in ('preparing', 'running'), 'quiescent scene')
        self.report['stores_before'] = self.store_hashes()
        profiles = self.c.call('output_profiles')['store']['profiles']
        check(len(profiles) <= 14, 'room for temporary profiles')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.changed = True
        self.c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        self.c.call('set_variant', variant='horizontal')
        self.c.call('configure_stream', endpoint={'transport': 'rtmp', 'port': self.port})
        stamp = str(time.time_ns())
        for target in TARGETS:
            value = profile(id='h13-perf-'+target+'-'+stamp, encoder=self.args.encoder,
                            bitrate=self.args.bitrate, reorder=self.args.reordering == 'on')
            self.c.call('upsert_output_profile', profile=value)
            self.profiles[target] = value
            self.c.call('select_output_profile', target=target, profile_id=value['id'])
        state = self.c.call('add_audio_input', name='H13 performance owned tone', source={'kind': 'tone'})['state']
        self.tone = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
        self.c.call('set_audio_gain', input_id=self.tone, gain_db=-6)
        self.scene = self.c.call('create_scene', name='H13 performance controlled')['state']['project']['graph']['active_scene']
        pattern = next(s['id'] for s in graph['sources'] if s['spec']['kind'] == 'pattern')
        state = self.c.call('add_layer', scene_id=self.scene, source_id=pattern)['state']
        self.transform(layer(state, self.scene, pattern)['id'], 0, 0, 960, 540, 0)
        legacy = next((s['id'] for s in graph['sources'] if s['spec']['kind'] == 'overlay'), None)
        if legacy:
            state = self.c.call('add_layer', scene_id=self.scene, source_id=legacy)['state']
            self.transform(layer(state, self.scene, legacy)['id'], 32, 436, 320, 72, 1)
        if self.args.fixture == 'video':
            fixture = self.directory / ('owned-1080p60-'+stamp+'.mp4')
            run('ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=1920x1080:rate=60', '-t', '6', '-c:v', 'libx264', '-preset',
                'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', str(fixture), timeout=180)
            known = {a['id'] for a in self.c.call('list_assets')['result']['assets']}
            self.inbox = ROOT/'var/imports'/fixture.name
            self.asset = import_asset(self.c, fixture)['asset']
            self.owned_asset = self.asset['id'] not in known
            created = self.c.call('create_overlay', scene_id=self.scene, name='H13 owned H11 video',
                definition={'kind': 'video', 'asset_id': self.asset['id'], 'opacity': 1., 'looping': True})
            self.video_source = created['result']['source_id']
            self.transform(layer(created['state'], self.scene, self.video_source)['id'], 600, 24, 320, 180, 2)
            self.report['fixture'] = {'path': str(fixture), 'sha256': sha(fixture), 'asset': self.asset}
        self.c.wait(lambda s: not s['issues'])
        # All fixture generation/import work above is intentionally outside samples.
        self.sampler = Sampler(self.initial['pid'])

    @staticmethod
    def store_hashes():
        return {name: sha(ROOT/'var'/name) if (ROOT/'var'/name).exists() else None for name in
                ('project.json', 'audio-mixer.json', 'output-profiles.json')}

    def transform(self, layer_id, x, y, width, height, order):
        self.c.call('set_transform', scene_id=self.scene, layer_id=layer_id, variant='horizontal',
                    transform=dict(x=x, y=y, width=width, height=height, visible=True, order=order))

    def phase(self, label, seconds, active):
        ps_before, _ = process_sample(self.initial['pid'])
        lo = time.monotonic()
        before = self.snapshot()
        snapshots = [before]
        deadline = lo + seconds
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(.5, remaining))
            state = self.snapshot()
            check({t for t, s in slots(state).items() if s['native_busy']} == set(active),
                  'exact active targets during measured interval', expected=active, outputs=state['outputs'])
            check(all(slots(state)[t]['phase'] == 'active' for t in active), 'outputs remain active')
            snapshots.append(state)
        hi = time.monotonic()
        ps_after, _ = process_sample(self.initial['pid'])
        metrics = process_interval(self.sampler, lo, hi)
        check(abs(metrics['cpu_seconds']-(ps_after-ps_before)) < .3,
              'libproc CPU agrees with ps within 0.3s', libproc=metrics['cpu_seconds'], ps=ps_after-ps_before)
        check(metrics['observed_hz'] >= 15 and metrics['sampling_interval_max_s'] < .25,
              '20Hz sampler coverage', sampling=metrics)
        delta = native_delta(before, snapshots[-1])
        elapsed = hi-lo
        check(delta['shared']['lagged_frames'] == 0 and delta['shared']['video_skipped_frames'] == 0,
              'no native render lag/skips', delta=delta)
        check(delta['shared']['rendered_frames'] >= elapsed*before['fps']*.9,
              'native render clock advances', delta=delta, seconds=elapsed)
        for target in active:
            check(delta['outputs'][target]['output_dropped_frames'] == 0,
                  'no output drops', target=target, delta=delta)
        result = {'label': label, 'lo': lo, 'hi': hi, 'seconds': elapsed, 'all': metrics,
                  'steady_after_2s': process_interval(self.sampler, lo+2, hi),
                  'cpu_seconds_ps': ps_after-ps_before, 'native_delta': delta,
                  'preview_copies_per_s': delta['shared']['preview_copies']/elapsed,
                  'preview_bgra_bytes_per_s': delta['shared']['preview_copies']*1920*1080*4/elapsed,
                  'preview_note': 'One counted BGRA copy; excludes other copies/uploads, not total bandwidth.',
                  'before': before, 'after': snapshots[-1]}
        if self.video_source:
            videos = [next(v for v in s['overlays']['runtime']['sources'] if v['id'] == self.video_source)
                      for s in snapshots]
            check(all(v['child_instances_created'] == 1 and v['audio_mixers'] == 0 for v in videos),
                  'one silent native media child')
            result['owned_video'] = {'media_times_ms': [v['media_time_ms'] for v in videos],
                                    'instance_ids': sorted({v['instance_id'] for v in videos})}
        self.report['phases'].append(result)
        return result

    def trial(self, label, fps, dual, encoder, reorder, seconds):
        check(sha(APP) == self.report['app_sha256'], 'bundle unchanged before trial')
        self.c.call('configure_video', video={'version': 1, 'resolution': 'full_hd1080',
                                             'fps': fps, 'coordinate_space': 'design960'})
        for target in TARGETS:
            value = {**self.profiles[target], 'encoder': encoder, 'frame_reordering': reorder}
            self.c.call('upsert_output_profile', profile=value)
        baseline = self.phase(label+'-idle-baseline', self.args.baseline_seconds, [])
        receiver = None
        if dual:
            receiver = Receiver(self.directory, label+'-rtmp', self.port)
            self.receivers.append(receiver)
        start_lo = time.monotonic()
        active = list(TARGETS) if dual else ['recording']
        records = []
        for target in active:
            response = self.c.call('start_output', target=target)
            item = {'label': label+'-'+target, 'target': target, 'trial': label, 'fps': fps,
                    'seconds': seconds, 'reordering': reorder, 'encoder': encoder,
                    'path': slots(response['state'])[target]['path'] if target == 'recording' else str(receiver.path)}
            records.append(item)
            # Preserve each accepted output even if starting the second fails.
            self.report['media'].append(item)
        started = self.c.wait(lambda s: all(slots(s)[t]['phase'] == 'active' for t in active))
        start_hi = time.monotonic()
        for target in active:
            expected_profile = {**self.profiles[target], 'encoder': encoder, 'frame_reordering': reorder}
            check(slots(started)[target]['profile'] == expected_profile,
                  'same explicit profile in each comparison arm', target=target)
            check(slots(started)[target]['video'] == {'width': 1920, 'height': 1080, 'fps': fps},
                  'actual native video snapshot', target=target)
            effective = slots(started)[target]['encoding']
            check(effective['selected_id'] is not None, 'effective encoder reported', target=target)
            if encoder == 'videotoolbox':
                check(effective['selected_hardware'] and effective['fallback_reason'] is None,
                      'explicit VT has no fallback', target=target, encoding=effective)
            if encoder == 'x264':
                check(effective['selected_id'] == 'obs_x264', 'explicit x264', target=target)
        measured = self.phase(label+'-active', seconds, active)
        stop_lo = time.monotonic()
        self.c.call('cancel_all_outputs' if dual else 'stop_output_target',
                    **({} if dual else {'target': 'recording'}))
        stop_ack = time.monotonic()
        ended = self.c.wait(lambda s: all(not v['native_busy'] for v in slots(s).values()))
        stop_hi = time.monotonic()
        check(all(not v['recovery_required'] for v in slots(ended).values()), 'clean finalization')
        if receiver:
            receiver_code = receiver.wait()
        else:
            receiver_code = None
        for item in records:
            item['native_final'] = slots(ended)[item['target']]
        # Include start/drain peaks, then sample a separate settled idle phase.
        time.sleep(.1)
        settled = self.phase(label+'-after-stop', self.args.baseline_seconds, [])
        entry = {'label': label, 'fps': fps, 'dual': dual, 'encoder': encoder, 'reordering': reorder,
            'requested_seconds': seconds, 'baseline': baseline, 'active': measured, 'settled': settled,
            'start_to_active_s': start_hi-start_lo, 'stop_ack_s': stop_ack-stop_lo,
            'stop_to_barrier_s': stop_hi-stop_lo, 'start_and_drain_process': process_interval(self.sampler, start_lo, stop_hi+.1),
            'receiver_returncode': receiver_code, 'started': started, 'ended': ended}
        for phase, before, after in (
            ('start_to_active', baseline['after'], started),
            ('stop_to_barrier', measured['after'], ended),
            ('complete_output_lifecycle', baseline['after'], ended),
        ):
            entry[phase+'_shared_delta'] = {key: after['stats'][key]-before['stats'][key]
                for key in ('rendered_frames', 'lagged_frames', 'video_skipped_frames',
                            'preview_copies', 'preview_busy_drops')}
        self.report['trials'].append(entry)
        write_json(self.directory/'report.json', self.report)
        # Startup/drain deltas are not erased by starting the steady timer later.
        lifecycle = entry['complete_output_lifecycle_shared_delta']
        check(lifecycle['lagged_frames'] == 0 and lifecycle['video_skipped_frames'] == 0,
              'no render lag/skips including startup and drain', delta=lifecycle)
        print(label, measured['steady_after_2s'], 'stop', entry['stop_to_barrier_s'], flush=True)

    def cleanup(self):
        errors = []
        if self.sampler:
            try:
                self.sampler.close()
                self.report['sampling_ns_per_mach_tick'] = self.sampler.ns_per_tick
            except BaseException as error:
                errors.append(repr(error))
        if self.c and self.changed:
            try:
                self.c.call('cancel_all_outputs')
                state = self.c.wait(lambda s: all(not v['native_busy'] for v in slots(s).values()))
                for target in TARGETS:
                    if slots(state)[target]['recovery_required']:
                        self.c.call('recover_output_target', target=target)
                self.c.call('select_scene', scene_id=self.initial['project']['graph']['active_scene'])
                if self.scene:
                    self.c.call('remove_scene', scene_id=self.scene)
                if self.video_source:
                    self.c.call('remove_source', source_id=self.video_source)
                if self.owned_asset:
                    self.c.call('remove_asset', asset_id=self.asset['id'])
                if self.tone:
                    self.c.call('remove_audio_input', input_id=self.tone)
                for target in TARGETS:
                    self.c.call('select_output_profile', target=target,
                        profile_id=self.initial['output_configuration'][target+'_profile'])
                for value in self.profiles.values():
                    self.c.call('remove_output_profile', id=value['id'])
                self.c.call('configure_video', video=self.initial['project'].get('video') or DEFAULT_VIDEO)
                self.c.call('set_variant', variant=self.initial['project']['variant'])
                endpoint = self.initial['output_configuration']['endpoint']
                if endpoint is not None:
                    self.c.call('configure_stream', endpoint=endpoint)
                else:
                    self.report['retained_loopback_endpoint'] = {'transport': 'rtmp', 'port': self.port}
                self.c.call('configure_transition', transition=self.initial['transition_configuration'])
                self.report['cleanup_state'] = self.c.state()
            except BaseException as error:
                errors.append(repr(error))
        for receiver in self.receivers:
            try:
                if receiver.process.poll() is None:
                    receiver.terminate()
            except BaseException as error:
                errors.append(repr(error))
        if self.inbox:
            try:
                self.inbox.unlink(missing_ok=True)
            except BaseException as error:
                errors.append(repr(error))
        if self.c:
            try:
                self.c.close()
            except BaseException as error:
                errors.append(repr(error))
        try:
            self.observations.close()
            if self.sampler:
                write_json(self.directory/'process-samples.json', self.sampler.rows)
            self.report['final_app_sha256'] = sha(APP) if APP.exists() else None
            self.report['stores_after'] = self.store_hashes()
        except BaseException as error:
            errors.append(repr(error))
        self.report['cleanup_errors'] = errors


def comparisons(report):
    result = []
    for fps in report['arguments']['fps']:
        trials = [t for t in report['trials'] if t['label'].startswith(f'perf-{fps}-')]
        if len(trials) != 4:
            continue
        a1, b1, b2, a2 = trials
        metrics = {}
        for key in ('cpu_median_percent', 'cpu_mean_percent', 'cpu_p95_percent',
                    'rss_median_mib', 'rss_max_mib'):
            values = [t['active']['steady_after_2s'][key] for t in trials]
            metrics[key] = {'ordered_abba': values,
                'paired_dual_minus_single': [values[1]-values[0], values[2]-values[3]],
                'mean_dual_minus_single': statistics.mean((values[1], values[2]))-
                                          statistics.mean((values[0], values[3]))}
        result.append({'fps': fps, 'fixture': report['arguments']['fixture'], 'metrics': metrics,
            'note': 'Two observations per arm; descriptive paired deltas, no significance or optimization claim.'})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lock-held', action='store_true')
    parser.add_argument('--mode', choices=('performance', 'tail', 'both'), default='performance')
    parser.add_argument('--fps', type=int, choices=(30, 60), nargs='+', default=[30])
    parser.add_argument('--seconds', type=float, default=12.)
    parser.add_argument('--baseline-seconds', type=float, default=4.)
    parser.add_argument('--fixture', choices=('pattern', 'video'), default='pattern')
    parser.add_argument('--encoder', choices=('videotoolbox', 'x264'), default='videotoolbox')
    parser.add_argument('--bitrate', type=int, default=2500)
    parser.add_argument('--reordering', choices=('on', 'off'), default='on')
    args = parser.parse_args()
    if not args.lock_held:
        parser.error('--lock-held is required: caller must own the shared device/bundle lock')
    if not math.isfinite(args.seconds) or not 6 <= args.seconds <= 120:
        parser.error('--seconds must be 6..120')
    if not math.isfinite(args.baseline_seconds) or not 3 <= args.baseline_seconds <= 30:
        parser.error('--baseline-seconds must be 3..30')
    if not 250 <= args.bitrate <= 20000 or len(set(args.fps)) != len(args.fps):
        parser.error('bitrate must be 250..20000 and FPS values must be distinct')
    directory = ROOT/'var/evidence'/('h13-performance-'+str(time.time_ns()))
    directory.mkdir(parents=True)
    report = {'ok': False, 'run': str(directory), 'arguments': vars(args), 'trials': [], 'phases': [], 'media': [],
        'sampling': 'H12 macOS libproc 20Hz; native MCP queries 2Hz; CPU 100%=one core',
        'limits': ['CPU/RSS exclude receiver, mux helper and verifier; short <50ms peaks may be missed.',
                   'Preview counters describe copies, not presentation latency or zero-copy GPU traffic.',
                   'H11 hidden playback/reconcile are a separate proposed matrix; no pause optimization.',
                   'No physical camera/window/system-audio or native GPUI interaction is exercised.',
                   'Graph counters and project v5 migration remain; no persisted store is written.',
                   'Functional PASS permits explicit historical tail <150ms; consult strict_cadence_ok.']}
    bench = Benchmark(args, directory, report)
    print(directory, flush=True)
    try:
        bench.open()
        for fps in args.fps:
            if args.mode in ('performance', 'both'):
                for index, dual in enumerate((False, True, True, False)):
                    bench.trial(f'perf-{fps}-{index+1}-'+('dual' if dual else 'single'), fps, dual,
                                args.encoder, args.reordering == 'on', args.seconds)
            if args.mode in ('tail', 'both'):
                for encoder in ('videotoolbox', 'x264'):
                    for index, reorder in enumerate((True, False, False, True)):
                        bench.trial(f'tail-{fps}-{encoder}-{index+1}', fps, False, encoder, reorder,
                                    6.10 if index < 2 else 6.33)
    except BaseException as error:
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        bench.cleanup()
        errors = []
        for record in report['media']:
            try:
                analyze_media(record, directory)
            except BaseException as error:
                record.setdefault('analysis', {})['error'] = repr(error)
                errors.append({'label': record['label'], 'error': repr(error)})
            write_json(directory/'report.json', report)
        report['analysis_errors'] = errors
        report['comparisons'] = comparisons(report)
        report['strict_cadence_ok'] = bool(report['media']) and all(
            m.get('analysis', {}).get('gates', {}).get('strict_all_frame_cadence', False) for m in report['media'])
        report['ok'] = (not report.get('error') and not report['cleanup_errors'] and not errors and
            bool(report['trials']) and report['app_sha256'] == report['final_app_sha256'] and
            report['stores_before'] == report['stores_after'])
        report['result'] = ('functional_pass' if report['strict_cadence_ok'] else 'functional_pass_with_tail_gaps') if report['ok'] else 'failed'
        write_json(directory/'report.json', report)
    print(json.dumps({'ok': report['ok'], 'result': report['result'], 'strict_cadence_ok': report['strict_cadence_ok'],
                      'report': str(directory/'report.json')}, indent=2), flush=True)
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
