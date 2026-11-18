"""Original native examples; deterministic assets generated with Python stdlib."""
import hashlib
from pathlib import Path
import struct
import zlib
from common import LAB, read_bytes, require, write_json

TEMPLATES=['lower-third','community-alert','goal-celebration','countdown']

def motif(seed: int) -> bytes:
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    pixels=bytearray()
    for y in range(48):
        pixels.append(0)
        for x in range(48):
            on=(x+y+seed*5)%20 < 7 and 5 <= x < 43 and 5 <= y < 43
            pixels.extend((245,194+seed*8,124+seed*16,255 if on else 0))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',48,48,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels,9))+chunk(b'IEND',b'')

def create(template: str,directory: Path,id_: str | None=None) -> Path:
    require(template in TEMPLATES,'TEMPLATE',template);require(not directory.exists(),'OUTPUT_EXISTS',str(directory))
    seed=TEMPLATES.index(template);id_=id_ or template
    title,subtitle,kind,duration=[('Alex Rivera','Ideas que merecen una conversación','lower_third',0),
        ('Una nueva voz','Gracias por ser parte de la comunidad','alert',4500),
        ('GOOOOL','Club del Puerto','alert',5000),('Volvemos en','Un momento para preparar lo siguiente','countdown',90000)][seed]
    name=['Minimal Lower Third','Community Alert','Goal Celebration','Countdown Card'][seed]
    widget={'kind':'widget','widget':{'kind':kind,'title':title,'subtitle':subtitle,'width':600,'height':140,
            'background':0x222429,'accent':0xf5c27c,'color':0xf1f2f4,'opacity':1,'duration_ms':duration}}
    def layout(x,y,w,h,order):return dict(x=x,y=y,width=w,height=h,visible=True,order=order)
    bottom=seed==0
    nodes=[{'id':'content','name':name,'type':'primitive','native':widget},
           {'id':'motif','name':'Original stripe motif','type':'primitive','native':{'kind':'image','resource_id':'motif-asset','opacity':.8}}]
    layers=[{'id':'content-layer','node':'content','horizontal':layout(40,360 if bottom else 170,600,140,0),
             'vertical':layout(40,730 if bottom else 340,460,108,0)},
            {'id':'motif-layer','node':'motif','horizontal':layout(660,420 if bottom else 220,48,48,1),
             'vertical':layout(246,858 if bottom else 470,48,48,1)}]
    properties=[]
    def prop(id_,label,type_,default,ref,field,export='compile_time',scope='node',**bounds):
        properties.append({'id':id_,'label':label,'value':{'type':type_,'default':default,**bounds},
            'bindings':[{'scope':scope,'ref':ref,'field':field}],'export':export})
    prop('title','Nombre' if bottom else 'Título','string',title,'content','widget.title','creatorpack_property',max_length=100)
    prop('description','Descripción' if bottom else 'Equipo' if seed==2 else 'Mensaje','string',subtitle,'content','widget.subtitle','creatorpack_property',max_length=160)
    prop('background','Fondo','color',0x222429,'content','widget.background')
    prop('accent','Acento','color',0xf5c27c,'content','widget.accent')
    prop('opacity','Opacidad','number',1,'content','widget.opacity',minimum=0,maximum=1)
    prop('horizontal-x','Posición X horizontal','number',40,'content-layer','horizontal.x',scope='layout',minimum=0,maximum=320)
    prop('vertical-y','Posición Y vertical','number',730 if bottom else 340,'content-layer','vertical.y',scope='layout',minimum=0,maximum=800)
    if duration:prop('duration','Tiempo (ms)','integer',duration,'content','widget.duration_ms',minimum=1000,maximum=3600000 if kind=='countdown' else 60000)
    animations=[];events=[]
    def binding(id_,actions,event_kind='manual.button_pressed',match=None):
        events.append({'id':id_,'event_kind':event_kind,'match':id_ if match is None else match,'description':'Intención visual declarativa; instalar y armar después mediante Motive','actions':actions})
    if kind=='countdown':
        binding('start',[{'type':'countdown_start','source_id':'content'}]);binding('reset',[{'type':'countdown_reset','source_id':'content'}])
        states=[{'id':s,'backend':'native_widget','description':'Estado informativo del countdown; su reloj pertenece al motor nativo'} for s in ('ready','running','completed')]
    else:
        for animation_id,kind_ in [('entry','slide_in'),('exit','slide_out')]:
            animations.append({'id':animation_id,'layer_id':'content-layer','kind':kind_,'easing':'ease_out' if animation_id=='entry' else 'ease_in',
                               'duration_ms':450,'distance':96,'scale_from':.9})
        binding('trigger',[{'type':'trigger_animated_widget','source_id':'content','scene_id':'$scene','layer_id':'content-layer','animation_ref':'entry'}],
                'motive.custom_event' if seed==2 else 'manual.button_pressed','goal-scored' if seed==2 else 'trigger')
        binding('exit',[{'type':'animate','scene_id':'$scene','layer_id':'content-layer','animation_ref':'exit'},{'type':'hide_overlay','source_id':'content'}])
        states=[{'id':s,'backend':'native_widget','description':'Visibilidad del widget nativo; sin máquina de estados adicional'} for s in ('hidden','visible')]
        prop('entry-duration','Duración de entrada (ms)','integer',450,'entry','duration_ms',scope='animation',minimum=100,maximum=10000)
    limitations=['Preview esquemático, no equivalencia de píxeles con libobs.','El motivo decorativo es una capa independiente y permanece visible.',
                 'Las propiedades compile_time generan otra definición; no amplían las cuatro properties de CreatorPack v1.']
    if seed==2:
        score={'kind':'text','text':'2 — 1','font':'Menlo','size':48,'color':0xf1f2f4,'opacity':1,'align':'center','width':300,'height':80,'background':None,'background_opacity':0,'outline':False}
        nodes.append({'id':'score','name':'Score','type':'primitive','native':score})
        layers.append({'id':'score-layer','node':'score','horizontal':layout(340,330,300,80,2),'vertical':layout(120,560,300,80,2)})
        prop('score','Marcador','string','2 — 1','score','text','creatorpack_property',max_length=24)
        limitations.append('Marcador de texto persistente editable; no se incrementa automáticamente con el evento. El widget se oculta por duración; salida animada es una acción explícita.')
    nodes.insert(0,{'id':'root','name':name,'type':'composed','children':[n['id'] for n in nodes]})
    asset=motif(seed)
    doc={'schema_version':1,'kind':'native_element','id':id_,'version':'1.0.0','name':name,'author':'Motive contributors','license':'GPL-3.0-or-later',
         'root':'root','nodes':nodes,'resources':[{'id':'motif-asset','path':'assets/motif.png','kind':'image','sha256':hashlib.sha256(asset).hexdigest(),
          'bytes':len(asset),'width':48,'height':48,'duration_ms':None,'license':'GPL-3.0-or-later'}],
         'layers':layers,'properties':properties,'states':states,'animations':animations,'events':events,'dependencies':[],
         'capabilities':{'required':['widget','image_asset']+(['layer_animation'] if animations else [])+(['text'] if seed==2 else []),'future':[]},
         'variants':[{'id':'warm','properties':{'accent':0xf5c27c}},{'id':'cool','properties':{'accent':0x9ea9f5,'background':0x171b2e}}],
         'budget':{'max_sources':4,'max_layers':8,'max_texture_bytes':96*1024**2,'max_resource_bytes':1024**2},
         'metadata':{'description':name+' · original native composition','category':'overlay','tags':['native','original',template],'limitations':limitations}}
    directory.mkdir(parents=True);(directory/'assets').mkdir();(directory/'assets/motif.png').write_bytes(asset)
    write_json(directory/'assets/provenance.json',{'original':True,'author':'Motive contributors','license':'GPL-3.0-or-later',
               'generator':'element-lab/sdk/templates.py:motif','seed':seed,'sha256':hashlib.sha256(asset).hexdigest()})
    (directory/'LICENSE').write_bytes(read_bytes(LAB.parent,'LICENSE'))
    write_json(directory/'element.json',doc)
    return directory/'element.json'
