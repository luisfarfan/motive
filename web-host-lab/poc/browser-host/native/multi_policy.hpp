// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "bridge_policy.hpp"
#include <set>
#include <utility>
namespace motive_multi {
inline bool SharedFailureDomain(int observed_origin_pid,int observed_peer_pid){
  return observed_origin_pid<=0||observed_peer_pid<=0||observed_origin_pid==observed_peer_pid;
}
inline bool GenerationWithRestartHeadroom(uint64_t generation){
  return generation>0&&generation<=motive_bridge::SafeInteger-1000;
}
inline bool ValidGeometry(int width,int height){
  return (width==640&&height==360)||(width==960&&height==540)||(width==540&&height==960);
}
inline bool UnusedGeometry(const std::set<std::pair<int,int>>& used,int width,int height){
  return ValidGeometry(width,height)&&!used.contains({width,height});
}
}
