#!/usr/bin/env python3
"""H10 real MCP/CLI recording + RTMP, independent meters, recovery and persistence.
Use only under the shared physical-test lock, with normal macOS permissions.
Plays an owned 997 Hz speaker fixture into the explicitly selected microphone.
"""
import argparse
import socket
from h7_support import Client, ROOT, EVIDENCE, EXE, process_sample
import hashlib, json, math, statistics, struct, subprocess, time
from verify_h10_audio import stimulus, power, tonal_amplitude


def cli(op, expect=True, **args):
    p = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **args})], capture_output=True, text=True, timeout=12)
    result = json.loads(p.stdout)
    assert result['ok'] == expect, result
    return result


def decoded(path):
    d = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    assert not d.stderr, d.stderr
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn',
                                   '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'])
    return struct.unpack('<%df' % (len(raw)//4), raw)


def db(value):
    return 20 * math.log10(max(value, 1e-15))


def isolated_rms(samples, stage, index):
    # libobs 33.0.1 obs-audio-controls.c:volmeter_process_magnitude computes
    # RMS per audio buffer. A median of those readings is NOT whole-second
    # energy RMS when a physical signal contains transients. Compare the same
    # statistic on the same interval, keeping the original 2 dB tolerance.
    # These decoded 20 ms blocks approximate capture-buffer duration; this is
    # a sampled meter comparison, not a sample-exact timestamp calibration.
    observations = stage['samples'][3:]
    assert len(observations) >= 8
    lo, hi = observations[0]['seconds'], observations[-1]['seconds']
    native = [s['state']['audio_mixer']['runtime']['inputs'][index]['levels']['rms_dbfs'][0]
              for s in observations]
    assert all(v is not None and math.isfinite(v) for v in native), native
    blocks = []
    for offset in range(round(lo * 48000), round(hi * 48000) - 959, 960):
        block = samples[offset:offset + 960]
        assert len(block) == 960
        blocks.append(db(math.sqrt(sum(x*x for x in block)/len(block))))
    assert len(blocks) >= 50
    native_median, decoded_median = statistics.median(native), statistics.median(blocks)
    return {'window_seconds': [lo, hi], 'decoded_block_ms': 20,
            'native_dbfs': native, 'decoded_block_dbfs': blocks,
            'native_median_dbfs': native_median, 'decoded_median_dbfs': decoded_median,
            'error_db': decoded_median - native_median}


def analyse(path, stages):
    samples = decoded(path)
    result = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'duration': len(samples)/48000,
              'peak_dbfs': db(max(abs(x) for x in samples)), 'stages': {}}
    for stage in stages:
        # Interior second, away from source/encoder action boundaries and AAC priming.
        offset = round((stage['start'] + 1) * 48000)
        chunk = samples[offset:offset+48000]
        assert len(chunk) == 48000
        result['stages'][stage['name']] = {'rms_dbfs': db(math.sqrt(sum(x*x for x in chunk)/len(chunk))),
                                          'coherent_a440':power(chunk,440), 'a440': tonal_amplitude(chunk, 440), 'a997': tonal_amplitude(chunk, 997)}
    r = result['stages']
    assert r['both']['a440'] > .005 and r['both']['a997'] > .00001, r['both']
    result['gain_delta_db'] = db(r['lower']['a440']/r['both']['a440'])
    assert -13 < result['gain_delta_db'] < -11, result
    for name in ('mic_muted', 'mic_disconnected'):
        assert r[name]['a997'] < r['both']['a997']*.02, (name, r[name])
        assert abs(db(r[name]['a440']/r['lower']['a440'])) < .6, (name, r[name])
    for name in ('mic_unmuted', 'mic_recovered', 'video_changes'):
        assert r[name]['a997'] > r['both']['a997']*.4, (name, r[name])
    assert r['tone_muted']['a440'] < r['tone_before_mute']['a440']*.03, r['tone_muted']
    assert r['both_muted']['rms_dbfs'] < -100, r['both_muted']
    # Match native per-input RMS to decoded isolated channels. Physical speaker
    # acoustics can vary, so retain all samples and allow a measured 2 dB margin.
    errors, meter_windows = {}, {}
    for name, index in [('mic_muted', 1), ('tone_muted', 0)]:
        stage = next(s for s in stages if s['name'] == name)
        meter_windows[name] = isolated_rms(samples, stage, index)
        errors[name] = meter_windows[name]['error_db']
        assert abs(errors[name]) < 2, (name, meter_windows[name])
    result['microphone_gain_delta_db'] = db(r['mic_lower']['a997']/r['mic_unmuted']['a997'])
    assert -14 < result['microphone_gain_delta_db'] < -10, result['microphone_gain_delta_db']
    result['isolated_rms_error_db'] = errors
    result['isolated_rms_windows'] = meter_windows
    assert result['peak_dbfs'] < -.5, result['peak_dbfs']
    # The 440 Hz path stays continuous through microphone disconnect and all
    # Cut/Fade switches. Check every 100 ms window of these complete sections.
    continuity = {}
    for name in ('mic_disconnected', 'mic_recovered', 'video_changes'):
        stage = next(s for s in stages if s['name'] == name)
        lo, hi = round((stage['start']+.2)*48000), round((stage['end']-.2)*48000)
        amps = [power(samples[i:i+4800], 440) for i in range(lo, hi-4799, 4800)]
        assert min(amps) > r['lower']['a440']*.55, (name, min(amps))
        continuity[name] = {'amplitude_min': min(amps), 'amplitude_max': max(amps), 'windows': len(amps)}
    result['continuity_100ms'] = continuity
    packets = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_packets',
        '-show_entries', 'packet=codec_type,pts_time,dts_time', '-of', 'json', str(path)]))['packets']
    result['timestamps'] = {}
    for kind in ('audio', 'video'):
        typed = [p for p in packets if p['codec_type'] == kind]
        dts = [float(p['dts_time']) for p in typed if 'dts_time' in p]
        assert all(b > a for a, b in zip(dts, dts[1:]))
        if kind == 'audio':
            times = [float(p['pts_time']) for p in typed]
        else:
            frames = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v',
                '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))['frames']
            times = [float(f['best_effort_timestamp_time']) for f in frames]
        gaps = [b-a for a,b in zip(times,times[1:])]
        assert min(gaps) > 0
        if kind == 'audio': assert max(gaps) <= .023, max(gaps)
        else: assert max(gaps[:-4]) <= .035, max(gaps[:-4])
        result['timestamps'][kind] = {'samples': len(times), 'packets_without_dts':len(typed)-len(dts), 'max_gap_ms': max(gaps)*1000,
                                       'max_interior_gap_ms': max(gaps[:-4])*1000}
    visual = next(s for s in stages if s['name'] == 'video_changes')
    pixels = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(visual['start']),
        '-i', str(path), '-t', str(visual['end']-visual['start']), '-vf', 'crop=4:60:32:440,scale=1:1',
        '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    colors = [list(pixels[i:i+3]) for i in range(0,len(pixels),3)]
    def near(c, target):return max(abs(a-b) for a,b in zip(c,target))<35
    a = sum(near(c,[51,232,181]) for c in colors)
    b = sum(near(c,[232,62,75]) for c in colors)
    mixed = {tuple(c) for c in colors if not near(c,[51,232,181]) and not near(c,[232,62,75])}
    assert a >= 5 and b >= 5 and len(mixed) >= 10, (a,b,len(mixed))
    result['video_changes'] = {'mint_frames':a,'red_frames':b,'distinct_blended_colors':len(mixed),'stripe_rgb':colors}
    return result


