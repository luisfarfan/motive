#!/usr/bin/env python3
"""One minute of prepared camera + microphone, without generated sound/scene cuts.

Use h21_run_owned_session under the physical lock. Physical acceptance requires
independent review of decoded contacts; runtime counters alone never certify A/V.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import time

from h7_support import Client
from h21_trace_origin import collect_origin
from verify_h14_collection import Receiver, default_owner, digest, lock, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--camera-id', required=True)
    parser.add_argument('--microphone-id', required=True)
    parser.add_argument('--controlled-devices-prepared', action='store_true', required=True)
    args = parser.parse_args()
    held = lock(); app = args.app.resolve(strict=True)
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=False)
    r = {'status':'FAIL', 'lock':held, 'owner_sha256':digest(app/'Contents/MacOS/motive'),
         'runner_sha256':digest(Path(__file__)), 'media':[], 'cleanup_errors':[],
         'physical_av':'NOT_MEASURED', 'requested_seconds':60,
         'scope':'Prepared physical camera/microphone, no generated audio, no hourly drift claim.'}
    client = receiver = None; attempts = {}
    def wait(predicate, label):
        deadline = time.monotonic()+20
        while True:
            state = client.state()
            if predicate(state): return state
            require(time.monotonic()<deadline, label+' timeout'); time.sleep(.1)
    try:
        client = Client(); default_owner(client.state()); r['owner_pid'] = client.state()['pid']
        devices = client.call('devices')['devices']
        require(devices['camera_permission'] and devices['microphone_permission'], 'Normal permissions required')
        require(any(x['id']==args.camera_id for x in devices['cameras']), 'Prepared camera absent')
        require(any(x['id']==args.microphone_id for x in devices['audio']), 'Prepared microphone absent')
        client.call('configure_video', video={'version':1,'resolution':'full_hd1080','fps':30,'coordinate_space':'design960'})
        client.call('set_overlay', visible=False)
        state = client.call('create_scene', name='C8 physical reference')['state']
        scene = state['project']['graph']['active_scene']
        client.call('add_source', scene_id=scene, name='Prepared camera', source={'kind':'camera','device_id':args.camera_id})
        state = client.call('add_audio_input', name='Prepared microphone', source={'kind':'microphone','device_id':args.microphone_id})['state']
        mic = next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']=='Prepared microphone')
        client.call('set_audio_gain', input_id=mic, gain_db=-12)
        wait(lambda s:all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']) and any(x['kind']=='camera' and x['frames']>10 for x in s['sources']), 'Devices ready')
        profile={'id':'c8-physical','encoder':'videotoolbox','bitrate_kbps':6000,'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':False}
        client.call('upsert_output_profile', profile=profile)
        for target in ('recording','streaming'): client.call('select_output_profile',target=target,profile_id=profile['id'])
        with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        client.call('configure_stream',endpoint={'transport':'rtmp','port':port})
        receiver=Receiver(str(app/'Contents/MacOS/ffmpeg'),out,port)
        r['initial_traces']={}
        for target in ('recording','streaming'):
            state=client.call('start_output',target=target)['state'];slot=state['outputs'][target];attempts[target]=slot['attempt_id']
            r['media'].append({'target':target,'path':str(receiver.path) if target=='streaming' else slot['path']})
            wait(lambda s:s['outputs'][target]['phase']=='active',target+' active')
            r['initial_traces'][target]=collect_origin(client,target,attempts[target])
        start=time.monotonic();r['started_monotonic']=start;r['recording_now']=True;save(out/'report.json',r)
        with (out/'samples.jsonl').open('x') as log:
            while time.monotonic()-start<60:
                state=client.state();row={'elapsed_s':time.monotonic()-start,'state':state}
                log.write(json.dumps(row)+'\n');log.flush()
                require(not Path(os.environ['MOTIVE_TEST_ABORT_FILE']).exists(),'Supervisor abort')
                require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==a for t,a in attempts.items()),'Output interrupted')
                require(not state['audio_mixer']['issues'],'Audio quality issue')
                require(state['audio_mixer']['runtime']['mix']['clipped_blocks']==0,'Mix clipping')
                time.sleep(.2)
        r['observed_seconds']=time.monotonic()-start;r['final_state']=state;r['runtime_status']='PASS'
    except Exception as e: r['error']=repr(e)
    finally:
        if client:
            try:
                for target,attempt in reversed(list(attempts.items())):
                    state=client.state();require(state['outputs'][target]['attempt_id']==attempt,'Output ownership changed')
                    if state['outputs'][target]['native_busy']: client.call('stop_output_target',target=target)
                    wait(lambda s:not s['outputs'][target]['native_busy'],target+' quiescent')
                r['final_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
            except Exception as e:r['cleanup_errors'].append(repr(e))
            client.close()
        if receiver:r['receiver_exit']=receiver.close()
        r['recording_now']=False
        if r.get('runtime_status')=='PASS' and not r['cleanup_errors']:r['status']='PARTIAL'
        save(out/'report.json',r)
    return int(r.get('runtime_status')!='PASS' or bool(r['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
