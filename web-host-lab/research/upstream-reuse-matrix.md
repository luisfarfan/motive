# Reuse matrix — checkpoint B

Labels describe the selected design, not code already shipped. A full plugin
fork is rejected. GPL code origins must survive any later extraction.

| Component / source | Decision | Reason and maintenance owner |
|---|---|---|
| CEF Chromium runtime | REUSE | Upstream engine; pin complete matching distribution, maintain security updates |
| CEF C++ wrapper/library loader | REUSE | Official ABI/lifetime glue; build from the same distribution |
| CEF sandbox loader | REUSE | Official macOS helper initialization; never invent Seatbelt policy |
| CEF process messages/tasks/refcounts | REUSE | Existing transport/thread primitives; Motive validates application messages |
| BrowserManager globals / plugin init | REPLACE | Small isolated host; no module cache/profile/frontend state |
| Qt MessageObject / task queue | REPLACE | CEF AppKit loop in dedicated process; bounded owner channel |
| BrowserSource create/close/visibility | ADAPT | Reuse ordering and public APIs; explicit final-close and generation barriers |
| GetViewRect / OnPaint | ADAPT | Full BGRA copy into bounded mailbox, no libobs calls in CEF process |
| CPU texture upload and render blend | ADAPT | Future libobs-owned texture, premultiplied alpha and sRGB verification |
| Accelerated paint IOSurface | DEFER | Pinned header requires owned copy/synchronization; no zero-copy assumption |
| http://absolute file scheme | REPLACE | Exact immutable inventory and no path-based native read after import |
| BrowserClient request/permission policy | REPLACE | All requests/devices denied except authorized asset response |
| BrowserDummyClient | ADAPT | Close unmanaged browsers; no window creation outside accounting |
| obsstudio V8 functions | REMOVE | Expose recording/streaming authority inappropriate for widgets |
| DispatchJSEvent | ADAPT | Typed visual projection, one instance/main frame; no broadcast secrets |
| Browser audio rerouting | REMOVE | H16 is visual-only; mute and deny devices |
| Browser panels/tooltips/context menus | REMOVE | GPUI owns UI, no browser interaction chrome |
| OBS frontend / websocket hooks | REMOVE | Production owns commands; channel has no such variants |
| Helper bundle layout/signing pattern | ADAPT | Match exact CEF revision, own IDs, minimum role entitlements |
| Profile migration/cookies/auth | REMOVE | Disposable per-instance contexts; no personal browser profile |

4 REUSE + 6 ADAPT = 10/20 decision rows (50%). This is an **unweighted component
classification**, not 50% functionality, LOC saved, performance gained, or a
coverage result. No defensible functional percentage exists without a defined
feature corpus and native equivalence tests. OBS implementation code transplanted
into the host at this checkpoint: zero. The valuable reuse is the actual CEF
engine, ABI wrapper and mature integration patterns; there is no new web engine.

## Candidate comparison

| Strategy | Code/dependencies | Security/update cost | Integration/risk |
|---|---|---|---|
| A: fork plugin, remove frontend | Own a broad edited plugin; Qt removals cross client/source/app/build; preserve libobs coupling | Security requires replacing files, permissions, bindings, profiles anyway; repeated upstream conflicts | Higher sustained delta; existing source render helpful but wrong process boundary |
| B: extract components | Own selected fragments and seams; CEF + small native adapter | Less fork surface, but old back-pointers and global contexts need redesign | Useful only for narrowly proven utilities; extract after measurement, not wholesale |
| C: CEF directly + OBS patterns | CEF official wrapper, AppKit host, Rust contracts, future libobs adapter | Own policy/lifecycle/frame contracts; upstream keeps Chromium; no Qt migration debt | Chosen experiment; macOS sandbox/egress and runtime acceptance remain gates |

No measured speed/memory ranking. C is the smallest responsibility boundary,
not proof of lowest runtime resource consumption. B remains a way to implement
specific C adapters; it is not a second permanent renderer. License obligations
are source-specific for all alternatives.

