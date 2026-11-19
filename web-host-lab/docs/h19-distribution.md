# H19 — macOS distribution audit

**Distribution BLOCKED.** The laboratory bundle is ARM64 and locally ad-hoc
sealed. Developer ID, Hardened Runtime/JIT acceptance, notarization, the browser
process OS boundary and production Keychain behavior remain separate gates.
Nothing was published, notarized or signed with a personal identity. Inspection
commands do not look up identities or touch Keychain.

## Measured bundle, not estimated RAM

`tools/h19_distribution_audit.py` inventories real files and internal symlinks,
hashes each regular file, reads bundle IDs, uses `lipo -archs`, inspects signatures
and entitlements, and runs `codesign --verify --strict --deep`. It never loads
the inspected executables. It rejects symlinks escaping the bundle. The observed
file sizes below exclude symlink/directory metadata and are **not APFS physical
allocation, archive sizes, RSS or memory footprint**.

| Artifact | Main executable SHA-256 | File bytes | MiB |
|---|---|---:|---:|
| Frozen H18 smoke copied into H19 cache | `4f77eea5e899f98ad57cb3a4bed047dcb0c87a8b8d784a361ac73606d2fca8f7` | 325,245,233 | 310.178 |
| Initial H19 multi build | `de8dfb72560700ee124705b6859459b3cc49b1acd2ae8fa62ccde290fa640cd7` | 325,657,473 | 310.571 |
| Final H19 multi build, Chromium credits preserved | `edccc2eef22cd2f7ef336c4256023b42555da97a8b1b9f18498a6ed715a07bd6` | 345,381,375 | 329.381 |

All three inspected bundles contain the same sealed CEF framework file payload:
**319,837,842 bytes / 305.021 MiB**. Total resources are 78,148,643 bytes; locale
files account for 50,540,214 bytes / 48.199 MiB. These values are from actual
inventories, not the older H16 installed-OBS measurement. Initial H19 grows by
412,240 bytes (0.393 MiB) outside the unchanged framework. Bundled disk payload
is shared by instances; it is not copied into one install per widget.
[Frozen H18 audit](../research/h19-distribution-baseline.json),
[initial H19 audit](../research/h19-distribution-multi.json),
[final H19 audit](../research/h19-distribution-final.json).
Final H19 additionally carries the full 19,690,678-byte Chromium credits file;
its total resources are 97,839,321 bytes. Final total growth from H18 is
20,136,142 bytes; the notices account for most of that increase. This is a
packaging correction, not a runtime-memory regression measurement.

The six executables are the main host plus generic, Alerts, GPU, Plugin and
Renderer helpers, with separate `org.motive.lab.browserfixture...` identifiers.
The inspections observe ARM64, `Signature=adhoc`, no Hardened Runtime flag and no
embedded entitlements. Plists declare macOS 15.0; runtime coverage on the current
Mac does not certify all systems from 15.0 onward. A valid resource seal only
proves this local artifact's signature consistency, not publisher trust,
Gatekeeper acceptance or effective sandboxing.

Reproduce into a **new report path**:

```sh
python3 web-host-lab/tools/h19_distribution_audit.py \
  --bundle web-host-lab/.cache/h19-native-multi-final-ephemeral/MotiveBrowserFixture.app \
  --output web-host-lab/research/h19-distribution-new-observation.json
```

## Required final bundle work

| Area | Evidence / decision | Final gate |
|---|---|---|
| Runtime correspondence | CEF 150.0.19, Chromium 150.0.7871.252; pinned binary/source archive and unchanged wrapper | Preserve exact version, compiler/build config, patches and archive hashes in product inventory |
| Framework/resources | Complete pinned framework, `libcef_sandbox.dylib`, ANGLE/Vulkan resources and locale data retained | Verify exact layout after final assembly and outside checkout |
| Helper roles | Five roles present with own IDs; sandbox initializer precedes framework load | Verify actual launch roles, policies, helper cleanup and role-specific release entitlements |
| ARM64 | `lipo` inspection for main/helpers/framework | Repeat on exact shipping binaries and declared macOS range/second Mac |
| Source and notices | CEF BSD license and upstream attribution retained; see issue below | Complete Chromium/Rust notices and corresponding source/build material for final linked payload |
| Signature | Local seals pass; no publisher identity claimed | Separately authorized Developer ID signing, consistent Team ID and final hashes |
| Hardened Runtime/JIT | Not enabled in these ad-hoc fixtures | Verify V8/graphics with minimal entitlements on the release candidate |
| OS confinement | CEF loader configured; limited negative probe described separately | Browser/renderer/GPU/network matrix must close before third parties |
| Keychain | Explicit test backend in artifact | Production-safe credential behavior must be demonstrated before distribution |
| Integration packaging | Lab host is a separate `.app`; no main Motive bundler edits | H17/H20 handoff, nested placement, resource discovery, single owner and source adapter |
| Notarization/Gatekeeper | Not performed | Explicit future authorization, notarize/staple exact artifact and test downloaded/quarantined offline launch |

The current [CEF signing guidance](https://chromiumembedded.github.io/cef/code_signing.html)
requires complete bundle assembly before signing, nested code signed before
containing bundles, and entitlements assigned per executable. `--deep` is useful
for verification here; it is not a substitute for explicit inside-out signing.
Use consistent signing identities across bundled libraries before considering
library-validation exceptions. No release entitlement or identity was added by
this audit.

The exact Chromium 150
[renderer](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/app/helper-renderer-entitlements.plist)
and [GPU](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/app/helper-gpu-entitlements.plist)
reference files contain `com.apple.security.cs.allow-jit`. The
[main-app reference](https://github.com/chromium/chromium/blob/150.0.7871.252/chrome/app/app-entitlements.plist)
contains camera, audio input and other device capabilities. A visual-only host
must review those individually; copying the whole browser capability set would
expand its intended surface. Exact plist hashes are in
[the H19 source index](../research/h19-source-index.json).

Apple's [JIT entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-jit)
permits `MAP_JIT` under Hardened Runtime. That exception does not imply arbitrary
filesystem or network access. [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
protects runtime integrity and places entitlements on executables; it is distinct
from App Sandbox resource confinement. No speculative
`allow-unsigned-executable-memory`, `disable-library-validation`,
`disable-executable-page-protection` or `get-task-allow` exception is justified by
the laboratory result.

## Notices and size reduction

The initial H19 inventory found `CEF-LICENSE.txt` but no standalone Chromium
credits file in the assembled `.app`. The pinned SDK supplies `CREDITS.html`.
This was a concrete packaging omission, separate from runtime rendering. The
final H19 build now verifies both notice files against the pinned SDK archive
and includes `Resources/Chromium-CREDITS.html` byte-for-byte. The final inventory
confirms the file, hash and size; the original omission report remains retained.
Copying it is necessary notice preservation, not evidence that every final
distribution obligation is satisfied. The existing [license audit](../research/license-review.md)
and [native attribution](../poc/browser-host/native/NOTICE.md) remain historical
records. This audit does not replace full license/source review of the final
binary or imply a source-reproducible CEF build from a small file subset.

Locale payload is measurable, but no locale/resource removal is accepted here.
Deleting the 48.199 MiB locale set would need a declared locale policy plus
startup, fallback-font, international text, error UI, resource lookup and helper
tests on the pruned, re-signed bundle. No such candidate was built. Framework,
ICU, sandbox dylib, graphics libraries and required `.pak`/snapshot resources
must not be removed merely to hit a size target. The safe size benefit already
available is one immutable runtime installation serving several owned widgets.
