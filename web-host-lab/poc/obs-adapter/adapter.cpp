#include "adapter.hpp"
#include <cstring>
#include <new>

namespace motive::h22 {
bool ValidGrant(const Grant& g) {
  return g.instance && g.generation && g.epoch && g.width && g.height &&
    g.width<=1920 && g.height<=1920 && uint64_t(g.width)*g.height*4<=1920*1080*4;
}
bool SameGrant(const Grant& a,const Grant& b) {
  return a.instance==b.instance && a.generation==b.generation && a.epoch==b.epoch &&
    a.width==b.width && a.height==b.height;
}
bool ValidFrame(const Grant& g,const Frame& f) {
  return ValidGrant(g) && SameGrant(g,f.grant) && f.sequence && f.bgra &&
    f.stride==g.width*4 && f.length==size_t(f.stride)*g.height;
}
bool Source::Current() const {return owner_ && gs_get_context()==owner_;}
Source* Source::Create(graphics_t* owner,Grant g,bool is_static) {
  if (!owner || gs_get_context()!=owner || !ValidGrant(g)) return nullptr;
  return new (std::nothrow) Source(owner,g,is_static);
}
Source::~Source() {if(texture_)gs_texture_destroy(texture_);}
bool Source::Destroy(Source*& source) {
  if (!source) return true;
  if (!source->Current()) return false;
  delete source;source=nullptr;return true;
}
bool Source::SetVisibleReferences(uint32_t references) {
  if (!Current() || revoked_) return false;
  references_=references;
  // Hiding one scene does not cancel a source still visible in another.
  // Full hide requires a fresh admitted frame before later show; no event replay.
  if(!references_)has_image_=false;
  return true;
}
bool Source::Revoke() {
  if(!Current())return false;
  revoked_=true;has_image_=false;references_=0;return true;
}
UploadResult Source::Upload(const Frame& f,uint64_t now,uint64_t max_age) {
  if(!Current())return UploadResult::Context;
  if(revoked_)return UploadResult::Revoked;
  if(!references_)return UploadResult::Hidden;
  if(!ValidFrame(grant_,f))return UploadResult::Layout;
  if(f.sequence<=sequence_ || f.owner_observed_ns>now || now-f.owner_observed_ns>max_age)return UploadResult::Stale;
  // Fail closed on any attempted replacement. A partial/failed mapping cannot
  // leave the previous image authorized for drawing.
  has_image_=false;
  if(!texture_)texture_=gs_texture_create(grant_.width,grant_.height,GS_BGRA,1,nullptr,GS_DYNAMIC);
  if(!texture_)return UploadResult::Allocate;
  uint8_t* mapped=nullptr;uint32_t pitch=0;
  if(!gs_texture_map(texture_,&mapped,&pitch))return UploadResult::Map;
  if(!mapped || pitch<f.stride) {gs_texture_unmap(texture_);return UploadResult::Map;}
  for(uint32_t y=0;y<grant_.height;++y)std::memcpy(mapped+size_t(y)*pitch,f.bgra+size_t(y)*f.stride,f.stride);
  gs_texture_unmap(texture_);
  sequence_=f.sequence;observed_ns_=f.owner_observed_ns;has_image_=true;
  // Upload submission only. This is not a GPU fence or decoded-output receipt.
  return UploadResult::Uploaded;
}
DrawResult Source::Draw(gs_effect_t* effect,uint64_t now,uint64_t max_age) {
  if(!Current())return DrawResult::Context;
  if(revoked_ || !references_ || !has_image_ || !texture_ || now<observed_ns_ || (!static_ && now-observed_ns_>max_age))return DrawResult::Blank;
  if(!effect)return DrawResult::Effect;
  gs_eparam_t* image=gs_effect_get_param_by_name(effect,"image");
  if(!image)return DrawResult::Effect;
  // Public obs-browser CPU BGRA path: default effect, sRGB sampling and
  // premultiplied ONE/INVSRCALPHA. No unpremultiply effect or vertical flip.
  const bool srgb=gs_framebuffer_srgb_enabled();
  gs_enable_framebuffer_srgb(true);gs_blend_state_push();
  gs_blend_function(GS_BLEND_ONE,GS_BLEND_INVSRCALPHA);
  gs_effect_set_texture_srgb(image,texture_);
  bool drew=false;
  while(gs_effect_loop(effect,"Draw")){gs_draw_sprite(texture_,0,0,0);drew=true;}
  gs_blend_state_pop();gs_enable_framebuffer_srgb(srgb);
  return drew?DrawResult::Drawn:DrawResult::Effect;
}
} // namespace motive::h22
