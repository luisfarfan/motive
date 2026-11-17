#!/usr/bin/env python3
"""Bounded OFFLINE PCM analysis of a completed native take. Never controls Motive.

Run ONLY after production is stopped and the owner authorizes offline decoding:
  python3 scripts/analyse_h13_native_audio.py --plan AUDIO_PLAN/report.json \
      --media media-manifest.json

Use a final plan_h13_native_audio.py plan and the closed version-1 media manifest
accepted by analyse_h13_native.py. No synthetic signal or private audio playback.
Each file gets its own bounded search for observed, mic-isolated gain edges.
Hann100ms, gain +/-1dB, native RMS +/-2dB and isolated20ms +/-1dB remain fixed.
The fixture declaration is 997Hz/-24dBFS (scripts/fixtures/h13_audio_app.m).
The physical microphone is NOT assumed stationary, noiseless or free of997Hz.

asettb/ashowinfo retain original sample timestamps before any sink rebasing.
Input -seek_timestamp 1 makes -ss absolute; input -t bounds demux as well as
atrim. No resample/downmix/normalization. Original stereo float PCM snippets,
20ms windows stepped10ms, Hann100ms bins, native readings, commands and hashes
are retained. This is bounded event evidence, not whole-file audio continuity.

Official option semantics: https://ffmpeg.org/ffmpeg.html#Advanced-options
https://ffmpeg.org/ffmpeg-filters.html#ashowinfo
https://ffmpeg.org/ffmpeg-filters.html#settb_002c-asettb
Exit0 functional PASS;1 FAIL;2 INCONCLUSIVE. Native acceptance is never granted.
"""

import argparse
import array
import bisect
import hashlib
import json
import math
import pathlib
import re
import statistics
import sys
import time
import traceback

from analyse_h13_native import Commands, combined, db, gate, judged, read_manifest, require, sha, write_json
# Main-guarded, side-effect-free helper: exact reviewed H10 Hann estimator.
from verify_h10_audio import tonal_amplitudes


ROOT = pathlib.Path(__file__).resolve().parents[1]
RATE = 48000
POLICY = {'search_radius_s': 3, 'minimum_plateau_bins': 10, 'alignment_plateau_db': .75,
    'minimum_alignment_step_db': 3, 'maximum_alignment_step_db': 30,
    'maximum_media_edge_bracket_s': .6, 'maximum_offset_bracket_s': 1.5,
    'reference_seconds_max': 8, 'reference_seconds_min': 5,
    'gain_tolerance_db': 1, 'meter_tolerance_db': 2, 'isolated_rms_tolerance_db': 1,
    'fixture_frequency_hz': 997, 'fixture_peak_dbfs': -24,
    'acoustic_frequency_hz': 440, 'minimum_audible_acoustic_amplitude': .00001,
    'pcm_window_samples': 960, 'pcm_step_samples': 480, 'hann_window_samples': 4800,
    'event_continuity_fraction': .55, 'event_guard_each_side_s': 2}


def matching(segment, item):
    slot = segment['outputs'][item['target']]
    return slot['attempt_id'] == item['attempt_id'] and slot['phase'] == 'active'


