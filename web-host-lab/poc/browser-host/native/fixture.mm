// SPDX-License-Identifier: GPL-3.0-or-later
// AppKit boilerplate adapted from pinned CEF cefsimple_mac.mm (BSD). See NOTICE.md.
#import <AppKit/AppKit.h>
#include "scheme.hpp"
#include "fixture_assets.hpp"
#include "include/cef_application_mac.h"
#include "include/cef_browser.h"
#include "include/cef_client.h"
#include "include/cef_task.h"
#include "include/wrapper/cef_byte_read_handler.h"
#include "include/wrapper/cef_library_loader.h"
#include "include/wrapper/cef_stream_resource_handler.h"
#include <atomic>
#include <chrono>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <vector>

namespace h16 {
constexpr int Width=640, Height=360, Fps=30;
constexpr const char* Entry="motive://i1-g1/index.html";
constexpr const char* Csp="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'";
struct Frame { uint64_t index, observed_ns; int width,height,stride; std::vector<unsigned char> pixels; };
struct State {
  std::mutex mutex;
  std::optional<Frame> latest;
  uint64_t paints=0, coalesced=0;
  std::atomic<uint64_t> invalid{0}, busy{0};
  std::vector<uint64_t> observations;
  // Only accessed on CEF UI thread. Not a cross-process supervisor.
  std::map<int,CefRefPtr<CefBrowser>> browsers;
  bool stopping=false;
  unsigned pending_creates=0;
  void CloseAll() {
    stopping=true;
    auto copy=browsers;
    for(auto& [id,browser]:copy) { browser->GetHost()->WasHidden(true); browser->GetHost()->CloseBrowser(true); }
    if(browsers.empty()&&pending_creates==0) CefQuitMessageLoop();
  }
};
std::weak_ptr<State> active_state;
class Later final : public CefTask {
 public:
  explicit Later(std::function<void()> fn): fn_(std::move(fn)) {}
  void Execute() override { fn_(); }
 private:
  std::function<void()> fn_;
  IMPLEMENT_REFCOUNTING(Later);
};

class Client final : public CefClient, public CefRenderHandler, public CefLifeSpanHandler,
  public CefRequestHandler, public CefResourceRequestHandler, public CefPermissionHandler,
  public CefDownloadHandler, public CefDialogHandler, public CefJSDialogHandler,
  public CefContextMenuHandler {
 public:
  Client(std::shared_ptr<State> state,bool primary):s_(std::move(state)),primary_(primary){}
  CefRefPtr<CefRenderHandler> GetRenderHandler() override {return this;}
  CefRefPtr<CefLifeSpanHandler> GetLifeSpanHandler() override {return this;}
  CefRefPtr<CefRequestHandler> GetRequestHandler() override {return this;}
  CefRefPtr<CefPermissionHandler> GetPermissionHandler() override {return this;}
  CefRefPtr<CefDownloadHandler> GetDownloadHandler() override {return this;}
  CefRefPtr<CefDialogHandler> GetDialogHandler() override {return this;}
  CefRefPtr<CefJSDialogHandler> GetJSDialogHandler() override {return this;}
  CefRefPtr<CefContextMenuHandler> GetContextMenuHandler() override {return this;}
  void GetViewRect(CefRefPtr<CefBrowser>,CefRect& rect) override {rect=CefRect(0,0,Width,Height);}
  void OnPaint(CefRefPtr<CefBrowser>,PaintElementType type,const RectList& dirty,const void* buffer,int width,int height) override {
    if(s_->stopping || !primary_ || type!=PET_VIEW || !buffer || width!=Width || height!=Height || dirty.size()>128) {++s_->invalid;return;}
    for(const auto& r:dirty) if(r.x<0||r.y<0||r.width<=0||r.height<=0||int64_t(r.x)+r.width>width||int64_t(r.y)+r.height>height){++s_->invalid;return;}
    std::unique_lock lock(s_->mutex,std::try_to_lock);
    if(!lock.owns_lock()){++s_->busy;return;}
    const auto observed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
    const auto* p=static_cast<const unsigned char*>(buffer);
    // Complete copy before callback return. No CEF-owned pointer escapes.
    Frame frame{++s_->paints,uint64_t(observed),width,height,width*4,std::vector<unsigned char>(p,p+size_t(width)*height*4)};
    if(s_->latest)++s_->coalesced;
    s_->latest=std::move(frame);
    if(s_->observations.size()<360)s_->observations.push_back(observed);
  }
  void OnAfterCreated(CefRefPtr<CefBrowser> browser) override {
    if(primary_&&s_->pending_creates)--s_->pending_creates;
    s_->browsers.emplace(browser->GetIdentifier(),browser);
    browser->GetHost()->SetAudioMuted(true);
    if(!primary_||s_->stopping){browser->GetHost()->CloseBrowser(true);return;}
    browser->GetHost()->WasResized();
    browser->GetHost()->WasHidden(false);
    browser->GetHost()->Invalidate(PET_VIEW);
  }
  void OnBeforeClose(CefRefPtr<CefBrowser> browser) override {
    s_->browsers.erase(browser->GetIdentifier());
    if(primary_)s_->stopping=true;
    if(s_->stopping&&s_->browsers.empty()&&s_->pending_creates==0)CefQuitMessageLoop();
  }
  bool OnBeforePopup(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,int,const CefString&,const CefString&,
    cef_window_open_disposition_t,bool,const CefPopupFeatures&,CefWindowInfo&,CefRefPtr<CefClient>&,
    CefBrowserSettings&,CefRefPtr<CefDictionaryValue>&,bool*) override {return true;}
  bool OnBeforeBrowse(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame> frame,CefRefPtr<CefRequest> r,bool,bool redirect) override {
    if(!primary_||navigated_||!frame->IsMain()||redirect||r->GetURL()!=Entry||r->GetMethod()!="GET")return true;
    navigated_=true;return false;
  }
  bool OnOpenURLFromTab(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,const CefString&,cef_window_open_disposition_t,bool) override {return true;}
  CefRefPtr<CefResourceRequestHandler> GetResourceRequestHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest>,bool,bool,const CefString&,bool& disable) override {disable=true;return this;}
  ReturnValue OnBeforeResourceLoad(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest> r,CefRefPtr<CefCallback>) override {
    return primary_&&r->GetMethod()=="GET"&&Assets.contains(r->GetURL().ToString())?RV_CONTINUE:RV_CANCEL;
  }
  CefRefPtr<CefResourceHandler> GetResourceHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest> r) override {
    auto it=Assets.find(r->GetURL().ToString());if(!primary_||r->GetMethod()!="GET"||it==Assets.end())return nullptr;
    const auto& a=it->second;
    // Generated arrays are immutable and live for process lifetime.
    auto reader=CefStreamReader::CreateForHandler(new CefByteReadHandler(a.bytes,a.size,nullptr));
    CefResponse::HeaderMap headers;
    headers.emplace("Content-Security-Policy",Csp);headers.emplace("Cache-Control","no-store");headers.emplace("X-Content-Type-Options","nosniff");
    headers.emplace("Permissions-Policy","camera=(), microphone=(), clipboard-read=(), clipboard-write=(), geolocation=()");
    return new CefStreamResourceHandler(200,"OK",a.mime,headers,reader);
  }
  bool OnRequestMediaAccessPermission(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,const CefString&,uint32_t,CefRefPtr<CefMediaAccessCallback> c) override {c->Cancel();return true;}
  bool OnShowPermissionPrompt(CefRefPtr<CefBrowser>,uint64_t,const CefString&,uint32_t,CefRefPtr<CefPermissionPromptCallback> c) override {c->Continue(CEF_PERMISSION_RESULT_DENY);return true;}
  bool CanDownload(CefRefPtr<CefBrowser>,const CefString&,const CefString&) override {return false;}
  bool OnBeforeDownload(CefRefPtr<CefBrowser>,CefRefPtr<CefDownloadItem>,const CefString&,CefRefPtr<CefBeforeDownloadCallback>) override {return true;}
  void OnDownloadUpdated(CefRefPtr<CefBrowser>,CefRefPtr<CefDownloadItem>,CefRefPtr<CefDownloadItemCallback> c) override {c->Cancel();}
  bool OnFileDialog(CefRefPtr<CefBrowser>,FileDialogMode,const CefString&,const CefString&,const std::vector<CefString>&,const std::vector<CefString>&,const std::vector<CefString>&,CefRefPtr<CefFileDialogCallback> c) override {c->Cancel();return true;}
  bool OnJSDialog(CefRefPtr<CefBrowser>,const CefString&,JSDialogType,const CefString&,const CefString&,CefRefPtr<CefJSDialogCallback>,bool& suppress) override {suppress=true;return false;}
  bool OnBeforeUnloadDialog(CefRefPtr<CefBrowser>,const CefString&,bool,CefRefPtr<CefJSDialogCallback> c) override {c->Continue(true,CefString());return true;}
  void OnBeforeContextMenu(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefContextMenuParams>,CefRefPtr<CefMenuModel> menu) override {menu->Clear();}
  void OnProtocolExecution(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest>,bool& allow) override {allow=false;}
  bool OnProcessMessageReceived(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefProcessId,CefRefPtr<CefProcessMessage>) override {return false;}
  void OnRenderProcessTerminated(CefRefPtr<CefBrowser>,TerminationStatus,int,const CefString&) override {s_->CloseAll();}
 private:
  std::shared_ptr<State> s_;
  bool primary_,navigated_=false;
  IMPLEMENT_REFCOUNTING(Client);
};
class App final : public SchemeApp, public CefBrowserProcessHandler {
 public:
  explicit App(std::shared_ptr<State> s):s_(std::move(s)){}
  CefRefPtr<CefBrowserProcessHandler> GetBrowserProcessHandler() override {return this;}
  CefRefPtr<CefClient> GetDefaultClient() override {return new Client(s_,false);}
  void OnContextInitialized() override {
    CefWindowInfo window;window.SetAsWindowless(0);window.shared_texture_enabled=false;
    CefBrowserSettings settings;settings.windowless_frame_rate=Fps;settings.background_color=0;
    CefRequestContextSettings context_settings;
    auto context=CefRequestContext::CreateContext(context_settings,nullptr);
    s_->pending_creates=1;
    if(!CefBrowserHost::CreateBrowser(window,new Client(s_,true),Entry,settings,nullptr,context)){s_->pending_creates=0;s_->CloseAll();return;}
    auto state=s_;
    CefPostDelayedTask(TID_UI,new Later([state](){state->CloseAll();}),5000);
  }
 private:
  std::shared_ptr<State> s_;
  IMPLEMENT_REFCOUNTING(App);
};
} // namespace h16

