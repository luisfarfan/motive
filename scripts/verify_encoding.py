#!/usr/bin/env python3
"""Compare real x264/VideoToolbox recordings through MCP, with owned layers.

Run on a signed, idle Motive using a disposable project (no physical sources).
Same process, canvas, sources, settings and preview; alternating AB/BA order.
Records H.264/AAC, decodes every file and measures interval process CPU time.
No public output, project-file editing, UI automation or global configuration.
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
from h7_support import assert_project_format

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = ROOT/'target/debug/motive'
OUT = ROOT/'var/evidence'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, default=60, choices=range(15, 301), metavar='15..300')
parser.add_argument('--rounds', type=int, default=2, choices=range(1, 4))
args = parser.parse_args()
report = {'ok':False, 'trials':[], 'rpc':[], 'seconds':args.seconds, 'rounds':args.rounds}
p = subprocess.Popen([str(EXE),'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def rpc(method, params=None):
    q = {'jsonrpc':'2.0','id':len(report['rpc'])+1,'method':method,'params':params or {}}
    p.stdin.write(json.dumps(q)+'\n');p.stdin.flush()
    answer = json.loads(p.stdout.readline())
    report['rpc'].append({'request':q,'response':answer})
    assert 'error' not in answer, answer
    return answer['result']


def command(op, expect=True, **arguments):
    result = rpc('tools/call', {'name':op,'arguments':arguments})
    value = json.loads(result['content'][0]['text'])
    assert value['ok']==expect, value
    return value


def state():
    return command('status')['state']


def idle():
    end = time.monotonic()+15
    while time.monotonic()<end:
        s = state()
        if s['output']=='idle':
            assert s['output_code']==0, s
            return s
        assert s['output']!='error', s
        time.sleep(.15)
    raise AssertionError('Output did not finish')


def add(scene, name, spec):
    before = {s['id'] for s in state()['project']['graph']['sources']}
    g = command('add_source',scene_id=scene,name=name,source=spec)['state']['project']['graph']
    source = next(s['id'] for s in g['sources'] if s['id'] not in before)
    layer = next(l['id'] for s in g['scenes'] if s['id']==scene for l in s['layers'] if l['source_id']==source)
    return source, layer


def transform(scene, layer, x, y, width, height, order):
    command('set_transform',scene_id=scene,layer_id=layer,variant='horizontal',
            transform={'x':x,'y':y,'width':width,'height':height,'visible':True,'order':order})


def ps(pids):
    result = {}
    raw = subprocess.check_output(['ps','-p',','.join(map(str,pids)),'-o','pid=,time=,rss='],text=True)
    for line in raw.splitlines():
        pid, cpu, rss = line.split()
        seconds = 0
        for field in cpu.split(':'): seconds=seconds*60+float(field)
        result[int(pid)] = {'cpu_seconds':seconds,'rss_mib':int(rss)/1024}
    return result


def crop(path, second, rect):
    return subprocess.check_output(['ffmpeg','-nostdin','-v','error','-ss',str(second),'-i',path,
                                   '-frames:v','1','-vf','crop='+rect,'-pix_fmt','rgb24','-f','rawvideo','-'])


def color_count(raw, rgb):
    return sum(all(abs(raw[i+c]-rgb[c])<32 for c in range(3)) for i in range(0,len(raw),3))


def verify_media(path, minimum):
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
    v = next(s for s in probe['streams'] if s['codec_type']=='video')
    a = next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (v['codec_name'],v['width'],v['height'],v['pix_fmt'],v['avg_frame_rate'])==('h264',960,540,'yuv420p','30/1'), v
    assert v['profile']=='High' and v['color_space']=='bt709' and v['color_range']=='tv', v
    assert a['codec_name']=='aac' and a['sample_rate']=='48000' and a['channels']==2, a
    assert float(probe['format']['duration'])>=minimum and int(v['nb_read_frames'])>=minimum*29, probe
    decode = subprocess.run(['ffmpeg','-nostdin','-v','error','-i',path,'-f','null','-'],capture_output=True,check=True)
    assert not decode.stderr, decode.stderr.decode()
    frames = json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_frames',
        '-show_entries','frame=best_effort_timestamp_time,key_frame','-of','json',path]))['frames']
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    gaps = [b-a for a,b in zip(pts,pts[1:])]
    # Inspect the stop boundary separately: delayed H.264 frames can leave a
    # final PTS gap even when the steady recording is continuous. Report it.
    assert min(gaps)>0 and max(gaps[:-3])<.05 and max(gaps)<.15, (min(gaps),max(gaps))
    boundary_gaps=[{'frame':i+1,'seconds':gap} for i,gap in enumerate(gaps) if gap>.05]
    keyframes = [float(f['best_effort_timestamp_time']) for f in frames if f['key_frame']]
    key_gaps = [b-a for a,b in zip(keyframes,keyframes[1:])]
    assert key_gaps and max(key_gaps)<=2.1, key_gaps
    pcm = subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',path,'-t','2','-vn','-ac','1','-ar','48000','-f','f32le','-'])
    samples = struct.unpack('<%df'%(len(pcm)//4),pcm)
    rms = math.sqrt(sum(x*x for x in samples)/len(samples));assert .02<rms<.08, rms
    overlays = [crop(path,t,'320:72:32:436') for t in (.5,1,1.5,2)]
    teal = color_count(overlays[0],(51,232,181));assert teal>500, teal
    motion = max(sum(abs(a-b)>25 for a,b in zip(overlays[0],f)) for f in overlays[1:]);assert motion>300, motion
    secondary = color_count(crop(path,1,'20:20:650:42'),(33,156,135));assert secondary>250, secondary
    return {'probe':probe,'duration':float(probe['format']['duration']),'frames':int(v['nb_read_frames']),
            'file_bytes':pathlib.Path(path).stat().st_size,'audio_rms':rms,'overlay_teal_pixels':teal,
            'overlay_changed_channels':motion,'secondary_green_pixels':secondary,
            'max_frame_gap_seconds':max(gaps),'stop_boundary_gaps':boundary_gaps,'max_keyframe_gap_seconds':max(key_gaps),
            'sha256':hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}


def trial(policy, index, project):
    command('set_encoder',encoder=policy)
    assert state()['project']==project, 'Encoder selection must not change project v3'
    before = state()
    start = command('start_recording')['state']
    assert start['encoding']['selected_hardware']==(policy=='videotoolbox'), start['encoding']
    assert start['encoding']['fallback_reason'] is None
    assert command('set_encoder',expect=False,encoder='auto')['error']['code']=='OUTPUT_BUSY'
    helpers=[]
    for line in subprocess.check_output(['ps','-axo','pid=,ppid=,comm='],text=True).splitlines():
        parts=line.strip().split(maxsplit=2)
        if len(parts)==3 and int(parts[1])==start['pid'] and pathlib.Path(parts[2]).name=='obs-ffmpeg-mux':helpers.append(int(parts[0]))
    assert len(helpers)==1, helpers
    pids=[start['pid'],*helpers]
    previous=ps(pids);t0=last=time.monotonic();samples=[]
    # Preserve the failing trial too. No extra polling or disk I/O during output.
    # Previously its samples were lost when a strict assertion fired before return.
    report['in_progress_trial']={'index':index,'policy':policy,'before':before,'start':start,'samples':samples}
    print(f'Trial {index}: {policy}, {args.seconds}s, same scene and process',flush=True)
    while time.monotonic()-t0<args.seconds:
        time.sleep(1)
        s=state();assert s['output']=='recording' and not s['issues'], s
        current=ps(pids);now=time.monotonic();dt=now-last
        assert set(current)==set(previous)
        sample={'elapsed':now-t0,'app_cpu_percent':100*(current[pids[0]]['cpu_seconds']-previous[pids[0]]['cpu_seconds'])/dt,
                'helper_cpu_percent':100*(current[pids[1]]['cpu_seconds']-previous[pids[1]]['cpu_seconds'])/dt,
                'app_rss_mib':current[pids[0]]['rss_mib'],'helper_rss_mib':current[pids[1]]['rss_mib'],'stats':s['stats']}
        samples.append(sample);previous=current;last=now
    command('stop_output');end=idle()
    assert end['project']==project and end['pid']==before['pid']
    steady=[s for s in samples if s['elapsed']>=5]
    metrics={key:{'median':statistics.median(s[key] for s in steady),'max':max(s[key] for s in steady),
                  'min':min(s[key] for s in steady)} for key in ['app_cpu_percent','helper_cpu_percent','app_rss_mib','helper_rss_mib']}
    counters={key:end['stats'][key]-before['stats'][key] for key in ['rendered_frames','lagged_frames','video_skipped_frames','preview_busy_drops','preview_copies']}
    report['in_progress_trial'].update({'end':end,'metrics':metrics,'counter_delta':counters})
    assert counters['lagged_frames']==0 and counters['video_skipped_frames']==0 and end['stats']['output_dropped_frames']==0, counters
    media=verify_media(start['output_path'],args.seconds-1)
    print(f'  Decoded {media["frames"]} frames; CPU median {metrics["app_cpu_percent"]["median"]:.1f}%',flush=True)
    report.pop('in_progress_trial',None)
    return {'policy':policy,'start':start,'end':end,'samples':samples,'metrics':metrics,'counter_delta':counters,'media':media}


original=None;scene=None;created=[]
try:
    rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'encoder-comparison','version':'1'}})
    original=idle()
    assert all(s['spec']['kind'] in ('pattern','overlay') for s in original['project']['graph']['sources']), 'Use a disposable project without physical captures'
    report['inventory']=command('encoders')['encoders'];assert report['inventory']['videotoolbox_id']
    report['app_sha256']=hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
    report['ui_sha256']=hashlib.sha256((ROOT/'src/main.rs').read_bytes()).hexdigest()
    command('set_variant',variant='horizontal');command('select_audio',id='tone')
    scene=command('create_scene',name='Encoder comparison')['state']['project']['graph']['active_scene']
    for name,spec in [('Pattern',{'kind':'pattern'}),('Secondary',{'kind':'pattern'}),('Overlay',{'kind':'overlay','color':0x33e8b5})]:
        source,layer=add(scene,name,spec);created.append(source)
        if name=='Secondary':transform(scene,layer,640,32,288,162,2)
        if name=='Overlay':transform(scene,layer,32,436,320,72,3)
    project=state()['project'];assert_project_format(project,3,original['project'].get('video'))
    command('save_project');assert command('load_project')['state']['project']==project
    for round in range(args.rounds):
        order=['x264','videotoolbox'] if round%2==0 else ['videotoolbox','x264']
        for policy in order:report['trials'].append(trial(policy,len(report['trials'])+1,project))
    report['summary']={policy:{key:statistics.median(t['metrics'][key]['median'] for t in report['trials'] if t['policy']==policy)
                               for key in ['app_cpu_percent','helper_cpu_percent','app_rss_mib','helper_rss_mib']}
                       for policy in ('x264','videotoolbox')}
    report['ok']=True
except BaseException as exc:
    report['error']=repr(exc);raise
finally:
    try:
        command('stop_output');idle()
        if scene: command('remove_scene',scene_id=scene)
        for source in created:command('remove_source',source_id=source)
        if original:
            command('select_scene',scene_id=original['project']['graph']['active_scene'])
            command('select_audio',id=original['project']['audio'])
            command('set_variant',variant=original['project']['variant'])
            command('set_encoder',encoder=original['encoding']['preference'])
            command('save_project')
    except Exception as exc:report['cleanup_error']=repr(exc)
    p.stdin.close();p.wait(timeout=8)
    (OUT/'encoding-comparison.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report.get('summary',{}),indent=2))
