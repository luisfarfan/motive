# Updating the small host

Keep Chromium/CEF engine, wrapper, sandbox loader and platform implementation
upstream. Motive maintains only package/resource policy, typed projection,
lifecycle/generation/watchdog, bounded CPU frame boundary, AppKit host glue and
libobs source adapter. No Qt compatibility layer, OBS profile migrator or private
GPU implementation. Every extracted upstream fragment needs a commit/file origin,
license, small explicit patch and a test for the reason it was changed.

`sources.lock.json` is reviewed input, never rewritten by fetch. `fetch_sources.py`
verifies archive SHA-256, optionally downloads missing archives, and extracts only
to explicit lab caches. `compile_native_api.py` verifies extracted headers against
the archive and compiles identical native code separately for both CEF pins.
`audit_sources.py` records API/source differences without executing binaries.

Update procedure, manually initiated in a future isolated change:

1. Resolve official OBS Browser and parent CEF manifest to exact commits; identify
   OBS's CEF fork and Chromium commit from its actual distributed README/header.
   Check CEF/Chromium security advisories and release notes, including patches
   beyond a major version number. Do not label an old pin secure from a clean build.
2. Review new dependency checksums/source/licenses. Fetch to a new cache directory;
   never replace a framework under a live helper or pair old wrappers/new headers.
3. Diff CEF headers, wrapper/sandbox bootstrap, Chromium patches, helper names,
   entitlements, framework resources and OBS lifecycle/render/client changes.
4. Run the contract suite and both API compile probes. Rebuild the wrapper and
   helpers from the new matched distribution; native linking/signing has its own
   gate. Then run authorized owned-content security and performance corpus, keep
   old/new failures and compare identical workloads. Only one renderer remains.
5. Recheck source notices/corresponding source, final dependency closure, signed
   bundle outside checkout, other supported macOS versions and another ARM64 Mac.
   Any security regression disables third-party execution, not a policy fallback.

Recent-source findings matter: OBS CEF v2 adds always-deny Bluetooth and WebAuthn
patches. It also adds macOS background game-controller monitoring; newer is not
automatically narrower in every capability. The M150 OSR/lifecycle/permission
headers are identical between the inspected distributions except generated
API/resource/version tables, while implementation patches differ. Keep that
distinction in each update review. No automatic CEF/OBS upgrade or scheduled
automation is installed by this laboratory.

Authoritative tracking entry points: [CEF project/security updates](https://github.com/chromiumembedded/cef),
[Chromium releases](https://chromereleases.googleblog.com/),
[OBS CEF fork](https://github.com/obsproject/cef),
[OBS Browser](https://github.com/obsproject/obs-browser).
