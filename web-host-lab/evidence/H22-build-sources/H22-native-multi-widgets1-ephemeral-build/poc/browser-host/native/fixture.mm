// SPDX-License-Identifier: GPL-3.0-or-later
// AppKit boilerplate adapted from pinned CEF cefsimple_mac.mm (BSD). See NOTICE.md.
#import <AppKit/AppKit.h>
#include "scheme.hpp"
#include "fixture_assets.hpp"
#include "fixture.hpp"
#include "diagnostic_policy.hpp"
#include "multi_policy.hpp"
#include "frame_consumer.hpp"
#ifdef MOTIVE_GOAL_BRIDGE
#include "goal_binding.h"
#include "bridge_policy.hpp"
#include "include/cef_parser.h"
#include <array>
#endif
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
#include <set>
#include <sys/stat.h>
#include <unistd.h>

namespace h16 {

[[maybe_unused]] constexpr const char* Csp="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'";
struct Host;
struct State {
  explicit State(const FixtureConfig& options,uint64_t instance=1):config(options),instance(instance),mailbox(motive_frames_create(instance,options.generation,1,options.width,options.height)) {
    trace_fd=open((options.private_root+"/lifecycle.jsonl").c_str(),O_WRONLY|O_NOFOLLOW|O_CLOEXEC|(options.multi?(O_CREAT|O_EXCL):O_APPEND),0600);
    Trace("constructed");
    origin="motive://i"+std::to_string(instance)+"-g"+std::to_string(options.generation)+"/";
#ifdef MOTIVE_GOAL_BRIDGE
    entry=origin+"host/index.html";widget_entry=origin+"widget/index.html";
    goal=motive_goal_create_for_instance(instance,options.generation,reinterpret_cast<const uint8_t*>(GoalDefinitionHash),64);
#else
    entry=origin+"index.html";
#endif
    for(const auto& [url,asset]:Assets)inventory.emplace(origin+url.substr(std::string("motive://i1-g1/").size()),asset);
  }
  ~State(){
#ifdef MOTIVE_GOAL_BRIDGE
    motive_goal_destroy(goal);
#endif
    consumer.reset();motive_frames_destroy(mailbox);
    if(trace_fd>=0)close(trace_fd);
  }
  void Trace(const char* phase){
    if(trace_fd<0||trace_count++>=4096)return;
    const std::string line="{\"phase\":\""+std::string(phase)+"\",\"observed_ns\":"+std::to_string(MonotonicNs())+",\"instance\":"+std::to_string(instance)+",\"generation\":"+std::to_string(config.generation)+",\"epoch\":"+std::to_string(epoch)+"}\n";
    (void)write(trace_fd,line.data(),line.size());
  }
  int trace_fd=-1;
  unsigned trace_count=0;
  FixtureConfig config;
  const uint64_t instance;
  uint64_t epoch=1,created_ns=MonotonicNs(),first_paint_ns=0,first_useful_paint_ns=0,closed_ns=0;
  int renderer_pid=0,browser_id=-1;
  bool renderer_decoy_observed=false,renderer_decoy_opened=false,browser_decoy_opened=false;
  int renderer_decoy_errno=-1,browser_decoy_errno=-1;
  bool rendered_content=false,frames_written=false,closed=false,animated=true,crash_allowed=false;
  bool failed=false,hidden=false,frame_finalized=false;
  uint64_t blocked_resources=0,blocked_navigation=0,blocked_popups=0,blocked_downloads=0,blocked_permissions=0,events_received=0;
  int last_renderer_status=0,last_renderer_exit_code=0;
  uint64_t epoch_started_ns=created_ns;
  std::vector<std::string> epoch_records;
  std::set<int> security_phases;
  void CaptureEpoch(bool resize,bool written);
  std::weak_ptr<Host> host;
  std::unique_ptr<FrameConsumer> consumer;
  MotiveFrameBridge* mailbox;
  CefRefPtr<CefRequestContext> context;
  std::string entry,origin,health="created";
  std::set<std::pair<int,int>> used_dimensions;
  void FinishFrames();
  bool StartConsumer();
  void Resize(int width,int height);
  void HostMaybeQuit();
  void ReplacementReady();
  void RendererFailed(int status,int exit_code);
#if defined(MOTIVE_GOAL_BRIDGE) || defined(MOTIVE_WIDGET_FIXTURES)
  std::atomic<uint64_t> visual_capture_after_ns{0};
  unsigned visibility_stage=0;
#endif
#ifdef MOTIVE_WIDGET_FIXTURES
  int widget_kind=0;
#endif
#ifdef MOTIVE_GOAL_BRIDGE
  std::string widget_entry;
  MotiveGoalBinding* goal=nullptr;
#ifdef MOTIVE_GOAL_CONTROLS
  unsigned control_stage=0;
  bool controls_complete=false;
#endif
  bool bootstrap_sent=false;
  int visibility_sequence=0;
  std::optional<int> primary_browser;
  const uint64_t clock_origin_ms=MonotonicNs()/1000000;
#endif
#ifdef MOTIVE_DIAGNOSTIC_MODE
  std::optional<int> diagnostic_browser;
  bool fixture_ready=false,static_painted=false,slow_started=false,slow_finished=false,revocation_confirmed=false;
  bool hidden_settled=false,hidden_finished=false,crash_requested=false,renderer_terminated=false;
  int renderer_status=0,renderer_exit_code=0,renderer_decoded_exit_code=-1;
  uint64_t hidden_baseline=0,hidden_end=0,slow_begin_ns=0,slow_end_ns=0;
  void WriteDiagnostic(){
    const int fd=open((config.private_root+"/diagnostic.json").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return;
    const std::string data="{\"native_executed\":true,\"mode\":"+std::to_string(MOTIVE_DIAGNOSTIC_MODE)+",\"fixture_ready\":"+(fixture_ready?"true":"false")+",\"static_painted\":"+(static_painted?"true":"false")+",\"hidden_settled\":"+(hidden_settled?"true":"false")+",\"hidden_finished\":"+(hidden_finished?"true":"false")+",\"hidden_baseline_callbacks\":"+std::to_string(hidden_baseline)+",\"hidden_end_callbacks\":"+std::to_string(hidden_end)+",\"slow_begin_ns\":"+std::to_string(slow_begin_ns)+",\"slow_end_ns\":"+std::to_string(slow_end_ns)+",\"crash_requested\":"+(crash_requested?"true":"false")+",\"renderer_terminated\":"+(renderer_terminated?"true":"false")+",\"revocation_confirmed\":"+(revocation_confirmed?"true":"false")+",\"renderer_status\":"+std::to_string(renderer_status)+",\"renderer_exit_code\":"+std::to_string(renderer_exit_code)+",\"renderer_decoded_exit_code\":"+std::to_string(renderer_decoded_exit_code)+"}\n";
    (void)write(fd,data.data(),data.size());close(fd);
  }
#endif
  std::map<std::string,Asset> inventory;
  std::atomic<uint64_t> invalid{0},busy{0},callbacks{0},max_publish_ns{0};
  // Only accessed on CEF UI thread. Not a cross-process supervisor.
  std::map<int,CefRefPtr<CefBrowser>> browsers;
  std::atomic<bool> stopping{false};
  unsigned pending_creates=0;
  bool quit_requested=false;
  void MaybeQuit(){HostMaybeQuit();}
  void CloseAll() {
    if(stopping.exchange(true))return;
    Trace("close_requested");
    if(mailbox)motive_frames_revoke(mailbox);
#ifdef MOTIVE_DIAGNOSTIC_MODE
    revocation_confirmed=!motive_frames_live(mailbox);Trace("frame_generation_revoked");
#endif
    auto copy=browsers;
    for(auto& [id,browser]:copy) { browser->GetHost()->WasHidden(true); browser->GetHost()->CloseBrowser(true); }
    MaybeQuit();
  }
};
std::weak_ptr<Host> active_host;
class Later final : public CefTask {
 public:
  explicit Later(std::function<void()> fn): fn_(std::move(fn)) {}
  void Execute() override { fn_(); }
 private:
  std::function<void()> fn_;
  IMPLEMENT_REFCOUNTING(Later);
};

#ifdef MOTIVE_GOAL_BRIDGE
bool GoalVisibilityCommand(std::shared_ptr<State> state,CefRefPtr<CefFrame> frame,bool hidden){
  if(state->stopping||!state->goal||!frame)return false;
  if((hidden&&state->visibility_stage!=0&&state->visibility_stage!=4)||(!hidden&&state->visibility_stage!=2)){state->Trace("visibility_transition_rejected");return false;}
  std::array<uint8_t,16384> output{};const uint64_t now=MonotonicNs()/1000000-state->clock_origin_ms;
  const auto count=motive_goal_control(state->goal,hidden?2:3,now,output.data(),output.size());
  if(count<=0){state->Trace("visibility_control_rejected");return false;}
  const std::string bytes(reinterpret_cast<const char*>(output.data()),size_t(count));
  auto value=CefParseJSON(bytes,JSON_PARSER_RFC);
  if(!value||value->GetType()!=VTYPE_DICTIONARY)return false;
  auto envelope=value->GetDictionary();auto body=envelope->GetDictionary("message");
  if(!body||body->GetType("seq")!=VTYPE_INT||body->GetInt("seq")<=0)return false;
  state->visibility_sequence=body->GetInt("seq");state->visibility_stage=hidden?1:3;
  state->Trace(hidden?"hidden_cancel_dispatched":"hidden_resume_dispatched");
  auto message=CefProcessMessage::Create(motive_bridge::DispatchMessage);message->GetArgumentList()->SetString(0,bytes);message->GetArgumentList()->SetDouble(1,double(now));frame->SendProcessMessage(PID_RENDERER,message);return true;
}
#endif
#ifdef MOTIVE_GOAL_CONTROLS
bool FixedControl(std::shared_ptr<State> state,CefRefPtr<CefFrame> frame,uint32_t action,const char* phase){
  if(state->stopping)return false;
  std::array<uint8_t,16384> output{};const uint64_t now=MonotonicNs()/1000000-state->clock_origin_ms;
  const auto count=motive_goal_control(state->goal,action,now,output.data(),output.size());
  if(action==1&&count==0){state->Trace("repeated_event_rejected");return true;}
  if(count<=0){state->Trace("fixed_control_failed");state->CloseAll();return false;}
  state->Trace(phase);auto message=CefProcessMessage::Create(motive_bridge::DispatchMessage);
  message->GetArgumentList()->SetString(0,std::string(reinterpret_cast<const char*>(output.data()),size_t(count)));
  message->GetArgumentList()->SetDouble(1,double(now));frame->SendProcessMessage(PID_RENDERER,message);return true;
}
#endif

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
  void OnPaint(CefRefPtr<CefBrowser> browser,PaintElementType type,const RectList& dirty,const void* buffer,int width,int height) override {
    ++s_->callbacks;
    if(s_->stopping || !s_->mailbox || !primary_ || browser->GetIdentifier()!=s_->browser_id || type!=PET_VIEW || !buffer || width!=s_->config.width || height!=s_->config.height || dirty.size()>128) {++s_->invalid;return;}
    for(const auto& r:dirty) if(r.x<0||r.y<0||r.width<=0||r.height<=0||int64_t(r.x)+r.width>width||int64_t(r.y)+r.height>height){++s_->invalid;return;}
    // The existing Rust mailbox copies all bytes synchronously before return.
    // It never retains this CEF-owned pointer and drops paints on contention.
    const auto started=MonotonicNs();
    const int result=motive_frames_publish(s_->mailbox,s_->config.generation,s_->epoch,MonotonicNs(),
      static_cast<const uint8_t*>(buffer),size_t(width)*size_t(height)*4);
    s_->max_publish_ns=std::max(s_->max_publish_ns.load(),MonotonicNs()-started);
    if(result==1)++s_->busy;else if(result!=0)++s_->invalid;
    else {
      if(!s_->first_paint_ns){s_->first_paint_ns=started;s_->Trace("first_accepted_paint");}
      if(!s_->first_useful_paint_ns){
        const auto* pixels=static_cast<const uint8_t*>(buffer);
        for(size_t alpha=3;alpha<size_t(width)*size_t(height)*4;alpha+=4)if(pixels[alpha]){s_->first_useful_paint_ns=started;s_->Trace("first_nontransparent_paint");break;}
      }
    }
  }
  void OnAfterCreated(CefRefPtr<CefBrowser> browser) override {
    if(primary_){s_->browser_id=browser->GetIdentifier();s_->health="ready";}s_->Trace("after_created");
#ifdef MOTIVE_GOAL_BRIDGE
    if(primary_)s_->primary_browser=browser->GetIdentifier();
#elif defined(MOTIVE_DIAGNOSTIC_MODE)
    if(primary_)s_->diagnostic_browser=browser->GetIdentifier();
#endif
    if(primary_&&s_->pending_creates)--s_->pending_creates;
    s_->browsers.emplace(browser->GetIdentifier(),browser);
    browser->GetHost()->SetAudioMuted(true);
    if(!primary_||s_->stopping){browser->GetHost()->CloseBrowser(true);return;}
    browser->GetHost()->WasResized();
    browser->GetHost()->WasHidden(false);
    browser->GetHost()->Invalidate(PET_VIEW);
  }
  void OnBeforeClose(CefRefPtr<CefBrowser> browser) override {
    s_->Trace("before_close");
    s_->browsers.erase(browser->GetIdentifier());
    if(primary_){s_->stopping=true;if(s_->mailbox)motive_frames_revoke(s_->mailbox);s_->closed=true;s_->closed_ns=MonotonicNs();s_->health=s_->failed?"failed_closed":"closed";s_->FinishFrames();s_->context=nullptr;s_->Trace("context_released");s_->ReplacementReady();}
    s_->MaybeQuit();
  }
  bool OnBeforePopup(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,int,const CefString&,const CefString&,
    cef_window_open_disposition_t,bool,const CefPopupFeatures&,CefWindowInfo&,CefRefPtr<CefClient>&,
    CefBrowserSettings&,CefRefPtr<CefDictionaryValue>&,bool*) override {++s_->blocked_popups;return true;}
  bool OnBeforeBrowse(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame> frame,CefRefPtr<CefRequest> r,bool,bool redirect) override {
    if(!primary_||!frame||redirect||r->GetMethod()!="GET"){++s_->blocked_navigation;return true;}
    if(frame->IsMain()){
      if(navigated_||r->GetURL()!=s_->entry)return true;navigated_=true;return false;
    }
#ifdef MOTIVE_GOAL_BRIDGE
    auto parent=frame->GetParent();
    if(!widget_navigated_&&parent&&parent->IsMain()&&r->GetURL()==s_->widget_entry){widget_navigated_=true;return false;}
#endif
    return true;
  }
  bool OnOpenURLFromTab(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,const CefString&,cef_window_open_disposition_t,bool) override {return true;}
  CefRefPtr<CefResourceRequestHandler> GetResourceRequestHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest>,bool,bool,const CefString&,bool& disable) override {disable=true;return this;}
  ReturnValue OnBeforeResourceLoad(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame> frame,CefRefPtr<CefRequest> r,CefRefPtr<CefCallback>) override {
    auto it=s_->inventory.find(r->GetURL().ToString());
    if(!primary_||!frame||r->GetMethod()!="GET"||it==s_->inventory.end()){++s_->blocked_resources;return RV_CANCEL;}
#ifdef MOTIVE_GOAL_BRIDGE
    if(frame->IsMain()==it->second.widget)return RV_CANCEL;
#endif
    return RV_CONTINUE;
  }
  CefRefPtr<CefResourceHandler> GetResourceHandler(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame> frame,CefRefPtr<CefRequest> r) override {
    auto it=s_->inventory.find(r->GetURL().ToString());if(!primary_||!frame||r->GetMethod()!="GET"||it==s_->inventory.end())return nullptr;
    const auto& a=it->second;
#ifdef MOTIVE_GOAL_BRIDGE
    if(frame->IsMain()==a.widget)return nullptr;
#endif
    // Generated arrays are immutable and live for process lifetime.
    auto reader=CefStreamReader::CreateForHandler(new CefByteReadHandler(a.bytes,a.size,nullptr));
    CefResponse::HeaderMap headers;
#ifdef MOTIVE_GOAL_BRIDGE
    const char* policy=a.widget?"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'":"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; frame-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; worker-src 'none'";
    headers.emplace("Content-Security-Policy",policy);
    if(a.widget)headers.emplace("Access-Control-Allow-Origin","*");
#else
    headers.emplace("Content-Security-Policy",Csp);
#endif
    headers.emplace("Cache-Control","no-store");headers.emplace("X-Content-Type-Options","nosniff");
    headers.emplace("Permissions-Policy","camera=(), microphone=(), clipboard-read=(), clipboard-write=(), geolocation=()");
    return new CefStreamResourceHandler(200,"OK",a.mime,headers,reader);
  }
  bool OnRequestMediaAccessPermission(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,const CefString&,uint32_t,CefRefPtr<CefMediaAccessCallback> c) override {++s_->blocked_permissions;c->Cancel();return true;}
  bool OnShowPermissionPrompt(CefRefPtr<CefBrowser>,uint64_t,const CefString&,uint32_t,CefRefPtr<CefPermissionPromptCallback> c) override {++s_->blocked_permissions;c->Continue(CEF_PERMISSION_RESULT_DENY);return true;}
  bool CanDownload(CefRefPtr<CefBrowser>,const CefString&,const CefString&) override {++s_->blocked_downloads;return false;}
  bool OnBeforeDownload(CefRefPtr<CefBrowser>,CefRefPtr<CefDownloadItem>,const CefString&,CefRefPtr<CefBeforeDownloadCallback>) override {++s_->blocked_downloads;return true;}
  void OnDownloadUpdated(CefRefPtr<CefBrowser>,CefRefPtr<CefDownloadItem>,CefRefPtr<CefDownloadItemCallback> c) override {c->Cancel();}
  bool OnFileDialog(CefRefPtr<CefBrowser>,FileDialogMode,const CefString&,const CefString&,const std::vector<CefString>&,const std::vector<CefString>&,const std::vector<CefString>&,CefRefPtr<CefFileDialogCallback> c) override {c->Cancel();return true;}
  bool OnJSDialog(CefRefPtr<CefBrowser>,const CefString&,JSDialogType,const CefString&,const CefString&,CefRefPtr<CefJSDialogCallback>,bool& suppress) override {suppress=true;return false;}
  bool OnBeforeUnloadDialog(CefRefPtr<CefBrowser>,const CefString&,bool,CefRefPtr<CefJSDialogCallback> c) override {c->Continue(true,CefString());return true;}
  void OnBeforeContextMenu(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefContextMenuParams>,CefRefPtr<CefMenuModel> menu) override {menu->Clear();}
  void OnProtocolExecution(CefRefPtr<CefBrowser>,CefRefPtr<CefFrame>,CefRefPtr<CefRequest>,bool& allow) override {allow=false;}
  bool OnProcessMessageReceived(CefRefPtr<CefBrowser> browser,CefRefPtr<CefFrame> frame,CefProcessId source,CefRefPtr<CefProcessMessage> message) override {
#ifdef MOTIVE_MULTI_BROWSER
    if(primary_&&!s_->stopping&&frame&&frame->IsMain()&&frame->GetURL()==s_->entry&&source==PID_RENDERER&&browser->GetIdentifier()==s_->browser_id){
      auto args=message->GetArgumentList();
      if(message->GetName()=="motive.h19.renderer_identity"&&args->GetSize()==1&&args->GetType(0)==VTYPE_INT&&args->GetInt(0)>0){
        if(s_->renderer_pid&&s_->renderer_pid!=args->GetInt(0))return false;
        s_->renderer_pid=args->GetInt(0);s_->Trace("renderer_identity_observed");return true;
      }
      if(message->GetName()=="motive.h19.decoy_result"&&s_->config.scenario=="security"&&args->GetSize()==3&&args->GetType(0)==VTYPE_BOOL&&args->GetType(1)==VTYPE_INT&&args->GetType(2)==VTYPE_INT&&args->GetInt(2)==s_->renderer_pid){
        s_->renderer_decoy_observed=true;s_->renderer_decoy_opened=args->GetBool(0);s_->renderer_decoy_errno=args->GetInt(1);s_->Trace("renderer_decoy_result");return true;
      }
      if(message->GetName()=="motive.h19.phase"&&args->GetSize()==1&&args->GetType(0)==VTYPE_INT){
        const int phase=args->GetInt(0);
        if(phase==1){s_->Trace("fixture_ready");return true;}
        if(phase==2){s_->rendered_content=true;s_->Trace("content_drawn");return true;}
        if(phase==5){s_->Trace("slow_begin");return true;}
        if(phase==6){s_->Trace("slow_end");return true;}
        if(phase==7){++s_->events_received;s_->Trace("fixture_event_received");return true;}
#ifdef MOTIVE_WIDGET_FIXTURES
        if(phase==8){s_->Trace("visual_active");uint64_t empty=0;s_->visual_capture_after_ns.compare_exchange_strong(empty,MonotonicNs()+600000000);return true;}
        if(phase==9){s_->Trace("visual_complete");return true;}
        if(phase==10&&s_->visibility_stage==1){s_->Trace("hidden_cancel_acknowledged");s_->visibility_stage=2;s_->hidden=true;browser->GetHost()->WasHidden(true);s_->Trace("hidden_begin");return true;}
        if(phase==11&&s_->visibility_stage==3){s_->Trace("hidden_resume_acknowledged");s_->visibility_stage=4;s_->hidden=false;browser->GetHost()->WasHidden(false);browser->GetHost()->Invalidate(PET_VIEW);s_->Trace("hidden_end");return true;}
        if(phase==12){s_->Trace("fixture_event_rejected");return true;}
#endif
        if(s_->config.scenario=="security"&&phase>=20&&phase<=29){s_->security_phases.insert(phase);s_->Trace("security_fixture_observation");return true;}
      }
    }
#endif
#ifdef MOTIVE_GOAL_BRIDGE
    if(!primary_||!s_->goal||s_->stopping||message->GetName()!=motive_bridge::StatusMessage)return false;
    auto args=message->GetArgumentList();if(args->GetType(0)!=VTYPE_STRING)return false;const auto text=args->GetString(0);
    const motive_bridge::Identity id{s_->instance,s_->config.generation,s_->primary_browser.value_or(-1),s_->entry};
    if(!s_->browsers.contains(browser->GetIdentifier())||!motive_bridge::Boundary(id,browser->GetIdentifier(),frame&&frame->IsMain(),source==PID_RENDERER,frame?frame->GetURL().ToString():"",args->GetSize(),1,text.length(),512))return false;
    auto value=CefParseJSON(text,JSON_PARSER_RFC);if(!value||value->GetType()!=VTYPE_DICTIONARY)return false;
    auto status=value->GetDictionary();
    if(status->GetString("kind")=="bootstrap_loaded"){
      if(s_->bootstrap_sent||status->GetSize()!=1)return false;s_->bootstrap_sent=true;s_->Trace("bootstrap_loaded");
      auto manifest=CefParseJSON(std::string(reinterpret_cast<const char*>(GoalManifestJson),GoalManifestJsonSize),JSON_PARSER_RFC);if(!manifest)return false;
      auto identity=CefDictionaryValue::Create();identity->SetDouble("instance",double(s_->instance));identity->SetDouble("generation",double(s_->config.generation));
      auto config=CefDictionaryValue::Create();config->SetDictionary("identity",identity);config->SetValue("contract",manifest);config->SetString("entry",s_->widget_entry);
      auto body=CefValue::Create();body->SetDictionary(config);auto init=CefProcessMessage::Create(motive_bridge::InitializeMessage);init->GetArgumentList()->SetString(0,CefWriteJSON(body,JSON_WRITER_DEFAULT));frame->SendProcessMessage(PID_RENDERER,init);return true;
    }
    if(!s_->bootstrap_sent)return false;
    const auto bytes=text.ToString();std::array<uint8_t,16384> output{};
    const uint64_t now=MonotonicNs()/1000000-s_->clock_origin_ms;
    const auto count=motive_goal_status(s_->goal,reinterpret_cast<const uint8_t*>(bytes.data()),bytes.size(),now,output.data(),output.size());
    if(count<0){s_->Trace("bridge_status_rejected");s_->CloseAll();return false;}
    const auto kind=status->GetString("kind");
    if(kind=="renderer_ready")s_->Trace("renderer_ready");
    if(kind=="visual_ack")s_->Trace("visual_ack");
    if(s_->config.multi&&kind=="visual_ack"&&status->GetBool("accepted")&&status->GetInt("seq")==s_->visibility_sequence){
      if(s_->visibility_stage==1){
        s_->Trace("hidden_cancel_acknowledged");s_->visibility_stage=2;s_->hidden=true;
        browser->GetHost()->WasHidden(true);s_->Trace("hidden_begin");
      }else if(s_->visibility_stage==3){
        s_->Trace("hidden_resume_acknowledged");s_->visibility_stage=4;s_->hidden=false;
        browser->GetHost()->WasHidden(false);browser->GetHost()->Invalidate(PET_VIEW);s_->Trace("hidden_end");
      }
    }
    if(kind=="visual_state"){
      if(status->GetString("state")=="active"){
        s_->Trace("visual_active");uint64_t empty=0;s_->visual_capture_after_ns.compare_exchange_strong(empty,MonotonicNs()+(s_->config.multi&&(s_->config.scenario=="hidden"||s_->config.scenario=="goal-lifecycle")?200000000:600000000));
#ifdef MOTIVE_GOAL_CONTROLS
        if(s_->control_stage==0){
          s_->control_stage=1;auto state=s_;
          CefPostDelayedTask(TID_UI,new Later([state,frame](){FixedControl(state,frame,1,"unused_repeat_dispatch");}),100);
          CefPostDelayedTask(TID_UI,new Later([state,frame](){if(state->stopping)return;state->control_stage=2;FixedControl(state,frame,2,"cancel_dispatched");}),800);
        }
#endif
      }
      if(status->GetString("state")=="ready"&&status->GetType("sequence")!=VTYPE_NULL)s_->Trace("visual_complete");
    }
#ifdef MOTIVE_GOAL_CONTROLS
    if(kind=="visual_state"){
      if(status->GetString("state")=="cancelled")s_->Trace("visual_cancelled");
      if(status->GetString("state")=="disposed")s_->Trace("visual_disposed");
      if(status->GetString("state")=="ready"&&s_->control_stage==3)s_->Trace("visual_resumed_ready");
    }
    if(kind=="visual_ack"&&status->GetBool("accepted")){
      const auto seq=status->GetInt("seq");
      if(s_->control_stage==2&&seq==3){s_->Trace("cancel_acknowledged");s_->control_stage=3;FixedControl(s_,frame,3,"resume_dispatched");}
      else if(s_->control_stage==3&&seq==4){s_->Trace("resume_acknowledged");s_->control_stage=4;FixedControl(s_,frame,4,"dispose_dispatched");}
      else if(s_->control_stage==4&&seq==5){
        s_->Trace("dispose_acknowledged");s_->control_stage=5;s_->controls_complete=true;auto state=s_;
        // Allow the final hidden document paint to reach the independent consumer.
        CefPostDelayedTask(TID_UI,new Later([state](){state->Trace("controls_close_task");state->CloseAll();}),250);
      }
    }
#endif
    if(count>0){s_->Trace(kind=="renderer_ready"?"properties_dispatched":"goal_dispatched");auto dispatch=CefProcessMessage::Create(motive_bridge::DispatchMessage);dispatch->GetArgumentList()->SetString(0,std::string(reinterpret_cast<const char*>(output.data()),size_t(count)));dispatch->GetArgumentList()->SetDouble(1,double(now));frame->SendProcessMessage(PID_RENDERER,dispatch);}
    return true;
#elif defined(MOTIVE_DIAGNOSTIC_MODE)
    if(!primary_||s_->stopping||!frame||message->GetName()!=motive_diagnostic::PhaseMessage)return false;
    auto args=message->GetArgumentList();
    const motive_bridge::Identity id{s_->instance,s_->config.generation,s_->diagnostic_browser.value_or(-1),s_->entry};
    if(!motive_bridge::Boundary(id,browser->GetIdentifier(),frame->IsMain(),source==PID_RENDERER,frame->GetURL().ToString(),args->GetSize(),1,1,1)||args->GetType(0)!=VTYPE_INT)return false;
    const int phase=args->GetInt(0);if(!motive_diagnostic::PhaseAllowed(MOTIVE_DIAGNOSTIC_MODE,phase))return false;
    if(phase==1){
      if(s_->fixture_ready)return false;s_->fixture_ready=true;s_->Trace("fixture_ready");[[maybe_unused]] auto state=s_;
#if MOTIVE_DIAGNOSTIC_MODE == 2
      CefPostDelayedTask(TID_UI,new Later([state,browser](){if(state->stopping)return;state->Trace("hidden_begin");browser->GetHost()->WasHidden(true);}),1000);
      CefPostDelayedTask(TID_UI,new Later([state](){if(state->stopping)return;state->hidden_settled=true;state->hidden_baseline=state->callbacks;state->Trace("hidden_settled");}),1100);
      CefPostDelayedTask(TID_UI,new Later([state,browser](){if(state->stopping)return;state->hidden_end=state->callbacks;state->hidden_finished=true;state->Trace("hidden_end");browser->GetHost()->WasHidden(false);browser->GetHost()->Invalidate(PET_VIEW);}),3000);
#elif MOTIVE_DIAGNOSTIC_MODE == 4
      CefPostDelayedTask(TID_UI,new Later([state,frame](){if(state->stopping)return;state->crash_requested=true;state->Trace("renderer_exit_requested");frame->SendProcessMessage(PID_RENDERER,CefProcessMessage::Create(motive_diagnostic::ExitMessage));}),1000);
#endif
    } else if(phase==2){if(!s_->fixture_ready||s_->static_painted)return false;s_->static_painted=true;s_->Trace("static_painted_once");}
    else if(phase==3)s_->Trace("document_hidden");
    else if(phase==4)s_->Trace("document_visible");
    else if(phase==5){if(!s_->fixture_ready||s_->slow_started)return false;s_->slow_started=true;s_->slow_begin_ns=MonotonicNs();s_->Trace("slow_begin");}
    else if(phase==6){if(!s_->slow_started||s_->slow_finished)return false;s_->slow_finished=true;s_->slow_end_ns=MonotonicNs();s_->Trace("slow_end");}
    return true;
#else
    return false;
#endif
  }
  void OnRenderProcessTerminated(CefRefPtr<CefBrowser> browser,TerminationStatus status,int exit_code,const CefString&) override {
    // All profiles invalidate frame admission immediately, before deferred close.
    if(s_->mailbox)motive_frames_revoke_reason(s_->mailbox,1);s_->failed=true;s_->health="failed";s_->last_renderer_status=int(status);s_->last_renderer_exit_code=exit_code;s_->Trace("renderer_terminated");
#ifdef MOTIVE_DIAGNOSTIC_MODE
    if(primary_&&s_->diagnostic_browser==browser->GetIdentifier()){
      s_->renderer_terminated=true;s_->renderer_status=int(status);s_->renderer_exit_code=exit_code;s_->renderer_decoded_exit_code=motive_diagnostic::PosixExitCode(exit_code);s_->Trace("renderer_error_observed");
      // Revoke immediately, but do not destroy browser/web-contents while CEF's
      // PrimaryMainFrameRenderProcessGone still owns its navigation lock.
      s_->revocation_confirmed=!motive_frames_live(s_->mailbox);
      s_->Trace("frame_generation_revoked");s_->WriteDiagnostic();
    }
#endif
    s_->RendererFailed(int(status),exit_code);
  }
 private:
  std::shared_ptr<State> s_;
  bool primary_,navigated_=false;
#ifdef MOTIVE_GOAL_BRIDGE
  bool widget_navigated_=false;
#endif
  IMPLEMENT_REFCOUNTING(Client);
};
struct Host : std::enable_shared_from_this<Host> {
  explicit Host(const FixtureConfig& options):config(options){
    trace_fd=open((config.private_root+"/lifecycle.jsonl").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  }
  ~Host(){if(trace_fd>=0)close(trace_fd);}
  FixtureConfig config;
  std::vector<std::shared_ptr<State>> states;
  int trace_fd=-1;
  bool stopping=false,quit_requested=false;
  struct Replacement {uint64_t old_generation;int width,height;};
  std::map<uint64_t,Replacement> replacements;
  uint64_t heartbeat_count=0,heartbeat_last_ns=0,heartbeat_max_gap_ns=0;
  uint64_t started_ns=MonotonicNs();
  void Trace(const char* phase){
    if(trace_fd<0)return;
    const std::string line="{\"phase\":\""+std::string(phase)+"\",\"observed_ns\":"+std::to_string(MonotonicNs())+"}\n";
    (void)write(trace_fd,line.data(),line.size());
  }
  std::shared_ptr<State> Current(uint64_t instance){
    for(auto it=states.rbegin();it!=states.rend();++it)if((*it)->instance==instance)return *it;return nullptr;
  }
  std::shared_ptr<State> Create(uint64_t instance,uint64_t generation,int width=0,int height=0){
    if(stopping||states.size()>=32||instance<1||instance>5||generation<1||generation>motive_bridge::SafeInteger)return nullptr;
    for(const auto& previous:states)if(previous->instance==instance&&(!previous->closed||generation<=previous->config.generation)){Trace("duplicate_instance_rejected");return nullptr;}
    auto options=config;options.generation=generation;
    if(width||height){if(!motive_multi::ValidGeometry(width,height))return nullptr;options.width=width;options.height=height;}
    if(config.multi){options.private_root=config.private_root+"/instance-"+std::to_string(instance)+"-g"+std::to_string(generation)+"-e1";if(mkdir(options.private_root.c_str(),0700))return nullptr;}
    auto s=std::make_shared<State>(options,instance);s->host=shared_from_this();
    s->animated=config.scenario!="static"&&(config.scenario!="mixed"||instance==1);
    s->crash_allowed=config.multi&&(config.scenario=="crash"||config.scenario=="lifecycle"||config.scenario=="cold-lifecycle"||config.scenario=="cold-cycles"||config.scenario=="widget-lifecycle"||config.scenario=="widget-soak"||config.scenario=="goal-lifecycle");
#ifdef MOTIVE_WIDGET_FIXTURES
    s->widget_kind=config.scenario=="lower-third"?1:config.scenario=="community-alert"?2:int((instance-1)%3)+1;
    s->animated=s->widget_kind!=3;
#endif
    s->used_dimensions.emplace(options.width,options.height);
    if(!s->mailbox||s->trace_fd<0||!s->StartConsumer())return nullptr;
#ifdef MOTIVE_GOAL_BRIDGE
    if(!s->goal)return nullptr;
#endif
    states.push_back(s);
    CefWindowInfo window;window.SetAsWindowless(0);window.shared_texture_enabled=false;
    CefBrowserSettings settings;settings.windowless_frame_rate=config.fps;settings.background_color=0;
    CefRequestContextSettings context_settings;context_settings.cookieable_schemes_exclude_defaults=true;
    s->context=CefRequestContext::CreateContext(context_settings,nullptr);
    if(!s->context){s->failed=true;s->CloseAll();return s;}
    s->pending_creates=1;
    CefRefPtr<CefDictionaryValue> extra;
#ifdef MOTIVE_GOAL_BRIDGE
    extra=CefDictionaryValue::Create();extra->SetDouble("instance",double(instance));extra->SetDouble("generation",double(generation));extra->SetString("entry",s->entry);extra->SetDouble("clock_origin_ms",double(s->clock_origin_ms));
#ifdef MOTIVE_MULTI_BROWSER
    extra->SetBool("allow_crash",s->crash_allowed);
#endif
#elif defined(MOTIVE_MULTI_BROWSER)
    extra=CefDictionaryValue::Create();extra->SetDouble("instance",double(instance));extra->SetDouble("generation",double(generation));extra->SetString("entry",s->entry);extra->SetBool("animated",s->animated);extra->SetBool("allow_crash",s->crash_allowed);extra->SetBool("slow",config.scenario=="slow"&&instance==1);
#ifdef MOTIVE_WIDGET_FIXTURES
    extra->SetInt("widget_kind",s->widget_kind);
#endif
#elif defined(MOTIVE_DIAGNOSTIC_MODE)
    extra=CefDictionaryValue::Create();extra->SetDouble("generation",double(generation));extra->SetString("entry",s->entry);extra->SetInt("mode",MOTIVE_DIAGNOSTIC_MODE);
#endif
    if(config.scenario=="security"){
      const auto decoy=config.private_root+"/sandbox-decoy";
      errno=0;const int fd=open(decoy.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);s->browser_decoy_opened=fd>=0;s->browser_decoy_errno=fd<0?errno:0;if(fd>=0)close(fd);
      if(extra)extra->SetString("decoy_path",decoy);
    }
    s->Trace("create_requested");
    if(!CefBrowserHost::CreateBrowser(window,new Client(s,true),s->entry,settings,extra,s->context)){s->pending_creates=0;s->failed=true;s->closed=true;s->CloseAll();return s;}
    return s;
  }
  void MaybeQuit(){
    if(!config.multi&&!states.empty()&&states.front()->stopping)stopping=true;
    if(!stopping||quit_requested)return;
    for(const auto& s:states)if(!s->browsers.empty()||s->pending_creates)return;
    quit_requested=true;Trace("quit_requested_once");CefQuitMessageLoop();Trace("quit_request_returned");
  }
  void RendererFailed(const std::shared_ptr<State>& origin,int status,int exit_code){
    for(const auto& state:states){
      if(state->closed||state->stopping)continue;
      // PID is a trusted native diagnostic matched to supervisor identities.
      // An unknown mapping is conservatively in the host failure domain.
      if(state!=origin&&!motive_multi::SharedFailureDomain(origin->renderer_pid,state->renderer_pid))continue;
      state->failed=true;state->health="failed";state->last_renderer_status=status;state->last_renderer_exit_code=exit_code;
      if(state->mailbox)motive_frames_revoke_reason(state->mailbox,1);
      state->Trace(state==origin?"frame_generation_revoked":"shared_renderer_generation_revoked");
      CefPostTask(TID_UI,new Later([state](){state->Trace("renderer_error_close_task");state->CloseAll();}));
    }
  }
  void CloseAll(){if(stopping)return;stopping=true;Trace("close_requested");for(const auto& s:states)s->CloseAll();MaybeQuit();}
  void Schedule(int delay,std::function<void(std::shared_ptr<Host>)> fn){auto self=shared_from_this();CefPostDelayedTask(TID_UI,new Later([self,fn](){if(!self->stopping)fn(self);}),delay);}
  void Visibility(uint64_t instance,bool hidden){
    auto s=Current(instance);if(!s||s->stopping)return;
#ifdef MOTIVE_GOAL_BRIDGE
    for(auto& [id,b]:s->browsers)if(!GoalVisibilityCommand(s,b->GetMainFrame(),hidden)){s->failed=true;s->health="visibility_failed";s->CloseAll();break;}
#elif defined(MOTIVE_WIDGET_FIXTURES)
    if((hidden&&s->visibility_stage!=0&&s->visibility_stage!=4)||(!hidden&&s->visibility_stage!=2)){s->Trace("visibility_transition_rejected");return;}
    s->visibility_stage=hidden?1:3;s->Trace(hidden?"hidden_cancel_dispatched":"hidden_resume_dispatched");
    for(auto& [id,b]:s->browsers)b->GetMainFrame()->SendProcessMessage(PID_RENDERER,CefProcessMessage::Create(hidden?"motive.h22.cancel":"motive.h22.resume"));
    const auto stage=s->visibility_stage;
    Schedule(1000,[s,stage](auto){if(!s->stopping&&s->visibility_stage==stage){s->failed=true;s->health="visibility_timeout";s->CloseAll();}});
#else
    s->hidden=hidden;s->Trace(hidden?"hidden_begin":"hidden_end");
    for(auto& [id,b]:s->browsers){b->GetHost()->WasHidden(hidden);if(!hidden)b->GetHost()->Invalidate(PET_VIEW);}
#endif
  }
  void Close(uint64_t instance,const char* reason){auto s=Current(instance);if(s&&!s->stopping){s->Trace(reason);s->CloseAll();}}
  void Recreate(uint64_t instance){auto s=Current(instance);if(!s||!s->closed){Trace("recreate_before_final_close_rejected");return;}Create(instance,s->config.generation+1);}
  void Replace(uint64_t instance,int width,int height,const char* reason){
    auto s=Current(instance);
    if(!s||s->stopping||replacements.contains(instance)||!motive_multi::ValidGeometry(width,height)||!motive_multi::GenerationWithRestartHeadroom(s->config.generation)){Trace("cold_replacement_rejected");return;}
    replacements.emplace(instance,Replacement{s->config.generation,width,height});
    s->Trace(reason);s->Trace("cold_replacement_requested");
    // Revoke visual authority immediately; final close and lease release are
    // separate barriers. Never relabel an old OnPaint with a new generation.
    if(s->mailbox)motive_frames_revoke_reason(s->mailbox,1);
    s->CloseAll();
  }
  void ReplacementReady(uint64_t instance,uint64_t generation){
    auto it=replacements.find(instance);if(it==replacements.end()||it->second.old_generation!=generation)return;
    auto self=shared_from_this();
    // No CreateBrowser inside OnBeforeClose: let CEF unwind its callback first.
    CefPostTask(TID_UI,new Later([self,instance,generation](){
      auto it=self->replacements.find(instance);if(it==self->replacements.end()||it->second.old_generation!=generation)return;
      const auto replacement=it->second;self->replacements.erase(it);
      auto old=self->Current(instance);
      if(self->stopping)return;
      if(!old||old->config.generation!=generation||!old->closed||old->pending_creates||!old->browsers.empty()||old->context||old->mailbox||old->consumer||!old->frames_written){self->Trace("cold_replacement_barrier_failed");self->CloseAll();return;}
      old->Trace("cold_replacement_barrier_passed");
      if(!self->Create(instance,generation+1,replacement.width,replacement.height)){self->Trace("cold_replacement_create_failed");self->CloseAll();}
    }));
  }
  void Heartbeat(){
    const auto now=MonotonicNs();if(heartbeat_last_ns)heartbeat_max_gap_ns=std::max(heartbeat_max_gap_ns,now-heartbeat_last_ns);
    heartbeat_last_ns=now;++heartbeat_count;Trace("ui_heartbeat");
    Schedule(50,[](auto h){h->Heartbeat();});
  }
  void Crash(uint64_t instance){auto s=Current(instance);if(!s||s->stopping||!s->crash_allowed)return;s->Trace("renderer_exit_requested");for(auto& [id,b]:s->browsers)b->GetMainFrame()->SendProcessMessage(PID_RENDERER,CefProcessMessage::Create("motive.h19.exit"));}
  void Event(uint64_t instance){
    auto s=Current(instance);if(!s||s->stopping||s->hidden)return;
#ifdef MOTIVE_GOAL_BRIDGE
    std::array<uint8_t,16384> output{};const uint64_t now=MonotonicNs()/1000000-s->clock_origin_ms;
    const auto count=motive_goal_control(s->goal,5,now,output.data(),output.size());
    if(count<=0){s->Trace(count==0?"fixture_goal_not_ready":"fixture_goal_failed");return;}
    s->Trace("fixture_goal_dispatched");
    for(auto& [id,b]:s->browsers){auto m=CefProcessMessage::Create(motive_bridge::DispatchMessage);m->GetArgumentList()->SetString(0,std::string(reinterpret_cast<const char*>(output.data()),size_t(count)));m->GetArgumentList()->SetDouble(1,double(now));b->GetMainFrame()->SendProcessMessage(PID_RENDERER,m);}
#else
    s->Trace("fixture_event_dispatched");for(auto& [id,b]:s->browsers)b->GetMainFrame()->SendProcessMessage(PID_RENDERER,CefProcessMessage::Create("motive.h19.event"));
#endif
  }
  void Scenario(){
    if(!config.multi)return;
    if(config.scenario.starts_with("cold-"))Heartbeat();
    if(config.scenario.starts_with("widget-")||config.scenario=="lower-third"||config.scenario=="community-alert"||config.scenario.starts_with("goal-")){
      Heartbeat();
      for(int at=2000;at<config.duration_ms-5000;at+=6000)Schedule(at,[](auto h){for(uint64_t i=1;i<=uint64_t(h->config.instances);++i)h->Event(i);});
      if(config.scenario=="widget-lifecycle"||config.scenario=="goal-lifecycle"){
        Schedule(2500,[](auto h){h->Close(3,"remove_requested");});Schedule(8500,[](auto h){h->Recreate(3);});
        Schedule(14500,[](auto h){h->Visibility(3,true);});Schedule(20500,[](auto h){h->Visibility(3,false);});
        Schedule(26500,[](auto h){h->Replace(3,540,960,"geometry_change_requested");});
        Schedule(32500,[](auto h){h->Crash(3);});Schedule(38500,[](auto h){h->Recreate(3);});
      }else if(config.scenario=="widget-soak"){
        for(int cycle=0;cycle<7;++cycle){const int at=2500+cycle*60000;
          Schedule(at,[](auto h){h->Replace(3,540,960,"geometry_change_requested");});
          Schedule(at+6000,[](auto h){h->Replace(3,640,360,"geometry_change_requested");});
          Schedule(at+12000,[](auto h){h->Visibility(3,true);});Schedule(at+18000,[](auto h){h->Visibility(3,false);});
          Schedule(at+24000,[](auto h){h->Close(3,"restart_requested");});Schedule(at+30000,[](auto h){h->Recreate(3);});
          Schedule(at+36000,[](auto h){h->Crash(3);});Schedule(at+42000,[](auto h){h->Recreate(3);});
        }
      }
      return;
    }
    if(config.scenario=="cold-resize"){
      Schedule(3000,[](auto h){h->Replace(1,540,960,"geometry_change_requested");});
      Schedule(7000,[](auto h){h->Replace(1,640,360,"geometry_change_requested");});
    }else if(config.scenario=="cold-cycles"){
      // Two unaffected animated peers throughout; <=27 creation records. The
      // closed inventory/history cap remains finite and is never silently reset.
      for(int cycle=0;cycle<8;++cycle){
        const int at=10000+cycle*65000;
        Schedule(at,[](auto h){h->Replace(3,540,960,"geometry_change_requested");});
        Schedule(at+5000,[](auto h){h->Replace(3,640,360,"geometry_change_requested");});
        Schedule(at+10000,[](auto h){h->Visibility(3,true);});
        Schedule(at+12000,[](auto h){h->Visibility(3,false);});
        Schedule(at+15000,[](auto h){h->Close(3,"restart_requested");});
        Schedule(at+17000,[](auto h){h->Recreate(3);});
        Schedule(at+22000,[](auto h){h->Event(3);});
      }
    }else if(config.scenario=="lifecycle"||config.scenario=="cold-lifecycle"){
      Schedule(3000,[](auto h){h->Close(2,"remove_requested");});
      Schedule(5000,[](auto h){h->Create(4,h->config.generation);});
      Schedule(7000,[](auto h){h->Visibility(1,true);});
      Schedule(9000,[](auto h){if(h->config.scenario=="cold-lifecycle")h->Replace(3,540,960,"geometry_change_requested");else {auto s=h->Current(3);if(s&&!s->stopping)s->Resize(540,960);}});
      Schedule(11000,[](auto h){h->Visibility(1,false);});
      Schedule(13000,[](auto h){h->Close(4,"restart_requested");});
      Schedule(15000,[](auto h){h->Recreate(4);});
      Schedule(17000,[](auto h){h->Crash(3);});
      Schedule(19000,[](auto h){h->Recreate(3);});
      Schedule(21000,[](auto h){h->Close(1,"suspend_requested");});
      Schedule(23000,[](auto h){h->Recreate(1);});
    }else if(config.scenario=="hidden"){
#ifdef MOTIVE_GOAL_BRIDGE
      Schedule(800,[](auto h){h->Visibility(1,true);});Schedule(3000,[](auto h){h->Visibility(1,false);});
#else
      Schedule(3000,[](auto h){h->Visibility(1,true);});Schedule(7000,[](auto h){h->Visibility(1,false);});
#endif
    }else if(config.scenario=="resize"){
      Schedule(3000,[](auto h){auto s=h->Current(1);if(s&&!s->stopping)s->Resize(540,960);});
    }else if(config.scenario=="crash"){
      Schedule(3000,[](auto h){h->Crash(1);});Schedule(5000,[](auto h){h->Recreate(1);});
    }else if(config.scenario=="events"){
      for(int i=0;i<24;++i)Schedule(2000+i*100,[](auto h){h->Event(1);});
    }
  }
  bool WriteReport(){
    if(!config.multi)return true;
    const int fd=open((config.private_root+"/instances.json").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return false;
    std::string json="{\"native_executed\":true,\"host_pid\":"+std::to_string(getpid())+",\"started_ns\":"+std::to_string(started_ns)+",\"configured_widgets\":"+std::to_string(config.instances)+",\"scenario\":\""+config.scenario+"\",\"test_keychain_backend\":";
#ifdef MOTIVE_EPHEMERAL_KEYCHAIN
    json+="true";
#else
    json+="false";
#endif
    json+=",\"third_party_execution\":false,\"ui_heartbeat_count\":"+std::to_string(heartbeat_count)+",\"ui_heartbeat_max_gap_ns\":"+std::to_string(heartbeat_max_gap_ns)+",\"instances\":[";
    bool first=true;for(const auto& s:states){if(!first)json+=',';first=false;
      json+="{\"instance\":"+std::to_string(s->instance)+",\"generation\":"+std::to_string(s->config.generation)+",\"epoch\":"+std::to_string(s->epoch)+",\"browser_id\":"+std::to_string(s->browser_id)+",\"renderer_pid_reported\":"+std::to_string(s->renderer_pid)+",\"origin\":\""+s->origin+"\",\"request_context\":\"distinct_in_memory\",\"package\":\"compiled_owned_inventory\",\"inventory_entries\":"+std::to_string(s->inventory.size())+",\"width\":"+std::to_string(s->config.width)+",\"height\":"+std::to_string(s->config.height)+",\"created_ns\":"+std::to_string(s->created_ns)+",\"first_paint_ns\":"+std::to_string(s->first_paint_ns)+",\"first_nontransparent_paint_ns\":"+std::to_string(s->first_useful_paint_ns)+",\"closed_ns\":"+std::to_string(s->closed_ns)+",\"frames_written\":"+(s->frames_written?"true":"false")+",\"closed\":"+(s->closed?"true":"false")+",\"failed\":"+(s->failed?"true":"false")+",\"health\":\""+s->health+"\",\"blocked_resources\":"+std::to_string(s->blocked_resources)+",\"blocked_navigation\":"+std::to_string(s->blocked_navigation)+",\"renderer_decoy_observed\":"+(s->renderer_decoy_observed?"true":"false")+",\"renderer_decoy_opened\":"+(s->renderer_decoy_opened?"true":"false")+",\"renderer_decoy_errno\":"+std::to_string(s->renderer_decoy_errno)+",\"browser_decoy_opened\":"+(s->browser_decoy_opened?"true":"false")+",\"browser_decoy_errno\":"+std::to_string(s->browser_decoy_errno)+",\"blocked_popups\":"+std::to_string(s->blocked_popups)+",\"blocked_downloads\":"+std::to_string(s->blocked_downloads)+",\"blocked_permissions\":"+std::to_string(s->blocked_permissions)+",\"events_received\":"+std::to_string(s->events_received)+",\"renderer_termination_status\":"+std::to_string(s->last_renderer_status)+",\"renderer_exit_code\":"+std::to_string(s->last_renderer_exit_code)+",\"renderer_decoded_exit_code\":"+std::to_string(s->failed?motive_diagnostic::PosixExitCode(s->last_renderer_exit_code):-1)+",\"security_phases\":[";
      bool comma=false;for(int phase:s->security_phases){if(comma)json+=',';comma=true;json+=std::to_string(phase);}json+="],\"epochs\":[";comma=false;for(const auto& record:s->epoch_records){if(comma)json+=',';comma=true;json+=record;}json+="]}";
    }json+="]}\n";const bool ok=write(fd,json.data(),json.size())==ssize_t(json.size());close(fd);return ok;
  }
};
void State::HostMaybeQuit(){if(auto h=host.lock())h->MaybeQuit();}
void State::ReplacementReady(){if(auto h=host.lock())h->ReplacementReady(instance,config.generation);}
void State::RendererFailed(int status,int exit_code){if(auto h=host.lock()){auto current=h->Current(instance);if(current.get()==this)h->RendererFailed(current,status,exit_code);}}
bool State::StartConsumer(){
  consumer=std::make_unique<FrameConsumer>(mailbox,config.private_root
#if defined(MOTIVE_GOAL_BRIDGE) || defined(MOTIVE_WIDGET_FIXTURES)
    ,&visual_capture_after_ns,config.scenario=="slow-consumer"?100:0
#elif defined(MOTIVE_DIAGNOSTIC_MODE) && MOTIVE_DIAGNOSTIC_MODE == 5
    ,nullptr,100
#else
    ,nullptr,config.scenario=="slow-consumer"?100:0
#endif
  );return consumer->valid();
}
void State::FinishFrames(){
  if(frame_finalized)return;frame_finalized=true;
  if(mailbox)motive_frames_revoke(mailbox);
  if(consumer){Trace("consumer_join_enter");consumer->Stop();Trace("consumer_joined");Trace("frame_report_enter");frames_written=consumer->WriteReport(callbacks,busy,invalid,max_publish_ns);consumer.reset();}
  Trace(frames_written?"frame_report_written":"frame_report_failed");
  CaptureEpoch(false,frames_written);
  motive_frames_destroy(mailbox);mailbox=nullptr;
#ifdef MOTIVE_GOAL_BRIDGE
  motive_goal_destroy(goal);goal=nullptr;
#endif
}
void State::CaptureEpoch(bool resize,bool written){
  MotiveFrameStatisticsV2 stats{};const bool got=mailbox&&motive_frames_stats_v2(mailbox,&stats);
  epoch_records.push_back("{\"epoch\":"+std::to_string(epoch)+",\"width\":"+std::to_string(config.width)+",\"height\":"+std::to_string(config.height)+",\"started_ns\":"+std::to_string(epoch_started_ns)+",\"first_paint_ns\":"+std::to_string(first_paint_ns)+",\"first_nontransparent_paint_ns\":"+std::to_string(first_useful_paint_ns)+",\"ended_ns\":"+std::to_string(MonotonicNs())+",\"revocation\":\""+(resize?"epoch":"close")+"\",\"frames_written\":"+(written?"true":"false")+",\"accounting_observed\":"+(got?"true":"false")+",\"pending_after_revoke\":"+std::to_string(stats.pending)+",\"leased_after_join\":"+std::to_string(stats.leased)+",\"retained_bytes_after_join\":"+std::to_string(stats.retained_bytes)+"}");
}
void State::Resize(int width,int height){
  if(stopping||!config.multi||!motive_multi::UnusedGeometry(used_dimensions,width,height)){Trace("resize_requires_cold_replacement");return;}
  Trace("resize_requested");
  // Never reuse geometry in a browser generation: a late paint cannot be
  // relabelled after A -> B -> A. That case requires cold browser replacement.
  motive_frames_revoke_reason(mailbox,1);
  consumer->Stop();const bool prior_ok=consumer->WriteReport(callbacks,busy,invalid,max_publish_ns);consumer.reset();
  CaptureEpoch(true,prior_ok);
  motive_frames_destroy(mailbox);mailbox=nullptr;
  auto h=host.lock();if(!h||!prior_ok){failed=true;CloseAll();return;}
  ++epoch;epoch_started_ns=MonotonicNs();config.width=width;config.height=height;used_dimensions.emplace(width,height);
  config.private_root=h->config.private_root+"/instance-"+std::to_string(instance)+"-g"+std::to_string(config.generation)+"-e"+std::to_string(epoch);
  if(mkdir(config.private_root.c_str(),0700)){failed=true;CloseAll();return;}
  if(trace_fd>=0)close(trace_fd);trace_fd=open((config.private_root+"/lifecycle.jsonl").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  callbacks=0;busy=0;invalid=0;max_publish_ns=0;first_paint_ns=0;first_useful_paint_ns=0;
  mailbox=motive_frames_create(instance,config.generation,epoch,width,height);
  if(!mailbox||!StartConsumer()){failed=true;CloseAll();return;}
  Trace("resize_epoch_started");for(auto& [id,b]:browsers){b->GetHost()->WasResized();b->GetHost()->Invalidate(PET_VIEW);}
}
class App final : public SchemeApp, public CefBrowserProcessHandler {
 public:
  explicit App(std::shared_ptr<Host> host):host_(std::move(host)){}
  CefRefPtr<CefBrowserProcessHandler> GetBrowserProcessHandler() override {return this;}
  CefRefPtr<CefClient> GetDefaultClient() override {return host_->states.empty()?nullptr:new Client(host_->states.front(),false);}
  void OnContextInitialized() override {
    host_->Trace("context_initialized");
    for(unsigned i=1;i<=host_->config.instances;++i)if(!host_->Create(i,host_->config.generation)){host_->CloseAll();return;}
    host_->Scenario();auto host=host_;
    CefPostDelayedTask(TID_UI,new Later([host](){host->Trace("close_task");host->CloseAll();}),host_->config.duration_ms);
  }
 private:
  std::shared_ptr<Host> host_;
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
-(void)terminate:(id)sender{(void)sender;if(auto host=h16::active_host.lock())host->CloseAll();}
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
    settings.cookieable_schemes_exclude_defaults=true;
    settings.command_line_args_disabled=true;settings.log_severity=LOGSEVERITY_DISABLE;
    CefString(&settings.root_cache_path)=config.private_root+"/cache";
    auto host=std::make_shared<h16::Host>(config);
    h16::active_host=host;
    CefRefPtr<h16::App> app=new h16::App(host);
    host->Trace("initialize_enter");
    if(!CefInitialize(args,settings,app,nullptr)){h16::active_host.reset();return 4;}
    host->Trace("initialize_return");
    CefRunMessageLoop();host->Trace("loop_return");
    bool frames_written=!host->states.empty();
    for(auto& state:host->states){
      state->FinishFrames();frames_written=frames_written&&state->frames_written;
#ifdef MOTIVE_DIAGNOSTIC_MODE
      state->WriteDiagnostic();
#endif
      state->browsers.clear();state->context=nullptr;
    }
    const bool manifest_written=host->WriteReport();
    app=nullptr;h16::active_host.reset();host->Trace("shutdown_enter");CefShutdown();host->Trace("shutdown_return");
#ifdef MOTIVE_GOAL_BRIDGE
    if(config.multi&&config.scenario=="hidden"){auto state=host->Current(1);if(!state||state->visibility_stage!=4)return 11;}
#endif
#ifdef MOTIVE_GOAL_CONTROLS
    for(auto& state:host->states)if(state->instance==1&&!state->controls_complete)return 10;
#endif
#ifdef MOTIVE_DIAGNOSTIC_MODE
    const auto& state=host->states.front();
    if(state->renderer_terminated)return state->crash_requested&&state->renderer_decoded_exit_code==86&&state->revocation_confirmed&&frames_written?42:43;
    if(MOTIVE_DIAGNOSTIC_MODE==4)return 44;
    if(!state->fixture_ready)return 45;
#endif
    return frames_written&&manifest_written?0:5;
  }
}
