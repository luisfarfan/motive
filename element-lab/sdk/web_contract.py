"""Strict Web Element authoring contract. No native host or sandbox claim."""
import hashlib
from pathlib import Path
import re
from common import LAB, read_json, read_bytes, relative, require, validate, write_json
from schemas import obj,arr,string,number,ID,VERSION,LICENSE,PATH,HASH

FIELD=obj({'type':{'enum':['string','color','integer','number','boolean']},'default':{},
           'minimum':number(-1e6,1e6),'maximum':number(-1e6,1e6),'max_length':number(1,4096,True),
           'options':arr(string(80),16)},('default','minimum','maximum','max_length','options'))
WEB=obj({'schema_version':{'const':1},'kind':{'const':'web_element'},'id':ID,'version':VERSION,'name':string(80),'author':string(128),'license':LICENSE,
    'entry':PATH,'assets':arr(obj({'path':PATH,'sha256':HASH,'bytes':number(1,4*1024**2,True),
        'media_type':{'enum':['text/html','text/css','text/javascript','image/svg+xml','image/png']}}),64,1),
    'viewport':obj({'horizontal':obj({'width':{'const':960},'height':{'const':540}}),'vertical':obj({'width':{'const':540},'height':{'const':960}})}),
    'requested_fps':{'enum':[30,60]},'properties':{'type':'object','additionalProperties':FIELD,'maxProperties':32},
    'events':{'type':'object','additionalProperties':obj({'fields':{'type':'object','additionalProperties':FIELD,'maxProperties':16}}),'maxProperties':16},
    'states':arr({'enum':['ready','active','cancelled','error','disposed']},5,5),
    'capabilities':arr({'enum':['html','css','javascript','svg','canvas']},5,1),
    'permissions':obj({key:{'const':False} for key in ['network','storage','devices','clipboard','production','mcp','shell']}),
    'limits':obj({'max_message_bytes':number(256,16384,True),'events_per_second':number(1,60,True),
        'max_asset_bytes':number(1,4*1024**2,True),'max_total_bytes':number(1,16*1024**2,True),'max_active_ms':number(1000,30000,True),
        'requested_memory_mib':number(16,256,True)}),
    'lifecycle':obj({'autostart':{'const':False},'on_hidden':{'const':'cancel'},'on_error':{'const':'stop'},'on_dispose':{'const':'cleanup'}}),
    'dependencies':arr(obj({'id':ID,'version':VERSION,'license':LICENSE,'asset':PATH}),16),
    'metadata':obj({'description':string(1024),'category':string(64),'tags':arr(string(32),16),'preview':PATH,
                    'integration':{'const':'authoring_prototype_only'}})})

def validate_field(value,spec,where):
    kind=spec['type']
    if kind in ('string','color'):
        s={'type':'string','maxLength':spec.get('max_length',160)}
        if kind=='color':s['pattern']='#[0-9a-fA-F]{6}'
    elif kind=='boolean':s={'type':'boolean'}
    else:
        require('minimum' in spec and 'maximum' in spec and spec['minimum'] <= spec['maximum'],'WEB_PROPERTY',where)
        s={'type':kind,'minimum':spec['minimum'],'maximum':spec['maximum']}
    if 'options' in spec:s['enum']=spec['options']
    validate(value,s,where)

def validate_web(directory: Path) -> tuple[dict,dict,dict]:
    manifest=read_json(directory/'web-element.json');validate(manifest,WEB)
    require(len(set(manifest['states']))==5,'WEB_STATES','All lifecycle states required')
    for key,spec in manifest['properties'].items():
        require(re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,47}',key) is not None and key not in ('constructor','prototype','__proto__'),'WEB_PROPERTY',key)
        require('default' in spec,'WEB_PROPERTY',key);validate_field(spec['default'],spec,key)
    for name,event in manifest['events'].items():
        require(re.fullmatch('[a-z][a-z0-9_.-]{0,63}',name) is not None,'WEB_EVENT',name)
        for key,spec in event['fields'].items():
            require(re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,47}',key) is not None and key not in ('constructor','prototype','__proto__'),'WEB_EVENT',key)
            if spec['type'] in ('number','integer'):require('minimum' in spec and 'maximum' in spec,'WEB_EVENT',key)
    files={};case=set()
    for item in manifest['assets']:
        name=relative(item['path']);require(name.casefold() not in case,'WEB_ASSET_COLLISION',name);case.add(name.casefold())
        data=read_bytes(directory,name,manifest['limits']['max_asset_bytes'])
        require(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],'WEB_ASSET_HASH',name)
        ext=Path(name).suffix.lower();types={'.html':'text/html','.css':'text/css','.js':'text/javascript','.mjs':'text/javascript','.svg':'image/svg+xml','.png':'image/png'}
        require(types.get(ext)==item['media_type'],'WEB_ASSET_TYPE',name)
        if ext!='.png':
            text=data.decode('utf-8')
            # Review gate for supplied source; obfuscated JavaScript is not proven safe.
            require(not re.search(r'https?://|wss?://|file://|/Users/|/etc/',text,re.I),'WEB_EXTERNAL_REFERENCE',name)
            require('sourceMappingURL=' not in text,'WEB_SOURCE_MAP','Package compiled JS without undeclared maps')
        files[name]=data
    require(manifest['entry'] in files and manifest['entry'].endswith('.html'),'WEB_ENTRY','Declared HTML entry required')
    require(manifest['metadata']['preview'] in files,'WEB_PREVIEW','Declared preview required')
    require(sum(map(len,files.values())) <= manifest['limits']['max_total_bytes'],'WEB_BUDGET','Total assets exceed limit')
    for dependency in manifest['dependencies']:require(dependency['asset'] in files,'WEB_DEPENDENCY',dependency['id'])
    return manifest,{'status':'PASS','mode':'web_authoring_contract','assets':len(files),'bytes':sum(map(len,files.values())),
                     'native_host_verified':False,'process_sandbox_verified':False,'rss_limit_enforced':False,
                     'source_review':'literal URL/path gate only; not proof against obfuscated code'},files

if __name__=='__main__':write_json(LAB/'element-spec/web-element.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema',**WEB})
