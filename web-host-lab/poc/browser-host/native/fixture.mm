// SPDX-License-Identifier: GPL-3.0-or-later
// AppKit boilerplate adapted from pinned CEF cefsimple_mac.mm (BSD). See NOTICE.md.
#import <AppKit/AppKit.h>
#include "scheme.hpp"
#include "fixture_assets.hpp"
#include "fixture.hpp"
#include "frame_consumer.hpp"
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

constexpr const char* Csp="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'";
struct State {
  explicit State(const FixtureConfig& options):config(options),mailbox(motive_frames_create(1,options.generation,1,options.width,options.height)) {
    const std::string origin="motive://i1-g"+std::to_string(options.generation)+"/";
    entry=origin+"index.html";
    for(const auto& [url,asset]:Assets)inventory.emplace(origin+url.substr(std::string("motive://i1-g1/").size()),asset);
  }
  ~State(){motive_frames_destroy(mailbox);}
  const FixtureConfig config;
  MotiveFrameBridge* mailbox;
  std::string entry;
  std::map<std::string,Asset> inventory;
  std::atomic<uint64_t> invalid{0},busy{0},callbacks{0},max_publish_ns{0};
  // Only accessed on CEF UI thread. Not a cross-process supervisor.
  std::map<int,CefRefPtr<CefBrowser>> browsers;
  std::atomic<bool> stopping{false};
  unsigned pending_creates=0;
  void CloseAll() {
    stopping=true;
    motive_frames_revoke(mailbox);
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
  void GetViewRect(CefRefPtr<CefBrowser>,CefRect& rect) override {rect=CefRect(0,0,s_->config.width,s_->config.height);}
  bool GetScreenInfo(CefRefPtr<CefBrowser>,CefScreenInfo& info) override {
    info.device_scale_factor=1.0f;info.depth=32;info.depth_per_component=8;
    info.is_monochrome=false;info.rect=CefRect(0,0,s_->config.width,s_->config.height);
    info.available_rect=info.rect;return true;
  }
  void OnPaint(CefRefPtr<CefBrowser>,PaintElementType type,const RectList& dirty,const void* buffer,int width,int height) override {
    ++s_->callbacks;
    if(s_->stopping || !primary_ || type!=PET_VIEW || !buffer || width!=s_->config.width || height!=s_->config.height || dirty.size()>128) {++s_->invalid;return;}
    for(const auto& r:dirty) if(r.x<0||r.y<0||r.width<=0||r.height<=0||int64_t(r.x)+r.width>width||int64_t(r.y)+r.height>height){++s_->invalid;return;}
    // The existing Rust mailbox copies all bytes synchronously before return.
    // It never retains this CEF-owned pointer and drops paints on contention.
    const auto started=MonotonicNs();
    const int result=motive_frames_publish(s_->mailbox,s_->config.generation,1,MonotonicNs(),
      static_cast<const uint8_t*>(buffer),size_t(width)*size_t(height)*4);
    s_->max_publish_ns=std::max(s_->max_publish_ns.load(),MonotonicNs()-started);
    if(result==1)++s_->busy;else if(result!=0)++s_->invalid;
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
    if(primary_){s_->stopping=true;motive_frames_revoke(s_->mailbox);}
    if(s_->stopping&&s_->browsers.empty()&&s_->pending_creates==0)CefQuitMessageLoop();
  }
  bool OnBeforePopup(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,int,const CefString&,const CefString&,
    cef_window_open_disposition_t,bool,const CefPopupFeatures&,CefWindowInfo&,CefRefPtr<CefClient>&,
    CefBrowserSettings&,CefRefPtr<CefDictionaryValue>&,bool*) override {return true;}
  bool OnBeforeBrowse(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame> frame,CefRefPtr<CefRequest> r,bool,bool redirect) override {
    if(!primary_||navigated_||!frame->IsMain()||redirect||r->GetURL()!=s_->entry||r->GetMethod()!="GET")return true;
    navigated_=true;return false;
  }
  bool OnOpenURLFromTab(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,const CefString&,cef_window_open_disposition_t,bool) override {return true;}
  CefRefPtr<CefResourceRequestHandler> GetResourceRequestHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest>,bool,bool,const CefString&,bool& disable) override {disable=true;return this;}
  ReturnValue OnBeforeResourceLoad(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest> r,CefRefPtr<CefCallback>) override {
    return primary_&&r->GetMethod()=="GET"&&s_->inventory.contains(r->GetURL().ToString())?RV_CONTINUE:RV_CANCEL;
  }
  CefRefPtr<CefResourceHandler> GetResourceHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest> r) override {
    auto it=s_->inventory.find(r->GetURL().ToString());if(!primary_||r->GetMethod()!="GET"||it==s_->inventory.end())return nullptr;
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
    CefBrowserSettings settings;settings.windowless_frame_rate=s_->config.fps;settings.background_color=0;
    CefRequestContextSettings context_settings;
    auto context=CefRequestContext::CreateContext(context_settings,nullptr);
    s_->pending_creates=1;
    if(!CefBrowserHost::CreateBrowser(window,new Client(s_,true),s_->entry,settings,nullptr,context)){s_->pending_creates=0;s_->CloseAll();return;}
    auto state=s_;
    CefPostDelayedTask(TID_UI,new Later([state](){state->CloseAll();}),s_->config.duration_ms);
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

// Linked only by the isolated development fixture, never by Production.
int RunOwnedFixture(const FixtureConfig& config,int argc,char** argv) {
  CefScopedLibraryLoader library;if(!library.LoadInMain())return 2;
  @autoreleasepool {
    [H16Application sharedApplication];
    if(![NSApp isKindOfClass:[H16Application class]])return 3;
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
    CefMainArgs args(argc,argv);
    CefSettings settings;settings.no_sandbox=false;settings.windowless_rendering_enabled=true;
    settings.command_line_args_disabled=true;settings.log_severity=LOGSEVERITY_DISABLE;
    CefString(&settings.root_cache_path)=config.private_root+"/cache";
    auto state=std::make_shared<h16::State>(config);
    if(!state->mailbox)return 7;
    FrameConsumer consumer(state->mailbox,config.private_root);
    if(!consumer.valid())return 8;
    h16::active_state=state;
    CefRefPtr<h16::App> app=new h16::App(state);
    if(!CefInitialize(args,settings,app,nullptr)){h16::active_state.reset();return 4;}
    CefRunMessageLoop();
    state->CloseAll();consumer.Stop();
    state->browsers.clear();app=nullptr;h16::active_state.reset();CefShutdown();
    return consumer.WriteReport(state->callbacks,state->busy,state->invalid,state->max_publish_ns)?0:5;
  }
}
