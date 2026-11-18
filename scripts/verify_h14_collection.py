#!/usr/bin/env python3
"""Bounded owned-window A/B trial. Never launch/quit/focus apps or enumerate windows.

Root launches a fresh fixture, supplies its observed PID/window ID, and records
three CUA focus observations with `mark`. `run` captures only that exact window;
`analyze` is an explicit later CPU window, never automatic during collection.
"""
import argparse
import ctypes
import hashlib
import json
import os
import pathlib
import plistlib
import socket
import stat
import subprocess
import time
import traceback

from h14_collection_helpers import (PHASES, collection_profile_id, counter_patches, counter_summary, decode_counter, focus_conditions, owned_stop_command,
    require, unique_owned_tone, validate_fixture, validate_manifest, validate_markers, validate_media_duration)

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIMIT = 16 * 1024 * 1024


def digest(path):
    result = hashlib.sha256()
    with pathlib.Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def load(path, limit=LIMIT):
    path = pathlib.Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, 'Invalid bounded input file')
    return json.loads(path.read_text())


def lines(path):
    path = pathlib.Path(path)
    if not path.exists():
        require(not path.is_symlink(), 'Dangling evidence link')
        return []
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT, 'Invalid JSONL evidence')
    data = path.read_bytes()
    # Writer may be between fwrite and newline: defer its incomplete last row.
    return [json.loads(row) for row in data.split(b'\n')[:-1] if row]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def lock():
    common = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip())
    if not common.is_absolute(): common = ROOT / common
    owner = load(common.resolve().parent / 'var/run/physical-test.lock/OWNER')
    require(owner['worktree'] == str(ROOT), 'Caller must own the canonical physical lock')
    return owner


def executable(bundle, identifier):
    bundle = pathlib.Path(bundle).resolve(strict=True)
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    require(info['CFBundleIdentifier'] == identifier, 'Wrong bundle identity')
    binary = (bundle / 'Contents/MacOS' / info['CFBundleExecutable']).resolve(strict=True)
    require(binary.is_relative_to(bundle), 'Bundle executable escapes its bundle')
    return binary


def process_identity(pid, binary):
    # libproc inspects only the exact PID supplied and observed by root.
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(4096)
    require(lib.proc_pidpath(pid, buffer, len(buffer)) > 0, 'Observed PID no longer exists')
    require(pathlib.Path(os.fsdecode(buffer.value)).resolve() == binary, 'PID does not execute the expected bundle')
    birth = subprocess.check_output(['/bin/ps', '-p', str(pid), '-o', 'lstart='], text=True).strip()
    require(bool(birth), 'PID birth identity unavailable')
    return {'pid': pid, 'binary': str(binary), 'birth': birth}


def clock_anchor():
    # Local Foundation call, no NSApplication/window creation. This is the same
    # named clock API used by the fixture, sampled inside a host-clock bracket.
    ctypes.CDLL('/System/Library/Frameworks/Foundation.framework/Foundation')
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes = [ctypes.c_char_p]; objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]; objc.sel_registerName.restype = ctypes.c_void_p
    pointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
    number = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
    info = pointer(objc.objc_getClass(b'NSProcessInfo'), objc.sel_registerName(b'processInfo'))
    before, wall_before = time.monotonic(), time.time()
    uptime = number(info, objc.sel_registerName(b'systemUptime'))
    after, wall_after = time.monotonic(), time.time()
    return {'fixture_clock': 'NSProcessInfo.systemUptime', 'fixture_clock_s': uptime,
            'host_clock': 'python.time.monotonic', 'host_before_s': before, 'host_after_s': after,
            'wall_before_unix': wall_before, 'wall_after_unix': wall_after,
            'offset_interval_s': [before-uptime, after-uptime],
            'event_delivery_latency': 'not assumed; log ingestion has separate brackets'}


def compact(state):
    return {key: state[key] for key in ('pid', 'revision', 'project', 'sources', 'issues', 'outputs',
        'stats', 'transition', 'output_lifecycle', 'audio_mixer')}


