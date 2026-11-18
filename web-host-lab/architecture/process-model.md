# Processes, contexts and pooling

Initial third-party design: **one host process tree per instance**, disposable
request context and unique origin. This is a containment baseline for experiments,
not a verified isolation guarantee. Keep the manager in Motive; move Chromium's
browser process out of Production. The browser process itself is privileged and
needs an OS confinement solution that remains unresolved on the tested bundle.

| Layout | Shares | Failure/security implication | Decision |
|---|---|---|---|
| Global context, multiple browsers | cookies/cache/storage; browser/network/GPU | Broad state/fault domain; same renderer possible | Reject for unrelated third-party elements |
| Distinct contexts in one CEF host | browser/network/GPU and framework maps | CEF request contexts separate storage; not a guarantee of independent processes or no cross-instance attack | Benchmark later for reviewed same-trust content only |
| Distinct host trees | read-only framework disk and OS shared pages only | Per-host kill/restart, clearer accounting; more process/initialization cost | Conservative initial experiment |

Do not describe CefRequestContext as a sandbox. Do not use CreateContext(other)
when isolation requires no shared storage. Empty per-context cache path requests
in-memory storage, but global root-cache/singleton/bookkeeping behavior must be
verified for each revision. Allocate unique private runtime root per host; revoke
it on close. No owner browser profile or same-origin reuse across instances.

Pooling must be earned: only same reviewed trust policy, fixed CEF distribution,
fresh context/origin, no persisted service workers/cookies, revoked channels and
asset references, and repeated contamination/crash tests. Prefer sharing immutable
runtime installation and OS file-backed pages first. RSS sums double-count some
shared pages; report physical footprint separately rather than claiming savings.

WasHidden suppresses render delivery; it does not prove JS pause. Hidden performs
cancel first. Suspension closes the browser, clears mailbox and revokes the channel;
only final-close confirms it. Resumption/restart is explicit, with a new generation
after teardown. Terminate only the lab-owned tree identified at launch; never kill
by process name or claim no orphans from a successful parent exit alone.

