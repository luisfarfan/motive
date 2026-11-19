// Fixed diagnostic boundary test; no CEF linkage, initialization or renderer.
#include "../poc/browser-host/native/diagnostic_policy.hpp"
#include <cassert>
#include <cstdio>
int main(){
 assert(motive_diagnostic::PosixExitCode(86<<8)==86);
 assert(motive_diagnostic::PosixExitCode(9)==-1);
 for(int mode=1;mode<=5;++mode){
  assert(motive_diagnostic::PhaseAllowed(mode,1));
  assert(!motive_diagnostic::PhaseAllowed(mode,0));assert(!motive_diagnostic::PhaseAllowed(mode,99));
  assert(motive_diagnostic::PhaseAllowed(mode,2)==(mode==1));
  assert(motive_diagnostic::PhaseAllowed(mode,5)==(mode==3));
  assert(motive_diagnostic::ExitAllowed(mode,true,true,true,0)==(mode==4));
 }
 assert(!motive_diagnostic::ExitAllowed(4,false,true,true,0));
 assert(!motive_diagnostic::ExitAllowed(4,true,false,true,0));
 assert(!motive_diagnostic::ExitAllowed(4,true,true,false,0));
 assert(!motive_diagnostic::ExitAllowed(4,true,true,true,1));
 std::puts("PASS fixed diagnostic phase/crash boundary; no CEF linked or executed");
}
