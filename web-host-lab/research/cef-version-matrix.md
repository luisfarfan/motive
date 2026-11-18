# CEF version matrix

Read actual distributed headers and README, not framework CFBundleVersion alone.
No OBS/CEF upgrade was applied to Motive. Downloaded binaries remain unexecuted.

| Item | A: H11 / OBS 33.0.1 | B: recent official reference |
|---|---|---|
| OBS Browser | d4db73e7e5d5b51d853177c8cddc796715a8ac84 / 2.27.5 | 08a0ada1d77b7003735823ff07cf1be1fb427ac1 / 2.27.6 |
| Parent dependency evidence | OBS 33.0.1 CMakePresets.json | OBS master 717cfa8b7e633853cd21ad2cc656185b3b4255bb CMakePresets.json |
| Archive | cef_binary_7871_macos_arm64.tar.xz | cef_binary_7871_macos_arm64_v2.tar.xz |
| SHA-256 | 0343233fc462384c2f1f58a4222028bc6171f05948a822241f89df2faa7cee8d | f1693ef12b28df06bbd9ebf215c9fe2d84e3066c220b905e71dc033bd5b6fbfc |
| CEF version | 150.0.19+gcf60f42+chromium-150.0.7871.252 | 150.25.31-7871_obsproject.3563+gabc1ece+chromium-150.0.7871.287 |
| CEF source | chromiumembedded/cef cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3 | obsproject/cef abc1ece6a66997894c4c953ed24937603fbd74b4 |
| Chromium | 150.0.7871.252 | 150.0.7871.287 |
| Sandbox | M138+ dynamic libcef_sandbox.dylib, scoped helper initialization | Same API generation; own complete distribution |

OBS Browser standalone does not lock CEF. B pairs its current source with the
current parent dependency manifest for comparison; it does not claim a released
OBS binary containing that combination. B's version suffix identifies an official
OBS fork. Attempting its commit under chromiumembedded/cef returned 404; the
correct obsproject/cef source was then resolved. See research-limits.json.

Headers are kept in separate roots. Relevant OnPaint/GetViewRect, lifecycle,
permission/request, macOS sandbox and wrapper APIs are compared byte-for-byte;
generated API version/hash and resource tables can differ. AppleDouble `._`
archive metadata is not an API difference. `evidence/cef-header-diff.json` records
both kinds separately. Never pair v2 headers with A's installed framework.

Both OnPaint APIs specify complete BGRA, upper-left, width*height*4; transparent
windowless backgrounds are documented in cef_types.h. OnAcceleratedPaint says
IOSurface on macOS and limits the delivered resource to callback lifetime.
The old general-usage text saying accelerated OSR is unsupported is not sufficient
to override these versioned headers. Neither statement proves runtime correctness.

Use A for the first compile-only fixture, then compile the same adapter against B.
Runtime choice remains gated on security patches, matched helper/framework
packaging and measured results. Merely changing the browser plugin to 2.27.6
does not incorporate the v2 CEF fork or demonstrate its sandbox behavior.

Sources: [A parent](https://github.com/obsproject/obs-studio/blob/33.0.1/CMakePresets.json),
[B parent](https://github.com/obsproject/obs-studio/blob/717cfa8b7e633853cd21ad2cc656185b3b4255bb/CMakePresets.json),
[A CEF](https://github.com/chromiumembedded/cef/tree/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3),
[B CEF](https://github.com/obsproject/cef/tree/abc1ece6a66997894c4c953ed24937603fbd74b4),
[CEF sandbox](https://chromiumembedded.github.io/cef/sandbox_setup).
