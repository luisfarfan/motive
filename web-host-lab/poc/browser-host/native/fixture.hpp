// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <string>
struct FixtureConfig {
  std::string private_root;
  uint64_t generation=1;
  int width=640,height=360,fps=30;
  int duration_ms=5000;
  bool multi=false;
  unsigned instances=1;
  std::string scenario="steady";
};
int RunOwnedFixture(const FixtureConfig&, int argc, char** argv);
