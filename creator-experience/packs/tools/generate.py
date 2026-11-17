#!/usr/bin/env python3
"""Original Creator Packs + reproducible design previews. No Motive/OBS invocation.
Uses Python stdlib and Apple's AppKit via Swift. GPL-3.0-or-later.
"""
from pathlib import Path
import base64, hashlib, html, json, math, subprocess
ROOT = Path(__file__).resolve().parents[1]
JOBS=[]
def write_json(path, data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def rgb(c): return int(c.lstrip('#'),16)
def hexcolor(c): return f'#{c:06x}'
def rect(x,y,w,h,fill,**kw): return dict(kind='rect',x=x,y=y,width=w,height=h,fill=fill,**kw)
def poly(pts,fill='none',stroke='none',sw=1,closed=True,**kw):return dict(kind='poly',points=pts,fill=fill,stroke=stroke,stroke_width=sw,closed=closed,**kw)
def line(x1,y1,x2,y2,c,sw=1,**kw):return poly([[x1,y1],[x2,y2]],stroke=c,sw=sw,closed=False,**kw)
def txt(text,x,y,size,fill,font='Helvetica'):return dict(kind='text',text=text,x=x,y=y,size=size,fill=fill,font=font)
def ellipse(x,y,w,h,fill,**kw):return dict(kind='ellipse',x=x,y=y,width=w,height=h,fill=fill,**kw)
def svg(nodes,w,h,title):
 out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img"><title>{html.escape(title)}</title>']
 for n in nodes:
  kind=n['kind'];a=f' opacity="{n.get("opacity",1)}"';fill=n.get('fill','none');stroke=n.get('stroke','none');sw=n.get('stroke_width',1)
  style=f' fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
  if kind=='rect':out.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["width"]}" height="{n["height"]}"{style}{a}/>')
  elif kind=='ellipse':out.append(f'<ellipse cx="{n["x"]+n["width"]/2}" cy="{n["y"]+n["height"]/2}" rx="{n["width"]/2}" ry="{n["height"]/2}"{style}{a}/>')
  elif kind=='poly':
   tag='polygon' if n.get('closed') else 'polyline';pts=' '.join(f'{x},{y}' for x,y in n['points']);out.append(f'<{tag} points="{pts}"{style}{a}/>')
  elif kind=='text':out.append(f'<text x="{n["x"]}" y="{n["y"]+n["size"]*.8}" fill="{fill}" font-family="{n["font"]},sans-serif" font-size="{n["size"]}"{a}>{html.escape(n["text"])}</text>')
  elif kind=='image':
   uri='data:image/png;base64,'+base64.b64encode(Path(n['path']).read_bytes()).decode()
   out.append(f'<image href="{uri}" x="{n["x"]}" y="{n["y"]}" width="{n["width"]}" height="{n["height"]}"{a}/>')
 out.append('</svg>');return '\n'.join(out)+'\n'
def render_job(nodes,w,h,path):JOBS.append(dict(nodes=nodes,width=w,height=h,output=str(path)))
def render():
 if not JOBS:return
 jobs=ROOT/'tools'/'render-jobs.json';write_json(jobs,JOBS)
 cache=ROOT/'tools'/'.build'/'module-cache';cache.mkdir(parents=True,exist_ok=True)
 try:
  subprocess.run(['swift','-module-cache-path',str(cache),str(ROOT/'tools'/'rasterize.swift'),str(jobs)],check=True)
 finally:
  jobs.unlink(missing_ok=True)
 JOBS.clear()
