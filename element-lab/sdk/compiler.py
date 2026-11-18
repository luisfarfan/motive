"""Declarative authoring compiler. Produces data; never executes audiovisual work."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path
from common import LabError, encode, read_bytes, read_json, require, validate, write_json
from schemas import ELEMENT
from contracts import check_asset, config, contract, estimate

@dataclass
class Bundle:
    pack: dict
    rules: dict
    assets: dict[str, bytes]
    report: dict

def symbol(prefix: str, local: str) -> str:
    full = prefix+'-'+local
    return full if len(full) <= 64 else full[:50]+'-'+hashlib.sha256(full.encode()).hexdigest()[:12]

def unique(items: list, label: str) -> dict:
    result = {x['id']:x for x in items}
    require(len(result) == len(items), 'DUPLICATE', label)
    return result

def property_value(value, spec: dict, label: str) -> None:
    kind = spec['type']
    schema = {'type':'integer' if kind == 'color' else kind}
    if kind in ('integer','number','color'):
        schema.update(minimum=spec.get('minimum',0 if kind == 'color' else -4096),
                      maximum=spec.get('maximum',0xffffff if kind == 'color' else 3600000))
        require(schema['minimum'] <= schema['maximum'], 'PROPERTY_SCHEMA', label)
    if kind == 'string':
        schema['maxLength'] = spec.get('max_length',4096)
    validate(value,schema,label)

def apply_values(doc: dict, values: dict, variant: str | None) -> dict:
    doc = deepcopy(doc)
    props = unique(doc['properties'], 'property IDs'); variants = unique(doc['variants'], 'variant IDs')
    overrides = {}
    for v in variants.values():
        require(v['properties'].keys() <= props.keys(), 'PROPERTY_UNKNOWN', v['id'])
        for key,value in v['properties'].items():
            property_value(value,props[key]['value'],key)
    if variant:
        require(variant in variants, 'VARIANT_UNKNOWN', variant)
        overrides.update(variants[variant]['properties'])
    require(type(values) is dict and values.keys() <= props.keys(), 'PROPERTY_UNKNOWN', 'Unknown property override')
    overrides.update(values)
    tables = {'node':unique(doc['nodes'],'nodes'),'layout':unique(doc['layers'],'layers'),
              'animation':unique(doc['animations'],'animations')}
    occupied = set()
    for p in props.values():
        property_value(p['value']['default'],p['value'],p['id'])
        value = overrides.get(p['id'],p['value']['default']); property_value(value,p['value'],p['id'])
        p['value']['default'] = value
        for binding in p['bindings']:
            scope,key,field = binding['scope'],binding['ref'],binding['field']
            token = (scope,key,field)
            require(token not in occupied, 'PROPERTY_CONFLICT', f'{token}: multiple writers')
            occupied.add(token)
            require(key in tables[scope], 'PROPERTY_REFERENCE', key)
            target = tables[scope][key]
            if scope == 'node':
                require(target['type'] == 'primitive' and not field.startswith(('horizontal.','vertical.')),
                        'PROPERTY_TARGET', field)
                target = target['native']
            if scope == 'layout':
                require(field.startswith(('horizontal.','vertical.')), 'PROPERTY_TARGET', field)
            if scope == 'animation':
                require(field in ('duration_ms','distance','scale_from'), 'PROPERTY_TARGET', field)
            parts = field.split('.')
            for part in parts[:-1]:
                require(part in target and isinstance(target[part],dict), 'PROPERTY_TARGET', field)
                target = target[part]
            require(parts[-1] in target, 'PROPERTY_TARGET', field)
            target[parts[-1]] = value
    return doc

def graph(doc: dict) -> list[str]:
    nodes = unique(doc['nodes'],'node IDs'); seen, visiting, order = set(), set(), []
    def visit(key,depth=0):
        require(depth <= 32, 'GRAPH_DEPTH', key)
        require(key in nodes, 'REFERENCE', f'Missing node {key}')
        require(key not in visiting, 'CYCLE', f'Cycle at {key}')
        if key in seen:
            return
        visiting.add(key); node = nodes[key]
        if node['type'] == 'composed':
            require(len(set(node['children'])) == len(node['children']), 'DUPLICATE', 'Duplicate child reference')
            for child in node['children']:
                visit(child,depth+1)
        visiting.remove(key); seen.add(key); order.append(key)
    # Check all nodes, including disconnected cycles, then reject unused definitions.
    visit(doc['root']); reachable = seen.copy()
    for key in nodes:
        visit(key)
    require(reachable == set(nodes), 'UNREACHABLE', 'Every node must belong to the selected root')
    primitive = {n['id'] for n in nodes.values() if n['type'] == 'primitive'}
    layered = {l['node'] for l in doc['layers']}
    require(layered == primitive, 'LAYER_REFERENCE', 'Every primitive needs a layer; layers may reference only primitives')
    return order

def action_remap(action: dict, sources: dict, layers: dict, scenes: dict) -> dict:
    value = deepcopy(action)
    # This compiler deliberately exposes only existing visual actions.
    allowed = {'show_overlay','hide_overlay','widget','trigger_animated_widget','animate',
               'countdown_start','countdown_reset','select_scene','update_text','sequence'}
    require(value.get('type') in allowed, 'ACTION_UNSUPPORTED', str(value.get('type')))
    for key,table in [('source_id',sources),('layer_id',layers),('scene_id',scenes)]:
        if key in value:
            require(value[key] in table, 'ACTION_REFERENCE', f'{key}: {value[key]}')
            value[key] = table[value[key]]
    if value['type'] == 'sequence':
        require(isinstance(value.get('actions'),list), 'ACTION_SCHEMA', 'Sequence actions required')
        value['actions'] = [action_remap(a,sources,layers,scenes) for a in value['actions']]
    return value

def rule(binding: dict, prefix: str, actions: list) -> dict:
    field = {'manual.button_pressed':'button_id','motive.custom_event':'name','timer.completed':'timer_id'}.get(binding['event_kind'])
    require(not binding['match'] or field is not None, 'EVENT_MATCH', 'Match only supported for button, custom name and timer')
    conditions = [] if not binding['match'] else [{'type':'equals','field':field,'value':{'type':'string','value':binding['match']}}]
    return {'id':symbol(prefix,binding['id']),'enabled':False,'event_kind':binding['event_kind'],'conditions':conditions,
            'actions':actions,'priority':5,'cooldown_ms':1000,'debounce_ms':0,'timeout_ms':15000,
            'busy_policy':'reject','failure_policy':'stop'}

def capabilities(pack: dict) -> list[str]:
    result = { {'image':'image_asset','video':'video_asset'}.get(o['definition']['kind'],o['definition']['kind']) for o in pack['overlays']}
    if pack['animations']: result.add('layer_animation')
    return sorted(result)

def compile_element(path: Path, values: dict | None = None, variant: str | None = None) -> Bundle:
    raw = read_json(path); validate(raw,ELEMENT)
    doc = apply_values(raw,values or {},variant); order = graph(doc)
    nodes = unique(doc['nodes'],'nodes'); layers = unique(doc['layers'],'layers')
    unique(doc['events'],'events'); unique(doc['states'],'states'); unique(doc['resources'],'resources'); unique(doc['dependencies'],'dependencies')
    for dep in doc['dependencies']:
        require(dep['status'] == 'embedded' and dep['id'] in nodes and dep['version'] == doc['version'],
                'DEPENDENCY_UNAVAILABLE', 'v1 dependencies must be embedded nodes at the element version; no registry resolution')
    prefix = doc['id']; scene_id = symbol(prefix,'scene')
    source_ids = {k:symbol(prefix,k) for k in order if nodes[k]['type'] == 'primitive'}
    layer_ids = {k:symbol(prefix,k) for k in layers}
    asset_ids = {r['id']:symbol(prefix,r['id']) for r in doc['resources']}
    assets,resources = {},[]
    for r in doc['resources']:
        data = read_bytes(path.parent,r['path']); basename = Path(r['path']).name
        name = symbol(prefix,Path(basename).stem)+Path(basename).suffix
        descriptor = {k:r[k] for k in ('kind','sha256','bytes','width','height','duration_ms')}
        descriptor.update(id=asset_ids[r['id']],file_name=name)
        check_asset(descriptor,data)
        require(name not in assets, 'ASSET_COLLISION', name)
        assets[name]=data; resources.append(descriptor)
    overlays,used_resources = [],set()
    for key,id_ in source_ids.items():
        d = deepcopy(nodes[key]['native'])
        if 'resource_id' in d:
            require(d['resource_id'] in asset_ids,'ASSET_REFERENCE',d['resource_id'])
            used_resources.add(d['resource_id']); d['resource_id']=asset_ids[d['resource_id']]
        overlays.append({'id':id_,'name':nodes[key]['name'],'definition':d})
    require(used_resources == set(asset_ids),'UNUSED_RESOURCE','Remove unreferenced native resources')
    pack_layers = [{'id':layer_ids[l['id']],'overlay_id':source_ids[l['node']],
                    'horizontal':l['horizontal'],'vertical':l['vertical']} for l in doc['layers']]
    animations = []
    for animation in doc['animations']:
        require(animation['layer_id'] in layer_ids,'ANIMATION_REFERENCE',animation['layer_id'])
        a = deepcopy(animation); a.update(id=symbol(prefix,a['id']),scene_id=scene_id,layer_id=layer_ids[a['layer_id']]); animations.append(a)
    properties = []
    targets = {'text':'text_content','widget.title':'widget_title','widget.subtitle':'widget_subtitle','color':'shape_color'}
    for p in doc['properties']:
        if p['export'] != 'creatorpack_property': continue
        require(len(p['bindings']) == 1,'PROPERTY_EXPORT','v1 properties have one target')
        b = p['bindings'][0]
        require(b['scope']=='node' and b['field'] in targets,'PROPERTY_EXPORT','Only the four native v1 property targets can be exported')
        properties.append({'id':symbol(prefix,p['id']),'label':p['label'],'overlay_id':source_ids[b['ref']],
                           'target':targets[b['field']],'value':{'type':'color' if p['value']['type']=='color' else 'text','value':p['value']['default']}})
    rules = config([rule(b,prefix,[action_remap(a,source_ids,layer_ids,{'$scene':scene_id}) for a in b['actions']]) for b in doc['events']])
    pack = {'schema_version':1,'id':prefix,'version':doc['version'],'name':doc['name'],'author':doc['author'],'license':doc['license'],
            'resources':resources,'scenes':[{'id':scene_id,'name':doc['name'],'layers':pack_layers}],'overlays':overlays,
            'animations':animations,'properties':properties,'events':sorted({b['event_kind'] for b in doc['events']}),
            'rule_ids':[r['id'] for r in rules['rules']],'requires':sorted(set(doc['capabilities']['required'])),
            'budget':{'max_resource_bytes':doc['budget']['max_resource_bytes'],'max_estimated_texture_bytes':doc['budget']['max_texture_bytes'],
                      'max_simultaneous_animations':1 if animations else 0}}
    require(set(capabilities(pack)) <= set(pack['requires']),'CAPABILITY_UNDECLARED','Declare every used primitive/animation capability')
    report = contract(pack,rules)
    stats = estimate(pack)
    require(len(overlays) <= doc['budget']['max_sources'] and len(pack_layers) <= doc['budget']['max_layers'], 'ELEMENT_BUDGET', 'Element budget exceeded')
    require(stats['native_texture_estimate_bytes'] <= doc['budget']['max_texture_bytes'], 'ELEMENT_BUDGET', 'H11 estimate exceeds authored budget')
    report.update(budget=stats,dependency_order=order,unsupported=doc['capabilities']['future'],
                  states=doc['states'],properties={p['id']:p['value']['default'] for p in doc['properties']},
                  authoring_document_sha256=hashlib.sha256(encode(doc)).hexdigest())
    return Bundle(pack,rules,assets,report)

def emit(bundle: Bundle, directory: Path) -> None:
    require(not directory.exists(), 'OUTPUT_EXISTS', f'Refusing to overwrite {directory}; choose a new output')
    # All validation occurs before any output. Directory is a new local review artifact.
    directory.mkdir(parents=True)
    write_json(directory/'manifest.json',bundle.pack); write_json(directory/'rules.json',bundle.rules)
    write_json(directory/'report.json',bundle.report)
    (directory/'assets').mkdir()
    for name,data in bundle.assets.items(): (directory/'assets'/name).write_bytes(data)
