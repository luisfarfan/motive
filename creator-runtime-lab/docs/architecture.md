# Creator Runtime H18 — isolated implementation

The importer reviews the **existing experimental** Element Lab container. It
retains immutable original bytes and stages only its authorized inventory. The
Rust crate imports `CreatorPack`, `PlanStep`, `PropertyValue`, `Layout`, `Config`
and `Action` directly from Show Control. No element schema, event dispatcher,
scene owner or audiovisual engine was copied into the product.

`prepare(InsertRequest, Snapshot)` returns an insertion proposal. It does not
create an authoring scene. The request selects existing scene IDs and optionally
places the same sources in several scenes. Definitions are identified by package
ID, version and verified archive hash. The caller assigns a local instance label;
it is not a final source/layer ID. Namespace symbols remain unresolved until a
matching typed receipt arrives. Each native compound definition can expand to
several visual sources and layers; an Element Instance is not necessarily one
native source. Independent instances have independent approved properties;
multiple placements of one instance share its source state.

Both design960 layouts, visibility and relative order survive insertion. New
layers append after each destination's current maximum order. Overflow is an
error; existing orders are never rewritten. Explicit layout overrides use the
upstream `Layout` validator. Properties use `CreatorPack::set_property`; the four
exported targets retain their existing type semantics. Compile-time colors or
geometry not exported by CreatorPack must be changed through Element Lab and
repackaged. Unknown properties fail; no silent runtime property extension.

A compound definition must first be selected to one authored scene through the
existing modular SDK. Dependencies resolve only inside that validated pack.
Resources are shared by exact hash, bytes, type, dimensions, duration and license;
source objects are shared only by explicit placement of the same instance. The
current 8 scenes / 16 sources / 32 layers / 4 local videos and 256 MiB conservative
texture estimate remain fixed. Asset inventory retains 128 objects / 512 MiB,
64 MiB per object. Existing camera/gameplay reservations count toward the total.
These are validation estimates, not measured CPU/GPU/RSS ceilings.

`StrictOwnerModel` is an explicitly simulated test adapter. Its nonserializable,
one-use `LocalModelReview` is bound to the model owner and exact snapshot digest.
Only the model generates `sim-*` IDs. Every receipt checks instance/session,
operation fingerprint, strict step order, revision continuity, and the complete
before/after graph. A foreign mutation cannot be adopted as an owned revision.
Partial or uncertain work remains visible; replay is disabled. No action, timer,
output or Show Control rule is started by an installation. Native admission is
absent, so these IDs/receipts must never be copied into Production as authority.

Removal is an explicit **proposal**, not automatic rollback. It includes only
objects owned by acknowledged steps; another instance's assets and any source
with surviving foreign layers are retained. Unknown pending effects require
reconciliation first. Real rollback, durable owner intent and recovery remain
H17 integration work; a model success is not an atomic transaction guarantee.

The optional experimental sidecar stores definitions, properties, physical model
IDs, both layouts, visibility, assets and disabled visual bindings. It excludes
owner sessions, process handles, IPC, credentials and browser state. Loading
checks format, references, ownership, properties and capabilities against freshly
reviewed package bytes. It compares saved sources with their definitions and
current graph, and reports incompatible/missing objects. All restore results
require local review and keep scripts, historical events and Show Control off.
