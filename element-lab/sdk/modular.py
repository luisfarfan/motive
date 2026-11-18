"""Selection, dependency closure and bounded merges of CreatorPack v1 proposals."""
from copy import deepcopy
from pathlib import Path
from common import read_json, require
from compiler import Bundle, capabilities, symbol
from contracts import check_assets, config, contract, estimate

VISUAL_ACTIONS={'show_overlay','hide_overlay','widget','trigger_animated_widget','animate',
                'countdown_start','countdown_reset','select_scene','update_text','sequence'}

def unsupported_actions(action):
    result=[] if action['type'] in VISUAL_ACTIONS else [action['type']]
    if action['type']=='sequence':
        for child in action['actions']:result+=unsupported_actions(child)
    return result

def load_pack(directory: Path) -> Bundle:
    pack=read_json(directory/'manifest.json')
    rules=read_json(directory/'rules.json') if (directory/'rules.json').exists() else config()
    report=contract(pack,rules);report['budget']=estimate(pack)
    assets=check_assets(pack,directory)
    return Bundle(pack,rules,assets,report)

def action_refs(action: dict) -> set[tuple[str,str]]:
    refs={(key,action[key]) for key in ('source_id','scene_id','layer_id') if key in action}
    if action['type']=='sequence':
        for child in action['actions']:refs |= action_refs(child)
    return refs

def action_caps(action: dict) -> set[str]:
    result=set()
    if action['type'] in ('animate','trigger_animated_widget'):result.add('layer_animation')
    if action['type']=='select_scene':result.add('scene_transition')
    if action['type']=='sequence':
        for child in action['actions']:result |= action_caps(child)
    return result

def finalize(pack: dict,rules: dict,assets: dict,selection=None,occupied=None) -> Bundle:
    pack['events']=sorted({r['event_kind'] for r in rules['rules']})
    pack['rule_ids']=[r['id'] for r in rules['rules']]
    requires=set(capabilities(pack))
    for r in rules['rules']:
        for a in r['actions']:requires |= action_caps(a)
    pack['requires']=sorted(requires)
    pack['budget']={'max_resource_bytes':sum(r['bytes'] for r in pack['resources']),
                    'max_estimated_texture_bytes':256*1024**2,
                    'max_simultaneous_animations':1 if 'layer_animation' in requires else 0}
    report=contract(pack,rules);report['budget']=estimate(pack,occupied)
    report['selection']=selection or {};report['rules_start_disarmed']=True
    return Bundle(pack,rules,assets,report)

def select(bundle: Bundle,scene_ids: list[str] | None=None,source_ids: list[str] | None=None) -> Bundle:
    pack=deepcopy(bundle.pack);rules=deepcopy(bundle.rules)
    available_scenes={s['id'] for s in pack['scenes']};available_sources={o['id'] for o in pack['overlays']}
    scenes=set(available_scenes if scene_ids is None else scene_ids)
    sources=set(available_sources if source_ids is None else source_ids)
    require(bool(scenes) and bool(sources) and scenes <= available_scenes and sources <= available_sources,'SELECTION','Unknown or empty scene/source selection')
    pack['scenes']=[s for s in pack['scenes'] if s['id'] in scenes]
    for scene in pack['scenes']:scene['layers']=[l for l in scene['layers'] if l['overlay_id'] in sources]
    pack['scenes']=[s for s in pack['scenes'] if s['layers']]
    require(bool(pack['scenes']),'SELECTION','No selected source occurs in selected scenes')
    used={l['overlay_id'] for s in pack['scenes'] for l in s['layers']}
    require(source_ids is None or sources <= used,'SELECTION','Selected source has no layer in selected scenes')
    pack['overlays']=[o for o in pack['overlays'] if o['id'] in used]
    resources={o['definition']['resource_id'] for o in pack['overlays'] if 'resource_id' in o['definition']}
    pack['resources']=[r for r in pack['resources'] if r['id'] in resources]
    kept_scenes={s['id'] for s in pack['scenes']};layers={l['id'] for s in pack['scenes'] for l in s['layers']}
    pack['animations']=[a for a in pack['animations'] if a['scene_id'] in kept_scenes and a['layer_id'] in layers]
    pack['properties']=[p for p in pack['properties'] if p['overlay_id'] in used]
    refs={('source_id',x) for x in used}|{('scene_id',x) for x in kept_scenes}|{('layer_id',x) for x in layers}
    dropped=[];kept=[]
    for rule in rules['rules']:
        missing=set().union(*(action_refs(a) for a in rule['actions']))-refs
        unsupported=[t for a in rule['actions'] for t in unsupported_actions(a)]
        if unsupported:dropped.append({'id':rule['id'],'reason':'unbound_action_semantics','actions':unsupported})
        elif missing:dropped.append({'id':rule['id'],'reason':'references_outside_selection','references':sorted(missing)})
        else:rule['enabled']=False;kept.append(rule)
    rules['rules']=kept
    assets={r['file_name']:bundle.assets[r['file_name']] for r in pack['resources']}
    audit={'selected_scenes':sorted(kept_scenes),'selected_sources':sorted(used),'removed':{},'removed_rules':dropped}
    for key in ('scenes','overlays','resources','animations','properties'):
        audit['removed'][key]=sorted({x['id'] for x in bundle.pack[key]}-{x['id'] for x in pack[key]})
    return finalize(pack,rules,assets,audit)

