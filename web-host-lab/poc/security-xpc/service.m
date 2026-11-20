// SPDX-License-Identifier: GPL-3.0-or-later
// Fixed owned probes only. This service does not load CEF or call Keychain.
#import "probe.h"
#include "probe_config.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

@interface H22Service : NSObject <H22Probe,NSXPCListenerDelegate>
@property BOOL used;
@end
@implementation H22Service
- (BOOL)listener:(NSXPCListener*)listener shouldAcceptNewConnection:(NSXPCConnection*)connection {
  (void)listener;
  // launchd's private embedded-service route is used. This is not an attestation
  // of Developer ID, Team ID, a compromised renderer, or arbitrary clients.
  if(connection.effectiveUserIdentifier!=getuid())return NO;
  connection.exportedInterface=[NSXPCInterface interfaceWithProtocol:@protocol(H22Probe)];
  connection.exportedObject=self;[connection resume];return YES;
}
- (void)probe:(NSFileHandle*)capability reply:(void (^)(NSDictionary*))reply {
  @synchronized(self){if(self.used){reply(@{@"error":@"one_use"});return;}self.used=YES;}
  errno=0;int fd=open(H22_DECOY,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
  int fileError=fd<0?errno:0;if(fd>=0)close(fd);
  int socketFD=socket(AF_INET,SOCK_STREAM,0);int networkError=socketFD<0?errno:0;
  int connected=-1;
  if(socketFD>=0){
    fcntl(socketFD,F_SETFL,O_NONBLOCK);struct sockaddr_in address={0};
    address.sin_len=sizeof(address);address.sin_family=AF_INET;
    address.sin_port=htons(H22_PORT);inet_pton(AF_INET,"127.0.0.1",&address.sin_addr);
    errno=0;connected=connect(socketFD,(struct sockaddr*)&address,sizeof(address));
    networkError=connected<0?errno:0;close(socketFD);
  }
  // Descriptor capability is limited to an already-open owned file. Never
  // inspect an arbitrary path from an IPC argument and never return its bytes.
  char bytes[64]={0};ssize_t count=pread(capability.fileDescriptor,bytes,sizeof(bytes),0);
  const char expected[]="MOTIVE_H22_OWNED_CAPABILITY\n";
  BOOL capabilityOK=count==sizeof(expected)-1&&!memcmp(bytes,expected,sizeof(expected)-1);
  [capability closeFile];
  reply(@{@"pid":@(getpid()),@"direct_file_opened":@(fd>=0),@"file_errno":@(fileError),
          @"network_connect_return":@(connected),@"network_errno":@(networkError),
          @"capability_read_verified":@(capabilityOK),@"capability_bytes":@(count),
          @"cef_loaded":@NO,@"keychain_called":@NO});
  // Fixture-only explicit exit. The external observer checks the launched
  // service's identity disappearing; this is not a CEF shutdown implementation.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,1000*NSEC_PER_MSEC),dispatch_get_global_queue(0,0),^{_exit(0);});
}
@end

int main(void){@autoreleasepool{
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC),dispatch_get_global_queue(0,0),^{_exit(90);});
  H22Service* service=[H22Service new];NSXPCListener* listener=[NSXPCListener serviceListener];
  listener.delegate=service;[listener resume];return 0;
}}
