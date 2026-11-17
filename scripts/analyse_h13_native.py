#!/usr/bin/env python3
"""OFFLINE structural evidence for an H13 native take; never controls Motive.

  python3 scripts/analyse_h13_native.py --observations DIR/observations.jsonl \
      --media manifest.json

Manifest (closed schema; paths relative to the manifest, or absolute):
{"version":1,"media":[{"pid":123,"target":"recording","attempt_id":1,
 "path":"take.mkv","intentional_fault":false,
 "expected_video":{"width":1920,"height":1080,"fps":30}}]}

Use a separate entry for each (pid,target,attempt_id), including RTMP receiver
files. Mapping a receiver file is an explicit caller declaration, not inferred
from names, timestamps or the unrelated recording zero point. Inputs are copied
or hashed and must be closed/stable. Evidence is written to a unique directory.

Functional cadence retains <=1.5/fps interior and <150ms all-frame gap gates.
Strict cadence separately requires every gap <=1/fps + 1ms container precision.
AAC gaps are <=22ms (+1ns numerical epsilon). All gaps, including the last four,
remain in artifacts. Only a bounded initial H264/Matroska B-frame DTS prefix may
be absent, per the reviewed H13 performance analyzer; no DTS is synthesized.

PCM checks both original stereo channels, without downmix or normalization.
Peak, saturated samples and every 20ms RMS/peak block are retained. Silence,
gain/mute, independent levels, spectral bins, visual changes and A/V alignment
are INCONCLUSIVE until actual event/frequency/geometry mappings are provided.
No polling-to-media alignment is invented. CPU/RSS refer to observed Motive PID
intervals, not helpers or unseen peaks; missing startup/terminal coverage stays
explicit. This instrument does not grant native/UI/H13 acceptance.

Exit 0: automatic functional checks PASS; 1: FAIL; 2: INCONCLUSIVE. Strict
cadence and deferred coverage have separate statuses; exit 0 is not acceptance.
Only ffmpeg/ffprobe subprocesses run. No app/client calls, device access, builds,
launches, network receivers, original-media edits or production-file writes.
"""

import argparse
import array
import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import sys
import time
import traceback
from fractions import Fraction


ROOT = pathlib.Path(__file__).resolve().parents[1]
EPSILON = 1e-9
SHARED_COUNTERS = ('rendered_frames', 'lagged_frames', 'video_skipped_frames',
                   'preview_copies', 'preview_busy_drops')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def gate(status, reason, **details):
    require(status in ('PASS', 'FAIL', 'INCONCLUSIVE'), 'invalid evidence status')
    return {'status': status, 'reason': reason, **details}


def judged(condition, reason, **details):
    return gate('PASS' if condition else 'FAIL', reason, **details)


def combined(checks):
    statuses = [item['status'] for item in checks]
    return ('FAIL' if 'FAIL' in statuses else 'INCONCLUSIVE'
            if not statuses or 'INCONCLUSIVE' in statuses else 'PASS')


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def db(value):
    return 20*math.log10(max(value, 1e-15))


def distribution(values):
    values = sorted(value for value in values if finite(value))
    if not values:
        return None
    return {'samples': len(values), 'min': values[0], 'max': values[-1],
            'median': statistics.median(values),
            'p95': values[min(len(values)-1, math.ceil(.95*len(values))-1)]}


def counter(values):
    if not values or not all(finite(v) for v in values):
        return {'status': 'INCONCLUSIVE', 'reason': 'counter absent/nonfinite; not zero'}
    changes = [b-a for a, b in zip(values, values[1:])]
    return {'status': 'PASS', 'samples': len(values), 'first': values[0], 'last': values[-1],
            'max': max(values), 'net_delta': values[-1]-values[0],
            'observed_positive_increments': sum(max(0, d) for d in changes),
            'resets': [{'sample': i+1, 'before': values[i], 'after': values[i+1]}
                       for i, d in enumerate(changes) if d < 0]}