def pcm_clip(path, start, end, directory, label, commands):
    require(0 <= start < end and end-start <= 31, 'bounded positive PCM interval required')
    seek = max(0, start-.25)
    rawpath = directory/(label+'.f32le')
    filters = f'asettb=1/48000,atrim=start={start:.9f}:end={end:.9f},ashowinfo'
    done = commands.run(['ffmpeg','-nostdin','-hide_banner','-nostats','-v','info',
        '-threads','1','-filter_threads','1','-copyts','-seek_timestamp','1','-ss',f'{seek:.9f}',
        '-t',f'{end-seek+.1:.9f}','-i',str(path),'-map','0:a:0','-vn',
        '-af',filters,'-c:a','pcm_f32le','-f','f32le','-'],label,rawpath)
    require(done.returncode == 0, 'PCM decode failed; see '+label+'.stderr.log')
    raw = rawpath.read_bytes(); require(len(raw) > 0 and len(raw)%8 == 0, 'stereo float32 PCM required')
    frames = []; offset = 0
    for line in done.stderr.decode(errors='replace').splitlines():
        if 'ashowinfo' not in line or not re.search(r'\bn:\s*\d+', line):
            continue
        values = dict(re.findall(r'\b(n|pts|rate|nb_samples):\s*([^\s]+)', line))
        require(set(values) == {'n','pts','rate','nb_samples'}, 'incomplete ashowinfo frame')
        require(int(values['rate']) == RATE and int(values['n']) == len(frames), 'audio frame rate/order mismatch')
        count = int(values['nb_samples']); require(count > 0, 'empty decoded audio frame')
        frames.append({'sample_offset': offset, 'pts_samples': int(values['pts']), 'samples': count})
        offset += count
    require(frames and offset*8 == len(raw), 'original timestamp frames and PCM count differ')
    gaps = [b['pts_samples']-(a['pts_samples']+a['samples']) for a,b in zip(frames,frames[1:])]
    require(all(abs(g) <= 48 for g in gaps), 'decoded audio timestamp discontinuity beyond 1ms container precision')
    samples = array.array('f',raw)
    if sys.byteorder != 'little': samples.byteswap()
    require(all(math.isfinite(v) for v in samples), 'nonfinite decoded PCM')
    channels = [samples[0::2], samples[1::2]]
    starts = [f['sample_offset'] for f in frames]
    def pts(sample):
        frame = frames[max(0,bisect.bisect_right(starts,sample)-1)]
        return (frame['pts_samples']+sample-frame['sample_offset'])/RATE
    require(abs(pts(0)-start) <= .002 and abs(pts(offset)-end) <= .002,
            'requested original-PTS interval not fully covered')
    windows = []
    for first in range(0,offset-959,480):
        block = [channel[first:first+960] for channel in channels]
        windows.append({'start_sample': first, 'pts_start': pts(first), 'pts_end': pts(first+960),
            'rms_dbfs': [db(math.sqrt(sum(v*v for v in c)/len(c))) for c in block],
            'peak_dbfs': [db(max(map(abs,c))) for c in block]})
    spectra = {freq: [tonal_amplitudes(c,freq) for c in channels] for freq in (440,997)}
    bins = [{'pts_start': pts(i*4800), 'pts_end': pts((i+1)*4800),
             'amplitude': {str(freq): [spectra[freq][c][i] for c in (0,1)] for freq in (440,997)}}
            for i in range(len(spectra[997][0]))]
    result = {'requested_pts': [start,end], 'actual_pts': [pts(0),pts(offset)], 'samples_per_channel': offset,
        'pcm_path': str(rawpath), 'pcm_sha256': sha(rawpath), 'format': 'original stereo f32le/48000Hz',
        'frames': frames, 'frame_timestamp_error_samples': gaps, 'windows_20ms_step10ms': windows,
        'hann_100ms': bins, 'peak_dbfs': [db(max(map(abs,c))) for c in channels],
        'saturated_samples': [sum(abs(v)>=1 for v in c) for c in channels]}
    write_json(directory/(label+'.json'),result)
    return result