def motif(tech):
 n=[]
 if tech:
  # Nested isometric circuit plates; no text is rasterized.
  for i in range(12,-1,-1):
   dx=i*7;dy=i*12
   p=[[110+dx,190+dy],[420+dx,90+dy],[570+dx,295+dy],[260+dx,395+dy]]
   n.append(poly(p,'#132521' if i else '#1B342D','#42685B' if i else '#C6E9D4',1.3 if i else 2.2))
  for t in [.12,.24,.36,.48,.6,.72,.84]:
   n.append(line(110+310*t,190-100*t,260+310*t,395-100*t,'#355C4D',1))
   n.append(line(110+150*t,190+205*t,420+150*t,90+205*t,'#355C4D',1))
  n += [poly([[208,221],[339,179],[405,267],[273,310]],'#BCE6CD'),poly([[246,235],[329,208],[368,260],[286,287]],'#173B2D')]
  for x,y in [(110,190),(420,90),(570,295),(260,395)]:n.append(ellipse(x-4,y-4,8,8,'#E8F1DA'))
  n += [line(120,590,380,590,'#4E6C61'),line(120,584,120,596,'#91B8A7'),line(380,584,380,596,'#91B8A7')]
 else:
  # Perspective portal: the luminous hierarchy is in original pixels, no GPU effect.
  n.append(poly([[170,54],[475,54],[644,222],[644,476],[480,640],[170,640],[56,526],[56,168]],'#1B1331'))
  for i in range(11,-1,-1):
   s=1-i*.048;cx=360+i*7;cy=330+i*10
   pts=[(170,74),(475,74),(624,222),(624,476),(480,620),(170,620),(76,526),(76,168)]
   p=[[cx+(x-350)*s,cy+(y-350)*s] for x,y in pts]
   n.append(poly(p,'none','#513375' if i else '#BC97FE',3 if i==0 else 1.4))
  n += [poly([[170,54],[475,54],[644,222],[644,360]],stroke='#A974FF',sw=5,closed=False),poly([[480,640],[170,640],[56,526],[56,350]],stroke='#CFF56A',sw=5,closed=False)]
  for i in range(6):n.append(poly([[168+i*27,602],[181+i*27,602],[195+i*27,588],[182+i*27,588]],'#CFF56A'))
  n += [poly([[300,270],[410,270],[445,305],[445,407],[410,442],[300,442],[265,407],[265,305]],'#332048','#8A59C5',1),poly([[327,307],[383,307],[412,355],[383,403],[327,403],[298,355]],'#CDF462')]
 return n

def frame(tech):
 c='#BCE6CD' if tech else '#CFF56A';dim='#537166' if tech else '#64448E';n=[rect(2,2,956,536,'none',stroke=dim,stroke_width=2)]
 if tech:
  for x,y,sx,sy in [(2,2,1,1),(958,2,-1,1),(2,538,1,-1),(958,538,-1,-1)]:n.append(poly([[x,y+30*sy],[x,y],[x+30*sx,y]],stroke=c,sw=5,closed=False))
  n += [line(430,2,530,2,c,4),line(430,538,530,538,c,4)]
 else:
  n=[poly([[36,2],[922,2],[958,38],[958,502],[922,538],[36,538],[2,502],[2,38]],stroke=dim,sw=2)]
  n += [poly([[36,2],[150,2]],stroke=c,sw=5,closed=False),poly([[810,538],[922,538],[958,502]],stroke='#B897F4',sw=5,closed=False),poly([[2,38],[36,2]],stroke='#B897F4',sw=5,closed=False)]
 return n

