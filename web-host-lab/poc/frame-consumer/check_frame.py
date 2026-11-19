#!/usr/bin/env python3
"""Inspect actual native fixture bytes, never generate evidence frames."""
import argparse
import json
from pathlib import Path

def inspect(meta, pixels):
    width,height,stride=meta['width'],meta['height'],meta['stride']
    if type(width) is not int or type(height) is not int or not((width,height) in {(640,360),(960,540),(540,960)}) or stride!=width*4 or len(pixels)!=stride*height:
        raise ValueError('FRAME_LAYOUT')
    if meta.get('native_executed') is not True: raise ValueError('NOT_NATIVE_EVIDENCE')
    def pixel(x,y):return tuple(pixels[y*stride+x*4:y*stride+x*4+4])
    corner=pixel(0,0);red=pixel(50,50)
    checks={'transparent_corner':corner==(0,0,0,0),'half_alpha_red':red[0:2]==(0,0) and 126<=red[2]<=129 and 126<=red[3]<=129,
            'premultiplied_bound':all(max(pixels[i:i+3])<=pixels[i+3]+1 for i in range(0,len(pixels),4))}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'samples':{'corner':corner,'red':red},
            'scope':'single native fixture buffer; not FPS, color calibration, libobs integration, sandbox or helper cleanup'}

def main():
    p=argparse.ArgumentParser();p.add_argument('metadata',type=Path);p.add_argument('bgra',type=Path);args=p.parse_args()
    if args.metadata.stat().st_size>65536 or args.bgra.stat().st_size>1920*1080*4:raise ValueError('INPUT_SIZE')
    result=inspect(json.loads(args.metadata.read_text()),args.bgra.read_bytes());print(json.dumps(result,indent=2));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