def locate_edge(clip, native_bracket, direction):
    bins = clip['hann_100ms']
    levels = [db(math.sqrt(sum(v*v for v in b['amplitude']['997'])/2)) for b in bins]
    count = POLICY['minimum_plateau_bins']
    if len(levels) < count*2+2:
        return gate('INCONCLUSIVE','too few bins for independent edge plateaus',levels_dbfs=levels)
    before, after = statistics.median(levels[:count]), statistics.median(levels[-count:])
    change = after-before
    detail = {'native_event_bracket': native_bracket, 'levels_dbfs': levels,
              'before_plateau_dbfs': before, 'after_plateau_dbfs': after, 'measured_search_step_db': change}
    if not POLICY['minimum_alignment_step_db'] <= abs(change) <= POLICY['maximum_alignment_step_db'] or change*direction <= 0:
        return gate('INCONCLUSIVE','no sufficiently distinct edge in the observed direction',**detail)
    classes = [('before' if abs(v-before)<.75 else 'after' if abs(v-after)<.75 else 'edge') for v in levels]
    detail['bin_classifications'] = classes
    after_indices = [i for i,v in enumerate(classes) if v=='after']
    if not after_indices:
        return gate('INCONCLUSIVE','no after plateau',**detail)
    first_after = after_indices[0]
    before_indices = [i for i,v in enumerate(classes[:first_after]) if v=='before']
    if not before_indices:
        return gate('INCONCLUSIVE','no before plateau',**detail)
    last_before = before_indices[-1]
    clean = (last_before+1 >= count and len(bins)-first_after >= count
             and all(v=='before' for v in classes[:last_before+1])
             and all(v=='after' for v in classes[first_after:]))
    bracket = [bins[last_before]['pts_start'],bins[first_after]['pts_end']]
    offsets = [native_bracket[0]-bracket[1],native_bracket[1]-bracket[0]]
    detail.update(media_edge_bracket=bracket,monotonic_minus_pts_bounds=offsets)
    if not clean or bracket[1]-bracket[0]>.6 or offsets[1]-offsets[0]>1.5:
        return gate('INCONCLUSIVE','ambiguous/noisy/repeated edge or overly wide timing bounds',**detail)
    return gate('PASS','unique bounded isolated gain edge; amplitude was not fitted to expected12dB',**detail)


def anchors_for(item, segments):
    result = []
    for before,after in zip(segments,segments[1:]):
        if not all(matching(s,item) and s['classification']=='application_isolated' and
                   s['controls']['microphone']['muted'] and s['status']=='READY_FOR_ALIGNMENT' for s in (before,after)):
            continue
        a,b=before['controls']['application'],after['controls']['application']
        if a['instance_id']!=b['instance_id'] or a['gain_db']==b['gain_db']:
            continue
        if after['observed_start']-before['observed_end']>1.5:
            continue
        result.append((before,after))
    return result


def robust_meter(clip, rows, role, offsets):
    lo,hi=clip['actual_pts']; minimum,maximum=offsets
    candidates={minimum,maximum}
    for row in rows:
        for edge in (lo,hi):
            for epsilon in (-1e-6,0,1e-6):
                value=row['monotonic']-edge+epsilon
                if minimum<=value<=maximum:candidates.add(value)
    decoded=[statistics.median(w['rms_dbfs'][c] for w in clip['windows_20ms_step10ms']) for c in (0,1)]
    comparisons=[]
    for offset in sorted(candidates):
        selected=[r for r in rows if lo+offset<=r['monotonic']<=hi+offset]
        valid=all(r['inputs'][role] and not r['inputs'][role]['levels']['stale'] and
                  r['inputs'][role]['levels']['age_ms'] is not None and r['inputs'][role]['levels']['age_ms']<=250
                  and all(v is not None and math.isfinite(v) for v in r['inputs'][role]['levels']['rms_dbfs']) for r in selected)
        if len(selected)<4 or not valid:
            return gate('INCONCLUSIVE','insufficient/faulty native RMS for a permitted alignment',offset=offset,samples=len(selected))
        native=[statistics.median(r['inputs'][role]['levels']['rms_dbfs'][c] for r in selected) for c in (0,1)]
        comparisons.append({'offset':offset,'native_samples':len(selected),'native_median_dbfs':native,
                            'error_db':[decoded[c]-native[c] for c in (0,1)]})
    errors=[v for comparison in comparisons for v in comparison['error_db']]
    return judged(all(abs(v)<2 for v in errors),'PCM20ms median vs native buffer-RMS median for every permitted alignment',
        decoded_median_dbfs=decoded,error_range_db=[min(errors),max(errors)],comparisons=comparisons,
        tolerance_db=2,scope='Sampled native meters, no claim of sample-exact synchronization')


