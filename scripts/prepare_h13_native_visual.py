#!/usr/bin/env python3
"""Prepare bounded OFFLINE visual evidence for the actual H13 native production.

No app/device/control imports. Planning reads observer JSONL and the closed
media manifest accepted by analyse_h13_native.py. Do not run extraction while
physical production is active. Planning itself does not decode any media.

  python3 scripts/prepare_h13_native_visual.py plan --observations OBS.jsonl \
      --media media-manifest.json
  var/verify-python/bin/python scripts/prepare_h13_native_visual.py extract \
      --plan var/evidence/h13-native-visual-plan-.../plan.json

The plan fixes geometry, extraction windows and numerical criteria BEFORE any
pixels are seen. active_duration_ms gives a SEARCH ESTIMATE, not a media clock
or exact cross-output alignment. Each destination is located independently.
The 4 Hz contact sheets are visual samples, NOT evidence of frame cadence.
Only transition-probe RGB uses every decoded frame, with original PTS retained.
Semantic identity, title spelling, camera content and common event mapping
remain explicit human-review items. No OCR and no blanket acceptance PASS.

Requires closed/stable inputs. Images/metrics go into new evidence directories;
source media and production files are never changed. FFmpeg decoder, filter
and encoder thread limits are one; calls are sequential. Ctrl+C stops extraction. Full-file structural/audio
checks belong to analyse_h13_native.py, not this bounded visual instrument.
"""
import argparse
import json
import math
import pathlib
import re
import statistics
import subprocess
import time

from analyse_h13_native import read_manifest, sha, write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
IDS = {'window': 'source-2', 'camera': 'source-4', 'lower': 'source-6', 'timer': 'source-8'}
# Logical design960 coordinates. No ROI crosses the timer/PiP/lower boundaries.
BOXES = {'scene_probe': [360, 48, 240, 40], 'lower': [32, 368, 640, 140],
         'timer': [32, 32, 280, 130], 'camera_pip': [640, 32, 288, 162]}
POLICY = {
    'canvas': [1920, 1080], 'logical_canvas': [960, 540], 'search_margin_seconds': 3,
    'contact_sheet_fps': 4, 'maximum_events': 24, 'maximum_window_seconds': 12,
    'periodic_first_seconds': 5, 'periodic_interval_seconds': 60,
    'periodic_maximum_per_medium': 65,
    'white_mask': {'min_channel_gt': 185, 'channel_range_lt': 55},
    'glyph_change': {'minimum_white_pixels_each': 100, 'minimum_xor_pixels_gt': 100,
                     'scope': 'lower title at design resolution; image review still required'},
    'timer_change': {'minimum_xor_pixels_gt': 50,
                     'scope': 'timer glyph region at design resolution; phase review still required'},
    'transition_preconditions': {'endpoint_rgb_distance_gt': 20, 'endpoint_max_channel_span_lte': 10},
    'transition': {'interior_alpha': [.1, .9], 'residual_fraction_lte': .15,
                   'cut_max_intermediate_frames': 0, 'fade_min_intermediate_frames': 10,
                   'fade_min_distinct_alpha_hundredths': 10},
    'limits': [
        'Native duration locates bounded search windows; it does not establish frame or A/V alignment.',
        'No binary image equality is required across independent encoders.',
        'Glyph-mask changes do not prove the intended spelling or running/paused semantics.',
        'Transition metrics are inconclusive if the selected region lacks stable contrasting endpoints.',
        'A cancelled Fade is reviewed separately and cannot pass the complete-Fade criterion.',
        'An unchanged camera visibility is no hide event; rejected gestures require separate UI evidence.',
        'Periodic full frames show the owned fixture counter for human review; pixel hashes never prove movement.',
        'No whole-file video freeze, audio continuity, soak or H13 acceptance is inferred from these samples.'
    ]}


