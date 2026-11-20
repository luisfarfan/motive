// SPDX-License-Identifier: GPL-3.0-or-later
#include "multi_renderer.hpp"
#include "include/cef_browser.h"
#include "include/cef_frame.h"
#include "include/cef_v8.h"
#include <cmath>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
namespace {
class Phase final : public CefV8Handler {
 public:
  explicit Phase(std::shared_ptr<MultiRendererState> s):s_(std::move(s)){}
  bool Execute(const CefString& name,CefRefPtr<CefV8Value>,const CefV8ValueList& args,CefRefPtr<CefV8Value>& result,CefString&) override {
    result=CefV8Value::CreateBool(false);auto c=CefV8Context::GetCurrentContext();
    if(!c||!s_->live||name!="motiveFixturePhase"||args.size()!=1||!args[0]->IsInt())return true;
    const int phase=args[0]->GetIntValue();if(phase!=1&&phase!=2&&phase!=5&&phase!=6&&phase!=7&&!(phase>=20&&phase<=29&&!s_->decoy.empty()))return true;
    auto b=c->GetBrowser();auto f=c->GetFrame();if(!b||!f||!f->IsMain()||b->GetIdentifier()!=s_->identity.browser||f->GetURL()!=s_->identity.entry)return true;
    auto m=CefProcessMessage::Create("motive.h19.phase");m->GetArgumentList()->SetInt(0,phase);f->SendProcessMessage(PID_BROWSER,m);result=CefV8Value::CreateBool(true);return true;
  }
 private:std::shared_ptr<MultiRendererState> s_;IMPLEMENT_REFCOUNTING(Phase);
};
}
void MotiveMultiRenderer::OnBrowserCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefDictionaryValue> extra){
  if(!extra||(extra->GetSize()!=6&&extra->GetSize()!=7)||extra->GetType("instance")!=VTYPE_DOUBLE||extra->GetType("generation")!=VTYPE_DOUBLE||extra->GetType("entry")!=VTYPE_STRING||extra->GetType("animated")!=VTYPE_BOOL||extra->GetType("allow_crash")!=VTYPE_BOOL||extra->GetType("slow")!=VTYPE_BOOL)return;
  const double i=extra->GetDouble("instance"),g=extra->GetDouble("generation");
  if(!std::isfinite(i)||!std::isfinite(g)||i<1||i>5||std::floor(i)!=i||g<1||g>double(motive_bridge::SafeInteger)||std::floor(g)!=g)return;
  const std::string entry="motive://i"+std::to_string(uint64_t(i))+"-g"+std::to_string(uint64_t(g))+"/index.html";if(extra->GetString("entry")!=entry)return;
  auto s=std::make_shared<MultiRendererState>();s->identity={uint64_t(i),uint64_t(g),browser->GetIdentifier(),entry};s->animated=extra->GetBool("animated");s->allow_crash=extra->GetBool("allow_crash");s->slow=extra->GetBool("slow");
  if(extra->GetSize()==7){if(extra->GetType("decoy_path")!=VTYPE_STRING)return;s->decoy=extra->GetString("decoy_path");if(s->decoy.size()>4096||!s->decoy.ends_with("/sandbox-decoy"))return;}
  states_[browser->GetIdentifier()]=std::move(s);
}
void MotiveMultiRenderer::OnBrowserDestroyed(CefRefPtr<CefBrowser> browser){auto i=states_.find(browser->GetIdentifier());if(i!=states_.end()){i->second->live=false;states_.erase(i);}}
void MotiveMultiRenderer::OnContextCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context> context){
  auto it=states_.find(browser->GetIdentifier());if(it==states_.end()||!it->second->live||!frame->IsMain()||frame->GetURL()!=it->second->identity.entry)return;
  auto s=it->second;auto flags=static_cast<CefV8Value::PropertyAttribute>(V8_PROPERTY_ATTRIBUTE_READONLY|V8_PROPERTY_ATTRIBUTE_DONTDELETE);
  auto config=CefV8Value::CreateObject(nullptr,nullptr);config->SetValue("instance",CefV8Value::CreateInt(int(s->identity.instance)),flags);config->SetValue("animated",CefV8Value::CreateBool(s->animated),flags);config->SetValue("slow",CefV8Value::CreateBool(s->slow),flags);
  config->SetValue("security",CefV8Value::CreateBool(!s->decoy.empty()),flags);
  context->GetGlobal()->SetValue("MotiveOwnedFixture",config,flags);
  context->GetGlobal()->SetValue("motiveFixturePhase",CefV8Value::CreateFunction("motiveFixturePhase",new Phase(s)),flags);
  auto identity=CefProcessMessage::Create("motive.h19.renderer_identity");identity->GetArgumentList()->SetInt(0,getpid());frame->SendProcessMessage(PID_BROWSER,identity);
  if(!s->decoy.empty()){
    errno=0;const int fd=open(s->decoy.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);const int error=fd<0?errno:0;if(fd>=0)close(fd);
    auto result=CefProcessMessage::Create("motive.h19.decoy_result");result->GetArgumentList()->SetBool(0,fd>=0);result->GetArgumentList()->SetInt(1,error);result->GetArgumentList()->SetInt(2,getpid());frame->SendProcessMessage(PID_BROWSER,result);
  }
}
void MotiveMultiRenderer::OnContextReleased(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context>){auto i=states_.find(browser->GetIdentifier());if(i!=states_.end()&&frame->IsMain())i->second->live=false;}
bool MotiveMultiRenderer::OnProcessMessageReceived(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefProcessId source,CefRefPtr<CefProcessMessage> message){
  auto i=states_.find(browser->GetIdentifier());if(i==states_.end()||!i->second->live||!frame||!frame->IsMain()||source!=PID_BROWSER||frame->GetURL()!=i->second->identity.entry||message->GetArgumentList()->GetSize()!=0)return false;
  if(message->GetName()=="motive.h19.exit"&&i->second->allow_crash)_exit(86);
  if(message->GetName()=="motive.h19.event"){
    auto c=frame->GetV8Context();if(!c||!c->Enter())return false;auto fn=c->GetGlobal()->GetValue("motiveOwnedEvent");bool ok=false;
    if(fn&&fn->IsFunction()){auto result=fn->ExecuteFunction(nullptr,{});ok=result&&result->IsBool()&&result->GetBoolValue();}c->Exit();return ok;
  }
  return false;
}
