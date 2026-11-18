// SPDX-License-Identifier: GPL-3.0-or-later
// Executes the Rust/C++ ABI with controlled bytes. This never links or loads CEF.
#include "../poc/browser-host/native/frame_bridge.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>

int main() {
  for(uint64_t generation=1;generation<=100;++generation) {
    auto* box=motive_frames_create(1,generation,1,2,1);assert(box);
    std::array<uint8_t,8> pixels{0,0,128,128,0,0,0,0};
    assert(motive_frames_publish(box,generation,1,1,pixels.data(),pixels.size())==0);
    pixels.fill(255);
    MotiveFrameMetadata metadata{};const uint8_t* data=nullptr;
    auto* lease=motive_frames_acquire(box,1,100,&metadata,&data);assert(lease);
    assert(metadata.instance==1&&metadata.generation==generation&&metadata.epoch==1&&metadata.index==1);
    assert(metadata.width==2&&metadata.height==1&&metadata.stride==8&&metadata.length==8&&metadata.bgra8==1&&metadata.alpha_mode==0);
    assert(data[2]==128&&data[3]==128);
    for(uint64_t t=2;t<=100;++t)assert(motive_frames_publish(box,generation,1,t,pixels.data(),pixels.size())==0);
    MotiveFrameMetadata other{};const uint8_t* ignored=nullptr;
    assert(!motive_frames_acquire(box,100,100,&other,&ignored));
    MotiveFrameStatistics stats{};assert(motive_frames_stats(box,&stats));assert(stats.coalesced==98);
    motive_frames_revoke(box);assert(!motive_frames_lease_valid(lease));
    motive_frames_destroy(box);assert(data[2]==128);motive_frames_release(lease);
  }
  auto* box=motive_frames_create(1,101,1,2,1);assert(box);
  std::atomic<bool> done{false};
  std::thread producer([&](){std::array<uint8_t,8> data{};for(uint64_t n=1;n<=10000;++n){auto result=motive_frames_publish(box,101,1,n,data.data(),data.size());assert(result==0||result==1);}done=true;});
  uint64_t last=0;
  while(!done.load()){
    MotiveFrameMetadata m{};const uint8_t* p=nullptr;
    auto* lease=motive_frames_acquire(box,10000,10000,&m,&p);
    if(lease){assert(m.index>last);last=m.index;assert(motive_frames_lease_valid(lease));motive_frames_release(lease);}
  }
  producer.join();motive_frames_destroy(box);
  std::puts("PASS C++/Rust ABI, copied input, generation, lease/revocation, coalescing, 100 synthetic lifecycles, concurrent bounded producer/consumer; CEF NOT EXECUTED");
}