def zero_increment(value, label):
    if value['status'] != 'PASS' or value.get('samples', 0) < 2:
        return gate('INCONCLUSIVE', label+' unavailable')
    if value['observed_positive_increments']:
        return gate('FAIL', label+' increased in the observed interval', counter=value)
    return gate('INCONCLUSIVE' if value['resets'] else 'PASS',
                label+' observed increments; excludes unobserved time', counter=value)


def progressing(value, label):
    if value['status'] != 'PASS' or value.get('samples', 0) < 2 or value['resets']:
        return gate('INCONCLUSIVE', label+' absent or reset within interval', counter=value)
    return judged(value['observed_positive_increments'] > 0, label+' advanced in observed interval', counter=value)


def read_manifest(path):
    document = json.loads(path.read_text())
    require(set(document) == {'version', 'media'} and type(document['version']) is int
            and document['version'] == 1, 'manifest requires version 1 and media only')
    require(isinstance(document['media'], list) and document['media'], 'nonempty media list required')
    seen, files = set(), set()
    for item in document['media']:
        require(isinstance(item, dict) and set(item) ==
                {'pid', 'target', 'attempt_id', 'path', 'intentional_fault', 'expected_video'},
                'media entry fields must match the documented closed schema')
        require(all(type(item[k]) is int and item[k] > 0 for k in ('pid', 'attempt_id')), 'positive PID/attempt required')
        require(item['target'] in ('recording', 'streaming') and type(item['intentional_fault']) is bool,
                'target and intentional_fault must be typed')
        video = item['expected_video']
        require(isinstance(video, dict) and set(video) == {'width', 'height', 'fps'}, 'expected_video requires width,height,fps')
        require(all(type(video[k]) is int and video[k] > 0 for k in video) and video['fps'] in (30, 60),
                'positive video dimensions and H13 30/60 FPS required')
        require(isinstance(item['path'], str) and item['path'], 'explicit media path required')
        media = pathlib.Path(item['path'])
        media = (media if media.is_absolute() else path.parent/media).resolve(strict=True)
        require(media.is_file() and media.stat().st_size > 0, 'nonempty regular media file required')
        key = (item['pid'], item['target'], item['attempt_id'])
        require(key not in seen and media not in files, 'duplicate attempt or media file')
        seen.add(key); files.add(media)
        item['path'] = str(media)
    return document


def observations(path, directory):
    before = path.stat()
    copy = directory/'observations.snapshot.jsonl'
    rows, errors = [], []
    with path.open('rb') as source, copy.open('wb') as sink:
        for number, raw in enumerate(source, 1):
            sink.write(raw)
            try:
                row = json.loads(raw)
                state = row['state']
                require(finite(row['monotonic']) and type(state['pid']) is int, 'invalid time/PID')
                require(set(state['outputs']) == {'recording', 'streaming'}, 'missing H13 slots')
                rows.append({'monotonic': row['monotonic'], 'pid': state['pid'],
                    'cpu_percent': row.get('cpu_percent'), 'rss_mib': row.get('rss_mib'),
                    'revision': state.get('revision'), 'last_action': state.get('last_action'),
                    'stats': state['stats'], 'outputs': state['outputs'],
                    'issues': state.get('issues'),
                    'master_clipped_blocks': state.get('audio_mixer', {}).get('runtime', {}).get('mix', {}).get('clipped_blocks'),
                    'source_instances': {s['id']: s.get('instance_id') for s in state.get('sources', [])},
                    'audio_instances': {s['id']: s.get('instance_id') for s in
                                        state.get('audio_mixer', {}).get('runtime', {}).get('inputs', [])}})
            except (ValueError, KeyError, TypeError) as error:
                errors.append({'line': number, 'error': str(error), 'bytes': len(raw)})
    after = path.stat()
    stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
              after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return rows, {'path': str(copy), 'sha256': sha(copy), 'rows': len(rows), 'parse_errors': errors,
                  'stability': gate('PASS' if stable else 'INCONCLUSIVE', 'observation file unchanged during snapshot'),
                  'schema': judged(bool(rows) and not errors, 'all observation lines parse; no silent drops')}


