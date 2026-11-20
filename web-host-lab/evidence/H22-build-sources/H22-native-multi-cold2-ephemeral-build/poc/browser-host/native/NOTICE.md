# Native fixture provenance and gate

Motive original fixture under GPL-3.0-or-later. Cocoa `CefAppProtocol` dispatch
and helper initialization ordering are adapted from Chromium Embedded Framework
`tests/cefsimple/cefsimple_mac.mm` and `process_helper_mac.cc`, commit
cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3. Copyright (c) 2013 The Chromium Embedded
Framework Authors. CEF BSD license retained in research/licenses/CEF-LICENSE.txt.
The original files retain their per-file notices in the pinned source cache.

Changes: no menus, nibs, browser windows, OBS/Qt/frontend API, arbitrary URL or
command-line passthrough. A compiled three-resource original fixture uses a
private scheme, explicit deny callbacks, independent request context, 640×360/30
OSR and a complete owned BGRA snapshot. Helpers initialize the supported sandbox
before loading CEF. A pending-create count prevents shutdown before creation is
acknowledged; final close of all tracked browsers ends the loop.

`compile_native_api.py` checks both native translation units against **both**
matching CEF header trees at API 15000. It only parses/type-checks (`-fsyntax-only`),
without linking or loading the runtime. No fake CEF headers, mock browser, dylib
load, helper execution or native screenshot is used.

RunOwnedFixture is prepared but has no host executable entry point. Linking a
fixture bundle, starting it, verifying helper entitlements/sandbox, and implementing
the external process watchdog require the next reviewed native step. No CMake is
installed on PATH; the compile-only verifier uses the installed Apple compiler.
Do not link the helper standalone and execute it, nor point it at Motive's .deps.
The separate Rust admission/lifecycle/frame library is not connected via FFI yet.
This is a native API fixture, not a complete Browser Engine or secure product.

The 5 s CEF task is cooperative; it cannot stop a wedged browser/GPU process.
An authorized runner must own/reap the tree independently with a hard timeout,
track CPU/RSS/footprint and prohibit unapproved content. Writes must use a fresh
lab-owned output prefix and private root supplied by that runner. No clipboard,
network/background-service or native sandbox guarantee follows from callbacks.
