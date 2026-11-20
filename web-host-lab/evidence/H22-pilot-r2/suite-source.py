#!/usr/bin/env python3
"""Closed H22 owned native matrices; exclusive physical slot per case.

No threshold changes/retries of failed native runs. Busy-slot attempts are logged
and retried before launch only. Every matrix/name is immutable once created.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

LAB=Path(__file__).resolve().parents[1]
SMOKE='h22-native-multi-cold2-ephemeral'
WIDGET='h22-native-multi-widgets1-ephemeral'
GOAL='h22-native-multi-goal-load1-ephemeral'


def cases(suite):
    # name, build, scenario, count, seconds, width, height, intermittent audit
    if suite=='pilot':
        return [('boundary2','h22-native-multi-boundary1-ephemeral','security',1,5,640,360,False),
            ('lower3h',WIDGET,'lower-third',3,72,640,360,True),
            ('alert3v',WIDGET,'community-alert',3,72,540,960,True),
            ('goal3h',GOAL,'goal-load',3,72,640,360,True),
            ('widgetlife3',WIDGET,'widget-lifecycle',3,45,640,360,True),
            ('goallife3',GOAL,'goal-lifecycle',3,45,640,360,True),
            ('coldresize3',SMOKE,'cold-resize',3,12,640,360,False)]
    if suite=='capacity':
        return [(f'simple{count}h-r{repeat}',SMOKE,'steady',count,72,640,360,False)
            for count in (1,3,5) for repeat in (1,2,3)]
    if suite=='widgets':
        return [(f'{kind}{count}{orientation}-r{repeat}',build,scenario,count,72,width,height,True)
            for kind,build,scenario,count,orientation,width,height in
            [('goal',GOAL,'goal-load',n,'h',640,360) for n in (1,3,5)]+
            [('lower',WIDGET,'lower-third',3,'h',640,360),('alert',WIDGET,'community-alert',3,'v',540,960),
             ('mix',WIDGET,'widget-mix',5,'h',960,540),('mix',WIDGET,'widget-mix',5,'v',540,960),
             ('goal',GOAL,'goal-load',3,'v',540,960)] for repeat in (1,2,3)]
    if suite=='soak':
        return [('coldcycles3',SMOKE,'cold-cycles',3,600,640,360,False),
            ('widgetmix3h',WIDGET,'widget-soak',3,600,640,360,True),
            ('goals3v',GOAL,'goal-load',3,600,540,960,True)]
    raise ValueError('CLOSED_SUITE')


def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=['pilot','capacity','widgets','soak'],required=True)
    p.add_argument('--name',required=True);p.add_argument('--generation',required=True,type=int);a=p.parse_args()
    if not a.name.startswith('H22-') or not a.name.replace('-','').isalnum():raise ValueError('NAME')
    root=LAB/'evidence'/a.name;root.mkdir(mode=0o700)
    matrix=cases(a.suite);plan={'suite':a.suite,'cases':matrix,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'policy':'stop on first failed native run/audit; physical slot released between each case'}
    (root/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(root/'suite-source.py').write_bytes(Path(__file__).read_bytes())
    summary={'status':'PARTIAL','cases':[]}
    for index,(name,build,scenario,count,seconds,width,height,workload) in enumerate(matrix):
        trial=a.name+'-'+name;out=LAB/'evidence'/trial
        command=[sys.executable,str(LAB/'tools/h22_trial.py'),'--build',build,'--name',trial,'--scenario',scenario,
            '--instances',str(count),'--seconds',str(seconds),'--width',str(width),'--height',str(height),
            '--generation',str(a.generation+index*100)]
        result={'name':name,'run':str(out.relative_to(LAB)),'command':command,'slot_busy_attempts':0}
        end=time.monotonic()+1800
        with (root/(name+'.log')).open('x') as log:
            while True:
                code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
                if code!=75:break
                result['slot_busy_attempts']+=1
                if time.monotonic()>=end:break
                time.sleep(3)
            result['native_returncode']=code
            if code==0:
                for tool,filename in [('h22_audit.py','analysis.json'),*([('h22_workload_check.py','workload-analysis.json')] if workload else [])]:
                    code=subprocess.call([sys.executable,str(LAB/'tools'/tool),str(out),'--output',str(out/filename)],stdout=log,stderr=subprocess.STDOUT)
                    result[filename]={'returncode':code,'sha256':hashlib.sha256((out/filename).read_bytes()).hexdigest()}
                    if code:break
        result['status']='PASS' if code==0 else 'FAIL';summary['cases'].append(result)
        if code:summary['status']='FAIL'
        elif len(summary['cases'])==len(matrix):summary['status']='PASS'
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'case':name,'status':result['status'],'completed':len(summary['cases']),'total':len(matrix)}),flush=True)
        if code:return 1
        time.sleep(3)
    return 0


if __name__=='__main__':raise SystemExit(main())
