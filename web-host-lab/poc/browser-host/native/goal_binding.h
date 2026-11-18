// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
struct MotiveGoalBinding;
extern "C" {
MotiveGoalBinding* motive_goal_create(uint64_t,const uint8_t*,size_t);
ptrdiff_t motive_goal_status(MotiveGoalBinding*,const uint8_t*,size_t,uint64_t,uint8_t*,size_t);
void motive_goal_destroy(MotiveGoalBinding*);
}
