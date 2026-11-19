// SPDX-License-Identifier: GPL-3.0-or-later
#include "../poc/browser-host/native/multi_policy.hpp"
#include <cassert>
int main(){
  // A shared process failure revokes both capabilities; a proven distinct peer
  // survives, while an unknown mapping cannot grant independent survival.
  assert(motive_multi::SharedFailureDomain(101,101));
  assert(!motive_multi::SharedFailureDomain(101,202));
  assert(motive_multi::SharedFailureDomain(0,202));
  assert(motive_multi::SharedFailureDomain(101,0));
  assert(!motive_multi::GenerationWithRestartHeadroom(0));
  assert(motive_multi::GenerationWithRestartHeadroom(1));
  assert(motive_multi::GenerationWithRestartHeadroom(motive_bridge::SafeInteger-1000));
  assert(!motive_multi::GenerationWithRestartHeadroom(motive_bridge::SafeInteger));
  std::set<std::pair<int,int>> used{{640,360}};
  assert(motive_multi::UnusedGeometry(used,540,960));
  used.emplace(540,960);
  assert(!motive_multi::UnusedGeometry(used,640,360));
  assert(!motive_multi::UnusedGeometry(used,540,960));
  assert(!motive_multi::UnusedGeometry(used,16384,16384));
}
