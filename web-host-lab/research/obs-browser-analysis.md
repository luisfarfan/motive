# OBS Browser audit — checkpoint A

Inspected full source snapshots, not just README, on 2026-11-18. The lock and
`evidence/source-inventory.json` identify archive and individual source hashes.
`evidence/obs-browser.diff` preserves the complete A→B diff.

## Exact references

- A: OBS 33.0.1 gitlink `d4db73e7e5d5b51d853177c8cddc796715a8ac84`, browser 2.27.5,
  already identified by [H11](../../docs/h11-browser-spike.md).
- B: official master `08a0ada1d77b7003735823ff07cf1be1fb427ac1`, browser 2.27.6.
- [A source](https://github.com/obsproject/obs-browser/tree/d4db73e7e5d5b51d853177c8cddc796715a8ac84),
  [B source](https://github.com/obsproject/obs-browser/tree/08a0ada1d77b7003735823ff07cf1be1fb427ac1).

## Responsibility and execution trace

There is no independent BrowserManager library to link. `obs-browser-plugin.cpp`
owns static manager state, initialization, source registration, frontend events,
websocket vendor integration, profile migration and shutdown. On macOS,
`obs_module_load` dynamically loads CEF; lazy `obs_browser_initialize` calls
`BrowserInit` on the Qt path. `CefInitialize` enables OSR, external message pump,
module profile/cache, fatal logs and **no_sandbox=true**. The non-Qt manager
thread exists in source but is not the configured macOS path. Simply selecting
it is not an AppKit integration proof.

`BrowserApp` combines browser-process initialization and renderer/V8 callbacks.
`BrowserSource::Tick` queues deferred creation after the CEF-started event.
`CreateBrowserSync` supplies viewport/FPS, optional shared textures and a null
request context (global context). `BrowserClient` holds the source back-pointer
and implements render, permissions, requests, audio, context menu and lifecycle.
This is one CEF infrastructure for many sources, with no per-element trust domain.

## Qt and frontend coupling

`CMakeLists.txt` links libobs, frontend-api, websocket-api and nlohmann_json;
`cmake/os-macos.cmake` unconditionally requires Qt Widgets and enables
`ENABLE_BROWSER_QT_LOOP`. Panels are optional, this loop is not. `browser-client.cpp`
also includes QApplication/QThread/QToolTip outside that loop macro.
`BrowserSource::ExecuteOnBrowser` checks `qApp->thread()` and can wait synchronously.
`BrowserTask::Execute` posts through Qt after CEF task delivery; its comment records
why running tasks directly interfered with the pump. `MessageObject` uses a mutex
and unbounded deque, queued invocations, a repeating 33 ms timer, and delayed pump
work capped at 33 ms. `Render` can also request message-loop work. These are OBS's
frontend scheduling choices, not CEF API requirements or a media clock to copy.

Remove panel widgets, tooltip UI, menus, source properties, hotkeys, profile
migration and OBS frontend notifications. Replace scheduling with a dedicated
AppKit main-thread host using CEF's upstream loop/example. Keep GPUI separate;
do not run a nested CEF loop inside Production. A later shared-process AppKit
integration would need its own external-pump/reentrancy acceptance.

## OSR, textures and timing

`GetViewRect` returns source dimensions. CPU `OnPaint` ignores PET_POPUP, accepts
the full BGRA image and uploads through `gs_texture_create`/`gs_texture_set_image`
under `obs_enter_graphics`. Dirty rectangles are ignored. Resize destroys/recreates
textures. `WasResized`, `WasHidden` and `Invalidate` drive visibility and resize.
This is useful proven behavior, but its direct libobs calls must not occur in an
isolated browser process. Our boundary copies callback bytes before returning;
Production later uploads the latest accepted complete frame.

Accelerated code accepts `CefAcceleratedPaintInfo` on modern CEF. macOS wraps
`shared_texture_io_surface` with `gs_texture_create_from_iosurface`; Windows and
Linux have separate implementations. The pinned CEF header requires reopening
each delivered resource and copying into client-owned storage before callback
return. An OBS wrapper is not evidence for ownership across our process boundary.
No IOSurface/Metal zero-copy claim is made. The CPU path is the initial direction.

`BrowserSource::Render` uses ONE/INVSRCALPHA blending and sRGB texture sampling;
this supports the premultiplied-alpha interpretation. The OnPaint header itself
specifies BGRA, upper-left origin and width*height*4, not a complete color contract.
Transparent background is supported by CEF browser settings. Edge pixels and
sRGB/premultiplication still require the native fixture and libobs composite test.
Custom FPS or external begin-frame can control requested rendering cadence; OBS
tick remains the output clock. No callback or MCP timestamp should become AV PTS.

## Lifecycle and failure

Source destruction marks `destroying`, releases textures, unlinks from the list,
then queues deletion. `ActuallyCloseBrowser` detaches the back-pointer, hides and
calls `CloseBrowser(true)`. Module shutdown drains pending browser tasks and calls
CEF shutdown on the Qt path; the other path quits and joins its manager thread.
Our host must additionally track `OnBeforeClose` for every accepted browser,
stop accepting operations, cancel watchdogs, invalidate generations and confirm
the entire helper tree is gone. A queued close is not completed destruction.
Renderer termination in OBS logs an error; this is not per-instance bounded
crash recovery. Visibility may close/recreate when shutdown-on-invisible is set;
otherwise hiding/throttling is not proof that JS timers or network are suspended.

## Bindings, IPC, files and network

`BrowserApp::OnContextCreated` injects `obsstudio` functions; process messages
dispatch permission-level-gated frontend commands including recording/streaming.
`DispatchJSEvent` broadcasts event name plus JSON to renderer frames. Reuse CEF's
message transport, not this authority model. Motive needs allowlisted visual data
and generation/sequence/size/rate/deadline checks outside JavaScript.

The local `http://absolute/` scheme decodes URL paths twice and opens files using
`CefStreamReader::CreateForFile`. It checks IP-shaped paths but has no Motive
inventory confinement. The request handler is selected for Origin:null and
returns RV_CONTINUE. The permission handler accepts loopback-network permission.
Popups and context menus are blocked in the source client, but that does not deny
subresource requests, external navigation, WebSocket, WebRTC, downloads or all
browser-process background services. `BrowserDummyClient` closes unmanaged Chrome
windows and rejects their commands/navigation; retain the defensive concept.

The helper entry point loads CEF and calls CefExecuteProcess; it does not initialize
`CefScopedSandboxContext`. A use-mock-keychain switch is present; it is not an OS
Keychain access boundary. Removing frontend bindings reduces exposed authority,
but enabling Chromium's renderer sandbox alone cannot prove no network/host reads:
browser/network/GPU processes have distinct privileges. See the security model.

## Audio, build and distribution

Audio can play through Chromium unless explicitly muted. When rerouted, CEF audio
callbacks map channels and send float packets to OBS with CEF's supplied timestamps.
H16 drops audio entirely, denies devices and keeps explicit host mute; no new DSP
or adapter into H10. A later audio feature needs a separate contract and tests.

Build requires OBS build helpers, CMake >=3.28, C++20, CEF >=95, Qt Widgets,
libobs/frontend/websocket and nlohmann_json. A plugin-only source checkout does
not pin a CEF artifact; the parent OBS CMakePresets supplies that pin. macOS builds
generic/GPU/Plugin/Renderer helper bundles with role entitlements and ARM64 CEF.
Existing binary inventory proves ARM64 artifacts exist, not safe embedding.
Signature, framework layout, helper names, JIT permissions and notarization are
separate gates. Do not copy permissive OBS helper entitlements blindly.

## Recent revision: what changed and what did not

The exact diff has four changed/added files: browser-app.cpp, browser-version.h,
cmake/os-macos.cmake, cmake/macos/Helper.plist.in. Sign-in preferences were replaced
with allow-browser-signin=false; helpers gained an explicit plist and LSUIElement.
This fixes metadata behavior relevant to invisible helper apps. Rendering,
source lifecycle, request policies, frontend bindings, Qt coupling and no_sandbox
remain identical between these pins. The conclusion is from their actual diff,
not an assumption that every H11 finding remains current forever.

Validation: two checksum-verified complete source archives; per-file inventory;
full diff; read-only installed framework/helper metadata. Native execution: NONE.