class Client:
    def __init__(self, bundle, owner_pid, out):
        marker = pathlib.Path(bundle) / 'Contents/Resources/MotivePortable.json'
        if marker.exists():
            require(load(marker) == {'version': 1, 'runtime_layout': 'macos-portable-v1'}, 'Unknown portable layout')
            self.socket = pathlib.Path.home() / 'Library/Application Support/local.motive.studio/run/motive.sock'
        else:
            self.socket = ROOT / 'var/run/motive.sock'
        require(stat.S_ISSOCK(self.socket.lstat().st_mode), 'Expected owner control socket')
        self.pid, self.out = owner_pid, out
        self.last_bracket = None

    def call(self, op, allow_error=False, **args):
        command = {'op': op, **args}; before, wall = time.monotonic(), time.time()
        with socket.socket(socket.AF_UNIX) as channel:
            channel.settimeout(7); channel.connect(str(self.socket))
            # Darwin sys/un.h: SOL_LOCAL=0, LOCAL_PEERPID=2. Validate the
            # connected peer before sending even one mutation; pathname/PID
            # checks alone cannot exclude a restarted owner between calls.
            require(channel.getsockopt(0, 2) == self.pid, 'Connected control peer is not the expected owner')
            channel.sendall((json.dumps({'command': command, 'origin': 'cli'})+'\n').encode())
            with channel.makefile('rb') as response:
                data = response.readline(1024*1024+1)
        require(len(data) <= 1024*1024 and data.endswith(b'\n'), 'Bounded control response required')
        value = json.loads(data); self.last_bracket = [before, time.monotonic()]
        pid = value.get('pid', value.get('state', {}).get('pid', self.pid))
        require(pid == self.pid, 'Control owner PID changed')
        with (self.out/'operations.jsonl').open('a') as log:
            log.write(json.dumps({'request': command, 'host_clock': 'python.time.monotonic',
                'host_bracket_s': self.last_bracket, 'wall_request_unix': wall, 'ok': value.get('ok'),
                'error': value.get('error')})+'\n')
        require(allow_error or value.get('ok') is True, f'Command rejected: {value.get("error")}')
        return value

    def state(self): return self.call('status')['state']


def default_owner(state):
    graph = state['project']['graph']
    require(len(graph['scenes']) == 1 and graph['active_scene'] == graph['scenes'][0]['id'], 'Fresh default scene required')
    require({s['id']: s['spec']['kind'] for s in graph['sources']} == {'main': 'pattern', 'overlay': 'overlay'},
            'Only default pattern/legacy overlay are permitted initially')
    require(len(graph['scenes'][0]['layers']) == 2 and state['project']['variant'] == 'horizontal', 'Default landscape layout required')
    layer = next(x for x in graph['scenes'][0]['layers'] if x['source_id'] == 'main')['layouts']['horizontal']
    require(all(layer[k] == v for k, v in {'x':0,'y':0,'width':960,'height':540,'visible':True}.items()),
            'Full-canvas main layer required for counter geometry')
    require(not state['audio_mixer']['store']['inputs'], 'Empty mixer required; never restore physical capture')
    require(state['destinations']['selected'] is None and state['output_configuration']['credential_ref'] is None,
            'No external destination or credential may be selected')
    require(all(not o['native_busy'] and not o['recovery_required'] for o in state['outputs'].values()), 'Owner must be idle/recovered')
    require(not state['show_control'].get('configured') and not state['output_lifecycle']['shutdown_requested'], 'Fresh non-closing owner required')


class Receiver:
    def __init__(self, binary, out, port):
        self.path = out/'received.mkv'
        with (out/'receiver-stderr.txt').open('w') as log:
            self.process = subprocess.Popen([binary, '-nostdin', '-v', 'error', '-listen', '1', '-i',
                f'rtmp://127.0.0.1:{port}/live/motive', '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', str(self.path)],
                stdout=subprocess.DEVNULL, stderr=log)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            require(self.process.poll() is None, 'Owned loopback receiver exited')
            found = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(self.process.pid), '-iTCP:'+str(port),
                                    '-sTCP:LISTEN'], capture_output=True)
            if found.returncode == 0: return
            time.sleep(.1)
        self.close(); raise ValueError('Owned receiver did not listen')

    def close(self):
        if self.process.poll() is None: self.process.terminate()
        return self.process.wait(timeout=8)


