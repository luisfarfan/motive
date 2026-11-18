import {createRuntime} from './runtime.mjs';
const panel=document.querySelector('#goal'),plate=document.querySelector('.plate');
let runtime,port,props,controller,animations=[],timer=null;
const media=matchMedia('(prefers-reduced-motion: reduce)');
function clean(){animations.forEach(a=>a.cancel());animations=[];if(timer!==null)clearTimeout(timer);timer=null;controller?.abort();controller=null;}
function display(p){props=p;panel.dataset.test=String(p.testMode);panel.dataset.reduced=String(p.reducedMotion||media.matches);
 document.documentElement.style.setProperty('--accent',p.accent);document.documentElement.style.setProperty('--ink',p.background);
 document.querySelector('#title').textContent=p.title;document.querySelector('#team').textContent=p.team;
 document.querySelector('#home').textContent=String(p.home);document.querySelector('#away').textContent=String(p.away);
 document.querySelector('.test-label').hidden=!p.testMode;}
function animate(target,frames,duration,signal){if(signal.aborted)return Promise.resolve();const a=target.animate(frames,{duration,easing:'cubic-bezier(.2,.75,.2,1)',fill:'both'});animations.push(a);return a.finished.catch(()=>{});}
function hold(ms,signal){return new Promise(resolve=>{const done=()=>{if(timer!==null)clearTimeout(timer);timer=null;signal.removeEventListener('abort',done);resolve();};signal.addEventListener('abort',done,{once:true});timer=setTimeout(done,ms);if(signal.aborted)done();});}
async function goal(event,{signal}){
 clean();controller=new AbortController();const local=controller.signal;
 const abort=()=>{controller?.abort();animations.forEach(a=>a.cancel());};signal.addEventListener('abort',abort,{once:true});
 runtime.element.onCleanup(()=>{signal.removeEventListener('abort',abort);clean();});
 document.querySelector('#team').textContent=event.team;document.querySelector('#home').textContent=String(event.home);document.querySelector('#away').textContent=String(event.away);
 const reduced=props.reducedMotion||media.matches;panel.dataset.reduced=String(reduced);panel.dataset.phase='active';
 const entrance=reduced?[{opacity:0},{opacity:1}]:[{opacity:0,transform:'translateX(-48px) scale(.98)',clipPath:'inset(0 100% 0 0)'},{opacity:1,transform:'translateX(0) scale(1)',clipPath:'inset(0 0 0 0)'}];
 const entry=animate(plate,entrance,reduced?100:480,local);
 if(!reduced)document.querySelectorAll('.rails i').forEach((rail,i)=>animate(rail,[{transform:'translateY(110%) skewX(-12deg)'},{transform:'translateY(0) skewX(-12deg)'}],280+i*65,local));
 await entry;if(local.aborted)return;
 animate(document.querySelector('.progress'),[{transform:'scaleX(1)'},{transform:'scaleX(0)'}],props.holdMs,local);
 await hold(props.holdMs,local);if(local.aborted)return;
 await animate(plate,reduced?[{opacity:1},{opacity:0}]:[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(36px)'}],reduced?100:320,local);
 if(!local.aborted)panel.dataset.phase='ready';
}
window.addEventListener('message',function bootstrap(event){
 if(event.source!==parent||runtime||event.data?.type!=='motive.bootstrap'||event.data?.version!==1||event.ports.length!==1)return;
 port=event.ports[0];runtime=createRuntime(event.data.contract,{observe:value=>port.postMessage(value)});
 Object.defineProperty(window,'MotiveElement',{value:runtime.element,writable:false});
 display(runtime.element.getProperties());runtime.element.onPropertiesChanged(display);runtime.element.on('goal.scored',goal);
 runtime.element.onLifecycle(state=>{if(state!=='active'){clean();panel.dataset.phase=state;}if(state==='disposed'){media.removeEventListener('change',reducedChanged);window.removeEventListener('error',onError);window.removeEventListener('unhandledrejection',onError);}});
 function reducedChanged(){display(props);}function onError(){runtime.element.reportError();}
 media.addEventListener('change',reducedChanged);window.addEventListener('error',onError);window.addEventListener('unhandledrejection',onError);
 port.onmessage=message=>{const receipt=runtime.receive(message.data);port.postMessage({kind:'receipt',...receipt});if(receipt.state==='disposed')port.close();};port.start();
 port.postMessage({kind:'ready',state:'ready'});
 window.removeEventListener('message',bootstrap);
});
