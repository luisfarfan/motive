#!/usr/bin/env python3
"""Bounded, explicitly authorized private RTMPS trial; external start is native UI only.

Run under h21_run_owned_session and the canonical lease. Uses only the built-in
moving pattern and generated tone; no device, screen, browser or asset source.
Never extracts a key. Sent bytes are not proof of remote delivery.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from h7_support import Client
from verify_h14_collection import default_owner, digest, lock, require, save


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,required=True)
    p.add_argument('--authorization',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); held=lock(); auth=json.loads(a.authorization.read_text())
    require(auth['authorized'] is True and auth['max_live_seconds']==180,'Specific private test authorization required')
    data=Path.home()/'Library/Application Support/local.motive.studio'
    store=data/'streaming/destinations.json'
    require(digest(store)==auth['destination_store_sha256'],'Approved destination store changed; review exact destination before use')
    entries=json.loads(store.read_text())['destinations']; require(len(entries)==1,'Unique authorized destination required')
    destination=entries[0]['destination']; ident=destination['id']
    require(ident==auth['destination_id'] and destination['host']==auth['host'] and destination['port']==auth['port'],'Authorization target mismatch')
    app=a.app.resolve(strict=True); out=a.output.absolute();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'runner-source.py');shutil.copy2(a.authorization,out/'authorization.json')
    abort=Path(os.environ['MOTIVE_TEST_ABORT_FILE'])
    report={'status':'FAIL','runtime_status':'NOT_COMPLETED','lock':held,
            'owner_sha256':digest(app/'Contents/MacOS/motive'),'authorization_sha256':digest(a.authorization),
            'destination_id':ident,'host':auth['host'],'port':auth['port'],
            'remote_delivery':'AWAITING_OPERATOR_OBSERVATION','privacy':'Private destination confirmed by operator; generated pattern/tone only',
            'stage':'PREPARING','verification_label':'H21 C7 / YT-'+uuid.uuid4().hex[:6].upper(),
            'events':[],'samples':[],'media':[],'cleanup_errors':[],
            'limits':['The application cannot inspect YouTube visibility settings; operator explicitly confirmed private.',
                      'Native sent bytes and a local MKV do not establish remote receipt or remote A/V timing.']}
    client=None; attempts={}
    def checkpoint():save(out/'report.json',report)
    def event(name,**values):
        report['events'].append({'name':name,'monotonic_s':time.monotonic(),**values});checkpoint()
    def sample(label):
        before=time.monotonic();state=client.state();after=time.monotonic()
        require(state['pid']==report['owner_pid'],'Owner identity changed')
        report['samples'].append({'label':label,'host_bracket_s':[before,after],'state':state})
        report['last_state']=state;checkpoint();return state
    def wait(predicate,label,seconds):
        deadline=time.monotonic()+seconds
        while True:
            state=sample(label)
            if predicate(state):return state
            require(not abort.exists(),'Supervisor requested stop')
            require(time.monotonic()<deadline,label+' timeout');time.sleep(1)
    def require_generated_only(state):
        require(all(s['kind'] in ('pattern','overlay') for s in state['sources']),'Unexpected visual source')
        inputs=state['audio_mixer']['store']['inputs']
        require(len(inputs)==1 and inputs[0]['source']['kind']=='tone','Generated tone must be the only audio input')
    try:
        client=Client();state=client.state();default_owner(state);report['owner_pid']=state['pid']
        client.call('configure_video',video={'version':1,'resolution':'full_hd1080','fps':30,'coordinate_space':'design960'})
        client.call('set_overlay',visible=True)
        scene=client.state()['project']['graph']['active_scene']
        response=client.call('create_overlay',scene_id=scene,name='Private trial identifier',
            definition={'kind':'text','text':report['verification_label'],'font':'Helvetica',
                        'size':40,'color':0xffffff,'opacity':1.0,'align':'left',
                        'width':820,'height':80,'background':None,
                        'background_opacity':0.0,'outline':False})
        label_source=response['result']['source_id']
        graph_scene=next(s for s in response['state']['project']['graph']['scenes'] if s['id']==scene)
        layer=next(l for l in graph_scene['layers'] if l['source_id']==label_source)
        client.call('set_transform',scene_id=scene,layer_id=layer['id'],variant='horizontal',
                    transform={'x':40,'y':400,'width':820,'height':80,'visible':True,'order':10})
        report['label_source_id']=label_source
        state=client.call('add_audio_input',name='H21 private generated tone',source={'kind':'tone'})['state']
        tone=next(i['id'] for i in state['audio_mixer']['store']['inputs'] if i['name']=='H21 private generated tone')
        client.call('set_audio_gain',input_id=tone,gain_db=-18)
        wait(lambda s:not s['audio_mixer']['issues'] and all(i['phase']=='ready' for i in s['audio_mixer']['runtime']['inputs']),'audio_ready',15)
        profile={'id':'h21-private-youtube','encoder':'videotoolbox','bitrate_kbps':6000,
                 'rate_control':'cbr','keyframe_seconds':2,'frame_reordering':False}
        client.call('upsert_output_profile',profile=profile)
        for target in ('recording','streaming'):client.call('select_output_profile',target=target,profile_id=profile['id'])
        client.call('select_approved_destination',id=ident)
        preflight=client.call('preflight_destination',id=ident);report['destination_preflight']=preflight
        state=client.state();require_generated_only(state)
        client.call('preflight_output',target='recording')
        slot=client.call('start_output',target='recording')['state']['outputs']['recording']
        attempts['recording']=slot['attempt_id'];report['media'].append({'target':'recording','path':slot['path']})
        wait(lambda s:s['outputs']['recording']['phase']=='active','recording_active',15)
        report['stage']='AWAITING_NATIVE_UI_START';event('recording_active_ready_for_local_rtmps_confirmation')
        # No CLI/MCP route can grant local external-start authority. The operator
        # or authorized native UI controller must review and confirm the dialog.
        state=wait(lambda s:s['outputs']['streaming']['phase']=='active','await_native_ui_stream_start',180)
        require_generated_only(state)
        attempts['streaming']=state['outputs']['streaming']['attempt_id']
        require(all(state['outputs'][t]['encoding']['selected_hardware'] for t in attempts),'Hardware encoder required')
        report['initial_state']=state
        report['initial_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
        start=time.monotonic();report['started_monotonic']=start;report['stage']='PRIVATE_STREAM_ACTIVE';event('private_stream_active')
        while time.monotonic()-start<180:
            state=sample('private_stream_active');require_generated_only(state)
            require(not abort.exists(),'Supervisor requested stop')
            require(all(state['outputs'][t]['phase']=='active' and state['outputs'][t]['attempt_id']==attempts[t] for t in attempts),'Output interrupted')
            require(not state['audio_mixer']['issues'],'Audio issue')
            report['last_elapsed_s']=time.monotonic()-start
            if len(report['samples'])%5==0:report['last_memory']=client.call('memory_diagnostics')
            time.sleep(1)
        report['observed_seconds']=time.monotonic()-start
        client.call('stop_output_target',target='streaming')
        state=wait(lambda s:not s['outputs']['streaming']['native_busy'],'stream_stopped',30)
        require(state['outputs']['recording']['phase']=='active','Recording did not continue independently')
        event('stream_stopped_recording_continues')
        end=time.monotonic()+5
        while time.monotonic()<end:
            require(sample('recording_only')['outputs']['recording']['phase']=='active','Recording interrupted');time.sleep(1)
        client.call('stop_output_target',target='recording')
        wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'outputs_quiescent',30)
        report['final_traces']={t:client.call('output_diagnostics',target=t) for t in attempts}
        report.update(runtime_status='PASS',status='PARTIAL',stage='CLOSED_OUTPUTS')
    except Exception as error:
        report['error']=repr(error);report['stage']='FAILED_OR_BLOCKED'
    finally:
        if client:
            try:
                state=client.state()
                require(state['pid']==report['owner_pid'],'Owner changed during cleanup')
                # A UI attempt can be connecting/failed before its active ID was
                # captured. It still belongs to this fresh, dedicated owner.
                for target in ('streaming','recording'):
                    if state['outputs'][target]['native_busy']:client.call('stop_output_target',target=target)
                wait(lambda s:all(not o['native_busy'] for o in s['outputs'].values()),'cleanup_outputs_quiescent',30)
            except Exception as error:report['cleanup_errors'].append(repr(error))
            client.close()
        report['destination_store_unchanged']=digest(store)==auth['destination_store_sha256']
        if not report['destination_store_unchanged']:
            report['cleanup_errors'].append('Destination store bytes changed during a trial that did not authorize destination edits')
        checkpoint()
    print(json.dumps({k:report.get(k) for k in ('status','runtime_status','stage','error','cleanup_errors')}))
    return int(report['runtime_status']!='PASS' or bool(report['cleanup_errors']))


if __name__=='__main__':raise SystemExit(main())