def run_trial(args):
    lock_owner = lock(); manifest = validate_manifest(load(args.manifest, 65536))
    out = pathlib.Path(args.output).resolve(); require(out.is_relative_to((ROOT/'var/evidence').resolve()), 'Use a new worktree evidence directory')
    out.mkdir(parents=True, exist_ok=False)
    report = {'version':1,'status':'FAIL','manifest':manifest,'lock':lock_owner,'samples':[], 'media':[],
              'limits':['Focus observations and fixture draw counts do not prove fresh captured pixels.',
                        'SCStreamFrameInfoDisplayTime is NOT_EXPOSED by the current diagnostic contract.',
                        'No cross-clock subtraction without an explicit bracket; fixture metadata is not decoded content.',
                        'No external destination, physical audio/camera, app launch, GUI control or automatic restart.']}
    client = receiver = initial = None; changed = False; tone = None; profile_id = collection_profile_id(manifest['trial_id'])
    attempted = {}; owned = {}; profiles_created = False; start = end = None; prior_fixture_rows = 0
    tone_name = 'H14 collection internal tone '+manifest['trial_id']; prior_audio_ids = set(); tone_attempted = False
    def flush(): save(out/'report.json', report)
    def sample(label):
        nonlocal prior_fixture_rows
        before, wall = time.monotonic(), time.time(); events = lines(manifest['fixture']['log'])
        ready, fixture_states = validate_fixture(events, manifest)
        require(len(events) >= prior_fixture_rows, 'Fixture log was truncated')
        report['fixture_ready'] = ready
        with (out/'fixture-events.jsonl').open('a') as log:
            for event in events[prior_fixture_rows:]:
                log.write(json.dumps({'event':event,'ingestion_host_bracket_s':[before,time.monotonic()],
                                     'ingestion_wall_unix':wall})+'\n')
        prior_fixture_rows = len(events)
        markers = validate_markers(lines(manifest['markers']), manifest); report['markers'] = markers
        state = client.state(); row = {'label':label,'host_bracket_s':client.last_bracket,
            'host_clock':'python.time.monotonic','wall_unix':wall,'state':compact(state),
            'fixture_latest':fixture_states[-1]}
        report['samples'].append(row); flush(); return state
    def identity():
        for role in ('owner','fixture'):
            observed = process_identity(manifest[role]['pid'], pathlib.Path(report['identities'][role]['binary']))
            require(observed == report['identities'][role], 'A supplied process identity changed')
    def trace(target, label):
        value = client.call('output_diagnostics', target=target)
        save(out/(label+'-packets-'+target+'.json'), value)
        return value['packet_trace']
    try:
        binaries = {role:executable(manifest[role]['bundle'], 'local.motive.studio' if role=='owner' else 'local.motive.collectionfixture') for role in ('owner','fixture')}
        report['identities'] = {role:process_identity(manifest[role]['pid'], binary) for role,binary in binaries.items()}
        build = load(manifest['fixture']['build_manifest'])
        require(digest(binaries['fixture']) == build['binary_sha256'], 'Fixture differs from signed build manifest')
        ready, fixture_states = validate_fixture(lines(manifest['fixture']['log']), manifest)
        require(isinstance(fixture_states[-1].get('cg_own_window_metadata'), dict), 'Fixture must report its exact own window before any mutation')
        report['fixture_ready'] = ready
        report['hashes'] = {'owner':digest(binaries['owner']),'fixture':build['binary_sha256'],
            'fixture_source':build['source_sha256'],'sck_module':digest(pathlib.Path(manifest['owner']['bundle'])/'Contents/PlugIns/mac-capture.plugin/Contents/MacOS/mac-capture'),
            'loopback_receiver':digest(manifest['receiver_ffmpeg']), 'harness':digest(__file__),
            'counter_helper':digest(ROOT/'scripts/h14_collection_helpers.py')}
        report['clock_anchors'] = [clock_anchor()]
        client = Client(manifest['owner']['bundle'], manifest['owner']['pid'], out)
        initial = client.state(); default_owner(initial); report['initial'] = compact(initial)
        config = initial['output_configuration']; report['original_configuration'] = {k:config[k] for k in ('recording_profile','streaming_profile','endpoint')}
        profile_store = client.call('output_profiles')['store']['profiles']
        require(not any(p['id']==profile_id for p in profile_store), 'Trial profile already exists')
        changed = True
        client.call('configure_video', video={'version':1,'resolution':'full_hd1080','fps':30,'coordinate_space':'design960'})
        client.call('set_overlay', visible=False)
        prior_audio_ids = {item['id'] for item in client.state()['audio_mixer']['store']['inputs']}
        require(not prior_audio_ids, 'Mixer changed before own tone admission')
        tone_attempted = True
        response = client.call('add_audio_input', name=tone_name, source={'kind':'tone'})
        inputs = response['state']['audio_mixer']['store']['inputs']
        tone = unique_owned_tone(inputs, tone_name, prior_audio_ids)
        require(len(inputs) == 1, 'Concurrent unrelated mixer input; do not start outputs')
        client.call('set_audio_gain',input_id=tone,gain_db=-12)
        profile = {'id':profile_id,'encoder':'videotoolbox','bitrate_kbps':4000,'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':False}
        client.call('upsert_output_profile',profile=profile); profiles_created=True; report['profile']=profile
        for target in ('recording','streaming'):client.call('select_output_profile',target=target,profile_id=profile_id)
        with socket.socket() as listener: listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
        client.call('configure_stream', endpoint={'transport':'rtmp','port':port})
        print(json.dumps({'event':'awaiting_fixture_front_marker','trial_id':manifest['trial_id'],'output':str(out)}),flush=True)
        deadline=time.monotonic()+30
        while not lines(manifest['markers']):
            require(time.monotonic()<deadline,'Root must record initial focus marker');time.sleep(.25)
        markers=validate_markers(lines(manifest['markers']),manifest)
        require(len(markers)==1 and 0<=time.monotonic()-markers[0]['host_monotonic']<=5,'Fresh first marker required')
        start=markers[0]['host_monotonic'];end=start+manifest['seconds'];report['trial_start_host_s']=start;report['trial_end_planned_host_s']=end
        report['phase_schedule_host_s']={phase:start+i*manifest['seconds']/3 for i,phase in enumerate(PHASES)}
        print(json.dumps({'event':'phase_schedule','schedule':report['phase_schedule_host_s']}),flush=True)
        identity();client.call('select_source',window_id=manifest['fixture']['window_id']);selection_bracket=client.last_bracket[:]
        state=sample('source_selected');main=next(s for s in state['sources'] if s['id']=='main');created=main.get('capture_diagnostics',{}).get('created_ns')
        require(created and main['kind']=='window','Exact owned SCK source diagnostic required')
        report['capture_clock_anchor']={'native_clock':'libobs.os_gettime_ns','created_ns':created,
            'host_clock':'python.time.monotonic','creation_rpc_bracket_s':selection_bracket,
            'offset_interval_s':[x-created/1e9 for x in selection_bracket],
            'basis':'motive_sck_diagnostics_init is synchronous inside the one SelectSource RPC'}
        ready_deadline=min(start+5,end);ready=False
        while time.monotonic()<ready_deadline:
            state=sample('first_buffer_preflight');flight={t:client.call('preflight_output',target=t,allow_error=True) for t in ('recording','streaming')}
            report['last_preflights']=flight
            if all(x.get('ok') and x['preflight']['ready'] for x in flight.values()):ready=True;break
            time.sleep(.5)
        if not ready:report['capture_failure']='CAPTURE_NOT_READY_OR_PREFLIGHT_REJECTED'
        else:
            receiver=Receiver(str(pathlib.Path(manifest['receiver_ffmpeg']).resolve(strict=True)),out,port)
            for target in ('recording','streaming'):
                identity();attempted[target]=state['outputs'][target]['attempt_id']
                response=client.call('start_output',target=target);slot=response['state']['outputs'][target]
                owned[target]=slot['attempt_id'];report['media'].append({'target':target,'attempt_id':slot['attempt_id'],
                    'path':str(receiver.path) if target=='streaming' else slot['path']})
                trace_end=time.monotonic()+2
                while True:
                    first=trace(target,'initial')
                    if {p['media_type'] for p in first['packets']}=={'audio','video'} or time.monotonic()>=trace_end:break
                    time.sleep(.05)
        report['status']='PARTIAL' if ready else 'FAIL'
        while time.monotonic()<end:
            state=sample('focus_observation')
            if any(state['outputs'][t]['attempt_id']!=attempt or state['outputs'][t]['phase']!='active' for t,attempt in owned.items()):
                report['status']='FAIL';report['output_continuity_failure']=True
            if len(report['samples'])%10==0:identity();report['clock_anchors'].append(clock_anchor())
            time.sleep(.5)
        validate_markers(report['markers'],manifest,complete=True)
        report['trial_end_host_s']=time.monotonic()
    except BaseException as error:
        report['status']='FAIL';report['error']=repr(error);report['traceback']=traceback.format_exc()
    finally:
        if client and initial:
            try:
                # The fixture may have died. That failure must not prevent
                # cleanup of our own output workers in the surviving owner.
                expected=report['identities']['owner']
                require(process_identity(expected['pid'],pathlib.Path(expected['binary']))==expected,
                        'Owner identity changed; cleanup withheld')
                state=client.state()
                # Reconcile only targets for which this runner sent StartOutput;
                # a lost reply never authorizes stopping an older/foreign attempt.
                for target,old_attempt in attempted.items():
                    slot=state['outputs'][target]
                    if target not in owned and slot['attempt_id']!=old_attempt and (slot.get('profile') or {}).get('id')==profile_id:owned[target]=slot['attempt_id']
                for target,attempt in owned.items():
                    command=owned_stop_command(state['outputs'][target],attempt)
                    if command:client.call(command,target=target)
                deadline=time.monotonic()+20
                while any(client.state()['outputs'][t]['native_busy'] for t in owned):
                    require(time.monotonic()<deadline,'Own outputs did not reach quiescence; owner left running');time.sleep(.25)
                for target in owned:trace(target,'final')
                report['terminal']=compact(client.state())
                if changed:
                    state=client.state();require(all(not s['native_busy'] for s in state['outputs'].values()),'Unrelated output busy; resource cleanup withheld')
                    require(state['window_id'] in (None,manifest['fixture']['window_id']),'Window selection changed; leave it for owner')
                    client.call('select_source',window_id=None)
                    if tone_attempted:
                        inputs = client.state()['audio_mixer']['store']['inputs']
                        if tone is None and any(i.get('name') == tone_name for i in inputs):
                            tone = unique_owned_tone(inputs, tone_name, prior_audio_ids)
                        matching = [i for i in inputs if i['id'] == tone]
                        if matching:
                            require(len(matching) == 1 and matching[0]['name'] == tone_name
                                    and matching[0]['source'] == {'kind':'tone'}, 'Tone identity changed; cleanup withheld')
                            client.call('remove_audio_input',input_id=tone)
                    for target in ('recording','streaming'):
                        current=client.state()['output_configuration'][target+'_profile']
                        original=report['original_configuration'][target+'_profile']
                        require(current in (profile_id,original),'Profile selection changed; cleanup withheld')
                        if current==profile_id:client.call('select_output_profile',target=target,profile_id=original)
                    if profiles_created:client.call('remove_output_profile',id=profile_id)
                    client.call('set_overlay',visible=initial['project']['overlay'])
                    client.call('configure_video',video=initial['project'].get('video') or {'version':1,'resolution':'legacy540','fps':30,'coordinate_space':'design960'})
                    if report['original_configuration']['endpoint']:client.call('configure_stream',endpoint=report['original_configuration']['endpoint'])
                    else:report['cleanup_residue']='Owned loopback endpoint remains selected; no unset API. No stores saved.'
                report['final']=compact(client.state())
            except BaseException as error:report['cleanup_error']=repr(error);report['status']='FAIL'
        if receiver:
            try:
                try:report['receiver_exit']=receiver.process.wait(timeout=5)
                except subprocess.TimeoutExpired:report['receiver_exit']=receiver.close();report['receiver_forced_after_wait']=True
            except BaseException as error:report['receiver_cleanup_error']=repr(error);report['status']='FAIL'
        if start is not None:
            report['elapsed_host_s']=time.monotonic()-start
            report['focus_condition']=focus_conditions([row['event'] for row in lines(out/'fixture-events.jsonl')],
                report.get('clock_anchors',[]),report.get('markers',[]),report.get('trial_end_host_s'))
        flush()
    print(json.dumps({'output':str(out),'status':report['status'],'error':report.get('error')}))
    return int(report['status']=='FAIL')


