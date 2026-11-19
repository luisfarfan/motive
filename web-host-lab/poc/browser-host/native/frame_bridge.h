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
struct MotiveFrameStatisticsV2 {
  uint64_t paints,coalesced,acquired,stale,pending,leased,consumed,released_unconsumed;
  uint64_t invalidated_close,revoked_generation,retained_leases,retained_bytes;
  uint64_t copied_bytes,copy_ns,publish_busy,acquire_busy,consumer_busy;
};
static_assert(sizeof(MotiveFrameMetadata)==72);
static_assert(sizeof(MotiveFrameStatisticsV2)==136);
extern "C" {
MotiveFrameBridge* motive_frames_create(uint64_t,uint64_t,uint64_t,uint32_t,uint32_t);
bool motive_frames_live(const MotiveFrameBridge*);
int32_t motive_frames_publish(const MotiveFrameBridge*,uint64_t,uint64_t,uint64_t,const uint8_t*,size_t);
MotiveFrameLease* motive_frames_acquire(const MotiveFrameBridge*,uint64_t,uint64_t,MotiveFrameMetadata*,const uint8_t**);
bool motive_frames_lease_valid(const MotiveFrameLease*);
bool motive_frames_complete(MotiveFrameLease*);
void motive_frames_release(MotiveFrameLease*);
bool motive_frames_stats(const MotiveFrameBridge*,MotiveFrameStatistics*);
bool motive_frames_stats_v2(const MotiveFrameBridge*,MotiveFrameStatisticsV2*);
bool motive_frames_revoke_reason(const MotiveFrameBridge*,uint32_t);
void motive_frames_revoke(const MotiveFrameBridge*);
void motive_frames_destroy(MotiveFrameBridge*);
}