def process_evidence(rows):
    result = {}
    for pid in sorted({r['pid'] for r in rows}):
        samples = [r for r in rows if r['pid'] == pid]
        gaps = [b['monotonic']-a['monotonic'] for a, b in zip(samples, samples[1:])]
        counters = {k: counter([r['stats'].get(k) for r in samples]) for k in SHARED_COUNTERS}
        clipping = counter([r['master_clipped_blocks'] for r in samples])
        cpu = distribution([r['cpu_percent'] for r in samples])
        rss = distribution([r['rss_mib'] for r in samples])
        checks = {'observation_time_order': (judged(min(gaps) > 0, 'strictly increasing observer monotonic time')
                                            if gaps else gate('INCONCLUSIVE', 'at least two observations required')),
                  'resource_samples': gate('PASS' if cpu and rss else 'INCONCLUSIVE',
                      'sampled CPU/RSS available; no resource budget or unobserved peak claim'),
                  'render_progress': progressing(counters['rendered_frames'], 'render frames'),
                  'preview_progress': progressing(counters['preview_copies'], 'preview copies'),
                  'render_lag': zero_increment(counters['lagged_frames'], 'render lag'),
                  'video_skips': zero_increment(counters['video_skipped_frames'], 'video skips'),
                  'master_clipping': zero_increment(clipping, 'native master clipping')}
        result[str(pid)] = {'scope': 'whole observed PID interval, shared once across destinations',
            'first_monotonic': samples[0]['monotonic'], 'last_monotonic': samples[-1]['monotonic'],
            'samples': len(samples), 'sample_interval_s': distribution(gaps),
            'cpu_percent': cpu, 'rss_mib': rss,
            'missing_cpu_samples': sum(not finite(r['cpu_percent']) for r in samples),
            'missing_rss_samples': sum(not finite(r['rss_mib']) for r in samples), 'counters': counters,
            'master_clipped_blocks': clipping, 'checks': checks,
            'limits': ['CPU 100% is one Motive core; excludes helpers/host.',
                       'Polling can miss peaks and events; counters can reset at reconfiguration.',
                       'No unobserved startup/stop work is inferred from these samples.']}
    return result


def attempt_evidence(item, rows):
    pid_rows = [r for r in rows if r['pid'] == item['pid']]
    selected = [(i, r) for i, r in enumerate(pid_rows)
                if r['outputs'][item['target']]['attempt_id'] == item['attempt_id']]
    if not selected:
        return {'checks': {'mapping': gate('INCONCLUSIVE', 'no observed matching PID/target/attempt')}, 'samples': 0}
    samples = [r for _, r in selected]
    slots = [r['outputs'][item['target']] for r in samples]
    checks = {'mapping': judged(all(s['video'] == item['expected_video'] for s in slots),
                               'explicit video matches every native attempt snapshot')}
    if item['target'] == 'recording':
        checks['recording_path'] = judged(all(s['path'] is not None and pathlib.Path(s['path']).resolve() ==
            pathlib.Path(item['path']) for s in slots), 'recording path bound by native snapshot')
    first = selected[0][0]
    checks['start_boundary'] = gate('PASS' if first > 0 else 'INCONCLUSIVE',
                                    'prior snapshot needed to bound attempt start; no invented start time')
    checks['terminal_boundary'] = gate('PASS' if any(not s['native_busy'] and s['phase'] in ('idle', 'error')
                                                   for s in slots) else 'INCONCLUSIVE',
                                       'native terminal barrier observed for this attempt')
    stats = {k: counter([s['stats'].get(k) for s in slots])
             for k in ('output_frames', 'encoded_frames', 'output_bytes', 'output_dropped_frames')}
    checks['output_drops'] = zero_increment(stats['output_dropped_frames'], 'slot drops')
    faults = [s['failure'] for s in slots if s['failure'] is not None]
    checks['native_fault'] = (gate('INCONCLUSIVE', 'intentional fault declared; preserve observed failures', failures=faults)
                              if item['intentional_fault'] else judged(not faults, 'no unexpected slot failure', failures=faults))
    variants = {}
    for kind in ('source_instances', 'audio_instances'):
        variants[kind] = {}
        for row in samples:
            for identifier, instance in row[kind].items():
                observed = variants[kind].setdefault(identifier, [])
                if instance not in observed:
                    observed.append(instance)
    return {'samples': len(samples), 'first_monotonic': samples[0]['monotonic'],
            'last_monotonic': samples[-1]['monotonic'], 'first_slot': slots[0], 'last_slot': slots[-1],
            'phases': list(dict.fromkeys(s['phase'] for s in slots)), 'stats': stats,
            'instance_variants': variants, 'checks': checks,
            'receiver_mapping': 'declared by manifest; no independent RTMP file-to-attempt binding' if item['target']=='streaming' else None,
            'media_alignment': gate('INCONCLUSIVE', 'no explicit alignment; first PTS and native duration are not interchangeable clocks')}


