import {createPortAdapter} from './port-adapter.mjs';
const frame=document.querySelector('#widget'),$=id=>document.querySelector('#'+id);
let adapter=null,generation=0,queue=Promise.resolve(),observations=[],lastResult=null;
async function api(route,data){const r=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-Motive-Fixture':'h18'},body:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw Error(value.code??'FIXTURE_HTTP');return value;}
function log(value){observations.push(value);if(observations.length>100)observations.shift();const li=document.createElement('li');li.textContent=JSON.stringify(value);$('log').prepend(li);while($('log').children.length>12)$('log').lastChild.remove();}
function status(state){$('status').textContent=state;$('goal').disabled=state!=='ready';$('cancel').disabled=!['ready','active'].includes(state);$('resume').disabled=state!=='cancelled';$('dispose').disabled=['starting','disposed','error'].includes(state);}
function schedule(fn){queue=queue.then(fn).catch(e=>{status('error');log({code:e.message});});return queue;}
async function command(command,extra={}){const result=await api('/api/command',{command,...extra});lastResult=result;log({command,ok:result.ok,code:result.code??null,native_terminal_outcome:false});if(!result.ok)return result;$('summary').textContent=JSON.stringify(result.scope,null,2);if(result.dispatch)adapter.deliver(result.dispatch,result.now_ms);return result;}
async function restart(){adapter?.revoke();status('starting');const session=await api('/api/session',{});generation=session.generation;const expected=generation;
 adapter=createPortAdapter({identity:session.identity,contract:session.contract,observe:o=>{
   if(expected!==generation)return;log(o);
   if(o.kind==='renderer_ready')schedule(async()=>{await command('ready');await command('properties');});
   if(o.kind==='visual_ack'&&$('status').textContent!=='disposed')schedule(async()=>{const result=await command('ack',{ack:o});if(o.seq===1&&result.ok)status('ready');});
   if(o.kind==='visual_state'){status(o.state);if(o.state==='ready'&&o.sequence!==null)schedule(()=>command('complete',{sequence:o.sequence}));}
 }});
 frame.onload=()=>{if(expected===generation)adapter.attach(frame.contentWindow);};frame.src='/widget/index.html?generation='+generation;
}
$('goal').addEventListener('click',()=>schedule(()=>command('goal')));$('cancel').addEventListener('click',()=>schedule(()=>command('cancel')));$('resume').addEventListener('click',()=>schedule(()=>command('resume')));$('dispose').addEventListener('click',()=>schedule(()=>command('dispose')));$('restart').addEventListener('click',()=>schedule(restart));
$('horizontal').addEventListener('click',()=>$('stage').classList.remove('vertical'));$('vertical').addEventListener('click',()=>$('stage').classList.add('vertical'));
document.addEventListener('visibilitychange',()=>{if(document.hidden&&adapter?.inspect().ready)schedule(()=>command('cancel'));});
window.fixtureTest=Object.freeze({inspect:()=>({generation,adapter:adapter?.inspect(),observations:[...observations],lastResult}),command:(name,data={})=>schedule(()=>command(name,data)),restart:()=>schedule(restart)});
await restart();
