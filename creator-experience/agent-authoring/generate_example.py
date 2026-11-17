#!/usr/bin/env python3
"""Generate a minimal didactic CreatorPack v1 with two reserved camera slots.
Python standard library only. No Motive, network, device or provider is invoked.
GPL-3.0-or-later.
"""
from pathlib import Path
import argparse, html, json
ROOT=Path(__file__).resolve().parent

def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def layout(x,y,w,h,order):return dict(x=x,y=y,width=w,height=h,visible=True,order=order)
def text(value,w,h,size,color=0xF4F1E7,font='Helvetica'):
 return dict(kind='text',text=value,font=font,size=size,color=color,opacity=1.0,align='left',width=w,height=h,background=None,background_opacity=0.0,outline=False)
def lower(title,subtitle):
 return dict(kind='widget',widget=dict(kind='lower_third',title=title,subtitle=subtitle,width=420,height=100,background=0x25342F,accent=0xBCE6CD,color=0xF4F1E7,opacity=1.0,duration_ms=0))
def source(id,name,d):return dict(id=id,name=name,definition=d)
def layer(id,overlay,H,V,order):return dict(id=id,overlay_id=overlay,horizontal=layout(*H,order),vertical=layout(*V,order))
def main(output):
 output.mkdir(parents=True,exist_ok=True);(output/'previews').mkdir(exist_ok=True)
 sources=[source('podcast-background','Background',dict(kind='shape',shape='rectangle',width=960,height=540,color=0x15201D,opacity=1.0,border_color=None,border_width=0)),source('podcast-heading','Episode heading',text('LOCAL SIGNAL / SOFTWARE PODCAST',700,42,22,0xBCE6CD,'Menlo')),source('podcast-host','Host identity',lower('Alex Rivera','Host / Software design')),source('podcast-guest','Guest identity',lower('Jordan Lee','Guest / Local-first systems')),source('podcast-pause-title','Pause title',text('A short pause.\nMore ideas soon.',510,190,60)),source('podcast-pause-detail','Pause detail',text('Thanks for joining the conversation.',600,48,22,0xBCE6CD))]
 scenes=[dict(id='podcast-live',name='Conversation',layers=[layer('podcast-live-bg','podcast-background',(0,0,960,540),(0,0,540,960),0),layer('podcast-live-heading','podcast-heading',(32,40,700,42),(32,40,476,29),3),layer('podcast-host-layer','podcast-host',(32,390,432,103),(32,390,476,113.34),4),layer('podcast-guest-layer','podcast-guest',(496,390,432,103),(32,796,476,113.34),5)]),dict(id='podcast-brb',name='Be Right Back',layers=[layer('podcast-brb-bg','podcast-background',(0,0,960,540),(0,0,540,960),0),layer('podcast-brb-title','podcast-pause-title',(64,170,510,190),(40,250,460,172),1),layer('podcast-brb-detail','podcast-pause-detail',(64,400,600,48),(40,510,460,37),2)])]
 animations=[dict(id='podcast-host-enter',scene_id='podcast-live',layer_id='podcast-host-layer',kind='slide_in',easing='ease_out',duration_ms=320,distance=24,scale_from=0.9),dict(id='podcast-guest-enter',scene_id='podcast-live',layer_id='podcast-guest-layer',kind='slide_in',easing='ease_out',duration_ms=320,distance=24,scale_from=0.9),dict(id='podcast-pause-enter',scene_id='podcast-brb',layer_id='podcast-brb-title',kind='fade_in',easing='linear',duration_ms=280,distance=0,scale_from=1.0)]
 properties=[]
 for id,label,source_id,target,value in [('heading','Episode heading','podcast-heading','text_content','LOCAL SIGNAL / SOFTWARE PODCAST'),('host-name','Host name','podcast-host','widget_title','Alex Rivera'),('host-role','Host role','podcast-host','widget_subtitle','Host / Software design'),('guest-name','Guest name','podcast-guest','widget_title','Jordan Lee'),('guest-role','Guest role','podcast-guest','widget_subtitle','Guest / Local-first systems'),('pause-title','Pause title','podcast-pause-title','text_content','A short pause.\nMore ideas soon.'),('pause-detail','Pause detail','podcast-pause-detail','text_content','Thanks for joining the conversation.'),('background','Background color','podcast-background','shape_color',0x15201D)]:
  properties.append(dict(id=id,label=label,overlay_id=source_id,target=target,value=dict(type='color' if isinstance(value,int) else 'text',value=value)))
 rule_ids=['podcast-show-identities','podcast-hide-identities','podcast-pause','podcast-resume']
 pack=dict(schema_version=1,id='podcast-two-camera-example',version='0.1.0',name='Podcast authoring example — two reserved cameras',author='Motive contributors',license='GPL-3.0-or-later',resources=[],scenes=scenes,overlays=sources,animations=animations,properties=properties,events=['manual.button_pressed'],rule_ids=rule_ids,requires=['text','shape','widget','layer_animation','scene_transition'],budget=dict(max_resource_bytes=0,max_estimated_texture_bytes=64*1024**2,max_simultaneous_animations=2))
 rules=[]
 def rule(id,button,actions):rules.append(dict(id=id,enabled=True,event_kind='manual.button_pressed',conditions=[dict(type='equals',field='button_id',value=dict(type='string',value=button))],actions=actions,priority=5,cooldown_ms=1000,debounce_ms=0,timeout_ms=5000,busy_policy='reject',failure_policy='stop'))
 rule('podcast-show-identities','show-names',[dict(type='sequence',actions=[dict(type='show_overlay',source_id='podcast-host'),dict(type='show_overlay',source_id='podcast-guest')])])
 rule('podcast-hide-identities','hide-names',[dict(type='sequence',actions=[dict(type='hide_overlay',source_id='podcast-host'),dict(type='hide_overlay',source_id='podcast-guest')])])
 rule('podcast-pause','pause',[dict(type='select_scene',scene_id='podcast-brb',transition=dict(kind='fade',duration_ms=350))])
 rule('podcast-resume','resume',[dict(type='select_scene',scene_id='podcast-live',transition=dict(kind='cut',duration_ms=0))])
 config=dict(schema_version=1,variables={},max_actions_per_event=8,queue_capacity=8,rate_limit=10,rate_window_ms=1000,rules=rules)
 buttons=[]
 for i,(id,label,icon,target,sensitive) in enumerate([('show-names','Show both names','text',dict(kind='composite',rule_id='podcast-show-identities'),False),('hide-names','Hide both names','text',dict(kind='composite',rule_id='podcast-hide-identities'),False),('host-entry','Host entry after Show','layers',dict(kind='animation',animation_id='podcast-host-enter'),False),('pause','Pause conversation','pause',dict(kind='rule',rule_id='podcast-pause'),True),('resume','Return to conversation','play',dict(kind='rule',rule_id='podcast-resume'),True)]):buttons.append(dict(id=id,group_id='conversation',label=label,icon=icon,order=i,enabled=True,shortcut=None,cooldown_ms=1000,sensitive=sensitive,target=target))
 deck=dict(schema_version=1,id='podcast-example-deck',name='Podcast — disconnected rehearsal',groups=[dict(id='conversation',label='Conversation',order=0)],buttons=buttons)
 recipes=dict(schema_version=1,scope='Authoring sidecar only. These are reserved layout slots, not capture sources or serialized devices.',selection='The user chooses two cameras through the official Motive UI later. No UID, URL, path or invented device ID is included.',sources_to_add=2,layers_to_add=2,project_after_selection=dict(scenes=2,sources=8,layers=9),slots=[dict(id='host-camera-slot',scene_id='podcast-live',role='user_selected_host_camera',horizontal=layout(32,132,432,243,1),vertical=layout(32,116,476,267.75,1)),dict(id='guest-camera-slot',scene_id='podcast-live',role='user_selected_guest_camera',horizontal=layout(496,132,432,243,2),vertical=layout(32,520,476,267.75,2))],notes=['The same two camera sources need not exist in BRB.','Choose two different user-selected camera identities; do not duplicate an invented UID.','Capture frames use contain at 16:9; no crop, portrait camera support or automatic device choice is claimed.','Recompute totals for any existing project; these totals assume an empty production.','Lower thirds are initially hidden. Show both names before rehearsing layer animation; animation does not make a hidden widget appear.'])
 metadata=dict(example=True,not_a_premium_collection=True,description='Minimal two-scene authoring example with a two-camera composition recipe.',category='Authoring example',tags=['podcast','two-camera','native-only'],runtime_status='No native install or capture performed. A generic official importer remains required; absence of media resources does not make the H14 MATCHDAY-only installer accept this pack.',preview_scope='SVG documentation only; colored dashed camera guides are not part of the manifest. Widgets illustrated after Show.',capability_baseline='../capabilities-baseline.json')
 brief=dict(intent='Create a minimal original software-podcast composition with two user-selected cameras, host and guest lower thirds, and a pause screen.',audience='Software podcast host and guest',tone='Editorial, quiet, native-only',host='Alex Rivera',guest='Jordan Lee',orientations=['horizontal','vertical'],compositions=['Conversation','Be Right Back'],camera_selection='Deferred to the user in Motive; no device identifiers supplied',motion='Short slide for names; linear fade for pause; reduced-motion recipe uses show/hide and scene Cut',scope='Two-scene teaching example, not a third premium collection or a native installation')
 (output/'LICENSE').write_text((ROOT/'LICENSE').read_text())
 for name,value in [('brief.json',brief),('manifest.json',pack),('deck.json',deck),('rules.json',config),('recipes.json',recipes),('metadata.json',metadata)]:write(output/name,value)
 events=[dict(schema_version=1,id=f'podcast-example-{i+1}',origin='simulator',timestamp_ms=1000+i*2000,correlation_id=f'podcast-example-{i+1}',external_id=None,simulated=True,payload=dict(kind='manual.button_pressed',button_id=button)) for i,button in enumerate(['show-names','hide-names','pause','resume'])]
 (output/'events.jsonl').write_text('\n'.join(json.dumps(e,separators=(',',':')) for e in events)+'\n')
 for scene in scenes:
  for variant in ['horizontal','vertical']:(output/'previews'/f'{scene["id"]}-{variant}.svg').write_text(preview(pack,scene,variant,recipes))
 print('Generated minimal native-only example: 2 scenes, 6 overlay sources, 7 layers; 2 camera sources/layers reserved, never created.')