class Commands:
    def __init__(self, directory):
        self.directory = directory
        self.entries = []

    def run(self, arguments, label, stdout_path=None):
        require(arguments[0] in ('ffmpeg', 'ffprobe'), 'offline tools only')
        start = time.monotonic()
        entry = {'arguments': arguments, 'label': label}
        self.entries.append(entry)
        try:
            if stdout_path:
                with stdout_path.open('wb') as output:
                    done = subprocess.run(arguments, stdout=output, stderr=subprocess.PIPE, timeout=900)
            else:
                done = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
            log = self.directory/(label+'.stderr.log'); log.write_bytes(done.stderr)
            entry.update(returncode=done.returncode, stderr_path=str(log), stderr_sha256=sha(log),
                         stderr_bytes=len(done.stderr))
            return done
        except BaseException as error:
            entry['error'] = repr(error)
            raise
        finally:
            entry['seconds'] = time.monotonic()-start
            write_json(self.directory/'commands.json', self.entries)

    def probe(self, path, label, extra):
        done = self.run(['ffprobe', '-v', 'error', '-threads', '1', *extra, '-of', 'json', str(path)], label)
        require(done.returncode == 0, 'ffprobe failed; see '+label+'.stderr.log')
        value = json.loads(done.stdout)
        write_json(self.directory/(label+'.json'), value)
        return value


def timestamp_evidence(probe, frames, packets, fps):
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    points = [float(f['best_effort_timestamp_time']) for f in frames if 'best_effort_timestamp_time' in f]
    require(len(points) >= 6 and all(map(math.isfinite, points)), 'at least six finite decoded video PTS required')
    gaps = [b-a for a, b in zip(points, points[1:])]
    interior, tail = gaps[:-4], gaps[-4:]
    checks = {'decoded_pts': judged(len(points) == len(frames) and min(gaps) > 0, 'complete positive presentation cadence'),
              'interior_cadence': judged(max(interior) <= 1.5/fps+EPSILON, 'all but final four gaps <=1.5 nominal intervals'),
              'functional_final_gap': judged(max(gaps) < .15, 'every gap, including final four, strictly below 150ms')}
    strict_limit = 1/fps+.001
    strict = judged(max(gaps) <= strict_limit+EPSILON, 'every gap <= nominal interval +1ms timestamp precision', limit_s=strict_limit)
    result = {'frames': len(frames), 'first_pts': points[0], 'last_pts': points[-1],
              'gaps_s': gaps, 'max_interior_gap_s': max(interior), 'last_four_gaps_s': tail,
              'max_gap_s': max(gaps), 'b_frames': sum(f.get('pict_type')=='B' for f in frames),
              'strict_cadence': strict, 'checks': checks, 'packets': {}}
    for kind in ('video', 'audio'):
        stream = next(s for s in probe['streams'] if s['codec_type']==kind)
        values = [p for p in packets if p['stream_index']==stream['index']]
        missing_pts = [i for i,p in enumerate(values) if 'pts_time' not in p]
        missing_dts = [i for i,p in enumerate(values) if 'dts_time' not in p]
        pts = [float(p['pts_time']) for p in values if 'pts_time' in p]
        dts = [float(p['dts_time']) for p in values if 'dts_time' in p]
        require(all(map(math.isfinite, pts+dts)), kind+' packet timestamp is nonfinite')
        depth = video.get('has_b_frames',0) if kind=='video' else 0
        matroska = 'matroska' in probe.get('format',{}).get('format_name','').split(',')
        allowed = (kind=='video' and video['codec_name']=='h264' and matroska and type(depth) is int
                   and depth>0 and result['b_frames']>0 and missing_dts==list(range(len(missing_dts)))
                   and len(missing_dts)<=depth)
        checks[kind+'_packet_pts'] = judged(len(pts)>=2 and not missing_pts and all(map(math.isfinite,pts)), 'finite PTS for every '+kind+' packet')
        checks[kind+'_packet_dts'] = judged(len(dts)>=2 and all(map(math.isfinite,dts))
            and (not missing_dts or allowed) and all(b>a for a,b in zip(dts,dts[1:])),
            'monotonic known DTS; only bounded initial H264/Matroska reordered prefix may be absent')
        detail = {'packets': len(values), 'missing_pts_indices': missing_pts, 'missing_dts_indices': missing_dts,
                  'reported_reorder_depth': depth, 'bounded_initial_dts_exception': bool(missing_dts and allowed),
                  'inferred_dts_count': 0, 'first_pts': min(pts) if pts else None, 'last_pts': max(pts) if pts else None,
                  'known_dts_gaps_s': [b-a for a,b in zip(dts,dts[1:])]}
        if kind=='audio':
            agaps = [b-a for a,b in zip(pts,pts[1:])]
            detail['gaps_s'] = agaps
            detail['max_gap_s'] = max(agaps) if agaps else None
            checks['aac_gaps'] = judged(bool(agaps) and min(agaps)>0 and max(agaps)<=.022+EPSILON,
                                       'AAC packet PTS gaps <=22ms; says nothing alone about PCM continuity')
        result['packets'][kind] = detail
    return result


