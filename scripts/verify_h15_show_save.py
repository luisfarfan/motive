#!/usr/bin/env python3
"""Verify a prior real GPUI save, stale rejection, restore disarming and explicit arm.

Requires a reviewed, idle MATCHDAY production saved through GPUI by the caller.
Does not install packs or claim UI interaction. Caller preserves original stores.
"""
import copy
import hashlib
import json
import argparse
import traceback
from pathlib import Path
from verify_h13_outputs import Client
from verification_paths import verification_paths
from verify_h14_collection import ROOT, lock

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
lock()
args.output.mkdir(parents=True, exist_ok=False)
client = Client(args.output)
report = {'ok':False,'ui_click':'EXTERNAL_EVIDENCE_REQUIRED','checks':{}}
path = verification_paths(ROOT).data_root/'show-control/configuration.json'
try:
    initial = client.state()
    sc = client.call('show_control_status')['show_control']
    receipt = sc['last_save']
    payload = path.read_bytes()
    assert receipt['write']['durable'] and receipt['write']['document_sha256'] == hashlib.sha256(payload).hexdigest()
    assert receipt['pid'] == initial['pid'] and receipt['session'] == sc['session']
    report['checks']['prior_ui_receipt_matches_disk'] = receipt
    saved = json.loads(payload)
    guard = {'pid':initial['pid'],'revision':initial['revision'],'session':sc['session']}
    # A legitimate independent CLI mutation invalidates the old review.
    scene_id = initial['project']['graph']['active_scene']
    scene_name = next(s['name'] for s in initial['project']['graph']['scenes'] if s['id'] == scene_id)
    client.call('rename_scene', transport='cli', scene_id=scene_id, name='H15 concurrent review')
    rejected = client.call('save_show_control', expected=guard, expect=False)
    assert rejected['error']['code'] == 'STALE_REVISION'
    assert path.read_bytes() == payload
    report['checks']['stale_save_preserved_bytes'] = rejected['error']
    client.call('rename_scene', scene_id=scene_id, name=scene_name)
    invalid = copy.deepcopy(saved['config'])
    invalid['rules'][0]['actions'] = [{'type':'show_overlay','source_id':'h15-missing-source'}]
    revision = client.state()['revision']
    rejected = client.call('configure_show_control', transport='cli', config=invalid, deck=saved['deck'], expect=False)
    assert rejected['error']['code'] == 'SHOW_CONTROL_BINDING_MISSING'
    assert client.state()['revision'] == revision and path.read_bytes() == payload
    report['checks']['broken_ids_rejected_before_mutation'] = rejected['error']
    restored = client.call('load_show_control')['show_control']
    assert restored['configured'] and not restored['armed'] and not restored['jobs']
    assert restored['session'] != sc['session'] and restored['bindings_current']
    report['checks']['restore_disarmed_new_session'] = restored
    rejected = client.call('save_show_control', expected=guard, expect=False)
    assert rejected['error']['code'] == 'CORE_SESSION_CHANGED' and path.read_bytes() == payload
    state = client.state()
    armed = client.call('arm_show_control', pid=state['pid'], revision=state['revision'])['show_control']
    assert armed['armed'] and not armed['jobs']
    state = client.state()
    fresh = {'pid':state['pid'],'revision':state['revision'],'session':armed['session']}
    saved_again = client.call('save_show_control', expected=fresh)
    assert saved_again['result']['saved_configuration']['write']['document_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    report['checks']['explicit_arm_and_save'] = saved_again['result']
    report['ok'] = True
except Exception as exc:
    report['failure'] = str(exc)
    report['traceback'] = traceback.format_exc()
    raise
finally:
    client.close()
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
