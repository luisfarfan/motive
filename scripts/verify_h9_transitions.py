#!/usr/bin/env python3
"""Real H9 scene transitions over recording and loopback RTMP, through MCP.

Requires a signed running Motive, ffmpeg/ffprobe and explicit --camera-id.
Captures only our AppKit fixture plus the authorized physical camera. Artifacts
stay in ignored var/. Production is controlled exclusively by shared commands.
"""
import argparse, os, signal, socket
from h7_support import *

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--camera-id',required=True)
args=parser.parse_args()
c=Client();receiver=None;fixture_pid=None
report={'ok':False,'checks':[]};created_sources=[];created_scenes=[]
a=None;b=None;window_scene=None;window_source=None

def graph():return c.state()['project']['graph']
def configure(kind,duration):return c.call('configure_transition',transition={'kind':kind,'duration_ms':duration})
def add_source(scene,name,spec):
    before={s['id'] for s in graph()['sources']}
    g=c.call('add_source',scene_id=scene,name=name,source=spec)['state']['project']['graph']
    sid=next(s['id'] for s in g['sources'] if s['id'] not in before);created_sources.append(sid)
    return sid,next(l['id'] for s in g['scenes'] if s['id']==scene for l in s['layers'] if l['source_id']==sid)
def add_scene(name):
    sid=c.call('create_scene',name=name)['state']['project']['graph']['active_scene'];created_scenes.append(sid);return sid
def transform(scene,layer,x,y,width,height,order):
    return c.call('set_transform',scene_id=scene,layer_id=layer,variant='horizontal',transform=dict(x=x,y=y,width=width,height=height,order=order,visible=True))
def selected(scene,timeout=10):
    return c.wait(lambda s:s['project']['graph']['active_scene']==scene and s['transition']['phase'] not in ('preparing','running'),timeout)
def switch(scene):
    response=c.call('select_scene',scene_id=scene);return {'response':response,'end':selected(scene)}
def listen():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    path=EVIDENCE/f'h9-stream-{time.time_ns()}.flv';log=(EVIDENCE/'h9-receiver.log').open('w')
    p=subprocess.Popen(['ffmpeg','-nostdin','-v','info','-listen','1','-i',f'rtmp://127.0.0.1:{port}/live/motive','-c','copy',str(path)],stdout=subprocess.DEVNULL,stderr=log);log.close()
    end=time.monotonic()+8
    while time.monotonic()<end:
        assert p.poll() is None
        if subprocess.run(['lsof','-a','-p',str(p.pid),'-iTCP:'+str(port),'-sTCP:LISTEN'],capture_output=True).returncode==0:return p,path,port
        time.sleep(.1)
    p.terminate();p.wait();raise AssertionError('Receiver did not listen')
def pixels(path):
    # Fixed mint/red stripe is independent of overlay animation and webcam data.
    raw=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vf','crop=4:60:32:440,scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
    values=[list(raw[i:i+3]) for i in range(0,len(raw),3)]
    def label(rgb):
        if max(abs(x-y) for x,y in zip(rgb,[51,232,181]))<35:return 'A'
        if max(abs(x-y) for x,y in zip(rgb,[232,62,75]))<35:return 'B'
        return 'blend'
    runs=[]
    for i,rgb in enumerate(values):
        tag=label(rgb)
        if not runs or runs[-1]['kind']!=tag:runs.append({'kind':tag,'start':i,'frames':0})
        runs[-1]['frames']+=1
    # Initial two Cut changes must have no blended frame; each 1 s Fade must
    # contain multiple distinct decoded colors between its endpoints.
    assert [r['kind'] for r in runs[:3]]==['A','B','A'],runs[:10]
    # Classify intervals between stable endpoints, not an exact list of runs.
    # Lossy H.264 can cross a color tolerance back and forth near either end
    # of a Fade. Every raw sample/run remains in the evidence.
    forward_end=next(i for i in range(3,len(runs)) if runs[i]['kind']=='B' and runs[i]['frames']>=10)
    reverse_end=next(i for i in range(forward_end+1,len(runs)) if runs[i]['kind']=='A' and runs[i]['frames']>=10)
    fades=[]
    for lo,hi in ((3,forward_end),(forward_end+1,reverse_end)):
        mixed=[r for r in runs[lo:hi] if r['kind']=='blend']
        count=sum(r['frames'] for r in mixed)
        distinct={tuple(rgb) for r in mixed for rgb in values[r['start']:r['start']+r['frames']]}
        assert count>=10 and len(distinct)>=10,(count,len(distinct),runs[lo:hi+1])
        fades.append({'mixed_frames':count,'distinct_colors':len(distinct)})
    return {'stripe_rgb_by_frame':values,'runs':runs,'cut_no_blended_frames':True,'fades':fades}


