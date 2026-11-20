#!/usr/bin/env python3
"""Select one immutable H22 owned build and run through the existing supervisor."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from build_native import is_h22_name

LAB=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--scenario',default='steady')
    p.add_argument('--instances',type=int,default=3)
    p.add_argument('--seconds',type=int,default=72)
    p.add_argument('--width',type=int,default=640)
    p.add_argument('--height',type=int,default=360)
    p.add_argument('--generation',type=int,required=True)
    p.add_argument('--memory-profile',action='store_true')
    a=p.parse_args()
    if not is_h22_name(a.build) or not a.name.startswith('H22-') or not a.name.replace('-','').isalnum():
        raise ValueError('H22_CLOSED_BUILD_AND_REPORT_NAME')
    report=json.loads((LAB/'evidence'/(a.build.replace('h22-','H22-',1)+'-build.json')).read_text())
    if not report.get('network_lab') or report.get('network_lab_policy')!='closed-resolver-v2':
        print('H22_NATIVE_HOLD: old network profile; see local coordination receipt',flush=True)
        return 78
    command=[sys.executable,str(LAB/'tools/h22_with_lock.py'),sys.executable,str(LAB/'tools/run_h19_multi.py'),
        '--build-root',str(LAB/'.cache'/a.build),'--expected-sha256',report['binaries'][0]['sha256'],
        '--output-dir',str(LAB/'evidence'/a.name),'--scenario',a.scenario,'--instances',str(a.instances),
        '--duration-ms',str(a.seconds*1000),'--deadline-seconds',str(a.seconds+20),
        '--width',str(a.width),'--height',str(a.height),'--generation',str(a.generation),'--png']
    if a.memory_profile:command.append('--memory-profile')
    return subprocess.call(command)


if __name__=='__main__':raise SystemExit(main())