def mark(args):
    lock();manifest=validate_manifest(load(args.manifest,65536));raw_path=pathlib.Path(manifest['markers']).absolute()
    require(not raw_path.is_symlink(),'Marker may not be a symlink')
    path=raw_path.parent.resolve()/raw_path.name
    require(path.is_relative_to((ROOT/'var/evidence').resolve()) and path.parent.is_dir(),'Marker must be in existing worktree evidence directory')
    prior=validate_markers(lines(path),manifest)
    require(len(prior)<3 and args.phase==PHASES[len(prior)],'Unexpected next focus marker')
    require(len(args.note)<=400,'Bounded focus note required')
    event={'version':1,'trial_id':manifest['trial_id'],'phase':args.phase,'owner_pid':manifest['owner']['pid'],
        'fixture_pid':manifest['fixture']['pid'],'window_id':manifest['fixture']['window_id'],
        'clock':'python.time.monotonic','host_monotonic':time.monotonic(),'wall_unix':time.time(),
        'observation':'root_observed_focus_after_cua','note':args.note,'proves_published_pixels':False}
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as destination:destination.write(json.dumps(event)+'\n')
    print(json.dumps(event))
    return 0


def analyze(args):
    lock();source=pathlib.Path(args.report).resolve();report=load(source);out=pathlib.Path(args.output).resolve()
    require(out.is_relative_to((ROOT/'var/evidence').resolve()),'Analysis must use a new evidence directory')
    out.mkdir(parents=True,exist_ok=False)
    result={'version':1,'status':'INCONCLUSIVE','trial_report_sha256':digest(source),'media':[],
        'collection_status':report['status'],'limits':['Only one frame in six is decoded for counter content (5 Hz at 30 fps).',
        'Root focus observations are not pixel evidence. Two-second boundary guard plus measured clock uncertainty excludes ambiguous phase transitions.',
        'Geometry must match SCALE_INNER and the owned fixture window bounds; unsupported geometry is INCONCLUSIVE, never a guessed crop.',
        'First-packet alignment is conditioned on complete trace beginning and matching size/keyframe; this is not cryptographic identity or proof of full delivery.']}
    result['focus_condition']=focus_conditions([row['event'] for row in lines(source.parent/'fixture-events.jsonl')],
        report.get('clock_anchors',[]),report.get('markers',[]),report.get('trial_end_host_s'))
    def command(binary,arguments):
        value=subprocess.run([str(pathlib.Path(binary).resolve(strict=True)),*arguments],capture_output=True,timeout=180)
        require(value.returncode==0 and not value.stderr,'Media decode/probe failed: '+value.stderr.decode(errors='replace')[:500])
        return value.stdout
    for medium in report['media']:
        row={'target':medium['target'],'path':medium['path'],'status':'INCONCLUSIVE'};result['media'].append(row)
        try:
            path=pathlib.Path(medium['path']);require(path.is_file(),'Output media absent')
            row['sha256']=digest(path);row['bytes']=path.stat().st_size
            probe=json.loads(command(args.ffprobe,['-v','error','-show_streams','-show_format','-of','json',str(path)]))
            video=next(x for x in probe['streams'] if x['codec_type']=='video')
            require((video['width'],video['height'],video['avg_frame_rate'])==(1920,1080,'30/1'),'Unexpected video format')
            validate_media_duration(float(probe['format']['duration']),report['manifest'])
            frames=json.loads(command(args.ffprobe,['-v','error','-threads','2','-select_streams','v:0','-show_frames',
                '-show_entries','frame=best_effort_timestamp_time,pict_type','-of','json',str(path)]))['frames']
            packets=json.loads(command(args.ffprobe,['-v','error','-show_packets','-show_entries',
                'packet=codec_type,pts_time,dts_time,duration_time,size,flags','-of','json',str(path)]))['packets']
            selected=frames[::6];pts=[float(x['best_effort_timestamp_time']) for x in frames]
            raw=command(args.ffmpeg,['-nostdin','-v','error','-threads','2','-i',str(path),'-map','0:v:0','-an',
                '-vf',"select='not(mod(n,6))',scale=480:270:flags=area,format=gray",'-fps_mode','passthrough','-f','rawvideo','-'])
            frame_bytes=480*270;require(len(raw)==len(selected)*frame_bytes,'Decoded frame/timestamp correspondence mismatch')
            sizes={(s['width'],s['height']) for sample in report['samples'] for s in sample['state']['sources']
                   if s['id']=='main' and s['kind']=='window' and s['width']>0 and s['height']>0}
            require(len(sizes)==1,'Changing/unknown capture dimensions prevent fixed geometry verification')
            fixture_bounds=[sample['fixture_latest']['cg_own_window_metadata']['bounds'] for sample in report['samples']
                            if isinstance(sample['fixture_latest'].get('cg_own_window_metadata'),dict)]
            require(fixture_bounds,'Owned window bounds unavailable');bounds=fixture_bounds[0]
            require(all(b['Width']==bounds['Width'] and b['Height']==bounds['Height'] for b in fixture_bounds),'Fixture size changed')
            boxes=counter_patches(next(iter(sizes)),(bounds['Width'],bounds['Height']))
            decoded=[{'pts_s':float(frame['best_effort_timestamp_time']),
                'counter':decode_counter(raw[i*frame_bytes:(i+1)*frame_bytes],480,boxes)} for i,frame in enumerate(selected)]
            del raw
            save(out/(medium['target']+'-counter.json'),{'boxes':boxes,'rows':decoded})
            row['counter']=counter_summary(decoded);row['decoded_frames']=len(frames)
            if row['counter']['status']=='FAIL':row['status']='FAIL'
            row['video_max_pts_gap_s']=max(b-a for a,b in zip(pts,pts[1:]));row['video_pts_strictly_increasing']=all(b>a for a,b in zip(pts,pts[1:]))
            if row['video_max_pts_gap_s']>.05 or not row['video_pts_strictly_increasing']:row['status']='FAIL'
            first=load(source.parent/('initial-packets-'+medium['target']+'.json'))['packet_trace']
            final=load(source.parent/('final-packets-'+medium['target']+'.json'))['packet_trace']
            from verify_h14_output_integrity import correlate_tail
            row['tail_accounting']=correlate_tail(first,final,packets)
            require(not first['snapshot_busy'] and first['summary']['trace_overwritten_records']==0
                    and first['summary']['trace_missed_records']==0,'Beginning of trace unavailable for clock alignment')
            native=next(p for p in first['packets'] if p['media_type']=='video')
            require(native['pts']==native['dts'],'Reordered PTS unsupported for focus alignment')
            actual=next(p for p in packets if p['codec_type']=='video')
            require(int(actual['size'])==native['size'] and ('K' in actual['flags'])==native['keyframe'],
                    'First native/container video packet identity cannot be established')
            anchor=report['capture_clock_anchor'];lo,hi=anchor['offset_interval_s'];uncertainty=hi-lo
            require(0<=uncertainty<=1,'Creation clock bracket too wide for phase alignment')
            origin=(lo+hi)/2+native['sys_dts_usec']/1e6-float(actual['pts_time'])
            markers=validate_markers(report['markers'],report['manifest'],complete=True)
            boundaries=[m['host_monotonic'] for m in markers]+[report['trial_end_host_s']]
            row['focus_clock_alignment']={'method':'Synchronous SCK creation RPC brackets OBS clock; complete first packet relates container PTS to native sys_dts.',
                'host_origin_s':origin,'uncertainty_s':uncertainty,'phase_boundary_guard_s':2+uncertainty}
            row['phases']={}
            for i,phase in enumerate(PHASES):
                inside=[d for d in decoded if boundaries[i]+2+uncertainty <= origin+d['pts_s'] <= boundaries[i+1]-2-uncertainty]
                row['phases'][phase]=counter_summary(inside)
            row['status']='FAIL' if row['counter']['status']=='FAIL' or any(x['status']=='FAIL' for x in row['phases'].values()) or row['video_max_pts_gap_s']>.05 or not row['video_pts_strictly_increasing'] else \
                'PASS' if all(x['status']=='PASS' for x in row['phases'].values()) and row['counter']['status']=='PASS' else 'INCONCLUSIVE'
            row['raw_output_frame_delta']=final['summary']['observed_video_packets']-len(frames)
        except BaseException as error:
            row['error']=repr(error)
            if str(error).startswith('Media decode/probe failed:'):row['status']='FAIL'
    result['pixel_freshness']='FAIL' if any(m['status']=='FAIL' for m in result['media']) else \
        'PASS' if len(result['media'])==2 and all(m['status']=='PASS' for m in result['media']) else 'INCONCLUSIVE'
    result['status']='FAIL' if report['status']=='FAIL' or result['pixel_freshness']=='FAIL' else \
        'PASS' if result['pixel_freshness']=='PASS' and result['focus_condition']['status']=='VERIFIED' else 'INCONCLUSIVE'
    result['full_output_delivery']='NOT_INFERRED_FROM_COUNTER_FRESHNESS'
    save(out/'analysis.json',result);print(json.dumps({'output':str(out),'status':result['status']}))
    return int(result['status']=='FAIL')