// CEF-required Cocoa event dispatch adaptation from cefsimple (BSD source).
@interface H16Application : NSApplication<CefAppProtocol> { BOOL handling_; }
@end
@implementation H16Application
-(BOOL)isHandlingSendEvent{return handling_;}
-(void)setHandlingSendEvent:(BOOL)value{handling_=value;}
-(void)sendEvent:(NSEvent*)event{CefScopedSendingEvent scope;[super sendEvent:event];}
// Orderly closure is driven by the fixture's bounded CEF task, not exit().
-(void)terminate:(id)sender{(void)sender;if(auto state=h16::active_state.lock())state->CloseAll();}
@end

// Prepared implementation; intentionally has NO executable entry point.
// Needs reviewed bundle layout, process supervisor and explicit native exception.
int RunOwnedFixture(const std::string& private_root,const std::string& output_prefix) {
  CefScopedLibraryLoader library;if(!library.LoadInMain())return 2;
  @autoreleasepool {
    [H16Application sharedApplication];
    if(![NSApp isKindOfClass:[H16Application class]])return 3;
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
    char name[]="Motive H16 Fixture";char* argv[]={name,nullptr};CefMainArgs args(1,argv);
    CefSettings settings;settings.no_sandbox=false;settings.windowless_rendering_enabled=true;
    settings.command_line_args_disabled=true;settings.log_severity=LOGSEVERITY_DISABLE;
    CefString(&settings.root_cache_path)=private_root;
    auto state=std::make_shared<h16::State>();h16::active_state=state;
    CefRefPtr<h16::App> app=new h16::App(state);
    if(!CefInitialize(args,settings,app,nullptr))return 4;
    CefRunMessageLoop();
    // No further CEF references may survive shutdown. The helper-tree watchdog
    // and reap verification belong to the future external runner, not this task.
    state->browsers.clear();app=nullptr;h16::active_state.reset();CefShutdown();
    std::lock_guard lock(state->mutex);
    if(!state->latest)return 5;
    const auto& f=*state->latest;
    std::ofstream raw(output_prefix+".bgra",std::ios::binary);
    raw.write(reinterpret_cast<const char*>(f.pixels.data()),f.pixels.size());
    std::ofstream meta(output_prefix+".json");
    meta<<"{\"native_executed\":true,\"width\":"<<f.width<<",\"height\":"<<f.height<<",\"stride\":"<<f.stride<<",\"index\":"<<f.index<<",\"observed_ns\":"<<f.observed_ns<<",\"paints\":"<<state->paints<<",\"coalesced\":"<<state->coalesced<<",\"observations_ns\":[";
    for(size_t i=0;i<state->observations.size();++i){if(i)meta<<',';meta<<state->observations[i];}
    meta<<"],\"helper_cleanup_verified\":false,\"sandbox_verified\":false}";
    return raw&&meta?0:6;
  }
}
