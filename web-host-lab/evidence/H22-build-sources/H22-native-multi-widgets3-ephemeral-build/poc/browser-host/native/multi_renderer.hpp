// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "bridge_policy.hpp"
#include "include/cef_render_process_handler.h"
#include <map>
#include <memory>
struct MultiRendererState {
  motive_bridge::Identity identity;
  bool live=true,animated=false,allow_crash=false,slow=false;
  int kind=0;
  std::string decoy;
};
class MotiveMultiRenderer final : public CefRenderProcessHandler {
 public:
  void OnBrowserCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefDictionaryValue>) override;
  void OnBrowserDestroyed(CefRefPtr<CefBrowser>) override;
  void OnContextCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  void OnContextReleased(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  bool OnProcessMessageReceived(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefProcessId,CefRefPtr<CefProcessMessage>) override;
 private:
  std::map<int,std::shared_ptr<MultiRendererState>> states_;
  IMPLEMENT_REFCOUNTING(MotiveMultiRenderer);
};
