#!/usr/bin/env python3
"""Explicit preset-based agent workflow using the same public CLI; no LLM service."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import LAB,LabError,encode,read_json,require,validate,write_json
from schemas import obj,string,ID

BRIEF=obj({'schema_version':{'const':1},'template':{'const':'community-alert'},'id':ID,
           'name':string(80),'description':string(1024),'properties':{'type':'object','maxProperties':32}})

def author(brief_path: Path,output: Path):
    brief=read_json(brief_path);validate(brief,BRIEF)
    require(not output.exists(),'OUTPUT_EXISTS','Choose a new authoring output')
    def cli(*args):
        result=subprocess.run([sys.executable,str(LAB/'sdk/motive_elements.py'),*map(str,args)],capture_output=True,text=True)
        require(result.returncode==0,'CLI_STEP',result.stderr)
        return json.loads(result.stdout)
    capabilities=cli('capabilities')
    cli('new',output/'element','--template',brief['template'],'--id',brief['id'])
    source=output/'element/element.json';doc=read_json(source)
    doc['name']=brief['name'];doc['metadata']['description']=brief['description']
    props={p['id']:p for p in doc['properties']}
    require(brief['properties'].keys()<=props.keys(),'PROPERTY_UNKNOWN','Brief contains an unknown property')
    for key,value in brief['properties'].items():props[key]['value']['default']=value
    # Trusted Motive provider events are only a declared future binding here.
    trigger=next(e for e in doc['events'] if e['id']=='trigger')
    trigger['event_kind']='viewer.donation';trigger['match']=''
    write_json(source,doc)
    validation=cli('validate',source)
    cli('preview',source,'-o',output/'preview')
    cli('pack',source,'-o',output/'candidate')
    composed=cli('compose',source,LAB/'native-elements/lower-third','--single-scene','--id','donation-and-lower','-o',output/'composition')
    archive=output/(brief['id']+'.motivepack')
    cli('package',output/'candidate','-o',archive)
    verified=cli('verify-package',archive)
    report={'status':'PASS','mode':'ordinary_cli_authoring','template':brief['template'],
            'element_id':brief['id'],'properties':validation['properties'],'capabilities_baseline':capabilities['baseline'],
            'composed_budget':composed['budget'],'package':verified,'output':str(output),
            'installed':False,'provider_connected':False,'native_render_verified':False}
    write_json(output/'workflow-report.json',report)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('brief',type=Path);parser.add_argument('--output',type=Path,required=True)
    try:
        args=parser.parse_args();print(encode(author(args.brief,args.output)).decode(),end='')
    except (LabError,OSError,ValueError,KeyError,TypeError) as e:
        print(encode({'status':'FAIL','error':{'code':getattr(e,'code','INPUT_ERROR'),'message':str(e)}}).decode(),file=sys.stderr,end='');sys.exit(1)
