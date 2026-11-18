// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "include/cef_app.h"
#include "include/cef_scheme.h"
#ifdef MOTIVE_GOAL_BRIDGE
#include "renderer_bridge.hpp"
#endif
class SchemeApp : public CefApp {
 public:
#ifdef MOTIVE_EPHEMERAL_KEYCHAIN
  void OnBeforeCommandLineProcessing(const CefString& process_type,CefRefPtr<CefCommandLine> command_line) override {
    // Official Chromium test backend: this owned ephemeral fixture neither
    // needs nor claims real OS credential storage. No global/keychain mutation.
    if(process_type.empty())command_line->AppendSwitch("use-mock-keychain");
  }
#endif
#ifdef MOTIVE_GOAL_BRIDGE
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
#endif
  IMPLEMENT_REFCOUNTING(SchemeApp);
};
