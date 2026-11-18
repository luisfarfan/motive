/* Explicit, synchronous diagnostics of this process only. Never call from an
 * audio/video callback or automatic UI status poll. Returned JSON uses malloc;
 * caller owns it and must free it (motive_free is compatible). */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
char *motive_memory_diagnostics(void);
#ifdef __cplusplus
}
#endif