def listener():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    path = EVIDENCE / f'h10-stream-{time.time_ns()}.flv'
    with (EVIDENCE/'h10-receiver.log').open('w') as log:
        p = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'info', '-listen', '1', '-i',
            f'rtmp://127.0.0.1:{port}/live/motive', '-c', 'copy', str(path)], stdout=subprocess.DEVNULL, stderr=log)
    for _ in range(80):
        assert p.poll() is None
        if subprocess.run(['lsof', '-a', '-p', str(p.pid), '-iTCP:'+str(port), '-sTCP:LISTEN'], capture_output=True).returncode == 0:
            return p, path, port
        time.sleep(.1)
    p.terminate(); p.wait(); raise AssertionError('receiver did not listen')


def exercise(c, mic, tone, scene_a, scene_b, kind, path=None):
    for input_id, gain in [(mic, 6), (tone, -6)]:
        c.call('set_audio_gain', input_id=input_id, gain_db=gain)
        c.call('set_audio_mute', input_id=input_id, muted=False)
    c.call('configure_transition', transition={'kind':'cut','duration_ms':0})
    c.call('select_scene', scene_id=scene_a)
    before = c.state()
    ready = c.call('start_recording' if kind == 'recording' else 'start_stream')['state']
    ready = c.wait(lambda s:s['output'] == kind)
    path = path or ROOT / ready['output_path']
    start = time.monotonic(); previous_cpu, _ = process_sample(ready['pid']); last = start
    last_frames = ready['stats']['encoded_frames']
    tone_instance = next(i['instance_id'] for i in ready['audio_mixer']['runtime']['inputs'] if i['id']==tone)
    stages = []
    def sample():
        nonlocal previous_cpu, last, last_frames
        state = c.state(); now = time.monotonic(); cpu, rss = process_sample(ready['pid'])
        assert state['pid'] == ready['pid'] and state['output'] == kind
        assert state['stats']['encoded_frames'] >= last_frames
        assert state['output_path'] == ready['output_path']
        for field in ('source_instances_created','scenes_built'):
            assert state['transition'][field] == ready['transition'][field]
        assert next(i['instance_id'] for i in state['audio_mixer']['runtime']['inputs'] if i['id']==tone) == tone_instance
        assert state['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0
        value = {'seconds':now-start, 'cpu_percent':100*(cpu-previous_cpu)/(now-last), 'rss_mib':rss, 'state':state}
        previous_cpu, last, last_frames = cpu, now, state['stats']['encoded_frames']
        return value
    def hold(name, seconds=3):
        stage = {'name':name,'start':time.monotonic()-start,'samples':[]}; stages.append(stage)
        until = time.monotonic()+seconds
        while time.monotonic()<until:
            time.sleep(.15); stage['samples'].append(sample())
        stage['end'] = time.monotonic()-start
        return stage
    hold('both')
    c.call('set_audio_gain', input_id=tone, gain_db=-18); hold('lower')
    c.call('set_audio_mute', input_id=mic, muted=True); hold('mic_muted')
    c.call('set_audio_mute', input_id=mic, muted=False); hold('mic_unmuted')
    c.call('set_audio_gain', input_id=mic, gain_db=-6); hold('mic_lower')
    c.call('set_audio_gain', input_id=mic, gain_db=6)
    # Use a clearly measurable reference above the physical microphone's
    # ambient 440 Hz-band noise, retaining the same >30 dB mute suppression gate.
    c.call('set_audio_gain', input_id=tone, gain_db=0); hold('tone_before_mute')
    c.call('set_audio_mute', input_id=tone, muted=True); hold('tone_muted')
    c.call('set_audio_mute', input_id=mic, muted=True); hold('both_muted')
    c.call('set_audio_mute', input_id=mic, muted=False)
    c.call('set_audio_mute', input_id=tone, muted=False)
    c.call('set_audio_gain', input_id=tone, gain_db=-18)
    c.call('disconnect_audio_input', input_id=mic)
    disconnected = c.state(); assert disconnected['audio_mixer']['runtime']['inputs'][0]['phase']=='disconnected'
    hold('mic_disconnected')
    c.call('reconnect_audio_input', input_id=mic)
    recovered = c.wait(lambda s:s['audio_mixer']['runtime']['inputs'][0]['phase']=='ready')
    assert recovered['audio_mixer']['runtime']['inputs'][0]['instance_id'] != ready['audio_mixer']['runtime']['inputs'][0]['instance_id']
    hold('mic_recovered')
    stage = hold('video_changes', 2)
    for transition, scene in [('cut',scene_b),('cut',scene_a),('fade',scene_b),('fade',scene_a)]:
        c.call('configure_transition', transition={'kind':transition,'duration_ms':1000 if transition=='fade' else 0})
        c.call('select_scene', scene_id=scene)
        until=time.monotonic()+6
        while True:
            time.sleep(.1); value=sample(); stage['samples'].append(value)
            if value['state']['transition']['phase']=='completed':break
            assert time.monotonic()<until
        time.sleep(.3)
    stage['end']=time.monotonic()-start
    stopped=c.stop(); assert stopped['end']['output']=='idle'
    assert stopped['end']['audio_mixer']['runtime']['mix']['clipped_blocks']==0
    observations=[v for s in stages for v in s['samples']]
    return {'before':before, 'started':ready, 'stopped':stopped, 'stages':stages, 'path':path,
            'cpu_median':statistics.median(v['cpu_percent'] for v in observations),
            'rss_median_mib':statistics.median(v['rss_mib'] for v in observations)}


def restart(c):
    pid=c.state()['pid'];c.call('shutdown')
    for _ in range(80):
        if subprocess.run(['kill','-0',str(pid)],capture_output=True).returncode:break
        time.sleep(.1)
    else:raise AssertionError('app did not close')
    subprocess.run(['open','-n','--stdout',str(EVIDENCE/'h10-restart.log'),'--stderr',str(EVIDENCE/'h10-restart-stderr.log'),str(ROOT/'target/Motive.app')],check=True)
    for _ in range(80):
        p=subprocess.run([str(EXE),'ctl','{"op":"status"}'],capture_output=True,text=True)
        v=json.loads(p.stdout)
        if v['ok']:assert v['state']['pid']!=pid;return v['state']
        time.sleep(.2)
    raise AssertionError(v)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--microphone-id',required=True);args=parser.parse_args()
    c=Client();report={'ok':False,'physical_hot_unplug':'not tested; explicit native release/reopen tested'}
    receiver=playback=None;scene_b=overlay_b=None
    try:
        initial=c.state();assert initial['output']=='idle' and not initial['audio_mixer']['store']['inputs']
        tools={t['name']:t for t in c.rpc('tools/list')['tools']}
        assert {'audio_mixer','add_audio_input','set_audio_gain','set_audio_mute','disconnect_audio_input','reconnect_audio_input','save_audio_mixer','load_audio_mixer','remove_audio_input'} <= tools.keys()
        assert tools['audio_mixer']['annotations']['readOnlyHint']
        scene_a=initial['project']['graph']['active_scene']
        c.call('add_audio_input',name='Physical microphone',source={'kind':'microphone','device_id':args.microphone_id})
        s=c.call('add_audio_input',name='Controlled tone',source={'kind':'tone'})['state'];mic,tone=[i['id'] for i in s['audio_mixer']['store']['inputs']]
        c.wait(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']))
        before=c.call('audio_mixer');shared=cli('audio_mixer');assert before['pid']==shared['pid'] and before['revision']==shared['revision'] and before['audio_mixer']['store']==shared['audio_mixer']['store']
        for op, fields in [('set_audio_gain',{'input_id':tone,'gain_db':24.1}),('set_audio_mute',{'input_id':'missing','muted':True}),('add_audio_input',{'name':'bad','source':{'kind':'microphone','device_id':'not-a-real-device'}})]:
            before=c.state();c.call(op,expect=False,**fields);after=c.state()
            assert after['audio_mixer']['store']==before['audio_mixer']['store']
            assert after['audio_mixer']['runtime']['instances_created']==before['audio_mixer']['runtime']['instances_created']
        c.call('add_audio_input',name='reuse',source={'kind':'microphone','device_id':args.microphone_id})
        assert c.state()['audio_mixer']['runtime']['instances_created']==initial['audio_mixer']['runtime']['instances_created']+2
        scene_b=c.call('create_scene',name='H10 red scene')['state']['project']['graph']['active_scene']
        c.call('add_layer',scene_id=scene_b,source_id='main')
        sources={s['id'] for s in c.state()['project']['graph']['sources']}
        state=c.call('add_source',scene_id=scene_b,name='H10 red overlay',source={'kind':'overlay','color':0xe83e4b})['state']
        overlay_b=next(s['id'] for s in state['project']['graph']['sources'] if s['id'] not in sources)
        fixture=ROOT/'var/h10-speaker-997.wav';stimulus(fixture,120)
        playback=subprocess.Popen(['afplay','-v','0.5',str(fixture)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        time.sleep(1)
        for kind in ('recording','streaming'):
            path=None
            if kind=='streaming':
                receiver,path,port=listener();c.call('configure_stream',endpoint={'transport':'rtmp','port':port})
            r=exercise(c,mic,tone,scene_a,scene_b,kind,path)
            if receiver:receiver.wait(timeout=10);receiver=None
            path=r.pop('path');r['path']=str(path);report[kind]=r;r['decoded']=analyse(path,r['stages'])
        # A separate deliberately saturated output verifies warnings. Earlier
        # acceptance outputs explicitly require zero clipping throughout.
        c.call('set_audio_gain',input_id=tone,gain_db=24);c.call('set_audio_gain',input_id=mic,gain_db=12)
        path=c.call('start_recording')['state']['output_path'];time.sleep(3)
        saturated=c.state();c.stop()
        assert saturated['audio_mixer']['runtime']['mix']['clipped_blocks']>0
        assert any(i['code']=='AUDIO_MIX_CLIPPING' for i in saturated['audio_mixer']['issues'])
        report['intentional_clipping']={'path':path,'state':saturated,'decoded_peak_dbfs':db(max(abs(x) for x in decoded(path)))}
        c.call('set_audio_gain',input_id=tone,gain_db=-18);c.call('set_audio_gain',input_id=mic,gain_db=6)
        c.call('set_audio_mute',input_id=mic,muted=True)
        project=c.call('save_project')['state']['project'];profiles=c.call('output_profiles')['store'];c.call('save_output_profiles')
        saved=c.call('save_audio_mixer')['state']['audio_mixer']['store']
        scene_bytes=(ROOT/'var/project.json').read_bytes();profile_bytes=(ROOT/'var/output-profiles.json').read_bytes()
        instances=c.state()['audio_mixer']['runtime']['instances_created']
        c.call('set_audio_gain',input_id=tone,gain_db=-30);c.call('load_audio_mixer')
        assert c.state()['audio_mixer']['store']==saved and c.state()['audio_mixer']['runtime']['instances_created']==instances
        # Exercise ID permutations without files: remove and re-add assigns new
        # IDs, then load must reuse both physical resources under persisted IDs.
        for input_id in (tone,mic):c.call('remove_audio_input',input_id=input_id)
        for i in reversed(saved['inputs']):c.call('add_audio_input',name=i['name'],source=i['source'])
        count=c.state()['audio_mixer']['runtime']['instances_created'];c.call('load_audio_mixer')
        assert c.state()['audio_mixer']['store']==saved and c.state()['audio_mixer']['runtime']['instances_created']==count
        c.call('disconnect_audio_input',input_id=mic);c.call('load_audio_mixer')
        c.wait(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']))
        boot=restart(c);assert boot['audio_mixer']['store']['inputs']==[]
        c.call('load_project');c.call('load_output_profiles');c.call('load_audio_mixer')
        restored=c.wait(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']))
        assert restored['audio_mixer']['store']==saved and restored['project']==project and c.call('output_profiles')['store']==profiles
        assert (ROOT/'var/project.json').read_bytes()==scene_bytes and (ROOT/'var/output-profiles.json').read_bytes()==profile_bytes
        restored_path=c.call('start_recording')['state']['output_path'];time.sleep(3);c.stop()
        restored_samples=decoded(restored_path)[48000:96000]
        restored_audio={'path':restored_path,'tone_amplitude':tonal_amplitude(restored_samples,440),
                        'microphone_amplitude':tonal_amplitude(restored_samples,997)}
        assert abs(db(restored_audio['tone_amplitude']) - (-24-18)) < .5, restored_audio
        assert restored_audio['microphone_amplitude'] < 1e-5, restored_audio
        report['persistence']={'saved':saved,'boot':boot,'restored':restored,'restored_audio':restored_audio,
            'project_sha256':hashlib.sha256(scene_bytes).hexdigest(),'profile_sha256':hashlib.sha256(profile_bytes).hexdigest()}
        report['ok']=True
    except BaseException as failure:
        report['error']=repr(failure);raise
    finally:
        if playback:playback.terminate();playback.wait(timeout=5)
        if receiver and receiver.poll() is None:receiver.terminate();receiver.wait(timeout=5)
        try:
            c.stop();c.call('configure_transition',transition={'kind':'cut','duration_ms':0})
            c.call('select_scene',scene_id='scene-1')
            if scene_b:c.call('remove_scene',scene_id=scene_b)
            if overlay_b:c.call('remove_source',source_id=overlay_b)
            for i in c.state()['audio_mixer']['store']['inputs']:c.call('remove_audio_input',input_id=i['id'])
        except Exception as failure:report['cleanup_error']=repr(failure)
        report['operations']=c.ops;c.close()
        report['app_sha256']=hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
        (EVIDENCE/'h10-mixer.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k in ('ok','error','app_sha256')},indent=2))


if __name__=='__main__':main()