def preview(pack,scene,variant,recipes):
 w,h=(960,540) if variant=='horizontal' else (540,960)
 out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img"><title>Authoring example: {scene["name"]}; approximate preview; camera guides are not sources; no Production connection</title>'];defs={s['id']:s['definition'] for s in pack['overlays']}
 def textblock(value,x,y,boxw,boxh,size,color,font='Helvetica'):
  lines=value.split('\n');sz=min(size,boxw/max(1,max(len(l) for l in lines)*.61),boxh/(len(lines)*1.2))
  return ''.join(f'<text x="{x}" y="{y+sz*.85+i*sz*1.2}" font-family="{font},sans-serif" font-size="{sz}" fill="#{color:06x}">{html.escape(line)}</text>' for i,line in enumerate(lines))
 for layer in sorted(scene['layers'],key=lambda l:l[variant]['order']):
  l=layer[variant];d=defs[layer['overlay_id']];x,y,lw,lh=[l[k] for k in ['x','y','width','height']]
  if d['kind']=='shape':out.append(f'<rect x="{x}" y="{y}" width="{lw}" height="{lh}" fill="#{d["color"]:06x}"/>');continue
  z=d.get('widget',d);scale=min(lw/z['width'],lh/z['height']);rw,rh=z['width']*scale,z['height']*scale;x+=(lw-rw)/2;y+=(lh-rh)/2
  if d['kind']=='text':out.append(textblock(d['text'],x,y,rw,rh,d['size']*scale,d['color'],d['font']))
  else:
   out += [f'<rect x="{x}" y="{y}" width="{rw}" height="{rh}" fill="#{z["background"]:06x}"/>',f'<rect x="{x}" y="{y}" width="{6*scale}" height="{rh}" fill="#{z["accent"]:06x}"/>',textblock(z['title'],x+14*scale,y+16*scale,rw-28*scale,rh*.38,29*scale,z['color']),textblock(z['subtitle'],x+14*scale,y+57*scale,rw-28*scale,rh*.25,19*scale,z['color'])]
 for index,slot in enumerate(recipes['slots']):
  if slot['scene_id']!=scene['id']:continue
  l=slot[variant];x,y,lw,lh=[l[k] for k in ['x','y','width','height']]
  out.append(f'<rect x="{x}" y="{y}" width="{lw}" height="{lh}" fill="none" stroke="#7C9CA5" stroke-width="2" stroke-dasharray="8 8"/>');out.append(textblock(f'CAMERA {index+1} / USER SELECTION PENDING',x+20,y+lh/2-10,lw-40,32,16,0xA5BAC0,'Menlo'))
 out.append('</svg>');return '\n'.join(out)+'\n'
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'example');args=parser.parse_args();main(args.output)
