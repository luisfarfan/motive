// SPDX-License-Identifier: GPL-3.0-or-later
// Initialization ordering follows CEF's BSD-licensed process_helper_mac.cc.
#include "scheme.hpp"
#include "include/cef_sandbox_mac.h"
#include "include/wrapper/cef_library_loader.h"
#include "h22_role_probe.hpp"
// Linked into each CEF role helper. Sandbox must initialize before framework load.
int main(int argc, char** argv) {
  CefScopedSandboxContext sandbox;
  if (!sandbox.Initialize(argc, argv)) return 1;
#ifdef MOTIVE_ROLE_PROBE
  H22RoleProbe(argc,argv,true);
#endif
  CefScopedLibraryLoader library;
  if (!library.LoadInHelper()) return 2;
  CefMainArgs args(argc, argv);
  return CefExecuteProcess(args, new SchemeApp, nullptr);
}