def source(id,name,definition):return dict(id=id,name=name,definition=definition)
def textdef(text,w,h,size,c,font='Helvetica'):return dict(kind='text',text=text,font=font,size=size,color=rgb(c),opacity=1.,align='left',width=w,height=h,background=None,background_opacity=0.,outline=False)
def widget(kind,title,subtitle,w,h,bg,accent,fg,duration):return dict(kind='widget',widget=dict(kind=kind,title=title,subtitle=subtitle,width=w,height=h,background=rgb(bg),accent=rgb(accent),color=rgb(fg),opacity=1.,duration_ms=duration))
def layout(x,y,w,h,order,visible=True):return dict(x=x,y=y,width=w,height=h,visible=visible,order=order)
def build(tech):
 name='creator-tech' if tech else 'neon-arena';p='tech' if tech else 'arena';out=ROOT/name
 for d in ['assets','assets/source','previews']:(out/d).mkdir(parents=True,exist_ok=True)
 bg='#101B19' if tech else '#140D22';fg='#F4F1E7' if tech else '#F4EEFF';ac='#BCE6CD' if tech else '#CFF56A';plate='#1C3029' if tech else '#302040'
 asset_specs=[('motif',720,720,motif(tech)),('frame',960,540,frame(tech))]
 for key,w,h,nodes in asset_specs:
  title=f'{name} {key} · original editable geometric asset'
  (out/f'assets/source/{p}-{key}.svg').write_text(svg(nodes,w,h,title));render_job(nodes,w,h,out/f'assets/{p}-{key}.png')
 render()
 resources=[]
 for key,w,h,_ in asset_specs:
  filename=f'{p}-{key}.png';data=(out/'assets'/filename).read_bytes()
  resources.append(dict(id=f'{p}-{key}-asset',file_name=filename,kind='image',sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),width=w,height=h,duration_ms=None))
 start='Make room\nfor ideas.' if tech else 'Your squad.\nYour arena.'
 pause='A little pause.\nA better idea.' if tech else 'Recharge.\nThen rejoin.'
 end='Keep building.\nSee you soon.' if tech else 'Good games.\nGreat people.'
 chapter='03 / DEBUG THE ASSUMPTION' if tech else 'SQUAD NIGHT / OPEN LOBBY'
 identity='CREATOR TECH / BUILD IN PUBLIC' if tech else 'NEON ARENA / PLAY TOGETHER'
 info='One idea.\nOne clear next step.' if tech else None
 overlays=[
 source(f'{p}-background','Ink background',dict(kind='shape',shape='rectangle',width=960,height=540,color=rgb(bg),opacity=1.,border_color=None,border_width=0)),
 source(f'{p}-motif','Original geometric signature',dict(kind='image',resource_id=f'{p}-motif-asset',opacity=1.)),
 source(f'{p}-frame','Transparent camera and screen frame',dict(kind='image',resource_id=f'{p}-frame-asset',opacity=1.)),
 source(f'{p}-title','Starting title',textdef(start,510,190,72,fg)),
 source(f'{p}-pause-title','Pause title',textdef(pause,510,190,68,fg)),
 source(f'{p}-end-title','Ending title',textdef(end,510,190,68,fg)),
 source(f'{p}-chapter' if tech else f'{p}-label','Chapter and session label',textdef(chapter,700,42,22,ac,'Menlo')),
 source(f'{p}-lower-third','Creator identification',widget('lower_third','Alex Rivera' if tech else 'NOVA / PLAYER ONE','Software, explained simply.' if tech else 'Good games. Better company.',560,120,plate,ac,fg,0)),
 source(f'{p}-timer','Session countdown',widget('countdown','NEXT CHAPTER IN' if tech else 'NEXT ROUND IN','',280,120,plate,ac,fg,300000)),
 source(f'{p}-alert','Community alert',widget('alert','A new idea just landed.' if tech else 'PLAYER TWO JOINED','Thanks for building with us.' if tech else 'WELCOME TO THE ARENA',560,120,plate,ac,fg,4500)),
 source(f'{p}-info' if tech else f'{p}-reward','Editorial note' if tech else 'Reward celebration',textdef(info,360,120,30,fg) if tech else widget('alert','POWER UP!','A COMMUNITY REWARD',560,120,'#CFF56A','#6B4392','#180F26',3500)),
 source(f'{p}-identity','Collection identifier',textdef(identity,470,32,14,ac,'Menlo'))]
 scenes=[]
 def scene(slug,label,layers):scenes.append(dict(id=f'{p}-{slug}',name=label,layers=layers))
 def layer(suffix,ref,H,V,order):return dict(id=f'{p}-{suffix}',overlay_id=f'{p}-{ref}',horizontal=layout(*H,order),vertical=layout(*V,order))
 def b(slug):return layer(slug+'-bg','background',(0,0,960,540),(0,0,540,960),0)
 def m(slug):return layer(slug+'-motif','motif',(540,70,400,400),(75,350,390,390),1)
 def title(slug,ref):return layer(slug+'-title',ref,(48,146,510,190),(40,170,460,172),3)
 def ident(slug):return layer(slug+'-identifier','identity',(88,64,470,32) if slug=='camera' else (48,40,470,32),(40,48,460,32),5)
 def timer(slug):return layer(slug+'-timer','timer',(48,380,280,120),(40,770,280,120),4)
 scene('starting','Starting Soon',[b('starting'),m('starting'),title('starting','title'),timer('starting'),ident('starting')])
 if tech:
  scene('live','Live Coding',[b('live'),layer('live-screen-frame','frame',(32,108,640,360),(32,150,476,267.75),3),layer('live-camera-frame','frame',(704,108,224,126),(32,480,476,267.75),3),layer('chapter-layer','chapter',(32,44,700,42),(32,80,476,29),4),layer('presenter','lower-third',(48,412,448,96),(32,770,476,102),5),layer('alert-layer','alert',(210,188,540,116),(32,420,476,102),6)])
  scene('presentation','Screen Presentation',[b('presentation'),layer('presentation-frame','frame',(32,92,672,378),(32,160,476,267.75),3),layer('presentation-chapter','chapter',(32,36,700,42),(32,80,476,29),4),layer('presentation-info','info',(736,230,192,64),(40,600,460,153.3),4)])
 else:
  scene('live','Gameplay',[b('live'),layer('live-frame','frame',(64,48,832,468),(24,185,492,276.75),2),layer('live-label','label',(64,12,700,30),(32,80,476,29),4),layer('presenter','lower-third',(88,396,448,96),(32,760,476,102),5),layer('alert-layer','alert',(240,90,480,103),(32,490,476,102),6)])
  scene('community','Community Interaction',[b('community'),m('community'),layer('community-label','label',(48,40,700,42),(40,60,460,28),4),layer('community-alert','alert',(48,170,560,120),(32,185,476,102),5),layer('reward-layer','reward',(48,340,560,120),(32,760,476,102),6)])
 scene('camera','Camera Focus',[b('camera'),layer('camera-frame','frame',(64,38,832,468),(24,185,492,276.75),3),layer('camera-presenter','lower-third',(88,374,448,96),(32,540,476,102),5),ident('camera')])
 scene('brb','Be Right Back',[b('brb'),m('brb'),title('brb','pause-title'),timer('brb')])
 scene('ending','Ending',[b('ending'),m('ending'),title('ending','end-title'),ident('ending')])
 # Stable experience order; symbols preserve the original collection IDs where possible.
 order=['starting','live','camera','presentation' if tech else 'community','brb','ending'];scenes.sort(key=lambda s:order.index(s['id'][len(p)+1:]))
 for sc in scenes:
  for index,lay in enumerate(sorted(sc['layers'],key=lambda item:item['horizontal']['order'])):
   for variant in ['horizontal','vertical']:lay[variant]['order']=0 if index==0 else index+1
 animations=[]
 def anim(id,scene,layer,kind,dur,easing='linear',distance=24,scale=.9):animations.append(dict(id=id,scene_id=f'{p}-{scene}',layer_id=f'{p}-{layer}',kind=kind,easing=easing,duration_ms=dur,distance=distance,scale_from=scale))
 anim(f'{p}-title-in','starting','starting-title','fade_in',280 if tech else 350)
 anim(f'{p}-title-out','ending','ending-title','fade_out',400)
 anim(f'{p}-label-in','live','chapter-layer' if tech else 'live-label','slide_in',320 if tech else 260,'ease_out',24 if tech else 40)
 anim(f'{p}-label-out','live','chapter-layer' if tech else 'live-label','slide_out',220,'ease_in',24)
 anim(f'{p}-lower-in','camera','camera-presenter','slide_in',320 if tech else 280,'ease_out',32 if tech else 48)
 anim(f'{p}-lower-out','camera','camera-presenter','slide_out',220,'ease_in',32 if tech else 48)
 anim(f'{p}-alert-in','live','alert-layer','scale_in',240,'ease_out',0,.92 if tech else .82)
 anim(f'{p}-alert-out','live','alert-layer','fade_out',220)
 anim(f'{p}-pause-in','brb','brb-title','fade_in',500)
 anim(f'{p}-indicator-in','starting','starting-identifier','fade_in',180)
 if not tech:
  anim('reward-in','community','reward-layer','scale_in',420,'ease_out',0,.82)
  anim('reward-out','community','reward-layer','scale_out',240,'ease_in',0,.82)
 props=[]
 def prop(id,label,ref,target,value,typ='text'):props.append(dict(id=id,label=label,overlay_id=f'{p}-{ref}',target=target,value=dict(type=typ,value=value)))
 for id,label,ref,value in [('starting-title','Starting title','title',start),('pause-title','Pause title','pause-title',pause),('ending-title','Ending title','end-title',end),('chapter','Chapter / session','chapter' if tech else 'label',chapter),('identifier','Identifier','identity',identity)]:prop(id,label,ref,'text_content',value)
 prop('presenter','Creator name','lower-third','widget_title','Alex Rivera' if tech else 'NOVA / PLAYER ONE')
 prop('presenter-detail','Creator description','lower-third','widget_subtitle','Software, explained simply.' if tech else 'Good games. Better company.')
 prop('countdown-title','Countdown title','timer','widget_title','NEXT CHAPTER IN' if tech else 'NEXT ROUND IN')
 prop('alert-title','Alert title','alert','widget_title','A new idea just landed.' if tech else 'PLAYER TWO JOINED')
 prop('alert-detail','Alert detail','alert','widget_subtitle','Thanks for building with us.' if tech else 'WELCOME TO THE ARENA')
 prop('background','Background color','background','shape_color',rgb(bg),'color')
 if tech:prop('note','Presentation note','info','text_content',info)
 else:prop('reward-text','Reward title','reward','widget_title','POWER UP!')
 rule_ids=[f'{p}-deck-alert',f'{p}-deck-chapter',f'{p}-provider-follow']
 if not tech:rule_ids += ['arena-deck-celebrate','arena-provider-reward']
 pack=dict(schema_version=1,id=name,version='0.2.0',name='CREATOR TECH — Build in Public' if tech else 'NEON ARENA — Play Together',author='Motive contributors',license='GPL-3.0-or-later',resources=resources,scenes=scenes,overlays=overlays,animations=animations,properties=props,events=['manual.button_pressed','viewer.follow']+([] if tech else ['viewer.reward_redeemed']),rule_ids=rule_ids,requires=['text','shape','widget','layer_animation','scene_transition','image_asset'],budget=dict(max_resource_bytes=4*1024*1024,max_estimated_texture_bytes=128*1024*1024,max_simultaneous_animations=4))
 write_json(out/'manifest.json',pack)
 meta=dict(schema_version=1,description='A quiet editorial collection for software, teaching and thoughtful conversations.' if tech else 'An angular, luminous collection for games, rewards and shared moments.',category='Education & technology' if tech else 'Gaming & community',tags=['coding','podcast','education','editorial'] if tech else ['gaming','community','events','neon'],cover='previews/starting-horizontal.png',art_direction='Ink / parchment / mint · engineering plates · generous margins' if tech else 'Midnight / violet / acid lime · angular portal · luminous hierarchy',palette=dict(background=bg,foreground=fg,accent=ac,panel=plate),preview_scope='Independent authored approximation. Widgets shown in an activated illustrative state. No native rendering, capture, timer or Production connection.',native_importer_status='pending_importer: observed H14 installer embeds MATCHDAY only and rejects resources',scenes=[dict(id=s['id'],label=s['name'],slug=s['id'][len(p)+1:]) for s in scenes],resource_reserve=dict(scenes=8-len(scenes),sources=16-len(overlays),layers=32-sum(len(s['layers']) for s in scenes)),layout_space=dict(horizontal=[960,540],vertical=[540,960]),attribution='Original Motive geometric artwork; no third-party assets or bundled fonts.',supported_customization='Only manifest properties are set_property targets. Widget palette/image replacement are not v1 properties.',style_variants=[dict(id='original',label='Original collection',status='implemented'),dict(id='reduced-motion',label='Reduced motion',status='recipe: show/hide or cut; no zero-duration layer animation')])
 write_json(out/'metadata.json',meta)
 old_sources=['tech-background','tech-accent','tech-title','tech-lower-third','tech-chapter','tech-timer','tech-camera-frame'] if tech else ['arena-background','arena-accent','arena-title','arena-alert','arena-reward','arena-frame','arena-label']
 current_sources={o['id'] for o in overlays}
 write_json(out/'migration-from-0.1.json',dict(scope='Reviewable migration proposal; not an executable installer or automatic update.',from_version='0.1.0',to_version='0.2.0',retained_collection_id=name,retained_source_symbols=[s for s in old_sources if s in current_sources],removed_source_symbols=[s for s in old_sources if s not in current_sources],requires_new_resource_staging=True,preserve_user_text='Match only existing compatible property IDs and preview all proposed edits. Do not overwrite personalized values silently.',incompatible_changes=['Arena frame changes from shape to image and needs a new native source binding.'] if not tech else ['Original tech-camera-frame shape replaced by shared tech-frame image; native source ID cannot be reused.'],timer_policy='Do not restore running timers, alerts, receipts or cooldown state.',update_policy='Install into a separately reviewed empty project or official transaction after capacity validation; no automatic in-place replay.'))
 make_deck_rules(out,pack,p,tech)
 recipes=dict(schema_version=1,scope='Capture recipes only; the manifest never opens devices or adds captures.',capture_sources=['One user-selected camera','One user-selected window or game capture'],remaining_capacity=meta['resource_reserve'],slots=[])
 for s in scenes:
  for l in s['layers']:
   if l['overlay_id']==f'{p}-frame':
    recipes['slots'].append(dict(scene_id=s['id'],frame_layer_id=l['id'],source_role='camera' if ('camera' in l['id']) else 'window',horizontal={**l['horizontal'],'order':1},vertical={**l['vertical'],'order':1},instructions='Add a user-selected source at order 1. Frame remains order >=2. Match 16:9; nonmatching capture aspect uses contain, never implied crop. These slots add layers against the whole-project limit.'))
 recipes['notes']=['Do not install two complete collections in one project. Their combined graph exceeds limits.','Frame interiors are transparent PNG. Empty previews show background, not a simulated camera.','Count all selected capture slots before adding them; reserve is not a promise for a pre-existing project.','The same camera/window may be reused across scenes with distinct layer transforms.','Optional native-only adaptation: omit image motif/frame layers, draw a native rectangle border around the capture; this is a manual recipe, not a second manifest/importer.']
 write_json(out/'recipes.json',recipes)
 write_json(out/'assets'/'provenance.json',dict(license='GPL-3.0-or-later',author='Motive contributors',generator='tools/generate.py + tools/rasterize.swift',original=True,third_party_assets=[],fonts='Helvetica and Menlo requested from macOS; font files are not copied or distributed.',resources=[dict(file_name=r['file_name'],sha256=r['sha256'],editable_source=f'source/{r["file_name"][:-4]}.svg') for r in resources]))
 (out/'LICENSE').write_text((ROOT/'tools'/'LICENSE.txt').read_text())
 count=sum(len(s['layers']) for s in scenes)
 (out/'README.md').write_text(f'''# {pack['name']}

Version {pack['version']} · GPL-3.0-or-later · Motive contributors.

{meta['description']} Original geometric assets, native editable typography and six compositions in both design960 orientations. This extends the existing {name} fixture, retaining its collection identity and relevant source/animation symbols; it does not overwrite the original.

## Deliverables and truthful status

- `manifest.json`: exact CreatorPack v1 schema; {len(scenes)} scenes, {len(overlays)} reusable overlay sources, {count} total layers, {len(animations)} animation definitions and {len(props)} properties.
- `assets/`: two transparent PNG resources with original editable SVG sources and provenance. No customizable text is baked into an asset.
- `previews/`: twelve SVG/PNG composition studies generated from the manifest. They approximate native typography and illustrate widgets after show/trigger; lower thirds and alerts are hidden initially in Motive. Empty frames are genuinely empty. These are not recordings, real captures or native acceptance evidence.
- `deck.json`, `rules.json`, `events.jsonl`: typed manual event examples and disabled provider rules. No platform connection, credential, script, sound or code execution.
- `recipes.json`: explicit capture slots for later user selection; captures are not included in the manifest.
- `metadata.json`: catalog information kept outside the strict native manifest.
- `migration-from-0.1.json`: explicit symbol/definition changes for a future reviewed update; no automatic in-place migration.

Validation reports: [asset/geometry gate](../../evidence/contracts-validation.json) and [authoritative Rust contract](../../evidence/contracts-native.json). These reports describe the last independently executed check, not a claim embedded in the manifest.

Native integration is pending: the observed H14 installer supports embedded MATCHDAY and rejects resource descriptors. These image-based packs validate as v1 proposals but cannot be installed by that observed installer. No installer is supplied here.

## Compositions

'''+ '\n'.join(f'- {s["name"]}: `previews/{s["id"][len(p)+1:]}-horizontal.png` and `-vertical.png`.' for s in scenes)+f'''

## Personalize safely

The {len(props)} declared properties edit native text, widget title/subtitle and background shape color. A long title is contained as a block and does not automatically wrap: keep explicit newlines, review both orientations, and shorten text if it becomes too small. Widget palette, fonts, durations and images are not `set_property` targets in v1. Direct definition edits require the official inspector/owner validation and preserve source identity restrictions.

Every source is shared. Editing the presenter changes all presenter layers; starting, pause and ending titles have independent sources so edits do not corrupt other compositions. The countdown is shared between Starting Soon and BRB: scene change does not reset it. Its default is five minutes; Reset/Start must be deliberate. A counter in Show Control remains internal state, never implied as a live widget binding.

The pack reserves {16-len(overlays)} source slots and {32-count} layer slots in an empty production. `recipes.json` shows optional capture layers. Existing projects and multiple packs require a fresh global capacity/budget preflight. Resources need authorized local staging and hash/decode verification by the official importer.

## Motion and operation

Declared Fade is linear; Slide/Scale use bounded native easing. Layer timing is 100–10000 ms. Reduced-motion recipes use immediate Show/Hide or Cut, not an invalid 0 ms animation. Widget appearance has its own native 300 ms behavior; source show/trigger and layer motion are distinct. Do not overlap multiple operations on one layer; wait for the owner acknowledgement. Four simultaneous animations is the authored budget, below the engine limit of eight.

Manual Deck rehearsal never changes Production. Provider rules are disabled until a trusted event adapter and user authorization exist. Source/layer/scene symbols must be resolved from official installer replies, never guessed.

## Reproduce

From `creator-experience/`: `python3 packs/tools/generate.py`, then run the independent validator described in `../../validation/README.md`. The generator uses Python stdlib and macOS Swift/AppKit, performs no capture and writes only within `packs/`. Run the independent validator before distributing changes. Source SVGs are design files, not accepted native resources. Widget and text rendering are approximations; exact native review remains pending.
''')
 return pack,out

