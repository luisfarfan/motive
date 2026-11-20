// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "bridge_policy.hpp"
#include <sys/wait.h>
namespace motive_diagnostic {
inline int PosixExitCode(int status){return WIFEXITED(status)?WEXITSTATUS(status):-1;}
constexpr const char* PhaseMessage="motive.fixture.phase.v1";
constexpr const char* ExitMessage="motive.fixture.controlled-exit.v1";
// Fixed source-owned phases, not free-form renderer diagnostics.
inline bool PhaseAllowed(int mode,int phase){
 return phase==1||(mode==1&&phase==2)||(mode==2&&(phase==3||phase==4))||(mode==3&&(phase==5||phase==6));
}
inline bool ExitAllowed(int mode,bool requested_by_browser,bool main_frame,bool exact_identity,size_t args){
 return mode==4&&requested_by_browser&&main_frame&&exact_identity&&args==0;
}
}
