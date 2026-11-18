# Licenses and macOS distribution — checkpoint L

Review of pinned source licenses and actual package inventory, not release
clearance. No binary was distributed, published, loaded or installed in Motive.

| Material | Evidence | Required treatment |
|---|---|---|
| Motive/H16 | Root Cargo.toml / LICENSE, GPL-3.0-or-later | Preserve source license and corresponding-source availability for distribution |
| OBS Browser | Both pins' COPYING plus per-file GPL-2.0-or-later notices | Keep original copyrights, origin/commit and modification record if copied; provide applicable GPL source/build material |
| OBS base64 helper | Its own permissive notice with origin/modification restrictions | Do not assume every file is GPL; not reused here |
| CEF/wrapper/samples | Both binary LICENSE.txt hashes match; source/sample notices | BSD conditions, disclaimer, copyright and no endorsement; retained CEF license and native NOTICE.md |
| Chromium and third parties | Pinned CREDITS.html / README and framework resources | Ship complete applicable notices and inventory; exact compiled feature/codecs review remains open |
| Rust contract dependencies | Cargo.lock checksums and evidence/rust-dependencies.json | Preserve MIT/Apache/Unlicense/Unicode notices as selected/applicable; inventory includes resolved packages not necessarily linked code |
| Element Lab runtime/fixtures | Existing manifest and package LICENSE, GPL-3.0-or-later | Read-only reuse, preserve origin/version and asset hashes |
| AppKit/Metal/macOS | System frameworks | No copied macOS binaries or private API in this lab |

GPL-2.0-or-later permits choosing GPLv3 for combination with Motive's GPLv3 code;
do not apply that conclusion to GPL-2.0-only dependencies. The upstream license
option is decisive. See the [GNU compatibility FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#AllCompatibility).
Free distribution is still distribution: prepare matching source, changes and build
instructions for the covered binaries. Dynamic linking does not remove license
review. This laboratory transplants no OBS plugin implementation; its Cocoa/helper
boilerplate is attributed to the pinned CEF samples.

CEF's BSD notice does not replace Chromium dependency licenses. The two downloaded
CEF packages include the same CREDITS.html digest, recorded in L-distribution.json;
that alone does not prove every changed compiled dependency has complete notices.
Review actual build provenance, GN flags and codecs before distribution; no patent
or codec clearance is inferred from a binary being available. Qt, nlohmann_json,
OBS frontend and OBS websocket are not dependencies of the selected host.

## Size evidence

Read-only existing OBS distribution: CEF framework regular files total
319,928,674 bytes (305.11 MiB); four helper executables add 2,233,520 bytes, excluding
their other bundle files. A's downloaded Release tree is 321,164,707 bytes; B's is
321,133,294 bytes (excluding AppleDouble metadata). These are different packaging
inventories, not a measured Motive.app delta or an optimization claim. Whole archives
are about 105 MB compressed and also contain headers/wrapper material. Expect
roughly 305–307 MiB of runtime payload before the final own helpers, notices and
packaging decisions; exact Motive.app size and compressed installer are NOT_EVALUATED.
No multiplying framework disk size by widget count: runtime files can be shared.

## Packaging and signature gates

Use the exact distribution's framework, resources, libcef_sandbox.dylib, ANGLE
libraries and matching helpers/wrapper. Preserve versioned framework symlinks and
bundle identifiers; Xcode 26 requirements are described by that distribution's
README. Do not prune pak/ICU/snapshot/locales to claim savings without compatibility
tests. Never reference the developer checkout or `.deps` in a portable app.

Assign entitlements per executable role and sign nested code before its enclosing
bundle. V8 JIT needs review on renderer/GPU helpers. Do not blindly copy OBS's
disable-library-validation/unsigned-executable-memory permissions. Use the matching
Chromium revision's entitlements, own identifiers and minimum required capabilities;
none are changed in this task. Framework dylibs, helpers and outer host each need
verification. See [CEF signing guidance](https://chromiumembedded.github.io/cef/code_signing.html).

Developer ID distribution, hardened runtime and notarization are separate from a
local development signature. Notarization checks submitted software; it is not a
widget sandbox. Validate the final signed package and ticket on another clean Mac
under normal Gatekeeper, without removing quarantine or changing trust/TCC/SIP.
See [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution/).
No certificates, keychains, notarization submission or signing operation occurred.

Release blockers: own linked host/helpers; OS confinement; matching sandbox behavior;
unnecessary permissions; JIT/helper launch; out-of-checkout run; macOS/ARM64 matrix;
complete third-party notices/corresponding source; final signature/notarization.
