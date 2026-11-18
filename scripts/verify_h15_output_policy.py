#!/usr/bin/env python3
"""Verify unsafe saved-profile values remain explicit and cannot start output."""
import json
import time
from h7_support import Client, EVIDENCE

client = Client()
report = {'ok': False, 'checks': []}
identifier = 'h15-unsafe-' + str(time.time_ns())
initial = client.state()
try:
    value = {'id': identifier, 'encoder': 'videotoolbox', 'bitrate_kbps':4000,
             'rate_control':'cbr','keyframe_seconds':1,'frame_reordering':True}
    client.call('upsert_output_profile', profile=value)
    client.call('select_output_profile', target='recording', profile_id=identifier)
    for operation in ('preflight_output', 'start_output'):
        response = client.call(operation, expect=False, target='recording')
        assert response['error']['code'] == 'FRAME_REORDERING_UNSUPPORTED', response
        report['checks'].append(response)
    final = client.state()
    assert final['outputs']['recording']['attempt_id'] == initial['outputs']['recording']['attempt_id']
    assert final['output_configuration']['recording_profile'] == identifier
    report['ok'] = True
finally:
    client.call('select_output_profile', target='recording', profile_id=initial['output_configuration']['recording_profile'])
    client.call('remove_output_profile', id=identifier)
    client.close()
    (EVIDENCE/'h15-output-policy.json').write_text(json.dumps(report, indent=2))
