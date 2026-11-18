// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "include/cef_app.h"
#include "include/cef_scheme.h"
class SchemeApp : public CefApp {
 public:
  void OnRegisterCustomSchemes(CefRawPtr<CefSchemeRegistrar> r) override {
    r->AddCustomScheme("motive", CEF_SCHEME_OPTION_STANDARD | CEF_SCHEME_OPTION_SECURE);
  }
 private:
  IMPLEMENT_REFCOUNTING(SchemeApp);
};
