#!/usr/bin/env python3
"""Bounded official B-frame experiment; preserve defaults, report every PTS gap."""
from h7_support import *
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
c=Client();report={'ok':False,'trials':[],'app_sha256':hashlib.sha256((VERIFY.app_executable).read_bytes()).hexdigest()}
try:
    project=setup_owned(c)
    for encoder in ('videotoolbox','x264'):
        for repeat in range(2):
            for reorder in ([True,False] if repeat==0 else [False,True]):
                p=profile('stop-probe',encoder,reorder=reorder)
                c.call('upsert_output_profile',profile=p);c.call('select_output_profile',target='recording',profile_id=p['id'])
                started=c.call('start_recording')['state'];metrics=measure(c,6.1+repeat*.23,'recording')
                stopped=c.stop();assert stopped['end']['output']=='idle' and stopped['end']['output_code']==0
                assert c.state()['project']==project
                m=media(started['output_path'],5,pixels=True)
                assert m['max_interior_gap']<.05,m
                if not reorder:assert m['b_frames']==0,m
                report['trials'].append({'profile':p,'started':started,'stop':stopped,'metrics':metrics,'media':m})
                print(encoder,'reorder',reorder,'gaps',m['gaps_over_50ms'],'B-frames',m['b_frames'],'stop',round(stopped['elapsed'],3),flush=True)
    report['ok']=True
except BaseException as e:report['error']=repr(e);raise
finally:
    try:
        c.stop();c.call('select_output_profile',target='recording',profile_id='standard');c.call('remove_output_profile',id='stop-probe');c.call('select_audio',id='none')
    except Exception as e:report['cleanup_error']=repr(e)
    report['operations']=c.ops;c.close();(EVIDENCE/'h7-vt-stop.json').write_text(json.dumps(report,indent=2))
