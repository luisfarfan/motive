#pragma once
// H22 isolated adapter. This header is trusted owner-side C++, not an IPC ABI.
// All calls, including authority changes, are serialized on the existing OBS
// graphics owner. The caller pins a complete immutable frame for Upload's call.
// No function waits for CEF, a socket, disk, shutdown or a lease mutex.
#include <cstddef>
#include <cstdint>
#include <graphics/graphics.h>

namespace motive::h22 {
struct Grant { uint64_t instance, generation, epoch; uint32_t width, height; };
struct Frame {
  Grant grant;
  uint64_t sequence, owner_observed_ns;
  uint32_t stride;
  const uint8_t* bgra;
  size_t length;
};
enum class UploadResult { Uploaded, Context, Revoked, Hidden, Stale, Layout, Allocate, Map };
enum class DrawResult { Drawn, Context, Blank, Effect };

bool ValidGrant(const Grant&);
bool SameGrant(const Grant&, const Grant&);
bool ValidFrame(const Grant&, const Frame&);

class Source final {
 public:
  // Borrowed context: does not create/start a composition engine or AV clock.
  static Source* Create(graphics_t* owner, Grant, bool static_content);
  // Refuses wrong context and leaves the pointer live for an owner retry.
  static bool Destroy(Source*&);
  Source(const Source&)=delete;
  Source& operator=(const Source&)=delete;
  bool SetVisibleReferences(uint32_t aggregate_references);
  bool Revoke(); // terminal; recovery/cold replacement creates a new Source.
  UploadResult Upload(const Frame&, uint64_t owner_now_ns, uint64_t max_age_ns);
  // Uses the existing owner's default effect, never OBS_EFFECT_PREMULTIPLIED_ALPHA.
  // Static repeat is explicit; animated frames expire at the same owner age gate.
  DrawResult Draw(gs_effect_t* default_effect, uint64_t owner_now_ns, uint64_t max_age_ns);
 private:
  Source(graphics_t* owner, Grant grant, bool is_static):owner_(owner),grant_(grant),static_(is_static){}
  ~Source();
  bool Current() const;
  graphics_t* owner_;
  const Grant grant_;
  const bool static_;
  bool revoked_=false, has_image_=false;
  uint32_t references_=0;
  uint64_t sequence_=0, observed_ns_=0;
  gs_texture_t* texture_=nullptr;
};
} // namespace motive::h22
