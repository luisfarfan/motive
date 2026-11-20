/* Owner-thread identity observations, never a media clock or replacement
 * process selection. Executable paths remain private in memory. */
#pragma once
#include <errno.h>
#include <libproc.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/proc.h>
#include <sys/proc_info.h>

typedef struct {
    pid_t pid;
    uid_t uid;
    uint64_t start_seconds, start_microseconds;
    char executable[PROC_PIDPATHINFO_MAXSIZE];
} motive_process_identity;

enum motive_process_probe { MOTIVE_PROCESS_UNOBSERVED, MOTIVE_PROCESS_OBSERVED,
                            MOTIVE_PROCESS_ABSENT };
enum motive_application_identity_health { MOTIVE_APPLICATION_MATCHES,
    MOTIVE_APPLICATION_CHANGED, MOTIVE_APPLICATION_AMBIGUOUS,
    MOTIVE_APPLICATION_IDENTITY_UNOBSERVED };

static bool motive_process_same_generation(const motive_process_identity *a,
                                           const motive_process_identity *b) {
    return a->pid > 0 && a->pid == b->pid && a->uid == b->uid &&
        a->start_seconds == b->start_seconds && a->start_microseconds == b->start_microseconds;
}

static enum motive_process_probe motive_process_observe(pid_t pid, motive_process_identity *out) {
    memset(out, 0, sizeof(*out));
    if (pid <= 0) return MOTIVE_PROCESS_UNOBSERVED;
    struct proc_bsdinfo before = {0}, after = {0};
    errno = 0;
    int size = proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &before, sizeof(before));
    if (size != (int)sizeof(before)) return errno == ESRCH ? MOTIVE_PROCESS_ABSENT : MOTIVE_PROCESS_UNOBSERVED;
    if (before.pbi_pid != (uint32_t)pid) return MOTIVE_PROCESS_UNOBSERVED;
    if (before.pbi_status == SZOMB) return MOTIVE_PROCESS_ABSENT;
    int path_size = proc_pidpath(pid, out->executable, sizeof(out->executable));
    if (path_size <= 0 || path_size >= (int)sizeof(out->executable) || !out->executable[0])
        return MOTIVE_PROCESS_UNOBSERVED;
    /* Bracket the path lookup with birth observations so PID reuse during
     * these separate syscalls cannot authorize a replacement. No future
     * liveness or SCStream callback lifetime is inferred from this sample. */
    errno = 0;
    size = proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &after, sizeof(after));
    if (size != (int)sizeof(after)) return errno == ESRCH ? MOTIVE_PROCESS_ABSENT : MOTIVE_PROCESS_UNOBSERVED;
    if (after.pbi_status == SZOMB) return MOTIVE_PROCESS_ABSENT;
    if (after.pbi_pid != before.pbi_pid || after.pbi_uid != before.pbi_uid ||
        after.pbi_start_tvsec != before.pbi_start_tvsec ||
        after.pbi_start_tvusec != before.pbi_start_tvusec) return MOTIVE_PROCESS_UNOBSERVED;
    out->pid = pid; out->uid = after.pbi_uid;
    out->start_seconds = after.pbi_start_tvsec; out->start_microseconds = after.pbi_start_tvusec;
    return MOTIVE_PROCESS_OBSERVED;
}

static enum motive_application_identity_health motive_application_identity_check(
    const motive_process_identity *admitted, enum motive_process_probe probe,
    const motive_process_identity *observed, unsigned registered_instances,
    pid_t registered_pid, bool positive_bundle_conflict) {
    if (probe == MOTIVE_PROCESS_ABSENT) return MOTIVE_APPLICATION_CHANGED;
    if (probe != MOTIVE_PROCESS_OBSERVED) return MOTIVE_APPLICATION_IDENTITY_UNOBSERVED;
    if (!motive_process_same_generation(admitted, observed) ||
        strcmp(admitted->executable, observed->executable)) return MOTIVE_APPLICATION_CHANGED;
    /* Keep admission strict and reject positive conflicts. A missing catalog
     * entry alone is not the death of this independently observed process. */
    if (registered_instances > 1) return MOTIVE_APPLICATION_AMBIGUOUS;
    if ((registered_instances == 1 && registered_pid != admitted->pid) || positive_bundle_conflict)
        return MOTIVE_APPLICATION_CHANGED;
    return MOTIVE_APPLICATION_MATCHES;
}
