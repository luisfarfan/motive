// Real MessageChannel plus unchanged runtime; no DOM/CEF execution claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {MessageChannel} from 'node:worker_threads';
import {createNativeBootstrap,installNativeBootstrap} from '../web/native-bootstrap.mjs';
import {createRuntime} from '../../../element-lab/web-elements/goal-celebration/runtime.mjs';
const contract=JSON.parse(readFileSync(new URL('../../../element-lab/web-elements/goal-celebration/web-element.json',import.meta.url)));
const parentURL='motive://i1-g3/host/index.html';
const config=()=>({identity:{instance:1,generation:3},contract,entry:'motive://i1-g3/widget/index.html'});
const message=(seq,body)=>({protocol:1,instance:1,generation:3,expires_ms:1000,message:{version:1,seq,...body}});
const wait=()=>new Promise(resolve=>setTimeout(resolve,15));
function fixture({pending=false}={}){
 let remote,runtime,loaded=null,postCount=0,received,release;
 const attributes=new Map(),observed=[];
 const frame={src:'',setAttribute:(k,v)=>attributes.set(k,v),addEventListener:(name,fn)=>{assert.equal(name,'load');loaded=fn;},removeEventListener:()=>{loaded=null;},contentWindow:{postMessage:(bootstrap,origin,ports)=>{
   postCount++;assert.equal(origin,'*');remote=ports[0];runtime=createRuntime(bootstrap.contract,{clock:()=>0,observe:value=>remote.postMessage(value)});
   runtime.element.on('goal.scored',value=>{received=value;if(pending)return new Promise(resolve=>{release=resolve;});});
   remote.onmessage=({data})=>remote.postMessage({kind:'receipt',...runtime.receive(data)});remote.start();remote.postMessage({kind:'ready',state:'ready'});
 }}};
 const bridge=createNativeBootstrap({frame,parentURL,postStatus:value=>observed.push(value),channelFactory:()=>new MessageChannel()});
 return {bridge,frame,attributes,observed,load:()=>loaded?.(),received:()=>received,finish:()=>release?.(),postCount:()=>postCount,close:()=>{bridge.revoke();remote?.close();}};
}
test('fixed bootstrap connects native admitted data to original MotiveElement runtime',async()=>{
 const f=fixture();try{
   assert.equal(f.bridge.initialize(config()),true);assert.equal(f.frame.src,config().entry);
   assert.equal(f.attributes.get('sandbox'),'allow-scripts');
   f.load();await wait();assert.equal(f.observed[0].kind,'renderer_ready');
   f.bridge.deliver(message(1,{kind:'event',name:'goal.scored',payload:{team:'Literal </script> text',home:3,away:1}}),0);await wait();
   assert.deepEqual(f.received(),{team:'Literal </script> text',home:3,away:1});
   assert.ok(f.observed.some(value=>value.kind==='visual_ack'&&value.accepted));
   assert.deepEqual(f.observed.filter(value=>value.kind==='visual_state').map(value=>value.state),['active','ready']);
   assert.equal(f.observed.find(value=>value.kind==='visual_state'&&value.state==='ready').sequence,1);
   assert.throws(()=>f.bridge.deliver(message(2,{kind:'start_recording'}),1),/UNAUTHORIZED_MESSAGE/);
   assert.ok(f.observed.filter(value=>value.kind!=='visual_ack').every(value=>value.native_terminal_outcome===false));
 }finally{f.close();}
});
test('fixed entry refuses other schemes, files, hosts, query strings, and extra config authority',()=>{
 for(const entry of ['https://example.invalid/widget/index.html','file:///tmp/index.html','motive://i2-g3/widget/index.html',config().entry+'?url=https://example.invalid']) {
   const f=fixture();try{assert.throws(()=>f.bridge.initialize({...config(),entry}),/NATIVE_CONFIG/);assert.equal(f.frame.src,'');}finally{f.close();}
 }
 const f=fixture();try{
   assert.throws(()=>f.bridge.initialize({...config(),confirmed:true}),/NATIVE_CONFIG/);
   assert.throws(()=>f.bridge.initialize({...config(),identity:{instance:2,generation:3}}),/NATIVE_IDENTITY/);
 }finally{f.close();}
});
test('initialize once, load once, revocation terminal, stale generation rejected',async()=>{
 const f=fixture();try{
   assert.throws(()=>f.bridge.deliver(message(1,{kind:'cancel'}),0),/NOT_INITIALIZED/);
   f.bridge.initialize(config());assert.throws(()=>f.bridge.initialize(config()),/INITIALIZE_ONCE/);
   f.load();f.load();await wait();assert.equal(f.postCount(),1);
   assert.throws(()=>f.bridge.deliver({...message(1,{kind:'cancel'}),generation:2},0),/STALE_GENERATION/);
   f.bridge.revoke();assert.equal(f.bridge.inspect().adapter.closed,true);assert.equal(f.bridge.inspect().revoked,true);
   assert.throws(()=>f.bridge.deliver(message(2,{kind:'resume'}),1),/NOT_INITIALIZED/);
 }finally{f.close();}
});
test('global bridge is immutable and module-ready contains no package-controlled data',()=>{
 const statuses=[],frame={addEventListener(){},removeEventListener(){}};
 const target={document:{getElementById:name=>{assert.equal(name,'widget');return frame;}},location:{href:parentURL},motiveNativePostStatus:value=>statuses.push(value)};
 const bridge=installNativeBootstrap(target);
 assert.deepEqual(statuses,[{kind:'bootstrap_loaded'}]);
 assert.equal(Object.isFrozen(target.MotiveNativeVisual),true);
 assert.equal(Object.getOwnPropertyDescriptor(target,'MotiveNativeVisual').writable,false);
 assert.equal(Object.getOwnPropertyDescriptor(target,'MotiveNativeVisual').configurable,false);
 bridge.revoke();
});

test('native boundary preserves cancel/resume/dispose and suppresses late completion',async()=>{
 const f=fixture({pending:true});try{
   f.bridge.initialize(config());f.load();await wait();
   f.bridge.deliver(message(1,{kind:'event',name:'goal.scored',payload:{team:'Club del Puerto',home:2,away:1}}),0);await wait();
   f.bridge.deliver(message(2,{kind:'cancel'}),1);await wait();f.finish();await wait();
   assert.equal(f.bridge.inspect().adapter.state,'cancelled');
   assert.equal(f.observed.filter(value=>value.kind==='visual_state'&&value.state==='ready').length,0);
   f.bridge.deliver(message(3,{kind:'resume'}),2);await wait();assert.equal(f.bridge.inspect().adapter.state,'ready');
   f.bridge.deliver(message(4,{kind:'dispose'}),3);await wait();assert.equal(f.bridge.inspect().adapter.closed,true);
   assert.throws(()=>f.bridge.deliver(message(5,{kind:'resume'}),4),/PORT_NOT_READY/);
 }finally{f.close();}
});
