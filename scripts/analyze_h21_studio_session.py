#!/usr/bin/env python3
"""Offline full decode, continuous PCM and owned guest-marker A/V over time.

Keeps original reports unchanged. Periodic marker pairing measures relative
alignment; it is not a calibrated camera/microphone latency measurement.
"""
import argparse
import array
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

from verify_h14_collection import digest, lock, require, save
from h21_session_metrics import summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();lock()
    source=args.report.resolve(strict=True);source_hash=digest(source);run=json.loads(source.read_text())
    out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    app=args.app.resolve(strict=True);ffmpeg=str(app/'Contents/MacOS/ffmpeg');ffprobe=str(app/'Contents/MacOS/ffprobe')
    report={'status':'FAIL','source_report':str(source),'source_sha256':source_hash,
        'analyzer_sha256':digest(Path(__file__)),'media':[],
        'scope':'Owned guest window/application audio marker; not calibrated physical camera/microphone latency.',
        'physical_camera_av':'NOT_MEASURED', 'browser_capture':run.get('browser_capture','NOT_TESTED'),
        'audio_quality_status':run.get('audio_quality_status','NOT_SEPARATELY_RECORDED'),
        'personal_ready':False,'resources':summarize(run)}
    try:
        require(run.get('runtime_status')=='PASS' and not run['cleanup_errors'],'Runtime did not pass')
        require(digest(app/'Contents/MacOS/motive')==run['owner_sha256'],'Candidate changed')
        for key in ('owner_pid','fixture_pid'):
            pid=run[key]
            result=subprocess.run(['ps','-p',str(pid),'-o','pid='],capture_output=True,text=True)
            require(result.returncode==1 and not result.stdout.strip(),'Owned producer still present; offline analysis refused')
        duration=run['requested_seconds']
        windows=[(10,19),(26,36),(48,58)] if duration==60 else [(15,45),(1760,1790),(3550,3580)]
        fps=run['fps']
        source_state=next(v for v in run['initial_state']['sources'] if v['id']==run['window_source_id'])
        width,height=source_state['width'],source_state['height']
        rx,ry,rw,rh=run['window_rect'];scale=min(2*rw/width,2*rh/height)
        x=round(2*rx+(2*rw-width*scale)/2+width*.04*scale)
        y=round(2*ry+(2*rh-height*scale)/2+height*.94*scale)
        report['marker_crop_center']=[x,y]
        cosine=[math.cos(2*math.pi*997*i/48000) for i in range(480)]
        sine=[math.sin(2*math.pi*997*i/48000) for i in range(480)]
        for medium in run['media']:
            row={**medium,'status':'FAIL','sha256':digest(Path(medium['path']))};report['media'].append(row)
            p=subprocess.run([ffprobe,'-v','error','-show_streams','-show_packets','-show_entries',
                'stream=codec_name,codec_type,width,height,avg_frame_rate,sample_rate,channels:packet=codec_type,pts_time',
                '-of','json',medium['path']],capture_output=True,timeout=300)
            require(p.returncode==0 and not p.stderr,'Packet probe failed');probe=json.loads(p.stdout)
            save(out/(medium['target']+'-probe.json'),probe)
            video=next(s for s in probe['streams'] if s['codec_type']=='video');audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
            require((video['codec_name'],video['width'],video['height'],video['avg_frame_rate'])==('h264',1920,1080,str(fps)+'/1'),'Wrong video format')
            require((audio['codec_name'],audio['sample_rate'],audio['channels'])==('aac','48000',2),'Wrong audio format')
            row['max_pts_gap_s']={}
            for kind,bound in (('video',1/fps+.0011),('audio',.023)):
                pts=[float(v['pts_time']) for v in probe['packets'] if v['codec_type']==kind]
                gaps=[b-a for a,b in zip(pts,pts[1:])]
                require(gaps and min(gaps)>0 and max(gaps)<=bound,kind+' packet cadence failed')
                row['max_pts_gap_s'][kind]=max(gaps)
            video_log=out/(medium['target']+'-video-decode.log')
            with video_log.open('x') as log:
                decoded=subprocess.run([ffmpeg,'-nostdin','-v','info','-xerror','-threads','2','-copyts','-i',medium['path'],
                    '-an','-vf',f'crop=8:8:{x-4}:{y-4},scale=1:1,showinfo','-fps_mode','passthrough',
                    '-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE,stderr=log,timeout=900)
            require(decoded.returncode==0,'Full video decode failed')
            video_pts=[]
            with video_log.open() as log:
                for line in log:
                    match=re.search(r'\bn:\s*\d+\s+pts:\s*[-\d]+\s+pts_time:([-\d.e+]+)',line)
                    if match:video_pts.append(float(match.group(1)))
            require(len(decoded.stdout)==3*len(video_pts) and len(video_pts)>=duration*(fps-.5),'Incomplete decoded video coverage')
            row['decoded_frames']=len(video_pts)
            video_edges=[];previous=False
            for i,t in enumerate(video_pts):
                r,g,b=decoded.stdout[i*3:i*3+3];on=g>90 and g>r*2 and g>b*1.7
                if on and not previous:video_edges.append(t)
                previous=on
            # Retain the whole decoded marker timeline for review of gaps between
            # A/V windows. Planned off-marker scenes must be assessed separately;
            # this telemetry alone is not a full-image freshness acceptance gate.
            row['marker_video_onsets_s']=video_edges
            marker_gaps=[(left,right,right-left) for left,right in zip(video_edges,video_edges[1:])]
            row['max_marker_gap_s']=max((gap for _,_,gap in marker_gaps),default=None)
            row['marker_gaps_over_1_2_s']=[{'from_s':left,'to_s':right,'gap_s':gap}
                                          for left,right,gap in marker_gaps if gap>1.2]
            row['marker_timeline_scope']='All decoded frames at the marker crop; expected off-marker scenes require event review. Not a full-image freshness proof.'
            audio_log=out/(medium['target']+'-audio-decode.log')
            amplitudes=[];rms=[];peak=0;sample_count=0
            with audio_log.open('x') as log:
                process=subprocess.Popen([ffmpeg,'-nostdin','-v','info','-xerror','-threads','2','-copyts','-i',medium['path'],
                    '-vn','-af','ashowinfo','-ac','1','-ar','48000','-f','f32le','-'],stdout=subprocess.PIPE,stderr=log)
                try:
                    while True:
                        block=process.stdout.read(4800*4)
                        if not block:break
                        require(len(block)%4==0,'Truncated PCM sample')
                        samples=array.array('f',block)
                        peak=max(peak,max(abs(v) for v in samples))
                        if sample_count>=48000 and len(samples)==4800:rms.append(math.sqrt(sum(v*v for v in samples)/len(samples)))
                        t=sample_count/48000
                        # Keep every application-marker audio onset, including
                        # intervals outside the three A/V measurement windows.
                        # This does not change their historical acceptance gates.
                        for offset in range(0,len(samples)-479,480):
                            values=samples[offset:offset+480]
                            real=sum(v*c for v,c in zip(values,cosine));imag=sum(v*s for v,s in zip(values,sine))
                            amplitudes.append(((sample_count+offset)/48000,2*math.hypot(real,imag)/480))
                        sample_count+=len(samples)
                    require(process.wait(timeout=30)==0,'Full audio decode failed')
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
            first_audio=None
            with audio_log.open() as log:
                for line in log:
                    match=re.search(r'\bn:\s*0\s+pts:\s*[-\d]+\s+pts_time:([-\d.e+]+)',line)
                    if match:first_audio=float(match.group(1));break
            require(first_audio is not None,'Decoded audio timestamp missing')
            require(sample_count>=duration*48000 and rms and min(rms[:-10])>.0001 and peak<.999,'PCM coverage, continuity or clipping failed')
            row.update(pcm_samples=sample_count,audio_rms_min=min(rms[:-10]),pcm_peak=peak,audio_origin_pts_s=first_audio)
            audio_edges=[];previous=False;prior_time=None
            for t,amplitude in amplitudes:
                if prior_time is None or t-prior_time>.011:previous=False
                on=amplitude>.005
                if on and not previous:audio_edges.append(t+first_audio)
                previous=on;prior_time=t
            row['marker_audio_onsets_s']=audio_edges
            audio_marker_gaps=[(left,right,right-left) for left,right in zip(audio_edges,audio_edges[1:])]
            row['max_audio_marker_gap_s']=max((gap for _,_,gap in audio_marker_gaps),default=None)
            row['audio_marker_gaps_over_1_2_s']=[{'from_s':left,'to_s':right,'gap_s':gap}
                for left,right,gap in audio_marker_gaps if gap>1.2]
            row['audio_marker_timeline_scope']='997 Hz component in the whole decoded mix. Planned gain changes require event review; this is not isolated microphone or second-application continuity.'
            row['av_windows']=[]
            for lo,hi in windows:
                visual=[t for t in video_edges if lo<=t<=hi]
                require(len(visual)>=5,'Missing guest marker transitions in measured window')
                pairs=[(v,min(audio_edges,key=lambda a:abs(a-v))) for v in visual]
                require(len(set(a for _,a in pairs))==len(pairs),'Ambiguous/reused audio onset')
                differences=[a-v for v,a in pairs]
                result={'window_s':[lo,hi],'video_onsets':visual,'audio_onsets':[a for _,a in pairs],
                        'audio_minus_video_s':differences,'median_s':statistics.median(differences),
                        'max_abs_s':max(abs(d) for d in differences)}
                row['av_windows'].append(result)
                require(result['max_abs_s']<=.080,'H20 80 ms A/V budget exceeded')
            first,last=row['av_windows'][0],row['av_windows'][-1]
            elapsed=statistics.mean(last['video_onsets'])-statistics.mean(first['video_onsets'])
            row['observed_offset_change_s']=last['median_s']-first['median_s']
            if duration==3600:
                row['drift_s_per_hour']=abs(row['observed_offset_change_s'])*3600/elapsed
                require(row['drift_s_per_hour']<=.040,'H20 40 ms/hour drift budget exceeded')
            else:row['drift_s_per_hour']=None
            row['status']='PASS'
        require(len(report['media'])==2,'Both outputs required')
        report['status']='PASS'
        report['duration_gate']='PASS' if duration==3600 and run['observed_seconds']>=3600 else 'PILOT_ONLY'
        if run.get('audio_quality_status') == 'FAIL':
            report['status']='PARTIAL'
            report['limitation']='Media/continuity gates passed, but microphone input clipping remains an audio-quality FAIL.'
    except Exception as error:report['error']=repr(error)
    report['source_unchanged']=digest(source)==source_hash
    if not report['source_unchanged']:report['status']='FAIL'
    save(out/'analysis.json',report)
    print(json.dumps({'status':report['status'],'error':report.get('error')}))
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
