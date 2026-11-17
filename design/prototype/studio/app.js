/* Motive — Studio prototype (Phase 1). Plain JS, no dependencies.
   The data model mirrors the real core: scenes → layers → reusable sources,
   one transform per canvas variant (960×540 / 540×960), one active output
   in "Hoy" scope. Behaviour notes for GPUI live in design/direction.md. */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const RM = matchMedia('(prefers-reduced-motion: reduce)');
  const icon = (n, cls = '') => `<svg class="i ${cls}"><use href="#i-${n}"/></svg>`;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const easeOut = (p) => 1 - Math.pow(1 - p, 3);
  const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif';
  const ART = Art.init();

  /* ---------------- Model ---------------- */
  const CANVAS = { h: { w: 960, h: 540 }, v: { w: 540, h: 960 } };
  const SAFE = 32;
  const ACCENT = '#FF8A3D'; // overlay accent colour: editable content, not UI

  const SOURCES = {
    win: { kind: 'window', icon: 'window', name: 'Presentación', detail: 'Ventana de Lámina' },
    cam: { kind: 'camera', icon: 'camera', name: 'Webcam', detail: 'Cámara integrada' },
    title: { kind: 'title', icon: 'title', name: 'Rótulo', detail: 'Texto y gráfico', nameNow: 'Overlay', detailNow: 'Gráfico animado original', future: true },
    pause: { kind: 'pause', icon: 'overlay', name: 'Fondo de pausa', detail: 'Gráfico animado' },
  };
  const R = (x, y, w, h) => ({ x, y, w, h });
  const layer = (id, src, h, v, extra = {}) => ({ id, src, visible: true, t: { h, v }, ...extra });

  const scenes = [
    { id: 'inicio', name: 'Inicio', layers: [
      layer('ini-win', 'win', R(0, 0, 960, 540), R(0, 0, 540, 960)),
      layer('ini-title', 'title', R(56, 392, 560, 92), R(32, 736, 476, 120), { text: ['Luz y materia', 'Taller en vivo con Ana Ruiz'] }),
    ] },
    { id: 'taller', name: 'Taller', layers: [
      layer('tal-win', 'win', R(0, 0, 960, 540), R(0, 72, 540, 304)),
      layer('tal-cam', 'cam', R(618, 296, 284, 200), R(32, 424, 476, 340)),
      layer('tal-title', 'title', R(32, 436, 380, 72), R(32, 808, 476, 96), { text: ['Ana Ruiz', 'Ilustradora, taller de luz y materia'] }),
    ] },
    { id: 'detalle', name: 'Detalle', layers: [
      layer('det-cam', 'cam', R(0, 0, 960, 540), R(0, 0, 540, 960)),
      layer('det-win', 'win', R(640, 32, 288, 162), R(32, 32, 256, 144)),
    ] },
    { id: 'pausa', name: 'Pausa', layers: [
      layer('pau-bg', 'pause', R(0, 0, 960, 540), R(0, 0, 540, 960)),
      layer('pau-title', 'title', R(56, 234, 560, 80), R(32, 420, 476, 110), { text: ['Volvemos en cinco minutos', 'Luz y materia'] }),
    ] },
  ];

  const S = {
    scene: 'taller', variant: 'h', selected: 'tal-cam', hover: null, zoom: 'fit',
    scope: 'vision', safe: false, lost: false,
    out: { stream: true, record: true, since: performance.now() - (18 * 60 + 42) * 1000, busy: null },
    drag: null, guides: [], fade: null,
    suggestion: { scene: 'taller', layer: 'tal-cam', variant: 'h', to: R(644, 308, 284, 200), state: 'idle' },
    history: [], future: [],
    agentLog: [
      { what: 'Cambió el color del overlay', tool: 'set_overlay_color', when: 'hace 4 min' },
      { what: 'Leyó el estado del estudio', tool: 'status', when: 'hace 6 min' },
    ],
  };

  const sceneById = (id) => scenes.find((s) => s.id === id);
  const curScene = () => sceneById(S.scene);
  const layerById = (id, sc = curScene()) => sc && sc.layers.find((l) => l.id === id);
  const selLayer = () => layerById(S.selected);
  const rectOf = (L, v = S.variant) => L.t[v];
  const active = () => S.out.stream || S.out.record;
  const isNow = () => S.scope === 'now';
  const srcName = (L) => { const s = SOURCES[L.src]; return (isNow() && s.nameNow) || s.name; };
  const srcDetail = (L) => { const s = SOURCES[L.src]; return (isNow() && s.detailNow) || s.detail; };

  /* ---------------- Drawing ---------------- */
  function cover(ctx, img, r, zoom = 1, ox = 0, oy = 0) {
    const rar = r.w / r.h, iar = img.width / img.height;
    let sw, sh;
    if (iar > rar) { sh = img.height / zoom; sw = sh * rar; } else { sw = img.width / zoom; sh = sw / rar; }
    const sx = clamp((img.width - sw) / 2 + ox * img.width, 0, img.width - sw);
    const sy = clamp((img.height - sh) / 2 + oy * img.height, 0, img.height - sh);
    ctx.drawImage(img, sx, sy, sw, sh, r.x, r.y, r.w, r.h);
  }

  function drawWindow(ctx, r, t) {
    const bar = Math.max(5, Math.min(30, r.h * 0.052));
    ctx.fillStyle = '#1c1d21'; ctx.fillRect(r.x, r.y, r.w, r.h);
    cover(ctx, ART.ribbons, R(r.x, r.y + bar, r.w, r.h - bar), 1.05 + 0.02 * Math.sin(t * 0.21), 0.012 * Math.sin(t * 0.13), 0.01 * Math.cos(t * 0.17));
    ctx.fillStyle = '#25262b'; ctx.fillRect(r.x, r.y, r.w, bar);
    ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(r.x, r.y + bar - 0.5, r.w, 0.5);
    ['#ff5f57', '#febc2e', '#28c840'].forEach((c, i) => {
      ctx.fillStyle = c; ctx.globalAlpha = 0.85;
      ctx.beginPath(); ctx.arc(r.x + bar * 0.62 + i * bar * 0.56, r.y + bar / 2, bar * 0.17, 0, Math.PI * 2); ctx.fill();
    });
    ctx.globalAlpha = 1;
    if (bar > 9) {
      ctx.font = `500 ${bar * 0.4}px ${FONT}`; ctx.fillStyle = '#9a9fa8'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('Luz y materia', r.x + r.w / 2, r.y + bar / 2 + 0.5);
      ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
    }
  }

  function drawNoSignal(ctx, r) {
    ctx.fillStyle = '#141518'; ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeStyle = 'rgba(255,255,255,.06)'; ctx.lineWidth = 1;
    for (let x = r.x - r.h; x < r.x + r.w; x += 14) { ctx.beginPath(); ctx.moveTo(x, r.y + r.h); ctx.lineTo(x + r.h, r.y); ctx.stroke(); }
    const s = Math.min(r.w, r.h);
    if (s < 40) return;
    ctx.fillStyle = '#FFB547'; ctx.textAlign = 'center';
    ctx.font = `600 ${clamp(s * 0.075, 9, 22)}px ${FONT}`;
    ctx.fillText('Sin señal de la cámara', r.x + r.w / 2, r.y + r.h / 2 - 2);
    ctx.fillStyle = 'rgba(241,242,244,.6)'; ctx.font = `400 ${clamp(s * 0.06, 8, 16)}px ${FONT}`;
    ctx.fillText('Última imagen hace 2 s', r.x + r.w / 2, r.y + r.h / 2 + clamp(s * 0.09, 10, 24));
    ctx.textAlign = 'start';
  }

  function fitText(ctx, text, size, weight, maxW) {
    let s = size;
    ctx.font = `${weight} ${s}px ${FONT}`;
    while (s > 6 && ctx.measureText(text).width > maxW) { s -= 1; ctx.font = `${weight} ${s}px ${FONT}`; }
  }

  function drawTitle(ctx, L, r, t) {
    const u = r.h;
    if (isNow()) {
      // Today's engine: the original animated overlay graphic with an editable accent.
      const bh = u * 0.42, y = r.y + (u - bh) / 2;
      ctx.fillStyle = 'rgba(10,11,13,.55)'; ctx.beginPath(); ctx.roundRect(r.x, y, r.w, bh, Math.min(6, bh / 4)); ctx.fill();
      ctx.fillStyle = ACCENT; ctx.fillRect(r.x, y, Math.max(3, u * 0.05), bh);
      const p = ((t * 0.22) % 1.3) - 0.15, gx = r.x + p * r.w, gw = r.w * 0.28;
      const g = ctx.createLinearGradient(gx - gw / 2, 0, gx + gw / 2, 0);
      g.addColorStop(0, 'rgba(255,138,61,0)'); g.addColorStop(0.5, 'rgba(255,138,61,.55)'); g.addColorStop(1, 'rgba(255,138,61,0)');
      ctx.save(); ctx.beginPath(); ctx.rect(r.x, y, r.w, bh); ctx.clip();
      ctx.fillStyle = g; ctx.fillRect(gx - gw / 2, y + bh * 0.82, gw, bh * 0.18); ctx.restore();
      return;
    }
    const bw = Math.max(3, u * 0.06);
    ctx.fillStyle = ACCENT; ctx.fillRect(r.x, r.y + u * 0.08, bw, u * 0.84);
    const x = r.x + bw + u * 0.2, maxW = r.w - (x - r.x);
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = u * 0.3;
    ctx.fillStyle = '#fff'; fitText(ctx, L.text[0], u * 0.4, 650, maxW);
    ctx.fillText(L.text[0], x, r.y + u * 0.47);
    ctx.fillStyle = 'rgba(255,255,255,.82)'; fitText(ctx, L.text[1], u * 0.235, 400, maxW);
    ctx.fillText(L.text[1], x, r.y + u * 0.83);
    ctx.restore();
  }

  function drawLayer(ctx, L, r, t) {
    const kind = SOURCES[L.src].kind;
    ctx.save();
    if (kind !== 'title') { ctx.beginPath(); ctx.rect(r.x, r.y, r.w, r.h); ctx.clip(); }
    if (kind === 'window') drawWindow(ctx, r, t);
    else if (kind === 'camera') {
      if (S.lost) drawNoSignal(ctx, r);
      else cover(ctx, ART.cam, r, 1.03 + 0.006 * Math.sin(t * 0.9), 0, 0.004 * Math.sin(t * 1.3));
    } else if (kind === 'pause') cover(ctx, ART.bokeh, r, 1.08 + 0.03 * Math.sin(t * 0.15), 0.02 * Math.sin(t * 0.11), 0.015 * Math.cos(t * 0.09));
    else if (kind === 'title') drawTitle(ctx, L, r, t);
    ctx.restore();
  }

  function drawScene(ctx, sc, variant, t) {
    const { w, h } = CANVAS[variant];
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
    for (const L of sc.layers) if (L.visible) drawLayer(ctx, L, L.t[variant], t);
  }

  /* ---------------- Program canvas geometry ---------------- */
  const area = $('#canvasArea'), program = $('#program'), pctx = program.getContext('2d');
  const overlay = $('#overlay');
  const G = { left: 0, top: 0, scale: 1, w: 960, h: 540, dpr: 1 };

  function layoutProgram() {
    const a = area.getBoundingClientRect();
    const { w, h } = CANVAS[S.variant];
    const pad = a.width < 700 ? 16 : 28;
    const fit = Math.min((a.width - pad * 2) / w, (a.height - pad * 2) / h);
    const scale = S.zoom === 'fit' ? fit : 1;
    G.scale = scale; G.w = w; G.h = h; G.dpr = devicePixelRatio || 1;
    const dw = Math.round(w * scale), dh = Math.round(h * scale);
    G.left = Math.round((a.width - dw) / 2); G.top = Math.round((a.height - dh) / 2);
    program.style.left = G.left + 'px'; program.style.top = G.top + 'px';
    program.style.width = dw + 'px'; program.style.height = dh + 'px';
    program.width = Math.round(dw * G.dpr); program.height = Math.round(dh * G.dpr);
    const sa = toScreen(R(SAFE, SAFE, w - SAFE * 2, h - SAFE * 2));
    Object.assign($('#safeArea').style, px(sa));
  }
  const toScreen = (r) => ({ x: G.left + r.x * G.scale, y: G.top + r.y * G.scale, w: r.w * G.scale, h: r.h * G.scale });
  const px = (r) => ({ left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
  function toCanvas(e) {
    const a = area.getBoundingClientRect();
    return { x: (e.clientX - a.left - G.left) / G.scale, y: (e.clientY - a.top - G.top) / G.scale };
  }

  function renderProgram(t, now) {
    pctx.setTransform(G.scale * G.dpr, 0, 0, G.scale * G.dpr, 0, 0);
    drawScene(pctx, curScene(), S.variant, t);
    if (S.fade) {
      const p = (now - S.fade.start) / 200;
      if (p >= 1 || RM.matches) S.fade = null;
      else {
        pctx.setTransform(1, 0, 0, 1, 0, 0);
        pctx.globalAlpha = 1 - easeOut(p);
        pctx.drawImage(S.fade.img, 0, 0, program.width, program.height);
        pctx.globalAlpha = 1;
      }
    }
  }

  /* ---------------- Overlay: selection, ghost, guides ---------------- */
  const sel = $('#sel'), hoverEl = $('#hoverOutline'), ghost = $('#ghost'), trail = $('#ghostTrail'), proposal = $('#proposal');
  const guideV = document.createElement('div'), guideH = document.createElement('div');
  guideV.className = 'guide v'; guideH.className = 'guide h';
  overlay.append(guideV, guideH);
  const HANDLE_POS = { nw: [0, 0], n: [50, 0], ne: [100, 0], e: [100, 50], se: [100, 100], s: [50, 100], sw: [0, 100], w: [0, 50] };
  $$('.handle', sel).forEach((h) => { const [x, y] = HANDLE_POS[h.dataset.dir]; h.style.left = x + '%'; h.style.top = y + '%'; });

  function suggestionLive() {
    const g = S.suggestion;
    return !isNow() && g.scene === S.scene && g.variant === S.variant && (g.state === 'idle' || g.state === 'preview');
  }

  function syncOverlay() {
    const L = selLayer();
    if (L && L.visible) {
      sel.hidden = false;
      Object.assign(sel.style, px(toScreen(rectOf(L))));
      const r = rectOf(L);
      $('#readout').textContent = S.drag && S.drag.mode === 'resize' ? `${Math.round(r.w)} × ${Math.round(r.h)}` : `X ${Math.round(r.x)}   Y ${Math.round(r.y)}`;
    } else sel.hidden = true;

    const H = S.hover && S.hover !== S.selected && !S.drag ? layerById(S.hover) : null;
    hoverEl.hidden = !H;
    if (H) Object.assign(hoverEl.style, px(toScreen(rectOf(H))));

    $('#safeArea').classList.toggle('is-on', S.safe || !!(S.drag && S.drag.moved));
    const gv = S.guides.find((g) => g.v !== undefined), gh = S.guides.find((g) => g.h !== undefined);
    guideV.style.display = gv ? 'block' : 'none'; guideH.style.display = gh ? 'block' : 'none';
    if (gv) Object.assign(guideV.style, { left: G.left + gv.v * G.scale + 'px', top: G.top + 'px', height: G.h * G.scale + 'px' });
    if (gh) Object.assign(guideH.style, { top: G.top + gh.h * G.scale + 'px', left: G.left + 'px', width: G.w * G.scale + 'px' });

    const showGhost = suggestionLive() && S.suggestion.state === 'preview';
    ghost.classList.toggle('is-on', showGhost); trail.classList.toggle('is-on', showGhost); proposal.classList.toggle('is-on', showGhost);
    if (showGhost) {
      const L2 = layerById(S.suggestion.layer);
      const to = toScreen(S.suggestion.to), from = toScreen(rectOf(L2));
      Object.assign(ghost.style, px(to));
      const fx = from.x + from.w / 2, fy = from.y + from.h / 2, tx = to.x + to.w / 2, ty = to.y + to.h / 2;
      const len = Math.hypot(tx - fx, ty - fy), ang = Math.atan2(ty - fy, tx - fx);
      Object.assign(trail.style, { left: fx + 'px', top: fy + 'px', width: len + 'px', transform: `rotate(${ang}rad)` });
      const a = area.getBoundingClientRect(), cw = proposal.offsetWidth, ch = proposal.offsetHeight;
      let x = to.x - cw - 16, y = to.y + to.h - ch;
      if (x < 12) { x = clamp(to.x + to.w - cw, 12, a.width - cw - 12); y = to.y - ch - 14; }
      proposal.style.left = clamp(x, 12, a.width - cw - 12) + 'px';
      proposal.style.top = clamp(y, 12, a.height - ch - 12) + 'px';
    }
  }

  function hitTest(p) {
    const sc = curScene();
    for (let i = sc.layers.length - 1; i >= 0; i--) {
      const L = sc.layers[i], r = rectOf(L);
      if (L.visible && p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) return L;
    }
    return null;
  }

  function snapAxis(pos, size, lines, thr) {
    let best = null;
    for (const [v, off] of [[pos, 0], [pos + size / 2, size / 2], [pos + size, size]]) {
      for (const line of lines) {
        const d = Math.abs(v - line);
        if (d < thr && (!best || d < best.d)) best = { d, pos: line - off, line };
      }
    }
    return best;
  }

  overlay.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.proposal')) return;
    closePop();
    const p = toCanvas(e), handle = e.target.closest('.handle');
    let L = handle ? selLayer() : hitTest(p);
    if (!L) { select(null); return; }
    if (!handle && L.id !== S.selected) select(L.id);
    S.drag = { mode: handle ? 'resize' : 'move', dir: handle && handle.dataset.dir, id: L.id, p0: p, r0: { ...rectOf(L) }, moved: false, pointer: e.pointerId };
    overlay.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  overlay.addEventListener('pointermove', (e) => {
    const p = toCanvas(e);
    if (!S.drag) {
      const L = hitTest(p);
      S.hover = L ? L.id : null;
      const onHandle = !!e.target.closest('.handle');
      sel.classList.toggle('is-hot', onHandle || (!!L && L.id === S.selected));
      overlay.style.cursor = onHandle ? '' : L ? 'move' : 'default';
      return;
    }
    const d = S.drag, L = layerById(d.id), r0 = d.r0;
    const dx = p.x - d.p0.x, dy = p.y - d.p0.y;
    if (!d.moved && Math.hypot(dx * G.scale, dy * G.scale) < 3) return;
    if (!d.moved) { d.moved = true; sel.classList.add('is-dragging'); }
    const thr = 6 / G.scale, noSnap = e.metaKey || e.ctrlKey;
    const xs = [0, SAFE, G.w / 2, G.w - SAFE, G.w], ys = [0, SAFE, G.h / 2, G.h - SAFE, G.h];
    S.guides = [];
    let r;
    if (d.mode === 'move') {
      r = { ...r0, x: r0.x + dx, y: r0.y + dy };
      if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) r.y = r0.y; else r.x = r0.x; }
      if (!noSnap) {
        const bx = snapAxis(r.x, r.w, xs, thr), by = snapAxis(r.y, r.h, ys, thr);
        if (bx) { r.x = bx.pos; S.guides.push({ v: bx.line }); }
        if (by) { r.y = by.pos; S.guides.push({ h: by.line }); }
      }
    } else {
      const dir = d.dir; let { x, y, w, h } = r0;
      if (dir.includes('e')) w = r0.w + dx;
      if (dir.includes('w')) w = r0.w - dx;
      if (dir.includes('s')) h = r0.h + dy;
      if (dir.includes('n')) h = r0.h - dy;
      const corner = dir.length === 2;
      if (corner && !e.shiftKey) { const ar = r0.w / r0.h; if (Math.abs(w / r0.w) > Math.abs(h / r0.h)) h = w / ar; else w = h * ar; }
      if (!corner && !noSnap) {
        if (dir === 'e') { const b = xs.find((l) => Math.abs(x + w - l) < thr); if (b !== undefined) { w = b - x; S.guides.push({ v: b }); } }
        if (dir === 'w') { const b = xs.find((l) => Math.abs(r0.x + r0.w - w - l) < thr); if (b !== undefined) { w = r0.x + r0.w - b; S.guides.push({ v: b }); } }
        if (dir === 's') { const b = ys.find((l) => Math.abs(y + h - l) < thr); if (b !== undefined) { h = b - y; S.guides.push({ h: b }); } }
        if (dir === 'n') { const b = ys.find((l) => Math.abs(r0.y + r0.h - h - l) < thr); if (b !== undefined) { h = r0.y + r0.h - b; S.guides.push({ h: b }); } }
      }
      w = Math.max(32, w); h = Math.max(18, h);
      if (dir.includes('w')) x = r0.x + r0.w - w;
      if (dir.includes('n')) y = r0.y + r0.h - h;
      r = { x, y, w, h };
    }
    L.t[S.variant] = { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.w), h: Math.round(r.h) };
    syncInspector();
  });

  function endDrag(cancel) {
    const d = S.drag; if (!d) return;
    const L = layerById(d.id);
    if (cancel) L.t[S.variant] = { ...d.r0 };
    else if (d.moved) record({ type: 'rect', scene: S.scene, variant: S.variant, id: d.id, before: d.r0, after: { ...rectOf(L) }, by: 'user' });
    S.drag = null; S.guides = []; sel.classList.remove('is-dragging');
    syncInspector();
  }
  overlay.addEventListener('pointerup', () => endDrag(false));
  overlay.addEventListener('pointercancel', () => endDrag(true));
  overlay.addEventListener('pointerleave', () => { if (!S.drag) { S.hover = null; sel.classList.remove('is-hot'); } });
  overlay.addEventListener('dblclick', (e) => {
    const L = hitTest(toCanvas(e));
    if (L) { select(L.id); const inp = $(`.layer[data-id="${L.id}"] input`); if (inp) { inp.focus(); inp.select(); } }
  });

  /* ---------------- History ---------------- */
  function record(entry) { S.history.push(entry); S.future = []; }
  function applyEntry(entry, which) {
    const sc = sceneById(entry.scene);
    if (entry.scene !== S.scene) switchScene(entry.scene, { force: true });
    if (entry.variant && entry.variant !== S.variant) setVariant(entry.variant);
    if (entry.type === 'rect') {
      const L = layerById(entry.id, sc);
      select(L.id);
      tween(L, entry.variant, entry[which]);
    } else if (entry.type === 'order') {
      sc.layers.sort((a, b) => entry[which].indexOf(a.id) - entry[which].indexOf(b.id));
      renderLayers();
    } else if (entry.type === 'visible') {
      layerById(entry.id, sc).visible = entry[which]; renderLayers();
    }
  }
  function undo() {
    const e = S.history.pop(); if (!e) return;
    S.future.push(e); applyEntry(e, 'before');
    if (e.by === 'agent') { S.suggestion.state = 'idle'; renderLayers(); renderAgentCount(); }
    toast('undo', 'Deshecho', null);
  }
  function redo() {
    const e = S.future.pop(); if (!e) return;
    S.history.push(e); applyEntry(e, 'after');
    if (e.by === 'agent') { S.suggestion.state = 'applied'; renderLayers(); renderAgentCount(); }
  }

  function tween(L, variant, to, done) {
    if (RM.matches) { L.t[variant] = { ...to }; syncInspector(); done && done(); return; }
    const from = { ...L.t[variant] }, t0 = performance.now(), dur = 280;
    const step = (now) => {
      const p = Math.min(1, (now - t0) / dur), k = easeOut(p);
      L.t[variant] = { x: from.x + (to.x - from.x) * k, y: from.y + (to.y - from.y) * k, w: from.w + (to.w - from.w) * k, h: from.h + (to.h - from.h) * k };
      if (p < 1) requestAnimationFrame(step); else { L.t[variant] = { ...to }; done && done(); }
      syncInspector();
    };
    requestAnimationFrame(step);
  }

  /* ---------------- Layers list + inline inspector ---------------- */
  const list = $('#layerList');

  function fieldHTML(k, key, label, v) {
    return `<label class="field" data-key="${key}"><span class="k" aria-hidden="true">${k}</span><input class="num" inputmode="numeric" spellcheck="false" aria-label="${label}" value="${Math.round(v)}"></label>`;
  }

  function renderLayers() {
    const sc = curScene();
    $('#layersScene').textContent = `en ${sc.name}`;
    list.innerHTML = '';
    [...sc.layers].reverse().forEach((L) => {
      const src = SOURCES[L.src], selected = L.id === S.selected, r = rectOf(L);
      const lost = S.lost && src.kind === 'camera';
      const li = document.createElement('li');
      li.className = 'layer ann-host';
      li.dataset.id = L.id;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', selected);
      li.dataset.hidden = !L.visible; li.dataset.lost = lost;
      if (src.future && !isNow()) { li.dataset.ann = 'future'; li.dataset.annLabel = 'Texto: futuro · hoy es un overlay animado'; }
      else if (selected) { li.dataset.ann = 'partial'; li.dataset.annLabel = 'Transformaciones reales · campos en UI: siguiente hito'; }
      const g = S.suggestion;
      const chip = suggestionLive() && g.layer === L.id
        ? `<button class="suggest ann-host" data-ann="future" data-ann-label="Revisión de propuestas" aria-expanded="${g.state === 'preview'}">${icon('agent')}<span class="txt">Alinear al margen seguro</span><span class="act">${g.state === 'preview' ? 'Ocultar' : 'Ver'}</span></button>`
        : '';
      const detail = selected
        ? fieldHTML('X', 'x', 'Posición X', r.x) + fieldHTML('Y', 'y', 'Posición Y', r.y) + '<span class="sep" aria-hidden="true"></span>' + fieldHTML('An', 'w', 'Ancho', r.w) + fieldHTML('Al', 'h', 'Alto', r.h)
        : `<span class="note num">${Math.round(r.w)} × ${Math.round(r.h)}</span>`;
      li.innerHTML = `
        <span class="grip" aria-hidden="true" title="Arrastrar para reordenar"><svg viewBox="0 0 8 14"><use href="#i-grip"/></svg></span>
        <span class="kind">${icon(src.icon)}</span>
        <span class="thumb"><canvas width="88" height="52"></canvas></span>
        <span class="name"><b>${esc(srcName(L))}</b><small><span class="health" aria-hidden="true"></span>${lost ? 'Sin señal' : esc(srcDetail(L))}</small></span>
        <button class="icon-btn icon-btn-sm eye" aria-pressed="${!L.visible}" aria-label="${L.visible ? 'Ocultar' : 'Mostrar'} ${esc(srcName(L))}">${icon(L.visible ? 'eye' : 'eye-off')}</button>
        <span class="detail">${detail}${chip}</span>
        <span class="end"><button class="icon-btn icon-btn-sm more" aria-haspopup="menu" aria-label="Más acciones de ${esc(srcName(L))}">${icon('more')}</button></span>`;
      list.appendChild(li);
    });
    drawLayerThumbs(performance.now() / 1000);
  }

  function drawLayerThumbs(t) {
    $$('.layer', list).forEach((li) => {
      const c = $('canvas', li); if (!c || !c.offsetParent) return;
      const L = layerById(li.dataset.id), ctx = c.getContext('2d');
      ctx.setTransform(2, 0, 0, 2, 0, 0);
      ctx.fillStyle = '#17181C'; ctx.fillRect(0, 0, 44, 26);
      const r = rectOf(L), k = Math.min(44 / r.w, 26 / r.h) * (SOURCES[L.src].kind === 'title' ? 0.9 : 1);
      const w = r.w * k, h = r.h * k;
      drawLayer(ctx, L, R((44 - w) / 2, (26 - h) / 2, w, h), t);
    });
  }

  function syncInspector() {
    const L = selLayer(); if (!L) return;
    const row = $(`.layer[data-id="${L.id}"]`, list); if (!row) return;
    const r = rectOf(L);
    $$('.field', row).forEach((f) => {
      const inp = $('input', f);
      if (document.activeElement !== inp) inp.value = Math.round(r[f.dataset.key]);
    });
  }

  function select(id) {
    if (S.selected === id) return;
    S.selected = id;
    renderLayers();
  }

  function commitField(input) {
    const L = selLayer(); if (!L) return;
    const key = input.closest('.field').dataset.key, before = { ...rectOf(L) };
    let v = parseInt(input.value.replace(/[^\d-]/g, ''), 10);
    if (Number.isNaN(v)) { input.value = Math.round(before[key]); return; }
    if (key === 'w' || key === 'h') v = Math.max(16, v);
    if (v === Math.round(before[key])) return;
    L.t[S.variant] = { ...before, [key]: v };
    record({ type: 'rect', scene: S.scene, variant: S.variant, id: L.id, before, after: { ...rectOf(L) }, by: 'user' });
    input.value = v;
  }

  list.addEventListener('click', (e) => {
    const li = e.target.closest('.layer'); if (!li) return;
    const L = layerById(li.dataset.id);
    if (e.target.closest('.eye')) return toggleVisible(L);
    if (e.target.closest('.suggest')) return S.suggestion.state === 'preview' ? closeSuggestion() : openSuggestion();
    if (e.target.closest('.more')) return openLayerMenu(e.target.closest('.more'), L);
    if (e.target.closest('.field')) return;
    select(L.id);
  });
  list.addEventListener('keydown', (e) => {
    const input = e.target.closest('.field input'); if (!input) return;
    if (e.key === 'Enter') { commitField(input); input.select(); e.preventDefault(); }
    else if (e.key === 'Escape') { syncInspectorForce(input); input.blur(); }
    else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const step = (e.shiftKey ? 10 : 1) * (e.key === 'ArrowUp' ? 1 : -1);
      input.value = (parseInt(input.value, 10) || 0) + step; commitField(input);
    }
  });
  list.addEventListener('focusout', (e) => { const input = e.target.closest('.field input'); if (input) commitField(input); });
  function syncInspectorForce(input) { const L = selLayer(); input.value = Math.round(rectOf(L)[input.closest('.field').dataset.key]); }

  // Scrub: drag a field's label horizontally to change its value (⇧ ×10).
  list.addEventListener('pointerdown', (e) => {
    const k = e.target.closest('.field .k'); if (!k) return;
    const L = selLayer(); if (!L) return;
    const key = k.parentElement.dataset.key, before = { ...rectOf(L) }, x0 = e.clientX;
    k.setPointerCapture(e.pointerId); e.preventDefault();
    const move = (ev) => {
      const d = Math.round((ev.clientX - x0) / 2) * (ev.shiftKey ? 10 : 1);
      let v = before[key] + d; if (key === 'w' || key === 'h') v = Math.max(16, v);
      L.t[S.variant] = { ...before, [key]: v }; syncInspector();
    };
    const up = () => {
      k.removeEventListener('pointermove', move); k.removeEventListener('pointerup', up);
      if (rectOf(L)[key] !== before[key]) record({ type: 'rect', scene: S.scene, variant: S.variant, id: L.id, before, after: { ...rectOf(L) }, by: 'user' });
    };
    k.addEventListener('pointermove', move); k.addEventListener('pointerup', up);
  });

  // Reorder by dragging the grip.
  list.addEventListener('pointerdown', (e) => { const g = e.target.closest('.grip'); if (g) g.closest('.layer').draggable = true; });
  list.addEventListener('dragstart', (e) => {
    const li = e.target.closest('.layer'); S.dnd = li.dataset.id; li.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', S.dnd);
  });
  list.addEventListener('dragover', (e) => {
    const li = e.target.closest('.layer'); if (!li || !S.dnd) return;
    e.preventDefault();
    $$('.layer', list).forEach((x) => x.classList.remove('drop-before', 'drop-after'));
    if (li.dataset.id === S.dnd) return;
    const r = li.getBoundingClientRect();
    li.classList.add(e.clientY < r.top + r.height / 2 ? 'drop-before' : 'drop-after');
  });
  list.addEventListener('drop', (e) => {
    e.preventDefault();
    const li = $('.drop-before, .drop-after', list); if (!li) return;
    const sc = curScene(), before = sc.layers.map((l) => l.id);
    const moving = sc.layers.find((l) => l.id === S.dnd);
    sc.layers.splice(sc.layers.indexOf(moving), 1);
    let idx = sc.layers.findIndex((l) => l.id === li.dataset.id);
    if (li.classList.contains('drop-before')) idx += 1; // list is top-first; array is bottom-first
    sc.layers.splice(idx, 0, moving);
    record({ type: 'order', scene: S.scene, before, after: sc.layers.map((l) => l.id), by: 'user' });
    renderLayers();
  });
  list.addEventListener('dragend', () => {
    S.dnd = null; $$('.layer', list).forEach((x) => { x.draggable = false; x.classList.remove('is-dragging', 'drop-before', 'drop-after'); });
  });

  function toggleVisible(L) {
    if (isNow() && active()) return blocked('Hoy, mostrar u ocultar capas requiere detener la salida.');
    const before = L.visible; L.visible = !L.visible;
    record({ type: 'visible', scene: S.scene, id: L.id, before, after: L.visible, by: 'user' });
    renderLayers();
  }

  function moveLayer(L, dir) {
    const sc = curScene(), before = sc.layers.map((l) => l.id), i = sc.layers.indexOf(L), j = clamp(i + dir, 0, sc.layers.length - 1);
    if (i === j) return;
    sc.layers.splice(i, 1); sc.layers.splice(j, 0, L);
    record({ type: 'order', scene: S.scene, before, after: sc.layers.map((l) => l.id), by: 'user' });
    renderLayers();
  }

  function openLayerMenu(anchor, L) {
    const el = openPop(anchor, `
      <button class="menu-item" data-a="up">Traer adelante<kbd>⌘]</kbd></button>
      <button class="menu-item" data-a="down">Enviar atrás<kbd>⌘[</kbd></button>
      <div class="menu-sep"></div>
      <button class="menu-item" data-a="fit">Ajustar al lienzo</button>
      <button class="menu-item" data-a="safe">Ajustar al margen seguro</button>
      <div class="menu-sep"></div>
      <button class="menu-item" data-a="remove">Quitar de la escena<kbd>⌫</kbd></button>`, { role: 'menu' });
    el.addEventListener('click', (e) => {
      const a = e.target.closest('[data-a]'); if (!a) return;
      closePop();
      const before = { ...rectOf(L) };
      const rectTo = (to) => { tween(L, S.variant, to); record({ type: 'rect', scene: S.scene, variant: S.variant, id: L.id, before, after: to, by: 'user' }); };
      if (a.dataset.a === 'up') moveLayer(L, 1);
      if (a.dataset.a === 'down') moveLayer(L, -1);
      if (a.dataset.a === 'fit') rectTo(R(0, 0, G.w, G.h));
      if (a.dataset.a === 'safe') rectTo(R(SAFE, SAFE, G.w - SAFE * 2, G.h - SAFE * 2));
      if (a.dataset.a === 'remove') toast('warn', 'Quitar capas se diseña con la biblioteca de fuentes (fase 3).', null, 'warn');
    });
  }

  /* ---------------- Scenes ---------------- */
  const scenesEl = $('#scenes');
  function renderScenes() {
    scenesEl.innerHTML = scenes.map((sc, i) => `
      <li><button class="scene" data-id="${sc.id}" aria-current="${sc.id === S.scene}" data-live="${active()}">
        <div class="thumb"><canvas></canvas></div>
        <div class="meta"><b>${esc(sc.name)}</b><span class="onair">Al aire</span><kbd class="num">⌘${i + 1}</kbd></div>
      </button></li>`).join('');
    $('#sceneCount').textContent = scenes.length;
    sizeThumbs(); renderThumbs(performance.now() / 1000);
  }
  function sizeThumbs() {
    $$('.scene canvas', scenesEl).forEach((c) => {
      const w = c.parentElement.clientWidth, h = c.parentElement.clientHeight, d = devicePixelRatio || 1;
      c.width = Math.round(w * d); c.height = Math.round(h * d); c.dataset.w = w; c.dataset.h = h;
    });
  }
  function renderThumbs(t) {
    $$('.scene', scenesEl).forEach((b) => {
      const c = $('canvas', b), ctx = c.getContext('2d'), sc = sceneById(b.dataset.id);
      const w = +c.dataset.w, h = +c.dataset.h, d = devicePixelRatio || 1, { w: cw, h: ch } = CANVAS[S.variant];
      const k = Math.min(w / cw, h / ch);
      ctx.setTransform(d, 0, 0, d, 0, 0); ctx.fillStyle = '#0E0F12'; ctx.fillRect(0, 0, w, h);
      ctx.setTransform(d * k, 0, 0, d * k, d * (w - cw * k) / 2, d * (h - ch * k) / 2);
      drawScene(ctx, sc, S.variant, t);
    });
  }
  function updateSceneMarks() {
    $$('.scene', scenesEl).forEach((b) => { b.setAttribute('aria-current', b.dataset.id === S.scene); b.dataset.live = active(); });
  }

  function switchScene(id, { force = false } = {}) {
    if (id === S.scene) return;
    if (!force && isNow() && active()) return blocked('Hoy, cambiar de escena requiere detener la salida.');
    if (!RM.matches) {
      const snap = document.createElement('canvas'); snap.width = program.width; snap.height = program.height;
      snap.getContext('2d').drawImage(program, 0, 0);
      S.fade = { img: snap, start: performance.now() };
    }
    S.scene = id;
    if (!layerById(S.selected)) S.selected = null;
    if (S.suggestion.state === 'preview') S.suggestion.state = 'idle';
    $('#sceneTitle').textContent = curScene().name;
    updateSceneMarks(); renderLayers();
  }
  scenesEl.addEventListener('click', (e) => { const b = e.target.closest('.scene'); if (b) switchScene(b.dataset.id); });

  function setVariant(v) {
    if (v === S.variant) return;
    S.variant = v;
    $$('#variantSeg button').forEach((b) => b.setAttribute('aria-checked', b.dataset.variant === v));
    $('#canvasSize').textContent = `${CANVAS[v].w} × ${CANVAS[v].h}`;
    program.classList.add('is-swapping');
    layoutProgram(); renderLayers(); renderThumbs(performance.now() / 1000);
    requestAnimationFrame(() => requestAnimationFrame(() => program.classList.remove('is-swapping')));
  }
  $('#variantSeg').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) setVariant(b.dataset.variant); });

  /* ---------------- Agent suggestion ---------------- */
  function renderAgentCount() {
    const pending = suggestionPending();
    $('#agentCount').style.display = pending ? '' : 'none';
  }
  const suggestionPending = () => !isNow() && (S.suggestion.state === 'idle' || S.suggestion.state === 'preview');

  function openSuggestion() {
    const g = S.suggestion;
    if (g.scene !== S.scene) switchScene(g.scene, { force: true });
    if (g.variant !== S.variant) setVariant(g.variant);
    g.state = 'preview';
    select(g.layer); renderLayers(); renderDiff();
    requestAnimationFrame(() => $('#proposalApply').focus({ preventScroll: true }));
  }
  function closeSuggestion() { S.suggestion.state = 'idle'; renderLayers(); }
  function renderDiff() {
    const L = layerById(S.suggestion.layer, sceneById(S.suggestion.scene)), r = rectOf(L, S.suggestion.variant), to = S.suggestion.to;
    const row = (k, a, b) => a === b ? '' : `<span>${k}</span><span><b>${Math.round(a)}</b> → <span class="to">${b}</span></span>`;
    $('#proposalDiff').innerHTML = row('X', r.x, to.x) + row('Y', r.y, to.y) + row('Ancho', r.w, to.w) + row('Alto', r.h, to.h);
  }
  function applySuggestion() {
    const g = S.suggestion, L = layerById(g.layer, sceneById(g.scene)), before = { ...rectOf(L, g.variant) };
    g.state = 'applied';
    tween(L, g.variant, g.to);
    record({ type: 'rect', scene: g.scene, variant: g.variant, id: L.id, before, after: { ...g.to }, by: 'agent' });
    S.agentLog.unshift({ what: 'Alineó la Webcam al margen seguro', tool: 'set_transform', when: 'ahora' });
    renderLayers(); renderAgentCount();
    flashFields();
    toast('agent', 'Webcam alineada al margen seguro', { label: 'Deshacer', kbd: '⌘Z', run: undo }, 'agent');
  }
  function rejectSuggestion() {
    S.suggestion.state = 'dismissed'; renderLayers(); renderAgentCount();
    toast('agent', 'Propuesta descartada', { label: 'Recuperar', run: () => { S.suggestion.state = 'idle'; renderLayers(); renderAgentCount(); } }, 'agent');
  }
  function flashFields() { $$('.layer[aria-selected="true"] .field').forEach((f) => { f.classList.remove('is-changed'); void f.offsetWidth; f.classList.add('is-changed'); }); }
  $('#proposalApply').addEventListener('click', applySuggestion);
  $('#proposalReject').addEventListener('click', rejectSuggestion);

  $('#agentBtn').addEventListener('click', (e) => {
    const pending = suggestionPending();
    const items = (pending ? [{ what: 'Propone alinear la Webcam al margen seguro', tool: 'Pendiente de revisión', when: 'ahora', pending: true }] : []).concat(S.agentLog);
    const el = openPop(e.currentTarget, `
      <div class="pad">
        <h3>Agente local</h3>
        <p>Conectado por MCP a este mismo estudio. Controla escenas y salidas; nunca transporta video.</p>
        <ul class="history">${items.map((it) => `<li${it.pending ? ' data-pending' : ''}><span>${esc(it.what)}</span><time>${it.when}</time><small>${esc(it.tool)}</small></li>`).join('')}</ul>
      </div>
      <div class="actions">${pending ? '<button class="btn btn-agent btn-sm" data-a="review">Revisar propuesta</button>' : '<button class="btn btn-sm" data-a="close">Cerrar</button>'}</div>`, { width: 300 });
    el.addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-a]'); if (!a) return;
      closePop(); if (a.dataset.a === 'review') openSuggestion();
    });
  });

  /* ---------------- Outputs ---------------- */
  const fmt = (ms) => { const s = Math.max(0, Math.floor(ms / 1000)); return [s / 3600, (s % 3600) / 60, s % 60].map((n) => String(Math.floor(n)).padStart(2, '0')).join(':'); };

  function renderOutputs() {
    const st = $('#status');
    let state = 'idle', label = 'Listo para producir';
    if (S.out.busy) { state = 'busy'; label = S.out.busy; }
    else if (S.out.stream) { state = 'live'; label = 'En directo'; }
    else if (S.out.record) { state = 'recording'; label = 'Grabando'; }
    else if (S.lost) { state = 'lost'; label = 'Webcam sin señal'; }
    st.dataset.state = state;
    $('#statusLabel').textContent = label;
    $('#statusTime').style.display = active() && !S.out.busy ? '' : 'none';
    $('#statusSub').style.display = S.out.stream && S.out.record && !S.out.busy ? '' : 'none';
    const rb = $('#recordBtn'), sb = $('#streamBtn');
    rb.setAttribute('aria-pressed', S.out.record); $('.t', rb).textContent = S.out.record ? 'Grabando' : 'Grabar';
    sb.setAttribute('aria-pressed', S.out.stream); $('.t', sb).textContent = S.out.stream ? 'Emitiendo' : 'Emitir';
    $('#endBtn').style.display = active() ? '' : 'none';
    rb.disabled = sb.disabled = !!S.out.busy;
    $('#stage').dataset.live = active();
    updateSceneMarks();
    updateClock(performance.now(), true);
  }

  let lastClock = 0;
  function updateClock(now, force) {
    if (!force && now - lastClock < 250) return;
    lastClock = now;
    if (active()) $('#statusTime').textContent = fmt(now - S.out.since);
  }

  function stopOutputs(which, reason) {
    const wasRecording = S.out.record && (which === 'all' || which === 'record');
    S.out.busy = 'Finalizando…'; renderOutputs();
    setTimeout(() => {
      if (which === 'all' || which === 'stream') S.out.stream = false;
      if (which === 'all' || which === 'record') S.out.record = false;
      S.out.busy = null; renderOutputs();
      if (reason) return;
      if (wasRecording) toast('check', 'Grabación guardada en Grabaciones', { label: 'Mostrar', run: () => toast('check', 'La biblioteca de grabaciones se diseña en la fase 3.') });
      else toast('check', 'Emisión finalizada');
    }, RM.matches ? 0 : 700);
  }

  function startOutput(kind) {
    if (!active()) S.out.since = performance.now();
    S.out[kind] = true; renderOutputs();
  }

  function confirmPop(anchor, title, body, actionLabel, run, cancelLabel = 'Cancelar') {
    const el = openPop(anchor, `<div class="pad"><h3>${title}</h3><p>${body}</p></div>
      <div class="actions"><button class="btn btn-sm" data-a="no">${cancelLabel}</button><button class="btn btn-danger btn-sm" data-a="yes" data-autofocus>${actionLabel}</button></div>`, { width: 280 });
    el.addEventListener('click', (e) => { const a = e.target.closest('[data-a]'); if (!a) return; closePop(); if (a.dataset.a === 'yes') run(); });
  }

  $('#recordBtn').addEventListener('click', (e) => {
    if (S.out.record) return confirmPop(e.currentTarget, 'Detener la grabación', S.out.stream ? 'El archivo se cierra y la emisión continúa.' : 'El archivo se cierra y aparece en Grabaciones.', 'Detener', () => stopOutputs('record'));
    if (isNow() && S.out.stream) return blocked('Hoy Motive ejecuta una salida a la vez. Finaliza la emisión para grabar.');
    if (S.lost) return blocked('Reconecta la Webcam antes de grabar.');
    startOutput('record');
  });
  $('#streamBtn').addEventListener('click', (e) => {
    if (S.out.stream) return confirmPop(e.currentTarget, 'Detener la emisión', S.out.record ? 'El público deja de recibir imagen. La grabación continúa.' : 'El público deja de recibir imagen.', 'Detener', () => stopOutputs('stream'));
    if (isNow() && S.out.record) return blocked('Hoy Motive ejecuta una salida a la vez. Finaliza la grabación para emitir.');
    preflight(e.currentTarget);
  });
  $('#endBtn').addEventListener('click', (e) => {
    const both = S.out.stream && S.out.record;
    confirmPop(e.currentTarget, 'Finalizar la producción',
      both ? 'Se detienen la emisión y la grabación. El archivo se guarda en Grabaciones.' : S.out.stream ? 'Se detiene la emisión.' : 'Se detiene la grabación y el archivo se guarda en Grabaciones.',
      'Finalizar', () => stopOutputs('all'), 'Seguir');
  });

  function preflight(anchor) {
    const checks = [
      ['Fuentes de la escena', S.lost ? null : 'Disponibles', S.lost ? 'La Webcam no envía imagen' : null],
      ['Micrófono', 'Recibe señal'],
      ['Codificador', 'VideoToolbox H.264'],
      ['Destino', 'RTMP local'],
    ];
    const el = openPop(anchor, `<div class="pad"><h3>Antes de emitir</h3><p>Motive comprueba la escena y la salida antes de conectar.</p>
      <ul class="checks">${checks.map((c) => `<li data-s="wait"><span class="st"><span class="spin"></span></span>${c[0]}<span class="val"></span></li>`).join('')}</ul></div>
      <div class="actions"><button class="btn btn-sm" data-a="no">Cancelar</button><button class="btn btn-primary btn-sm" data-a="go" disabled>Emitir ahora</button></div>`, { width: 300 });
    const lis = $$('.checks li', el);
    let failed = false;
    checks.forEach((c, i) => setTimeout(() => {
      if (!el.isConnected) return;
      const li = lis[i], ok = !!c[1];
      li.dataset.s = ok ? 'ok' : 'fail';
      $('.st', li).innerHTML = icon(ok ? 'check' : 'warn');
      $('.val', li).textContent = ok ? c[1] : c[2];
      if (!ok) failed = true;
      if (i === checks.length - 1) {
        const go = $('[data-a="go"]', el);
        if (failed) { go.textContent = 'Reconectar fuentes'; go.dataset.a = 'reconnect'; }
        go.disabled = false; go.focus();
      }
    }, (RM.matches ? 0 : 220) * (i + 1)));
    el.addEventListener('click', (e) => {
      const a = e.target.closest('[data-a]'); if (!a || a.disabled) return;
      closePop();
      if (a.dataset.a === 'go') startOutput('stream');
      if (a.dataset.a === 'reconnect') reconnect();
    });
  }

  /* ---------------- Source loss and recovery ---------------- */
  const banner = $('#banner');
  function loseCamera() {
    S.lost = true;
    const wasActive = active(), wasRecording = S.out.record;
    if (wasActive) { S.out.stream = false; S.out.record = false; }
    $('#bannerText').innerHTML = wasActive
      ? `<b>La salida se detuvo.</b> <span>La Webcam dejó de enviar imagen${wasRecording ? '; la grabación quedó guardada' : ''}.</span>`
      : `<b>La Webcam dejó de enviar imagen.</b> <span>Comprueba la conexión y reintenta.</span>`;
    banner.classList.add('is-on');
    $('#simLoss').textContent = 'Restaurar la cámara';
    renderOutputs(); renderLayers();
  }
  function reconnect() {
    const b = $('#reconnectBtn');
    b.disabled = true; b.lastChild.textContent = 'Reconectando…';
    setTimeout(() => {
      S.lost = false; b.disabled = false; b.lastChild.textContent = 'Reconectar fuentes';
      banner.classList.remove('is-on'); $('#simLoss').textContent = 'Perder la cámara';
      renderOutputs(); renderLayers();
      toast('check', 'Webcam reconectada. La salida sigue detenida hasta que la inicies.');
    }, RM.matches ? 0 : 900);
  }
  $('#reconnectBtn').addEventListener('click', reconnect);
  $('#simLoss').addEventListener('click', () => (S.lost ? reconnect() : loseCamera()));

  /* ---------------- Audio ---------------- */
  const channels = [
    { id: 'mic', name: 'Voz', device: 'Micrófono MacBook Pro', icon: 'mic', gain: 0, muted: false, peak: -60, peakAt: 0, ann: ['partial', 'Nivel real · volumen y silencio por implementar'] },
    { id: 'sys', name: 'Sistema', device: 'Audio de la Mac', icon: 'display', gain: -6, muted: false, peak: -60, peakAt: 0, future: true, ann: ['future', 'Audio del sistema: futuro'] },
  ];
  const DB_MIN = -60, DB_MAX = 6;
  const dbText = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1).replace('.', ',')} dB`;
  const dbPos = (v) => (v - DB_MIN) / (DB_MAX - DB_MIN);

  function renderChannels() {
    $('#channels').innerHTML = channels.map((c) => `
      <div class="channel ann-host" data-id="${c.id}" data-muted="${c.muted}" ${c.future ? 'data-scope="vision"' : ''} data-ann="${c.ann[0]}" data-ann-label="${c.ann[1]}">
        <div class="ch-top">${icon(c.icon)}<b>${c.name}</b><small>${c.device}</small><span class="db num">${c.muted ? 'Silenciado' : dbText(c.gain)}</span></div>
        <div class="ch-body">
          <div>
            <div class="meter" aria-hidden="true"><div class="bar"><div class="lit"></div></div><div class="bar"><div class="lit"></div></div><span class="peak"></span></div>
            <div class="fader" role="slider" tabindex="0" aria-label="Volumen de ${c.name}" aria-valuemin="${DB_MIN}" aria-valuemax="${DB_MAX}" aria-valuenow="${c.gain}" aria-valuetext="${dbText(c.gain)}">
              <div class="track"></div><div class="fill"></div><span class="unity" style="left:${dbPos(0) * 100}%"></span><span class="knob"></span>
            </div>
          </div>
          <button class="icon-btn icon-btn-sm mute" aria-pressed="${c.muted}" aria-label="${c.muted ? 'Activar' : 'Silenciar'} ${c.name}" data-tip="${c.muted ? 'Activar' : 'Silenciar'}">${icon(c.muted ? 'speaker-off' : 'speaker')}</button>
        </div>
      </div>`).join('');
    channels.forEach(syncFader);
  }
  function syncFader(c) {
    const el = $(`.channel[data-id="${c.id}"]`); if (!el) return;
    const p = dbPos(c.gain) * 100;
    $('.knob', el).style.left = p + '%'; $('.fill', el).style.width = p + '%';
    const f = $('.fader', el); f.setAttribute('aria-valuenow', c.gain); f.setAttribute('aria-valuetext', dbText(c.gain));
    $('.db', el).textContent = c.muted ? 'Silenciado' : dbText(c.gain);
  }
  const chan = (el) => channels.find((c) => c.id === el.closest('.channel').dataset.id);
  $('#channels').addEventListener('pointerdown', (e) => {
    const f = e.target.closest('.fader'); if (!f) return;
    const c = chan(f), r = f.getBoundingClientRect();
    const set = (x) => { c.gain = Math.round((DB_MIN + clamp((x - r.left) / r.width, 0, 1) * (DB_MAX - DB_MIN)) * 2) / 2; if (Math.abs(c.gain) < 1) c.gain = 0; syncFader(c); };
    f.setPointerCapture(e.pointerId); f.focus(); set(e.clientX);
    const mv = (ev) => set(ev.clientX);
    const up = () => { f.removeEventListener('pointermove', mv); f.removeEventListener('pointerup', up); };
    f.addEventListener('pointermove', mv); f.addEventListener('pointerup', up);
  });
  $('#channels').addEventListener('dblclick', (e) => { const f = e.target.closest('.fader'); if (f) { const c = chan(f); c.gain = 0; syncFader(c); } });
  $('#channels').addEventListener('keydown', (e) => {
    const f = e.target.closest('.fader'); if (!f) return;
    const c = chan(f), step = e.shiftKey ? 6 : 1;
    const map = { ArrowRight: step, ArrowUp: step, ArrowLeft: -step, ArrowDown: -step, Home: -999, End: 999 };
    if (!(e.key in map)) return;
    e.preventDefault(); c.gain = clamp(c.gain + map[e.key], DB_MIN, DB_MAX); syncFader(c);
  });
  $('#channels').addEventListener('click', (e) => {
    const m = e.target.closest('.mute'); if (!m) return;
    const c = chan(m); c.muted = !c.muted; renderChannels();
    $(`.channel[data-id="${c.id}"] .mute`).focus();
  });

  function levelFor(c, t) {
    if (c.id === 'mic') {
      const talking = Math.sin(t * 0.7) + Math.sin(t * 1.9 + 1) > -0.7;
      return talking ? -27 + 15 * Math.abs(Math.sin(t * 9.3) * Math.sin(t * 3.1 + 1)) + Math.random() * 4 : -56 + Math.random() * 3;
    }
    return -24 + 6 * Math.sin(t * 2.1) * Math.sin(t * 0.6) + Math.random() * 2.5;
  }
  function updateMeters(now) {
    const t = now / 1000;
    channels.forEach((c) => {
      const el = $(`.channel[data-id="${c.id}"]`); if (!el || !el.offsetParent) return;
      const base = levelFor(c, t) + c.gain;
      const lits = $$('.lit', el);
      [base, base - 1.5 + Math.random() * 2].forEach((db, i) => { lits[i].style.clipPath = `inset(0 ${(1 - clamp((db + 60) / 60, 0, 1)) * 100}% 0 0)`; });
      if (base > c.peak || now - c.peakAt > 1200) { c.peak = Math.max(base, c.peak - 0.8); if (base >= c.peak) c.peakAt = now; }
      $('.peak', el).style.left = `calc(${clamp((c.peak + 60) / 60, 0, 1) * 100}% - 2px)`;
    });
  }

  /* ---------------- Popovers, toasts, tooltips ---------------- */
  let pop = null;
  function openPop(anchor, html, opts = {}) {
    closePop(true);
    const el = document.createElement('div');
    el.className = 'popover'; el.setAttribute('role', opts.role || 'dialog'); el.innerHTML = html;
    if (opts.width) el.style.width = opts.width + 'px';
    document.body.appendChild(el);
    const r = anchor.getBoundingClientRect(), pr = el.getBoundingClientRect();
    let x = r.right - pr.width; if (r.left + pr.width < innerWidth - 8 && r.left < innerWidth / 2) x = r.left;
    x = clamp(x, 8, innerWidth - pr.width - 8);
    let y = r.bottom + 6; if (y + pr.height > innerHeight - 8) y = r.top - pr.height - 6;
    el.style.left = x + 'px'; el.style.top = y + 'px';
    el.style.transformOrigin = y < r.top ? 'bottom center' : 'top center';
    requestAnimationFrame(() => el.classList.add('is-on'));
    anchor.setAttribute('aria-expanded', 'true');
    pop = { el, anchor };
    const f = $('[data-autofocus]', el) || $('button:not([disabled])', el);
    if (f) requestAnimationFrame(() => f.focus({ preventScroll: true }));
    return el;
  }
  function closePop(instant) {
    if (!pop) return;
    const { el, anchor } = pop; pop = null;
    anchor.setAttribute('aria-expanded', 'false');
    if (instant) { el.remove(); return; }
    el.classList.remove('is-on'); setTimeout(() => el.remove(), 120);
    if (document.activeElement && el.contains(document.activeElement)) anchor.focus({ preventScroll: true });
  }
  document.addEventListener('pointerdown', (e) => { if (pop && !pop.el.contains(e.target) && !pop.anchor.contains(e.target)) closePop(); }, true);

  let toastTimer = null;
  function toast(ic, text, action, tone) {
    const host = $('#toastHost');
    host.innerHTML = `<div class="toast" data-tone="${tone || ''}">${icon(ic)}<span>${esc(text)}</span>${action ? `<button class="btn btn-sm">${esc(action.label)}${action.kbd ? ` <kbd>${action.kbd}</kbd>` : ''}</button>` : ''}</div>`;
    const el = host.firstElementChild;
    requestAnimationFrame(() => el.classList.add('is-on'));
    if (action) $('button', el).addEventListener('click', () => { hide(); action.run(); });
    const hide = () => { el.classList.remove('is-on'); setTimeout(() => el.remove(), 200); };
    clearTimeout(toastTimer);
    const arm = () => { toastTimer = setTimeout(hide, action ? 6000 : 3200); };
    el.addEventListener('pointerenter', () => clearTimeout(toastTimer));
    el.addEventListener('pointerleave', arm);
    arm();
  }
  const blocked = (msg) => toast('warn', msg, null, 'warn');

  const tip = $('#tooltip'); let tipTimer = null;
  document.addEventListener('pointerover', (e) => {
    const t = e.target.closest('[data-tip]');
    clearTimeout(tipTimer); tip.classList.remove('is-on');
    if (!t) return;
    tipTimer = setTimeout(() => {
      tip.innerHTML = esc(t.dataset.tip) + (t.dataset.kbd ? `<kbd>${t.dataset.kbd}</kbd>` : '');
      const r = t.getBoundingClientRect();
      tip.style.left = clamp(r.left + r.width / 2 - tip.offsetWidth / 2, 8, innerWidth - tip.offsetWidth - 8) + 'px';
      tip.style.top = (r.bottom + 6) + 'px';
      tip.classList.add('is-on');
    }, 550);
  });
  document.addEventListener('pointerdown', () => { clearTimeout(tipTimer); tip.classList.remove('is-on'); });

  /* ---------------- Toolbar menus ---------------- */
  $('#projectBtn').addEventListener('click', (e) => {
    const el = openPop(e.currentTarget, `
      <div class="menu-label">Proyecto</div>
      <button class="menu-item" data-a="save">Guardar proyecto<kbd>⌘S</kbd></button>
      <button class="menu-item" data-a="load">Restaurar proyecto</button>
      <div class="menu-sep"></div>
      <button class="menu-item" data-a="out">Ajustes de salida<kbd>⌘,</kbd></button>
      <button class="menu-item" data-a="diag">Diagnóstico</button>`, { role: 'menu' });
    el.addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-a]'); if (!a) return; closePop();
      if (a.dataset.a === 'save') toast('check', 'Proyecto guardado');
      else toast('check', 'Esta pantalla se diseña en la fase 3.');
    });
  });
  $('#addSourceBtn').addEventListener('click', (e) => {
    const sc = curScene(), used = new Set(sc.layers.map((l) => l.src));
    const reuse = Object.entries(SOURCES).filter(([k]) => !used.has(k));
    const el = openPop(e.currentTarget, `
      <div class="menu-label">Capturar</div>
      <button class="menu-item" data-a="new">${icon('window')}Ventana</button>
      <button class="menu-item" data-a="new">${icon('camera')}Cámara</button>
      <button class="menu-item" data-a="new">${icon('overlay')}Overlay animado</button>
      ${reuse.length ? `<div class="menu-sep"></div><div class="menu-label">Reutilizar en ${esc(sc.name)}</div>` + reuse.map(([k, s]) => `<button class="menu-item" data-a="reuse" data-src="${k}">${icon(s.icon)}${esc((isNow() && s.nameNow) || s.name)}</button>`).join('') : ''}`, { role: 'menu' });
    el.addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-a]'); if (!a) return; closePop();
      if (a.dataset.a === 'new') {
        if (isNow() && active()) return blocked('Hoy, añadir capturas requiere detener la salida.');
        return toast('check', 'El selector de fuentes se diseña en la fase 3.');
      }
      const id = `${sc.id}-${a.dataset.src}-${Date.now() % 1e5}`;
      const L = layer(id, a.dataset.src, R(240, 135, 480, 270), R(70, 330, 400, 300), a.dataset.src === 'title' ? { text: ['Luz y materia', 'Taller en vivo'] } : {});
      sc.layers.push(L); S.selected = id; renderLayers();
      toast('check', `${srcName(L)} reutilizada en ${sc.name}`);
    });
  });
  $('#zoomBtn').addEventListener('click', (e) => {
    const el = openPop(e.currentTarget, `
      <button class="menu-item" data-z="fit">Ajustar a la ventana${S.zoom === 'fit' ? '<kbd>✓</kbd>' : ''}</button>
      <button class="menu-item" data-z="1">Tamaño real${S.zoom === '1' ? '<kbd>✓</kbd>' : ''}</button>`, { role: 'menu' });
    el.addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-z]'); if (!a) return; closePop();
      S.zoom = a.dataset.z; $('#zoomBtn').firstChild.textContent = S.zoom === 'fit' ? 'Ajustar' : '100 %'; layoutProgram();
    });
  });
  const toggleSafe = () => { S.safe = !S.safe; $('#safeBtn').setAttribute('aria-pressed', S.safe); };
  $('#safeBtn').addEventListener('click', toggleSafe);
  $('#addSceneBtn').addEventListener('click', () => toast('check', 'Crear escenas se diseña en la fase 3.'));

  /* ---------------- Keyboard ---------------- */
  document.addEventListener('keydown', (e) => {
    const tgt = e.target instanceof Element ? e.target : document.body;
    const inField = tgt.matches('input, textarea');
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === 'Escape') {
      if (pop) return closePop();
      if (S.drag) return endDrag(true);
      if (S.suggestion.state === 'preview') return closeSuggestion();
      if (!inField) select(null);
      return;
    }
    if (/^[1-9]$/.test(e.key) && (mod || !inField)) {
      const sc = scenes[+e.key - 1];
      if (sc) { e.preventDefault(); switchScene(sc.id); }
      return;
    }
    if (mod && e.key.toLowerCase() === 'z' && !inField) { e.preventDefault(); return e.shiftKey ? redo() : undo(); }
    if (inField || pop) return;
    if (e.key === 'Enter' && S.suggestion.state === 'preview' && !tgt.closest('button')) { e.preventDefault(); return applySuggestion(); }
    if (e.shiftKey && !mod && e.key.toLowerCase() === 's') return toggleSafe();
    if (mod && (e.key === ']' || e.key === '[')) { const L = selLayer(); if (L) { e.preventDefault(); moveLayer(L, e.key === ']' ? 1 : -1); } return; }
    const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (arrows[e.key] && selLayer() && !tgt.closest('.fader, .seg')) {
      e.preventDefault();
      const L = selLayer(), before = { ...rectOf(L) }, k = e.shiftKey ? 10 : 1, [dx, dy] = arrows[e.key];
      L.t[S.variant] = { ...before, x: before.x + dx * k, y: before.y + dy * k };
      record({ type: 'rect', scene: S.scene, variant: S.variant, id: L.id, before, after: { ...rectOf(L) }, by: 'user' });
      syncInspector();
    }
  });

  /* ---------------- Prototype controls ---------------- */
  $('#protoToggle').addEventListener('click', () => { const p = $('#proto'); p.dataset.collapsed = p.dataset.collapsed !== 'true'; });
  $$('#proto .seg').forEach((seg) => seg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    $$('button', seg).forEach((x) => x.setAttribute('aria-checked', x === b));
    const v = b.dataset.v;
    switch (seg.dataset.proto) {
      case 'scope':
        S.scope = v;
        document.body.classList.toggle('scope-now', v === 'now'); document.body.classList.toggle('scope-vision', v === 'vision');
        if (v === 'now' && S.out.stream && S.out.record) S.out.record = false;
        if (S.suggestion.state === 'preview') S.suggestion.state = 'idle';
        renderOutputs(); renderLayers(); renderAgentCount(); renderThumbs(performance.now() / 1000);
        break;
      case 'theme': document.documentElement.dataset.theme = v; break;
      case 'ann': document.body.classList.toggle('annotate', v === 'on'); break;
      case 'size':
        document.body.classList.toggle('windowed', v === 'small');
        requestAnimationFrame(() => { layoutProgram(); sizeThumbs(); renderThumbs(performance.now() / 1000); drawLayerThumbs(performance.now() / 1000); });
        break;
    }
  }));

  /* ---------------- Metrics (sampled) ---------------- */
  setInterval(() => {
    $('#cpu').textContent = `${12 + Math.round(Math.random() * 4)} %`;
  }, 2000);

  /* ---------------- Boot ---------------- */
  new ResizeObserver(() => { layoutProgram(); }).observe(area);
  new ResizeObserver(() => { sizeThumbs(); renderThumbs(performance.now() / 1000); }).observe(scenesEl);

  renderScenes(); renderLayers(); renderChannels(); renderOutputs(); renderAgentCount();
  layoutProgram();

  let lastFrame = 0, lastThumb = 0, lastLayerThumb = 0;
  function loop(now) {
    requestAnimationFrame(loop);
    updateMeters(now); updateClock(now);
    if (now - lastFrame >= 32) { lastFrame = now; renderProgram(now / 1000, now); syncOverlay(); }
    if (now - lastThumb > 600) { lastThumb = now; renderThumbs(now / 1000); }
    if (now - lastLayerThumb > 1500) { lastLayerThumb = now; drawLayerThumbs(now / 1000); }
  }
  requestAnimationFrame(loop);

  // Expose a tiny hook for screenshot automation.
  window.MotiveProto = { S, openSuggestion, setVariant, switchScene, loseCamera, reconnect };
})();
