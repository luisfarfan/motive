#!/usr/bin/env python3
"""Decode the owned H12 GPUI walkthrough; never sends production commands.

Use the checkout-local verification Python (Pillow). The observer must contain
one recording and one stream, with UI-origin edits/animations and mixer stages.
Frame counters associate observations with media time (4 Hz sampling, not a
sample-exact audio latency measurement). Preserve failures in the JSON report.
"""
import argparse
import array
import hashlib
import io
import json
import math
import pathlib
import statistics
import subprocess

from PIL import Image
from verify_h10_audio import tonal_amplitude, power


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def db(x):
    return 20 * math.log10(max(x, 1e-12))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(path, rows, output, directory, result):
    samples = [r for r in rows if r['state']['output'] == output]
    assert len(samples) > 40
    states = [r['state'] for r in samples]
    result.update(path=str(path), sha256=sha(path), observed_samples=len(samples))
    assert all(s['encoding']['selected_hardware'] for s in states)
    assert all(s['last_action'].startswith('UI ·') for s in states)
    assert not any(s['issues'] or s['output_failure'] for s in states)
    for key in ('lagged_frames', 'output_dropped_frames', 'video_skipped_frames'):
        values = [s['stats'][key] for s in states]
        result[key] = {'first': values[0], 'last': values[-1], 'max': max(values)}
        assert max(values) == 0, (key, result[key])
    for field, values in {
        'source_instances': [{s['id']: s['instance_id'] for s in x['sources']} for x in states],
        'audio_instances': [{s['id']: s['instance_id'] for s in x['audio_mixer']['runtime']['inputs']} for x in states],
        'overlay_children': [{s['id']: s['child_instances_created'] for s in x['overlays']['runtime']['sources']} for x in states],
    }.items():
        assert all(v == values[0] for v in values), field
        result[field] = values[0]
    assert all(s['audio_mixer']['monitoring'] == 'off' for s in states)
    assert all(s['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0 for s in states)
    decode = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    result['decode_stderr'] = decode.stderr.decode()
    assert not decode.stderr
    probe = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)))
    result['probe'] = probe
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['codec_name'], video['width'], video['height']) == ('h264', 960, 540)
    assert (audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2)
    frames = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)))['frames']
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    gaps = [b-a for a, b in zip(pts, pts[1:])]
    result['timestamps'] = {'frames': len(pts), 'first': pts[0], 'last': pts[-1], 'max_interior_gap_s': max(gaps[:-4]), 'max_gap_s': max(gaps), 'gaps_over_50ms': [{'frame': i+1, 'gap': g} for i, g in enumerate(gaps) if g > .05]}
    assert min(gaps) > 0 and max(gaps[:-4]) < .05 and max(gaps) < .15
    packets = json.loads(run('ffprobe', '-v', 'error', '-show_packets', '-show_entries', 'packet=stream_index,pts_time,dts_time,duration_time', '-of', 'json', str(path)))['packets']
    for index in (video['index'], audio['index']):
        dts = [float(p['dts_time']) for p in packets if p['stream_index'] == index and 'dts_time' in p]
        assert all(b > a for a, b in zip(dts, dts[1:])), ('dts', index)
    ap = [p for p in packets if p['stream_index'] == audio['index']]
    agaps = [float(b['pts_time'])-float(a['pts_time']) for a, b in zip(ap, ap[1:])]
    result['audio_max_packet_gap_s'] = max(agaps)
    assert min(agaps) > 0 and max(agaps) < .025
    pcm = array.array('f', run('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'))
    result['audio_duration_s'] = len(pcm)/48000
    result['peak_dbfs'] = db(max(map(abs, pcm)))
    assert result['peak_dbfs'] < -.5

    def time_of(row):
        return row['state']['stats']['output_frames']/30 + pts[0]

    # Contiguous mixer configurations; single-second interior spectral samples.
    groups = []
    for row in samples:
        ins = row['state']['audio_mixer']['store']['inputs']
        key = tuple((i['gain_db'], i['muted']) for i in ins)
        if not groups or groups[-1]['key'] != key:
            groups.append({'key': key, 'rows': []})
        groups[-1]['rows'].append(row)
    stages = []
    for group in groups:
        lo, hi = time_of(group['rows'][0]), time_of(group['rows'][-1])
        if hi-lo < 4:
            continue
        t = lo+1.5
        chunk = pcm[round(t*48000):round((t+1)*48000)]
        stage = {'config': group['key'], 'start': lo, 'end': hi, 'sample_start': t, 'a440': tonal_amplitude(chunk, 440), 'a997': tonal_amplitude(chunk, 997), 'rms_dbfs': db(math.sqrt(sum(x*x for x in chunk)/len(chunk)))}
        if group['key'][0][1] != group['key'][1][1]:
            index = 1 if group['key'][0][1] else 0
            aligned = [r for r in group['rows'] if lo+1 < time_of(r) < hi-.5]
            a, b = time_of(aligned[0]), time_of(aligned[-1])
            native = [r['state']['audio_mixer']['runtime']['inputs'][index]['levels']['rms_dbfs'][0] for r in aligned]
            decoded = [db(math.sqrt(sum(x*x for x in pcm[n:n+960])/960)) for n in range(round(a*48000), round(b*48000)-959, 960)]
            stage['meter'] = {'input': index, 'window': [a,b], 'native_median_dbfs': statistics.median(native), 'decoded_median_dbfs': statistics.median(decoded)}
            stage['meter']['error_db'] = stage['meter']['decoded_median_dbfs']-stage['meter']['native_median_dbfs']
        stages.append(stage)
    result['audio_stages'] = stages
    both = next(s for s in stages if s['config'] == ((0, False), (-18, False)))
    lower = next(s for s in stages if s['config'] == ((0, False), (-30, False)))
    mic_only = next(s for s in stages if s['config'][1][1] and not s['config'][0][1])
    tone_only = next(s for s in stages if s['config'][0][1] and not s['config'][1][1])
    result['tone_gain_delta_db'] = db(lower['a440']/both['a440'])
    assert -13 < result['tone_gain_delta_db'] < -11
    assert both['a440'] > .005 and both['a997'] > .00001
    assert mic_only['a440'] < both['a440']*.03
    assert tone_only['a997'] < both['a997']*.02
    assert abs(db(tone_only['a440']/both['a440'])) < .6
    assert all(abs(s['meter']['error_db']) < 2 for s in stages if 'meter' in s)

    # Sample every 100 ms across each observed scene switch while the tone is
    # unmuted; a native Cut/Fade cannot interrupt the global audio clock.
    transitions = {}
    first_op = states[0]['transition']['operation_id']
    for row in samples:
        tr = row['state']['transition']
        if tr['operation_id'] > first_op and tr['operation_id'] not in transitions:
            t = time_of(row)
            transitions[tr['operation_id']] = {'time': t, 'kind': tr['kind'], 'duration_ms': tr['duration_ms']}
            nearby = [r for r in samples if t-.3 <= time_of(r) <= t+1.5]
            assert not any(all(i['muted'] for i in r['state']['audio_mixer']['store']['inputs']) for r in nearby)
            blocks = [pcm[n:n+4800] for n in range(round((t-.3)*48000),round((t+1.5)*48000),4800)]
            transitions[tr['operation_id']]['rms_min'] = min(math.sqrt(sum(v*v for v in b)/len(b)) for b in blocks)
            assert transitions[tr['operation_id']]['rms_min'] > .00001
            if not any(r['state']['audio_mixer']['store']['inputs'][1]['muted'] for r in nearby):
                amp = [power(pcm[n:n+4800],440) for n in range(round((t-.3)*48000),round((t+1.5)*48000),4800)]
                transitions[tr['operation_id']]['tone_min'] = min(amp)
                assert min(amp) > lower['a440']*.5
    result['transitions'] = transitions
    assert {'cut','fade'} <= {v['kind'] for v in transitions.values()}

    def frame(t, name):
        data = run('ffmpeg','-nostdin','-v','error','-ss',str(max(t,0)),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-')
        (directory/f'{output}-{name}.png').write_bytes(data)
        return Image.open(io.BytesIO(data)).convert('RGB')

    def white(image, box=(40,32,600,172)):
        return sum(min(p)>190 for p in image.crop(box).getdata())

    def difference(a,b,box):
        return sum(max(abs(x-y) for x,y in zip(p,q))>30 for p,q in zip(a.crop(box).getdata(),b.crop(box).getdata()))

    for op, tr in transitions.items():
        t=tr['time']; before=frame(t-.5,f'scene-{op}-before'); after=frame(t+1.5,f'scene-{op}-after')
        box=(32,8,800,24)
        tr['changed_pixels']=difference(before,after,box)
        assert tr['changed_pixels']>1000
        if tr['kind']=='fade':
            middle=frame(t+.35,f'scene-{op}-middle')
            means=[statistics.mean(sum(p)/3 for p in im.crop(box).getdata()) for im in (before,middle,after)]
            tr['background_means_before_middle_after']=means
            assert min(means[0],means[2])+5 < means[1] < max(means[0],means[2])-5

    original = frame(4,'original')
    changed = next(r for r in samples if 'update_overlay' in r['state']['last_action'])
    edited = frame(time_of(changed)+1,'edited')
    textdiff = sum(max(abs(a-b) for a,b in zip(p,q))>40 for p,q in zip(original.crop((40,32,600,172)).getdata(),edited.crop((40,32,600,172)).getdata()))
    result['text_changed_pixels'] = textdiff
    assert textdiff > 500
    first_job = states[0]['overlays']['runtime']['animations']['last_operation_id']
    jobs = {}
    for row in samples:
        for job in row['state']['overlays']['runtime']['animations']['jobs']:
            if job['operation_id'] <= first_job:
                continue
            entry = jobs.setdefault(job['operation_id'], {'first_time':time_of(row), 'job':job})
            entry['job'] = job
    result['animation_jobs'] = jobs
    for op, entry in jobs.items():
        job = entry['job']; assert job['phase'] in ('completed','cancelled') and not job['pending_ack']
        if job['layer_id'] != 'layer-5':
            continue
        t = entry['first_time']; before = frame(t-.5,f'animation-{op}-before'); after = frame(t+job['duration_ms']/1000+.5,f'animation-{op}-after')
        entry['white_before'],entry['white_after'] = white(before),white(after)
        if job['kind'].endswith('_out'):
            assert entry['white_before'] > 500 and entry['white_after'] < 20
        else:
            assert entry['white_before'] < 20 and entry['white_after'] > 500
    # Transparent third exposes background; semi-transparent and opaque thirds
    # are distinct in the decoded frame. The local video and owned-window tick
    # must both change, independently of text/widget animation.
    a,b = frame(2,'composition-a'),frame(3,'composition-b')
    alpha = [a.getpixel((x,280)) for x in (60,110,160)]
    result['alpha_samples_rgb'] = alpha
    assert alpha[0][1]<60 and 60<alpha[1][1]<190 and alpha[2][1]>180
    result['motion'] = {}
    for label, box in {'video':(640,220,928,382),'owned_window':(640,32,928,194)}.items():
        n = sum(max(abs(x-y) for x,y in zip(p,q))>30 for p,q in zip(a.crop(box).getdata(),b.crop(box).getdata()))
        result['motion'][label] = n; assert n>30,(label,n)
    result['lower_third_white_pixels']=white(a,(32,368,672,508))
    # Recovery rebuilds reset the lower-third event before the repeat recording;
    # its visible native composition is verified in the preceding RTMP clip.
    if output=='streaming':
        assert result['lower_third_white_pixels']>500
    running = next(r for r in samples if any(x['id']=='source-10' and x['phase']=='running' for x in r['state']['overlays']['runtime']['sources']))
    t=time_of(running); ca,cb=frame(t+2,'countdown-a'),frame(t+6,'countdown-b')
    result['countdown_changed_pixels']=difference(ca,cb,(304,220,592,340))
    assert result['countdown_changed_pixels']>20
    if output=='streaming':
        alert = next(r for r in samples if any(x['id']=='source-28' and x['phase']=='visible' for x in r['state']['overlays']['runtime']['sources']))
        t=time_of(alert); aa,ab=frame(t-.5,'alert-before'),frame(t+.6,'alert-visible')
        result['alert_changed_pixels']=difference(aa,ab,(640,32,928,194))
        assert result['alert_changed_pixels']>500
        paused = next(r for r in samples if any(x['id']=='source-14' and x.get('media_state')=='paused' for x in r['state']['overlays']['runtime']['sources']))
        t=time_of(paused); pa,pb=frame(t+1,'video-paused-a'),frame(t+3,'video-paused-b')
        result['paused_video_changed_pixels']=difference(pa,pb,(640,220,928,382))
        assert result['paused_video_changed_pixels']<50
    result['ok'] = True


def analyze_scale(path, rows, directory):
    """First take contains the native BRB Scale/cancel and visible lower third."""
    samples=[r for r in rows if r['state']['output']=='recording']
    jobs={}
    for row in samples:
        t=row['state']['stats']['output_frames']/30
        for job in row['state']['overlays']['runtime']['animations']['jobs']:
            if job['kind'] not in ('scale_in','scale_out'):
                continue
            item=jobs.setdefault(job['operation_id'],{'first':t})
            if job['phase']=='cancelled' and 'cancelled_at' not in item:
                item['cancelled_at']=t
            item['job']=job
    entry=next(v for v in jobs.values() if v['job']['kind']=='scale_in')
    cancel=next(v for v in jobs.values() if v['job']['kind']=='scale_out' and v['job']['phase']=='cancelled')
    times={'scale-in-start':entry['first']+.1,'scale-in-middle':entry['first']+.6,'scale-in-end':entry['first']+1.5,
           'scale-out-partial':cancel['first']+2.5,'scale-cancelled':cancel['cancelled_at']+.1,'lower-third-recorded':2}
    counts={}
    for name,t in times.items():
        data=run('ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-')
        (directory/f'{name}.png').write_bytes(data)
        im=Image.open(io.BytesIO(data)).convert('RGB')
        pixels=im.crop((400,40,560,180)).getdata()
        counts[name]={'time':t,'mint_pixels':sum(g>80 and g>r*1.5 and g>b*1.1 for r,g,b in pixels)}
        if name=='lower-third-recorded':
            counts[name]['white_pixels']=sum(min(p)>190 for p in im.crop((32,368,672,508)).getdata())
            assert counts[name]['white_pixels']>500
    assert counts['scale-in-start']['mint_pixels']<counts['scale-in-middle']['mint_pixels']<counts['scale-in-end']['mint_pixels']
    assert counts['scale-out-partial']['mint_pixels']<counts['scale-cancelled']['mint_pixels']
    assert cancel['job']['duration_ms']==10000 and 0<cancel['job']['progress']<1
    return {'path':str(path),'sha256':sha(path),'jobs':jobs,'samples':counts,'ok':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observer',type=pathlib.Path,required=True)
    p.add_argument('--recording-observer',type=pathlib.Path,help='Separate status-only trace for a repeated recording')
    p.add_argument('--scale-recording',type=pathlib.Path,help='First take with BRB Scale/cancel and visible lower third')
    p.add_argument('--recording',type=pathlib.Path,required=True)
    p.add_argument('--stream',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(line) for line in a.observer.read_text().splitlines()]
    report={'ok':False,'observer':str(a.observer),'observer_sha256':sha(a.observer),'alignment':'output_frames / 30 + first video PTS; observer at 4 Hz'}
    try:
        for kind,path in [('recording',a.recording),('streaming',a.stream)]:
            selected = rows
            if kind == 'recording' and a.recording_observer:
                selected = [json.loads(line) for line in a.recording_observer.read_text().splitlines()]
                report['recording_observer'] = {'path':str(a.recording_observer),'sha256':sha(a.recording_observer)}
            report[kind]={};analyze(path,selected,kind,a.out,report[kind])
        if a.scale_recording:
            report['scale_recording']=analyze_scale(a.scale_recording,rows,a.out)
        report['ok']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2))
    print(a.out/'report.json')


if __name__=='__main__':
    main()
