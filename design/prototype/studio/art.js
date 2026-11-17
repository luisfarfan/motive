/* Motive prototype — procedural placeholder media.
   Every image in this prototype is drawn here from code: no photographs,
   stock or third-party assets. Same license as the repository
   (GPL-3.0-or-later). The person in the webcam is a soft illustration,
   deliberately out of focus: it stands in for a real camera feed. */

const Art = (() => {
  const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
  const rng = (seed) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

  const bez = (p, u) => {
    const v = 1 - u, a = v * v * v, b = 3 * v * v * u, c = 3 * v * u * u, d = u * u * u;
    return [a * p[0][0] + b * p[1][0] + c * p[2][0] + d * p[3][0], a * p[0][1] + b * p[1][1] + c * p[2][1] + d * p[3][1]];
  };
  const bezD = (p, u) => {
    const v = 1 - u;
    return [
      3 * v * v * (p[1][0] - p[0][0]) + 6 * v * u * (p[2][0] - p[1][0]) + 3 * u * u * (p[3][0] - p[2][0]),
      3 * v * v * (p[1][1] - p[0][1]) + 6 * v * u * (p[2][1] - p[1][1]) + 3 * u * u * (p[3][1] - p[2][1]),
    ];
  };

  // A twisted glass ribbon: many faint strands that converge where the band turns edge-on.
  function ribbon(ctx, pts, width, twist, phase, hue, k) {
    const N = 180, S = 64;
    for (let j = 0; j < S; j++) {
      const s = (j / (S - 1)) * 2 - 1;
      const edge = Math.pow(Math.abs(s), 10);
      const core = 1 - Math.abs(s);
      ctx.beginPath();
      for (let i = 0; i <= N; i++) {
        const u = i / N;
        const [x, y] = bez(pts, u);
        const [dx, dy] = bezD(pts, u);
        const L = Math.hypot(dx, dy) || 1;
        const taper = 0.25 + 0.75 * Math.sin(Math.PI * u);
        const off = s * width * k * Math.cos(u * Math.PI * twist + phase) * taper;
        const px = x * k + (-dy / L) * off, py = y * k + (dx / L) * off;
        if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      }
      ctx.strokeStyle = `hsla(${hue + s * 6 + edge * 6}, 100%, ${40 + edge * 26}%, ${0.05 + core * 0.035 + edge * 0.55})`;
      ctx.lineWidth = (1.6 + edge * 1.4) * k;
      ctx.stroke();
    }
  }

  function ribbons(w, h) {
    const c = mk(w, h), ctx = c.getContext('2d'), k = w / 960;
    const g = ctx.createRadialGradient(w * 0.34, h * 0.42, 0, w * 0.5, h * 0.5, w * 0.78);
    g.addColorStop(0, '#11414a'); g.addColorStop(0.5, '#0a262c'); g.addColorStop(1, '#040b0d');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);

    const layer = mk(w, h), lc = layer.getContext('2d');
    lc.globalCompositeOperation = 'lighter';
    ribbon(lc, [[-80, 470], [240, 40], [520, 640], [1040, 90]], 92, 2.3, 0.5, 20, k);
    ribbon(lc, [[90, 620], [320, 230], [690, 10], [1020, 400]], 64, 3.1, 1.2, 15, k);
    ribbon(lc, [[430, -60], [560, 290], [840, 380], [1010, 640]], 46, 1.7, 2.1, 26, k);

    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    ctx.filter = `blur(${40 * k}px)`; ctx.globalAlpha = 0.75; ctx.drawImage(layer, 0, 0);
    ctx.filter = `blur(${12 * k}px)`; ctx.globalAlpha = 0.6; ctx.drawImage(layer, 0, 0);
    ctx.filter = `blur(${3 * k}px)`; ctx.globalAlpha = 0.7; ctx.drawImage(layer, 0, 0);
    ctx.filter = 'none'; ctx.globalAlpha = 1; ctx.drawImage(layer, 0, 0);
    ctx.restore();

    const v = ctx.createRadialGradient(w / 2, h / 2, h * 0.35, w / 2, h / 2, w * 0.75);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.55)');
    ctx.fillStyle = v; ctx.fillRect(0, 0, w, h);
    return c;
  }

  function bokeh(w, h, seed = 7) {
    const c = mk(w, h), ctx = c.getContext('2d'), r = rng(seed), k = w / 960;
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, '#1d1611'); g.addColorStop(0.6, '#0d1a1c'); g.addColorStop(1, '#071012');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 26; i++) {
      const x = r() * w, y = h * (0.15 + r() * 0.75), rad = (30 + r() * 110) * k;
      const warm = r() > 0.28;
      const col = warm ? [255, 168 + r() * 50, 90 + r() * 40] : [80, 190, 200];
      const a = 0.08 + r() * 0.28;
      const rg = ctx.createRadialGradient(x, y, 0, x, y, rad);
      rg.addColorStop(0, `rgba(${col},${a})`);
      rg.addColorStop(0.82, `rgba(${col},${a * 0.8})`);
      rg.addColorStop(1, `rgba(${col},0)`);
      ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
    return c;
  }

  function webcam(w, h) {
    const c = mk(w, h), ctx = c.getContext('2d');
    const room = ctx.createLinearGradient(0, 0, w, h);
    room.addColorStop(0, '#3a2c22'); room.addColorStop(0.55, '#1f1914'); room.addColorStop(1, '#100d0b');
    ctx.fillStyle = room; ctx.fillRect(0, 0, w, h);

    // Shelf and books, far behind and soft
    ctx.save(); ctx.filter = `blur(${h * 0.012}px)`;
    ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(w * 0.66, h * 0.18, w * 0.34, h * 0.012);
    const books = ['#5b3a2a', '#2f3b3a', '#6d5236', '#3c2a24', '#47524a', '#7a5a3b'];
    let bx = w * 0.68;
    for (let i = 0; i < 9; i++) {
      const bw = w * (0.012 + (i % 3) * 0.005), bh = h * (0.1 + (i % 4) * 0.018);
      ctx.fillStyle = books[i % books.length]; ctx.globalAlpha = 0.7;
      ctx.fillRect(bx, h * 0.18 - bh, bw, bh); bx += bw + w * 0.003;
    }
    ctx.restore();

    // Lamp glow
    const lx = w * 0.17, ly = h * 0.36;
    let rg = ctx.createRadialGradient(lx, ly, 0, lx, ly, h * 0.5);
    rg.addColorStop(0, 'rgba(255,196,120,.55)'); rg.addColorStop(0.25, 'rgba(255,170,90,.18)'); rg.addColorStop(1, 'rgba(255,150,80,0)');
    ctx.fillStyle = rg; ctx.fillRect(0, 0, w, h);
    rg = ctx.createRadialGradient(lx, ly, 0, lx, ly, h * 0.07);
    rg.addColorStop(0, 'rgba(255,240,210,1)'); rg.addColorStop(0.6, 'rgba(255,214,150,.9)'); rg.addColorStop(1, 'rgba(255,200,130,0)');
    ctx.fillStyle = rg; ctx.beginPath(); ctx.ellipse(lx, ly, h * 0.09, h * 0.06, 0, 0, Math.PI * 2); ctx.fill();

    // Person
    const cx = w * 0.53, s = h;
    ctx.save(); ctx.filter = `blur(${h * 0.0065}px)`;
    // hair volume behind
    ctx.fillStyle = '#21160f';
    ctx.beginPath(); ctx.ellipse(cx, s * 0.43, s * 0.2, s * 0.25, 0, 0, Math.PI * 2); ctx.fill();
    const hr = rng(3);
    for (let i = 0; i < 70; i++) {
      const a = Math.PI * (0.95 + hr() * 1.1), rr = s * (0.17 + hr() * 0.07);
      ctx.beginPath(); ctx.arc(cx + Math.cos(a) * rr, s * 0.42 + Math.sin(a) * rr * 1.1, s * (0.025 + hr() * 0.03), 0, Math.PI * 2); ctx.fill();
    }
    ctx.beginPath(); ctx.ellipse(cx - s * 0.16, s * 0.6, s * 0.07, s * 0.16, 0.2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(cx + s * 0.16, s * 0.6, s * 0.07, s * 0.16, -0.2, 0, Math.PI * 2); ctx.fill();
    // shoulders
    const sw = ctx.createLinearGradient(cx - s * 0.5, 0, cx + s * 0.5, 0);
    sw.addColorStop(0, '#efe3cd'); sw.addColorStop(0.55, '#cdbd9f'); sw.addColorStop(1, '#8f8068');
    ctx.fillStyle = sw;
    ctx.beginPath();
    ctx.moveTo(cx - s * 0.52, s * 1.02);
    ctx.bezierCurveTo(cx - s * 0.48, s * 0.78, cx - s * 0.3, s * 0.72, cx - s * 0.1, s * 0.7);
    ctx.lineTo(cx + s * 0.1, s * 0.7);
    ctx.bezierCurveTo(cx + s * 0.3, s * 0.72, cx + s * 0.48, s * 0.78, cx + s * 0.52, s * 1.02);
    ctx.closePath(); ctx.fill();
    // collar shadow
    ctx.fillStyle = 'rgba(70,50,35,.35)';
    ctx.beginPath(); ctx.moveTo(cx - s * 0.09, s * 0.7); ctx.quadraticCurveTo(cx, s * 0.8, cx + s * 0.09, s * 0.7); ctx.closePath(); ctx.fill();
    // neck
    const nk = ctx.createLinearGradient(cx - s * 0.06, 0, cx + s * 0.06, 0);
    nk.addColorStop(0, '#c99476'); nk.addColorStop(1, '#91604a');
    ctx.fillStyle = nk; ctx.beginPath(); ctx.ellipse(cx, s * 0.64, s * 0.058, s * 0.09, 0, 0, Math.PI * 2); ctx.fill();
    // head
    const hd = ctx.createRadialGradient(cx - s * 0.06, s * 0.4, s * 0.02, cx, s * 0.44, s * 0.2);
    hd.addColorStop(0, '#e8bb9b'); hd.addColorStop(0.6, '#c58f71'); hd.addColorStop(1, '#8e5c45');
    ctx.fillStyle = hd; ctx.beginPath(); ctx.ellipse(cx, s * 0.45, s * 0.118, s * 0.152, 0, 0, Math.PI * 2); ctx.fill();
    // soft features
    ctx.fillStyle = 'rgba(60,35,25,.38)';
    ctx.beginPath(); ctx.ellipse(cx - s * 0.043, s * 0.435, s * 0.011, s * 0.007, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(cx + s * 0.043, s * 0.435, s * 0.011, s * 0.007, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(120,55,45,.3)'; ctx.lineWidth = s * 0.008; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(cx - s * 0.03, s * 0.53); ctx.quadraticCurveTo(cx, s * 0.548, cx + s * 0.03, s * 0.53); ctx.stroke();
    // fringe
    ctx.fillStyle = '#21160f';
    for (let i = 0; i < 9; i++) {
      ctx.beginPath(); ctx.arc(cx - s * 0.1 + i * s * 0.025, s * 0.31 + Math.sin(i) * s * 0.01, s * 0.04, 0, Math.PI * 2); ctx.fill();
    }
    // rim light from the lamp side
    ctx.strokeStyle = 'rgba(255,200,140,.35)'; ctx.lineWidth = s * 0.008;
    ctx.beginPath(); ctx.ellipse(cx, s * 0.45, s * 0.118, s * 0.152, 0, Math.PI * 0.75, Math.PI * 1.25); ctx.stroke();
    ctx.restore();

    // Microphone in the foreground
    ctx.save(); ctx.translate(w * 0.86, h * 0.92); ctx.rotate(-0.5);
    ctx.fillStyle = '#0c0c0d'; ctx.beginPath(); ctx.roundRect(-s * 0.07, -s * 0.24, s * 0.14, s * 0.34, s * 0.07); ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,.08)'; ctx.lineWidth = 1;
    for (let i = 0; i < 6; i++) { ctx.beginPath(); ctx.moveTo(-s * 0.06, -s * 0.2 + i * s * 0.025); ctx.lineTo(s * 0.06, -s * 0.2 + i * s * 0.025); ctx.stroke(); }
    ctx.restore();

    const v = ctx.createRadialGradient(w / 2, h / 2, h * 0.3, w / 2, h / 2, w * 0.7);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.45)');
    ctx.fillStyle = v; ctx.fillRect(0, 0, w, h);
    return c;
  }

  let cache = null;
  function init() {
    if (cache) return cache;
    cache = { ribbons: ribbons(1920, 1080), bokeh: bokeh(1920, 1080), cam: webcam(1280, 720) };
    return cache;
  }

  return { init };
})();