def make_deck_rules(out,pack,p,tech):
 rules=[]
 def rule(id,button,actions,event='manual.button_pressed',enabled=True):
  conditions=[dict(type='equals',field='button_id',value=dict(type='string',value=button))] if event=='manual.button_pressed' else []
  rules.append(dict(id=id,enabled=enabled,event_kind=event,conditions=conditions,actions=actions,priority=5,cooldown_ms=2500,debounce_ms=0,timeout_ms=5000,busy_policy='reject',failure_policy='stop'))
 rule(f'{p}-deck-alert','alert',[dict(type='widget',source_id=f'{p}-alert',event='trigger')])
 rule(f'{p}-deck-chapter','chapter',[dict(type='show_overlay',source_id=f'{p}-chapter' if tech else f'{p}-label')])
 rule(f'{p}-provider-follow','',[dict(type='widget',source_id=f'{p}-alert',event='trigger')],'viewer.follow',False)
 if not tech:
  rule('arena-deck-celebrate','celebrate',[dict(type='sequence',actions=[dict(type='widget',source_id='arena-reward',event='trigger'),dict(type='increment_counter',name='community_rewards',amount=1)])])
  rule('arena-provider-reward','',[dict(type='widget',source_id='arena-reward',event='trigger')],'viewer.reward_redeemed',False)
 write_json(out/'rules.json',dict(schema_version=1,variables={},max_actions_per_event=16,queue_capacity=8,rate_limit=20,rate_window_ms=1000,rules=rules))
 buttons=[]
 def button(id,label,icon,target,group='show',sensitive=False,cooldown=0,enabled=True):
  buttons.append(dict(id=id,group_id=group,label=label,icon=icon,order=sum(b['group_id']==group for b in buttons),enabled=enabled,shortcut=None,cooldown_ms=cooldown,sensitive=sensitive,target=target))
 button('presenter','Show name','text',dict(kind='overlay',source_ref=f'{p}-lower-third',show=True))
 button('chapter','Show chapter' if tech else 'Session label','text',dict(kind='rule',rule_id=f'{p}-deck-chapter'))
 button('countdown','Start countdown','timer',dict(kind='countdown',source_ref=f'{p}-timer',reset=False))
 button('countdown-reset','Reset countdown','timer',dict(kind='countdown',source_ref=f'{p}-timer',reset=True),sensitive=True)
 button('live','Live Coding' if tech else 'Gameplay','play',dict(kind='scene',scene_ref=f'{p}-live',transition=dict(kind='cut')),sensitive=True,cooldown=1000)
 button('brb','Pause','pause',dict(kind='scene',scene_ref=f'{p}-brb',transition=dict(kind='fade',duration_ms=350)),sensitive=True,cooldown=1000)
 button('alert','Community alert','bell',dict(kind='rule',rule_id=f'{p}-deck-alert'),'community',cooldown=2500)
 if not tech:
  button('celebrate','Celebration','spark',dict(kind='composite',rule_id='arena-deck-celebrate'),'community',cooldown=6000)
  button('reward-entry','Reward entry','layers',dict(kind='animation',animation_id='reward-in'),'community',cooldown=1500)
 button('provider-follow','Automatic follow · disabled','bell',dict(kind='rule',rule_id=f'{p}-provider-follow'),'community',enabled=False)
 write_json(out/'deck.json',dict(schema_version=1,id=f'{p}-creator-deck',name=f'{pack["name"]} · independent rehearsal',groups=[dict(id='show',label='Show',order=0),dict(id='community',label='Community',order=1)],buttons=buttons))
 # The real event envelope is copied structurally from the existing fixtures, never a provider signal.
 example=dict(schema_version=1,id='manual-fixture',origin='simulator',timestamp_ms=1000,correlation_id='manual-fixture',external_id=None,simulated=True,payload={})
 events=[]
 for i,button_id in enumerate(['alert','chapter']+([] if tech else ['celebrate'])):
  e=dict(example);e['id']=f'{p}-manual-{i+1}';e['origin']='simulator';e['correlation_id']=e['id'];e['timestamp_ms']=(i+1)*1000;e['payload']={'kind':'manual.button_pressed','button_id':button_id};events.append(e)
 (out/'events.jsonl').write_text('\n'.join(json.dumps(e,separators=(',',':')) for e in events)+'\n')