def plan():
    return {'version':1,'status':'NOT_RUN','sequence':['default','join-all','default'],
        'commands':['run --lock-held --manifest TRIAL.json --output NEW_EVIDENCE_DIRECTORY',
                    'mark --lock-held --manifest TRIAL.json --phase fixture_front --note "Root CUA focus observation"',
                    'mark --lock-held --manifest TRIAL.json --phase studio_front --note "Root CUA focus observation"',
                    'mark --lock-held --manifest TRIAL.json --phase fixture_return --note "Root CUA focus observation"',
                    'analyze --lock-held --report REPORT.json --ffmpeg /absolute/ffmpeg --ffprobe /absolute/ffprobe --output NEW_ANALYSIS_DIRECTORY'],
        'manifest':{'version':1,'trial_id':'a1','arm':'default','seconds':180,
            'owner':{'bundle':'/absolute/Motive.app','pid':111},
            'fixture':{'bundle':str(ROOT/'target/H14CollectionFixture.app'),'pid':222,'window_id':333,
                'log':str(ROOT/'var/evidence/fixture-a1.jsonl'),'build_manifest':str(ROOT/'target/h14-collection-build.json')},
            'markers':str(ROOT/'var/evidence/collection-a1-markers.jsonl'),'receiver_ffmpeg':'/opt/homebrew/bin/ffmpeg'},
        'workflow':'Root launches fresh owner/fixture, records exact PID/window ID, starts run, then marks observed fixture focus when awaiting_fixture_front_marker appears. Recommended duration is 180s, with three 60s phases and focus changes around the printed +60/+120s deadlines. Other accepted durations divide equally into three phases. If focus cannot be observed (e.g. only a thumbnail and fixture app_active false), do not create a front marker; retain the timeout/blocker. No GUI or launch automation.',
        'observation_seconds':[45,180],'recommended_seconds':180,'recommended_phase_seconds':60,
        'trial_id_policy':'1–33 lowercase ASCII letters/digits/hyphens/underscores, including at least one letter/digit; h14-collection- plus trial_id must fit the 48-byte output profile ID.',
        'bounded_extra_waits':'30s initial marker, 5s preflight, up to 20s quiescence; errors retained.',
        'analysis':'Separate serialized CPU window only. Focus conditions are corroborated per phase from fixture metadata through measured clocks, separately from decoded pixel freshness. Missing focus evidence prevents a trial PASS. A→B→A requires fresh fixture PID/window ID each time and unchanged bundle/module/profile/size. Do not infer a general Stage Manager cause.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='mode',required=True)
    commands.add_parser('plan')
    run=commands.add_parser('run');run.add_argument('--lock-held',action='store_true',required=True);run.add_argument('--manifest',required=True);run.add_argument('--output',required=True)
    marker=commands.add_parser('mark');marker.add_argument('--lock-held',action='store_true',required=True);marker.add_argument('--manifest',required=True);marker.add_argument('--phase',choices=PHASES,required=True);marker.add_argument('--note',default='Root observed focus through CUA')
    decoder=commands.add_parser('analyze');decoder.add_argument('--lock-held',action='store_true',required=True);decoder.add_argument('--report',required=True);decoder.add_argument('--output',required=True);decoder.add_argument('--ffmpeg',required=True);decoder.add_argument('--ffprobe',required=True)
    args=parser.parse_args()
    if args.mode=='plan':print(json.dumps(plan(),indent=2));return 0
    return {'run':run_trial,'mark':mark,'analyze':analyze}[args.mode](args)


if __name__=='__main__':raise SystemExit(main())