def event_windows(item,plan,observed_rows,bounds,covered,path,directory,commands,extrapolated=False,media_extent=None):
    results=[];seen=set()
    operations=('select_scene','cancel_transition','disconnect_audio_input','reconnect_audio_input',
                'update_overlay','overlay_event','stop_output_target','start_output','recover_output_target')
    for event in plan['events']:
        action=event.get('last_action') or ''
        slot=event['outputs'][item['target']]
        app=event['inputs']['application']
        changes=event.get('output_changes',[])
        if ((not changes and not any(f'· {op} ·' in action for op in operations)) or slot['attempt_id']!=item['attempt_id']
            or slot['phase']!='active' or not app or app['muted'] or app['phase']!='ready'):
            continue
        transition=event.get('transition') or {}
        key=(action,transition.get('operation_id'),json.dumps(changes,sort_keys=True))
        if key in seen:continue
        seen.add(key)
        lo,hi=event['observed_interval_monotonic']
        extension=(transition.get('duration_ms',0)/1000 if '· select_scene ·' in action else 0)
        lo-=2;hi+=2+extension
        entry={'last_action':action,'transition':transition,'observed_interval':event['observed_interval_monotonic'],
               'output_changes':changes,
               'checks':{},'attribution':'Final mixture continuity only; mixed997 does not independently identify the app path.'}
        results.append(entry)
        if lo<covered[0] or hi>covered[1]:
            entry['checks']['alignment']=gate('INCONCLUSIVE','event outside measured anchor span; no extrapolation')
            if not extrapolated:continue
            entry['checks']['alignment']=gate('INCONCLUSIVE',
                'Explicit diagnostic search extrapolates the measured offset; event association is not proven',
                distance_before_anchor_span_s=max(0,covered[0]-lo),
                distance_after_anchor_span_s=max(0,hi-covered[1]),
                time_error_bound='Unbounded outside anchoring observations; no finite drift guarantee asserted.')
        start,end=lo-bounds[1],hi-bounds[0]
        if media_extent and (start<media_extent[0]+.002 or end>media_extent[1]-.002):
            entry['checks']['media_window']=gate('INCONCLUSIVE','complete event window exceeds media extent; no truncated window accepted')
            continue
        clip=pcm_clip(path,start,end,directory,f'event-{len(results):02d}',commands)
        entry['sampled_pts']=clip['actual_pts']
        expected=-24+app['gain_db']-10*math.log10(2)
        floor=expected+db(.55)
        violations=[{'index':i,'pts':w['pts_start'],'rms_dbfs':w['rms_dbfs']}
                    for i,w in enumerate(clip['windows_20ms_step10ms']) if any(v<floor for v in w['rms_dbfs'])]
        entry['checks']['mixture_continuity']=judged(not violations,
            'Every20ms/10ms-step mixture RMS remains above55% of isolated-app expected RMS; no lifecycle exclusions',
            floor_dbfs=floor,violations=violations,windows=len(clip['windows_20ms_step10ms']))
        entry['checks']['peak']=judged(max(clip['peak_dbfs'])<-.5 and not any(clip['saturated_samples']),
            'event PCM retains historical headroom',peak_dbfs=clip['peak_dbfs'],saturated_samples=clip['saturated_samples'])
        # Include all originally observed states, not only usable meter
        # interiors. Expand for the complete allowed alignment interval.
        native_span=[start+bounds[0],end+bounds[1]]
        rows=[r for r in observed_rows if native_span[0]<=r['monotonic']<=native_span[1]]
        values=[r['inputs']['application'] for r in rows]
        healthy=(len(values)>=4 and all(v and v['phase']=='ready' and v['issue'] is None and not v['muted']
                    and v['gain_db']==app['gain_db'] and v['instance_id']==app['instance_id']
                    and not v['levels']['stale'] and v['levels']['age_ms'] is not None
                    and v['levels']['age_ms']<=250 for v in values))
        progressed=healthy and all(b['levels']['frames']>a['levels']['frames']
                    and b['levels']['timestamp_ns']>a['levels']['timestamp_ns'] for a,b in zip(values,values[1:]))
        entry['checks']['native_app_progress']=judged(progressed,
            'Observed app input retains instance, ready state and advancing native frames/timestamps',
            samples=len(values),instance_id=app['instance_id'],
            native_window_with_alignment_uncertainty=native_span,
            invalid_samples=[{'monotonic':r['monotonic'],'application':r['inputs']['application']}
                for r in rows if not r['inputs']['application'] or r['inputs']['application']['phase']!='ready'
                or r['inputs']['application']['issue'] is not None or r['inputs']['application']['muted']
                or r['inputs']['application']['gain_db']!=app['gain_db']
                or r['inputs']['application']['instance_id']!=app['instance_id']
                or r['inputs']['application']['levels']['stale']
                or r['inputs']['application']['levels']['age_ms'] is None
                or r['inputs']['application']['levels']['age_ms']>250],
            coverage='Sampled native evidence; discontinuities between observations remain governed by decoded mixture checks.')
        entry['mixed_997_diagnostic']={'minimum_amplitude':[min(b['amplitude']['997'][c] for b in clip['hann_100ms']) for c in (0,1)],
            'attribution_status':'INCONCLUSIVE','reason':'Physical microphone can carry997Hz; no isolated app gain claim.'}
    return results


