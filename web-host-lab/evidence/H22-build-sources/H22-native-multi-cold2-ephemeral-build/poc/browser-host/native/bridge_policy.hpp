// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
namespace motive_bridge {
constexpr uint64_t SafeInteger=9007199254740991ULL;
constexpr const char* StatusMessage="motive.visual.status.v1";
constexpr const char* InitializeMessage="motive.visual.initialize.v1";
constexpr const char* DispatchMessage="motive.visual.dispatch.v1";
struct Identity { uint64_t instance,generation;int browser;std::string entry; };
inline bool Fresh(uint64_t expires,uint64_t sent,uint64_t arrival){
 return sent<=arrival&&expires>=arrival&&expires-arrival<=30000&&expires<=SafeInteger;
}
inline bool Boundary(const Identity& id,int browser,bool main_frame,bool correct_process,const std::string& url,size_t args,size_t expected_args,size_t bytes,size_t max_bytes){
 return id.instance>0&&id.generation>0&&id.instance<=SafeInteger&&id.generation<=SafeInteger&&id.browser==browser&&main_frame&&correct_process&&url==id.entry&&args==expected_args&&bytes>0&&bytes<=max_bytes;
}
}
