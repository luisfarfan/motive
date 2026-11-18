# Compatibility decision

No production project revision is needed for this isolated phase. Project v1–v5,
Show Control v1 and the current core remain byte-for-byte untouched. The new
`motive-creator-runtime-lab-state` version 1 is an **experimental sidecar**, not a
Motive project migration or installable official format. An absent sidecar has
no effect. Synthetic v1–v5 passthrough fixtures verify only that this adapter does
not rewrite legacy bytes; they do not certify Production's legacy loader.

`motive-element-lab-review` version 1 stays a review container. Its historical
`6019ad0` compatibility marker is accepted explicitly by the local review policy;
H18 itself starts at `15ffbad`. Unknown markers and versions fail. Exported native
properties retain CreatorPack limits; original Element Schema compile-time
constraints are not all present in that export and are not reconstructed by
claim. License text/inventory checks do not establish authorship or per-resource
provenance that CreatorPack v1 does not carry.

Before official integration, decide how package archive hash + resource receipt
map enter the managed asset store, how an installation journal is fsynced before
owner dispatch, and how a partial operation is reconciled without replay. Then
choose either a separately versioned owner-managed installation store or an
explicit project extension with old-project fixtures from H17. Do not promote
this sidecar or simulated IDs merely because tests pass.

Capabilities reported by the offline fixture are `Capability::h12_contracts()`.
They are not a probe of running Motive. PNG validation is the existing bounded
SDK decoder gate; official native import/normalization remains required. Web
content keeps its separate `.motiveweb` path and cannot enter the declarative
importer as a native source.
