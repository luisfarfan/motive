/* Real owned process lifecycle plus explicit policy counterexamples.
 * Catalog absence below is injected metadata, not a LaunchServices test. */
#include "process-identity.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t child = -1;
static unsigned checks;
static void cleanup(void) {
    if (child > 0) { kill(child, SIGKILL); waitpid(child, NULL, 0); child = -1; }
}
#define CHECK(condition) do { checks++; if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); exit(1); } } while (0)
static enum motive_application_identity_health health(const motive_process_identity *pin,
        enum motive_process_probe probe, const motive_process_identity *now,
        unsigned count, pid_t registered, bool conflict) {
    return motive_application_identity_check(pin, probe, now, count, registered, conflict);
}
int main(void) {
    atexit(cleanup);
    motive_process_identity pin, now, changed;
    CHECK(motive_process_observe(getpid(), &pin) == MOTIVE_PROCESS_OBSERVED);
    CHECK(pin.pid == getpid() && pin.uid == getuid() && pin.executable[0]);
    CHECK(motive_process_observe(getpid(), &now) == MOTIVE_PROCESS_OBSERVED);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 1, getpid(), false) == MOTIVE_APPLICATION_MATCHES);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 0, 0, false) == MOTIVE_APPLICATION_MATCHES);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 2, getpid(), false) == MOTIVE_APPLICATION_AMBIGUOUS);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 1, getpid()+1, false) == MOTIVE_APPLICATION_CHANGED);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 0, 0, true) == MOTIVE_APPLICATION_CHANGED);
    CHECK(health(&pin, MOTIVE_PROCESS_UNOBSERVED, &now, 0, 0, false) == MOTIVE_APPLICATION_IDENTITY_UNOBSERVED);
    CHECK(health(&pin, MOTIVE_PROCESS_ABSENT, &now, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    changed = now; changed.pid++;
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &changed, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    changed = now; changed.uid++;
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &changed, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    changed = now; changed.start_seconds++;
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &changed, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    changed = now; changed.start_microseconds++;
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &changed, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    changed = now; strcpy(changed.executable, "/different/executable");
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &changed, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    CHECK(motive_process_observe(0, &now) == MOTIVE_PROCESS_UNOBSERVED);

    int gate[2]; CHECK(pipe(gate) == 0);
    child = fork(); CHECK(child >= 0);
    if (child == 0) {
        close(gate[1]); char token;
        if (read(gate[0], &token, 1) != 1) _exit(2);
        close(gate[0]); execl("/bin/sleep", "sleep", "30", (char *)NULL); _exit(3);
    }
    close(gate[0]);
    CHECK(motive_process_observe(child, &pin) == MOTIVE_PROCESS_OBSERVED);
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &pin, 0, 0, false) == MOTIVE_APPLICATION_MATCHES);
    CHECK(write(gate[1], "x", 1) == 1); close(gate[1]);
    bool exec_observed = false;
    for (int i=0; i<300; i++) {
        if (motive_process_observe(child, &now) == MOTIVE_PROCESS_OBSERVED &&
            strcmp(pin.executable, now.executable)) { exec_observed = true; break; }
        usleep(10000);
    }
    CHECK(exec_observed);
    CHECK(motive_process_same_generation(&pin, &now));
    CHECK(health(&pin, MOTIVE_PROCESS_OBSERVED, &now, 0, 0, false) == MOTIVE_APPLICATION_CHANGED);
    CHECK(kill(child, SIGTERM) == 0);
    pid_t dead = child; int status;
    CHECK(waitpid(child, &status, 0) == child); child = -1;
    CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGTERM);
    enum motive_process_probe gone = motive_process_observe(dead, &now);
    CHECK(health(&pin, gone, &now, 0, 0, false) != MOTIVE_APPLICATION_MATCHES);
    printf("{\"status\":\"PASS\",\"checks\":%u,\"real_exec_and_exit\":true,"
           "\"catalog_absence\":\"injected metadata with real OS identity\","
           "\"pid_reuse\":\"birth mismatch policy only, no real PID reuse induced\"}\n", checks);
    return 0;
}
