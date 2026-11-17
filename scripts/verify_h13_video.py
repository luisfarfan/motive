#!/usr/bin/env python3
"""Real configurable-canvas pilot/matrix on a signed, already running Motive.

The caller holds the shared physical-test lock. Only owned generated media is
used. No launch, signing, permissions, global preferences or public outputs.
Failed runs and their media remain in a unique evidence directory. This does
not replace later camera/window/system-audio and integrated GPUI acceptance.
"""
import argparse
import hashlib
import json
import math
import pathlib
import statistics
import struct
import subprocess
import time

from h7_support import Client, EVIDENCE, EXE, ROOT, process_sample
from verify_h11_visuals import fixture_png, import_asset, shape_definition, text_definition


def config(resolution, fps):
    return dict(version=1, resolution=resolution, fps=fps, coordinate_space='design960')


def decode(path, width, height, fps, vertical, out):
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) == ('h264', width, height, f'{fps}/1'), video
    assert (audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2), audio
    full = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    assert not full.stderr, full.stderr
    frames = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v',
        '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))['frames']
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    gaps = [b-a for a, b in zip(pts, pts[1:])]
    # Preserve the historical explicit tail allowance; never hide it as cadence.
    assert min(gaps) > 0 and max(gaps[:-4]) < 1.5/fps and max(gaps) < .15, (min(gaps), max(gaps[:-4]), max(gaps))
    packets = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a',
        '-show_packets', '-show_entries', 'packet=pts_time', '-of', 'json', str(path)]))['packets']
    ap = [float(p['pts_time']) for p in packets]
    ag = [b-a for a, b in zip(ap, ap[1:])]
    assert min(ag) > 0 and max(ag) < .023, (min(ag), max(ag))
    pcm = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'])
    samples = struct.unpack('<%df' % (len(pcm)//4), pcm)
    levels = [math.sqrt(sum(x*x for x in samples[i:i+4800])/4800) for i in range(0, len(samples)-4799, 4800)][1:-1]
    peak = max(abs(x) for x in samples)
    assert levels and .02 < min(levels) <= max(levels) < .08 and peak < .2, (min(levels), max(levels), peak)
    lw, lh = (540, 960) if vertical else (960, 540)
    scale = f'scale={lw}:{lh}:flags=area'
    # The logical bottom stripe must exhibit two cuts and two real blended fades.
    y = 804 if vertical else 440
    stripe = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
        '-vf', scale + f',crop=4:60:32:{y},scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    colors = [tuple(stripe[i:i+3]) for i in range(0, len(stripe), 3)]
    def label(rgb):
        for tag, color in [('A', (51,232,181)), ('B', (232,62,75))]:
            if max(abs(a-b) for a,b in zip(rgb, color)) < 35: return tag
        return 'blend'
    runs = []
    for index, rgb in enumerate(colors):
        tag = label(rgb)
        if not runs or runs[-1]['kind'] != tag: runs.append(dict(kind=tag, start=index, frames=0))
        runs[-1]['frames'] += 1
    assert [r['kind'] for r in runs[:3]] == ['A', 'B', 'A'], runs
    end_b = next(i for i in range(3, len(runs)) if runs[i]['kind'] == 'B' and runs[i]['frames'] >= fps)
    end_a = next(i for i in range(end_b+1, len(runs)) if runs[i]['kind'] == 'A' and runs[i]['frames'] >= fps)
    blends = [sum(r['frames'] for r in runs[lo:hi] if r['kind'] == 'blend') for lo, hi in [(3,end_b),(end_b+1,end_a)]]
    assert min(blends) >= fps//3, blends
    # Inspect original generated pattern motion over one early second. White
    # square centroid distinguishes a 60Hz renderer from duplicate 30Hz frames.
    crop_y = 148 if vertical else 270
    strip = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-ss', '0.3', '-i', str(path), '-t', '1',
        '-vf', scale + f',format=rgb24,crop={lw}:1:0:{crop_y}', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    centers = []
    for start in range(0, len(strip), lw*3):
        row = strip[start:start+lw*3]
        white = [x for x in range(lw) if min(row[x*3:x*3+3]) > 215]
        assert len(white) >= (30 if vertical else 60), len(white)
        centers.append(statistics.mean(white))
    advances = sum(abs(b-a) > .3 for a,b in zip(centers, centers[1:]))
    assert advances >= .9*(len(centers)-1), centers
    # Geometry, alpha and text are inspected at canonical coordinates, making
    # equal logical locations testable for all physical resolutions.
    screenshot = out/'frame.png'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', '0.5', '-i', str(path), '-frames:v', '1', str(screenshot)], check=True)
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-ss', '0.5', '-i', str(path), '-frames:v', '1',
        '-vf', scale, '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    def mean(box):
        x,y,w,h = box
        return [statistics.mean(raw[(yy*lw+xx)*3+k] for yy in range(y,y+h) for xx in range(x,x+w)) for k in range(3)]
    shape_y = 350 if vertical else 160
    circle = mean((70,shape_y+35,20,20))
    assert max(abs(a-b) for a,b in zip(circle,(230,60,75))) < 25, circle
    opaque = mean((250,shape_y+35,15,20))
    assert max(abs(a-b) for a,b in zip(opaque,(32,224,96))) < 25, opaque
    ty = 220 if vertical else 30
    bright = sum(min(raw[(yy*lw+xx)*3:(yy*lw+xx)*3+3]) > 210 for yy in range(ty,ty+90) for xx in range(40,400))
    assert bright > 300, bright
    return dict(probe=probe, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), frames=len(pts),
        video_max_interior_gap=max(gaps[:-4]), video_max_gap=max(gaps), tail_gaps=gaps[-4:],
        audio_max_gap=max(ag), audio_rms_min=min(levels), audio_rms_max=max(levels), peak=peak,
        av_start_delta=ap[0]-pts[0], av_end_delta=ap[-1]-pts[-1],
        stripe_runs=runs, fade_blended_frames=blends, motion_centroids=centers, motion_advances=advances,
        circle_rgb=circle, image_opaque_rgb=opaque, text_bright_pixels=bright, screenshot=str(screenshot))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', action='store_true', help='All candidate H/V presets plus x2641080p30; default720p30 pilot')
    parser.add_argument('--resolution', choices=['legacy540','hd720','full_hd1080'], default='hd720')
    parser.add_argument('--fps', type=int, choices=[30,60], default=30)
    parser.add_argument('--variant', choices=['horizontal','vertical'], default='horizontal')
    parser.add_argument('--encoder', choices=['videotoolbox','x264'], default='videotoolbox')
    args = parser.parse_args()
    run = EVIDENCE/f'h13-video-{time.time_ns()}'
    run.mkdir(parents=True)
    report = dict(ok=False, trials=[], run=str(run), scope='Owned pattern, text, PNG, circle, Cut/Fade and tone; capture/GPUI gates separate')
    c = None
    try:
        c = Client()
        initial = c.state(); report['initial'] = initial
        assert initial['output'] == 'idle' and not initial['audio_mixer']['store']['inputs']
        assert len(initial['project']['graph']['scenes']) == 1
        assert all(s['spec']['kind'] in ('pattern','overlay') and s.get('overlay') is None for s in initial['project']['graph']['sources'])
        report['binary_sha256'] = hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
        report['capabilities'] = c.call('video_capabilities')
        c.call('select_audio', id='tone')
        c.call('configure_transition', transition=dict(kind='cut', duration_ms=0))
        a = initial['project']['graph']['active_scene']
        b = c.call('create_scene', name='H13 canvas B')['state']['project']['graph']['active_scene']
        c.call('add_layer', scene_id=b, source_id='main')
        before = {s['id'] for s in c.state()['project']['graph']['sources']}
        g = c.call('add_source', scene_id=b, name='H13 red marker', source=dict(kind='overlay',color=0xe83e4b))['state']['project']['graph']
        red = next(s['id'] for s in g['sources'] if s['id'] not in before)
        fixture = run/'alpha.png'; fixture_png(fixture)
        asset = import_asset(c, fixture)['asset']
        c.call('select_scene', scene_id=a)
        for name, definition, horizontal, vertical in [
            ('H13 text', text_definition('H13 CANVAS'), (40,30,400,90), (40,220,400,90)),
            ('H13 circle', shape_definition('circle',96,96,0xe63c4b), (40,160,96,96), (40,350,96,96)),
            ('H13 image', dict(kind='image',asset_id=asset['id'],opacity=1.), (180,160,96,96), (180,350,96,96)),
        ]:
            sid = c.call('create_overlay', scene_id=a, name=name, definition=definition)['result']['source_id']
            c.call('add_layer', scene_id=b, source_id=sid)
            for scene in (a,b):
                g = c.state()['project']['graph']
                layer = next(l['id'] for s in g['scenes'] if s['id']==scene for l in s['layers'] if l['source_id']==sid)
                for variant, box in [('horizontal',horizontal),('vertical',vertical)]:
                    x,y,w,h = box
                    c.call('set_transform', scene_id=scene, layer_id=layer, variant=variant, transform=dict(x=x,y=y,width=w,height=h,order=4,visible=True))
        for scene, source in ((a,'overlay'),(b,red)):
            g = c.state()['project']['graph']
            layers = next(s['layers'] for s in g['scenes'] if s['id']==scene)
            for variant in ('horizontal','vertical'):
                marker = next(l['id'] for l in layers if l['source_id']==source)
                c.call('set_transform', scene_id=scene, layer_id=marker, variant=variant, transform=dict(x=32,y=800 if variant=='vertical' else 436,width=320,height=72,order=5,visible=True))
                main = next(l['id'] for l in layers if l['source_id']=='main')
                c.call('set_transform', scene_id=scene, layer_id=main, variant=variant, transform=dict(x=0,y=0,width=540 if variant=='vertical' else 960,height=303.75 if variant=='vertical' else 540,order=0,visible=True))
        cases = [(args.resolution,args.fps,args.variant,args.encoder)]
        if args.matrix:
            cases += [(r,f,v,'videotoolbox') for r,f in [('hd720',30),('full_hd1080',30),('full_hd1080',60)] for v in ('horizontal','vertical') if (r,f,v)!=('hd720',30,'horizontal')]
            cases += [('full_hd1080',30,'horizontal','x264')]
        for resolution,fps,variant,encoder in cases:
            trial = dict(resolution=resolution,fps=fps,variant=variant,encoder=encoder,samples=[],events=[])
            report['trials'].append(trial)
            out = run/f'{resolution}-{fps}-{variant}-{encoder}';out.mkdir()
            c.call('configure_transition', transition=dict(kind='cut',duration_ms=0))
            c.call('select_scene', scene_id=a)
            c.call('set_variant', variant=variant)
            configured = c.call('configure_video', video=config(resolution,fps))['state']
            assert configured['project']['version']==5 and configured['fps']==fps, configured
            expected = {'legacy540':(960,540),'hd720':(1280,720),'full_hd1080':(1920,1080)}[resolution]
            if variant=='vertical': expected=expected[::-1]
            assert (configured['width'],configured['height'])==expected
            c.call('set_encoder', encoder=encoder)
            c.call('save_project')
            assert c.call('load_project')['state']['project']==configured['project']
            c.wait(lambda s:not s['issues'] and not s['recovery_required'])
            # Exercise CLI and MCP on the same owner, without another instance.
            cli=json.loads(subprocess.check_output([str(EXE),'ctl',json.dumps(dict(op='video_capabilities'))]))
            assert cli['ok'] and cli['pid']==configured['pid'], cli
            before=c.state();trial['before']=before
            start=c.call('start_recording')['state'];trial['start']=start
            assert c.call('configure_video',expect=False,video=config('legacy540',30))['error']['code']=='OUTPUT_BUSY'
            origin=last=time.monotonic();previous,_=process_sample(start['pid'])
            def hold(seconds):
                nonlocal last,previous
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    time.sleep(.2);s=c.state();now=time.monotonic();cpu,rss=process_sample(s['pid'])
                    assert s['output']=='recording' and not s['issues'],s
                    assert s['transition']['source_instances_created']==start['transition']['source_instances_created']
                    trial['samples'].append(dict(seconds=now-origin,cpu_percent=100*(cpu-previous)/(now-last),rss_mib=rss,state=s))
                    previous=cpu;last=now
            def switch(scene):
                trial['events'].append(dict(seconds=time.monotonic()-origin,response=c.call('select_scene',scene_id=scene)))
            hold(2);switch(b);hold(1.5);switch(a);hold(1.5)
            c.call('configure_transition',transition=dict(kind='fade',duration_ms=1000))
            switch(b);hold(2.5);switch(a);hold(2.5)
            stopped=c.stop();trial['stop']=stopped
            end=stopped['end'];assert end['output']=='idle'
            trial['counter_delta']={key:end['stats'][key]-before['stats'][key] for key in ['lagged_frames','video_skipped_frames','rendered_frames','preview_copies']}
            # Decode even if native metrics fail, preserving both independent gates.
            trial['media']=decode(pathlib.Path(start['output_path']),*expected,fps,variant=='vertical',out)
            assert trial['counter_delta']['lagged_frames']==0 and trial['counter_delta']['video_skipped_frames']==0 and end['stats']['output_dropped_frames']==0,trial['counter_delta']
            trial['performance']=dict(cpu_median=statistics.median(x['cpu_percent'] for x in trial['samples']),rss_median=statistics.median(x['rss_mib'] for x in trial['samples']),rss_peak=max(x['rss_mib'] for x in trial['samples']))
            trial['ok']=True
            (run/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps({k:trial[k] for k in ['resolution','fps','variant','encoder','performance','counter_delta','ok']}),flush=True)
        report['ok']=True
    except BaseException as exc:
        report['error']=repr(exc)
        raise
    finally:
        if c:
            try:
                if c.state()['output'] not in ('idle','error'):c.stop()
            except Exception as exc:report['cleanup_error']=repr(exc)
            report['rpc']=c.ops;c.close()
        (run/'report.json').write_text(json.dumps(report,indent=2))
        print(run/'report.json',flush=True)


if __name__=='__main__':main()
