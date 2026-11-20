// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "diagnostic_policy.hpp"
#include "include/cef_render_process_handler.h"
#include <map>
#include <memory>
struct DiagnosticState {motive_bridge::Identity identity;bool live=true,context_installed=false;};
class MotiveDiagnosticRenderer final : public CefRenderProcessHandler {
 public:
  void OnBrowserCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefDictionaryValue>) override;
  void OnBrowserDestroyed(CefRefPtr<CefBrowser>) override;
  void OnContextCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  void OnContextReleased(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  bool OnProcessMessageReceived(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefProcessId,CefRefPtr<CefProcessMessage>) override;
 private:
  std::map<int,std::shared_ptr<DiagnosticState>> states_;
  IMPLEMENT_REFCOUNTING(MotiveDiagnosticRenderer);
};
