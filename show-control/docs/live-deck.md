# Live Deck — typed local model and simulation contract

This is an independent model and design prototype. It does not change GPUI or own
Production. `Deck`, `DeckButton`, `ButtonTarget`, `DeckRuntime`, `DeckPress`,
`ButtonState` and `DeckHistory` are implemented in `src/deck.rs`; fixtures are in
`examples/decks/matchday.json`. Schema v1 rejects unknown fields and malformed input.

A Deck has up to eight ordered groups and 64 buttons. Each button has a stable ID,
label, icon enum, group/order, enabled flag, optional unique shortcut, cooldown,
sensitive flag and bounded typed target. Targets represent a rule, source show/hide,
pack animation, scene Cut/Fade, countdown or composite rule. There is no shell,
provider credential, raw MCP command or arbitrary expression target.

`press(button_id, monotonic_ms, confirmed)` returns a **simulated**
`manual.button_pressed` request and its target. Rule/composite targets must bind to
manual-event rules; a manual button never forges voice confidence or chat authority.
Other targets are converted by the simulator into typed manual action rules. Runtime
states distinguish ready, disabled, awaiting confirmation, pending, cooldown, rejected,
cancelled and simulated result. There is no fake live accepted/completed state.
Pending presses are not duplicated, cooldown boundaries are deterministic, backward
clock values fail, and recent history is bounded to 64 entries. Completion is explicit
through `finish_simulation`; cancellation affects only this simulation request.

The cooldown displayed by the Deck is a local interaction guard. The rule engine's
cooldown/rate/dedup policy still applies; the Deck cannot override it. Ephemeral Deck
history is not persisted or a source of media state. Restarting the prototype does
not resume actions. Show Control's explicit checkpointed state owns replay protection; durable intent journaling for live dispatch is still pending.

Sensitive buttons require explicit confirmation before a simulated press is returned.
The boolean/CLI `--confirm` is strictly a prototype input. It is **not** authorization
for remote live control. A later native integration must bind a short-lived local
confirmation to the exact action and production identity/revision, invalidate it on
change, and keep untrusted event/provider inputs outside that authorization path.

## Component specification

- Group header: title and stable order; group changes do not alter rule priority.
- Action tile: icon, concise label, shortcut hint, enabled state and cooldown remainder.
- Pending indicator: show request/operation identity; acceptance never implies completed.
- Sensitive confirmation: describe the scene/action and production, offer cancel,
  restore focus, and avoid execution on focus/hover.
- Recent history: compact, bounded, sanitized status and error code; no viewer message,
  secret or transport payload required in the tile.
- Keyboard: explicit modifiers and canonical ASCII key, no global hook implemented.
  Future GPUI must skip shortcuts while editing text or when context is inappropriate.
- Accessibility: descriptive labels, keyboard focus, sufficient contrast, non-color
  state indications and reduced-motion support. The HTML study has focus rings and
  semantic buttons; GPUI accessibility is still pending.

## Future Production bridge

Button activation enters the same validated event/rule/action pipeline as CLI/MCP.
The integration consumes observed owner snapshots and submits commands on the one
Production owner. It never maintains another scene graph or multimedia clock.
Source-wide show/hide is different from layer visibility; the label should explain
shared-source effects. A lower-third entry animation alone does not show a hidden
source: activate `Presenter` first, then `Presenter entry`, or use an explicit sequence.

Cut/Fade must await incompatible layer animations and pending acknowledgements;
structural/import/shutdown busy states must remain visible. Future source failures,
stale revision/identity, transport uncertainty and operation completion must be
reconciled from core state. The Deck must not retry uncertain mutations, reconnect a
source, install a pack, or declare a live operation finished by elapsed UI time.
