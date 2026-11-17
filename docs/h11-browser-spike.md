# H11 — Native source inventory and bounded Browser Source spike

Inspected 2026-11-17 against the checksum-pinned OBS 33.0.1 ARM64 distribution
already used by Motive. This spike is **static and blocked before browser
execution**. It does not claim CEF initialization, rendered frames, audio,
performance, or a usable Browser Source in Motive. No plugin, helper, browser,
capture device or signed bundle was started or modified for this inspection.

## Reusable native sources

`file`, `otool -L`, bundle metadata and the official source tree establish:

| Module | Installed ARM64 binary | Source / usable controls | H11 implication |
|---|---|---|---|
| `text-freetype2` | Yes, 33.0.1 | `text_ft2_source` v2; inline UTF-8 text, font face/style/size/flags, two RGBA colors, outline, shadow, wrapping and width | Use `obs_get_latest_input_type_id("text_ft2_source")`; do not build a replacement font renderer |
| `image-source` | Yes, 33.0.1 | `image_source`; file, unload policy, alpha interpretation | Give it only a validated managed asset path; source claims PNG/JPEG/WebP among supported formats, but each exposed format still needs decoded acceptance |
| `obs-ffmpeg` | Yes, 33.0.1 | `ffmpeg_source`; local file, loop, activation/end policy, official play/pause/restart/stop/time/state callbacks | Use local-only validated files and explicitly suppress audio until routed through an H10-owned policy |
| `obs-browser` | Yes, 33.0.1 bundle | `browser_source`, browser 2.27.5; width/height/FPS, local file or URL, custom CSS, visibility and audio controls | Presence does not establish safe embedding in GPUI |

FreeType's macOS default is Helvetica. The registered v1 text source is obsolete;
v2 is the current implementation. It has no text-alignment or background-color
property in this revision: use Motive's existing layout/alignment and a separate
shape/background when needed. Outline/shadow widths are fixed internally, not
arbitrary stroke controls. Keep `from_file=false`; accepting a `text_file` would
create an unrelated filesystem-read capability. These findings come from the
[official text source](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/text-freetype2/text-freetype2.c).

Image paths are consumed by the
[official image source](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/image-source/image-source.c);
its memory query is useful for native diagnostics. The
[media source](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-source.c)
declares both async video and audio. A visual-only H11 adapter should explicitly
set audio mixers to zero, mute, and monitoring off before activation, and retain
those settings on updates. Muting only a UI indicator is insufficient. Pause and
restart use libobs media APIs; do not re-clock decoded frames from MCP.

## Browser binary and embedding constraints

The OBS 33.0.1 source tree pins obs-browser commit
`d4db73e7e5d5b51d853177c8cddc796715a8ac84`; its own version is **2.27.5**.
The installed browser plugin links QtCore/QtGui/QtWidgets **6.11.1**, libobs and
`obs-frontend-api.dylib`. Installed CEF bundle metadata reports **150.0.19.0**;
the CEF executable alone is 218,201,312 bytes. This is disk size, not an RSS
measurement. Four signed-helper bundles exist: OBS Helper, GPU, Plugin and
Renderer, all ARM64. No helper was launched.

The pinned [macOS build](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/cmake/os-macos.cmake)
requires Qt Widgets and enables `ENABLE_BROWSER_QT_LOOP` even independently of
optional browser panels. The
[source lifecycle](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/obs-browser-source.cpp)
uses Qt task dispatch and `qApp->thread()`. Motive has a GPUI/AppKit owner, not an
initialized OBS Qt frontend. **Inference:** loading the binary alone cannot
supply that lifecycle; disabling browser panels alone does not remove it.

The [plugin initialization](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/obs-browser-plugin.cpp)
loads CEF through `CefScopedLibraryLoader`, registers frontend callbacks and
uses a module cache/profile directory. A successful integration must resolve
framework/helper paths inside the intended app, initialize and drain the message
pump, close renderer/GPU processes, and then shut CEF down. The current checkout
bundle's external Frameworks symlink is already unsuitable for strict release
verification; copying or re-signing helpers blindly does not solve that design.

## Isolation stop gate

The pinned implementation is not the requested restrictive widget host:

