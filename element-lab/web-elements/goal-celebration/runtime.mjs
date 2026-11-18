// Proposed MotiveElement API v1. Visual authoring only, not a process sandbox.
export class ElementError extends Error {
  constructor(code) { super(code); this.code = code; }
}
const need = (ok, code) => { if (!ok) throw new ElementError(code); };
const object = x => x !== null && typeof x === 'object' && !Array.isArray(x) && Object.getPrototypeOf(x) === Object.prototype;
const exact = (value, keys) => need(object(value) && Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value, k)), 'MESSAGE_SCHEMA');
const clone = x => structuredClone(x);
function freeze(x) { if (x && typeof x === 'object') { Object.values(x).forEach(freeze); Object.freeze(x); } return x; }
export function validateValue(value, spec) {
  if (spec.type === 'string' || spec.type === 'color') {
    need(typeof value === 'string' && value.length <= (spec.max_length ?? 160), 'PROPERTY_TYPE');
    if (spec.type === 'color') need(/^#[0-9a-fA-F]{6}$/.test(value), 'PROPERTY_COLOR');
    need(!/[\u0000-\u001f]/.test(value), 'PROPERTY_CONTROL');
  } else if (spec.type === 'boolean') need(typeof value === 'boolean', 'PROPERTY_TYPE');
  else {
    need(typeof value === 'number' && Number.isFinite(value), 'PROPERTY_TYPE');
    if (spec.type === 'integer') need(Number.isInteger(value), 'PROPERTY_TYPE');
    need(value >= spec.minimum && value <= spec.maximum, 'PROPERTY_RANGE');
  }
  if (spec.options) need(spec.options.includes(value), 'PROPERTY_OPTION');
}
export function createRuntime(contract, {clock = () => performance.now(), observe = () => {}} = {}) {
  need(contract.schema_version === 1 && contract.kind === 'web_element', 'CONTRACT_VERSION');
  const propertySpecs = clone(contract.properties), eventSpecs = clone(contract.events), limits = clone(contract.limits);
  need(limits.max_message_bytes > 0 && limits.max_message_bytes <= 16384 && limits.events_per_second > 0 && limits.events_per_second <= 60, 'CONTRACT_LIMIT');
  let properties = Object.fromEntries(Object.entries(propertySpecs).map(([k,s]) => { validateValue(s.default,s); return [k,clone(s.default)]; }));
  let state = 'ready', lastSeq = 0, lastClock = -Infinity, attempts = [], generation = 0, controller = null;
  const events = new Map(), changes = new Set(), cleanups = new Set(), lifecycle = new Set();
  const metrics = {accepted:0,rejected:0,cleanups:0,errors:0};
  function notifyState(next) { state = next; for (const fn of lifecycle) { try { fn(next); } catch { metrics.errors++; } } observe({kind:'lifecycle',state}); }
  function cleanup() { controller?.abort(); controller=null; generation++; for (const fn of [...cleanups]) { try { fn(); } catch { metrics.errors++; } metrics.cleanups++; } cleanups.clear(); }
  function fail() { cleanup(); metrics.errors++; notifyState('error'); }
  function register(set, fn) { need(state !== 'disposed', 'DISPOSED'); need(typeof fn === 'function' && set.size < 32, 'LISTENER_LIMIT'); set.add(fn); return () => set.delete(fn); }
  const element = Object.freeze({
    on(name, handler) { need(Object.hasOwn(eventSpecs,name), 'UNKNOWN_EVENT'); if (!events.has(name)) events.set(name,new Set()); return register(events.get(name),handler); },
    getProperties() { return freeze(clone(properties)); },
    onPropertiesChanged(handler) { return register(changes,handler); },
    onLifecycle(handler) { return register(lifecycle,handler); },
    onCleanup(handler) { return register(cleanups,handler); },
    getState() { return state; },
    reportError() { if (state !== 'disposed') fail(); }
  });
  function receive(message) {
    try {
      need(state !== 'disposed','DISPOSED');
      const now = clock(); need(Number.isFinite(now) && now >= lastClock,'CLOCK_REGRESSION'); lastClock=now;
      const serialized = JSON.stringify(message);
      need(typeof serialized === 'string' && new TextEncoder().encode(serialized).length <= limits.max_message_bytes,'MESSAGE_SIZE');
      need(object(message) && message.version === 1 && Number.isSafeInteger(message.seq) && message.seq > lastSeq,'MESSAGE_SEQUENCE');
      // Consume the sequence even for rejected messages: no replay or unbounded ID cache.
      lastSeq=message.seq;
      attempts=attempts.filter(t => now-t < 1000);
      // Control messages always remain usable to cancel an overloaded element.
      if (message.kind === 'event' || message.kind === 'properties') {
        need(attempts.length < limits.events_per_second,'RATE_LIMIT'); attempts.push(now);
      }
      if (message.kind === 'event') {
        exact(message,['version','seq','kind','name','payload']);
        need(state === 'ready','NOT_READY');need(Object.hasOwn(eventSpecs,message.name),'UNKNOWN_EVENT');
        const fields=eventSpecs[message.name].fields;exact(message.payload,Object.keys(fields));
        for (const [key,spec] of Object.entries(fields)) validateValue(message.payload[key],spec);
        need(events.has(message.name) && events.get(message.name).size > 0,'NO_HANDLER');
        controller=new AbortController();const signal=controller.signal, turn=++generation;
        const payload=freeze(clone(message.payload));notifyState('active');
        let results;
        try { results=[...events.get(message.name)].map(fn => fn(payload,{signal})); }
        catch { fail(); throw new ElementError('HANDLER_ERROR'); }
        Promise.all(results).then(() => { if (generation===turn && state==='active') { cleanup(); notifyState('ready'); } }, () => { if (generation===turn && state !== 'disposed') fail(); });
      } else if (message.kind === 'properties') {
        exact(message,['version','seq','kind','properties']);need(object(message.properties),'PROPERTY_SCHEMA');
        const next=clone(properties);
        for (const [key,value] of Object.entries(message.properties)) { need(Object.hasOwn(propertySpecs,key),'UNKNOWN_PROPERTY');validateValue(value,propertySpecs[key]);next[key]=clone(value); }
        // Validate the whole patch before applying any part.
        properties=next;
        try { for (const fn of changes) fn(freeze(clone(properties))); } catch { fail(); throw new ElementError('HANDLER_ERROR'); }
      } else if (['cancel','resume','dispose'].includes(message.kind)) {
        exact(message,['version','seq','kind']);
        if (message.kind==='resume') { need(state==='cancelled' || state==='error','LIFECYCLE');cleanup();notifyState('ready'); }
        else { cleanup();notifyState(message.kind==='dispose'?'disposed':'cancelled');if (state==='disposed') { events.clear();changes.clear();lifecycle.clear(); } }
      } else throw new ElementError('UNAUTHORIZED_MESSAGE');
      metrics.accepted++;return {ok:true,seq:message.seq,state};
    } catch (e) { metrics.rejected++;return {ok:false,seq:Number.isSafeInteger(message?.seq)?message.seq:0,state,code:e.code ?? 'MESSAGE_INVALID'}; }
  }
  return Object.freeze({element,receive,inspect:() => ({state,lastSeq,...metrics,listeners:[...events.values()].reduce((n,s)=>n+s.size,0)+changes.size+lifecycle.size,cleanupHandlers:cleanups.size})});
}
