#!/usr/bin/env python3
"""Read-only identity/hash checked vmmap and heap summary comparison.

Rounded vmmap categories are not unique physical RAM or allocation callsites.
All raw reports survive. No allocator purge, GC request or performance gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def size(value):
    match=re.fullmatch(r'(\d+(?:\.\d+)?)([KMGT]?)',value)
    if not match:raise ValueError('VM_SIZE')
    return round(float(match[1])*1024**('KMGT'.index(match[2])+1 if match[2] else 0))


def vm_summary(text):
    r={'regions':{},'malloc_zones':{},'note':'sizes rounded by vmmap; categories overlap and must not be summed as unique RAM'}
    footprint=re.search(r'^Physical footprint:\s+(\S+)',text,re.M)
    if footprint:r['physical_footprint_rounded_bytes']=size(footprint[1])
    zone=False
    for line in text.splitlines():
        if line.startswith('MALLOC ZONE'):zone=True;continue
        tokens=line.split()
        if zone and len(tokens)>=10:
            try:
                r['malloc_zones'][tokens[0]]={'virtual_bytes':size(tokens[1]),'resident_bytes':size(tokens[2]),
                    'dirty_bytes':size(tokens[3]),'swapped_bytes':size(tokens[4]),'allocation_count':int(tokens[5]),
                    'allocated_bytes':size(tokens[6]),'fragmentation_bytes':size(tokens[7])}
            except ValueError:continue
        elif not zone:
            match=re.match(r'^(.*?)\s{2,}((?:\d+(?:\.\d+)?[KMGT]?\s+){7}\d+)\s*(?:.*)?$',line)
            if match:
                fields=match[2].split()
                r['regions'][match[1].strip()]={key:size(value) for key,value in zip(
                    ('virtual_bytes','resident_bytes','dirty_bytes','swapped_bytes','volatile_bytes','nonvolatile_bytes','empty_bytes'),fields[:7])}
                r['regions'][match[1].strip()]['region_count']=int(fields[7])
    if 'TOTAL' not in r['malloc_zones'] or 'TOTAL' not in r['regions']:raise ValueError('VM_SUMMARY_TABLES')
    return r


def analyze(root):
    profile_path=root/'memory-profile.json';profile=json.loads(profile_path.read_text())
    hashes={'memory-profile.json':hashlib.sha256(profile_path.read_bytes()).hexdigest()};by_identity={}
    result={'status':'PARTIAL','scope':'one instrumented 600s session; no allocation-callsite or leak proof',
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':hashes,
        'unreached_stages':profile['unreached_stages_ms'],'identities':[],'heap':[]}
    for stage in profile['stages']:
        for process in stage['processes']:
            if process['status']!='PASS':continue
            path=root/process['path'];data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if digest!=process['sha256'] or not process['identity_still_matched']:raise ValueError('VM_PROVENANCE')
            hashes[process['path']]=digest
            key=(process['pid'],tuple(process['birth']),process['proc_start_abstime'])
            row=by_identity.setdefault(key,{'pid':key[0],'birth':key[1],'proc_start_abstime':key[2],'role':process['role'],'stages':[]})
            row['stages'].append({'requested_elapsed_ms':stage['requested_elapsed_ms'],'probe_ms':process['probe_ms'],
                'path':process['path'],'summary':vm_summary(data.decode())})
    for row in by_identity.values():
        if len(row['stages'])==3:
            first,middle,last=[r['summary'] for r in row['stages']]
            row['malloc_60_to_570']={key:last['malloc_zones']['TOTAL'][key]-first['malloc_zones']['TOTAL'][key]
                for key in ('allocated_bytes','allocation_count','virtual_bytes','resident_bytes','swapped_bytes','fragmentation_bytes')}
            row['malloc_300_to_570']={key:last['malloc_zones']['TOTAL'][key]-middle['malloc_zones']['TOTAL'][key]
                for key in ('allocated_bytes','allocation_count','virtual_bytes','resident_bytes','swapped_bytes','fragmentation_bytes')}
            changes=[]
            for name,values in last['regions'].items():
                if name.startswith('TOTAL'):continue
                old=first['regions'].get(name,{})
                changes.append({'name':name,'dirty_plus_swap_delta_bytes':values['dirty_bytes']+values['swapped_bytes']-old.get('dirty_bytes',0)-old.get('swapped_bytes',0),
                    'virtual_delta_bytes':values['virtual_bytes']-old.get('virtual_bytes',0)})
            row['largest_dirty_swap_changes']=sorted(changes,key=lambda x:abs(x['dirty_plus_swap_delta_bytes']),reverse=True)[:12]
        result['identities'].append(row)
    for name in ('heap-browser-summary','heap-browser-summary-late'):
        meta_path=root/(name+'.json');path=root/(name+'.txt')
        if not meta_path.exists() and not path.exists():continue
        meta=json.loads(meta_path.read_text());data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if meta.get('returncode')!=0 or digest!=meta['sha256'] or not meta['identity_matched']:raise ValueError('HEAP_PROVENANCE')
        if not any(row['pid']==meta['pid'] and list(row['birth'])==meta['birth'] for row in result['identities']):raise ValueError('HEAP_NOT_SUPERVISED_IDENTITY')
        hashes[meta_path.name]=hashlib.sha256(meta_path.read_bytes()).hexdigest();hashes[path.name]=digest
        text=data.decode();found=re.search(r'All zones: (\d+) nodes \((\d+) bytes\)',text)
        if not found:raise ValueError('HEAP_COUNTS')
        zombies={name:{'count':int(count),'bytes':int(length)} for count,length,name in
            re.findall(r'^\s+(\d+)\s+(\d+)\s+[\d.]+\s+(Cr(?:Fat)?Zombie)\b',text,re.M)}
        result['heap'].append({'path':path.name,'pid':meta['pid'],'birth':meta['birth'],
            'allocation_count':int(found[1]),'allocated_bytes':int(found[2]),'chromium_zombies':zombies})
    result['late_heap_growth_bytes']=(result['heap'][1]['allocated_bytes']-result['heap'][0]['allocated_bytes']) if len(result['heap'])==2 else None
    result['heap_status']='COMPARED' if len(result['heap'])==2 else 'NOT_FULLY_OBSERVED'
    result['limits']=['No CPU cadence acceptance from profiling runs.',
        'Heap bytes in use include allocations retained intentionally by Chromium and allocator clients; not automatically a leak.',
        'CrZombie counts identify some diagnostic retention, not the cause of all browser growth.',
        'Public region walk can hit its region limit; only complete vmmap summaries are compared here.',
        'Private/shared maps, RSS, footprint, virtual reservations and allocated bytes are distinct measurements.']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=analyze(a.root)
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'status':r['status'],'identities':len(r['identities']),'late_heap_growth_bytes':r['late_heap_growth_bytes']}))
