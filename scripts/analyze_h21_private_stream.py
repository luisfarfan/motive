#!/usr/bin/env python3
"""Offline local-file validation; never treats sent bytes as remote delivery."""
import argparse
import array
import json
import math
from pathlib import Path
import shutil
import subprocess

from verify_h14_collection import digest, lock, require, save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();held=lock();run=json.loads(a.report.read_text())
    out=a.output.absolute();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'analyzer-source.py')
    result={'status':'FAIL','scope':'Local MKV full decode, cadence and generated-tone continuity only.',
            'lock':held,'run_report_sha256':digest(a.report),'analyzer_sha256':digest(Path(__file__)),
            'remote_delivery':'NOT_MEASURED_BY_THIS_ANALYZER',
            'physical_av':'NOT_APPLICABLE_GENERATED_CONTENT','terminal_delivery':'NOT_ASSESSED'}
    try:
        owner=json.loads(a.report.parent.with_name(a.report.parent.name+'-owner').joinpath('report.json').read_text())
        require(owner['owner_exit']==0 and not owner['cleanup_errors'],'Owner must be closed')
        process=subprocess.run(['ps','-p',str(run['owner_pid']),'-o','pid='],capture_output=True,text=True,timeout=5)
        require(process.returncode==1 and not process.stdout.strip(),'Native owner still present')
        require(run['runtime_status']=='PASS' and not run['cleanup_errors'],'Runtime did not complete')
        require(digest(a.app/'Contents/MacOS/motive')==run['owner_sha256'],'Candidate changed')
        media=next(m for m in run['media'] if m['target']=='recording')
        result['media']={**media,'sha256':digest(media['path'])}
        ff=str(a.app/'Contents/MacOS/ffmpeg');fp=str(a.app/'Contents/MacOS/ffprobe')
        def decode(arguments):
            r=subprocess.run([ff,'-nostdin','-v','error','-xerror','-threads','2',*arguments],capture_output=True,timeout=180)
            require(r.returncode==0 and not r.stderr,'Local decode failed');return r.stdout
        decode(['-i',media['path'],'-f','null','-'])
        probe=subprocess.run([fp,'-v','error','-count_frames','-show_streams','-show_packets','-show_entries',
            'stream=codec_name,codec_type,width,height,avg_frame_rate,sample_rate,channels,nb_read_frames:packet=codec_type,pts_time',
            '-of','json',media['path']],capture_output=True,timeout=180)
        require(probe.returncode==0 and not probe.stderr,'Local probe failed')
        data=json.loads(probe.stdout);save(out/'probe.json',data)
        video=next(s for s in data['streams'] if s['codec_type']=='video')
        audio=next(s for s in data['streams'] if s['codec_type']=='audio')
        require((video['codec_name'],video['width'],video['height'],video['avg_frame_rate'])==('h264',1920,1080,'30/1'),'Wrong video format')
        require((audio['codec_name'],audio['sample_rate'],audio['channels'])==('aac','48000',2),'Wrong audio format')
        result['frames']=int(video['nb_read_frames']);result['cadence']={}
        for kind,bound in (('video',1/30+.0011),('audio',.023)):
            pts=[float(p['pts_time']) for p in data['packets'] if p['codec_type']==kind]
            gaps=[b-a for a,b in zip(pts,pts[1:])]
            require(gaps and min(gaps)>0 and max(gaps)<=bound,'Unexpected '+kind+' cadence')
            result['cadence'][kind]={'first_pts_s':pts[0],'last_pts_s':pts[-1],'max_gap_s':max(gaps)}
        require(result['cadence']['video']['last_pts_s']-result['cadence']['video']['first_pts_s']>=run['observed_seconds'],'Incomplete local duration')
        pcm=array.array('f',decode(['-i',media['path'],'-vn','-ac','1','-ar','48000','-f','f32le','-']))
        bins=[math.sqrt(sum(v*v for v in pcm[i:i+4800])/4800) for i in range(4800,len(pcm)-9600,4800)]
        require(bins and min(bins)>.0001,'Interior 100 ms tone discontinuity')
        peak=max(abs(v) for v in pcm);require(peak<.999,'Decoded audio clipping')
        result.update(status='PASS',audio_rms_min=min(bins),audio_peak=peak,
                      local_file_only=True,verification_label=run['verification_label'])
    except Exception as error:result['error']=repr(error)
    result['original_report_unchanged']=digest(a.report)==result['run_report_sha256']
    if not result['original_report_unchanged']:result['status']='FAIL'
    save(out/'analysis.json',result);print(json.dumps(result))
    return int(result['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
