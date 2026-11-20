// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#ifdef MOTIVE_ROLE_PROBE
#include "h22_role_probe_config.h"
#include <arpa/inet.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

inline void H22RoleProbe(int argc,char** argv,bool helper) {
  const char* role=helper?"unknown_helper":"browser_host";
  bool seatbelt_argument=false;
  for(int i=1;i<argc;++i){
    if(!std::strcmp(argv[i],"--type=renderer"))role="renderer";
    if(!std::strcmp(argv[i],"--type=gpu-process"))role="gpu";
    if(!std::strcmp(argv[i],"--type=utility"))role="utility";
    if(!std::strncmp(argv[i],"--seatbelt-client=",17))seatbelt_argument=true;
  }
  for(int i=1;i<argc;++i){
    if(!std::strcmp(argv[i],"--utility-sub-type=network.mojom.NetworkService"))role="network_service";
    if(!std::strcmp(argv[i],"--utility-sub-type=storage.mojom.StorageService"))role="storage_service";
  }
  errno=0;const int fd=open(H22_ROLE_DECOY,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
  const int file_error=fd<0?errno:0;if(fd>=0)close(fd);
  int endpoint_error=0;bool connected=false;
  const int s=socket(AF_INET,SOCK_STREAM,0);
  if(s<0)endpoint_error=errno;
  else {
    fcntl(s,F_SETFL,O_NONBLOCK);sockaddr_in address{};
    address.sin_len=sizeof(address);address.sin_family=AF_INET;address.sin_port=htons(18719);
    inet_pton(AF_INET,"127.0.0.1",&address.sin_addr);
    const int result=connect(s,reinterpret_cast<const sockaddr*>(&address),sizeof(address));
    if(result==0)connected=true;
    else if(errno==EINPROGRESS){
      pollfd pending{s,POLLOUT,0};const int ready=poll(&pending,1,100);
      socklen_t size=sizeof(endpoint_error);
      if(ready>0&&getsockopt(s,SOL_SOCKET,SO_ERROR,&endpoint_error,&size)==0)connected=endpoint_error==0;
      else endpoint_error=ready==0?ETIMEDOUT:errno;
    }else endpoint_error=errno;
    close(s);
  }
  // Atomic short record to the supervisor's owned stream. No path, command
  // line, payload, environment, credential or unbounded diagnostic text.
  char record[384];const int n=snprintf(record,sizeof(record),
    "H22_BOUNDARY {\"pid\":%d,\"role\":\"%s\",\"after_cef_sandbox_initialize\":%s,\"seatbelt_argument\":%s,\"file_opened\":%s,\"file_errno\":%d,\"loopback_connected\":%s,\"loopback_errno\":%d}\n",
    getpid(),role,helper?"true":"false",seatbelt_argument?"true":"false",fd>=0?"true":"false",file_error,connected?"true":"false",endpoint_error);
  if(n>0&&size_t(n)<sizeof(record))(void)write(STDERR_FILENO,record,size_t(n));
}
#endif
