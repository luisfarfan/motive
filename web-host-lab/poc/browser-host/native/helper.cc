// SPDX-License-Identifier: GPL-3.0-or-later
// Initialization ordering follows CEF's BSD-licensed process_helper_mac.cc.
#include "scheme.hpp"
#include "include/cef_sandbox_mac.h"
#include "include/wrapper/cef_library_loader.h"
// Prepared helper entry point; object compilation only. No executable is linked.
int main(int argc, char** argv) {
  CefScopedSandboxContext sandbox;
  if (!sandbox.Initialize(argc, argv)) return 1;
  CefScopedLibraryLoader library;
  if (!library.LoadInHelper()) return 2;
  CefMainArgs args(argc, argv);
  return CefExecuteProcess(args, new SchemeApp, nullptr);
}
