#!/usr/bin/env python3
"""Read-only observer for a production operated through native GPUI.

Run under the shared device/bundle lock. Only MCP `status` is sent; this tool
cannot create sources, edit overlays, start outputs, or advance a media clock.
Stop with Ctrl-C after the native workflow. Evidence remains local in var/.
"""
import argparse, datetime, hashlib, json, pathlib, time
from h7_support import Client, ROOT, EVIDENCE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=1200)
    args=p.parse_args();assert 1<=args.seconds<=1800
    run=EVIDENCE/f'h12-native-{time.time_ns()}';run.mkdir(parents=True)
    exe=ROOT/'target/Motive.app/Contents/MacOS/motive'
    manifest={'app_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'observer':'status only, 4 Hz; does not control production','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run':str(run),'samples':0,'outputs':{},'revisions':[]}
    c=Client();start=time.monotonic();revision=None;initial_pid=None
    print(run,flush=True)
    try:
        with (run/'observations.jsonl').open('w') as log:
            while time.monotonic()-start<args.seconds:
                s=c.state();now=time.monotonic()
                if initial_pid is None:initial_pid=s['pid']
                assert s['pid']==initial_pid,'App restarted; start a new observation session'
                row={'seconds':now-start,'monotonic':now,'state':{k:s[k] for k in ('pid','revision','last_action','output','output_path','stats','encoding','sources','issues','recovery_required','recovery_sources','output_failure','transition','audio_mixer','overlays')}}
                if s['revision']!=revision:
                    row['project']=s['project'];row['output_configuration']=s['output_configuration'];revision=s['revision'];manifest['revisions'].append({'seconds':row['seconds'],'revision':revision,'origin':s['last_action']})
                if s['output'] in ('recording','streaming'):
                    key=s['output_path'] or 'loopback-rtmp'
                    manifest['outputs'].setdefault(key,{'kind':s['output'],'first_observation':row['seconds']})['last_observation']=row['seconds']
                log.write(json.dumps(row,separators=(',',':'))+'\n');log.flush();manifest['samples']+=1
                # The observer retains its own bounded transcript on disk, not
                # every JSON-RPC response in the helper's in-memory history.
                c.ops=c.ops[-1:]
                time.sleep(.25)
    except KeyboardInterrupt:manifest['stopped_by_operator']=True
    except BaseException as error:manifest['error']=repr(error);raise
    finally:
        c.close();manifest['elapsed_s']=time.monotonic()-start
        manifest['observations_sha256']=hashlib.sha256((run/'observations.jsonl').read_bytes()).hexdigest()
        (run/'manifest.json').write_text(json.dumps(manifest,indent=2));print(run/'manifest.json',flush=True)

if __name__=='__main__':main()
