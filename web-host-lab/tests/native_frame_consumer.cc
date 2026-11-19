// SPDX-License-Identifier: GPL-3.0-or-later
#include "../poc/browser-host/native/frame_consumer.hpp"
#include <array>
#include <cassert>
#include <filesystem>
#include <iterator>
#include <sys/stat.h>

static std::vector<uint8_t> Read(const std::filesystem::path& path){
  std::ifstream input(path,std::ios::binary);
  assert(input);return {std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>()};
}
static void AwaitConsumed(MotiveFrameBridge* mailbox,uint64_t count){
  const auto deadline=MonotonicNs()+3000000000;
  while(MonotonicNs()<deadline){
    MotiveFrameStatisticsV2 stats{};assert(motive_frames_stats_v2(mailbox,&stats));
    if(stats.consumed==count)return;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  assert(false&&"bounded consumer completion deadline");
}
int main(){
  char name[]="web-host-lab/.cache/h19-consumer-test-XXXXXX";
  const char* made=mkdtemp(name);assert(made);const std::filesystem::path root=made;
  const auto file=root/"fixed.bgra";
  const int fd=open(file.c_str(),O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);assert(fd>=0);
  const std::array<uint8_t,8> old{9,9,9,9,9,9,9,9};assert(write(fd,old.data(),old.size())==ssize_t(old.size()));
  FixedFrameFile writer;const std::array<uint8_t,4> a{1,2,3,4},b{5,6,7,8};
  assert(writer.Write(fd,a.data(),a.size()));assert(Read(file)==std::vector<uint8_t>(a.begin(),a.end()));
  assert(writer.Write(fd,b.data(),b.size()));assert(Read(file)==std::vector<uint8_t>(b.begin(),b.end()));
  assert(writer.full_writes()==2&&writer.truncate_calls()==1&&writer.length()==4);
  assert(!writer.Write(fd,b.data(),3));assert(!writer.Write(fd,old.data(),old.size()));
  assert(!writer.Write(fd+10000,b.data(),b.size()));
  assert(writer.rejected()==3&&writer.full_writes()==2&&writer.truncate_calls()==1);
  assert(Read(file)==std::vector<uint8_t>(b.begin(),b.end()));
  struct stat st{};assert(fstat(fd,&st)==0&&st.st_size==4);close(fd);
  {
    auto* mailbox=motive_frames_create(1,19,1,2,2);assert(mailbox);
    const auto sink=root/"consumer";assert(std::filesystem::create_directory(sink));
    FrameConsumer consumer(mailbox,sink.string());assert(consumer.valid());
    std::array<uint8_t,16> first,latest;first.fill(0x11);latest.fill(0x22);
    assert(motive_frames_publish(mailbox,19,1,MonotonicNs(),first.data(),first.size())==0);AwaitConsumed(mailbox,1);
    assert(motive_frames_publish(mailbox,19,1,MonotonicNs(),latest.data(),latest.size())==0);AwaitConsumed(mailbox,2);
    motive_frames_revoke(mailbox);consumer.Stop();assert(consumer.WriteReport(2,0,0,0));
    assert(Read(sink/"first.bgra")==std::vector<uint8_t>(first.begin(),first.end()));
    assert(Read(sink/"latest.bgra")==std::vector<uint8_t>(latest.begin(),latest.end()));
    const auto data=Read(sink/"frames.json");const std::string report(data.begin(),data.end());
    assert(report.find("\"latest_file_full_writes\":2")!=std::string::npos);
    assert(report.find("\"latest_file_ftruncate_calls\":1")!=std::string::npos);
    assert(report.find("\"latest_file_rejected_geometry_or_descriptor\":0")!=std::string::npos);
    assert(report.find("\"latest_file_fixed_bytes\":16")!=std::string::npos);
    MotiveFrameStatisticsV2 stats{};assert(motive_frames_stats_v2(mailbox,&stats));
    assert(stats.paints==2&&stats.consumed==2&&stats.pending==0&&stats.leased==0);
    motive_frames_destroy(mailbox);
  }
  assert(std::filesystem::remove_all(root)>0);
}
