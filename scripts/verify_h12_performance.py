#!/usr/bin/env python3
"""Owned H12 media lifecycle probe. Serial physical/bundle lock required.

Measures real process RSS/CPU via macOS libproc at 20 Hz, separately from native
estimated texture budgets. Never changes global settings or public destinations.
The app must be freshly opened, idle, with only default pattern/legacy sources.
"""
import ctypes, hashlib, json, os, pathlib, statistics, subprocess, threading, time
from h7_support import Client, ROOT, EVIDENCE, process_sample
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
from verify_h11_visuals import import_asset

class TaskInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('virtual','resident','user','system','threads_user','threads_system')] + [(name,ctypes.c_int32) for name in ('policy','faults','pageins','cow','sent','received','mach','unix','switches','threads','running','priority')]

class Timebase(ctypes.Structure):
    _fields_=[('numer',ctypes.c_uint32),('denom',ctypes.c_uint32)]

class Sampler:
    def __init__(self,pid):
        self.pid=pid;self.rows=[];self.stop=threading.Event()
        self.lib=ctypes.CDLL('/usr/lib/libproc.dylib');self.lib.proc_pidinfo.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int];self.lib.proc_pidinfo.restype=ctypes.c_int
        system=ctypes.CDLL('/usr/lib/libSystem.B.dylib');base=Timebase()
        system.mach_timebase_info.argtypes=[ctypes.POINTER(Timebase)]
        assert system.mach_timebase_info(ctypes.byref(base))==0 and base.denom
        self.ns_per_tick=base.numer/base.denom
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        previous=None
        while not self.stop.is_set():
            info=TaskInfo();n=self.lib.proc_pidinfo(self.pid,4,0,ctypes.byref(info),ctypes.sizeof(info));now=time.monotonic()
            if n!=ctypes.sizeof(info):break
            cpu=(info.user+info.system)*self.ns_per_tick/1e9
            self.rows.append({'monotonic':now,'rss_mib':info.resident/1048576,'cpu_total_s':cpu,'threads':info.threads,'cpu_percent':None if previous is None else 100*(cpu-previous[1])/(now-previous[0])})
            previous=(now,cpu);self.stop.wait(.05)
    def close(self):self.stop.set();self.thread.join()
    def interval(self,lo,hi):
        rows=[r for r in self.rows if lo<=r['monotonic']<=hi]
        assert rows,'No process samples'
        return {'samples':len(rows),'rss_min_mib':min(r['rss_mib'] for r in rows),'rss_max_mib':max(r['rss_mib'] for r in rows),'rss_median_mib':statistics.median(r['rss_mib'] for r in rows),'cpu_median_percent':statistics.median(r['cpu_percent'] for r in rows if r['cpu_percent'] is not None)}

