// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "include/cef_app.h"
#include "include/cef_scheme.h"
#include <cstdlib>
#include <string>
#ifdef MOTIVE_GOAL_BRIDGE
#include "renderer_bridge.hpp"
#elif defined(MOTIVE_MULTI_BROWSER)
#include "multi_renderer.hpp"
#elif defined(MOTIVE_DIAGNOSTIC_MODE)
#include "diagnostic_renderer.hpp"
#endif
class SchemeApp : public CefApp {
 public:
#ifdef MOTIVE_EPHEMERAL_KEYCHAIN
  void OnBeforeCommandLineProcessing(const CefString& process_type,CefRefPtr<CefCommandLine> command_line) override {
    // Official Chromium test backend: this owned ephemeral fixture neither
    // needs nor claims real OS credential storage. No global/keychain mutation.
    if(process_type.empty())command_line->AppendSwitch("use-mock-keychain");
#ifdef MOTIVE_H22_NETWORK_LAB
    if(process_type.empty()) {
      // Owned laboratory routing only. This is NOT an OS security boundary or
      // production update policy. Keep CEF sandbox and TLS verification intact.
      command_line->AppendSwitch("disable-component-update");
      command_line->AppendSwitch("disable-quic");
      std::string features=command_line->GetSwitchValue("disable-features").ToString();
      if(!features.empty())features+=",";
      command_line->AppendSwitchWithValue("disable-features",features+"MediaRouter");
      command_line->AppendSwitchWithValue("proxy-server","http://127.0.0.1:18719");
      command_line->AppendSwitchWithValue("proxy-bypass-list","<-loopback>");
      // Chromium 150 MappedHostResolver recognizes ^NOTFOUND, not the older
      // ~NOTFOUND spelling. Reject the proxy itself too: even literal-IP
      // resolution otherwise runs the shared IPv6 reachability socket probe.
      command_line->AppendSwitchWithValue("host-resolver-rules","MAP * ^NOTFOUND");
      // main.mm replaces TMPDIR with the verified private fixture directory.
      const char* root=std::getenv("TMPDIR");
      if(root)command_line->AppendSwitchWithValue("log-net-log",std::string(root)+"/h22-netlog.json");
      command_line->AppendSwitchWithValue("net-log-capture-mode","Default");
      command_line->AppendSwitchWithValue("net-log-max-size-mb","8");
    }
#endif
  }
#endif
#if defined(MOTIVE_GOAL_BRIDGE) || defined(MOTIVE_MULTI_BROWSER) || defined(MOTIVE_DIAGNOSTIC_MODE)
  CefRefPtr<CefRenderProcessHandler> GetRenderProcessHandler() override {return renderer_;}
#endif
  void OnRegisterCustomSchemes(CefRawPtr<CefSchemeRegistrar> r) override {
    int options=CEF_SCHEME_OPTION_STANDARD | CEF_SCHEME_OPTION_SECURE;
#ifdef MOTIVE_GOAL_BRIDGE
    options|=CEF_SCHEME_OPTION_CORS_ENABLED | CEF_SCHEME_OPTION_FETCH_ENABLED;
#endif
    r->AddCustomScheme("motive",options);
  }
 private:
#ifdef MOTIVE_GOAL_BRIDGE
  CefRefPtr<MotiveRenderBridge> renderer_=new MotiveRenderBridge;
#elif defined(MOTIVE_MULTI_BROWSER)
  CefRefPtr<MotiveMultiRenderer> renderer_=new MotiveMultiRenderer;
#elif defined(MOTIVE_DIAGNOSTIC_MODE)
  CefRefPtr<MotiveDiagnosticRenderer> renderer_=new MotiveDiagnosticRenderer;
#endif
  IMPLEMENT_REFCOUNTING(SchemeApp);
};
