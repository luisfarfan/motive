# Declarative review and staging

`runtime_importer.py` reuses Element Lab's experimental container validator, PNG
checks, `compiler.Bundle` and real offline Rust Show Control parser. It does not
install into Motive, execute HTML/JS, approve trust or ratify a `.motivepack`
format. `motive-element-lab-review` remains experimental.

```python
from pathlib import Path
from runtime_importer import ReviewPolicy, review_package, stage_package

# A caller-owned capability snapshot, not a value accepted from the package.
policy = ReviewPolicy(available_capabilities=frozenset({
    "image_asset", "widget", "layer_animation"
}))
review = review_package(Path("element-lab/marketplace-contract/packages/lower-third.motivepack"), policy)
bundle = review.as_bundle()  # Existing SDK Bundle; safe independent copy.
with stage_package(review, Path("creator-runtime-lab/.scratch/private-staging")) as stage:
    stage.reverify()        # Same reviewed archive bytes, exact expanded inventory.
    # Feed manifest/rules/hash to the offline installation planner here.
```

Create the staging root's parent first. The root itself is created as 0700 or
must already be owned by this user and private. Inputs containing symlink
components are refused, including platform aliases such as `/var`; a trusted
caller can select the actual `/private/var` directory before calling this API.
The importer never resolves a package-supplied path against the host filesystem.

`ReviewedPackage` retains immutable archive/file bytes. `.manifest`, `.rules`,
`.metadata` and `.report` return defensive JSON copies; `.assets` and `.inventory`
are read-only mappings over immutable bytes. `.sha256`, `.package_id` and
`.version` identify the exact reviewed candidate. A mutable `as_bundle()` cannot
change that identity. Package replacement after review cannot change staging.

The local policy checks capabilities, supported compatibility baselines, declared
license, approved license-text digest, resource bytes and total staging bytes.
Its default approves only the repository's exact GPL text and admits no
capabilities. Approval of other license text must come from a separate local
review; package fields never add approvals. This verifies declarations and
reviewed bytes, not ownership or legal compatibility. CreatorPack v1 carries no
per-resource license provenance: the report retains this limitation explicitly.

All archive checks remain in the existing SDK: exact checksum inventory, paths,
entry types/modes, size and compression bounds, passive previews, schema and
native definitions. H18 additionally rejects NUL-truncated ZIP filenames,
checks the selected path through held no-follow descriptors, and refuses orphan
resources. Resources resolve exclusively from the verified embedded inventory.
No download or registry is introduced. The legacy Element Lab baseline marker
is explicitly accepted as a compatibility input, not confused with current Git
HEAD. Unknown baselines require a policy decision.

Staging writes a new random operation directory, 0700 directories and 0400 files,
using descriptor-relative exclusive creates. It includes the unchanged archive,
verified payload and an informational record. Its reported disk budget covers
all three; it is not a disk-space reservation or RSS measurement. Reverification
checks owned inode identities, full inventory and every byte. Cleanup preflights
the complete tree and removes only those owned objects. A replacement inode,
symlink, hardlink or foreign entry produces `STAGING_RECONCILIATION` and leaves
all objects for explicit recovery; it never runs recursive `rmtree`. Interrupted
construction similarly preserves possible partial staging. This is not a sandbox
against concurrent hostile native processes running as the same user.

The staging record's `owner_authorized:false` and `installed:false` are reports,
not serializable authorities. No state here can arm Show Control. A future owner
must revalidate the snapshot/revision, call its normal importer/decoder, apply
approved operations and retain actual receipts. Native decoding, renderer output,
Production integration and atomic rollback remain separate gates.

Run reproducible checks from the worktree root:

```sh
python3 -m unittest discover -s creator-runtime-lab/tests -p test_importer.py -v
python3 creator-runtime-lab/importer/verify_examples.py
```

The seven unchanged packages include Lower Third, Community Alert, Goal
Celebration, Countdown, Creator Tech minimal, Neon Arena minimal and the existing
mixed example. `.motiveweb` is deliberately rejected by this declarative path.
