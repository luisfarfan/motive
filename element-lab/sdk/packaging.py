"""Reproducible offline review packages. Private validation staging; no installer."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import stat
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from common import LAB,LabError,encode,loads,read_bytes,relative,require,validate
from schemas import obj,arr,string,number,ID,VERSION,LICENSE,HASH,PATH
from compiler import Bundle
from contracts import check_asset,contract,estimate,png_info
from preview import svg
from web_contract import WEB,validate_web

MAX_TOTAL=128*1024**2;MAX_FILE=64*1024**2;MAX_ENTRIES=256
METADATA=obj({'package_version':{'const':1},'format':{'const':'motive-element-lab-review'},
    'content_kind':{'enum':['declarative_pack','web_element']},'id':string(64),'version':VERSION,'name':string(128),'author':string(128),'license':LICENSE,
    'manifest':{'enum':['manifest.json','web-element.json']},'preview_paths':arr(PATH,16,1),
    'payload_files':number(1,254,True),'payload_bytes':number(1,MAX_TOTAL,True),
    'compatibility':obj({'baseline':{'type':'string','pattern':'[0-9a-f]{40}'},'creatorpack_schema':number(0,1,True),'web_element_schema':number(0,1,True),'required_capabilities':arr(string(64),32)}),
    'review':{'const':'required_before_official_installation'},'trusted_author':{'const':False}})
CHECKSUMS=obj({'version':{'const':1},'algorithm':{'const':'sha256'},'files':arr(obj({'path':PATH,'bytes':number(1,MAX_FILE,True),'sha256':HASH}),255,1)})
BASELINE='6019ad0acac4b52dcf1ebc44f2006406fde533f8'

def passive_svg(data: bytes):
    require(len(data)<=4*1024**2 and b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(),'SVG','Bounded passive SVG required')
    try:root=ET.fromstring(data)
    except ET.ParseError as e:raise LabError('SVG','Invalid XML') from e
    allowed={'svg','g','defs','pattern','path','rect','ellipse','circle','line','polygon','text','tspan','image','title','desc'}
    attrs={'width','height','viewBox','role','aria-label','id','x','y','x1','x2','y1','y2','cx','cy','rx','ry','r','d','points','fill','stroke','stroke-width',
           'opacity','transform','patternUnits','font-family','font-size','font-weight','letter-spacing','text-anchor','href'}
    require(root.tag.rsplit('}',1)[-1]=='svg','SVG','SVG root required')
    for element in root.iter():
        require(element.tag.rsplit('}',1)[-1] in allowed,'SVG','Active or unsupported SVG element')
        for key,value in element.attrib.items():
            key=key.rsplit('}',1)[-1];require(key in attrs,'SVG','Unsupported SVG attribute')
            if key=='href':
                require(value.startswith('data:image/png;base64,'),'SVG','Only embedded PNG preview images')
                try:png_info(base64.b64decode(value.split(',',1)[1],validate=True))
                except (ValueError,TypeError) as e:raise LabError('SVG','Invalid embedded PNG') from e
            elif 'url(' in value:
                require(re.fullmatch(r'url\(#[A-Za-z0-9_-]+\)',value) is not None,'SVG','External SVG reference')
            else:require('://' not in value,'SVG','External SVG reference')

def make_archive(payload: dict[str,bytes],manifest: dict,kind: str,previews: list[str]) -> bytes:
    require('package.json' not in payload and 'checksums.json' not in payload,'PACKAGE_RESERVED','Reserved metadata paths')
    metadata={'package_version':1,'format':'motive-element-lab-review','content_kind':kind,
        **{k:manifest[k] for k in ['id','version','name','author','license']},'manifest':'manifest.json' if kind=='declarative_pack' else 'web-element.json',
        'preview_paths':previews,'payload_files':len(payload),'payload_bytes':sum(map(len,payload.values())),
        'compatibility':{'baseline':BASELINE,'creatorpack_schema':1 if kind=='declarative_pack' else 0,'web_element_schema':1 if kind=='web_element' else 0,
                         'required_capabilities':manifest['requires'] if kind=='declarative_pack' else manifest['capabilities']},
        'review':'required_before_official_installation','trusted_author':False}
    validate(metadata,METADATA)
    files={**payload,'package.json':encode(metadata)}
    files['checksums.json']=encode({'version':1,'algorithm':'sha256','files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(files.items())]})
    require(len(files)<=MAX_ENTRIES and sum(map(len,files.values()))<=MAX_TOTAL,'PACKAGE_LIMIT','Archive budget exceeded')
    buffer=BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        for name,data in sorted(files.items()):
            relative(name);require(0<len(data)<=MAX_FILE,'PACKAGE_LIMIT',name)
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,data)
    return buffer.getvalue()

def package_bundle(bundle: Bundle,license_bytes=None) -> bytes:
    contract(bundle.pack,bundle.rules);estimate(bundle.pack)
    if license_bytes is None:
        require(bundle.pack['license']=='GPL-3.0-or-later','LICENSE_FILE','Provide the full license text for other licenses')
        license_bytes=read_bytes(LAB.parent,'LICENSE')
    payload={'manifest.json':encode(bundle.pack),'rules.json':encode(bundle.rules),'LICENSE':license_bytes}
    for resource in bundle.pack['resources']:
        data=bundle.assets[resource['file_name']];check_asset(resource,data);payload['assets/'+resource['file_name']]=data
    previews=[]
    for scene in bundle.pack['scenes']:
        for orientation in ('horizontal','vertical'):
            name=f'previews/{scene["id"]}-{orientation}.svg';data=svg(bundle,scene,orientation).encode();passive_svg(data);payload[name]=data;previews.append(name)
    return make_archive(payload,bundle.pack,'declarative_pack',previews)

def package_web_bytes(directory: Path) -> bytes:
    manifest,_,assets=validate_web(directory)
    payload={**assets,'web-element.json':encode(manifest),'LICENSE':read_bytes(directory,'LICENSE',1_048_576)}
    return make_archive(payload,manifest,'web_element',[manifest['metadata']['preview']])

def verify_bytes(data: bytes) -> dict:
    require(len(data)<=MAX_TOTAL,'PACKAGE_LIMIT','Archive exceeds 128 MiB')
    files={};seen=set();total=0
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries=archive.infolist();require(0<len(entries)<=MAX_ENTRIES,'PACKAGE_LIMIT','Entry count')
            for info in entries:
                name=relative(info.filename)
                require(name.casefold() not in seen,'PACKAGE_COLLISION',name);seen.add(name.casefold())
                mode=info.external_attr>>16
                require(stat.S_IFMT(mode) in (0,stat.S_IFREG) and not mode&0o111 and not info.is_dir(),'PACKAGE_TYPE','Regular nonexecutable files only')
                require(not info.flag_bits&1 and info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'PACKAGE_TYPE','Unsupported encryption/compression')
                require(0<info.file_size<=MAX_FILE and info.file_size<=max(1,info.compress_size)*100,'PACKAGE_LIMIT','File size or compression ratio')
                total+=info.file_size;require(total<=MAX_TOTAL,'PACKAGE_LIMIT','Total expanded bytes')
                with archive.open(info) as stream:
                    content=stream.read(info.file_size+1)
                    require(len(content)==info.file_size and not stream.read(1),'PACKAGE_LIMIT','Expanded length mismatch')
                files[name]=content
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as e:raise LabError('PACKAGE_ZIP',str(e)) from e
    require({'manifest.json','web-element.json'}&files.keys() and {'checksums.json','package.json','LICENSE'}<=files.keys(),'PACKAGE_FILES','Missing metadata')
    metadata=loads(files['package.json']);validate(metadata,METADATA)
    checks=loads(files['checksums.json']);validate(checks,CHECKSUMS)
    inventory={f['path']:f for f in checks['files']}
    require(len(inventory)==len(checks['files']) and set(inventory)==files.keys()-{'checksums.json'},'PACKAGE_INVENTORY','Exact checksum inventory required')
    for name,item in inventory.items():
        require(item['bytes']==len(files[name]) and item['sha256']==hashlib.sha256(files[name]).hexdigest(),'PACKAGE_HASH',name)
    payload={k:v for k,v in files.items() if k not in ('package.json','checksums.json')}
    require(metadata['payload_files']==len(payload) and metadata['payload_bytes']==sum(map(len,payload.values())),'PACKAGE_METADATA','Payload counts differ')
    require(len(files['LICENSE'])>100,'LICENSE_FILE','Full license required')
    require(metadata['manifest'] in files,'PACKAGE_MANIFEST','Declared manifest missing')
    manifest=loads(files[metadata['manifest']])
    require(all(metadata[k]==manifest.get(k) for k in ('id','version','name','author','license')),'PACKAGE_METADATA','Identity differs')
    for preview in metadata['preview_paths']:require(preview in files,'PACKAGE_PREVIEW',preview)
    if metadata['content_kind']=='declarative_pack':
        require(metadata['manifest']=='manifest.json' and 'rules.json' in files,'PACKAGE_KIND','Native contract required')
        rules=loads(files['rules.json']);report=contract(manifest,rules);report['budget']=estimate(manifest)
        allowed={'manifest.json','rules.json','LICENSE','package.json','checksums.json'}|set(metadata['preview_paths'])
        for r in manifest['resources']:
            name='assets/'+r['file_name'];require(name in files,'PACKAGE_RESOURCE',name);check_asset(r,files[name]);allowed.add(name)
        require(set(files)==allowed,'PACKAGE_EXTRA','Undeclared native files')
        for preview in metadata['preview_paths']:
            require(preview.startswith('previews/') and preview.endswith('.svg'),'PACKAGE_PREVIEW','Passive SVG preview required');passive_svg(files[preview])
        require(metadata['compatibility']['creatorpack_schema']==1 and metadata['compatibility']['web_element_schema']==0 and
                metadata['compatibility']['required_capabilities']==manifest['requires'],'PACKAGE_COMPATIBILITY','Native compatibility mismatch')
    else:
        require(metadata['manifest']=='web-element.json','PACKAGE_KIND','Web contract required');validate(manifest,WEB)
        expected={'web-element.json','LICENSE','package.json','checksums.json'}|{a['path'] for a in manifest['assets']}
        require(set(files)==expected,'PACKAGE_EXTRA','Undeclared web files')
        # Write only to a private, newly created lab temp directory after all ZIP/path gates.
        # This is validation staging, never an installation or execution of package code.
        scratch=LAB/'.scratch';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            root=Path(tmp)
            for name,content in payload.items():
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
            _,report,_=validate_web(root)
        require(metadata['compatibility']['creatorpack_schema']==0 and metadata['compatibility']['web_element_schema']==1 and
                metadata['compatibility']['required_capabilities']==manifest['capabilities'],'PACKAGE_COMPATIBILITY','Web compatibility mismatch')
    return {'status':'PASS','format':'experimental_review_package','content_kind':metadata['content_kind'],'id':manifest['id'],
            'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'files':len(files),'integrity_verified':True,'creator_identity_verified':False,
            'installed':False,'contract':report}

def package(directory: Path,output: Path,web=False) -> dict:
    require(not output.exists(),'OUTPUT_EXISTS',str(output))
    require(output.suffix==('.motiveweb' if web else '.motivepack'),'PACKAGE_EXTENSION','Keep declarative and web content distinct')
    if web:data=package_web_bytes(directory)
    else:
        from modular import load_pack
        data=package_bundle(load_pack(directory),read_bytes(directory,'LICENSE',1_048_576))
    report=verify_bytes(data);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as file:file.write(data)
    return report

def verify_package(path: Path) -> dict:
    report=verify_bytes(read_bytes(path.parent,path.name,MAX_TOTAL))
    require(path.suffix==('.motiveweb' if report['content_kind']=='web_element' else '.motivepack'),'PACKAGE_EXTENSION','Content type and extension disagree')
    return report
