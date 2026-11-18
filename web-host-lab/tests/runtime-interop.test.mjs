import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRuntime} from '../../element-lab/web-elements/goal-celebration/runtime.mjs';
const manifest=JSON.parse(readFileSync(new URL('../../element-lab/web-elements/goal-celebration/web-element.json',import.meta.url)));
const message=JSON.parse(readFileSync(new URL('../evidence/K-goal-message.json',import.meta.url)));
test('Rust-projected Show Control fixture is admitted unchanged by existing JS runtime',async()=>{
 let observed;
 const runtime=createRuntime(manifest,{clock:()=>0});
 runtime.element.on('goal.scored',payload=>{observed=payload;});
 assert.equal(runtime.receive(message).ok,true);
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(observed,{team:'Club del Puerto',home:2,away:1});
 assert.equal(runtime.inspect().state,'ready');
 assert.equal(runtime.receive(message).code,'MESSAGE_SEQUENCE');
});
test('Existing runtime cancel/dispose remain visual-only',()=>{
 const runtime=createRuntime(manifest,{clock:()=>0});
 assert.equal(runtime.receive({version:1,seq:1,kind:'start_recording'}).ok,false);
 assert.equal(runtime.receive({version:1,seq:2,kind:'cancel'}).state,'cancelled');
 assert.equal(runtime.receive({version:1,seq:3,kind:'resume'}).state,'ready');
 assert.equal(runtime.receive({version:1,seq:4,kind:'dispose'}).state,'disposed');
 assert.equal(runtime.receive({version:1,seq:5,kind:'resume'}).ok,false);
});
