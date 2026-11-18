import test from 'node:test';
import assert from 'node:assert/strict';
import {createRuntime} from '../web-elements/runtime-prototype/runtime.mjs';
const contract={schema_version:1,kind:'web_element',properties:{team:{type:'string',default:'Puerto',max_length:60},accent:{type:'color',default:'#f2c782'},holdMs:{type:'integer',default:1000,minimum:100,maximum:10000}},events:{'goal.scored':{fields:{team:{type:'string',max_length:60},home:{type:'integer',minimum:0,maximum:99},away:{type:'integer',minimum:0,maximum:99}}}},limits:{max_message_bytes:4096,events_per_second:4}};
const event=(seq,payload={team:'Puerto',home:2,away:1})=>({version:1,seq,kind:'event',name:'goal.scored',payload});
test('typed events, immutable properties, lifecycle and cleanup',async()=>{
 let now=0;const rt=createRuntime(contract,{clock:()=>now});let seen,cleaned=0;rt.element.on('goal.scored',p=>{seen=p;rt.element.onCleanup(()=>cleaned++);});
 assert.equal(rt.receive(event(1)).ok,true);assert.equal(rt.inspect().state,'active');await new Promise(r=>setImmediate(r));
 assert.equal(seen.home,2);assert.ok(Object.isFrozen(seen));assert.equal(rt.inspect().state,'ready');assert.equal(cleaned,1);
 assert.equal(rt.receive({version:1,seq:2,kind:'properties',properties:{team:'Other',holdMs:999}}).ok,true);
 assert.equal(rt.element.getProperties().team,'Other');assert.ok(Object.isFrozen(rt.element.getProperties()));
});
test('unknown/malformed/large/unauthorized/replayed messages',()=>{
 const cases=[{...event(1),name:'unknown'},event(1,{team:'x',home:'2',away:1}),event(1,{team:'x'.repeat(8000),home:2,away:1}),
 {version:1,seq:1,kind:'production.start'}, {...event(1),secret:'forbidden'}];
 for(const m of cases){const rt=createRuntime(contract);rt.element.on('goal.scored',()=>{});assert.equal(rt.receive(m).ok,false);}
 const rt=createRuntime(contract);rt.element.on('goal.scored',()=>{});assert.equal(rt.receive(event(1)).ok,true);assert.equal(rt.receive(event(1)).code,'MESSAGE_SEQUENCE');
});
test('rate limit cannot block cancellation; cancellation aborts and disposal removes listeners',()=>{
 const rt=createRuntime(contract,{clock:()=>0});let signal,cleaned=0;rt.element.on('goal.scored',(_,context)=>{signal=context.signal;rt.element.onCleanup(()=>cleaned++);return new Promise(()=>{});});
 rt.receive(event(1));for(let seq=2;seq<=5;seq++)rt.receive({...event(seq),name:'unknown'});
 assert.equal(rt.receive(event(6)).code,'RATE_LIMIT');assert.equal(rt.receive({version:1,seq:7,kind:'cancel'}).ok,true);
 assert.ok(signal.aborted);assert.equal(cleaned,1);assert.equal(rt.inspect().cleanupHandlers,0);
 assert.equal(rt.receive({version:1,seq:8,kind:'resume'}).ok,true);
 assert.equal(rt.receive({version:1,seq:9,kind:'dispose'}).ok,true);assert.equal(rt.inspect().listeners,0);assert.equal(rt.receive(event(10)).code,'DISPOSED');
});
test('property patch is atomic and rejects extra keys/types',()=>{
 const rt=createRuntime(contract);for(const [seq,properties] of [[1,{team:'changed',holdMs:-1}],[2,{secret:'x'}],[3,{holdMs:true}],[4,{accent:'url(x)'}]]) assert.equal(rt.receive({version:1,seq,kind:'properties',properties}).ok,false);
 assert.equal(rt.element.getProperties().team,'Puerto');
});
test('runtime exception enters error; asynchronous failure cannot revive cancelled state',async()=>{
 const rt=createRuntime(contract);rt.element.on('goal.scored',()=>{throw Error('private details');});
 assert.equal(rt.receive(event(1)).code,'HANDLER_ERROR');assert.equal(rt.inspect().state,'error');
 const other=createRuntime(contract);let reject;other.element.on('goal.scored',()=>new Promise((_,r)=>{reject=r;}));other.receive(event(1));other.receive({version:1,seq:2,kind:'cancel'});reject(Error('late'));
 await new Promise(r=>setImmediate(r));assert.equal(other.inspect().state,'cancelled');
});
test('monotonic clock guard',()=>{let now=10;const rt=createRuntime(contract,{clock:()=>now});rt.receive({version:1,seq:1,kind:'properties',properties:{}});now=9;assert.equal(rt.receive(event(2)).code,'CLOCK_REGRESSION');});
