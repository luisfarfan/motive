#!/usr/bin/env python3
"""Regenerate original design previews from the declarative fixtures, not libobs.
SVG/HTML are documentation artifacts: H12 does not import SVG or browser sources.
No filesystem access occurs inside a pack; this explicit developer script reads fixtures.
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'design'

def color(c): return f'#{c:06x}'
def esc(t): return html.escape(str(t), quote=True)
def text_block(t, x, y, w, h, size, fill, font='Helvetica', align='left', weight=700):
    lines=t.split('\n') or ['']
    # Deliberately approximate typography; exact output requires native FreeType verification.
    max_chars=max((len(line) for line in lines),default=1)
    size=min(size, w/max(max_chars*.63,1), h/(max(len(lines),1)*1.22))
    anchor={'left':'start','center':'middle','right':'end'}[align]
    tx={'left':x,'center':x+w/2,'right':x+w}[align]
    baseline=y+(h-size*len(lines)*1.15)/2+size*.85
    return ''.join(f'<text x="{tx:g}" y="{baseline+i*size*1.15:g}" font-family="{font}, sans-serif" font-size="{size:g}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(line)}</text>' for i,line in enumerate(lines))
def scene_svg(pack, scene_id, orientation='horizontal', celebration=False):
    scene=next(s for s in pack['scenes'] if s['id']==scene_id)
    w,h=(960,540) if orientation=='horizontal' else (540,960)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(pack["name"])} {orientation} design prototype"><title>{esc(pack["name"])} · {esc(scene["name"])} · design prototype</title>']
    definitions={o['id']:o['definition'] for o in pack['overlays']}
    for layer in sorted(scene['layers'],key=lambda l:l[orientation]['order']):
        l=layer[orientation];d=definitions[layer['overlay_id']]
        if not l['visible']: continue
        if d['kind']=='widget' and d['widget']['kind']!='countdown':
            if celebration and layer['overlay_id']=='goal-celebration':pass
            elif pack['id']=='matchday' and layer['overlay_id']!='match-lower-third':continue
            elif pack['id']=='neon-arena' and layer['overlay_id']=='arena-alert':continue
        x,y,lw,lh=(l[k] for k in ['x','y','width','height'])
        out.append(f'<g opacity="{d.get("opacity",1)}">')
        if d['kind']=='shape':
            bc=d['border_color'];bw=d['border_width']
            if d['shape']=='circle':out.append(f'<circle cx="{x+lw/2:g}" cy="{y+lh/2:g}" r="{min(lw,lh)/2:g}" fill="{color(d["color"])}" stroke="{color(bc) if bc is not None else "none"}" stroke-width="{bw}"/>')
            else:out.append(f'<rect x="{x:g}" y="{y:g}" width="{lw:g}" height="{lh:g}" fill="{color(d["color"])}" stroke="{color(bc) if bc is not None else "none"}" stroke-width="{bw}"/>')
        elif d['kind']=='text':
            out.append(text_block(d['text'],x,y,lw,lh,d['size'],color(d['color']),d['font'],d['align']))
        elif d['kind']=='widget':
            z=d['widget'];out.append(f'<rect x="{x:g}" y="{y:g}" width="{lw:g}" height="{lh:g}" fill="{color(z["background"])}"/><rect x="{x:g}" y="{y:g}" width="{max(4,lw*.012):g}" height="{lh:g}" fill="{color(z["accent"])}"/>')
            if z['kind']=='countdown':
                out.append(text_block(z['title'],x+16,y+8,lw-32,lh*.3,22,color(z['color']),align='center'))
                seconds=z['duration_ms']//1000
                out.append(text_block(f'{seconds//60:02}:{seconds%60:02}',x+16,y+lh*.35,lw-32,lh*.56,64,color(z['color']),'Menlo','center'))
            else:
                out.append(text_block(z['title'],x+lw*.05,y+lh*.14,lw*.9,lh*.44,58 if layer['overlay_id']=='goal-celebration' else 32,color(z['color'])))
                out.append(text_block(z['subtitle'],x+lw*.05,y+lh*.62,lw*.9,lh*.23,22,color(z['color']),'Menlo',weight=400))
        out.append('</g>')
    out.append('</svg>')
    return ''.join(out)
packs={name:json.loads((ROOT/f'examples/packs/{name}.json').read_text()) for name in ['matchday','creator-tech','neon-arena']}
scenes={'matchday':'match-live','creator-tech':'tech-live','neon-arena':'arena-live'}
for name,p in packs.items():
 for orientation in ['horizontal','vertical']:
  (OUT/f'{name}-{orientation}.svg').write_text(scene_svg(p,scenes[name],orientation,True)+'\n')
for scene_id in ['match-starting','match-brb','match-ending']:
 (OUT/f'{scene_id}.svg').write_text(scene_svg(packs['matchday'],scene_id)+'\n')
print('Generated nine SVG documentation previews; no native production was launched.')