def signature(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def descriptor(row):
    s = row['state']; graph = s['project']['graph']
    definitions = {v['id']: v for v in graph['sources']}
    runtime = {v['id']: v for v in s['overlays']['runtime']['sources']}
    lower = definitions.get(IDS['lower'], {}).get('overlay', {}).get('widget', {})
    timer = runtime.get(IDS['timer'], {})
    camera = [(scene['id'], layer['id'], layer['layouts']['horizontal']['visible'])
              for scene in graph['scenes'] for layer in scene['layers'] if layer['source_id'] == IDS['camera']]
    return {'title': lower.get('title'), 'timer_phase': timer.get('phase'),
            'timer_remaining_ms': timer.get('remaining_ms'), 'camera_visibility': camera,
            'scene': graph['active_scene'], 'transition': s['transition']}


def search_estimates(previous, current):
    result = []
    for target, slot in current['state']['outputs'].items():
        if not slot['native_busy'] or slot['phase'] != 'active' or not slot['attempt_id']:
            continue
        old = previous['state']['outputs'][target]
        hi = slot['active_duration_ms']/1000
        lo = old['active_duration_ms']/1000 if old['attempt_id'] == slot['attempt_id'] else None
        result.append({'pid': current['state']['pid'], 'target': target,
                       'attempt_id': slot['attempt_id'], 'native_search_seconds': hi,
                       'previous_native_seconds': lo,
                       'output_frame_search_seconds': slot['stats']['output_frames']/slot['video']['fps'],
                       'video': slot['video']})
    return result


def derive_events(rows):
    iterator = iter(rows)
    events = []; transitions = {}; previous = next(iterator); before = descriptor(previous)
    for row in iterator:
        after = descriptor(row); state = row['state']; tr = after['transition']
        estimates = search_estimates(previous, row)
        details = []
        op = tr['operation_id']
        if estimates and op != before['transition']['operation_id'] and tr.get('target_scene'):
            event = {'kind': tr['kind'], 'operation_id': op, 'transition': tr,
                     'scene_before': before['scene'], 'scene_after': after['scene']}
            details.append(event); transitions[op] = event
        if op in transitions:
            transitions[op]['last_transition'] = tr
            transitions[op]['last_scene'] = after['scene']
        if estimates and before['title'] is not None and after['title'] != before['title']:
            details.append({'kind': 'lower_title', 'before': before['title'], 'after': after['title']})
        if estimates and before['timer_phase'] is not None and after['timer_phase'] != before['timer_phase']:
            details.append({'kind': 'timer_'+str(after['timer_phase']), 'before': before['timer_phase'],
                            'remaining_ms': after['timer_remaining_ms']})
        if estimates and after['camera_visibility'] != before['camera_visibility']:
            details.append({'kind': 'camera_visibility', 'before': before['camera_visibility'],
                            'after': after['camera_visibility']})
        for detail in details:
            detail.update(event_id=f'event-{len(events)+1:02d}', revision=state['revision'],
                          action=state['last_action'], observer_bracket=[previous['monotonic'], row['monotonic']],
                          search_estimates=estimates)
            events.append(detail)
        previous, before = row, after
    return events


def plan(args):
    observations = args.observations.resolve(strict=True); manifest = args.media.resolve(strict=True)
    before = signature(observations)
    rows = [json.loads(line) for line in observations.read_text().splitlines()]
    if not rows or signature(observations) != before:
        raise ValueError('observer must be nonempty and stable; stop observation before final planning')
    if len({r['state']['pid'] for r in rows}) != 1:
        raise ValueError('one owner PID per visual plan required')
    events = derive_events(rows)
    if len(events) > POLICY['maximum_events']:
        raise ValueError('more than 24 events: split observation takes explicitly; do not silently omit events')
    media = read_manifest(manifest)['media']
    tasks = []
    for event in events:
        duration = event.get('transition', {}).get('duration_ms', 0)/1000
        length = min(POLICY['maximum_window_seconds'], max(8, duration+6))
        for estimate in event['search_estimates']:
            matches = [m for m in media if all(m[k] == estimate[k] for k in ('pid', 'target', 'attempt_id'))]
            if not matches:
                event.setdefault('unmapped_searches', []).append(estimate)
                continue
            if estimate['video'] != {'width': 1920, 'height': 1080, 'fps': 30}:
                raise ValueError('this geometry/criterion plan is specifically 1080p30')
            tasks.append({'event_id': event['event_id'], 'kind': event['kind'], 'media': matches[0],
                          'search_start_seconds': max(0, estimate['native_search_seconds']-3),
                          'search_duration_seconds': length,
                          'cancelled': event.get('last_transition', {}).get('phase') == 'cancelled'})
    periodic = []
    for item in media:
        durations = [r['state']['outputs'][item['target']]['active_duration_ms']/1000
                     for r in rows if r['state']['pid'] == item['pid'] and
                     r['state']['outputs'][item['target']]['attempt_id'] == item['attempt_id']]
        if not durations:
            continue
        first = math.ceil(max(0, min(durations)-5)/60)*60+5
        points = list(range(int(first), int(max(durations)-.5)+1, 60))
        if len(points) > POLICY['periodic_maximum_per_medium']:
            raise ValueError('more than 65 periodic images for a medium: split takes explicitly')
        periodic.extend({'media':item, 'native_search_seconds':point,
                         'scope':'full native frame; manually inspect owned fixture counter, no hash-motion gate'}
                        for point in points)
    directory = ROOT/'var/evidence'/f'h13-native-visual-plan-{time.time_ns()}'; directory.mkdir(parents=True)
    snapshot = directory/'observations.snapshot.jsonl'; snapshot.write_bytes(observations.read_bytes())
    if signature(observations) != before:
        raise ValueError('observer changed while copying; discard this incomplete plan and retry after stop')
    value = {'version': 1, 'scope': 'PREDECODE_PLAN_NOT_ACCEPTANCE', 'policy': POLICY,
             'geometry_logical': BOXES, 'source_ids': IDS,
             'observations': {'path': str(snapshot), 'sha256': sha(snapshot), 'rows': len(rows)},
             'manifest': {'path': str(manifest), 'sha256': sha(manifest)},
             'script_sha256': sha(pathlib.Path(__file__)),
             'events': events, 'tasks': tasks, 'periodic_samples': periodic,
             'camera_visibility_changes': [e for e in events if e['kind'] == 'camera_visibility'],
             'review': {'status': 'INCONCLUSIVE', 'required': ['source identity and controlled camera',
                         'correct before/after title', 'timer advance/pause/resume',
                         'matching events in both outputs', 'rejected gestures kept separate']}}
    write_json(directory/'plan.json', value)
    print(directory/'plan.json')


def run(command, directory, label, stdout=None):
    log = directory/(label+'.stderr.log')
    entry = {'argv': command, 'returncode': None, 'stderr': str(log)}
    try:
        with log.open('wb') as error:
            if stdout:
                with stdout.open('wb') as output:
                    done = subprocess.run(command, stdout=output, stderr=error, timeout=120)
            else:
                done = subprocess.run(command, stdout=subprocess.PIPE, stderr=error, timeout=120)
        entry['returncode'] = done.returncode
    finally:
        entry['stderr_sha256'] = sha(log) if log.exists() else None
        write_json(directory/(label+'.command.json'), entry)
    if done.returncode:
        raise RuntimeError(f'{label}: ffmpeg/ffprobe failed; preserve stderr')
    return done.stdout if not stdout else None


def white_mask(image):
    return bytes(min(p)>185 and max(p)-min(p)<55 for p in image.convert('RGB').getdata())


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def transition_metrics(rgb, pts, task):
    colors = [list(rgb[i:i+3]) for i in range(0, len(rgb), 3)]
    if len(colors) != len(pts) or len(colors) < 30:
        return {'status': 'FAIL', 'reason': 'RGB/PTS count mismatch or fewer than 30 frames',
                'colors': colors, 'pts': pts}
    first, last = colors[:15], colors[-15:]
    a = [statistics.median(c[k] for c in first) for k in range(3)]
    b = [statistics.median(c[k] for c in last) for k in range(3)]
    contrast = distance(a,b)
    span = max(max(c[k] for c in group)-min(c[k] for c in group)
               for group in (first,last) for k in range(3))
    result = {'status':'INCONCLUSIVE', 'original_pts':pts, 'rgb':colors,
              'endpoint_before':a, 'endpoint_after':b, 'endpoint_distance':contrast,
              'endpoint_max_channel_span':span}
    if task['cancelled']:
        result['reason']='cancelled transition: inspect excursion and return; not a complete-Fade gate'
        return result
    if contrast <= 20 or span > 10:
        result['reason']='fixed probe does not have stable contrasting endpoints; no alternative ROI selected after pixels'
        return result
    delta = [y-x for x,y in zip(a,b)]; norm = contrast**2
    alphas = [sum((c[k]-a[k])*delta[k] for k in range(3))/norm for c in colors]
    residual = [distance(c,[a[k]+alpha*delta[k] for k in range(3)])/contrast
                for c,alpha in zip(colors,alphas)]
    middle = [i for i,(alpha,error) in enumerate(zip(alphas,residual)) if .1<alpha<.9 and error<=.15]
    distinct = len({round(alphas[i]*100) for i in middle})
    accepted = len(middle)==0 if task['kind']=='cut' else len(middle)>=10 and distinct>=10
    result.update(status='PASS' if accepted else 'FAIL',
                  reason='fixed probe Cut/Fade intermediate-frame criterion; semantic review still required',
                  alpha=alphas, residual_fraction=residual, intermediate_indices=middle,
                  distinct_alpha_hundredths=distinct)
    return result


def extract(args):
    from PIL import Image, ImageDraw
    path = args.plan.resolve(strict=True); value = json.loads(path.read_text())
    if value['version'] != 1 or value['policy'] != POLICY or value['geometry_logical'] != BOXES:
        raise ValueError('plan does not match this frozen policy/geometry')
    directory = ROOT/'var/evidence'/f'h13-native-visual-extract-{time.time_ns()}'; directory.mkdir(parents=True)
    report = {'acceptance':'NOT_EVALUATED', 'coverage_status':'INCONCLUSIVE', 'plan_sha256':sha(path),
              'plan':str(path), 'script_sha256':sha(pathlib.Path(__file__)), 'tasks':[],
              'periodic_samples':[], 'media':{}}
    try:
        for task in value['tasks']:
            medium = pathlib.Path(task['media']['path'])
            if str(medium) not in report['media']:
                report['media'][str(medium)] = {'sha256_before':sha(medium)}
            label = task['event_id']+'-'+task['media']['target']+'-'+str(task['media']['attempt_id'])
            output = directory/label; output.mkdir()
            raw = run(['ffprobe','-v','error','-show_entries','format=start_time:stream=codec_type,width,height,avg_frame_rate',
                       '-of','json',str(medium)],output,'probe')
            probe = json.loads(raw); write_json(output/'probe.json',probe)
            report['media'][str(medium)]['probe']=probe
            video = next(s for s in probe['streams'] if s['codec_type']=='video')
            if (video['width'],video['height'],video['avg_frame_rate']) != (1920,1080,'30/1'):
                raise ValueError('media does not match fixed 1080p30 geometry')
            start = task['search_start_seconds']; length = task['search_duration_seconds']
            original_start = float(probe['format'].get('start_time',0))+start
            trim = f'trim=start={original_start:.6f}:end={original_start+length:.6f}'
            # Bound input demux/decode too. trim alone drops later frames but
            # could keep reading the remainder of a long production file.
            base = ['ffmpeg','-nostdin','-v','info','-threads','1','-filter_threads','1','-copyts',
                    '-ss',f'{start:.6f}','-t',f'{length+.5:.6f}','-i',str(medium),'-an','-threads:v','1']
            # fps=4 intentionally samples/repeats frames for review sheets only.
            run([*base,'-vf',trim+',scale=960:540:flags=area,fps=4,showinfo,setpts=PTS-STARTPTS',
                 '-t',f'{length:.6f}','-frames:v',str(math.ceil(length*4)+1),'-fps_mode','passthrough',
                 str(output/'frame-%03d.png')],output,'sheet-frames')
            files = sorted(output.glob('frame-*.png'))
            if not files: raise ValueError('bounded search returned no frames')
            sheet = Image.new('RGB',(960, len(files)*155),'#18202b'); draw=ImageDraw.Draw(sheet)
            masks = {'lower':[], 'timer':[]}
            for i, filename in enumerate(files):
                with Image.open(filename) as image:
                    image=image.convert('RGB'); thumbnail=image.resize((240,135))
                    sheet.paste(thumbnail,(0,i*155+20))
                    draw.text((0,i*155),f'{filename.name} sampled offset ~{i/4:.2f}s',fill='white')
                    for name,xpos in [('lower',250),('timer',680)]:
                        x,y,w,h=BOXES[name]; crop=image.crop((x,y,x+w,y+h))
                        masks[name].append(white_mask(crop))
                        crop.thumbnail((420 if name=='lower' else 280,130)); sheet.paste(crop,(xpos,i*155+20))
            sheet.save(output/'contact-sheet.png')
            entry={'task':task, 'frames_sampled':len(files), 'contact_sheet':str(output/'contact-sheet.png'),
                   'status':'INCONCLUSIVE', 'reason':'human mapping/spelling/phase review required', 'glyph_metrics':{}}
            for name,values in masks.items():
                entry['glyph_metrics'][name]={'white_pixels':[sum(v) for v in values],
                    'xor_adjacent':[sum(a!=b for a,b in zip(left,right)) for left,right in zip(values,values[1:])],
                    'xor_first_last':sum(a!=b for a,b in zip(values[0],values[-1]))}
            if task['kind'] in ('cut','fade'):
                x,y,w,h=BOXES['scene_probe']; rawpath=output/'scene-probe.rgb'
                run([*base,'-vf',trim+f',crop={w*2}:{h*2}:{x*2}:{y*2},scale=1:1:flags=area,format=rgb24,showinfo,setpts=PTS-STARTPTS',
                     '-t',f'{length:.6f}','-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','-'],
                    output,'scene-probe',rawpath)
                stderr=(output/'scene-probe.stderr.log').read_text()
                pts=[float(p) for p in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([^\s]+)',stderr)]
                entry['transition_probe']=transition_metrics(rawpath.read_bytes(),pts,task)
            report['tasks'].append(entry); write_json(directory/'report.json',report)
        # Fixed periodic full frames support review of the fixture's rendered
        # counter over the long take. They cannot rule out freezes between
        # samples, nor can encoder noise/image hashes establish advancement.
        periodic_directory=directory/'periodic'; periodic_directory.mkdir()
        for index, sample in enumerate(value['periodic_samples'],1):
            medium=pathlib.Path(sample['media']['path']); key=str(medium)
            label=f'periodic-{index:03d}-{sample["media"]["target"]}-{sample["media"]["attempt_id"]}'
            if key not in report['media']:
                report['media'][key]={'sha256_before':sha(medium)}
            probe=report['media'][key].get('probe')
            if probe is None:
                raw=run(['ffprobe','-v','error','-show_entries','format=start_time:stream=codec_type,width,height,avg_frame_rate',
                         '-of','json',key],periodic_directory,label+'-probe')
                probe=json.loads(raw); report['media'][key]['probe']=probe
            video=next(s for s in probe['streams'] if s['codec_type']=='video')
            if (video['width'],video['height'],video['avg_frame_rate']) != (1920,1080,'30/1'):
                raise ValueError('periodic media does not match fixed 1080p30 geometry')
            start=sample['native_search_seconds']; absolute=float(probe['format'].get('start_time',0))+start
            image_path=periodic_directory/(label+'.png')
            run(['ffmpeg','-nostdin','-v','info','-threads','1','-filter_threads','1','-copyts',
                 '-ss',str(start),'-t','0.5','-i',key,'-an','-threads:v','1',
                 '-vf',f'trim=start={absolute:.6f},showinfo,setpts=PTS-STARTPTS',
                 '-frames:v','1','-fps_mode','passthrough',str(image_path)],periodic_directory,label)
            if not image_path.exists(): raise ValueError('periodic frame missing')
            log=(periodic_directory/(label+'.stderr.log')).read_text()
            pts=[float(p) for p in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([^\s]+)',log)]
            report['periodic_samples'].append({'sample':sample,'image':str(image_path),'sha256':sha(image_path),
                'first_original_pts':pts[0] if pts else None,'status':'INCONCLUSIVE',
                'reason':'inspect fixture counter in original full frame; no automatic motion assertion'})
            write_json(directory/'report.json',report)
        for filename, item in report['media'].items():
            item['sha256_after']=sha(pathlib.Path(filename)); item['unchanged']=item['sha256_before']==item['sha256_after']
            if not item['unchanged']: raise ValueError('source media changed during extraction')
        report['extraction_completed']=True
    except Exception as error:
        report['error']=repr(error); raise
    finally:
        write_json(directory/'report.json',report); print(directory/'report.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('plan'); p.add_argument('--observations',type=pathlib.Path,required=True)
    p.add_argument('--media',type=pathlib.Path,required=True)
    p=sub.add_parser('extract'); p.add_argument('--plan',type=pathlib.Path,required=True)
    args=parser.parse_args()
    plan(args) if args.mode=='plan' else extract(args)

if __name__=='__main__': main()
