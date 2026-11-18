#!/usr/bin/env python3
"""Reproduce the eight owned review packages and local catalog; no installation."""
import sys,hashlib,zipfile
from io import BytesIO
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,write_json,loads
from compiler import compile_element
from modular import load_pack
from templates import TEMPLATES
from packaging import package_bundle,package_web_bytes,verify_bytes,BASELINE,METADATA,CHECKSUMS
from catalog import CATALOG,validate_catalog
root=LAB/'marketplace-contract';(root/'packages').mkdir(exist_ok=True)
entries=[];reports=[]
items=[(n,lambda n=n:package_bundle(compile_element(LAB/'native-elements'/n/'element.json')),'element','native') for n in TEMPLATES]
items += [(n,lambda n=n:package_bundle(load_pack(LAB/'packs'/n)),'pack','native') for n in ['creator-tech-minimal','neon-arena-minimal','mixed-example']]
items.append(('goal-web',lambda:package_web_bytes(LAB/'web-elements/goal-celebration'),'element','web'))
for name,build,kind,mode in items:
 data=build();assert data==build(),f'Non-reproducible: {name}'
 report=verify_bytes(data);report['reproducible_bytes']=True;reports.append(report)
 path='packages/'+name+('.motiveweb' if mode=='web' else '.motivepack');(root/path).write_bytes(data)
 with zipfile.ZipFile(BytesIO(data)) as z:
  package=loads(z.read('package.json'));preview=package['preview_paths'][0];preview_hash=hashlib.sha256(z.read(preview)).hexdigest()
 entry={'id':package['id'],'version':package['version'],'kind':kind,'mode':mode,'name':package['name'],
        'description':'Original local authoring example; official installation pending.',
        'author':{'id':'motive-contributors','name':package['author'],'identity':'unverified'},'category':'celebration' if 'goal' in name else 'overlay',
        'tags':['original','local',mode],'license':package['license'],'required_capabilities':package['compatibility']['required_capabilities'],
        'compatibility':{'baseline_source_commit':BASELINE,'element_schema':1,'creatorpack_schema':1 if mode=='native' else 0,'web_element_schema':1 if mode=='web' else 0,'official_installation':'pending'},
        'package':{'path':path,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'content_kind':package['content_kind']},
        'preview':{'package_path':preview,'sha256':preview_hash,'media_type':'image/svg+xml'},
        'update':{'channel':'local_files','replaces_versions':[],'review_required':True}}
 entries.append(entry)
write_json(root/'catalog.json',{'schema_version':1,'kind':'motive_local_catalog','entries':entries})
write_json(root/'catalog.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema',**CATALOG})
write_json(LAB/'packager/package.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema',**METADATA})
write_json(LAB/'packager/checksums.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema',**CHECKSUMS})
write_json(LAB/'evidence/J-packages.json',{'status':'PASS','packages':reports})
write_json(LAB/'evidence/K-catalog.json',validate_catalog(root/'catalog.json'))
