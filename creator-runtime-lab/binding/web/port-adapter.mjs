// Trusted outer-document adapter. The MessagePort is a data channel, not owner
// authority or a process sandbox. Native admission must precede deliver().
const states = new Set(['ready','active','cancelled','error','disposed']);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value,keys) => object(value) && Object.keys(value).length === keys.length && keys.every(k=>Object.hasOwn(value,k));
const safe = value => Number.isSafeInteger(value) && value > 0;
function need(value,code) { if (!value) throw new Error(code); }
export function createPortAdapter({identity,contract,channelFactory=()=>new MessageChannel(),observe=()=>{}}) {
  need(exact(identity,['instance','generation']) && safe(identity.instance) && safe(identity.generation),'IDENTITY');
  need(contract.schema_version===1 && contract.kind==='web_element','CONTRACT_VERSION');
  const pinned = structuredClone(identity), manifest=structuredClone(contract);
  let port=null, epoch=0, lastSequence=0, closed=false, ready=false, pending=new Map();
  let activeSequence=null, state='starting', lastClock=0;
  function close() { closed=true;ready=false;epoch++;port?.close();port=null;pending.clear();activeSequence=null;state='disposed'; }
  function attach(target) {
    need(!closed && port===null,'ATTACH_ONCE');need(typeof target?.postMessage==='function','BOOTSTRAP_TARGET');
    const channel=channelFactory();port=channel.port1;const turn=++epoch;
    port.onmessage=({data:m})=>{
      if(closed||turn!==epoch)return;
      // Renderer diagnostics never forward strings, objects, private paths or commands.
      if(exact(m,['kind','state'])&&m.kind==='ready'&&m.state==='ready'&&!ready) {
        ready=true;state='ready';observe({kind:'renderer_ready',identity:{...pinned},native_terminal_outcome:false});
      } else if(exact(m,['kind','state'])&&m.kind==='lifecycle'&&states.has(m.state)&&ready) {
        const completed=m.state==='ready'&&state==='active'?activeSequence:null;
        state=m.state;
        if(m.state!=='active')activeSequence=null;
        observe({kind:'visual_state',state,sequence:completed,identity:{...pinned},native_terminal_outcome:false});
      } else if(m?.kind==='receipt'&&typeof m.ok==='boolean'&&safe(m.seq)&&pending.has(m.seq)
          &&states.has(m.state)&&(exact(m,['kind','ok','seq','state'])||(!m.ok&&exact(m,['kind','ok','seq','state','code'])&&typeof m.code==='string'&&m.code.length<=64))) {
        pending.delete(m.seq);
        observe({kind:'visual_ack',protocol:1,instance:pinned.instance,generation:pinned.generation,
          seq:m.seq,accepted:m.ok});
        if(m.state==='disposed')close();
      }
    };
    port.start();
    // Opaque iframe origin requires '*'; target is an exact WindowProxy retained
    // by the host. No global message listener accepts commands from the iframe.
    target.postMessage({type:'motive.bootstrap',version:1,contract:manifest},'*',[channel.port2]);
  }
  function deliver(envelope,nowMs) {
    need(!closed&&ready,'PORT_NOT_READY');
    need(Number.isSafeInteger(nowMs)&&nowMs>=lastClock,'CLOCK_REGRESSION');lastClock=nowMs;
    need(exact(envelope,['protocol','instance','generation','expires_ms','message']),'ENVELOPE_SCHEMA');
    need(envelope.protocol===1&&envelope.instance===pinned.instance&&envelope.generation===pinned.generation,'STALE_GENERATION');
    need(Number.isSafeInteger(envelope.expires_ms)&&envelope.expires_ms>=nowMs&&envelope.expires_ms-nowMs<=30000,'MESSAGE_DEADLINE');
    const message=structuredClone(envelope.message);
    need(object(message)&&message.version===1&&safe(message.seq)&&message.seq>lastSequence,'MESSAGE_SEQUENCE');
    lastSequence=message.seq;
    need(new TextEncoder().encode(JSON.stringify(message)).length<=manifest.limits.max_message_bytes,'MESSAGE_SIZE');
    need(['event','properties','cancel','resume','dispose'].includes(message.kind),'UNAUTHORIZED_MESSAGE');
    // No event backlog; bounded status bookkeeping. Cancellation has a reserve.
    if(['cancel','dispose'].includes(message.kind)){pending.clear();activeSequence=null;}
    need(pending.size<8,'PENDING_LIMIT');pending.set(message.seq,true);
    if(message.kind==='event')activeSequence=message.seq;
    port.postMessage(message);
  }
  return Object.freeze({attach,deliver,revoke:close,inspect:()=>({identity:{...pinned},state,ready,closed,pending:pending.size,lastSequence})});
}
