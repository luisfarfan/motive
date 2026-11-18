#!/usr/bin/env python3
"""Compile-only API fixture. Never links, loads or starts Chromium."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'tools'))
from fetch_sources import verify
sources=json.loads((ROOT/'research/sources.lock.json').read_text())['sources']
out=ROOT/'.cache/native-api';out.mkdir(parents=True,exist_ok=True)
fixture=ROOT/'poc/fixtures'
rows=['#pragma once','#include <map>','#include <string>','#include <cstddef>','struct Asset { const unsigned char* bytes; size_t size; const char* mime; };']
entries=[]
for index,(name,mime) in enumerate([('index.html','text/html'),('fixture.css','text/css'),('fixture.js','text/javascript')]):
    data=(fixture/name).read_bytes();rows.append(f'inline constexpr unsigned char asset{index}[]={{'+','.join(str(b) for b in data)+'};')
    entries.append(f'{{"motive://i1-g1/{name}",{{asset{index},sizeof(asset{index}),"{mime}"}}}}')
rows.append('inline const std::map<std::string,Asset> Assets={'+','.join(entries)+'};')
(out/'fixture_assets.hpp').write_text('\n'.join(rows)+'\n')
reports=[]
for e in sources:
    if not e['id'].startswith('cef-obs'):continue
    verify(e)
    for file in ['fixture.mm','helper.cc']:
        command=['clang++','-std=c++20','-DCEF_API_VERSION=15000','-I'+str(ROOT/e['source']),'-I'+str(out),'-fsyntax-only',str(ROOT/'poc/browser-host/native'/file)]
        result=subprocess.run(command,text=True,capture_output=True)
        reports.append({'source':e['id'],'file':file,'command':command,'returncode':result.returncode,'diagnostics':result.stdout+result.stderr})
report={'native_executed':False,'linked':False,'checks':reports,'status':'PASS' if all(x['returncode']==0 for x in reports) else 'FAIL'}
(ROOT/'evidence/I-native-api.json').write_text(json.dumps(report,indent=2)+'\n')
for r in reports:print(r['source'],r['file'],r['returncode'],r['diagnostics'][:5000])
sys.exit(0 if report['status']=='PASS' else 1)
