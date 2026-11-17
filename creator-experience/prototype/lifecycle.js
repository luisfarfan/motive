/* Installation presentation fixtures only. No files, native state or installer are mutated. */
const fixtures = [
  ['ready', 'Preparado para revisar'],
  ['reviewed', 'Plan revisado'],
  ['installing-demo', 'Instalando · ejemplo'],
  ['installed-demo', 'Instalado · ejemplo'],
  ['partial-error', 'Error parcial · ejemplo'],
  ['missing-resource', 'Recurso faltante · ejemplo'],
  ['stale-review', 'Revisión obsoleta · ejemplo'],
];
const stepNames = [
  'Verificar recursos, hashes y licencia',
  'Revisar capacidades y revisión del proyecto',
  'Crear escenas y fuentes; vincular IDs',
  'Aplicar layouts y bindings declarados',
  'Reconciliar el resultado observado',
];
const escape = value => String(value).replace(/[&<>"']/g, character => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
}[character]));

export function renderLifecycleStudy({host, pack, model, onCustomize}) {
  const resource = pack.resources[0];
  model.lifecycleRevision ??= 7;
  model.lifecycleSnapshot ??= {completed:2,scenes:2,sources:1};
  const [fixture, label] = fixtures.find(([id]) => id === model.lifecycle) || fixtures[0];
  const terminalError = ['partial-error', 'missing-resource', 'stale-review'].includes(fixture);
  const completed = fixture === 'installed-demo' ? 5
    : fixture === 'installing-demo' ? model.lifecycleStep
    : fixture === 'partial-error' ? model.lifecycleSnapshot.completed
    : fixture === 'reviewed' ? 2 : 0;
  const details = contentFor(fixture, pack, resource, model);
  host.innerHTML = `
    <div class="lifecycle-heading">
      <div><div class="eyebrow">Estudio de estados / Datos de ejemplo</div>
        <h2>Una instalación que explica cada paso.</h2>
        <p>Selecciona un fixture para revisar la interfaz y su recuperación. Este estudio no instala recursos ni lee el estado de Production.</p>
      </div>
      <label class="field"><span class="field-label">Estado del ejemplo</span>
        <select id="lifecycle-fixture">${fixtures.map(([id,name]) => `<option value="${id}" ${id === fixture ? 'selected' : ''}>${name}</option>`).join('')}</select>
      </label>
    </div>
    <div class="notice neutral lifecycle-disclaimer"><strong>Solo UI de ejemplo.</strong> «Instalado» e «instalando» describen este fixture, nunca la aplicación real. H14 observado admite MATCHDAY sin recursos externos; estos packs siguen pendientes de integración.</div>
    <div class="lifecycle-grid">
      <section class="lifecycle-progress" aria-label="Pasos del ejemplo">
        <div class="lifecycle-state ${terminalError ? 'attention' : ''}"><span>Fixture seleccionado</span><strong>${escape(label)}</strong></div>
        <ol class="lifecycle-steps">${stepNames.map((name,index) => {
          const phase = index < completed ? 'done' : index === completed && fixture === 'partial-error' ? 'partial' : index === completed && fixture === 'installing-demo' ? 'active' : 'waiting';
          return `<li data-phase="${phase}"><span class="step-index">${String(index + 1).padStart(2,'0')}</span><div><strong>${name}</strong><small>${phase === 'done' ? 'Completado en el ejemplo' : phase === 'partial' ? 'Interrumpido en el ejemplo' : phase === 'active' ? 'Paso pendiente del ejemplo' : 'Sin ejecutar en este ejemplo'}</small></div></li>`;
        }).join('')}</ol>
        <p class="fixture-footnote">Los estados se cambian manualmente. No hay un worker, importación, progreso temporal ni recibos nativos.</p>
      </section>
      <section class="lifecycle-detail" aria-live="polite" aria-label="Detalle y recuperación del ejemplo">
        <div class="eyebrow">${escape(details.kicker)}</div><h3>${escape(details.title)}</h3><p>${details.copy}</p>
        ${details.body || ''}
        <div class="lifecycle-actions">${details.actions.map(action => `<button class="button ${action.primary ? 'primary' : ''}" data-lifecycle-action="${action.id}">${action.label}</button>`).join('')}</div>
        ${model.lifecycleNote ? `<div class="notice neutral lifecycle-result" role="status">${escape(model.lifecycleNote)}</div>` : ''}
      </section>
    </div>`;
  host.querySelector('#lifecycle-fixture').addEventListener('change', event => choose(event.target.value));
  host.querySelectorAll('[data-lifecycle-action]').forEach(button => {
    button.addEventListener('click', () => act(button.dataset.lifecycleAction));
  });

  function rerender() {
    const focused=document.activeElement;
    const selector=focused?.id ? `#${CSS.escape(focused.id)}`
      : focused?.dataset.lifecycleAction ? `[data-lifecycle-action="${focused.dataset.lifecycleAction}"]` : null;
    renderLifecycleStudy({host, pack, model, onCustomize});
    const next=selector?host.querySelector(selector):null;
    if(next)next.focus({preventScroll:true});
    else if(selector) {
      const heading=host.querySelector('.lifecycle-detail h3');
      heading.tabIndex=-1;
      heading.focus({preventScroll:true});
    }
  }
  function choose(next) {
    if(next === 'stale-review') {
      model.lifecycleApprovedRevision = model.lifecycleRevision;
      model.lifecycleRevision += 1;
    }
    if(next === 'reviewed') model.lifecycleApprovedRevision = model.lifecycleRevision;
    if(next === 'partial-error') model.lifecycleSnapshot = {completed:2,scenes:2,sources:1};
    model.lifecycle = next;
    model.lifecycleStep = next === 'installing-demo' ? 2 : 0;
    model.lifecycleDetail = false;
    model.lifecycleNote = '';
    rerender();
  }
  function act(action) {
    if (action === 'review') choose('reviewed');
    if (action === 'start-demo') choose('installing-demo');
    if (action === 'next-step') {
      model.lifecycleStep += 1;
      if (model.lifecycleStep >= stepNames.length) model.lifecycle = 'installed-demo';
      rerender();
    }
    if (action === 'partial') {
      model.lifecycleSnapshot = {completed:model.lifecycleStep,scenes:model.lifecycleStep >= 3 ? pack.scenes.length : 2,sources:model.lifecycleStep >= 3 ? pack.overlays.length : 1};
      model.lifecycle = 'partial-error';
      model.lifecycleDetail = false;
      model.lifecycleNote = '';
      rerender();
    }
    if (action === 'cancel-demo') {
      model.lifecycleSnapshot = {completed:model.lifecycleStep,scenes:model.lifecycleStep >= 3 ? pack.scenes.length : 2,sources:model.lifecycleStep >= 3 ? pack.overlays.length : 1};
      model.lifecycle = 'partial-error';
      model.lifecycleDetail = true;
      model.lifecycleNote = 'Cancelación del ejemplo: se conserva la lista de entidades del fixture para reconciliar. No se afirma rollback ni se ha borrado ningún archivo.';
      rerender();
    }
    if (action === 'inspect-created' || action === 'inspect-resource') {
      model.lifecycleDetail = !model.lifecycleDetail;
      rerender();
    }
    if (action === 'reconcile-demo') {
      model.lifecycleApprovedRevision = model.lifecycleRevision;
      model.lifecycleRevision += 1;
      model.lifecycle = 'stale-review';
      model.lifecycleDetail = false;
      model.lifecycleNote = 'Reconciliación marcada solo en el ejemplo. La nueva revisión requiere preparar y revisar otro plan; no se repiten mutaciones inciertas.';
      rerender();
    }
    if (action === 'reload-demo' || action === 'resolve-demo') {
      model.lifecycle = 'ready';
      model.lifecycleApprovedRevision = null;
      model.lifecycleDetail = false;
      model.lifecycleNote = action === 'resolve-demo'
        ? 'El fixture ahora representa el recurso idéntico localizado. No se seleccionó, copió ni verificó un archivo real; revisa de nuevo el plan de ejemplo.'
        : 'Plan del fixture recargado con una nueva revisión. La aprobación anterior queda invalidada solo en este estudio.';
      rerender();
    }
    if (action === 'customize') onCustomize();
    if (action === 'restart-demo') choose('ready');
  }
}

