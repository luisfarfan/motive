// SPDX-License-Identifier: GPL-3.0-or-later
// Pure boundary/FFI unit test. Does not link, initialize or load CEF.
#include "../poc/browser-host/native/bridge_policy.hpp"
#include "../poc/browser-host/native/goal_binding.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <string>
int main(){
 assert(motive_bridge::Fresh(1010,10,10));assert(!motive_bridge::Fresh(1010,10,1011));assert(!motive_bridge::Fresh(1010,11,10));
 motive_bridge::Identity id{1,7,42,"motive://i1-g7/host/index.html"};
 auto allowed=[&](int browser,bool main,bool process,const std::string& url,size_t args,size_t length){return motive_bridge::Boundary(id,browser,main,process,url,args,1,length,512);};
 assert(allowed(42,true,true,id.entry,1,25));
 assert(!allowed(43,true,true,id.entry,1,25));assert(!allowed(42,false,true,id.entry,1,25));assert(!allowed(42,true,false,id.entry,1,25));
 for(const auto& url:{"motive://i1-g6/host/index.html","motive://i1-g7/host/index.html?x=1","motive://i1-g7/widget/index.html","https://example.invalid/"})assert(!allowed(42,true,true,url,1,25));
 assert(!allowed(42,true,true,id.entry,2,25));assert(!allowed(42,true,true,id.entry,1,513));assert(!allowed(42,true,true,id.entry,1,0));
 std::array<uint8_t,64> hash;hash.fill('a');auto* binding=motive_goal_create(7,hash.data(),hash.size());assert(binding);
 std::array<uint8_t,16384> output{};
 auto send=[&](const std::string& json,uint64_t now){return motive_goal_status(binding,reinterpret_cast<const uint8_t*>(json.data()),json.size(),now,output.data(),output.size());};
 assert(send(R"({"kind":"renderer_ready","identity":{"instance":1,"generation":6},"native_terminal_outcome":false})",1)<0);
 auto n=send(R"({"kind":"renderer_ready","identity":{"instance":1,"generation":7},"native_terminal_outcome":false})",2);assert(n>0);assert(std::string(reinterpret_cast<char*>(output.data()),n).find("properties")!=std::string::npos);
 n=send(R"({"kind":"visual_ack","protocol":1,"instance":1,"generation":7,"seq":1,"accepted":true})",3);assert(n>0);const std::string goal(reinterpret_cast<char*>(output.data()),n);assert(goal.find("goal.scored")!=std::string::npos);assert(goal.find("simulation.h18")==std::string::npos);
 assert(send(R"({"kind":"visual_ack","protocol":1,"instance":1,"generation":7,"seq":1,"accepted":true})",4)<0);
 assert(send(R"({"kind":"visual_ack","protocol":1,"instance":1,"generation":7,"seq":2,"accepted":true})",5)==0);
 assert(motive_goal_control(binding,1,6,output.data(),output.size())==0);
 for(uint32_t action=2;action<=4;++action){
  assert(motive_goal_control(binding,action,7+(action-2)*2,output.data(),output.size())>0);
  const auto ack=std::string("{\"kind\":\"visual_ack\",\"protocol\":1,\"instance\":1,\"generation\":7,\"seq\":")+std::to_string(action+1)+",\"accepted\":true}";
  assert(send(ack,8+(action-2)*2)==0);
 }
 assert(motive_goal_control(binding,3,13,output.data(),output.size())<0);
 motive_goal_destroy(binding);
 std::puts("PASS pure native boundary and linked offline owner-binding FFI; no CEF transport/runtime execution");
}
