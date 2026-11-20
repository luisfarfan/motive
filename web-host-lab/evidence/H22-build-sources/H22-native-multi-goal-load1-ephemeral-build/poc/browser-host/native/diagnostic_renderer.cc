// SPDX-License-Identifier: GPL-3.0-or-later
#include "diagnostic_renderer.hpp"
#include "include/cef_browser.h"
#include "include/cef_frame.h"
#include "include/cef_v8.h"
#include <cmath>
#include <unistd.h>
namespace {
class PhaseHandler final : public CefV8Handler {
 public:
  explicit PhaseHandler(std::shared_ptr<DiagnosticState> state):state_(std::move(state)){}
  bool Execute(const CefString& name,CefRefPtr<CefV8Value>,const CefV8ValueList& args,CefRefPtr<CefV8Value>& result,CefString&) override{
    result=CefV8Value::CreateBool(false);auto context=CefV8Context::GetCurrentContext();
    if(!context||!state_->live||name!="motiveFixturePhase"||args.size()!=1||!args[0]->IsInt())return true;
    const int phase=args[0]->GetIntValue();auto browser=context->GetBrowser();auto frame=context->GetFrame();
    if(!browser||!frame||!frame->IsMain()||browser->GetIdentifier()!=state_->identity.browser||frame->GetURL()!=state_->identity.entry||!motive_diagnostic::PhaseAllowed(MOTIVE_DIAGNOSTIC_MODE,phase))return true;
    auto message=CefProcessMessage::Create(motive_diagnostic::PhaseMessage);message->GetArgumentList()->SetInt(0,phase);
    frame->SendProcessMessage(PID_BROWSER,message);result=CefV8Value::CreateBool(true);return true;
  }
 private:std::shared_ptr<DiagnosticState> state_;IMPLEMENT_REFCOUNTING(PhaseHandler);
};
}
void MotiveDiagnosticRenderer::OnBrowserCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefDictionaryValue> extra){
  if(!extra||extra->GetSize()!=3||extra->GetType("generation")!=VTYPE_DOUBLE||extra->GetType("entry")!=VTYPE_STRING||extra->GetType("mode")!=VTYPE_INT||extra->GetInt("mode")!=MOTIVE_DIAGNOSTIC_MODE)return;
  const double generation=extra->GetDouble("generation");if(!std::isfinite(generation)||generation<1||generation>double(motive_bridge::SafeInteger)||std::floor(generation)!=generation)return;
  const std::string entry="motive://i1-g"+std::to_string(uint64_t(generation))+"/index.html";if(extra->GetString("entry")!=entry)return;
  auto prior=states_.find(browser->GetIdentifier());if(prior!=states_.end())prior->second->live=false;
  auto state=std::make_shared<DiagnosticState>();state->identity={1,uint64_t(generation),browser->GetIdentifier(),entry};states_[browser->GetIdentifier()]=std::move(state);
}
void MotiveDiagnosticRenderer::OnBrowserDestroyed(CefRefPtr<CefBrowser> browser){auto found=states_.find(browser->GetIdentifier());if(found!=states_.end()){found->second->live=false;states_.erase(found);}}
void MotiveDiagnosticRenderer::OnContextCreated(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context> context){
  auto found=states_.find(browser->GetIdentifier());if(found==states_.end()||!found->second->live||!frame->IsMain()||frame->GetURL()!=found->second->identity.entry)return;
  found->second->context_installed=true;
  context->GetGlobal()->SetValue("motiveFixturePhase",CefV8Value::CreateFunction("motiveFixturePhase",new PhaseHandler(found->second)),static_cast<CefV8Value::PropertyAttribute>(V8_PROPERTY_ATTRIBUTE_READONLY|V8_PROPERTY_ATTRIBUTE_DONTDELETE));
}
void MotiveDiagnosticRenderer::OnContextReleased(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefRefPtr<CefV8Context>){auto found=states_.find(browser->GetIdentifier());if(found!=states_.end()&&found->second->context_installed&&frame->IsMain())found->second->live=false;}
bool MotiveDiagnosticRenderer::OnProcessMessageReceived(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefProcessId source,CefRefPtr<CefProcessMessage> message){
  auto found=states_.find(browser->GetIdentifier());if(found==states_.end()||!found->second->live||!frame||message->GetName()!=motive_diagnostic::ExitMessage)return false;
  const auto& id=found->second->identity;
  if(!motive_diagnostic::ExitAllowed(MOTIVE_DIAGNOSTIC_MODE,source==PID_BROWSER,frame->IsMain(),id.browser==browser->GetIdentifier()&&frame->GetURL()==id.entry,message->GetArgumentList()->GetSize()))return false;
  // Controlled failure of this exact renderer, not a memory-fault simulation.
  // _exit avoids crash dialogs and does not address any PID or process name.
  _exit(86);
}
