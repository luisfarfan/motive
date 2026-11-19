// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "bridge_policy.hpp"
#include "include/cef_render_process_handler.h"
#include <map>
#include <memory>
struct RendererState {
 motive_bridge::Identity identity;
 bool live=true,initialized=false,context_installed=false;
 uint64_t last_sequence=0,clock_origin_ms=0;
};
class MotiveRenderBridge final : public CefRenderProcessHandler {
 public:
  void OnBrowserCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefDictionaryValue>) override;
  void OnBrowserDestroyed(CefRefPtr<CefBrowser>) override;
  void OnContextCreated(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  void OnContextReleased(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefV8Context>) override;
  bool OnProcessMessageReceived(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefProcessId,CefRefPtr<CefProcessMessage>) override;
 private:
  std::map<int,std::shared_ptr<RendererState>> states_;
  IMPLEMENT_REFCOUNTING(MotiveRenderBridge);
};
