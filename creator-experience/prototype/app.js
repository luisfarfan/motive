import {renderMotionWorkbench} from './motion.js';
import {renderLifecycleStudy} from './lifecycle.js';
/* Original Motive Creator Experience presentation prototype, GPL-3.0-or-later.
 * All actions below are local UI rehearsals. No Production/socket/device/provider calls.
 * Manifest and deck documents are read-only inputs; exports are explicit local downloads.
 */
const main = document.querySelector('#main');
const dialog = document.querySelector('#confirm-dialog');
const ids = ['creator-tech', 'neon-arena'];
const packs = new Map();
const state = {motionKey:'creator-tech/tech-title-in',motionOrientation:'horizontal',motionDrafts:new Map(),lifecycle:'ready',lifecycleRevision:7,lifecycleApprovedRevision:null,lifecycleSnapshot:null,lifecycleStep:0,lifecycleDetail:false,lifecycleNote:'',route:'library', selected:'creator-tech', scene:0, orientation:'horizontal', tab:'customize', query:'', category:'all', filter:'all', reduced:false, project:'empty', imageCapability:true, approved:false, planReviewed:false, deckHold:false, missingCapability:false, nextRequest:1, history:[], pending:new Map(), cooldowns:new Map()};
let toastTimer;
let routeRevision=0;
// Keep the skip link out of the hash router so it never changes the current view.
document.querySelector('.skip-link').addEventListener('click',event=>{
  event.preventDefault();
  main.focus({preventScroll:true});
  main.scrollIntoView({block:'start'});
});
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hex = value => `#${Number(value).toString(16).padStart(6,'0')}`;
const bytes = value => value >= 1048576 ? `${(value/1048576).toFixed(1)} MiB` : `${Math.round(value/1024)} KiB`;
const clone = value => structuredClone(value);
const title = id => id === 'creator-tech' ? 'Creator Tech' : 'Neon Arena';
const subtitle = id => id === 'creator-tech' ? 'Ideas claras. Una presencia propia.' : 'La energía de tu comunidad, en escena.';
const category = id => id === 'creator-tech' ? 'Tecnología y educación' : 'Gaming y comunidad';
const description = id => id === 'creator-tech' ? 'Un lenguaje editorial para desarrollar, enseñar y compartir lo que viene. Precisión, espacio y detalles que dejan respirar tus ideas.' : 'Geometría luminosa para los momentos que unen a tu comunidad. Contraste y energía, con todo el espacio para jugar.';
const current = () => packs.get(state.selected);
const manifest = () => current().draft;
const resourceURL = (id, file) => `../packs/${id}/assets/${encodeURIComponent(file)}`;
function previewURL(id, sceneIndex=0, orientation='horizontal') {
  const p = packs.get(id);
  const scene = p.metadata.scenes?.[sceneIndex];
  const slug = scene?.slug || ['starting','live','camera',id==='creator-tech'?'presentation':'community','brb','ending'][sceneIndex];
  return `../packs/${id}/previews/${slug}-${orientation}.png`;
}
function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}
async function readJSON(path) {
  const response = await fetch(path, {cache:'no-store'});
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}
function footer() {
  return '<div class="prototype-footer">Estudio independiente de Creator Experience. Las vistas y los ensayos no están conectados con Production; no instalan recursos ni ejecutan multimedia.</div>';
}
function selectPack(id) {
  if(state.selected!==id) {
    state.scene=0;
    state.tab='customize';
    state.planReviewed=false;
    state.approved=false;
    state.selected=id;
    state.lifecycle='ready';state.lifecycleRevision=7;state.lifecycleApprovedRevision=null;state.lifecycleSnapshot=null;state.lifecycleStep=0;state.lifecycleDetail=false;state.lifecycleNote='';
  }
}
function route() {
  routeRevision++;
  // A different route invalidates an open local confirmation, even on the same pack.
  if(dialog.open)dialog.close('cancel');
  const hash = location.hash.slice(1) || 'library';
  const [section,id,entry] = hash.split('/');
  state.route = ['library','pack','deck','motion'].includes(section) ? section : 'library';
  if(ids.includes(id))selectPack(id);
  if(section==='motion'&&ids.includes(id)&&packs.get(id).draft.animations.some(animation=>animation.id===entry))state.motionKey=`${id}/${entry}`;
  document.querySelectorAll('[data-nav]').forEach(el => {const active=el.dataset.nav === (state.route==='pack'?'library':state.route);el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  render();
}
function render() {
  if (state.route==='library') renderLibrary();
  if (state.route==='pack') renderPack();
  if (state.route==='deck') renderDeck();
  if (state.route==='motion') renderMotion();
}
function renderLibrary() {
  main.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Colecciones de Motive</div><h1>Encuentra tu siguiente escena.</h1><p>Dos universos visuales. Una forma más simple de crear.<br>Elige una colección y hazla tuya.</p></div><span class="subtle-count">Vol. 01 / Colección original</span></div>
  <div class="toolbar"><label class="search-wrap"><span class="sr-only">Buscar colecciones</span><input type="search" id="search" placeholder="Buscar por estilo, uso o nombre…" value="${escape(state.query)}" aria-label="Buscar colecciones"></label><button class="chip ${state.category==='all'?'active':''}" data-category="all" aria-pressed="${state.category==='all'}">Todas</button><button class="chip ${state.category==='tech'?'active':''}" data-category="tech" aria-pressed="${state.category==='tech'}">Tecnología</button><button class="chip ${state.category==='gaming'?'active':''}" data-category="gaming" aria-pressed="${state.category==='gaming'}">Gaming</button><select class="filter-select" id="compat-filter" aria-label="Filtrar colecciones"><option value="all">Todos los recursos</option><option value="offline">Uso offline</option><option value="native">Sin imágenes</option></select></div>
  <section class="cards" id="pack-results" aria-label="Colecciones disponibles" aria-live="polite"></section>
  <div class="support-strip"><div><h3>Diseño que puedes hacer tuyo</h3><p>Textos nativos y propiedades declaradas. Personaliza sin perder la coherencia de la colección.</p></div><div><h3>Una colección, dos orientaciones</h3><p>Composiciones propias para 16:9 y 9:16. Pensadas desde el mismo espacio lógico de Motive.</p></div><div><h3>Tus recursos se quedan contigo</h3><p>Archivos locales, fuentes de diseño editables y licencia abierta. La biblioteca no exige una cuenta.</p></div></div>
  <div class="page-note"><span>Previews de diseño · Widgets ilustrados en estado activo · Sin captura nativa</span><span>Originales de Motive · GPL-3.0-or-later</span></div>`;
  document.querySelector('#compat-filter').value=state.filter;
  document.querySelector('#search').addEventListener('input', e => {state.query=e.target.value;renderCards();});
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click',()=>{state.category=button.dataset.category;renderLibrary();}));
  document.querySelector('#compat-filter').addEventListener('change',e=>{state.filter=e.target.value;renderCards();});
  renderCards();
}
function renderCards() {
  const matches=ids.filter(id=>{
    const p=packs.get(id); const text=[title(id),description(id),category(id),...(p.metadata.tags||[])].join(' ').toLowerCase();
    return text.includes(state.query.toLowerCase()) && (state.category==='all'||(state.category==='tech'&&id==='creator-tech')||(state.category==='gaming'&&id==='neon-arena')) && (state.filter!=='native'||p.original.resources.length===0);
  });
  document.querySelector('#pack-results').innerHTML=matches.length?matches.map((id)=>{
    const p=packs.get(id).original;
    return `<article class="pack-card"><a class="cover-link" href="#pack/${id}" aria-label="Explorar ${title(id)}"><img src="${previewURL(id)}" alt="${title(id)}: composición Starting Soon en horizontal" width="960" height="540"></a><div class="card-heading"><h2><a href="#pack/${id}">${title(id)}</a></h2><span class="category-label">${category(id)}</span></div><p class="card-copy">${description(id)}</p><div class="pack-compatibility">Instalación pendiente · H14 admite MATCHDAY</div><p class="card-capabilities">${p.requires.map(capability=>({text:'Texto',shape:'Formas',widget:'Widgets',image_asset:'PNG',layer_animation:'Animación',scene_transition:'Cut/Fade'}[capability]||capability)).join(' · ')}</p><div class="card-footer"><span>${p.scenes.length} composiciones</span><span aria-hidden="true">·</span><span>${p.resources.length} PNG</span><span aria-hidden="true">·</span><span>16:9 + 9:16</span><span aria-hidden="true">·</span><span>v${escape(p.version)}</span><a href="#pack/${id}">Explorar colección →</a></div></article>`;
  }).join(''):'<div class="empty"><h2>No hay colecciones con esos filtros.</h2><p>Prueba otro término o vuelve a ver todos los recursos.</p><button class="button" id="clear-filters" style="margin-top:18px">Restablecer filtros</button></div>';
  document.querySelector('#clear-filters')?.addEventListener('click',()=>{state.query='';state.category='all';state.filter='all';renderLibrary();});
}
function renderPack() {
  const p=manifest();
  main.innerHTML=`<a class="back" href="#library">← Biblioteca de colecciones</a><div class="page-heading detail-heading"><div><div class="eyebrow">${category(p.id)}</div><h1>${title(p.id)}</h1><p>${subtitle(p.id)}</p></div><div class="detail-actions"><a class="button" href="#deck/${p.id}">Abrir Live Deck</a><button class="button primary" id="open-plan">Revisar plan</button></div></div><div class="tabs" aria-label="Secciones de la colección">${[['customize','Personalizar'],['details','La colección'],['plan','Plan de instalación'],['lifecycle','Estados de instalación']].map(([id,label])=>`<button class="tab ${state.tab===id?'active':''}" data-tab="${id}" aria-pressed="${state.tab===id}">${label}</button>`).join('')}</div><div id="pack-content"></div>${footer()}`;
  document.querySelectorAll('[data-tab]').forEach(el=>el.addEventListener('click',()=>{state.tab=el.dataset.tab;renderPack();document.querySelector(`[data-tab="${state.tab}"]`).focus({preventScroll:true});}));
  document.querySelector('#open-plan').addEventListener('click',()=>{state.tab='plan';renderPack();});
  if(state.tab==='customize') renderCustomizer();
  if(state.tab==='details') renderDetails();
  if(state.tab==='plan') renderPlan();
  if(state.tab==='lifecycle') renderLifecycle();
}
function renderCustomizer() {
  const p=manifest(); const scene=p.scenes[state.scene]||p.scenes[0];
  document.querySelector('#pack-content').innerHTML=`<div class="detail-grid"><section aria-label="Vista previa de la colección"><div class="stage-toolbar"><span class="stage-title">${escape(scene.name)}</span><div class="segmented" aria-label="Orientación">${[['horizontal','16:9'],['vertical','9:16']].map(([id,label])=>`<button data-orientation="${id}" class="${state.orientation===id?'active':''}" aria-pressed="${state.orientation===id}">${label}</button>`).join('')}</div></div><div class="preview-stage ${state.orientation}" id="stage"></div><p class="preview-caption">${state.orientation==='horizontal'?'960 × 540':'540 × 960'} · Vista de diseño aproximada. Widgets ilustrados activos; la importación no los dispara. Tipografía final por verificar en Motive.</p><div class="scene-rail" aria-label="Composiciones">${p.scenes.map((s,i)=>`<button class="scene-thumb ${state.scene===i?'active':''}" data-scene="${i}" aria-pressed="${state.scene===i}"><img src="${previewURL(p.id,i)}" alt="" width="960" height="540"><span>${escape(s.name)}</span></button>`).join('')}</div></section><aside class="inspector" aria-label="Personalización"><h3>Tu identidad, en escena</h3><p>Las propiedades se comparten entre escenas. Los cambios permanecen en esta vista hasta que descargues el manifiesto.</p><label class="field"><span class="field-label">Estilo de fondo</span><select id="visual-style"><option value="original">Fondo original de la colección</option><option value="deep-ink">Tinta profunda · fondo neutro</option><option value="custom" disabled>Color de fondo personalizado</option></select><small>Solo modifica la propiedad de color del fondo. El motivo, marco, texto y widgets conservan sus colores.</small></label><label class="field"><span class="field-label">Variante de movimiento</span><select id="style-variant"><option value="original">Colección original</option><option value="reduced-motion">Receta de movimiento reducido</option></select><small id="style-description">${current().style==='reduced-motion'?'Receta: Show/Hide o Fade100 y Cut. No añade un campo al manifiesto v1.':'Textos, formas y gráficos originales de la colección.'}</small></label><div class="inspector-fields">${p.properties.map(property=>propertyField(property,p)).join('')}</div><p id="property-error" class="field-error" role="alert"></p><details class="resource-controls"><summary>Recursos gráficos · ${p.resources.length} PNG</summary><p id="resource-replacement-limit">Pack v1 no declara una propiedad para sustituir imágenes. Los recursos conservan sus checksums y dimensiones.</p>${p.resources.map(resource=>`<div class="resource-control"><code>${escape(resource.file_name)}</code><button class="button" disabled aria-describedby="resource-replacement-limit">Sustituir recurso</button></div>`).join('')}</details><div class="inspector-footer"><button class="button" id="reset-properties">Restablecer</button><button class="button primary" id="export-manifest">Descargar manifiesto</button></div></aside></div>`;
  paintStage();
  const background=p.properties.find(property=>property.id==='background'&&property.target==='shape_color');
  const originalBackground=current().original.properties.find(property=>property.id===background?.id)?.value.value;
  const visualStyle=document.querySelector('#visual-style');
  visualStyle.value=background?.value.value===originalBackground?'original':background?.value.value===0x101216?'deep-ink':'custom';
  visualStyle.disabled=!background;
  visualStyle.addEventListener('change',event=>{
    const color=event.target.value==='deep-ink'?0x101216:originalBackground;
    background.value.value=color;
    p.overlays.find(overlay=>overlay.id===background.overlay_id).definition.color=color;
    state.planReviewed=false;state.approved=false;
    renderCustomizer();
    document.querySelector('#visual-style').focus({preventScroll:true});
    toast('Estilo aplicado solo a background.shape_color. Los demás recursos conservan su identidad.');
  });
  document.querySelector('#style-variant').value=current().style||'original';
  document.querySelector('#style-variant').addEventListener('change',event=>{current().style=event.target.value;renderCustomizer();document.querySelector('#style-variant').focus({preventScroll:true});toast(event.target.value==='reduced-motion'?'Receta reducida seleccionada para los previews; no se modifica el esquema v1.':'Colección original seleccionada para los previews.');});
  document.querySelectorAll('[data-orientation]').forEach(el=>el.addEventListener('click',()=>{state.orientation=el.dataset.orientation;renderCustomizer();document.querySelector(`[data-orientation="${state.orientation}"]`).focus({preventScroll:true});}));
  document.querySelectorAll('[data-scene]').forEach(el=>el.addEventListener('click',()=>{state.scene=Number(el.dataset.scene);renderCustomizer();document.querySelector(`[data-scene="${state.scene}"]`).focus({preventScroll:true});}));
  document.querySelectorAll('[data-property]').forEach(el=>el.addEventListener('input',()=>updateProperty(el)));
  document.querySelector('#reset-properties').addEventListener('click',()=>{current().draft=clone(current().original);current().style='original';state.planReviewed=false;state.approved=false;renderCustomizer();toast('Propiedades originales restauradas en el prototipo.');});
  document.querySelector('#export-manifest').addEventListener('click',()=>{
    if(document.querySelector('[aria-invalid="true"]')){toast('Corrige el campo señalado antes de descargar.');return;}
    downloadJSON(`${p.id}-customized.json`,manifest());toast('Manifiesto descargado. Valídalo con el validador Rust antes de instalar.');
  });
}
function propertyField(property,p) {
  const overlay=p.overlays.find(o=>o.id===property.overlay_id);
  const value=property.value.value;
  const color=property.target==='shape_color';
  const limit=property.target==='widget_title'?160:property.target==='widget_subtitle'?256:Math.min(4096,Math.floor(24576/(overlay.definition.size||8)));
  return `<label class="field"><span class="field-label">${escape(property.label)}</span>${color?`<input type="color" value="${hex(value)}" data-property="${escape(property.id)}" aria-label="${escape(property.label)}">`:`<textarea rows="${String(value).includes('\n')?3:2}" data-property="${escape(property.id)}" maxlength="${limit}" aria-label="${escape(property.label)}">${escape(value)}</textarea>`}<small>${color?'Color de esta forma nativa. El motivo y el marco conservan su color.':`Texto editable · ${limit} caracteres como máximo`}</small></label>`;
}
function updateProperty(input) {
  const p=manifest();const property=p.properties.find(prop=>prop.id===input.dataset.property);const overlay=p.overlays.find(o=>o.id===property.overlay_id);const d=overlay.definition;
  let value=input.value;let error='';
  if(property.target==='shape_color')value=parseInt(value.slice(1),16);
  else {
    const count=Array.from(value).length;const lines=value.replace(/\n$/,'').split('\n').length;
    if(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/.test(value))error='El texto contiene caracteres de control no admitidos.';
    if(new TextEncoder().encode(value).length>4096)error='El texto supera el límite de 4096 bytes.';
    if(property.target==='text_content'&&(lines>16||count*d.size>24576))error='El texto supera el presupuesto de render de esta fuente.';
    if(property.target==='widget_title'&&(count>160||lines>3))error='El título admite hasta 160 caracteres y 3 líneas.';
    if(property.target==='widget_subtitle'&&(count>256||lines>4))error='El subtítulo admite hasta 256 caracteres y 4 líneas.';
  }
  input.setAttribute('aria-invalid',String(Boolean(error)));document.querySelector('#property-error').textContent=error;
  if(error)return;
  property.value.value=value;
  if(property.target==='text_content')d.text=value;
  if(property.target==='widget_title')d.widget.title=value;
  if(property.target==='widget_subtitle')d.widget.subtitle=value;
  if(property.target==='shape_color') {
    d.color=value;
    if(property.id==='background') {
      const original=current().original.properties.find(item=>item.id===property.id).value.value;
      document.querySelector('#visual-style').value=value===original?'original':value===0x101216?'deep-ink':'custom';
    }
  }
  state.planReviewed=false;state.approved=false;paintStage();
}
function paintStage() {document.querySelector('#stage').innerHTML=sceneSVG(manifest(),manifest().scenes[state.scene],state.orientation);}
function textSVG(text,x,y,w,h,size,color,font='Helvetica',align='left') {
  const lines=String(text).split('\n');const fitted=Math.min(size,w/Math.max(1,...lines.map(l=>Array.from(l).length*.59)),h/(lines.length*1.25));
  const tx=align==='center'?x+w/2:align==='right'?x+w:x;
  const anchor=align==='center'?'middle':align==='right'?'end':'start';
  const baseline=y+(h-fitted*lines.length*1.15)/2+fitted*.86;
  return lines.map((line,i)=>`<text x="${tx}" y="${baseline+i*fitted*1.15}" font-size="${fitted}" fill="${hex(color)}" font-family="${escape(font)}, sans-serif" font-weight="400" text-anchor="${anchor}">${escape(line)}</text>`).join('');
}
function sceneSVG(p,scene,orientation) {
  const [w,h]=orientation==='horizontal'?[960,540]:[540,960];
  let svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="Vista de diseño de ${escape(scene.name)}"><title>${escape(scene.name)}: aproximación de diseño, no salida nativa</title>`;
  for(const layer of [...scene.layers].sort((a,b)=>a[orientation].order-b[orientation].order)) {
    const l=layer[orientation];if(!l.visible)continue;
    const d=p.overlays.find(o=>o.id===layer.overlay_id).definition;
    let x=l.x,y=l.y,lw=l.width,lh=l.height;
    if(d.kind!=='shape'||d.shape!=='rectangle') {
      const intrinsic=d.kind==='widget'?d.widget:d.kind==='image'?p.resources.find(r=>r.id===d.resource_id):d;
      if(intrinsic?.width&&intrinsic?.height){const scale=Math.min(lw/intrinsic.width,lh/intrinsic.height);const nw=intrinsic.width*scale,nh=intrinsic.height*scale;x+=(lw-nw)/2;y+=(lh-nh)/2;lw=nw;lh=nh;}
    }
    svg+=`<g data-layer="${escape(layer.id)}" opacity="${d.opacity??d.widget?.opacity??1}">`;
    if(d.kind==='shape') {
      const stroke=d.border_color===null?'none':hex(d.border_color);const bw=d.border_width;
      svg+=d.shape==='circle'?`<ellipse cx="${x+lw/2}" cy="${y+lh/2}" rx="${lw/2}" ry="${lh/2}" fill="${hex(d.color)}" stroke="${stroke}" stroke-width="${bw}"/>`:`<rect x="${x}" y="${y}" width="${lw}" height="${lh}" fill="${hex(d.color)}" stroke="${stroke}" stroke-width="${bw}"/>`;
    }
    if(d.kind==='image') {const r=p.resources.find(r=>r.id===d.resource_id);svg+=`<image href="${resourceURL(p.id,r.file_name)}" x="${x}" y="${y}" width="${lw}" height="${lh}" preserveAspectRatio="xMidYMid meet"/>`;}
    if(d.kind==='text') {
      if(d.background!==null)svg+=`<rect x="${x}" y="${y}" width="${lw}" height="${lh}" fill="${hex(d.background)}" opacity="${d.background_opacity}"/>`;
      svg+=textSVG(d.text,x,y,lw,lh,d.size*(lw/d.width),d.color,d.font,d.align);
    }
    if(d.kind==='widget') {
      const z=d.widget;svg+=`<rect x="${x}" y="${y}" width="${lw}" height="${lh}" fill="${hex(z.background)}"/><rect x="${x}" y="${y}" width="${Math.max(3,lw*.012)}" height="${lh}" fill="${hex(z.accent)}"/>`;
      if(z.kind==='countdown'){const seconds=Math.ceil(z.duration_ms/1000);svg+=textSVG(z.title,x+16,y+lh*.08,lw-32,lh*.22,22,z.color,'Helvetica','center');svg+=textSVG(`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`,x+16,y+lh*.34,lw-32,lh*.56,58,z.color,'Menlo','center');}
      else {svg+=textSVG(z.title,x+lw*.05,y+lh*.12,lw*.9,lh*.44,32,z.color);svg+=textSVG(z.subtitle,x+lw*.05,y+lh*.64,lw*.9,lh*.22,20,z.color);}
    }
    svg+='</g>';
  }
  return svg+'</svg>';
}
function textureEstimate(p) {
  return p.overlays.reduce((total,{definition:d})=>{if(d.kind==='image')return total+2048*2048*4;if(d.kind==='video')return total+1920*1080*16;const s=d.widget||d;return total+s.width*s.height*4*(d.kind==='text'?3:d.kind==='widget'?4:1);},0);
}
function renderDetails() {
  const p=manifest();const meta=current().metadata;
  document.querySelector('#pack-content').innerHTML=`<div class="notice neutral">Colección declarativa v${escape(p.version)}. Los recursos y el manifiesto están disponibles localmente; la instalación real y los bindings de Show Control requieren el adaptador oficial de Motive. El instalador H14 observado solo admite MATCHDAY sin recursos externos; estos dos packs aún no son instalables por esa ruta.</div><div class="stat-grid"><div class="stat"><strong>${p.scenes.length}</strong><span>Escenas con ambos layouts</span></div><div class="stat"><strong>${p.overlays.length}</strong><span>Fuentes reutilizables</span></div><div class="stat"><strong>${p.animations.length}</strong><span>Animaciones declaradas</span></div><div class="stat"><strong>${p.properties.length}</strong><span>Propiedades editables</span></div></div><div class="info-columns"><section><h3>Una identidad visual completa</h3><p>${description(p.id)}</p><div class="tag-list">${(meta.tags||[category(p.id),'Offline','16:9','9:16']).map(tag=>`<span class="tag">${escape(tag)}</span>`).join('')}</div><h3 style="margin-top:25px">Escenas incluidas</h3><ul>${p.scenes.map(s=>`<li><button class="detail-link" data-detail-scene="${escape(s.id)}">${escape(s.name)} · Ver ambos layouts</button></li>`).join('')}</ul><h3 style="margin-top:25px">Propiedades editables</h3><ul>${p.properties.map(property=>`<li>${escape(property.label)} <code>${escape(property.target)}</code></li>`).join('')}</ul><h3 style="margin-top:25px">Autor y licencia</h3><p>${escape(p.author)}<br>${escape(p.license)} · Recursos originales.<br>Fuentes nativas Helvetica, Arial o Menlo; no se distribuyen tipografías.</p></section><section><h3>Recursos y compatibilidad</h3>${p.resources.map(r=>`<div class="asset-row"><code>${escape(r.file_name)}</code><span>${r.width} × ${r.height}</span></div>`).join('')}<p style="margin:15px 0">${bytes(textureEstimate(p))} estimados de texturas. Este cálculo de planificación no mide RSS ni decodificación nativa.</p><h3>Capacidades declaradas</h3><div class="tag-list">${p.requires.map(c=>`<span class="tag">${escape(c)}</span>`).join('')}</div><h3 style="margin-top:25px">Límites que importan</h3><p>Cámaras y capturas se añaden después, con selección explícita. Los marcos son imágenes; no son dispositivos. Widgets y animaciones necesitan activación explícita. Los eventos de comunidad son ejemplos de reglas, sin proveedor conectado.</p><h3 style="margin-top:25px">Animaciones incluidas</h3><ul>${p.animations.map(animation=>`<li><a class="detail-link" href="#motion/${p.id}/${escape(animation.id)}">${escape(animation.id)} · ${animation.duration_ms} ms</a></li>`).join('')}</ul><a class="button" href="../packs/${p.id}/README.md" style="margin-top:18px">Leer documentación del pack</a></section></div>`;
  document.querySelectorAll('[data-detail-scene]').forEach(button=>button.addEventListener('click',()=>{state.scene=p.scenes.findIndex(scene=>scene.id===button.dataset.detailScene);state.tab='customize';renderPack();}));
}
function planFacts() {
  const p=manifest();const existing=state.project==='empty'?[0,0,0]:state.project==='matchday'?[4,12,23]:[6,12,27];
  const added=[p.scenes.length,p.overlays.length,p.scenes.reduce((n,s)=>n+s.layers.length,0)];const limits=[8,16,32];
  const errors=[];added.forEach((n,i)=>{if(n+existing[i]>limits[i])errors.push(`El proyecto superaría el límite de ${limits[i]} ${['escenas','fuentes','capas'][i]}.`);});
  if(state.project==='duplicate')errors.push('Los identificadores de esta colección ya existen en el escenario de prueba. No se sobrescriben.');
  if(!state.imageCapability&&p.requires.includes('image_asset'))errors.push('Falta image_asset en el escenario de prueba. No se sustituyen recursos.');
  return {existing,added,limits,errors};
}
function renderPlan() {
  const p=manifest();const facts=planFacts();
  document.querySelector('#pack-content').innerHTML=`<div class="plan-layout"><section><h3>Comprueba el espacio antes de instalar</h3><p style="font-size:12px">Este plan es una propuesta local. La capacidad definitiva y la revisión del proyecto las comprueba el instalador de Motive.</p><div class="plan-controls"><label class="field"><span class="field-label">Proyecto de ejemplo</span><select id="project-state"><option value="empty">Proyecto vacío</option><option value="matchday">Con MATCHDAY (4 / 12 / 23)</option><option value="duplicate">Ya contiene esta colección</option></select></label><label class="field"><span class="field-label">Capacidad de imágenes</span><select id="image-capability"><option value="yes">Disponible en el ejemplo</option><option value="no">No disponible en el ejemplo</option></select></label></div><table class="plan-table"><thead><tr><th>Recurso</th><th>Existente</th><th>Pack</th><th>Total / Límite</th></tr></thead><tbody>${['Escenas','Fuentes','Capas'].map((name,i)=>`<tr><td>${name}</td><td>${facts.existing[i]}</td><td>+${facts.added[i]}</td><td class="${facts.existing[i]+facts.added[i]>facts.limits[i]?'over':''}">${facts.existing[i]+facts.added[i]} / ${facts.limits[i]}</td></tr>`).join('')}</tbody></table>${facts.errors.length?`<div class="notice" role="alert"><strong>El plan requiere cambios.</strong><ul style="margin:5px 0;padding-left:17px">${facts.errors.map(e=>`<li>${escape(e)}</li>`).join('')}</ul>Usa un proyecto vacío o prepara una selección compatible con el instalador oficial.</div>`:`<div class="notice good">La composición cabe en este ejemplo. Quedan ${facts.limits[0]-facts.added[0]} escenas, ${facts.limits[1]-facts.added[1]} fuentes y ${facts.limits[2]-facts.added[2]} capas antes de añadir capturas.</div>`}<ol class="steps"><li>Verificar licencia, metadatos, checksums y bytes de los recursos.</li><li>Consultar capacidades, estado idle y revisión del proyecto.</li><li>Crear escenas y fuentes; resolver los IDs devueltos por el núcleo.</li><li>Aplicar ambos layouts y registrar bindings de reglas.</li><li>Reconciliar el resultado observado, sin iniciar timers ni salidas.</li></ol><label class="check-line"><input type="checkbox" id="approve-plan" ${state.approved?'checked':''}><span>He revisado el plan de ejemplo. Entiendo que esta confirmación no instala recursos.</span></label><button class="button primary" id="confirm-plan" ${facts.errors.length||!state.approved?'disabled':''}>Confirmar ensayo del plan</button><div id="plan-result" style="margin-top:14px">${state.planReviewed?'<div class="notice good">Plan revisado (simulación). No se ha instalado el pack ni se ha conectado con Production.</div>':''}</div></section><aside><h3>Qué se prepararía</h3>${p.resources.map(r=>`<div class="asset-row"><code>${escape(r.file_name)}</code><span>${bytes(r.bytes??r.size_bytes??0)}</span></div>`).join('')}<div class="asset-row"><span>Animaciones</span><span>${p.animations.length} definiciones</span></div><div class="asset-row"><span>Texturas estimadas</span><span>${bytes(textureEstimate(p))}</span></div><div class="asset-row"><span>Límite del pack</span><span>${bytes(p.budget.max_estimated_texture_bytes)}</span></div><div class="notice neutral" style="margin-top:20px">El plan no es ejecutable desde este prototipo. El instalador H14 observado solo acepta MATCHDAY y rechaza recursos externos. La instalación de estos packs queda pendiente de soporte oficial para medios, IDs reales, revisiones y errores parciales.</div><button class="button" id="download-plan" style="margin-top:15px;width:100%">Descargar revisión del plan</button></aside></div>`;
  document.querySelector('#project-state').value=state.project;
  document.querySelector('#image-capability').value=state.imageCapability?'yes':'no';
  document.querySelector('#project-state').addEventListener('change',e=>{state.project=e.target.value;state.approved=false;state.planReviewed=false;renderPlan();document.querySelector('#project-state').focus({preventScroll:true});});
  document.querySelector('#image-capability').addEventListener('change',e=>{state.imageCapability=e.target.value==='yes';state.approved=false;state.planReviewed=false;renderPlan();document.querySelector('#image-capability').focus({preventScroll:true});});
  document.querySelector('#approve-plan').addEventListener('change',e=>{state.approved=e.target.checked;renderPlan();document.querySelector('#approve-plan').focus({preventScroll:true});});
  document.querySelector('#confirm-plan').addEventListener('click',()=>{state.planReviewed=true;renderPlan();toast('Ensayo confirmado. Ningún recurso instalado.');});
  document.querySelector('#download-plan').addEventListener('click',()=>downloadJSON(`${p.id}-plan-review.json`,{document:'creator-experience-plan-review',version:1,pack_id:p.id,pack_version:p.version,simulated:true,executable:false,requires_idle:true,project_scenario:state.project,resources:clone(p.resources),counts:facts,estimated_texture_bytes:textureEstimate(p),reviewed:state.planReviewed}));
}
function renderLifecycle() {
  renderLifecycleStudy({
    host:document.querySelector('#pack-content'),
    pack:manifest(),
    model:state,
    onCustomize:()=>{state.tab='customize';renderPack();},
  });
}
function downloadJSON(filename,value) {
  const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;window.document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function deckKey(button) {return `${state.selected}:${button.id}`;}
function ruleMotionCapabilities(rule) {
  const required=new Set();
  function visit(action,depth=0) {
    if(depth>4)return;
    if(action.type==='sequence') {for(const child of action.actions||[])visit(child,depth+1);return;}
    if(['animate','cancel_animation'].includes(action.type))required.add('layer_animation');
    if(action.type==='select_scene')required.add('scene_transition');
  }
  for(const action of rule?.actions||[])visit(action);
  return required;
}
function deckState(button) {
  const rule=current().rules?.rules?.find(r=>r.id===button.target.rule_id);
  if(rule&&rule.enabled===false)return {state:'disabled',label:'Regla deshabilitada'};
  if(!button.enabled)return {state:'disabled',label:'Deshabilitado'};
  if(state.pending.has(deckKey(button)))return {state:'pending',label:'Ensayo pendiente'};
  const remaining=(state.cooldowns.get(deckKey(button))||0)-performance.now();
  if(remaining>0)return {state:'cooling_down',label:`Espera ${Math.ceil(remaining/1000)} s`};
  const required=ruleMotionCapabilities(rule);
  if(button.target.kind==='animation')required.add('layer_animation');
  if(button.target.kind==='scene')required.add('scene_transition');
  if(state.missingCapability&&required.size)return {state:'missing',label:`Falta ${[...required].join(' / ')} (ejemplo)`};
  return {state:'ready',label:button.sensitive?'Requiere confirmación':'Listo para ensayar'};
}

const actionNames={overlay:'Visibilidad',animation:'Animación',scene:'Escena',countdown:'Countdown',rule:'Regla',composite:'Acciones agrupadas'};
function renderDeck() {
  const p=manifest();const deck=current().deck;
  main.innerHTML=`<div class="page-heading"><div><div class="eyebrow">Show Control / Ensayo de interfaz</div><h1>Cada momento, a mano.</h1><p>Un espacio para preparar tus acciones, comprobar los estados<br>y ensayar tu siguiente directo.</p></div></div><div class="deck-toolbar"><select id="deck-pack" aria-label="Colección del Live Deck">${ids.map(id=>`<option value="${id}">${title(id)}</option>`).join('')}</select><div class="notice neutral">Ensayo local · Ninguna acción multimedia real</div></div><div class="deck-layout"><section><div id="deck-groups">${deck.groups.slice().sort((a,b)=>a.order-b.order).map(group=>`<section class="deck-group"><h3>${escape(group.label)}</h3><div class="deck-grid">${deck.buttons.filter(b=>b.group_id===group.id).sort((a,b)=>a.order-b.order).map(button=>deckButton(button)).join('')}</div></section>`).join('')}</div><div class="deck-options"><label><input type="checkbox" id="hold-pending" ${state.deckHold?'checked':''}> Mantener ensayo pendiente</label><label><input type="checkbox" id="missing-capability" ${state.missingCapability?'checked':''}> Sin animación/transición (ejemplo)</label></div><div class="notice neutral" style="margin-top:19px">Los botones usan targets declarados del Deck v1. Los atajos se muestran como referencia; no se registran atajos del sistema. La confirmación local del prototipo no autoriza operaciones reales.</div></section><aside class="history" aria-label="Historial del ensayo"><h3>Actividad de esta sesión</h3><p>Solo ensayos del prototipo. Sin recibos de Production.</p><div id="pending-list"></div><ol class="history-list" id="history-list"></ol></aside></div>${footer()}`;
  document.querySelector('#deck-pack').value=p.id;
  document.querySelector('#deck-pack').addEventListener('change',e=>{location.hash=`deck/${e.target.value}`;});
  document.querySelector('#hold-pending').addEventListener('change',e=>{state.deckHold=e.target.checked;});
  document.querySelector('#missing-capability').addEventListener('change',e=>{state.missingCapability=e.target.checked;renderDeck();});
  bindDeckButtons();renderHistory();
}
function deckButton(button) {
  const status=deckState(button);const disabled=['disabled','pending','cooling_down','missing'].includes(status.state);
  const shortcut=button.shortcut?`${button.shortcut.command?'⌘':''}${button.shortcut.option?'⌥':''}${button.shortcut.shift?'⇧':''}${button.shortcut.key.toUpperCase()}`:'';
  return `<button class="deck-button" data-button="${escape(button.id)}" data-state="${status.state}" ${disabled?'disabled':''} aria-label="${escape(button.label)}: ${status.label}"><span class="target-kind">${actionNames[button.target.kind]}</span><span class="shortcut" aria-hidden="true">${escape(shortcut)}</span><strong>${escape(button.label)}</strong><small>${status.label}</small></button>`;
}
function bindDeckButtons() {document.querySelectorAll('[data-button]').forEach(el=>el.addEventListener('click',()=>pressButton(current().deck.buttons.find(b=>b.id===el.dataset.button))));}
function remember(button,phase,requestId=null,packId=state.selected) {
  state.history.unshift({pack:packId,button:button.label,phase,requestId,time:new Date().toLocaleTimeString('es-PE',{hour:'2-digit',minute:'2-digit',second:'2-digit'})});state.history=state.history.slice(0,64);renderHistory();
}
async function pressButton(button) {
  if(deckState(button).state!=='ready')return;
  const requestedPackId=state.selected;
  const requestedRevision=routeRevision;
  if(button.sensitive) {
    remember(button,'Esperando confirmación',null,requestedPackId);
    document.querySelector('#dialog-title').textContent=`Ensayar «${button.label}»`;
    document.querySelector('#dialog-description').textContent='Este botón requiere confirmación en el modelo del Deck. El ensayo solo añade un registro local y muestra su estado pendiente.';
    document.querySelector('#dialog-target').textContent=JSON.stringify(button.target,null,2);
    // Escape leaves returnValue untouched, so reset it before every opening.
    dialog.returnValue='cancel';
    dialog.showModal();
    const answer=await new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true}));
    if(answer!=='confirm'){
      remember(button,'Confirmación descartada (UI)',null,requestedPackId);
      return;
    }
  }
  if(routeRevision!==requestedRevision||state.route!=='deck'||state.selected!==requestedPackId) {
    remember(button,'Confirmación obsoleta (UI)',null,requestedPackId);
    return;
  }
  // Recheck pending/cooldown/capabilities after a potentially asynchronous confirmation.
  if(deckState(button).state!=='ready') {
    remember(button,'Estado cambiado; ensayo rechazado (UI)',null,requestedPackId);
    return;
  }
  const key=`${requestedPackId}:${button.id}`;
  const requestId=state.nextRequest++;
  state.cooldowns.set(key,performance.now()+button.cooldown_ms);
  state.pending.set(key,{requestId,button:clone(button),pack:requestedPackId});
  remember(button,'Pendiente (ensayo)',requestId,requestedPackId);
  renderDeck();
  if(!state.deckHold)setTimeout(()=>finishRequest(key,'Simulado · sin ejecución',requestId),900);
}