def pcm_evidence(path, label, commands, directory):
    temporary = directory/(label+'.pcm.tmp')
    windows = directory/(label+'-pcm-20ms.jsonl')
    peaks, clipped, sums = [0.,0.], [0,0], [0.,0.]
    samples, bad, blocks = 0, 0, 0
    try:
        done = commands.run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(path),
             '-map','0:a:0','-vn','-c:a','pcm_f32le','-f','f32le','-'], label+'-pcm', temporary)
        pcm_hash = sha(temporary)
        require(temporary.stat().st_size % 8 == 0, 'complete stereo float32 samples')
        with temporary.open('rb') as source, windows.open('w') as sink:
            while raw := source.read(960*8):
                values = array.array('f',raw)
                if sys.byteorder!='little': values.byteswap()
                count = len(values)//2
                channels = [values[0::2], values[1::2]]
                row = {'start_sample':samples, 'start_seconds':samples/48000, 'samples':count,
                       'full_20ms':count==960, 'rms_dbfs':[], 'peak_dbfs':[]}
                for channel, values in enumerate(channels):
                    nonfinite = sum(not math.isfinite(x) for x in values); bad += nonfinite
                    clean = [x for x in values if math.isfinite(x)]
                    peak = max(map(abs,clean),default=0.)
                    square = sum(x*x for x in clean)
                    peaks[channel] = max(peaks[channel],peak); sums[channel] += square
                    clipped[channel] += sum(abs(x)>=1 for x in clean)
                    row['rms_dbfs'].append(db(math.sqrt(square/count)))
                    row['peak_dbfs'].append(db(peak))
                    if nonfinite: row['nonfinite_samples'] = row.get('nonfinite_samples',0)+nonfinite
                sink.write(json.dumps(row,separators=(',',':'))+'\n')
                samples += count; blocks += 1
        checks = {'pcm_decode': judged(done.returncode==0 and not done.stderr, 'complete stereo PCM decode'),
                  'pcm_samples': judged(samples>0 and bad==0, 'finite PCM samples in both channels',nonfinite=bad),
                  'digital_clipping': judged(not any(clipped), 'no decoded samples with abs(value)>=1',per_channel_counts=clipped),
                  'peak_headroom': judged(max(peaks)<10**(-.5/20), 'historical H12 headroom: peak below -0.5dBFS')}
        return {'checks':checks,'channels':2,'sample_rate':48000,'samples_per_channel':samples,
                'duration_s':samples/48000,'peak_dbfs':[db(v) for v in peaks],
                'rms_dbfs':[db(math.sqrt(v/samples)) if samples else None for v in sums],
                'pcm_sha256':pcm_hash,'windows':{'path':str(windows),'sha256':sha(windows),'blocks':blocks},
                'channel_policy':'Original stereo, no sum/resample/normalization; times are sample offsets, not aligned PTS.'}
    finally:
        temporary.unlink(missing_ok=True)


