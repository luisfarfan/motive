// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "frame_bridge.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <vector>
#include <chrono>
#include <fcntl.h>
#include <fstream>
#include <string>
#include <thread>
#include <unistd.h>

inline uint64_t MonotonicNs() {
  return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}
// Two bounded disk samples plus an optional fixed visual sample; one lease.
// No queue or extra pixel copy; optional capture is a fixture observation only.
// Files live in a fresh 0700 directory owned by this launch. No package paths.
class FrameConsumer {
 public:
  FrameConsumer(MotiveFrameBridge* mailbox,const std::string& root,std::atomic<uint64_t>* visual_after=nullptr):mailbox_(mailbox),root_(root),visual_after_(visual_after) {
    dir_=open(root.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(dir_<0)return;
    first_=openat(dir_,"first.bgra",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    latest_=openat(dir_,"latest.bgra",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(first_<0||latest_<0)return;
    valid_=true;
    thread_=std::thread([this](){Run();});
  }
  ~FrameConsumer(){Stop();if(first_>=0)close(first_);if(latest_>=0)close(latest_);if(visual_>=0)close(visual_);if(dir_>=0)close(dir_);}
  bool valid()const{return valid_;}
  void Stop(){stop_.store(true);if(thread_.joinable())thread_.join();}
  bool WriteReport(uint64_t callbacks,uint64_t busy,uint64_t invalid,uint64_t max_publish_ns) {
    Stop();
    if(!seen_||failed_)return false;
    return (!visual_seen_||WriteMetadata("visual.json",visual_meta_))&&WriteMetadata("first.json",first_meta_)&&WriteMetadata("latest.json",latest_meta_)&&WriteTelemetry(callbacks,busy,invalid,max_publish_ns);
  }
 private:
  bool WritePixels(int fd,const uint8_t* bytes,size_t n) {
    size_t offset=0;
    while(offset<n){auto count=pwrite(fd,bytes+offset,n-offset,off_t(offset));if(count<0&&errno==EINTR)continue;if(count<=0)return false;offset+=size_t(count);}
    return ftruncate(fd,off_t(n))==0;
  }
  bool WriteMetadata(const char* filename,const MotiveFrameMetadata& m) {
    const int fd=openat(dir_,filename,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return false;
    // Internal integers only; no renderer-supplied diagnostics/strings are serialized.
    const std::string json="{\"native_executed\":true,\"instance\":"+std::to_string(m.instance)+",\"generation\":"+std::to_string(m.generation)+",\"epoch\":"+std::to_string(m.epoch)+",\"index\":"+std::to_string(m.index)+",\"observed_ns\":"+std::to_string(m.observed_ns)+",\"width\":"+std::to_string(m.width)+",\"height\":"+std::to_string(m.height)+",\"stride\":"+std::to_string(m.stride)+",\"bgra8\":true,\"alpha_verified\":false,\"acquired\":"+std::to_string(seen_)+",\"max_disk_consumer_ns\":"+std::to_string(max_disk_consumer_ns_)+",\"sandbox_verified\":false,\"helper_cleanup_verified\":false}\n";
    const bool ok=WritePixels(fd,reinterpret_cast<const uint8_t*>(json.data()),json.size());close(fd);return ok;
  }
  bool WriteTelemetry(uint64_t callbacks,uint64_t busy,uint64_t invalid,uint64_t max_publish_ns) {
    const int fd=openat(dir_,"frames.json",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return false;
    MotiveFrameStatistics stats{};if(!motive_frames_stats(mailbox_,&stats)){close(fd);return false;}
    std::string json="{\"native_executed\":true,\"paints\":"+std::to_string(stats.paints)+",\"coalesced\":"+std::to_string(stats.coalesced)+",\"acquired\":"+std::to_string(stats.acquired)+",\"stale\":"+std::to_string(stats.stale)+",\"samples\":[";
    for(size_t i=0;i<samples_.size();++i){const auto& sample=samples_[i];if(i)json+=',';json+="["+std::to_string(sample.index)+","+std::to_string(sample.observed)+","+std::to_string(sample.acquired)+","+std::to_string(sample.transfer)+"]";}
    json+="],\"onpaint_callbacks\":"+std::to_string(callbacks)+",\"onpaint_busy\":"+std::to_string(busy)+",\"onpaint_invalid\":"+std::to_string(invalid)+",\"max_publish_callback_ns\":"+std::to_string(max_publish_ns)+",\"samples_truncated\":"+std::string(seen_>samples_.size()?"true":"false")+"}\n";
    const bool ok=WritePixels(fd,reinterpret_cast<const uint8_t*>(json.data()),json.size());close(fd);return ok;
  }
  void Run() {
    while(!stop_.load()){
      MotiveFrameMetadata meta{};const uint8_t* pixels=nullptr;
      auto* lease=motive_frames_acquire(mailbox_,MonotonicNs(),1000000000,&meta,&pixels);
      if(lease){
        const auto start=MonotonicNs();
        bool consumed=false;
        if(motive_frames_lease_valid(lease)){
          bool ok=true;
          if(!seen_){ok=WritePixels(first_,pixels,size_t(meta.length));first_meta_=meta;}
          ok=ok&&WritePixels(latest_,pixels,size_t(meta.length));
          latest_meta_=meta;++seen_;consumed=true;
          const auto threshold=visual_after_?visual_after_->load():0;
          if(!visual_seen_&&threshold&&meta.observed_ns>=threshold){
            visual_=openat(dir_,"visual.bgra",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
            ok=ok&&visual_>=0&&WritePixels(visual_,pixels,size_t(meta.length));visual_meta_=meta;visual_seen_=true;
          }
          if(!ok)failed_=true;
        }
        motive_frames_release(lease);
        const auto transfer=MonotonicNs()-start;
        max_disk_consumer_ns_=std::max(max_disk_consumer_ns_,transfer);
        if(consumed&&samples_.size()<1024)samples_.push_back({meta.index,meta.observed_ns,start,transfer});
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
  }
  MotiveFrameBridge* mailbox_;
  std::string root_;
  std::atomic<uint64_t>* visual_after_;
  int dir_=-1,first_=-1,latest_=-1,visual_=-1;
  bool valid_=false,failed_=false,visual_seen_=false;
  std::atomic<bool> stop_{false};
  std::thread thread_;
  uint64_t seen_=0,max_disk_consumer_ns_=0;
  MotiveFrameMetadata first_meta_{},latest_meta_{},visual_meta_{};
  struct Sample {uint64_t index,observed,acquired,transfer;};
  std::vector<Sample> samples_;
};
