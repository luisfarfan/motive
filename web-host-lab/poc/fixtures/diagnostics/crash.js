'use strict';
const canvas=document.querySelector('#surface'),ctx=canvas.getContext('2d');
let counter=0,ready=false;
const phase=globalThis.motiveFixturePhase;
function paint(){
  if(canvas.width!==innerWidth||canvas.height!==innerHeight){canvas.width=innerWidth;canvas.height=innerHeight;}
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle='rgba(255,0,0,0.5)';ctx.fillRect(32,32,64,64);
  ctx.fillStyle='#ffffff';ctx.font='24px monospace';ctx.fillText(`H16 ${++counter}`,130,65);
  // Eight visible binary bars identify the JS paint, independent of host index.
  for(let bit=0;bit<8;bit++){ctx.fillStyle=(counter&(1<<bit))?'#ffffff':'#333333';ctx.fillRect(130+bit*18,90,12,28);}
  ctx.fillStyle='#55ddaa';ctx.fillRect(32+(counter%120)*3,canvas.height-48,16,16);
  if(!ready){ready=true;phase(1);}
  requestAnimationFrame(paint);
}
requestAnimationFrame(paint);
