// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
struct MotiveFrameBridge;
struct MotiveFrameLease;
struct MotiveFrameMetadata {
  uint64_t instance,generation,epoch,index,observed_ns;
  uint32_t width,height,stride,bgra8,alpha_mode,reserved;
  uint64_t length;
};
struct MotiveFrameStatistics { uint64_t paints,coalesced,acquired,stale; };
static_assert(sizeof(MotiveFrameMetadata)==72);
extern "C" {
MotiveFrameBridge* motive_frames_create(uint64_t,uint64_t,uint64_t,uint32_t,uint32_t);
int32_t motive_frames_publish(const MotiveFrameBridge*,uint64_t,uint64_t,uint64_t,const uint8_t*,size_t);
MotiveFrameLease* motive_frames_acquire(const MotiveFrameBridge*,uint64_t,uint64_t,MotiveFrameMetadata*,const uint8_t**);
bool motive_frames_lease_valid(const MotiveFrameLease*);
void motive_frames_release(MotiveFrameLease*);
bool motive_frames_stats(const MotiveFrameBridge*,MotiveFrameStatistics*);
void motive_frames_revoke(const MotiveFrameBridge*);
void motive_frames_destroy(MotiveFrameBridge*);
}
