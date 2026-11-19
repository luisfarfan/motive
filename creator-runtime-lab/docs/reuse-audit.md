# H18 reuse audit — 2026-11-18

Fetched `origin/main` at `15ffbad307c5439270130979dae0e9d66d92d700` before creating
`codex/h18-creator-runtime` in `motive-h18`. No H17 handoff was received. At this
initial audit, only Element Lab, Browser Host Lab and this isolated lab were
writable in H18. The table preserves that starting state.

| Existing component | Actual capability | Reuse / required delta | H17 dependency | Test / status at start |
|---|---|---|---|---|
| Element Schema v1 + compiler | Typed properties, DAG, H/V, native lowering | Keep schema; represent runtime instances separately from authoring scenes | None offline | Existing 48 Python tests; baseline evidence only |
| CreatorPack / Config / PlanStep | Strict Rust parsing, plans, action preparation | Import types directly; map scenes to existing owner IDs, suppress CreateScene | Owner apply later | Real crate contract tests; installation missing |
| Modular compositor | Dependency closure, remapping, resource dedup, estimates | Reuse packages; global owner snapshot and receipts required | Owner graph revision | Offline only |
| Experimental review ZIP | Inventory/hash/path/resource checks | Reuse verification; immutable review + private staging + local review policy | Official picker/broker later | Review format is not official installation |
| src/creator_packs.rs | Local capability, MATCHDAY steps, partial state | Reference receipt/order semantics; cannot import these assets today | Exclusive H17 | Read only; no simulated native claims |
| Production graph | 8 scenes / 16 sources / 32 layers / 4 videos | Preserve quotas; budget existing plus proposed | Exclusive H17 | No quota increase |
| Native overlays/libobs | Shared sources, layers, native PTS, output engine | Future adapter uses owner commands only | Explicit handoff + authorization | BLOCKED integration |
| Goal MotiveElement API | Real DOM visual behavior in harness | Owner-scoped projection + MessagePort bootstrap | Live Show Control backend later | No native frame receipt |
| H16 Rust frames/lifecycle/IPC | Owned BGRA mailbox, generations, typed admission | Reuse, connect native boundary and supervisor | None for isolated build | Rust tests do not prove OnPaint |
| H16 CEF fixture/broker | Static API validation, immutable inventory | Complete matching framework/wrapper/helper/AppKit build | Execution exception from owner | BLOCKED browser execution |
| Creator Experience | Existing local library/form, tokens, validated packs | CLI review/library now; preserve visual source of truth | GPUI implementation later | No new editor/marketplace |
| Project v1–v5 | Real production compatibility | Experimental install sidecar; no new production revision yet | Migration integration after handoff | Fixtures must remain unchanged |

Read-only references: AGENTS.md; README.md; docs/plan.md and decisions.md;
H11 browser spike; H14 beta and H15 resume verification; Element Lab architecture,
integration, QA, schema/SDK/web sources; Creator Experience; Show Control packs and
owner installer; H16 final decision, integration, build, upstream reuse, security
and libobs adapter contracts. Native browser execution is specifically gated by
the request and AGENTS; build/link/static inspection and non-browser tests are allowed.

The owner subsequently authorized the native fixture and explicitly requested
updating AGENTS.md to allow supervised owned-content CEF tests. That local policy
change is the only addition outside the two implementation labs. Actual native
results and remaining security/Production gates are in [acceptance](acceptance.md);
the earlier BLOCKED entries above are not the current execution status.
