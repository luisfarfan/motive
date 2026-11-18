# H16 — Motive Browser Engine laboratory

Independent research and contract implementation based on remote main
`130b626168cbe1336afb85c3810fa6be5e6b2b11`, 2026-11-18. All H16 changes live here.
H15 owns production. No application, CEF process, capture, recording or stream
is started by the static test workflow. No changes to `.deps/` or global tools.

**PARTIAL laboratory; native rendering and third-party isolation BLOCKED.**
Read [the final decision](docs/final-decision.md), [audit](research/obs-browser-analysis.md)
and [build instructions](docs/build-and-test.md). Static contract tests are not
CEF runtime evidence. The native fixture is explicitly gated by repository
policy; proxima-browser is the only authorized browser QA tool.

Direction: CEF upstream runtime/wrapper, a small separate host, CPU-copy OSR,
existing Web Element v1, bounded channels, no Qt or OBS frontend in that host.
The future libobs source remains owned and clocked by Motive's one Production.

Source archives and binaries used for static inspection are checksum pinned
in [sources.lock.json](research/sources.lock.json) and cached only in `.cache/`.
They are not vendored, published, executed, or installed into Motive.

