#!/usr/bin/env python3
"""Offline decoded pixels/counters, audio and cadence; retain original run report.

Snapshot phase brackets come from the actual OBS preview. Encoded frames are
matched by the fixture's visual counter, not by guessed cross-clock subtraction.
"""
import argparse
import array
from collections import defaultdict
import json
import math
from pathlib import Path
import statistics
import subprocess

from verify_h14_collection import digest, lock, require, save

WIDTH, HEIGHT = 768, 432


def counters(raw):
    require(len(raw)==WIDTH*HEIGHT*3,'Incomplete RGB frame')
    regions=[[],[]]
    for i in range(0,len(raw),3):
        r,g,b=raw[i:i+3]
        if r>120 and r>2*g and r>2*b: regions[0].append(i//3)
        if g>100 and b>100 and r<g/2 and abs(g-b)<45: regions[1].append(i//3)
    result={}
    for label,points in zip(('red','cyan'),regions):
        if len(points)<100: result[label]=None; continue
        xs=[p%WIDTH for p in points]; ys=[p//WIDTH for p in points]
        x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
        bits=[]; valid=True
        for bit in range(16):
            x=round(x0+(x1-x0)*(.07+bit*.055)); y=round(y0+(y1-y0)*.725)
            samples=[statistics.mean(raw[(yy*WIDTH+xx)*3:(yy*WIDTH+xx)*3+3])
                     for yy in range(max(0,y-1),min(HEIGHT,y+2))
                     for xx in range(max(0,x-1),min(WIDTH,x+2))]
            level=statistics.median(samples)
            if not (level<85 or level>165): valid=False
            bits.append(int(level>165))
        result[label]={'pixels':len(points),'bounds':[x0,y0,x1,y1],
                       'counter':sum(b<<i for i,b in enumerate(bits)) if valid else None}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); lock()
    source=args.report.resolve(strict=True); source_hash=digest(source); run=json.loads(source.read_text())
    out=args.output.absolute(); out.mkdir(parents=True,exist_ok=False)
    app=args.app.resolve(strict=True)
    report={'status':'FAIL','run_report':str(source),'run_report_sha256':source_hash,
            'owner_sha256':run['owner_sha256'],'analyzer_sha256':digest(Path(__file__)), 'snapshots':[],'media':[],
            'scope':'Real decoded pixels; no 60 Hz source freshness, physical A/V, long soak or terminal delivery claim.'}
    def ff(arguments):
        p=subprocess.run([str(app/'Contents/MacOS/ffmpeg'),'-nostdin','-v','error','-threads','2',*arguments],capture_output=True,timeout=180)
        require(p.returncode==0 and not p.stderr,'Decode error: '+p.stderr.decode()[:300]);return p.stdout
    phases=defaultdict(list)
    try:
        for key in ('owner_pid','fixture_pid'):
            pid=run.get(key)
            require(isinstance(pid,int) and pid>1,'Missing owned process identity')
            p=subprocess.run(['ps','-p',str(pid),'-o','pid='],capture_output=True,text=True,timeout=5)
            require(p.returncode==1 and not p.stdout.strip(),'Owned PID still present; offline analysis withheld')
        require(run.get('runtime_status')=='PASS' and not run['cleanup_errors'],'Runtime did not pass')
        require(digest(app/'Contents/MacOS/motive')==run['owner_sha256'],'Candidate changed')
        for entry in run['snapshots']:
            require(digest(Path(entry['path']))==entry['sha256'],'Snapshot changed')
            rgb=ff(['-i',entry['path'],'-frames:v','1','-vf',f'scale={WIDTH}:{HEIGHT},format=rgb24','-f','rawvideo','-'])
            decoded=counters(rgb); row={**entry,'decoded':decoded};report['snapshots'].append(row)
            phases[entry['phase']].append(decoded)
        required=(['both_visible','focus_second'] if run.get('window_layer_after_admission') else
                  ['controlled_display'] if run['mode']=='display' else ['both_visible','focus_second','resized','restored'])
        if run.get('native_fullscreen'): required.append('fullscreen')
        required.extend(run.get('additional_verified_phases', []))
        for phase in required:
            rows=phases[phase];require(len(rows)==2,'Missing paired snapshots: '+phase)
            for color in (('red','cyan') if run['mode']=='application' else ('red',)):
                require(all(r[color] and r[color]['counter'] is not None for r in rows),f'{phase}: {color} pixels/counter absent')
                a,b=[r[color]['counter'] for r in rows]
                require(0<(b-a)%65536<(650 if run['mode']=='display' else 30),f'{phase}: {color} counter stalled or invalid')
        if run['mode']=='application':
            for phase in ('minimized','first_window_closed'):
                rows=phases[phase]
                require(len(rows)==2 and all(r['cyan'] and r['cyan']['counter'] is not None for r in rows),'Second window absent: '+phase)
                require(0<(rows[1]['cyan']['counter']-rows[0]['cyan']['counter'])%65536<30,'Second window stalled: '+phase)
        report['preview_progress']='PASS'
        for medium in run['media']:
            row={**medium,'status':'FAIL','sha256':digest(Path(medium['path']))};report['media'].append(row)
            ff(['-i',medium['path'],'-f','null','-'])
            p=subprocess.run([str(app/'Contents/MacOS/ffprobe'),'-v','error','-count_frames','-show_streams','-show_packets','-show_entries',
                'stream=codec_name,codec_type,width,height,avg_frame_rate,sample_rate,channels,nb_read_frames:packet=codec_type,pts_time',
                '-of','json',medium['path']],capture_output=True,timeout=120)
            require(p.returncode==0 and not p.stderr,'Packet probe failed'); probe=json.loads(p.stdout)
            save(out/(medium['target']+'-probe.json'),probe)
            video=next(s for s in probe['streams'] if s['codec_type']=='video');audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
            require((video['codec_name'],video['width'],video['height'],video['avg_frame_rate'])==('h264',1920,1080,str(run['fps'])+'/1'),'Wrong video format')
            require((audio['codec_name'],audio['sample_rate'],audio['channels'])==('aac','48000',2),'Wrong audio format')
            row['frames']=int(video['nb_read_frames']);row['max_pts_gap_s']={}
            for kind,bound in (('video',1/run['fps']+.0011),('audio',.023)):
                pts=[float(p['pts_time']) for p in probe['packets'] if p['codec_type']==kind]
                gaps=[b-a for a,b in zip(pts,pts[1:])]
                require(gaps and min(gaps)>0 and max(gaps)<=bound,kind+' cadence failed')
                row['max_pts_gap_s'][kind]=max(gaps)
            pcm=array.array('f',ff(['-i',medium['path'],'-vn','-ac','1','-ar','48000','-f','f32le','-']))
            rms=[math.sqrt(sum(v*v for v in pcm[i:i+4800])/4800) for i in range(4800,len(pcm)-9600,4800)]
            require(rms and min(rms)>.0001 and max(abs(v) for v in pcm)<.999,'Tone discontinuity or clipping')
            row['audio_rms_min']=min(rms)
            raw=ff(['-i',medium['path'],'-an','-vf',f'fps=2,scale={WIDTH}:{HEIGHT},format=rgb24','-f','rawvideo','-'])
            size=WIDTH*HEIGHT*3;require(len(raw)%size==0,'Truncated sampled video')
            decoded=[counters(raw[i:i+size]) for i in range(0,len(raw),size)]
            save(out/(medium['target']+'-counters.json'),decoded)
            row['source_counters']={}
            for color in (('red','cyan') if run['mode']=='application' else ('red',)):
                values=[r[color]['counter'] for r in decoded if r[color] and r[color]['counter'] is not None]
                require(len(set(values))>=(100 if run['mode']=='display' else 10),'Insufficient encoded '+color+' progress')
                reference_phase=('raised' if run.get('window_layer_after_admission') else
                                 'controlled_display' if run['mode']=='display' else 'restored')
                lo,hi=[r[color]['counter'] for r in phases[reference_phase]]
                restored=sorted(set(v for v in values if lo<=v<=hi))
                require(len(restored)>=2,'Encoded '+reference_phase+' '+color+' progress not observed')
                reference_key='raised_observed' if run.get('window_layer_after_admission') else 'restored_observed'
                row['source_counters'][color]={'distinct':len(set(values)),reference_key:restored}
                if run.get('native_fullscreen'):
                    lo,hi=[r[color]['counter'] for r in phases['fullscreen']]
                    fullscreen=sorted(set(v for v in values if lo<=v<=hi))
                    require(len(fullscreen)>=2,'Encoded fullscreen '+color+' progress not observed')
                    row['source_counters'][color]['fullscreen_observed']=fullscreen
                for phase in run.get('additional_verified_phases', []):
                    lo,hi=[r[color]['counter'] for r in phases[phase]]
                    observed=sorted(set(v for v in values if lo<=v<=hi))
                    require(len(observed)>=2,'Encoded '+phase+' '+color+' progress not observed')
                    row['source_counters'][color][phase+'_observed']=observed
            final=ff(['-sseof','-2','-i',medium['path'],'-frames:v','1','-vf','scale=96:54,format=rgb24','-f','rawvideo','-'])
            expected=((33,156,135),(59,92,181),(199,87,61))
            actual=[list(final[(5*96+x)*3:(5*96+x)*3+3]) for x in (15,48,80)]
            require(len(final)==96*54*3 and all(max(abs(a-b) for a,b in zip(v,e))<=25 for v,e in zip(actual,expected)),'Safe pattern absent')
            row['safe_pattern_rgb']=actual;row['status']='PASS'
        require(len(report['media'])==2,'Both outputs required');report['status']='PASS'
    except Exception as error: report['error']=repr(error)
    report['run_report_unchanged']=digest(source)==source_hash
    if not report['run_report_unchanged']:report['status']='FAIL'
    save(out/'analysis.json',report);print(json.dumps({'status':report['status'],'error':report.get('error'),'output':str(out)}))
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
