// SPDX-License-Identifier: GPL-3.0-or-later
#include "fixture.hpp"
#include "multi_policy.hpp"
#include <charconv>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <crt_externs.h>
#include <vector>
#include <filesystem>
#include <sys/stat.h>
#include <unistd.h>

// This executable is NOT launched by build/test. Native browser execution needs
// the specific owner policy exception described in docs/h18-native-host.md.
int main(int argc,char** argv) {
  const bool multi=argc==10&&std::strcmp(argv[1],"--owned-multi")==0;
  if(!multi&&(argc!=8||std::strcmp(argv[1],"--owned-fixture")!=0)){std::fprintf(stderr,"OWNED_FIXTURE_ARGUMENTS_REQUIRED\n");return 64;}
  FixtureConfig c;c.private_root=argv[2];c.multi=multi;
  auto number=[](const char* text,auto& value){const char* end=text+std::strlen(text);auto r=std::from_chars(text,end,value);return r.ec==std::errc{}&&r.ptr==end;};
  if(!number(argv[3],c.generation)||!number(argv[4],c.width)||!number(argv[5],c.height)||!number(argv[6],c.fps)||!number(argv[7],c.duration_ms))return 65;
  if(multi){
#ifndef MOTIVE_MULTI_BROWSER
    return 64;
#endif
    if(!number(argv[8],c.instances)||(c.instances!=1&&c.instances!=3&&c.instances!=5))return 65;
    c.scenario=argv[9];
    const std::vector<std::string> scenarios={"steady","static","mixed","hidden","resize","crash","lifecycle","events","slow","goal","security","slow-consumer"};
    if(std::find(scenarios.begin(),scenarios.end(),c.scenario)==scenarios.end())return 65;
    if(c.scenario=="lifecycle"&&(c.instances!=3||c.duration_ms<25000))return 65;
  }
  const bool viewport=(c.width==640&&c.height==360)||(c.width==960&&c.height==540)||(c.width==540&&c.height==960);
  if(!motive_multi::GenerationWithRestartHeadroom(c.generation)||!viewport||(c.fps!=30&&c.fps!=60)||c.duration_ms<1000||c.duration_ms>(multi?600000:15000))return 65;
  // The trusted supervisor supplies a fresh private directory. Refuse aliases,
  // shared permissions, foreign owners and preexisting output/cache paths.
  struct stat st{};
  std::error_code ec;
  const auto canonical=std::filesystem::canonical(c.private_root,ec);
  if(ec||canonical.string()!=c.private_root||lstat(c.private_root.c_str(),&st)||!S_ISDIR(st.st_mode)||st.st_uid!=getuid()||(st.st_mode&077)!=0)return 66;
  if(mkdir((c.private_root+"/cache").c_str(),0700))return 66;
  // A direct invocation must not forward shell credentials to Chromium either.
  // This removes environment data; it is not HOME/Keychain/filesystem confinement.
  std::vector<std::string> environment_names;
  for(char** e=*_NSGetEnviron();e&&*e;++e){const char* equal=std::strchr(*e,'=');if(equal)environment_names.emplace_back(*e,size_t(equal-*e));}
  for(const auto& name:environment_names)if(unsetenv(name.c_str()))return 67;
  if(setenv("PATH","/usr/bin:/bin:/usr/sbin:/sbin",1)||setenv("TMPDIR",c.private_root.c_str(),1)||setenv("LANG","C",1))return 67;
  return RunOwnedFixture(c,argc,argv);
}
