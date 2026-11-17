/* A bounded browser design study, not a second animation runtime for Motive.
 * Only existing PackAnimation values are selected; drafts never change a manifest.
 * Web Animations interpolates sampled native quadratic equations for visual review.
 */
const escape = value => String(value).replace(/[&<>"']/g, character => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
}[character]));
const easingNames = {
  linear:'Linear · lineal',
  ease_in:'EaseIn · cuadrática',
  ease_out:'EaseOut · cuadrática',
  ease_in_out:'EaseInOut · cuadrática',
};

function collectEntries(packs) {
  return [...packs.values()].flatMap(({draft:pack}) => pack.animations.map(animation => {
    const scene = pack.scenes.find(candidate => candidate.id === animation.scene_id);
    const layer = scene.layers.find(candidate => candidate.id === animation.layer_id);
    const source = pack.overlays.find(candidate => candidate.id === layer.overlay_id);
    return {key:`${pack.id}/${animation.id}`,pack,animation,scene,source};
  }));
}
function describe(animation) {
  const leaving = animation.kind.endsWith('_out');
  if (animation.id.startsWith('reward-')) return {
    label:`Celebración / ${leaving ? 'salida' : 'entrada'}`,
    purpose:leaving ? 'Cerrar la recompensa y devolver protagonismo a la comunidad.' : 'Destacar una recompensa comunitaria con una escala expresiva y acotada.',
  };
  if (animation.id.includes('indicator')) return {
    label:'Identificador / evento',
    purpose:'Señalar la aparición del identificador sin afirmar que una regla o proveedor haya ejecutado un evento.',
  };
  if (animation.id.includes('label')) return {
    label:`Capítulo / ${leaving ? 'salida' : 'entrada'}`,
    purpose:leaving ? 'Retirar el capítulo anterior con una salida corta en X.' : 'Presentar el siguiente bloque editorial con un desplazamiento breve en X.',
  };
  if (animation.id.includes('lower')) return {
    label:`Lower third / ${leaving ? 'salida' : 'entrada'}`,
    purpose:leaving ? 'Retirar la identificación del creador sin alterar la escena.' : 'Identificar al creador con un rótulo legible y un movimiento discreto.',
  };
  if (animation.id.includes('alert')) return {
    label:`Alerta / ${leaving ? 'salida' : 'entrada'}`,
    purpose:leaving ? 'Cerrar la alerta sin detener la producción.' : 'Atraer atención hacia una alerta; Trigger del widget sigue siendo una acción separada.',
  };
  if (animation.id.includes('pause')) return {
    label:'Pausa / aparición',
    purpose:'Introducir el título de BRB dentro de su escena, por separado del Fade de cambio de escena.',
  };
  return {
    label:leaving ? 'Título / finalización' : 'Título / aparición',
    purpose:leaving ? 'Cerrar el título editorial al terminar. No detiene la grabación ni la emisión.' : 'Presentar el título principal con un Fade lineal que deja respirar la composición.',
  };
}
function initialDraft(animation) {
  return {
    duration_ms:String(animation.duration_ms),
    easing:animation.easing,
    distance:String(animation.distance),
    scale_from:String(animation.scale_from),
  };
}
function validateDraft(animation,draft) {
  const errors = [];
  const invalidFields = new Set();
  const fail = (field,message) => {invalidFields.add(field);errors.push(message);};
  const values = {...animation};
  for (const name of ['duration_ms','distance','scale_from']) {
    const raw = draft[name];
    const value = Number(raw);
    if (typeof raw !== 'string' || !raw.trim() || !Number.isFinite(value)) fail(name,`${name}: se requiere un número finito.`);
    values[name] = value;
  }
  if (!Number.isInteger(values.duration_ms) || values.duration_ms < 100 || values.duration_ms > 10000) fail('duration_ms','Duración: entero de 100 a 10000 ms.');
  if (values.distance < -1920 || values.distance > 1920) fail('distance','Distancia X: de −1920 a 1920 píxeles lógicos.');
  if (values.scale_from < .1 || values.scale_from > 2) fail('scale_from','Escala: de 0,1 a 2.');
  if (!Object.hasOwn(easingNames,draft.easing)) fail('easing','Easing no admitido por el contrato.');
  if (animation.kind.startsWith('fade') && draft.easing !== 'linear') fail('easing','Fade solo admite Linear.');
  values.easing = draft.easing;
  return {values,errors,invalidFields};
}
function equation(t,easing) {
  if (easing === 'ease_in') return t*t;
  if (easing === 'ease_out') return 1-(1-t)*(1-t);
  if (easing === 'ease_in_out') return t < .5 ? 2*t*t : 1-2*(1-t)*(1-t);
  return t;
}
function sampleFrames(animation,opacity) {
  const frames = [];
  const leaving = animation.kind.endsWith('_out');
  for (let i=0;i<=40;i++) {
    const offset = i/40;
    const p = equation(offset,animation.easing);
    let frame;
    if (animation.kind.startsWith('fade')) frame = {opacity:opacity*(leaving ? 1-p : p)};
    if (animation.kind.startsWith('slide')) frame = {transform:`translateX(${-animation.distance*(leaving ? p : 1-p)}px)`};
    if (animation.kind.startsWith('scale')) {
      const scale = leaving ? 1+(animation.scale_from-1)*p : animation.scale_from+(1-animation.scale_from)*p;
      frame = {transform:`scale(${scale})`};
    }
    frames.push({...frame,offset});
  }
  return frames;
}