def text_nodes(value,x,y,w,h,size,c,font='Helvetica',align='left'):
 lines=value.split('\n');maxwidth=max([len(t)*size*(.61 if font=='Menlo' else .55) for t in lines]+[1]);height=len(lines)*size*1.18
 scale=min(1,w/maxwidth,h/height);s=size*scale;lh=s*1.18;result=[]
 for i,t in enumerate(lines):
  tw=len(t)*s*(.61 if font=='Menlo' else .55);tx=x+(w-tw)*(0 if align=='left' else .5 if align=='center' else 1)
  result.append(txt(t,tx,y+i*lh,s,c,font))
 return result

def scene_nodes(pack,scene,orientation,out,show_alert=False):
 nodes=[];defs={o['id']:o['definition'] for o in pack['overlays']};res={r['id']:r for r in pack['resources']}
 for layer in sorted(scene['layers'],key=lambda l:l[orientation]['order']):
  l=layer[orientation];d=defs[layer['overlay_id']]
  if not l['visible']:continue
  if d['kind']=='widget' and d['widget']['kind']=='alert' and scene['id'].endswith('-live') and not show_alert:continue
  x,y,w,h=[l[k] for k in ['x','y','width','height']];kind=d['kind']
  if kind=='shape':nodes.append(rect(x,y,w,h,hexcolor(d['color']),opacity=d['opacity']));continue
  intrinsic=d.get('widget',d)
  if kind=='image':intrinsic=res[d['resource_id']]
  iw,ih=intrinsic['width'],intrinsic['height'];scale=min(w/iw,h/ih);rw,rh=iw*scale,ih*scale;x+=(w-rw)/2;y+=(h-rh)/2;w,h=rw,rh
  if kind=='image':nodes.append(dict(kind='image',x=x,y=y,width=w,height=h,path=str(out/'assets'/res[d['resource_id']]['file_name']),opacity=d['opacity']))
  elif kind=='text':nodes+=text_nodes(d['text'],x,y,w,h,d['size']*scale,hexcolor(d['color']),d['font'],d['align'])
  elif kind=='widget':
   z=d['widget'];bg=hexcolor(z['background']);ac=hexcolor(z['accent']);fg=hexcolor(z['color']);nodes.append(rect(x,y,w,h,bg));pad=min(24,min(iw,ih)*.12)*scale
   if z['kind']=='countdown':
    nodes.append(rect(x+w*.3,y+h*.86,w*.4,min(4,ih*.03)*scale,ac))
    fs=max(16,min(48,ih*.13))*scale;nodes+=text_nodes(z['title'],x+pad,y+h*.12,w-pad*2,h*.2,fs,fg,align='center')
    sec=z['duration_ms']//1000;nodes+=text_nodes(f'{sec//60:02}:{sec%60:02}',x+pad,y+h*.33,w-pad*2,h*.47,max(24,min(192,ih*.42))*scale,fg,align='center')
   else:
    nodes.append(rect(x,y,min(6,iw*.06)*scale,h,ac));nodes+=text_nodes(z['title'],x+pad,y+h*.16,w-pad*2,h*.38,max(12,min(48,ih*.29))*scale,fg);nodes+=text_nodes(z['subtitle'],x+pad,y+h*.57,w-pad*2,h*.25,max(12,min(30,ih*.19))*scale,fg)
 return nodes