def combine(bundles: list[Bundle],id_: str='composition',single_scene: bool=False,occupied=None) -> Bundle:
    require(0 < len(bundles) <= 16,'COMPOSE_LIMIT','Choose 1..16 inputs')
    require(all(not b.rules['variables'] for b in bundles),'COMPOSE_VARIABLES','Variables need explicit migration; this adapter rejects them')
    require(all(not unsupported_actions(a) for b in bundles for r in b.rules['rules'] for a in r['actions']),
            'COMPOSE_ACTION','Only visual actions have namespace semantics; select first to review discarded rules')
    # Distinct licenses need a reviewed composite license policy, not a guessed replacement.
    licenses={b.pack['license'] for b in bundles}
    require(len(licenses)==1,'LICENSE_COMBINATION','Mixed licenses require review; no silent relicensing')
    out={'schema_version':1,'id':id_,'version':'1.0.0','name':'Motive · '+id_,'author':'Motive contributors',
         'license':next(iter(licenses)),'resources':[],'scenes':[],'overlays':[],'animations':[],'properties':[]}
    rules=[];assets={};dedup={};audit=[];layer_order=0
    single={'id':symbol(id_,'scene'),'name':'Composed elements','layers':[]}
    for index,bundle in enumerate(bundles):
        p=deepcopy(bundle.pack);prefix=f'i{index+1}-{p["id"]}'
        source={o['id']:symbol(prefix,o['id']) for o in p['overlays']}
        scene={s['id']:single['id'] if single_scene else symbol(prefix,s['id']) for s in p['scenes']}
        layer={l['id']:symbol(prefix,l['id']) for s in p['scenes'] for l in s['layers']}
        resource={}
        for r in p['resources']:
            identity=tuple(r[k] for k in ('sha256','bytes','kind','width','height','duration_ms'))
            if identity not in dedup:
                oldname=r['file_name'];newid=symbol(prefix,r['id']);newname=newid+Path(oldname).suffix
                r.update(id=newid,file_name=newname);out['resources'].append(r);assets[newname]=bundle.assets[oldname]
                dedup[identity]=newid
        # Map every alias, including identical resources with different source IDs.
        for r in bundle.pack['resources']:
            resource[r['id']]=dedup[tuple(r[k] for k in ('sha256','bytes','kind','width','height','duration_ms'))]
        for o in p['overlays']:
            o['id']=source[o['id']]
            if 'resource_id' in o['definition']:o['definition']['resource_id']=resource[o['definition']['resource_id']]
        out['overlays']+=p['overlays']
        for s in p['scenes']:
            s['id']=scene[s['id']]
            # Keep both orientations' relative order while assigning disjoint ranges.
            if single_scene:
                for orient in ('horizontal','vertical'):
                    for rank,l in enumerate(sorted(s['layers'],key=lambda x:x[orient]['order'])):l[orient]['order']=layer_order+rank
            for l in s['layers']:l.update(id=layer[l['id']],overlay_id=source[l['overlay_id']])
            if single_scene:single['layers']+=s['layers'];layer_order+=len(s['layers'])
            else:out['scenes'].append(s)
        for a in p['animations']:a.update(id=symbol(prefix,a['id']),scene_id=scene[a['scene_id']],layer_id=layer[a['layer_id']])
        out['animations']+=p['animations']
        for prop in p['properties']:prop.update(id=symbol(prefix,prop['id']),overlay_id=source[prop['overlay_id']])
        out['properties']+=p['properties']
        def remap(action):
            a=deepcopy(action)
            for key,table in [('source_id',source),('scene_id',scene),('layer_id',layer)]:
                if key in a:a[key]=table[a[key]]
            if a['type']=='sequence':a['actions']=[remap(x) for x in a['actions']]
            return a
        matches=[]
        for r in deepcopy(bundle.rules['rules']):
            r['id']=symbol(prefix,r['id']);r['enabled']=False;r['actions']=[remap(a) for a in r['actions']]
            for c in r['conditions']:
                if c.get('type')=='equals' and c.get('field') in ('button_id','name') and c['value']['type']=='string':
                    before=c['value']['value'];c['value']['value']=symbol(prefix,before);matches.append({'from':before,'to':c['value']['value']})
            rules.append(r)
        audit.append({'pack':bundle.pack['id'],'sources':source,'scenes':scene,'layers':layer,'resources':resource,'trigger_names':matches,
                      'upstream_selection':bundle.report.get('selection')})
    if single_scene:out['scenes']=[single]
    return finalize(out,config(rules),assets,{'inputs':audit,'single_scene':single_scene},occupied)
