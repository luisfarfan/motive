#!/usr/bin/env python3
"""Refresh deterministic Web Element inventory after editing original local sources."""
import sys,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,read_bytes,write_json
from web_contract import validate_web
root=LAB/'web-elements/goal-celebration'
(root/'runtime.mjs').write_bytes(read_bytes(LAB,'web-elements/runtime-prototype/runtime.mjs'))
(root/'LICENSE').write_bytes(read_bytes(LAB.parent,'LICENSE'))
string=lambda default,max_length=60:{'type':'string','default':default,'max_length':max_length}
integer=lambda default,lo,hi:{'type':'integer','default':default,'minimum':lo,'maximum':hi}
properties={'title':string('GOOOOL',12),'team':string('Club del Puerto'),'home':integer(2,0,99),'away':integer(1,0,99),
 'accent':{'type':'color','default':'#f5c27c'},'background':{'type':'color','default':'#222429'},'holdMs':integer(2500,500,10000),
 'reducedMotion':{'type':'boolean','default':False},'testMode':{'type':'boolean','default':True}}
fields={k:{p:v for p,v in properties[k].items() if p!='default'} for k in ['team','home','away']}
assets=[]
for name,media in [('index.html','text/html'),('goal.css','text/css'),('goal.mjs','text/javascript'),('runtime.mjs','text/javascript'),('preview.svg','image/svg+xml')]:
 data=read_bytes(root,name);assets.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'media_type':media})
manifest={'schema_version':1,'kind':'web_element','id':'goal-celebration-web','version':'1.0.0','name':'Goal Celebration — Web Edition','author':'Motive contributors','license':'GPL-3.0-or-later',
 'entry':'index.html','assets':assets,'viewport':{'horizontal':{'width':960,'height':540},'vertical':{'width':540,'height':960}},'requested_fps':30,
 'properties':properties,'events':{'goal.scored':{'fields':fields}},'states':['ready','active','cancelled','error','disposed'],
 'capabilities':['html','css','javascript'],'permissions':{k:False for k in ['network','storage','devices','clipboard','production','mcp','shell']},
 'limits':{'max_message_bytes':4096,'events_per_second':8,'max_asset_bytes':1048576,'max_total_bytes':4194304,'max_active_ms':15000,'requested_memory_mib':128},
 'lifecycle':{'autostart':False,'on_hidden':'cancel','on_error':'stop','on_dispose':'cleanup'},'dependencies':[],
 'metadata':{'description':'Original geometric goal celebration with synthetic events and reduced motion','category':'celebration','tags':['goal','sport','original'],
 'preview':'preview.svg','integration':'authoring_prototype_only'}}
write_json(root/'web-element.json',manifest)
_,report,_=validate_web(root);write_json(LAB/'evidence/H-web-contract.json',report)
