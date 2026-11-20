// Pure validation against the real OBS headers. No fake GPU PASS.
#include "adapter.hpp"
#include <cassert>
using namespace motive::h22;
int main(){
  Grant g{1,2,3,640,360};uint8_t byte=0;
  Frame frame{g,1,100,2560,&byte,640*360*4};
  assert(ValidGrant(g));assert(ValidFrame(g,frame));
  frame.grant.generation++;assert(!ValidFrame(g,frame));frame.grant=g;
  frame.grant.epoch++;assert(!ValidFrame(g,frame));frame.grant=g;
  frame.stride++;assert(!ValidFrame(g,frame));frame.stride--;
  frame.length--;assert(!ValidFrame(g,frame));frame.length++;
  frame.sequence=0;assert(!ValidFrame(g,frame));frame.sequence=1;
  frame.bgra=nullptr;assert(!ValidFrame(g,frame));
  assert(!ValidGrant({1,1,1,1920,1920}));assert(!ValidGrant({1,1,0,640,360}));
  assert(!ValidGrant({1,1,1,0xffffffff,0xffffffff}));
  assert(Source::Create(nullptr,g,false)==nullptr);
  Source* none=nullptr;assert(Source::Destroy(none));
}
