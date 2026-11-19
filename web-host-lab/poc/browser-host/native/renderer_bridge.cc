// SPDX-License-Identifier: GPL-3.0-or-later
// Compiled candidate only. No ExecuteJavaScript, eval, raw creator commands or
// retained V8 context. CEF supplies process/frame provenance; JSON cannot grant it.
#include "renderer_bridge.hpp"
#include "include/cef_browser.h"
#include "include/cef_frame.h"
#include "include/cef_parser.h"
#include "include/cef_v8.h"
#include <cmath>
#include <chrono>
#include <set>
#include <unistd.h>

namespace {
bool Keys(CefRefPtr<CefV8Value> object,std::initializer_list<const char*> expected){
 if(!object||!object->IsObject()||object->IsArray())return false;
 std::vector<CefString> keys;if(!object->GetKeys(keys)||keys.size()!=expected.size())return false;
 std::set<std::string> actual;for(const auto& key:keys){if(key.length()>32)return false;actual.insert(key.ToString());}
 for(const char* key:expected)if(!actual.contains(key))return false;return true;
}
bool Number(CefRefPtr<CefV8Value> value,uint64_t& output,bool zero=false){
 if(!value||(!value->IsDouble()&&!value->IsInt()&&!value->IsUInt()))return false;const double n=value->IsInt()?double(value->GetIntValue()):value->IsUInt()?double(value->GetUIntValue()):value->GetDoubleValue();
 if(!std::isfinite(n)||n<(zero?0:1)||n>double(motive_bridge::SafeInteger)||std::floor(n)!=n)return false;output=uint64_t(n);return true;
}
bool Identity(CefRefPtr<CefV8Value> value,const motive_bridge::Identity& id){
 uint64_t instance=0,generation=0;return Keys(value,{"instance","generation"})&&Number(value->GetValue("instance"),instance)&&Number(value->GetValue("generation"),generation)&&instance==id.instance&&generation==id.generation;
}
CefRefPtr<CefDictionaryValue> IdentityValue(const motive_bridge::Identity& id){auto d=CefDictionaryValue::Create();d->SetDouble("instance",double(id.instance));d->SetDouble("generation",double(id.generation));return d;}
bool False(CefRefPtr<CefV8Value> value){return value&&value->IsBool()&&!value->GetBoolValue();}
CefRefPtr<CefValue> Status(CefRefPtr<CefV8Value> input,const motive_bridge::Identity& id){
 if(!input||!input->IsObject())return nullptr;auto kind=input->GetValue("kind");if(!kind||!kind->IsString()||kind->GetStringValue().length()>32)return nullptr;
 const std::string name=kind->GetStringValue().ToString();auto d=CefDictionaryValue::Create();d->SetString("kind",name);
 if(name=="bootstrap_loaded") {if(!Keys(input,{"kind"}))return nullptr;}
 else if(name=="renderer_ready"){
  if(!Keys(input,{"kind","identity","native_terminal_outcome"})||!Identity(input->GetValue("identity"),id)||!False(input->GetValue("native_terminal_outcome")))return nullptr;
  d->SetDictionary("identity",IdentityValue(id));d->SetBool("native_terminal_outcome",false);
 }else if(name=="visual_ack"){
  uint64_t instance=0,generation=0,seq=0,protocol=0;auto accepted=input->GetValue("accepted");
  if(!Keys(input,{"kind","protocol","instance","generation","seq","accepted"})||!Number(input->GetValue("protocol"),protocol)||protocol!=1||!Number(input->GetValue("instance"),instance)||instance!=id.instance||!Number(input->GetValue("generation"),generation)||generation!=id.generation||!Number(input->GetValue("seq"),seq)||!accepted||!accepted->IsBool())return nullptr;
  d->SetInt("protocol",1);d->SetDouble("instance",double(instance));d->SetDouble("generation",double(generation));d->SetDouble("seq",double(seq));d->SetBool("accepted",accepted->GetBoolValue());
 }else if(name=="visual_state"){
  if(!Keys(input,{"kind","state","sequence","identity","native_terminal_outcome"})||!Identity(input->GetValue("identity"),id)||!False(input->GetValue("native_terminal_outcome")))return nullptr;
  auto state=input->GetValue("state"),seq=input->GetValue("sequence");if(!state||!state->IsString()||state->GetStringValue().length()>16||!seq)return nullptr;
  const auto s=state->GetStringValue().ToString();if(s!="ready"&&s!="active"&&s!="cancelled"&&s!="error"&&s!="disposed")return nullptr;
  uint64_t n=0;if(seq->IsNull())d->SetNull("sequence");else if(Number(seq,n))d->SetDouble("sequence",double(n));else return nullptr;
  d->SetString("state",s);d->SetDictionary("identity",IdentityValue(id));d->SetBool("native_terminal_outcome",false);
 }else return nullptr;
 auto value=CefValue::Create();value->SetDictionary(d);return value;
}
class StatusHandler final : public CefV8Handler {
 public:
  explicit StatusHandler(std::shared_ptr<RendererState> state):state_(std::move(state)){}
  bool Execute(const CefString& name,CefRefPtr<CefV8Value>,const CefV8ValueList& arguments,CefRefPtr<CefV8Value>& retval,CefString&) override{
   retval=CefV8Value::CreateBool(false);
   auto context=CefV8Context::GetCurrentContext();if(!context||!state_->live||name!="motiveNativePostStatus"||arguments.size()!=1)return true;
   auto browser=context->GetBrowser();auto frame=context->GetFrame();
   if(!browser||!frame||!frame->IsMain()||browser->GetIdentifier()!=state_->identity.browser||frame->GetURL()!=state_->identity.entry)return true;
   auto value=Status(arguments[0],state_->identity);if(!value)return true;
   const auto json=CefWriteJSON(value,JSON_WRITER_OMIT_DOUBLE_TYPE_PRESERVATION);if(json.empty()||json.length()>512)return true;
   auto message=CefProcessMessage::Create(motive_bridge::StatusMessage);message->GetArgumentList()->SetString(0,json);frame->SendProcessMessage(PID_BROWSER,message);retval=CefV8Value::CreateBool(true);return true;
  }
 private:std::shared_ptr<RendererState> state_;IMPLEMENT_REFCOUNTING(StatusHandler);
};
CefRefPtr<CefV8Value> ToV8(CefRefPtr<CefValue> value,size_t depth,size_t& count){
 if(!value||depth>16||++count>2048)return nullptr;
 switch(value->GetType()){
 case VTYPE_NULL:return CefV8Value::CreateNull();
 case VTYPE_BOOL:return CefV8Value::CreateBool(value->GetBool());
 case VTYPE_INT:return CefV8Value::CreateInt(value->GetInt());
 case VTYPE_DOUBLE:if(!std::isfinite(value->GetDouble()))return nullptr;return CefV8Value::CreateDouble(value->GetDouble());
 case VTYPE_STRING:if(value->GetString().length()>8192)return nullptr;return CefV8Value::CreateString(value->GetString());
 case VTYPE_LIST:{auto list=value->GetList();if(list->GetSize()>512)return nullptr;auto out=CefV8Value::CreateArray(int(list->GetSize()));for(size_t i=0;i<list->GetSize();++i){auto child=ToV8(list->GetValue(i),depth+1,count);if(!child||!out->SetValue(int(i),child))return nullptr;}return out;}
 case VTYPE_DICTIONARY:{auto dict=value->GetDictionary();CefDictionaryValue::KeyList keys;dict->GetKeys(keys);if(keys.size()>128)return nullptr;auto out=CefV8Value::CreateObject(nullptr,nullptr);for(const auto& key:keys){if(key.length()>128)return nullptr;auto child=ToV8(dict->GetValue(key),depth+1,count);if(!child||!out->SetValue(key,child,V8_PROPERTY_ATTRIBUTE_NONE))return nullptr;}return out;}
 default:return nullptr;
 }
}
bool JsonNumber(CefRefPtr<CefDictionaryValue> object,const char* key,double& out){
 const auto type=object->GetType(key);if(type==VTYPE_INT)out=object->GetInt(key);else if(type==VTYPE_DOUBLE)out=object->GetDouble(key);else return false;
 return std::isfinite(out)&&out>=0&&out<=double(motive_bridge::SafeInteger)&&std::floor(out)==out;
}
bool Invoke(CefRefPtr<CefFrame> frame,const char* method,CefRefPtr<CefValue> value,double now_ms=0){
 auto context=frame->GetV8Context();if(!context||!context->Enter())return false;
 auto global=context->GetGlobal();auto bridge=global->GetValue("MotiveNativeVisual");
 bool ok=false;
 if(bridge&&bridge->IsObject()){
  auto function=bridge->GetValue(method);size_t count=0;auto data=ToV8(value,0,count);
  if(function&&function->IsFunction()&&data){CefV8ValueList args{data};if(std::string(method)=="deliver")args.push_back(CefV8Value::CreateDouble(now_ms));auto result=function->ExecuteFunction(bridge,args);ok=result&&result->IsBool()&&result->GetBoolValue();}
 }
 context->Exit();return ok;
}
}
void MotiveRenderBridge::OnBrowserCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefDictionaryValue> extra){
 if(!extra||extra->GetSize()!=
#ifdef MOTIVE_MULTI_BROWSER
 5
#else
 4
#endif
 ||extra->GetType("instance")!=VTYPE_DOUBLE||extra->GetType("generation")!=VTYPE_DOUBLE||extra->GetType("entry")!=VTYPE_STRING||extra->GetType("clock_origin_ms")!=VTYPE_DOUBLE)return;
 const double i=extra->GetDouble("instance"),g=extra->GetDouble("generation"),origin=extra->GetDouble("clock_origin_ms");
 if(!std::isfinite(origin)||origin<1||origin>double(motive_bridge::SafeInteger)||std::floor(origin)!=origin)return;
 if(!std::isfinite(i)||!std::isfinite(g)||i<1||i>5||std::floor(i)!=i||g<1||g>double(motive_bridge::SafeInteger)||std::floor(g)!=g)return;
 const std::string expected="motive://i"+std::to_string(uint64_t(i))+"-g"+std::to_string(uint64_t(g))+"/host/index.html";
 if(extra->GetString("entry")!=expected)return;
 auto prior=states_.find(browser->GetIdentifier());if(prior!=states_.end())prior->second->live=false;
 auto state=std::make_shared<RendererState>();state->identity={uint64_t(i),uint64_t(g),browser->GetIdentifier(),expected};state->clock_origin_ms=uint64_t(origin);
#ifdef MOTIVE_MULTI_BROWSER
 if(extra->GetType("allow_crash")!=VTYPE_BOOL)return;state->allow_crash=extra->GetBool("allow_crash");
#endif
 states_[browser->GetIdentifier()]=std::move(state);
}
void MotiveRenderBridge::OnBrowserDestroyed(CefRefPtr<CefBrowser> browser){auto found=states_.find(browser->GetIdentifier());if(found!=states_.end()){found->second->live=false;states_.erase(found);}}
void MotiveRenderBridge::OnContextCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context> context){
 auto found=states_.find(browser->GetIdentifier());if(found==states_.end()||!found->second->live||!frame->IsMain()||frame->GetURL()!=found->second->identity.entry)return;
 found->second->context_installed=true;
#ifdef MOTIVE_MULTI_BROWSER
 auto identity=CefProcessMessage::Create("motive.h19.renderer_identity");identity->GetArgumentList()->SetInt(0,getpid());frame->SendProcessMessage(PID_BROWSER,identity);
#endif
 context->GetGlobal()->SetValue("motiveNativePostStatus",CefV8Value::CreateFunction("motiveNativePostStatus",new StatusHandler(found->second)),static_cast<CefV8Value::PropertyAttribute>(V8_PROPERTY_ATTRIBUTE_READONLY|V8_PROPERTY_ATTRIBUTE_DONTDELETE));
}
void MotiveRenderBridge::OnContextReleased(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context>){auto found=states_.find(browser->GetIdentifier());if(found!=states_.end()&&found->second->context_installed&&frame->IsMain())found->second->live=false;}
bool MotiveRenderBridge::OnProcessMessageReceived(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefProcessId source,CefRefPtr<CefProcessMessage> message){
 auto found=states_.find(browser->GetIdentifier());if(found==states_.end()||!found->second->live)return false;

#ifdef MOTIVE_MULTI_BROWSER
 if(message->GetName()=="motive.h19.exit"&&found->second->allow_crash&&frame&&frame->IsMain()&&source==PID_BROWSER&&frame->GetURL()==found->second->identity.entry&&message->GetArgumentList()->GetSize()==0)_exit(86);
#endif
 const auto name=message->GetName();const bool init=name==motive_bridge::InitializeMessage;if(!init&&name!=motive_bridge::DispatchMessage)return false;
 auto args=message->GetArgumentList();if(args->GetType(0)!=VTYPE_STRING)return false;const auto json=args->GetString(0);auto& state=*found->second;
 if(!motive_bridge::Boundary(state.identity,browser->GetIdentifier(),frame->IsMain(),source==PID_BROWSER,frame->GetURL().ToString(),args->GetSize(),init?1:2,json.length(),init?65536:16384))return false;
 auto value=CefParseJSON(json,JSON_PARSER_RFC);if(!value||value->GetType()!=VTYPE_DICTIONARY)return false;
 if(init){if(state.initialized)return false;state.initialized=Invoke(frame,"initialize",value);return state.initialized;}
 if(!state.initialized||args->GetType(1)!=VTYPE_DOUBLE)return false;
 const double sent=args->GetDouble(1);if(!std::isfinite(sent)||sent<0||sent>double(motive_bridge::SafeInteger)||std::floor(sent)!=sent)return false;
 // mach monotonic-backed steady clock is shared by these local processes.
 // Recheck on arrival; the browser's sent timestamp does not freeze expiry.
 const auto absolute=uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
 if(absolute<state.clock_origin_ms)return false;const auto now=absolute-state.clock_origin_ms;
 auto envelope=value->GetDictionary();double protocol=0,instance=0,generation=0,expires=0;
 if(envelope->GetSize()!=5||!JsonNumber(envelope,"protocol",protocol)||protocol!=1||!JsonNumber(envelope,"instance",instance)||instance!=double(state.identity.instance)||!JsonNumber(envelope,"generation",generation)||generation!=double(state.identity.generation)||!JsonNumber(envelope,"expires_ms",expires)||envelope->GetType("message")!=VTYPE_DICTIONARY)return false;
 auto visual=envelope->GetDictionary("message");double seq=0;
 if(!JsonNumber(visual,"seq",seq)||seq<=double(state.last_sequence)||!motive_bridge::Fresh(uint64_t(expires),uint64_t(sent),now))return false;
 state.last_sequence=uint64_t(seq);return Invoke(frame,"deliver",value,now);
}
