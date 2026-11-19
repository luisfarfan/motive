// Fixed trusted outer document for the compile-only CEF candidate. Payloads are
// data passed by CefV8Value invocation; no eval or payload-built JavaScript.
import {createPortAdapter} from './port-adapter.mjs';
const exact=(value,keys)=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k));
function need(value,code){if(!value)throw new Error(code);}
export function createNativeBootstrap({frame,parentURL,postStatus,channelFactory}) {
  need(frame&&typeof frame.addEventListener==='function'&&typeof frame.removeEventListener==='function','FRAME');
  need(typeof postStatus==='function','NATIVE_CALLBACK');
  const parent=new URL(parentURL);
  need(parent.protocol==='motive:'&&parent.pathname==='/host/index.html'&&!parent.search&&!parent.hash,'HOST_LOCATION');
  const expectedEntry=new URL('/widget/index.html',parent).href;
  let adapter=null,initialized=false,revoked=false,loaded=false;
  function onLoad(){
    if(revoked||loaded)return;
    loaded=true;
    adapter.attach(frame.contentWindow);
  }
  function initialize(config){
    need(!initialized&&!revoked,'INITIALIZE_ONCE');
    need(exact(config,['identity','contract','entry'])&&config.entry===expectedEntry,'NATIVE_CONFIG');
    need(new TextEncoder().encode(JSON.stringify(config)).length<=65536,'NATIVE_CONFIG_SIZE');
    need(exact(config.identity,['instance','generation'])&&Number.isSafeInteger(config.identity.instance)&&config.identity.instance>0
      &&Number.isSafeInteger(config.identity.generation)&&config.identity.generation>0
      &&parent.href===`motive://i${config.identity.instance}-g${config.identity.generation}/host/index.html`,'NATIVE_IDENTITY');
    // Authority remains outside the renderer. The native caller validated the
    // manifest/inventory and minted its offline owner approval before this call.
    adapter=createPortAdapter({identity:config.identity,contract:config.contract,channelFactory,observe:postStatus});
    initialized=true;
    frame.setAttribute('sandbox','allow-scripts');
    frame.setAttribute('allow',"camera 'none'; microphone 'none'; geolocation 'none'; clipboard-read 'none'; clipboard-write 'none'");
    frame.addEventListener('load',onLoad);
    frame.src=expectedEntry;
    return true;
  }
  function deliver(envelope,nowMs){
    need(initialized&&!revoked,'NOT_INITIALIZED');
    adapter.deliver(envelope,nowMs);
    return true;
  }
  function revoke(){
    if(revoked)return true;
    revoked=true;
    frame.removeEventListener('load',onLoad);
    adapter?.revoke();
    return true;
  }
  return Object.freeze({initialize,deliver,revoke,inspect:()=>({initialized,revoked,loaded,adapter:adapter?.inspect()??null})});
}

export function installNativeBootstrap(target){
  const nativePostStatus=target.motiveNativePostStatus;
  need(typeof nativePostStatus==='function','NATIVE_CALLBACK');
  const bridge=createNativeBootstrap({frame:target.document.getElementById('widget'),parentURL:target.location.href,
    postStatus:value=>nativePostStatus(value)});
  // Only the reviewed top-level native context receives motiveNativePostStatus.
  // Untrusted iframe code cannot gain native authority by calling this object.
  const publicBridge=Object.freeze({initialize:bridge.initialize,deliver:bridge.deliver,revoke:bridge.revoke});
  Object.defineProperty(target,'MotiveNativeVisual',{value:publicBridge,writable:false,configurable:false});
  nativePostStatus({kind:'bootstrap_loaded'});
  return bridge;
}
if(typeof window!=='undefined'&&typeof document!=='undefined')installNativeBootstrap(window);
