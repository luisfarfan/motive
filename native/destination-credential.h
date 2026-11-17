#ifndef MOTIVE_DESTINATION_CREDENTIAL_H
#define MOTIVE_DESTINATION_CREDENTIAL_H
#include <CoreFoundation/CoreFoundation.h>
#include <stdbool.h>
#include <stdint.h>

enum motive_destination_credential_phase {
    MOTIVE_CREDENTIAL_IDLE = 0,
    MOTIVE_CREDENTIAL_AWAITING_USER = 1,
    MOTIVE_CREDENTIAL_WRITING = 2,
    MOTIVE_CREDENTIAL_STORED = 3,
    MOTIVE_CREDENTIAL_CANCELLED = 4,
    MOTIVE_CREDENTIAL_FAILED = 5,
    MOTIVE_CREDENTIAL_STORED_AFTER_CANCEL = 6,
};
typedef struct {
    uint64_t request_id;
    uint32_t phase;
    int32_t code;
    uint8_t cancel_requested;
    uint8_t reserved[7];
    char credential_ref[40];
} motive_destination_credential_result;
#if defined(__cplusplus)
static_assert(sizeof(motive_destination_credential_result) == 64, "credential result ABI");
#else
_Static_assert(sizeof(motive_destination_credential_result) == 64, "credential result ABI");
#endif

/* Main-thread owner only. window is an exact live NSWindow owned by NSApp.
 * JSON contains only {"name":...,"binding":<canonical v2 binding string>}.
 * No secret enters or leaves this bridge. request_id must increase per process.
 * begin: 0 accepted, 4 invalid data, 6 signed identity unavailable, 7 busy,
 * 8 unconsumed result, 9 invalid window. poll consume=true acknowledges only
 * terminal results. cancel after writing cannot promise no Keychain write. */
int motive_destination_credential_begin(void *window, const char *request_json, uint64_t request_id);
/* GPUI AppKit handles expose NSView. The owner passes its exact live view;
 * this bridge resolves its window, never NSApp.keyWindow/mainWindow. */
int motive_destination_credential_begin_for_view(void *view, const char *request_json, uint64_t request_id);
bool motive_destination_credential_poll(uint64_t request_id, motive_destination_credential_result *result, bool consume);
bool motive_destination_credential_cancel(uint64_t request_id);
bool motive_destination_credential_busy(void);

/* Native-only read. Returned CFData must never be passed to Rust/GPUI/MCP or
 * serialized in obs_data. Service owner releases it and wipes its own copy.
 * Reader requires an exact canonical v2 binding; H8 port-only bindings fail. */
int motive_destination_credential_read(const char *reference, const char *binding, CFDataRef *secret);
int motive_destination_credential_status(const char *reference, const char *binding);
#endif
