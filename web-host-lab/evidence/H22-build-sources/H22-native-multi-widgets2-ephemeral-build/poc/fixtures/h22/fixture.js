'use strict';
// Original controlled web workloads for H22. These are NOT the native Element
// Lab renderers, and NOT a claim about arbitrary creator packages.
const config = globalThis.MotiveOwnedFixture;
const canvas = document.querySelector('#surface'), ctx = canvas.getContext('2d');
let active = false, suspended = false, started = 0, serial = 0, raf = 0, ready = false;
const duration = config.kind === 2 ? 3200 : 4600;

function draw(now) {
  raf = 0;
  if (canvas.width !== innerWidth || canvas.height !== innerHeight) {
    canvas.width = innerWidth; canvas.height = innerHeight;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  // Separate fixed identity oracle, not used as evidence of animation cadence.
  ctx.fillStyle = `rgb(${config.instance * 32},64,192)`; ctx.fillRect(100,32,16,16);
  const elapsed = now - started;
  if (active && elapsed >= duration) { active = false; motiveFixturePhase(9); }
  if (active || config.kind === 3) {
    const progress = config.kind === 3 ? 1 : Math.min(1, elapsed / 300, (duration - elapsed) / 300);
    const opacity = Math.max(0, progress);
    ctx.save(); ctx.globalAlpha = opacity;
    if (config.kind === 1 || config.kind === 3) {
      const w = Math.min(canvas.width - 64, 660), y = canvas.height - 132;
      ctx.translate((1 - opacity) * -100, 0);
      ctx.fillStyle = 'rgba(16,23,36,.92)'; ctx.fillRect(32,y,w,92);
      ctx.fillStyle = '#59ddb7'; ctx.fillRect(32,y,5,92);
      ctx.fillStyle = '#ffffff'; ctx.font = 'bold 26px sans-serif'; ctx.fillText('MOTIVE · ESTUDIO LOCAL',52,y+36);
      ctx.fillStyle = '#c6d2e0'; ctx.font = '17px sans-serif'; ctx.fillText(`Lower Third propio · Evento ${serial}`,52,y+66);
      if (config.kind !== 3) {
        ctx.fillStyle = '#59ddb7'; ctx.fillRect(52,y+80,(w-40)*((elapsed%1800)/1800),2);
      }
    } else {
      const x = canvas.width / 2, y = canvas.height / 2;
      ctx.translate(x,y); ctx.scale(.92+.08*opacity,.92+.08*opacity);
      ctx.fillStyle = 'rgba(25,19,48,.94)'; ctx.fillRect(-210,-62,420,124);
      ctx.strokeStyle = '#c7a6ff'; ctx.lineWidth = 2; ctx.strokeRect(-210,-62,420,124);
      ctx.fillStyle = '#ffffff'; ctx.textAlign = 'center'; ctx.font = 'bold 26px sans-serif'; ctx.fillText('¡GRACIAS, COMUNIDAD!',0,-5);
      ctx.fillStyle = '#c7a6ff'; ctx.font = '18px sans-serif'; ctx.fillText(`Community Alert · ${serial}`,0,28);
      for (let n=0;n<20;n++) {
        const angle=n*Math.PI/10+elapsed/1200;
        ctx.fillStyle=n%2?'#59ddb7':'#c7a6ff';
        ctx.fillRect(Math.cos(angle)*(235+12*Math.sin(elapsed/220+n)),Math.sin(angle)*90,5,5);
      }
    }
    ctx.restore();
  }
  if (!ready) { ready=true; motiveFixturePhase(2); }
  if (active) raf=requestAnimationFrame(draw);
}
function redraw() { if (!raf) raf=requestAnimationFrame(draw); }
globalThis.motiveOwnedEvent=()=>{
  if(suspended || active || config.kind===3){motiveFixturePhase(12);return false;}
  serial++; started=performance.now(); active=true;
  motiveFixturePhase(7); motiveFixturePhase(8); redraw(); return true;
};
globalThis.motiveOwnedCancel=()=>{
  suspended=true; active=false; if(raf)cancelAnimationFrame(raf); raf=0;
  draw(performance.now()); motiveFixturePhase(10); return true;
};
globalThis.motiveOwnedResume=()=>{
  if(!suspended)return false;
  suspended=false; redraw(); motiveFixturePhase(11); return true;
};
addEventListener('resize',redraw);
motiveFixturePhase(1); redraw();
