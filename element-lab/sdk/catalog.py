"""Offline catalogue metadata and integrity verification; no account/backend."""
import hashlib
from io import BytesIO
from pathlib import Path
import zipfile
from common import LAB, read_json, read_bytes, relative, require, validate, write_json
from schemas import obj,arr,string,VERSION,LICENSE,HASH,PATH
from packaging import verify_bytes

ENTRY=obj({'id':string(64),'version':VERSION,'kind':{'enum':['element','pack']},'mode':{'enum':['native','web']},
    'name':string(128),'description':string(1024),'author':obj({'id':string(64),'name':string(128),'identity':{'const':'unverified'}}),
    'category':string(64),'tags':arr(string(32),16),'license':LICENSE,'required_capabilities':arr(string(64),32),
    'compatibility':obj({'baseline_source_commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'element_schema':{'const':1},
                         'creatorpack_schema':{'enum':[0,1]},'web_element_schema':{'enum':[0,1]},'official_installation':{'const':'pending'}}),
    'package':obj({'path':PATH,'sha256':HASH,'bytes':{'type':'integer','minimum':1,'maximum':128*1024**2},
                   'content_kind':{'enum':['declarative_pack','web_element']}}),
    'preview':obj({'package_path':PATH,'sha256':HASH,'media_type':{'const':'image/svg+xml'}}),
    'update':obj({'channel':{'const':'local_files'},'replaces_versions':arr(VERSION,16),'review_required':{'const':True}})})
CATALOG=obj({'schema_version':{'const':1},'kind':{'const':'motive_local_catalog'},'entries':arr(ENTRY,128,1)})

def validate_catalog(path: Path):
    doc=read_json(path);validate(doc,CATALOG);seen=set();reports=[]
    for e in doc['entries']:
        key=(e['id'],e['version']);require(key not in seen,'CATALOG_DUPLICATE',str(key));seen.add(key)
        pkg=e['package'];data=read_bytes(path.parent,relative(pkg['path']),128*1024**2)
        require(len(data)==pkg['bytes'] and hashlib.sha256(data).hexdigest()==pkg['sha256'],'CATALOG_INTEGRITY',e['id'])
        report=verify_bytes(data)
        require(report['content_kind']==pkg['content_kind'] and report['id']==e['id'],'CATALOG_IDENTITY',e['id'])
        require((e['mode']=='web')==(pkg['content_kind']=='web_element'),'CATALOG_KIND',e['id'])
        with zipfile.ZipFile(BytesIO(data)) as z:
            from common import loads
            metadata=loads(z.read('package.json'));internal=metadata['compatibility']
            require(all(e[k]==metadata[k] for k in ('version','name','license')) and e['author']['name']==metadata['author'],'CATALOG_IDENTITY',e['id'])
            require(e['required_capabilities']==internal['required_capabilities'] and
                    e['compatibility']['baseline_source_commit']==internal['baseline'] and
                    all(e['compatibility'][k]==internal[k] for k in ('creatorpack_schema','web_element_schema')),'CATALOG_COMPATIBILITY',e['id'])
            preview=e['preview']['package_path'];require(preview in metadata['preview_paths'],'CATALOG_PREVIEW',preview)
            require(hashlib.sha256(z.read(preview)).hexdigest()==e['preview']['sha256'],'CATALOG_PREVIEW',preview)
        reports.append({'id':e['id'],'version':e['version'],'integrity':'PASS','author_identity':'unverified'})
    return {'status':'PASS','mode':'offline_catalog','entries':reports,'installed':False}

if __name__=='__main__':write_json(LAB/'marketplace-contract/catalog.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema',**CATALOG})
