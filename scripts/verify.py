#!/usr/bin/env python3
"""Real acceptance check. Open Motive and its controlled source window first.
Writes only under var; sends streaming traffic only to loopback UDP 19350.
"""
import json, math, pathlib, statistics, struct, subprocess, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EXE = VERIFY.client_executable
EVIDENCE = ROOT / 'var/evidence'
report = {'checks': [], 'samples': []}

def ctl(op, expect=True, **args):
    result = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **args})], capture_output=True, text=True, timeout=10)
    value = json.loads(result.stdout)
    if expect:
        assert value['ok'], value
    else:
        assert not value['ok'], value
    return value

def idle():
    end = time.monotonic() + 12
    while time.monotonic() < end:
        state = ctl('status')['state']
        if state['output'] == 'idle':
            assert state['output_code'] == 0, state
            return state
        assert state['output'] != 'error', state
        time.sleep(.2)
    raise AssertionError('Output did not finalize in 12 seconds')

def verify_file(path, width, height, min_seconds):
    result = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', path], capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    assert any(s['codec_type']=='audio' for s in info['streams']), 'Missing audio stream'
    audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height']) == (width, height), video
    assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
    assert float(info['format']['duration']) >= min_seconds, info
    assert int(video['nb_read_frames']) >= min_seconds * 29, video
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-f', 'null', '-'], check=True, capture_output=True)
    pcm = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-t', '2', '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    samples = struct.unpack('<' + 'f' * (len(pcm)//4), pcm)
    rms = math.sqrt(sum(s*s for s in samples)/len(samples))
    assert .02 < rms < .08, rms
    raw_scene = subprocess.run(['ffmpeg','-nostdin','-v','error','-ss','1','-i',path,'-frames:v','1','-vf',f'crop={width}:{height-130}:0:0','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
    nonblack = sum(1 for i in range(0,len(raw_scene),3) if max(raw_scene[i:i+3])>40)
    assert nonblack > 10000, ('Missing source content outside overlay', nonblack)
    crops = []
    for second in (.5, 1, 1.5, 2, 2.5):
        raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(second), '-i', path, '-frames:v', '1', '-vf', f'crop=320:72:32:{height-104}', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
        crops.append(raw)
    assert len(crops[0]) == 320*72*3
    teal = sum(1 for i in range(0, len(crops[0]), 3) if 30<crops[0][i]<100 and crops[0][i+1]>175 and crops[0][i+2]>100)
    changed = max(sum(abs(a-b)>25 for a,b in zip(crops[0],sample)) for sample in crops[1:])
    assert teal > 500 and changed > 300, (teal, changed)
    return {'path':path, 'duration':info['format']['duration'], 'frames':video['nb_read_frames'], 'width':width, 'height':height, 'audio_rms':rms, 'overlay_teal_pixels':teal, 'overlay_changed_channels':changed,'source_nonblack_pixels':nonblack}

try:
    state = idle(); report['pid'] = state['pid']
    devices = ctl('devices')['devices']
    assert devices['screen_permission'], 'Grant screen permission normally; no bypass.'
    assert devices['windows'], 'Open the controlled source window in Motive first.'
    window = next(w['id'] for w in devices['windows'] if w.get('test'))
    ctl('select_source', window_id=window)
    ctl('select_audio', id='tone')
    ctl('set_variant', variant='horizontal')
    ctl('set_overlay', visible=True)
    missing = ctl('select_source', expect=False, window_id=4294967295)
    assert missing['error']['code'] == 'SOURCE_UNAVAILABLE'
    invalid = ctl('start_local_stream', expect=False, url='https://example.invalid')
    assert invalid['error']['code'] == 'INVALID_ARGUMENT'
    if not devices['microphone_permission']:
        denied = ctl('select_audio', expect=False, id='default')
        assert denied['error']['code'] == 'MICROPHONE_PERMISSION_DENIED'
        report['checks'].append('Microphone denied: real OS state; no prompt or recording')
    ctl('save_project')
    ctl('set_overlay', visible=False)
    restored = ctl('load_project')['state']
    assert restored['project']['overlay'] and restored['project']['capture_window']
    report['checks'].append('Project save/load restores capture, audio, variant and overlay')
    ready_deadline=time.monotonic()+8
    while ctl('status')['state']['stats']['capture_width']==0:
        assert time.monotonic()<ready_deadline, 'Capture not ready after restore'
        time.sleep(.1)
    recording = ctl('start_recording')['state']
    path = recording['output_path']
    assert ctl('set_variant', expect=False, variant='vertical')['error']['code'] == 'OUTPUT_BUSY'
    assert ctl('start_recording', expect=False)['error']['code'] == 'OUTPUT_BUSY'
    start = time.monotonic()
    print('Recording 65 seconds of real window capture + tone + animated overlay', flush=True)
    while time.monotonic()-start < 65:
        sample = ctl('status')['state']
        assert sample['output'] == 'recording' and sample['pid'] == report['pid']
        assert sample['stats']['capture_width']>0 and not sample.get('issues'), sample
        ps = subprocess.run(['ps','-p',str(report['pid']),'-o','%cpu=,rss='], capture_output=True,text=True,check=True).stdout.split()
        report['samples'].append({'elapsed':round(time.monotonic()-start,2),'cpu_percent':float(ps[0]),'rss_kib':int(ps[1]),'stats':sample['stats']})
        time.sleep(1)
    ctl('stop_output'); report['horizontal_end'] = idle()
    report['horizontal'] = verify_file(path,960,540,60)
    print('Horizontal recording and audio verified', flush=True)
    ctl('snapshot'); (EVIDENCE/'horizontal.png').write_bytes((VERIFY.diagnostics_root/'preview.png').read_bytes())
    ctl('set_variant', variant='vertical')
    vertical = ctl('start_recording')['state']['output_path']
    time.sleep(4)
    ctl('stop_output');idle()
    report['vertical'] = verify_file(vertical,540,960,3)
    ctl('snapshot'); (EVIDENCE/'vertical.png').write_bytes((VERIFY.diagnostics_root/'preview.png').read_bytes())
    ctl('load_project')
    ready_deadline=time.monotonic()+8
    while ctl('status')['state']['stats']['capture_width']==0:
        assert time.monotonic()<ready_deadline, 'Capture not ready after restore'
        time.sleep(.1)
    print('Vertical composition and project restore verified', flush=True)
    stream_path = EVIDENCE / ('loopback-'+str(time.time_ns())+'.ts')
    receiver = subprocess.Popen(['ffmpeg','-nostdin','-v','error','-i','udp://127.0.0.1:19350?localaddr=127.0.0.1&fifo_size=1000000&overrun_nonfatal=1','-t','5','-c','copy',str(stream_path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        time.sleep(.3)
        ctl('start_local_stream')
        _,err=receiver.communicate(timeout=25)
        assert receiver.returncode == 0, err.decode()
    finally:
        ctl('stop_output');idle()
        if receiver.poll() is None:
            receiver.terminate();receiver.communicate(timeout=5)
    report['loopback'] = verify_file(str(stream_path),960,540,4)
    report['checks'].append('libobs MPEG-TS -> UDP 127.0.0.1 -> FFmpeg receiver; no public service')
    cpu=[s['cpu_percent'] for s in report['samples']];rss=[s['rss_kib']/1024 for s in report['samples']]
    report['metrics']={'cpu_percent_median':statistics.median(cpu),'cpu_percent_max':max(cpu),'rss_mib_min':min(rss),'rss_mib_max':max(rss),'note':'ps process samples; CPU can exceed 100%. Debug build; includes UI and controlled source window; not a comparative benchmark.'}
    report['ok']=True
except BaseException as e:
    report['ok']=False;report['error']=repr(e)
    try: ctl('stop_output');idle()
    except Exception: pass
    raise
finally:
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    (EVIDENCE/'acceptance.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2),flush=True)