def main():
 packs=[build(True),build(False)]
 for pack,out in packs:
  for s in pack['scenes']:
   slug=s['id'].split('-',1)[1]
   for orientation,(w,h) in [('horizontal',(960,540)),('vertical',(540,960))]:
    nodes=scene_nodes(pack,s,orientation,out);stem=f'{slug}-{orientation}';title=f'{pack["name"]} · {s["name"]} · {orientation} · authored approximation, not native output'
    (out/f'previews/{stem}.svg').write_text(svg(nodes,w,h,title));render_job(nodes,w,h,out/f'previews/{stem}.png')
 render()
 for pack,out in packs:
  scene=next(s for s in pack['scenes'] if s['id'].endswith('-live'))
  for orientation,(w,h) in [('horizontal',(960,540)),('vertical',(540,960))]:
   nodes=scene_nodes(pack,scene,orientation,out,True);stem=f'alert-{orientation}'
   (out/f'previews/{stem}.svg').write_text(svg(nodes,w,h,'Activated alert illustration; not native output'));render_job(nodes,w,h,out/f'previews/{stem}.png')
 render()
 for pack,out in packs:
  nodes=[rect(0,0,1440,1120,'#F2F3F5'),txt(pack['name']+' / composition studies',24,18,24,'#16181D'),txt('Authored approximation · widgets illustrated after activation · no Production connection',24,50,15,'#545A65')]
  for i,scene in enumerate(pack['scenes']):
   slug=scene['id'].split('-',1)[1];col=i%3;row=i//3
   nodes.append(dict(kind='image',x=24+col*472,y=102+row*295,width=448,height=252,path=str(out/f'previews/{slug}-horizontal.png')))
   nodes.append(txt(scene['name'],24+col*472,80+row*295,15,'#16181D'))
   nodes.append(dict(kind='image',x=24+i*236,y=710,width=212,height=377,path=str(out/f'previews/{slug}-vertical.png')))
   nodes.append(txt(scene['name'],24+i*236,688,14,'#16181D'))
  render_job(nodes,1440,1120,out/'previews/contact-sheet.png')
 render()
 print('Generated two original packs; 24 SVG+PNG composition previews; no production engine invoked.')
if __name__=='__main__':main()
