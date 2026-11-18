"""Shared real MCP/media helpers for H7 verification (no mocked media)."""
import hashlib,json,math,pathlib,statistics,struct,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EVIDENCE=ROOT/'var/evidence'
EXE=VERIFY.client_executable

def assert_project_format(project, legacy_version, expected_video):
    """The same legacy graph round-trips inside H13's explicit video envelope.

    expected_video comes from the pre-test state, never from the object under
    test. This catches lost/changed video configuration as well as wrong schema.
    """
    assert project['version'] == (5 if expected_video is not None else legacy_version), project
    assert project.get('video') == expected_video, (project.get('video'), expected_video)
    if expected_video is None:
        assert 'video' not in project, 'Legacy project must not contain even a null video extension'

class Client:
    def __init__(self):
        self.ops=[]
        self.p=subprocess.Popen([str(EXE),'mcp'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        self.rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'h7-verification','version':'1'}})
    def rpc(self,method,params=None):
        q={'jsonrpc':'2.0','id':len(self.ops)+1,'method':method,'params':params or {}}
        self.p.stdin.write(json.dumps(q)+'\n');self.p.stdin.flush()
        r=json.loads(self.p.stdout.readline());self.ops.append({'request':q,'response':r});assert 'error' not in r,r
        return r['result']
    def call(self,op,expect=True,**args):
        r=self.rpc('tools/call',{'name':op,'arguments':args});v=json.loads(r['content'][0]['text'])
        assert v['ok']==expect and r['isError']==(not expect),v
        return v
    def state(self):return self.call('status')['state']
    def wait(self,predicate,timeout=15):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            s=self.state()
            if predicate(s):return s
            time.sleep(.1)
        raise AssertionError(s)
    def stop(self):
        start=time.monotonic();response=self.call('stop_output')
        end=self.wait(lambda s:s['output'] in ('idle','error'),40)
        return {'response':response,'end':end,'elapsed':time.monotonic()-start}
    def close(self):self.p.stdin.close();self.p.wait(timeout=8)

def profile(id='h7-test',encoder='videotoolbox',bitrate=2500,keyframes=2,reorder=False):
    return {'id':id,'encoder':encoder,'bitrate_kbps':bitrate,'rate_control':'cbr','keyframe_seconds':keyframes,'frame_reordering':reorder}

def process_sample(pid):
    cpu,rss=subprocess.check_output(['ps','-p',str(pid),'-o','time=,rss='],text=True).split()
    seconds=0
    for x in cpu.split(':'):seconds=seconds*60+float(x)
    return seconds,int(rss)/1024

def measure(c,seconds,expected):
    s=c.state();pid=s['pid'];previous,_=process_sample(pid);start=last=time.monotonic();samples=[]
    while time.monotonic()-start<seconds:
        time.sleep(.5);s=c.state();assert s['output']==expected and not s['issues'],s
        cpu,rss=process_sample(pid);now=time.monotonic()
        samples.append({'seconds':now-start,'cpu_percent':100*(cpu-previous)/(now-last),'rss_mib':rss,'stats':s['stats']})
        previous=cpu;last=now
    steady=[x for x in samples if x['seconds']>=min(3,seconds/2)]
    return {'samples':samples,'cpu_median':statistics.median(x['cpu_percent'] for x in steady),
            'rss_median_mib':statistics.median(x['rss_mib'] for x in steady),'rss_range_mib':[min(x['rss_mib'] for x in samples),max(x['rss_mib'] for x in samples)]}

def media(path,minimum=2,geometry=(960,540),pixels=False):
    path=str(path)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
    v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (v['codec_name'],v['width'],v['height'],v['avg_frame_rate'])==('h264',*geometry,'30/1'),v
    assert a['codec_name']=='aac' and a['sample_rate']=='48000' and a['channels']==2,a
    assert int(v['nb_read_frames'])>=minimum*28
    d=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',path,'-f','null','-'],capture_output=True,check=True);assert not d.stderr,d.stderr
    frames=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_frames','-show_entries','frame=best_effort_timestamp_time,key_frame,pict_type','-of','json',path]))['frames']
    pts=[float(f['best_effort_timestamp_time']) for f in frames];gaps=[b-a for a,b in zip(pts,pts[1:])];assert min(gaps)>0
    keys=[float(f['best_effort_timestamp_time']) for f in frames if f['key_frame']]
    pcm=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',path,'-t','2','-vn','-ac','1','-ar','48000','-f','f32le','-'])
    samples=struct.unpack('<%df'%(len(pcm)//4),pcm);rms=math.sqrt(sum(x*x for x in samples)/len(samples));assert .02<rms<.08,rms
    result={'path':path,'probe':probe,'frames':len(frames),'pts_first':pts[0],'pts_last':pts[-1],
        'gaps_over_50ms':[{'index':i+1,'seconds':g} for i,g in enumerate(gaps) if g>.05],
        'max_interior_gap':max(gaps[:-4]),'b_frames':sum(f['pict_type']=='B' for f in frames),
        'max_keyframe_gap':max([b-a for a,b in zip(keys,keys[1:])],default=None),'audio_rms':rms,
        'bytes':pathlib.Path(path).stat().st_size,'sha256':hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}
    if pixels:
        def crop(t):return subprocess.check_output(['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',path,'-frames:v','1','-vf','crop=320:72:32:436','-pix_fmt','rgb24','-f','rawvideo','-'])
        first=crop(.5)
        mint=sum(all(abs(first[i+j]-[51,232,181][j])<32 for j in range(3)) for i in range(0,len(first),3))
        # A periodic animation may revisit its position at exactly 1.5 seconds.
        # Keep that observation, but sample multiple phases; a frozen overlay
        # still fails the same motion threshold. See H8's retained failed clip.
        changes={str(t):sum(abs(a-b)>25 for a,b in zip(first,crop(t))) for t in (.8,1.1,1.5,1.9)}
        changed=max(changes.values());assert mint>500 and changed>300,(mint,changed)
        result['overlay']={'mint_pixels':mint,'changed_channels':changed,'changed_channels_by_time':changes}
    return result

def setup_owned(c):
    s=c.state();assert s['output']=='idle' and all(x['spec']['kind'] in ('pattern','overlay') for x in s['project']['graph']['sources'])
    c.call('set_variant',variant='horizontal');c.call('select_audio',id='tone');c.call('set_overlay',visible=True)
    c.call('set_overlay_color',source_id='overlay',color=0x33e8b5)
    g=c.state()['project']['graph'];scene=next(x for x in g['scenes'] if x['id']==g['active_scene']);layer=next(x for x in scene['layers'] if x['source_id']=='overlay')
    c.call('set_transform',scene_id=scene['id'],layer_id=layer['id'],variant='horizontal',transform={'x':32,'y':436,'width':320,'height':72,'visible':True,'order':3})
    c.wait(lambda s:not s['issues'])
    return c.state()['project']
