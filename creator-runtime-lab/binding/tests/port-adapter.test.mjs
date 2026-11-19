import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {MessageChannel} from 'node:worker_threads';
import {createPortAdapter} from '../web/port-adapter.mjs';
import {createRuntime} from '../../../element-lab/web-elements/goal-celebration/runtime.mjs';
const contract=JSON.parse(readFileSync(new URL('../../../element-lab/web-elements/goal-celebration/web-element.json',import.meta.url)));
const pause=()=>new Promise(r=>setTimeout(r,10));
const envelope=(seq,body,identity={instance:1,generation:1})=>({protocol:1,...identity,expires_ms:1000,message:{version:1,seq,...body}});
async function fixture(){
 let remote,runtime,resolveActive,observed=[];
 const adapter=createPortAdapter({identity:{instance:1,generation:1},contract,channelFactory:()=>new MessageChannel(),observe:o=>observed.push(o)});
 adapter.attach({postMessage:(bootstrap,origin,ports)=>{
  assert.equal(origin,'*');assert.equal(bootstrap.type,'motive.bootstrap');assert.equal(ports.length,1);remote=ports[0];
  runtime=createRuntime(bootstrap.contract,{clock:()=>0,observe:o=>remote.postMessage(o)});
  runtime.element.on('goal.scored',()=>new Promise(resolve=>{resolveActive=resolve;}));
  remote.onmessage=({data})=>remote.postMessage({kind:'receipt',...runtime.receive(data)});remote.start();remote.postMessage({kind:'ready',state:'ready'});
 }});await pause();
 return {adapter,runtime,observed,remote,finish:()=>resolveActive(),close:()=>{adapter.revoke();remote.close();}};
}
test('MessagePort bootstraps the unchanged MotiveElement runtime and preserves exact projection',async()=>{
 const f=await fixture();try{
  assert.equal(f.adapter.inspect().ready,true);
  f.adapter.deliver(envelope(1,{kind:'properties',properties:{testMode:false}}),0);await pause();
  assert.equal(f.runtime.element.getProperties().testMode,false);
  f.adapter.deliver(envelope(2,{kind:'event',name:'goal.scored',payload:{team:'Club del Puerto',home:2,away:1}}),1);await pause();
  assert.equal(f.runtime.element.getState(),'active');
  assert.deepEqual(f.observed.find(o=>o.kind==='visual_ack'&&o.seq===2),{kind:'visual_ack',protocol:1,instance:1,generation:1,seq:2,accepted:true});
  f.finish();await pause();
  assert.equal(f.observed.find(o=>o.kind==='visual_state'&&o.state==='ready').sequence,2);
 }finally{f.close();}
});
test('rejects old generation, replay, expired deadline, unsafe messages and clock regression',async()=>{
 const f=await fixture();try{
  assert.throws(()=>f.adapter.deliver(envelope(1,{kind:'cancel'},{instance:1,generation:2}),0),/STALE_GENERATION/);
  assert.throws(()=>f.adapter.deliver({...envelope(1,{kind:'cancel'}),expires_ms:0},1),/MESSAGE_DEADLINE/);
  f.adapter.deliver(envelope(2,{kind:'cancel'}),2);await pause();
  assert.throws(()=>f.adapter.deliver(envelope(2,{kind:'cancel'}),3),/MESSAGE_SEQUENCE/);
  assert.throws(()=>f.adapter.deliver(envelope(3,{kind:'start_recording'}),4),/UNAUTHORIZED_MESSAGE/);
  assert.throws(()=>f.adapter.deliver(envelope(4,{kind:'resume'}),3),/CLOCK_REGRESSION/);
 }finally{f.close();}
});
test('cancel revokes active completion, dispose closes port, old callbacks cannot resurrect it',async()=>{
 const f=await fixture();try{
  f.adapter.deliver(envelope(1,{kind:'event',name:'goal.scored',payload:{team:'T',home:2,away:1}}),0);await pause();
  f.adapter.deliver(envelope(2,{kind:'cancel'}),1);await pause();f.finish();await pause();
  assert.equal(f.runtime.element.getState(),'cancelled');
  assert.equal(f.observed.filter(o=>o.kind==='visual_state'&&o.state==='ready').length,0);
  f.adapter.deliver(envelope(3,{kind:'dispose'}),2);await pause();
  assert.equal(f.adapter.inspect().closed,true);
  assert.throws(()=>f.adapter.deliver(envelope(4,{kind:'resume'}),3),/PORT_NOT_READY/);
 }finally{f.close();}
});
test('renderer cannot return arbitrary diagnostics, commands, duplicate ACKs or an unknown sequence',async()=>{
 const f=await fixture();try{
  f.remote.postMessage({kind:'lifecycle',state:'error',secret:'not forwarded'});
  f.remote.postMessage({kind:'start_recording'});
  f.remote.postMessage({kind:'receipt',ok:true,seq:900,state:'ready'});
  await pause();assert.equal(f.observed.length,1);
  f.adapter.deliver(envelope(1,{kind:'cancel'}),0);await pause();
  const n=f.observed.length;f.remote.postMessage({kind:'receipt',ok:true,seq:1,state:'cancelled'});await pause();
  assert.equal(f.observed.length,n);
 }finally{f.close();}
});
test('bounded pending receipts keep cancel/dispose available',async()=>{
 const f=await fixture();try{
  for(let i=1;i<=8;i++)f.adapter.deliver(envelope(i,{kind:'properties',properties:{home:1}}),0);
  assert.throws(()=>f.adapter.deliver(envelope(9,{kind:'properties',properties:{home:1}}),0),/PENDING_LIMIT/);
  f.adapter.deliver(envelope(10,{kind:'cancel'}),0);await pause();
  assert.equal(f.runtime.element.getState(),'cancelled');
  assert.ok(f.adapter.inspect().pending<=1);
 }finally{f.close();}
});
