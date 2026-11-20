// SPDX-License-Identifier: GPL-3.0-or-later
#import "probe.h"
#include "probe_config.h"
#include <fcntl.h>
#include <unistd.h>

int main(void){@autoreleasepool{
  int fd=open(H22_DECOY,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
  if(fd<0)return 71;
  NSFileHandle* capability=[[NSFileHandle alloc]initWithFileDescriptor:fd closeOnDealloc:YES];
  NSXPCConnection* connection=[[NSXPCConnection alloc]initWithServiceName:@"org.motive.lab.h22.boundary"];
  connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(H22Probe)];
  dispatch_semaphore_t done=dispatch_semaphore_create(0);
  __block NSDictionary* result=nil;
  [connection resume];
  id<H22Probe> proxy=[connection remoteObjectProxyWithErrorHandler:^(NSError* error){
    // Only typed error code/domain: no raw userInfo or paths from an OS service.
    result=@{@"xpc_error_code":@(error.code),@"xpc_error_domain":error.domain};dispatch_semaphore_signal(done);
  }];
  [proxy probe:capability reply:^(NSDictionary* response){result=response;dispatch_semaphore_signal(done);}];
  long timedOut=dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC));
  [connection invalidate];[capability closeFile];
  if(timedOut)return 72;
  NSData* data=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:nil];
  if(!data||data.length>4096)return 73;
  write(STDOUT_FILENO,data.bytes,data.length);write(STDOUT_FILENO,"\n",1);
  return result[@"xpc_error_code"]?74:0;
}}