function contentFor(fixture, pack, resource, model) {
  const primary = (id,label) => ({id,label,primary:true});
  const secondary = (id,label) => ({id,label});
  if (fixture === 'ready') return {
    kicker:'Antes de aplicar / ejemplo', title:'Un plan listo para inspeccionar',
    copy:`El proyecto vacío del fixture dispone de espacio para ${pack.scenes.length} escenas y ${pack.overlays.length} fuentes. La instalación real todavía necesita verificación del owner, medios e IDs retornados.`,
    body:`<dl class="fixture-facts"><div><dt>Revisión del ejemplo</dt><dd>demo-revision-${model.lifecycleRevision}</dd></div><div><dt>Salida del ejemplo</dt><dd>Idle · dato ficticio</dd></div><div><dt>Acciones al importar</dt><dd>Ningún timer, alerta o salida se inicia</dd></div></dl>`,
    actions:[primary('review','Ensayar revisión del plan')],
  };
  if (fixture === 'reviewed') return {
    kicker:'Revisión confirmada / ejemplo', title:'Se conserva lo que se aprobó',
    copy:`Este fixture representa un plan ligado a demo-revision-${model.lifecycleApprovedRevision ?? model.lifecycleRevision} y a los hashes de sus recursos. Cambiar el proyecto o sus bytes invalida esa revisión antes de ejecutar.`,
    body:'<div class="notice neutral">La confirmación del plan real no se reutiliza aquí. Este botón solo recorre los estados visuales del ejemplo.</div>',
    actions:[primary('start-demo','Ensayar estados de instalación'),secondary('restart-demo','Volver a preparado')],
  };
  if (fixture === 'installing-demo') return {
    kicker:'Instalando / fixture estático', title:`Paso ${Math.min(model.lifecycleStep + 1,5)} de 5 del ejemplo`,
    copy:'El ensayo espera tu siguiente paso. En la aplicación futura, esta vista debe avanzar únicamente con recibos del instalador oficial y mantener el bloqueo de revisión.',
    body:'<div class="fixture-operation"><span>Operación ficticia</span><code>demo-install-1</code><span>Este ID no identifica una operación nativa.</span></div>',
    actions:[primary('next-step','Avanzar un paso del ejemplo'),secondary('partial','Ensayar error parcial'),secondary('cancel-demo','Ensayar cancelación')],
  };
  if (fixture === 'installed-demo') return {
    kicker:'Instalado / solo ejemplo visual', title:'La colección aparecería en el proyecto',
    copy:`El fixture muestra ${pack.scenes.length} escenas reconciliadas y ${pack.properties.length} propiedades disponibles. No se ha instalado ${escape(pack.name)} ni se han creado fuentes en Motive.`,
    body:'<div class="notice good"><strong>Estado ilustrado: instalado.</strong> El éxito real exige observar la conciliación completa del instalador y guardar sus bindings. Los timers y eventos seguirían detenidos.</div>',
    actions:[primary('customize','Volver al personalizador local'),secondary('restart-demo','Restablecer el estudio')],
  };
  if (fixture === 'partial-error') return {
    kicker:'Error parcial / fixture', title:'Conservar evidencia antes de reintentar',
    copy:'El ejemplo se interrumpió después de crear parte de la composición. No presupone transacción ni rollback. El flujo real debe consultar las entidades existentes y reconciliar sus IDs antes de preparar otro plan.',
    body:`<div class="notice"><strong>Código ficticio: DEMO_PARTIAL_FAILURE</strong><br>El ejemplo conserva ${model.lifecycleSnapshot.scenes} escenas y ${model.lifecycleSnapshot.sources} fuentes. No son entidades de Production.</div>${model.lifecycleDetail ? `<table class="plan-table"><thead><tr><th>Entidad del fixture</th><th>Estado ilustrado</th></tr></thead><tbody>${pack.scenes.slice(0,model.lifecycleSnapshot.scenes).map((scene,i) => `<tr><td>${escape(scene.name)}<br><code>demo-scene-${i+1}</code></td><td>Creada en el ejemplo</td></tr>`).join('')}${pack.overlays.slice(0,model.lifecycleSnapshot.sources).map((source,i)=>`<tr><td>${escape(source.name)}<br><code>demo-source-${i+1}</code></td><td>Binding por reconciliar</td></tr>`).join('')}</tbody></table>` : ''}`,
    actions:[secondary('inspect-created',model.lifecycleDetail ? 'Ocultar entidades del fixture' : 'Inspeccionar entidades del fixture'), ...(model.lifecycleDetail ? [primary('reconcile-demo','Ensayar reconciliación explícita')] : [])],
  };
  if (fixture === 'missing-resource') return {
    kicker:'Recurso faltante / fixture', title:'Pedir el recurso preciso',
    copy:`El ejemplo representa la ausencia de <code>${escape(resource.file_name)}</code>. Una recuperación real debe seleccionar el original idéntico mediante el importador autorizado; no descargar una URL ni sustituirlo silenciosamente.`,
    body:`<div class="notice"><strong>Código ficticio: DEMO_RESOURCE_MISSING</strong><br>Este estudio no ha eliminado ni intentado abrir el recurso real.</div>${model.lifecycleDetail ? `<dl class="fixture-facts"><div><dt>Archivo esperado</dt><dd>${escape(resource.file_name)}</dd></div><div><dt>Tamaño declarado</dt><dd>${resource.bytes} bytes · ${resource.width} × ${resource.height}</dd></div><div><dt>SHA-256 esperado</dt><dd><code>${escape(resource.sha256)}</code></dd></div></dl>` : ''}`,
    actions:[secondary('inspect-resource',model.lifecycleDetail ? 'Ocultar referencia' : 'Ver identidad del recurso'),primary('resolve-demo','Ensayar recurso idéntico localizado')],
  };
  return {
    kicker:'Revisión obsoleta / fixture', title:'El proyecto cambió después de revisar',
    copy:`La revisión aprobada demo-revision-${model.lifecycleApprovedRevision ?? model.lifecycleRevision-1} ya no coincide con demo-revision-${model.lifecycleRevision}. El flujo bloquea la aplicación del plan anterior y exige recargarlo; no adapta una aprobación sin mostrar el nuevo impacto.`,
    body:`<dl class="fixture-facts"><div><dt>Revisión aprobada</dt><dd>demo-revision-${model.lifecycleApprovedRevision ?? model.lifecycleRevision-1}</dd></div><div><dt>Revisión actual del ejemplo</dt><dd>demo-revision-${model.lifecycleRevision}</dd></div></dl><div class="notice">Aplicar el plan anterior queda bloqueado en el fixture. Revisa de nuevo recursos, capacidad y bindings.</div>`,
    actions:[primary('reload-demo','Recargar plan del ejemplo')],
  };
}