def analyze_file(item,plan,native_rows,directory,commands,extrapolated=False,observed_rows=None):
    result={'mapping':item,'acceptance':'NOT_EVALUATED','status':'INCONCLUSIVE','checks':{},'anchors':[],'references':[]}
    path=pathlib.Path(item['path'])
    terminal=any(s['outputs'][item['target']]['attempt_id']==item['attempt_id']
                 and not s['outputs'][item['target']]['native_busy']
                 and s['outputs'][item['target']]['phase'] in ('idle','error') for s in plan['segments'])
    if not terminal:
        result['reason']='No observed native terminal barrier for this exact attempt; refuse live-media decoding.'
        return result
    if item['target']=='recording':
        slots=[s['outputs']['recording'] for s in plan['segments']
               if s['outputs']['recording']['attempt_id']==item['attempt_id']]
        require(slots and all(s['path'] is not None and pathlib.Path(s['path']).resolve()==path for s in slots),
                'recording manifest path differs from observed native attempt')
    result['mapping_basis']=('Native recording path + PID/target/attempt' if item['target']=='recording'
                             else 'Caller-declared RTMP file + observed PID/target/attempt; receiver binding not independently inferred')
    require(observed_rows is not None,'final plan must contain all observed samples for continuity')
    result['sha256_before']=sha(path)
    if item['intentional_fault']:
        result['reason']='Intentional-fault media retained for structural analysis; healthy PCM attribution not granted.'
        return result
    segments=plan['segments']; pairs=anchors_for(item,segments)
    if not pairs:
        result['reason']='No observed adjacent isolated gain edge for this exact output attempt.'
        return result
    probe=commands.probe(path,'metadata',['-show_streams','-show_format'])
    audio=[s for s in probe['streams'] if s.get('codec_type')=='audio']
    require(len(audio)==1 and audio[0]['codec_name']=='aac' and audio[0]['sample_rate']=='48000'
            and audio[0]['channels']==2,'AAC stereo48k required; no implicit format conversion')
    format_start=float(probe['format'].get('start_time',0))
    for index,(before,after) in enumerate(pairs,1):
        hint=after['outputs'][item['target']]['active_duration_ms']/1000+format_start
        clip=pcm_clip(path,max(0,hint-3),hint+3,directory,f'anchor-{index:02d}',commands)
        edge=locate_edge(clip,[before['observed_end'],after['observed_start']],
                         after['controls']['application']['gain_db']-before['controls']['application']['gain_db'])
        result['anchors'].append({'before_segment':before['segment_id'],'after_segment':after['segment_id'],
                                  'search_hint_pts':hint,**edge})
    good=[a for a in result['anchors'] if a['status']=='PASS']
    if len(good)!=len(result['anchors']):
        result['reason']='At least one predefined anchor was ambiguous; no favorable subset selected.'
        return result
    bounds=[max(a['monotonic_minus_pts_bounds'][0] for a in good),min(a['monotonic_minus_pts_bounds'][1] for a in good)]
    if bounds[0]>=bounds[1]:
        result['reason']='Early/late offset bounds do not intersect; drift/model uncertainty needs explicit review.'
        result['nonintersecting_offset_bounds']=bounds
        return result
    covered=[min(s['observed_start'] for pair in pairs for s in pair),max(s['observed_end'] for pair in pairs for s in pair)]
    result['alignment']={'status':'PASS','monotonic_minus_pts_bounds':bounds,'observed_span':covered,
        'anchors':len(good),'model':'Constant offset consistent with all measured anchors; no extrapolation outside anchor-pair span.',
        'limitation':'Bounds include polling and100ms spectral edge width; this is not sample-exact wall/media sync.'}
    for segment in segments:
        if not matching(segment,item) or segment['status']!='READY_FOR_ALIGNMENT' or segment['classification'] not in ('application_isolated','microphone_isolated'):
            continue
        lo,hi=segment['interior_monotonic']
        entry={'segment_id':segment['segment_id'],'classification':segment['classification'],'checks':{}}
        result['references'].append(entry)
        if lo<covered[0] or hi>covered[1]:
            entry['checks']['alignment']=gate('INCONCLUSIVE','reference outside measured anchor span; no silent extrapolation')
            continue
        certain=[lo-bounds[0],hi-bounds[1]]
        width=min(8,certain[1]-certain[0]);midpoint=sum(certain)/2
        if width<5:
            entry['checks']['interior']=gate('INCONCLUSIVE','less than five seconds certain stable interior')
            continue
        clip=pcm_clip(path,midpoint-width/2,midpoint+width/2,directory,f'segment-{segment["segment_id"]:03d}',commands)
        entry['selected_pts']=clip['actual_pts'];entry['original_stable_interior_monotonic']=[lo,hi]
        entry['coverage']='Fixed centered bounded interval, no selection by decoded quality; full-file continuity separate.'
        role='application' if segment['classification']=='application_isolated' else 'microphone'
        selected=[r for r in native_rows if r['segment_id']==segment['segment_id']]
        entry['checks']['native_rms']=robust_meter(clip,selected,role,bounds)
        entry['checks']['peak']=judged(max(clip['peak_dbfs'])<-.5 and not any(clip['saturated_samples']),
            'decoded stereo peak below-0.5dBFS, no abs(sample)>=1',peak_dbfs=clip['peak_dbfs'],saturated_samples=clip['saturated_samples'])
        entry['amplitude']={freq:[math.sqrt(statistics.mean(b['amplitude'][freq][c]**2 for b in clip['hann_100ms']))
                                 for c in (0,1)] for freq in ('440','997')}
        if role=='application':
            expected=-24+segment['controls']['application']['gain_db']-10*math.log10(2)
            violations=[{'index':i,'pts':w['pts_start'],'error_db':[v-expected for v in w['rms_dbfs']]}
                        for i,w in enumerate(clip['windows_20ms_step10ms']) if any(abs(v-expected)>=1 for v in w['rms_dbfs'])]
            entry['checks']['isolated_continuity']=judged(not violations,'every original20ms/10ms-step window within1dB of fixed fixture RMS',
                expected_rms_dbfs=expected,violations=violations,windows=len(clip['windows_20ms_step10ms']))
        else:
            entry['checks']['physical_440_present']=judged(min(entry['amplitude']['440'])>.00001,
                'controlled440Hz present while app capture muted; no microphone-noise/997-absence claim',
                amplitude_440=entry['amplitude']['440'],residual_997_diagnostic=entry['amplitude']['997'])
    result['gain_pairs']=[]
    for pair in plan['isolated_gain_pairs']:
        if pair['same_output_attempts'].get(item['target'])!=item['attempt_id']:continue
        low=next((r for r in result['references'] if r['segment_id']==pair['low_segment'] and 'amplitude' in r),None)
        high=next((r for r in result['references'] if r['segment_id']==pair['high_segment'] and 'amplitude' in r),None)
        if not low or not high:continue
        delta=[db(low['amplitude']['997'][c]/max(high['amplitude']['997'][c],1e-15)) for c in (0,1)]
        result['gain_pairs'].append(judged(all(abs(v-pair['expected_low_minus_high_db'])<1 for v in delta),
            'same-file isolated997Hz gain difference',low_segment=pair['low_segment'],high_segment=pair['high_segment'],
            expected_db=pair['expected_low_minus_high_db'],actual_db=delta,tolerance_db=1))
    result['checks']['isolated_gain_coverage']=gate('PASS' if result['gain_pairs'] else 'INCONCLUSIVE','at least one measured isolated same-file gain pair')
    result['checks']['isolated_microphone_coverage']=gate('PASS' if any('physical_440_present' in r['checks'] for r in result['references']) else 'INCONCLUSIVE','physical microphone measured with app capture muted')
    reference_checks=[*result['checks'].values(),*result['gain_pairs'],*(g for r in result['references'] for g in r['checks'].values())]
    result['reference_status']=combined(reference_checks)
    duration=float(probe['format']['duration'])
    result['events']=event_windows(item,plan,observed_rows,bounds,covered,path,directory,commands,
                                  extrapolated,[format_start,format_start+duration])
    event_checks=[g for event in result['events'] for g in event['checks'].values()]
    result['event_status']=combined(event_checks)
    result['sha256_after']=sha(path)
    result['checks']['stable_media']=judged(result['sha256_before']==result['sha256_after'],'media unchanged during offline analysis')
    checks=[*reference_checks,*event_checks,result['checks']['stable_media']]
    result['status']=combined(checks)
    result['whole_file_audio_continuity']=gate('INCONCLUSIVE','Only fixed reference and event windows decoded here; entire take coverage belongs to a separate instrument.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan',type=pathlib.Path,required=True)
    parser.add_argument('--media',type=pathlib.Path,required=True)
    parser.add_argument('--extrapolated-event-diagnostics',action='store_true',
        help='Decode conditional event search windows beyond anchors; alignment remains INCONCLUSIVE with unbounded drift error.')
    args=parser.parse_args();directory=ROOT/'var/evidence'/f'h13-native-pcm-{time.time_ns()}';directory.mkdir(parents=True)
    report={'version':1,'status':'FAIL','acceptance':'NOT_EVALUATED','policy':POLICY,'media':[],
            'extrapolated_event_diagnostics':args.extrapolated_event_diagnostics}
    print(directory,flush=True)
    try:
        plan_path=args.plan.resolve(strict=True);manifest=args.media.resolve(strict=True)
        plan=json.loads(plan_path.read_text());document=read_manifest(manifest)
        require(plan['acceptance']=='NOT_EVALUATED' and not plan.get('error'),'valid native audio plan required')
        require(not plan['observations']['parse_errors'],'plan contains incomplete/invalid observations')
        samples=pathlib.Path(plan['meter_samples']['path'])
        require(sha(samples)==plan['meter_samples']['sha256'],'native meter samples changed')
        native_rows=[json.loads(line) for line in samples.open()]
        observed=pathlib.Path(plan['observed_samples']['path'])
        require(sha(observed)==plan['observed_samples']['sha256'],'all-observation samples changed')
        observed_rows=[json.loads(line) for line in observed.open()]
        require(len(observed_rows)==plan['observations']['rows_for_pid'],'all-observation coverage mismatch')
        report['inputs']={'plan':str(plan_path),'plan_sha256':sha(plan_path),'manifest':str(manifest),'manifest_sha256':sha(manifest),
                          'script_sha256':sha(pathlib.Path(__file__)),'hann_helper_sha256':sha(ROOT/'scripts/verify_h10_audio.py')}
        write_json(directory/'plan.snapshot.json',plan);write_json(directory/'media.snapshot.json',document)
        for index,item in enumerate(document['media'],1):
            require(item['pid']==plan['pid'],'manifest PID differs from native plan')
            output=directory/f'{index:02d}-{item["target"]}-{item["attempt_id"]}';output.mkdir()
            commands=Commands(output)
            try:result=analyze_file(item,plan,native_rows,output,commands,args.extrapolated_event_diagnostics,observed_rows)
            except Exception as error:
                result={'mapping':item,'status':'FAIL','error':repr(error),'traceback':traceback.format_exc()}
            report['media'].append(result);write_json(directory/'report.json',report)
        report['status']=combined(gate(m['status'],'bounded audio evidence') for m in report['media'])
    except BaseException as error:
        report['error']={'message':repr(error),'traceback':traceback.format_exc()}
    finally:
        write_json(directory/'report.json',report)
    print(json.dumps({'report':str(directory/'report.json'),'status':report['status'],'acceptance':report['acceptance']}))
    return {'PASS':0,'FAIL':1,'INCONCLUSIVE':2}[report['status']]


if __name__=='__main__':raise SystemExit(main())
