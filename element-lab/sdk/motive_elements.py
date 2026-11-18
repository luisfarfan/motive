#!/usr/bin/env python3
"""Local CLI. Python stdlib + an offline Cargo adapter, no global installation."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from common import LAB, LabError, encode, loads, read_json, require
from compiler import compile_element, emit
from contracts import estimate
from modular import load_pack, select, combine
from preview import render
from templates import create, TEMPLATES

def parser():
    p=argparse.ArgumentParser(description='Motive Elements · offline authoring, never Production')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('capabilities',help='Static source contract baseline, not runtime discovery')
    new=sub.add_parser('new');new.add_argument('output',type=Path);new.add_argument('--template',choices=TEMPLATES,default='lower-third');new.add_argument('--id')
    for name in ('validate','inspect','preview','pack'):
        cmd=sub.add_parser(name);cmd.add_argument('input',type=Path)
        cmd.add_argument('--set',action='append',default=[],metavar='ID=JSON');cmd.add_argument('--variant')
        if name in ('preview','pack'):cmd.add_argument('--output','-o',required=True,type=Path)
    compose=sub.add_parser('compose');compose.add_argument('inputs',nargs='+',type=Path);compose.add_argument('--output','-o',required=True,type=Path)
    compose.add_argument('--id',default='composition');compose.add_argument('--single-scene',action='store_true');compose.add_argument('--occupied',type=Path)
    selection=sub.add_parser('select');selection.add_argument('input',type=Path);selection.add_argument('--scenes',nargs='+');selection.add_argument('--sources',nargs='+');selection.add_argument('--output','-o',required=True,type=Path)
    rehearsal=sub.add_parser('rehearse');rehearsal.add_argument('input',type=Path);rehearsal.add_argument('--events',required=True,type=Path);rehearsal.add_argument('--enable-for-simulation',action='store_true')
    web=sub.add_parser('web-validate');web.add_argument('input',type=Path)
    package=sub.add_parser('package');package.add_argument('input',type=Path);package.add_argument('--output','-o',required=True,type=Path);package.add_argument('--web',action='store_true')
    verify=sub.add_parser('verify-package');verify.add_argument('input',type=Path)
    catalog=sub.add_parser('catalog-validate');catalog.add_argument('input',type=Path)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8776)
    return p

def bundle(path,values=None,variant=None):
    if path.is_dir() and (path/'element.json').exists():path=path/'element.json'
    if path.is_dir():
        require(not values and not variant,'PACK_PROPERTIES','Edit authoring elements before exporting packs')
        return load_pack(path)
    return compile_element(path,values,variant)

def run(args):
    if args.command=='capabilities':
        return {'schema_version':1,'baseline':'6019ad0acac4b52dcf1ebc44f2006406fde533f8',
            'mode':'static_read_only_contract','native':['text','shape','widget','layer_animation','scene_transition','image_asset','video_asset'],
            'asset_bytes_verified':['png'],'unavailable':['browser_source_in_libobs','custom_native_widget','automatic_score_binding','third_party_code_isolation'],
            'limits':{'scenes':8,'sources':16,'layers':32,'video_sources':4,'texture_estimate_bytes':256*1024**2},
            'production_connected':False}
    if args.command=='new':
        path=create(args.template,args.output,args.id);result=compile_element(path)
        return {'created':str(path),'status':result.report['status']}
    if args.command in ('validate','inspect','preview','pack'):
        values={}
        for arg in args.set:
            require('=' in arg,'ARGUMENT','Use --set property=JSON');key,value=arg.split('=',1)
            require(key not in values,'ARGUMENT','Duplicate property override');values[key]=loads(value)
        b=bundle(args.input,values,args.variant)
        if args.command=='pack':emit(b,args.output)
        if args.command=='preview':render(b,args.output)
        return b.report if args.command!='inspect' else {'report':b.report,'manifest':b.pack,'rules':b.rules}
    if args.command=='compose':
        b=combine([bundle(p) for p in args.inputs],args.id,args.single_scene,read_json(args.occupied) if args.occupied else None)
        emit(b,args.output);return b.report
    if args.command=='select':
        b=select(load_pack(args.input),args.scenes,args.sources);emit(b,args.output);return b.report
    if args.command=='web-validate':
        from web_contract import validate_web
        return validate_web(args.input)[1]
    if args.command=='rehearse':
        from contracts import contract
        b=bundle(args.input)
        if args.enable_for_simulation:
            for rule in b.rules['rules']:rule['enabled']=True
        events=read_json(args.events);require(type(events) is list and 0<len(events)<=32,'SIMULATION_INPUT','Choose 1..32 synthetic events')
        result=contract(b.pack,b.rules,events);result['fixture_rules_enabled']=args.enable_for_simulation
        return result
    if args.command in ('package','verify-package'):
        from packaging import package, verify_package
        return package(args.input,args.output,args.web) if args.command=='package' else verify_package(args.input)
    if args.command=='catalog-validate':
        from catalog import validate_catalog
        return validate_catalog(args.input)
    if args.command=='serve':
        from server import serve
        serve(args.port);return {'status':'stopped'}

def main():
    try:
        result=run(parser().parse_args());print(encode(result).decode(),end='')
    except (LabError,OSError,ValueError,KeyError,TypeError) as e:
        print(encode({'status':'FAIL','error':{'code':getattr(e,'code','INPUT_ERROR'),'message':str(e)}}).decode(),file=sys.stderr,end='')
        sys.exit(1)

if __name__=='__main__':main()
