// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <unistd.h>

// A borrowed, already-open private descriptor, fixed for one viewport epoch.
// Each call writes the complete frame. Only the first successful call changes
// file length; subsequent calls must match both descriptor and byte length.
class FixedFrameFile {
 public:
  bool Write(int fd,const uint8_t* bytes,size_t length){
    if(fd<0||!bytes||!length||(initialized_&&(fd!=fd_||length!=length_))){++rejected_;return false;}
    size_t offset=0;
    while(offset<length){
      const auto count=pwrite(fd,bytes+offset,length-offset,off_t(offset));
      if(count<0&&errno==EINTR)continue;
      if(count<=0)return false;
      offset+=size_t(count);
    }
    if(!initialized_){
      ++truncate_calls_;
      if(ftruncate(fd,off_t(length)))return false;
      fd_=fd;length_=length;initialized_=true;
    }
    ++full_writes_;return true;
  }
  uint64_t full_writes()const{return full_writes_;}
  uint64_t truncate_calls()const{return truncate_calls_;}
  uint64_t rejected()const{return rejected_;}
  size_t length()const{return length_;}
 private:
  int fd_=-1;
  size_t length_=0;
  bool initialized_=false;
  uint64_t full_writes_=0,truncate_calls_=0,rejected_=0;
};