def main():
    run=EVIDENCE/f'h12-performance-{time.time_ns()}';run.mkdir(parents=True)
    report={'ok':False,'run':str(run),'phases':[],'operations':[],'sampling':'macOS proc_pidinfo PROC_PIDTASKINFO at 20 Hz; CPU 100%=one core; includes GPUI/native preview','limits':'RSS sampling can miss peaks shorter than 50 ms. Native child counts are source counts, not a decoder allocator trace.'}
    c=None;sampler=None;original=None;disk=None;asset=None;owned_asset=False;fixture=None
    project=VERIFY.data_root / 'project.json';inbox=None
    try:
        c=Client();original=c.state();assert original['output']=='idle' and not original['audio_mixer']['store']['inputs'];assert all(s.get('overlay') is None and s['spec']['kind'] in ('pattern','overlay') for s in original['project']['graph']['sources'])
        report['initial']=original;report['app_sha256']=hashlib.sha256((VERIFY.app_executable).read_bytes()).hexdigest()
        disk=(project.read_bytes() if project.exists() else None,project.stat().st_mode&0o777 if project.exists() else 0o600)
        fixture=run/'owned-1080p.mp4'
        # Generate before taking any performance samples.
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=1920x1080:rate=30','-t','6','-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p',str(fixture)],check=True)
        assets={a['id'] for a in c.call('list_assets')['result']['assets']}
        asset=import_asset(c,fixture)['asset'];owned_asset=asset['id'] not in assets;inbox=VERIFY.data_root/'imports'/fixture.name
        sampler=Sampler(original['pid'])
        def operation(label,fn):
            lo=time.monotonic();value=fn();hi=time.monotonic();time.sleep(.1)
            report['operations'].append({'label':label,'milliseconds':(hi-lo)*1000,**sampler.interval(lo,hi+.1)})
            return value
        def phase(label,seconds=8):
            ps_before,_=process_sample(original['pid'])
            lo=time.monotonic();before=c.state();snapshots=[]
            while time.monotonic()-lo<seconds:
                time.sleep(.5);snapshots.append(c.state())
            hi=time.monotonic();end=snapshots[-1];assert end['pid']==original['pid'] and end['output']=='idle'
            assert end['stats']['rendered_frames']-before['stats']['rendered_frames']>seconds*20
            videos=[s for s in end['overlays']['runtime']['sources'] if s['kind']=='video'];assert all(v['audio_mixers']==0 and v['child_instances_created']==1 for v in videos)
            ps_after,_=process_sample(original['pid'])
            cpu_rows=[r for r in sampler.rows if lo<=r['monotonic']<=hi]
            measured_cpu=cpu_rows[-1]['cpu_total_s']-cpu_rows[0]['cpu_total_s']
            # Independent ps TIME check confirms the libproc time-unit mapping.
            assert abs(measured_cpu-(ps_after-ps_before))<.3,(measured_cpu,ps_after-ps_before)
            media_times={v['id']:sorted({s['media_time_ms'] for snap in snapshots for s in snap['overlays']['runtime']['sources'] if s['id']==v['id']}) for v in videos}
            result={'label':label,'seconds':hi-lo,'cpu_seconds_libproc':measured_cpu,'cpu_seconds_ps':ps_after-ps_before,'all':sampler.interval(lo,hi),'steady_after_2s':sampler.interval(lo+2,hi),'render_lag_delta':end['stats']['lagged_frames']-before['stats']['lagged_frames'],'before':before,'snapshots':snapshots,'media_times_ms':media_times,'estimated_visual_bytes':sum(s.get('framebuffer_estimate_bytes',0)+s.get('text_atlas_estimate_bytes',0) for s in end['overlays']['runtime']['sources'])}
            report['phases'].append(result);print(label,result['all'],'lag',result['render_lag_delta'],flush=True)
        scene=operation('create_scene',lambda:c.call('create_scene',name='H12 decoder performance'))['state']['project']['graph']['active_scene']
        phase('zero_video')
        ids=[];layers=[]
        for n in range(4):
            r=operation(f'create_video_{n+1}',lambda:c.call('create_overlay',scene_id=scene,name=f'Owned video {n+1}',definition={'kind':'video','asset_id':asset['id'],'opacity':1.,'looping':True}))
            sid=r['result']['source_id'];ids.append(sid);layer=next(l for s in r['state']['project']['graph']['scenes'] if s['id']==scene for l in s['layers'] if l['source_id']==sid);layers.append(layer['id'])
            c.call('set_transform',scene_id=scene,layer_id=layer['id'],variant='horizontal',transform={'x':(n%2)*480,'y':(n//2)*270,'width':480,'height':270,'visible':True,'order':n})
            if n==0:
                phase('one_visible')
                set_visibility(c,scene,layers,False);phase('one_hidden');set_visibility(c,scene,layers,True)
        phase('four_visible');set_visibility(c,scene,layers,False);phase('four_hidden');set_visibility(c,scene,layers,True)
        before=c.state();replacement=json.loads(json.dumps(before['project']));mapping={sid:f'h12-video-replacement-{i}' for i,sid in enumerate(ids)}
        for source in replacement['graph']['sources']:
            if source['id'] in mapping:source['id']=mapping[source['id']]
        for s in replacement['graph']['scenes']:
            for layer in s['layers']:layer['source_id']=mapping.get(layer['source_id'],layer['source_id'])
        write_project(project,replacement)
        operation('reconcile_four_replacement_video_ids',lambda:c.call('load_project'))
        after=c.state();report['reconcile']={'before':before,'after':after};assert len([s for s in after['overlays']['runtime']['sources'] if s['kind']=='video'])==4
        assert {s['instance_id'] for s in before['overlays']['runtime']['sources']}.isdisjoint({s['instance_id'] for s in after['overlays']['runtime']['sources']})
        phase('four_reconciled')
        # A long native animation and explicit cancellation; no per-frame writes.
        first=layers[0];result=c.call('animate_overlay',scene_id=scene,layer_id=first,animation={'kind':'scale_in','easing':'ease_in_out','duration_ms':10000,'distance':0,'scale_from':.2})
        token=result['result']['operation_id'];phase('ten_second_animation_first_half',6)
        c.call('cancel_overlay_animation',operation_id=token);cancelled=c.wait(lambda s:any(j['operation_id']==token and j['phase']=='cancelled' and not j['pending_ack'] for j in s['overlays']['runtime']['animations']['jobs']))
        report['cancelled']=cancelled['overlays']['runtime']['animations'];phase('after_cancel')
        completed_token=c.call('animate_overlay',scene_id=scene,layer_id=first,animation={'kind':'scale_in','easing':'ease_in_out','duration_ms':10000,'distance':0,'scale_from':.2})['result']['operation_id']
        phase('full_ten_second_animation',12)
        completed=c.state()['overlays']['runtime']['animations']
        assert any(j['operation_id']==completed_token and j['phase']=='completed' and not j['pending_ack'] for j in completed['jobs'])
        report['completed_animation']=completed
        operation('restore_original_project',lambda:(write_project(project,original['project']),c.call('load_project')))
        phase('after_release')
        # Repeated reopen/release distinguishes retained allocator pages from
        # unbounded growth. Keep every peak and lag counter; no RSS acceptance
        # limit is invented from the separate visual texture budget.
        for cycle in range(3):
            write_project(project,replacement)
            operation(f'reopen_four_cycle_{cycle+1}',lambda:c.call('load_project'))
            phase(f'reopen_four_cycle_{cycle+1}',6)
            write_project(project,original['project'])
            operation(f'release_cycle_{cycle+1}',lambda:c.call('load_project'))
            phase(f'released_cycle_{cycle+1}',8)
        phase('released_settling',20)
        assert c.state()['project']==original['project']
        report['temporary_assets']=[p.name for p in (VERIFY.data_root / 'assets').glob('.import-*')];assert not report['temporary_assets']
        report['ok']=True
    except BaseException as error:report['error']=repr(error);raise
    finally:
        errors=[]
        if sampler:sampler.close();report['process_samples']=sampler.rows;report['cpu_nanoseconds_per_mach_tick']=sampler.ns_per_tick
        if c and original:
            try:
                if c.state()['output']!='idle':c.stop()
                state=c.state()
                for j in state['overlays']['runtime']['animations']['jobs']:
                    if j['phase']=='running':c.call('cancel_overlay_animation',operation_id=j['operation_id'])
                c.wait(lambda s:not s['overlays']['runtime']['animations']['busy'])
                write_project(project,original['project']);c.call('load_project')
                if owned_asset:c.call('remove_asset',asset_id=asset['id'])
            except BaseException as error:errors.append(repr(error))
            report['control_operations']=c.ops;c.close()
        if disk:
            if disk[0] is None:project.unlink(missing_ok=True)
            else:project.write_bytes(disk[0]);project.chmod(disk[1])
        if inbox:inbox.unlink(missing_ok=True)
        if errors:report['ok']=False;report['cleanup_errors']=errors
        (run/'report.json').write_text(json.dumps(report,indent=2));print(run/'report.json',flush=True)
    assert report['ok']

def write_project(path,value):
    temp=path.with_suffix('.h12-tmp');temp.write_text(json.dumps(value,indent=2));temp.chmod(0o600);temp.replace(path)

def set_visibility(c,scene,ids,visible):
    state=c.state();s=next(s for s in state['project']['graph']['scenes'] if s['id']==scene)
    for layer in s['layers']:
        if layer['id'] in ids:
            transform=dict(layer['layouts']['horizontal']);transform['visible']=visible
            c.call('set_transform',scene_id=scene,layer_id=layer['id'],variant='horizontal',transform=transform)

if __name__=='__main__':main()