def analyze(item, rows, commands, directory, index):
    label=f'media-{index:02d}-{item["target"]}-{item["attempt_id"]}'
    path=pathlib.Path(item['path']); initial=sha(path)
    result={'mapping':item,'sha256':initial,'bytes':path.stat().st_size,'checks':{},
            'native':attempt_evidence(item,rows),'strict_video_cadence':gate('INCONCLUSIVE','not analyzed')}
    try:
        probe=commands.probe(path,label+'-probe',['-count_frames','-show_streams','-show_format'])
        videos=[s for s in probe['streams'] if s['codec_type']=='video']
        audios=[s for s in probe['streams'] if s['codec_type']=='audio']
        require(len(videos)==1 and len(audios)==1,'exactly one video/audio track required')
        v,a=videos[0],audios[0]; expected=item['expected_video']
        result['checks']['metadata']=judged(v['codec_name']=='h264' and
            (v['width'],v['height'])==(expected['width'],expected['height']) and
            Fraction(v['avg_frame_rate'])==expected['fps'] and a['codec_name']=='aac' and
            a['sample_rate']=='48000' and a['channels']==2,'explicit H264 dimensions/FPS and AAC stereo 48k',video=v,audio=a)
        decoded=commands.run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(path),
                             '-map','0:v:0','-map','0:a:0','-f','null','-'],label+'-full-decode')
        result['checks']['full_decode']=judged(decoded.returncode==0 and not decoded.stderr,'complete video/audio decode',returncode=decoded.returncode,stderr=decoded.stderr.decode(errors='replace'))
        frames=commands.probe(path,label+'-frames',['-select_streams','v:0','-show_frames','-show_entries',
             'frame=best_effort_timestamp_time,pkt_dts_time,duration_time,key_frame,pict_type'])['frames']
        result['checks']['decoded_frame_count']=judged(str(len(frames))==v.get('nb_read_frames'),
            'complete frame enumeration agrees with independent metadata count',
            enumerated=len(frames),metadata=v.get('nb_read_frames'))
        packets=commands.probe(path,label+'-packets',['-show_packets','-show_entries',
             'packet=stream_index,pts_time,dts_time,duration_time,flags'])['packets']
        result['timeline']=timestamp_evidence(probe,frames,packets,expected['fps'])
        result['checks'].update(result['timeline']['checks'])
        result['strict_video_cadence']=result['timeline']['strict_cadence']
        if a['sample_rate']=='48000' and a['channels']==2:
            result['pcm']=pcm_evidence(path,label,commands,directory)
            result['checks'].update(result['pcm']['checks'])
        else:
            result['checks']['pcm_format']=gate('FAIL','PCM interpretation requires stereo 48k; no silent conversion')
        result['checks']['media_unchanged']=judged(sha(path)==initial,'media bytes unchanged throughout analysis')
    except Exception as error:
        result['checks']['analysis_error']=gate('FAIL','analysis could not complete',error=repr(error),traceback=traceback.format_exc())
    if item['intentional_fault']:
        result['integrity']=gate('INCONCLUSIVE','intentional fault: raw decode failures retained; no claim of clean finalization')
    else:
        result['integrity']=gate(combined(result['checks'].values()),'healthy-file automatic structural checks')
    result['functional_status']=combined([*result['checks'].values(),*result['native']['checks'].values(),result['integrity']])
    result['deferred_coverage']={name:gate('INCONCLUSIVE',reason) for name,reason in {
        'gain_mute_and_independent_levels':'Need actual frequencies, isolated references and event-to-media alignment.',
        'audio_continuity':'PCM RMS/packet cadence alone cannot distinguish intended mute/silence from a gap.',
        'visual_edits_widgets_cut_fade':'Need actual source/layer IDs, geometry, event receipts and controlled expected pixels.',
        'audio_video_sync':'No explicit visual/audio markers mapped in this manifest.',
        'native_gestures_and_confirmations':'Requires observed GPUI actions; state/media do not establish the interaction.'}.items()}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--observations',type=pathlib.Path,required=True)
    parser.add_argument('--media',type=pathlib.Path,required=True)
    args=parser.parse_args()
    directory=ROOT/'var/evidence'/f'h13-native-analysis-{time.time_ns()}';directory.mkdir(parents=True)
    report={'analysis_version':1,'acceptance':'NOT_EVALUATED','coverage_status':'INCONCLUSIVE',
            'functional_status':'FAIL','strict_video_cadence_status':'INCONCLUSIVE','media':[],
            'scope':'Offline automatic structural checks only; never H13/native acceptance.'}
    print(directory,flush=True)
    try:
        manifest=args.media.resolve(strict=True); source=args.observations.resolve(strict=True)
        report['inputs']={'manifest':str(manifest),'manifest_sha256':sha(manifest),
                          'observations':str(source),'script_sha256':sha(pathlib.Path(__file__))}
        (directory/'media-manifest.original.json').write_bytes(manifest.read_bytes())
        document=read_manifest(manifest);write_json(directory/'media-manifest.snapshot.json',document)
        rows,summary=observations(source,directory);report['observation_snapshot']=summary
        report['processes']=process_evidence(rows)
        mapped={(m['pid'],m['target'],m['attempt_id']) for m in document['media']}
        seen={}
        for row in rows:
            for target,slot in row['outputs'].items():
                if slot['attempt_id'] is None:
                    continue
                key=(row['pid'],target,slot['attempt_id'])
                entry=seen.setdefault(key,{'pid':key[0],'target':target,'attempt_id':key[2],
                    'media_mapped':key in mapped,'phases':[],'observed_failure':False})
                if slot['phase'] not in entry['phases']: entry['phases'].append(slot['phase'])
                entry['observed_failure'] |= slot['failure'] is not None
        report['observed_attempts']=list(seen.values())
        report['mapping_coverage']=gate('INCONCLUSIVE' if any(not e['media_mapped'] for e in seen.values()) else 'PASS',
            'All observed attempts inventoried; an unmapped failed attempt may legitimately have no file, requiring explicit review.')
        commands=Commands(directory)
        report['tool_versions']={}
        for name in ('ffmpeg','ffprobe'):
            version=commands.run([name,'-version'],name+'-version')
            require(version.returncode==0, name+' version unavailable')
            report['tool_versions'][name]=version.stdout.decode(errors='replace')
        for index,item in enumerate(document['media'],1):
            report['media'].append(analyze(item,rows,commands,directory,index))
            write_json(directory/'report.json',report)
        checks=[summary['stability'],summary['schema']]
        checks += [gate(m['functional_status'],'mapped media structural checks') for m in report['media']]
        checks += [g for p in report['processes'].values() for g in p['checks'].values()]
        report['functional_status']=combined(checks)
        report['strict_video_cadence_status']=combined(m['strict_video_cadence'] for m in report['media'])
    except BaseException as error:
        report['error']={'message':repr(error),'traceback':traceback.format_exc()}
    finally:
        report['finished_unix_ns']=time.time_ns();write_json(directory/'report.json',report)
    print(json.dumps({'report':str(directory/'report.json'),'functional_status':report['functional_status'],
                      'strict_video_cadence_status':report['strict_video_cadence_status'],
                      'coverage_status':report['coverage_status'],'acceptance':report['acceptance']}),flush=True)
    return {'PASS':0,'FAIL':1,'INCONCLUSIVE':2}[report['functional_status']]


if __name__=='__main__':
    raise SystemExit(main())