function finishRequest(key,phase,expectedRequestId=null) {
  const pending=state.pending.get(key);
  if(!pending||(expectedRequestId!==null&&pending.requestId!==expectedRequestId))return;
  state.pending.delete(key);
  state.history.unshift({pack:pending.pack,button:pending.button.label,phase,requestId:pending.requestId,time:new Date().toLocaleTimeString('es-PE',{hour:'2-digit',minute:'2-digit',second:'2-digit'})});state.history=state.history.slice(0,64);
  if(state.route==='deck')renderDeck();
}
function renderHistory() {
  const history=document.querySelector('#history-list');if(!history)return;
  const entries=state.history.filter(h=>h.pack===state.selected);
  history.innerHTML=entries.length?entries.slice(0,10).map(h=>`<li><strong>${escape(h.button)}</strong><span>${escape(h.phase)}</span><span>${h.time}${h.requestId?` · Solicitud ${h.requestId}`:''}</span></li>`).join(''):'<li class="history-empty">Todavía no hay ensayos. Elige una acción para revisar su comportamiento.</li>';
  document.querySelector('#pending-list').innerHTML=[...state.pending].filter(([,v])=>v.pack===state.selected).map(([key,v])=>`<div class="pending-card"><p><strong>${escape(v.button.label)}</strong><br>Solicitud ${v.requestId} pendiente en el ensayo.</p><div class="history-actions"><button class="button" data-finish="${escape(key)}">Completar ensayo</button><button class="button" data-cancel="${escape(key)}">Cancelar</button><button class="button" data-reject="${escape(key)}">Simular rechazo</button></div></div>`).join('');
  document.querySelectorAll('[data-finish]').forEach(b=>b.addEventListener('click',()=>finishRequest(b.dataset.finish,'Simulado · sin ejecución')));
  document.querySelectorAll('[data-cancel]').forEach(b=>b.addEventListener('click',()=>finishRequest(b.dataset.cancel,'Cancelado (ensayo)')));
  document.querySelectorAll('[data-reject]').forEach(b=>b.addEventListener('click',()=>finishRequest(b.dataset.reject,'Rechazado · SIMULATED_REJECTION (ensayo)')));
}
// Presentation-only cooldown updates. This timer never drives media or native animations.
setInterval(()=>{
  if(state.route!=='deck'||!current()?.deck)return;
  document.querySelectorAll('[data-button]').forEach(el=>{const b=current().deck.buttons.find(b=>b.id===el.dataset.button);const s=deckState(b);el.dataset.state=s.state;el.disabled=['disabled','pending','cooling_down','missing'].includes(s.state);el.querySelector('small').textContent=s.label;el.setAttribute('aria-label',`${b.label}: ${s.label}`);});
},250);
function renderMotion() {
  renderMotionWorkbench({
    host:main,packs,state,sceneSVG,previewURL,title,footer,
    onInspect:(id,sceneId)=>{
      selectPack(id);
      state.scene=packs.get(id).draft.scenes.findIndex(scene=>scene.id===sceneId);
      state.tab='customize';
      location.hash=`pack/${id}`;
    },
  });
}

