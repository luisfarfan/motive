'use strict';
// Fixed owned fixture. Instance identity is injected by the trusted native host.
const config=globalThis.MotiveOwnedFixture;
const canvas=document.querySelector('#surface'),ctx=canvas.getContext('2d');
let counter=0,eventCount=0,started=false;
function paint(){
  if(canvas.width!==innerWidth||canvas.height!==innerHeight){canvas.width=innerWidth;canvas.height=innerHeight;}
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle='rgba(255,0,0,0.5)';ctx.fillRect(32,32,64,64);
  ctx.fillStyle='#ffffff';ctx.font='24px monospace';ctx.fillText(`H19 ${config.instance} ${++counter} E${eventCount}`,130,65);
  // Per-instance exact opaque marker and eight counter bars are pixel oracles.
  ctx.fillStyle=`rgb(${config.instance*32},64,192)`;ctx.fillRect(100,32,16,16);
  for(let bit=0;bit<8;bit++){ctx.fillStyle=(counter&(1<<bit))?'#ffffff':'#333333';ctx.fillRect(130+bit*18,90,12,28);}
  ctx.fillStyle='#55ddaa';ctx.fillRect(32+(counter%120)*3,canvas.height-48,16,16);
  if(!started){started=true;motiveFixturePhase(2);}
  if(config.animated)requestAnimationFrame(paint);
}
globalThis.motiveOwnedEvent=()=>{++eventCount;motiveFixturePhase(7);if(!config.animated)paint();return true;};
addEventListener('resize',()=>{if(!config.animated)paint();});
motiveFixturePhase(1);requestAnimationFrame(paint);
if(config.slow)setTimeout(()=>{motiveFixturePhase(5);const start=performance.now();while(performance.now()-start<500){}motiveFixturePhase(6);},2000);

// Endpoints are fixed; launcher must own the loopback listener before this profile.
// These observations measure web policy only, not browser-process OS confinement.
if(config.security){
  fetch('http://127.0.0.1:18719/owned-probe').then(()=>motiveFixturePhase(21),()=>motiveFixturePhase(20));
  try{const ws=new WebSocket('ws://127.0.0.1:18719/owned-probe');ws.onopen=()=>{motiveFixturePhase(23);ws.close();};ws.onerror=()=>motiveFixturePhase(22);}catch{motiveFixturePhase(22);}
  const popup=open('about:blank');motiveFixturePhase(popup===null?24:25);if(popup)popup.close();
  try{document.cookie='MOTIVE_H19_DECOY=1; SameSite=Strict';motiveFixturePhase(document.cookie===''?26:27);}catch{motiveFixturePhase(26);}
  try{const worker=new Worker('fixture.js');worker.onerror=()=>motiveFixturePhase(28);worker.onmessage=()=>{motiveFixturePhase(29);worker.terminate();};}catch{motiveFixturePhase(28);}
}