def audio_continuity(path):
    pcm=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar','48000','-f','f32le','-'])
    samples=struct.unpack('<%df'%(len(pcm)//4),pcm)
    # Inspect the entire sequence in 100 ms windows, excluding only codec
    # priming and final padding at the two endpoints, never a scene change.
    levels=[math.sqrt(sum(x*x for x in samples[i:i+4800])/4800) for i in range(0,len(samples)-4799,4800)][1:-1]
    assert levels and min(levels)>.04 and max(levels)<.08,(min(levels),max(levels))
    return {'window_ms':100,'rms_min':min(levels),'rms_max':max(levels),'rms_by_window':levels}

def exercise(kind,path=None):
    configure('cut',0);switch(a)
    before=c.state();r={'before':before,'events':[]};report[kind]=r
    started=c.call('start_recording' if kind=='recording' else 'start_stream')['state'];r['started']=started
    expected='recording' if kind=='recording' else 'streaming';ready=c.wait(lambda s:s['output']==expected);r['ready']=ready
    assert ready['encoding']['selected_hardware'],ready['encoding']
    pid=ready['pid'];counts=(ready['transition']['source_instances_created'],ready['transition']['scenes_built'])
    instances={s['id']:s['instance_id'] for s in ready['sources']};previous_cpu,_=process_sample(pid);last=time.monotonic();start=last
    samples=[];previous_frames=ready['stats']['encoded_frames']
    def sample():
        nonlocal previous_cpu,last,previous_frames
        s=c.state();now=time.monotonic();cpu,rss=process_sample(pid)
        assert s['pid']==pid and s['output']==expected and not s['issues'] and not s['recovery_required'],s
        assert (s['transition']['source_instances_created'],s['transition']['scenes_built'])==counts,s['transition']
        assert {v['id']:v['instance_id'] for v in s['sources']}==instances
        assert s['stats']['encoded_frames']>=previous_frames
        samples.append({'seconds':now-start,'cpu_percent':100*(cpu-previous_cpu)/(now-last),'rss_mib':rss,'state':s})
        previous_cpu=cpu;last=now;previous_frames=s['stats']['encoded_frames'];return s
    def hold(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:time.sleep(.1);sample()
    def change(scene,label):
        response=c.call('select_scene',scene_id=scene);r['events'].append({'label':label,'seconds':time.monotonic()-start,'response':response})
        end=time.monotonic()+10
        while True:
            s=sample()
            if s['transition']['phase']=='completed' and s['project']['graph']['active_scene']==scene:return s
            assert time.monotonic()<end,s;time.sleep(.05)
    hold(2);change(b,'cut B');hold(1.2);change(a,'cut A');hold(1.2)
    configure('fade',1000);pending=c.call('select_scene',scene_id=b)['state'];op=pending['transition']['operation_id']
    r['events'].append({'label':'fade B','seconds':time.monotonic()-start,'state':pending})
    same=c.call('select_scene',scene_id=b)['state'];assert same['transition']['operation_id']==op
    for name,fields in [('select_scene',{'scene_id':a}),('configure_transition',{'transition':{'kind':'cut','duration_ms':0}}),('save_project',{}),('set_overlay_color',{'source_id':'overlay','color':0x33e8b5})]:
        assert c.call(name,expect=False,**fields)['error']['code']=='TRANSITION_BUSY'
    assert c.call('cancel_transition',expect=False,operation_id=op-1)['error']['code']=='TRANSITION_OPERATION_MISMATCH'
    hold(1.2);assert sample()['project']['graph']['active_scene']==b
    change(a,'fade A');hold(1.2)
    configure('fade',3000);pending=c.call('select_scene',scene_id=b)['state'];hold(.8)
    running=sample();assert running['transition']['phase']=='running' and .1<running['transition']['progress']<.9
    cancelled=c.call('cancel_transition',operation_id=pending['transition']['operation_id'])['state']
    assert cancelled['transition']['phase']=='cancelled' and cancelled['project']['graph']['active_scene']==a
    c.call('cancel_transition',operation_id=pending['transition']['operation_id']);r['cancelled']=cancelled;hold(.7)
    configure('cut',0)
    for i in range(20):change(b if i%2==0 else a,f'rapid cut {i}')
    configure('fade',300)
    for i in range(6):change(b if i%2==0 else a,f'rapid fade {i}')
    configure('cut',0);hold(.5)
    # Target window no longer exists; program remains on A and encoder continues.
    bad=c.call('select_scene',expect=False,scene_id=window_scene)
    assert bad['error']['code']=='SCENE_TARGET_UNAVAILABLE',bad
    assert bad['transition']['phase']=='failed' and bad['transition']['current_scene']==a
    r['unavailable_target']=bad;hold(1)
    r['last']=sample();r['stop']=c.stop();assert r['stop']['end']['output']=='idle'
    assert r['last']['stats']['output_dropped_frames']==0
    assert r['last']['stats']['video_skipped_frames']==ready['stats']['video_skipped_frames']
    r['metrics']={'samples':samples,'cpu_median':statistics.median(x['cpu_percent'] for x in samples),
        'rss_median_mib':statistics.median(x['rss_mib'] for x in samples),'rss_range_mib':[min(x['rss_mib'] for x in samples),max(x['rss_mib'] for x in samples)],
        'elapsed':time.monotonic()-start,'lagged_delta':r['last']['stats']['lagged_frames']-ready['stats']['lagged_frames']}
    if kind=='streaming':receiver.wait(timeout=10)
    path=path or started['output_path'];r['media']=media(path,10);r['pixels']=pixels(path)
    assert r['media']['max_interior_gap']<.05,r['media']['gaps_over_50ms']
    # Full audio packet timeline, in addition to full decode and RMS.
    packets=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','a','-show_packets','-show_entries','packet=pts_time','-of','json',str(path)]))['packets']
    pts=[float(p['pts_time']) for p in packets];gaps=[y-x for x,y in zip(pts,pts[1:])]
    assert min(gaps)>0 and max(gaps)<.03,(min(gaps),max(gaps))
    r['audio_timeline']={'first':pts[0],'last':pts[-1],'packets':len(pts),'max_gap':max(gaps),'continuity':audio_continuity(path)}
    # One shared physical source continues delivering across the whole sequence.
    cam0=next(s for s in ready['sources'] if s['id']==camera)
    cam1=next(s for s in r['last']['sources'] if s['id']==camera)
    assert cam0['instance_id']==cam1['instance_id'] and cam1['frames']>cam0['frames']+100
    return r
try:
    initial=c.state();assert initial['output']=='idle' and len(graph()['scenes'])==1
    assert all(s['spec']['kind'] in ('pattern','overlay') for s in graph()['sources']), 'Requires controlled initial scene'
    report['initial']=initial;a=graph()['active_scene'];setup_owned(c)
    tools=c.rpc('tools/list')['tools'];assert next(t for t in tools if t['name']=='scenes')['annotations']['readOnlyHint']
    assert next(t for t in tools if t['name']=='cancel_transition')['annotations']['destructiveHint']
    for config in [{'kind':'cut','duration_ms':1},{'kind':'fade','duration_ms':99},{'kind':'fade','duration_ms':5001}]:
        assert c.call('configure_transition',expect=False,transition=config)['error']['code']=='INVALID_TRANSITION'
    camera,layer=add_source(a,'H9 shared webcam',{'kind':'camera','device_id':args.camera_id});transform(a,layer,640,32,288,162,2)
    c.wait(lambda s:not s['issues']);b=add_scene('H9 B');c.call('add_layer',scene_id=b,source_id='main')
    red,red_layer=add_source(b,'H9 red marker',{'kind':'overlay','color':0xe83e4b});transform(b,red_layer,32,436,320,72,1)
    bg=c.call('add_layer',scene_id=b,source_id=camera)['state']['project']['graph']
    bl=next(l['id'] for s in bg['scenes'] if s['id']==b for l in s['layers'] if l['source_id']==camera);transform(b,bl,640,32,288,162,2)
    c.call('select_scene',scene_id=a);c.wait(lambda s:not s['issues'])
    subprocess.run(['python3',str(ROOT/'scripts/window_fixture.py')],check=True,capture_output=True)
    old={w['pid'] for w in c.call('devices')['devices']['windows'] if w['bundle_id']=='local.motive.fixture'}
    subprocess.run(['open','-n',str(ROOT/'target/MotiveFixture.app')],check=True)
    end=time.monotonic()+10
    while True:
        windows=[w for w in c.call('devices')['devices']['windows'] if w['bundle_id']=='local.motive.fixture' and w['pid'] not in old]
        if windows:break
        assert time.monotonic()<end;time.sleep(.2)
    fixture=windows[0];fixture_pid=fixture['pid'];window_scene=add_scene('H9 cold window')
    # Keep A active while creating the cold source in an inactive scene.
    c.call('select_scene',scene_id=a);window_source,wl=add_source(window_scene,'H9 owned window',{'kind':'window','window_id':fixture['id']})
    transform(window_scene,wl,0,0,960,540,0)
    configure('fade',5000)
    started=c.call('start_recording')['state'];preparation_cancellations=[]
    for _ in range(4):
        pending=c.call('select_scene',scene_id=window_scene)['state']
        assert pending['transition']['phase']=='preparing' and pending['project']['graph']['active_scene']==a
        cancelled=c.call('cancel_transition',operation_id=pending['transition']['operation_id'])['state']
        assert cancelled['transition']['phase'] in ('cancelled','failed') and cancelled['output']=='recording'
        assert cancelled['project']['graph']['active_scene']==a
        if cancelled['transition']['phase']=='failed':assert cancelled['transition']['blocked_sources']
        preparation_cancellations.append(cancelled)
    assert any(s['transition']['phase']=='cancelled' for s in preparation_cancellations)
    configure('cut',0)
    warm=c.call('select_scene',scene_id=window_scene)['state']
    assert warm['transition']['phase']=='preparing' and warm['project']['graph']['active_scene']==a,warm
    prepared=selected(window_scene);assert prepared['output']=='recording' and not prepared['issues'];time.sleep(1)
    switch(a);configure('fade',3000);c.call('select_scene',scene_id=window_scene)
    c.wait(lambda s:s['transition']['phase']=='running');time.sleep(.3)
    os.kill(fixture_pid,signal.SIGTERM);fixture_pid=None
    failed=c.wait(lambda s:s['transition']['phase']=='failed')
    assert failed['transition']['error']=='SCENE_TARGET_FAILED' and failed['project']['graph']['active_scene']==a
    assert failed['output']=='recording' and not failed['recovery_required'],failed
    time.sleep(.5);c.stop()
    report['cold_window']={'started':started,'preparation_cancellations':preparation_cancellations,'preparing':warm,'completed':prepared,'failed_during_fade':failed,'media':media(started['output_path'],1)}
    exercise('recording')
    receiver,path,port=listen();c.call('configure_stream',endpoint={'transport':'rtmp','port':port});exercise('streaming',path);receiver=None
    c.call('remove_scene',scene_id=window_scene);created_scenes.remove(window_scene)
    c.call('remove_source',source_id=window_source);created_sources.remove(window_source)
    switch(b);saved=c.call('save_project')['state']['project'];pid=c.state()['pid'];c.call('shutdown')
    end=time.monotonic()+10
    while subprocess.run(['ps','-p',str(pid)],capture_output=True).returncode==0:
        assert time.monotonic()<end;time.sleep(.1)
    subprocess.run(['open',str(ROOT/'target/Motive.app')],check=True);time.sleep(2)
    restored=c.call('load_project')['state'];assert restored['project']==saved
    assert restored['pid']!=pid and restored['transition_configuration']=={'kind':'cut','duration_ms':0}
    c.wait(lambda s:not s['issues']);report['restore']={'saved':saved,'restored':restored}
    cli=json.loads(subprocess.check_output([str(EXE),'ctl','{"op":"scenes"}']));mcp=c.call('scenes')
    assert cli==mcp;report['cli_mcp_shared']=cli
    report['bundle_sha256']=hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
    report['checks']=['continuous VT H264/AAC recording and RTMP','Cut has no blended decoded frame','Fade has multiple decoded intermediate colors','same production PID, monotonic encoder frames and unchanged native scene/resource counts','shared physical camera frame counter continues','cold window prepared off-air','unavailable window preserves program and output','busy/idempotent/repeated/cancel/stale-token contracts','CLI/MCP shared revision and state','project v3 save/close/open/load']
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        s=c.state();c.call('cancel_transition',operation_id=s['transition']['operation_id'])
        if s['output'] not in ('idle','error'):c.stop()
        if c.state()['output']=='error':c.call('recover_output')
        configure('cut',0)
        if a:c.call('select_scene',scene_id=a)
        for sid in list(created_scenes):c.call('remove_scene',scene_id=sid)
        for sid in list(created_sources):
            for scene in graph()['scenes']:
                for layer in scene['layers']:
                    if layer['source_id']==sid:c.call('remove_layer',scene_id=scene['id'],layer_id=layer['id'])
            c.call('remove_source',source_id=sid)
        c.call('select_audio',id='none');c.call('save_project')
    except Exception as e:report['cleanup_error']=repr(e)
    if fixture_pid:os.kill(fixture_pid,signal.SIGTERM)
    if receiver and receiver.poll() is None:receiver.terminate();receiver.wait(timeout=10)
    report['operations']=c.ops;c.close();(EVIDENCE/'h9-transitions.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k in ('ok','error','checks')},indent=2))