- `BrowserInit` sets `settings.no_sandbox = true` and passes no sandbox object
  to `CefInitialize` in the [plugin initialization](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/obs-browser-plugin.cpp).
- Local files become `http://absolute/...`. The
  [scheme handler](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/browser-scheme.cpp)
  checks the main-frame origin and rejects IP-like file paths, then calls
  `CefStreamReader::CreateForFile`. It does not confine access to a Motive asset
  root or a declared package manifest.
- The [request/permission handler](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/browser-client.cpp)
  continues resource requests and explicitly accepts loopback-network permission
  on applicable CEF versions. This is not a network-deny policy. The same file
  exposes permission-gated OBS frontend operations to page messages.
- Official [Browser Source documentation](https://obsproject.com/kb/browser-source)
  describes local/remote content, a transparent default stylesheet, configurable
  FPS and page control permissions. Those are useful production features, not a
  filesystem or process security boundary.

The appropriate H11 result is to keep browser input unavailable and continue
native overlays. No arbitrary HTML, URL, JavaScript, CEF arguments or browser
profile is exposed through CLI/MCP. This is a concrete lifecycle/isolation
blocker, not evidence that libobs cannot render browser content in general.

## Controlled fixture and future experiment

`scripts/fixtures/h11-browser.html` is an original transparent local panel with
a two-second moving marker. It has no JavaScript, external assets, links, audio,
network calls or OBS bindings. Its CSP permits only its exact hashed stylesheet.
It is retained **unexecuted**. CSP is defense in depth; it cannot compensate for
the host gaps above and is not proof of sandboxing.

After a reviewed host provides the missing lifecycle and isolation, the bounded
experiment is: start one isolated renderer, use this fixture at 640×360/30 FPS,
record and receive RTMP locally, decode transparency/background and marker
positions, verify monotonic PTS and audio silence, measure total process-tree
CPU/RSS/initialization time, then confirm every helper exits. Stop after two
failed hypotheses rather than turning H11 into a CEF port. No such runtime or
performance measurements are claimed here.

## Future import contract

Accept a versioned package manifest with stable identity, an entry asset ID,
declared immutable asset IDs, bounded viewport/FPS/memory, typed configuration,
and a finite event vocabulary. The native broker owns package resolution;
pages never receive filesystem paths, credentials, the MCP socket, or a direct
Production handle. Events can flow into an overlay, not invoke studio controls.

Default-deny navigation, requests (including localhost/private networks), popup,
downloads, device/clipboard permissions, filesystem and browser control bindings.
Confine package reads using a managed scheme and authorized asset IDs. Enforce
process isolation and resource limits outside the page, use disposable profiles,
disable browser audio until an explicit H10 adapter exists, and make shutdown
observable. Verify attempted traversal, undeclared reads, loopback access and
resource exhaustion with controlled fixtures before importing agent-generated
or third-party content.

StreamElements URLs remain a future explicit remote capability: their hosted
scripts, network services, tokens and event adapters cannot be treated as a
local asset package. Do not silently enable external URLs to claim compatibility.

## Licensing and evidence

The inspected obs-browser source headers use GPL-2.0-or-later and include
[GPL COPYING](https://github.com/obsproject/obs-browser/blob/d4db73e7e5d5b51d853177c8cddc796715a8ac84/COPYING).
[CEF's license](https://github.com/chromiumembedded/cef/blob/master/LICENSE.txt)
has BSD-style redistribution conditions and points to separately licensed
Chromium dependencies. [Qt licensing](https://doc.qt.io/qt-6/licensing.html)
and third-party notices also need an inventory for the actual redistributed
modules. No redistribution/compliance or notarization claim is made by this
development spike; it adds no new shipped dependency.

Private reproducible evidence is in `var/evidence/h11-browser/`: `inventory.json`
(binary metadata, architecture, dependencies and hashes), `submodule.json`
(official tag's gitlink), `sources.json` (URLs and hashes of pinned source files),
and `fixture.json` (hash, CSP hash, `executed:false`). Downloaded official source
is retained there for audit and is not committed. No proprietary source, assets,
REA, CDP or owner browser profile was used.