export function renderMotionWorkbench(options) {
  const {host,packs,state,sceneSVG,previewURL,title,onInspect,footer} = options;
  const entries = collectEntries(packs);
  const entry = entries.find(candidate => candidate.key === state.motionKey) || entries[0];
  state.motionKey = entry.key;
  const {pack,animation,scene,source} = entry;
  const details = describe(animation);
  const draft = state.motionDrafts.get(entry.key) || initialDraft(animation);
  const checked = validateDraft(animation,draft);
  const reducedBySystem = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const reducedByRecipe = packs.get(pack.id).style === 'reduced-motion';
  const isReducedNow = () => state.reduced || matchMedia('(prefers-reduced-motion: reduce)').matches || packs.get(pack.id).style === 'reduced-motion';
  const reduced = isReducedNow();
  let previewGeneration = 0;
  const previewScene = structuredClone(scene);
  previewScene.layers.find(layer => layer.id === animation.layer_id)[state.motionOrientation].visible = true;
  const bridgeFrom = pack.scenes.findIndex(candidate => candidate.id.endsWith('-live'));
  const bridgeTo = pack.scenes.findIndex(candidate => candidate.id.endsWith('-brb'));
  const bridge = packs.get(pack.id).deck.buttons.find(button => button.target.kind === 'scene' && button.target.scene_ref === pack.scenes[bridgeTo].id).target.transition;
  host.innerHTML = `
    <div class="page-heading"><div><div class="eyebrow">Motive Motion / ${entries.length} animaciones declaradas</div>
      <h1>Movimiento con intención.</h1><p>Cada gesto, su propósito. Explora las capas reales de las colecciones<br>y ajusta sus parámetros en un ensayo local.</p>
    </div></div>
    <div class="motion-workbench-toolbar">
      <label class="field"><span class="field-label">Animación del catálogo</span><select id="pack-animation">${entries.map(candidate => `<option value="${candidate.key}" ${candidate.key === entry.key ? 'selected' : ''}>${title(candidate.pack.id)} · ${candidate.animation.id}</option>`).join('')}</select></label>
      <label class="motion-check"><input type="checkbox" id="reduced-motion" ${reduced ? 'checked' : ''} ${reducedBySystem || reducedByRecipe ? 'disabled' : ''}> Reducir movimiento</label>
    </div>
    ${reducedBySystem || reducedByRecipe ? `<p class="motion-preference-note">${reducedBySystem ? 'La preferencia del sistema mantiene el preview estático.' : 'La receta reducida elegida en el personalizador mantiene el preview estático.'}</p>` : ''}
    <div class="motion-workbench">
      <nav class="motion-catalogue" aria-label="Las ${entries.length} animaciones de los packs">${[...packs.keys()].map(id => `<section><h2>${title(id)} <span>${entries.filter(candidate => candidate.pack.id === id).length}</span></h2>${entries.filter(candidate => candidate.pack.id === id).map(candidate => `<button class="motion-entry ${candidate.key === entry.key ? 'active' : ''}" data-motion-select="${candidate.key}" aria-pressed="${candidate.key === entry.key}"><strong>${describe(candidate.animation).label}</strong><small>${candidate.animation.id}</small><span>${candidate.animation.kind} · ${candidate.animation.duration_ms} ms</span></button>`).join('')}</section>`).join('')}</nav>
      <section class="motion-editor" aria-label="Preview y parámetros de la animación">
        <div class="stage-toolbar"><div><div class="eyebrow">${title(pack.id)} / ${escape(scene.name)}</div><h2>${details.label}</h2></div><div class="segmented" aria-label="Orientación del preview de movimiento">${[['horizontal','16:9'],['vertical','9:16']].map(([orientation,label]) => `<button data-motion-orientation="${orientation}" class="${state.motionOrientation === orientation ? 'active' : ''}" aria-pressed="${state.motionOrientation === orientation}">${label}</button>`).join('')}</div></div>
        <p class="motion-purpose">${details.purpose}</p>
        <div class="preview-stage motion-live-preview ${state.motionOrientation}" id="selected-motion-stage">${sceneSVG(pack,previewScene,state.motionOrientation)}</div>
        <p class="preview-caption">Target ilustrado activo en una copia. Los widgets nativos necesitan Show/Trigger por separado. SVG y curvas muestreadas del navegador no acreditan equivalencia con libobs.</p>
        <div class="motion-play-actions"><button class="button primary" id="play-selected-motion" data-play="${animation.kind}" ${checked.errors.length ? 'disabled' : ''}>Reproducir este preview</button><button class="button" id="reset-motion-preview">Restablecer preview</button><button class="button" id="inspect-animation">Ver composición</button></div>
        <p id="motion-play-status" class="motion-play-status" role="status">Preview detenido · Sin conexión a Production</p>
        <div class="motion-parameters"><h3>Parámetros de ensayo</h3><p>Valores acotados al contrato. No cambian el manifiesto ni registran animaciones en Motive.</p>
          <div class="motion-parameter-grid">
            <label class="field"><span class="field-label">Duración (ms)</span><input id="motion-duration" data-motion-field="duration_ms" type="number" min="100" max="10000" step="1" value="${escape(draft.duration_ms)}"><small>Entero · 100–10000 ms</small></label>
            <label class="field"><span class="field-label">Easing</span><select id="motion-easing" data-motion-field="easing" ${animation.kind.startsWith('fade') ? 'disabled' : ''}>${Object.entries(easingNames).map(([id,label]) => `<option value="${id}" ${draft.easing === id ? 'selected' : ''}>${label}</option>`).join('')}</select><small>${animation.kind.startsWith('fade') ? 'Fade usa exclusivamente Linear.' : 'Curvas cuadráticas nativas; aproximación visual muestreada.'}</small></label>
            ${animation.kind.startsWith('slide') ? `<label class="field"><span class="field-label">Distancia X (px lógicos)</span><input id="motion-distance" data-motion-field="distance" type="number" min="-1920" max="1920" step="any" value="${escape(draft.distance)}"><small>−1920…1920 · Positivo entra desde la izquierda.</small></label>` : ''}
            ${animation.kind.startsWith('scale') ? `<label class="field"><span class="field-label">Escala inicial / destino</span><input id="motion-scale" data-motion-field="scale_from" type="number" min="0.1" max="2" step="any" value="${escape(draft.scale_from)}"><small>0,1…2 · Inicial en entrada; destino en salida.</small></label>` : ''}
          </div>
          <p id="motion-param-error" class="field-error" role="alert">${checked.errors.map(escape).join(' ')}</p><button class="button" id="reset-motion-parameters">Restaurar valores declarados</button>
        </div>
        <dl class="motion-target-facts"><div><dt>Animación</dt><dd><code>${animation.id}</code></dd></div><div><dt>Escena / capa</dt><dd><code>${scene.id}<br>${animation.layer_id}</code></dd></div><div><dt>Fuente objetivo</dt><dd>${escape(source.name)}<br><code>${source.id}</code></dd></div><div><dt>Compatibilidad</dt><dd>H11 · <code>layer_animation</code><br>Binding e integración nativa pendientes</dd></div></dl>
      </section>
    </div>
    <section class="scene-transition-study" aria-labelledby="bridge-title"><div class="bridge-stage"><img src="${previewURL(pack.id,bridgeFrom,state.motionOrientation)}" alt="Composición ${escape(pack.scenes[bridgeFrom].name)} antes de la pausa" width="960" height="540"><img id="bridge-after" src="${previewURL(pack.id,bridgeTo,state.motionOrientation)}" alt="Composición Be Right Back después del fundido" width="960" height="540"></div><div><div class="eyebrow">Transición entre escenas / H9</div><h3 id="bridge-title">Un puente hacia la pausa</h3><p>${escape(pack.scenes[bridgeFrom].name)} → ${escape(pack.scenes[bridgeTo].name)}. Fade de ${bridge.duration_ms} ms declarado en el Deck; no es una animación de capa. Estudio de diseño, sin conmutación real.</p><div class="bridge-actions"><button class="button" id="play-scene-transition">Previsualizar pausa</button><button class="button" id="reset-scene-transition">Restablecer</button></div><small>Movimiento reducido: Cut inmediato en esta vista.</small></div></section>
    <div class="notice neutral motion-contract-note">Una operación por capa y hasta ocho operaciones simultáneas en el motor, sujetas al presupuesto del pack. Los previews animados se ejecutan de uno en uno y regresan al estado inicial al terminar. El modo reducido conserva el estado final ilustrado hasta Restablecer. La alternativa nativa reducida es Show/Hide o Fade100 lineal y escena Cut; nunca serializar una duración cero.</div>${footer()}`;
  const bridgeStage = host.querySelector('.bridge-stage');
  bridgeStage.classList.toggle('vertical',state.motionOrientation === 'vertical');
  host.querySelector('#pack-animation').addEventListener('change', event => choose(event.target.value));
  host.querySelectorAll('[data-motion-select]').forEach(button => button.addEventListener('click', () => choose(button.dataset.motionSelect)));
  host.querySelectorAll('[data-motion-orientation]').forEach(button => button.addEventListener('click', () => {
    state.motionOrientation = button.dataset.motionOrientation;
    rerender();
  }));
  host.querySelector('#reduced-motion').addEventListener('change', event => {
    state.reduced = event.target.checked;
    rerender();
  });
  host.querySelectorAll('[data-motion-field]').forEach(input => {
    input.setAttribute('aria-invalid',String(checked.invalidFields.has(input.dataset.motionField)));
    input.addEventListener(input.tagName === 'SELECT' ? 'change' : 'input', () => {
      const next = {...(state.motionDrafts.get(entry.key) || initialDraft(animation)),[input.dataset.motionField]:input.value};
      state.motionDrafts.set(entry.key,next);
      const result = validateDraft(animation,next);
      host.querySelector('#motion-param-error').textContent = result.errors.join(' ');
      host.querySelector('#play-selected-motion').disabled = result.errors.length > 0;
      host.querySelectorAll('[data-motion-field]').forEach(control=>control.setAttribute('aria-invalid',String(result.invalidFields.has(control.dataset.motionField))));
    });
  });
  host.querySelector('#reset-motion-parameters').addEventListener('click', () => {
    state.motionDrafts.delete(entry.key);
    rerender();
  });
  host.querySelector('#inspect-animation').addEventListener('click', () => onInspect(pack.id,scene.id));
  host.querySelector('#play-selected-motion').addEventListener('click',play);
  host.querySelector('#reset-motion-preview').addEventListener('click', () => {
    cancelPreviews();
    host.querySelector('#motion-play-status').textContent = 'Preview restablecido · Sin ejecución nativa';
  });
  host.querySelector('#play-scene-transition').addEventListener('click', () => {
    cancelPreviews();
    const after = host.querySelector('#bridge-after');
    after.style.opacity = '0';
    if (isReducedNow()) after.style.opacity = '1';
    else after.animate([{opacity:0},{opacity:1}],{duration:bridge.duration_ms,easing:'linear',fill:'forwards'});
  });
  host.querySelector('#reset-scene-transition').addEventListener('click', () => {
    const after = host.querySelector('#bridge-after');
    after.getAnimations().forEach(item => item.cancel());
    after.style.opacity = '0';
  });

  function rerender() {
    const focused = document.activeElement;
    const selector = focused?.id ? `#${CSS.escape(focused.id)}`
      : focused?.dataset.motionSelect ? `[data-motion-select="${CSS.escape(focused.dataset.motionSelect)}"]`
      : focused?.dataset.motionOrientation ? `[data-motion-orientation="${focused.dataset.motionOrientation}"]` : null;
    cancelPreviews();
    renderMotionWorkbench(options);
    if(selector)host.querySelector(selector)?.focus({preventScroll:true});
  }
  function choose(key) {
    state.motionKey = key;
    rerender();
  }
  function target() {
    return host.querySelector(`#selected-motion-stage [data-layer="${CSS.escape(animation.layer_id)}"]`);
  }
  function cancelPreviews() {
    previewGeneration += 1;
    host.querySelectorAll('.motion-live-preview *, .bridge-stage *').forEach(element => {
      element.getAnimations().forEach(item => item.cancel());
    });
    const element = target();
    if (element) {
      element.style.removeProperty('opacity');
      element.style.removeProperty('transform');
    }
  }
  function play() {
    const result = validateDraft(animation,state.motionDrafts.get(entry.key) || initialDraft(animation));
    if (result.errors.length) return;
    cancelPreviews();
    const element = target();
    const status = host.querySelector('#motion-play-status');
    if (!element) {
      status.textContent = 'No se encontró la capa objetivo del preview.';
      return;
    }
    if (isReducedNow()) {
      element.style.opacity = result.values.kind.endsWith('_out') ? '0' : element.getAttribute('opacity') || '1';
      status.textContent = 'Movimiento reducido · Estado ilustrado inmediato, sin animación ni comando nativo.';
      return;
    }
    element.style.transformBox = 'fill-box';
    element.style.transformOrigin = '0 0';
    const frames = sampleFrames(result.values,Number(element.getAttribute('opacity') || 1));
    const generation = previewGeneration;
    const running = element.animate(frames,{duration:result.values.duration_ms,easing:'linear',fill:'none'});
    status.textContent = `Preview de ${animation.id} · ${result.values.duration_ms} ms · ${result.values.easing}`;
    running.finished.then(() => {
      if (status.isConnected && generation === previewGeneration) status.textContent = 'Preview terminado · Estado inicial restablecido · Sin ejecución nativa';
    }).catch(() => {
      // A cancelled or replaced browser preview is not a native failure.
    });
  }
}