try {
  await Promise.all(ids.map(async id=>{
    const [original,metadata,deck,rules]=await Promise.all([readJSON(`../packs/${id}/manifest.json`),readJSON(`../packs/${id}/metadata.json`),readJSON(`../packs/${id}/deck.json`),readJSON(`../packs/${id}/rules.json`)]);
    packs.set(id,{original,metadata,deck,rules,draft:clone(original)});
  }));
  document.querySelector('[data-nav="motion"] span').textContent=[...packs.values()].reduce((total,pack)=>total+pack.draft.animations.length,0);
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',()=>{
    if(state.route==='motion') {
      main.querySelectorAll('*').forEach(element=>element.getAnimations().forEach(animation=>animation.cancel()));
      renderMotion();
    }
  });
  window.addEventListener('hashchange',route);route();
} catch(error) {
  main.innerHTML=`<div class="error-page"><div class="eyebrow">Recursos locales</div><h1>No se pudo abrir la biblioteca.</h1><p>Sirve la carpeta <code>creator-experience/</code> completa por HTTP local para incluir los manifiestos, previews y recursos de los packs.</p><p><code>${escape(error.message)}</code></p><button class="button" id="retry">Volver a intentar</button></div>`;
  document.querySelector('#retry').addEventListener('click',()=>location.reload());
}
