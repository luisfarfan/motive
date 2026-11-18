"""Static SVG design previews. No clock, renderer integration or pixel parity claim."""
import base64
from html import escape
from pathlib import Path
from common import require
from compiler import Bundle

def color(value):return f'#{value:06x}'

def svg(bundle: Bundle,scene: dict,orientation: str) -> str:
    width,height=(960,540) if orientation=='horizontal' else (540,960)
    sources={o['id']:o['definition'] for o in bundle.pack['overlays']}
    resources={r['id']:r for r in bundle.pack['resources']}
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Approximate authoring preview">',
           '<defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#30323a" stroke-width="0.5"/></pattern></defs>',
           f'<rect width="100%" height="100%" fill="#17181c"/><rect width="100%" height="100%" fill="url(#grid)"/>']
    def text(content,x,y,size,fill,anchor='start',font='Helvetica'):
        lines=content.split('\n')
        return ''.join(f'<text x="{x}" y="{y+i*size*1.2}" font-family="{font},sans-serif" font-size="{size}" text-anchor="{anchor}" fill="{fill}">{escape(line)}</text>' for i,line in enumerate(lines))
    for layer in sorted(scene['layers'],key=lambda l:l[orientation]['order']):
        t=layer[orientation]
        if not t['visible']:continue
        d=sources[layer['overlay_id']];kind=d['kind'];box=d['widget'] if kind=='widget' else resources.get(d.get('resource_id'),d)
        w,h=box['width'],box['height'];stretch=kind=='shape' and d['shape']=='rectangle'
        sx,sy=t['width']/w,t['height']/h
        if not stretch:sx=sy=min(sx,sy)
        x=t['x']+(t['width']-w*sx)/2;y=t['y']+(t['height']-h*sy)/2
        opacity=box.get('opacity',d.get('opacity',1))
        parts.append(f'<g transform="translate({x} {y}) scale({sx} {sy})" opacity="{opacity}">')
        if kind=='shape':
            attrs=f'fill="{color(d["color"])}" stroke="{color(d["border_color"]) if d["border_color"] is not None else "none"}" stroke-width="{d["border_width"]}"'
            parts.append(f'<rect width="{w}" height="{h}" {attrs}/>' if d['shape']=='rectangle' else f'<ellipse cx="{w/2}" cy="{h/2}" rx="{w/2}" ry="{h/2}" {attrs}/>')
        elif kind=='text':
            if d['background'] is not None:parts.append(f'<rect width="{w}" height="{h}" fill="{color(d["background"])}" opacity="{d["background_opacity"]}"/>')
            anchor={'left':'start','center':'middle','right':'end'}[d['align']]
            tx={'left':0,'center':w/2,'right':w}[d['align']]
            parts.append(text(d['text'],tx,d['size'],d['size'],color(d['color']),anchor,d['font']))
        elif kind=='widget':
            parts.append(f'<rect width="{w}" height="{h}" fill="{color(box["background"])}"/><rect width="8" height="{h}" fill="{color(box["accent"])}"/>')
            parts.append(text(box['title'],28,42,28,color(box['color'])))
            subtitle=box['subtitle']
            if box['kind']=='countdown':
                seconds=box['duration_ms']//1000;subtitle=f'{seconds//60:02}:{seconds%60:02}'
            parts.append(text(subtitle,28,82,22,color(box['color'])))
        elif kind=='image':
            resource=resources[d['resource_id']];data=base64.b64encode(bundle.assets[resource['file_name']]).decode()
            parts.append(f'<image width="{w}" height="{h}" href="data:image/png;base64,{data}"/>')
        else:
            parts.append(text('Video preview unavailable',16,36,24,'#ffffff'))
        parts.append('</g>')
    parts.append('</svg>')
    return ''.join(parts)

def render(bundle: Bundle,directory: Path) -> list[str]:
    require(not directory.exists(),'OUTPUT_EXISTS',str(directory));directory.mkdir(parents=True)
    cards=[];files=[]
    for s in bundle.pack['scenes']:
        for orient in ('horizontal','vertical'):
            name=f'{s["id"]}-{orient}.svg';(directory/name).write_text(svg(bundle,s,orient));files.append(name)
            cards.append(f'<figure><img src="{name}" alt="{escape(s["name"])} · {orient}"><figcaption>{escape(s["name"])} · {orient}</figcaption></figure>')
    html='''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Element Lab · Preview</title>
<style>body{margin:0;background:#f2f3f5;color:#16181d;font:15px system-ui}header,main{padding:24px 4vw}header{border-bottom:1px solid #d5d8de}h1{font-size:24px}p{max-width:80ch;color:#545a65}main{display:flex;gap:32px;flex-wrap:wrap}figure{margin:0;max-width:100%;}img{display:block;max-width:100%;max-height:620px;background:#17181c;border-radius:12px}figcaption{padding:12px 0}</style>
<header><span>MOTIVE / ELEMENT LAB</span><h1>'''+escape(bundle.pack['name'])+'''</h1><p>Preview de autoría aproximado · sin libobs. Tipografía, encaje y widgets son esquemáticos; se muestran activos para revisión. No ejecuta animaciones ni countdown. Ambos layouts usan design960.</p></header><main>'''+''.join(cards)+'</main></html>'
    (directory/'index.html').write_text(html);return files+['index.html']
