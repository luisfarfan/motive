# Third-party components

Motive's original code is GPL-3.0-or-later; see the root LICENSE. Dependencies
retain their licenses. This source repository does not include downloaded OBS
binaries, recordings, vendor assets or the `.deps` directory.

| Component | Pinned version | License / source |
|---|---|---|
| OBS Studio / libobs and official plugins | 33.0.1 | [GPL-2.0-or-later](https://github.com/obsproject/obs-studio/blob/33.0.1/COPYING) |
| GPUI Kit | 0.10.0 | [Apache-2.0](https://github.com/longbridge/gpui-kit) |
| GPUI (`gpui-pre`) | 0.3.12 | Apache-2.0; exact crate metadata and source are available through Cargo.lock |
| SIMDe | 0.8.2 | [MIT](https://github.com/simd-everywhere/simde/blob/v0.8.2/COPYING) |

The bootstrap preserves the complete OBS app, its source archive and SIMDe
source. The development bundle references those local components. The source
archives, download URLs and SHA-256 digests are defined in `scripts/bootstrap.py`.
Cargo.lock identifies all Rust dependencies; `cargo metadata --locked` exposes
their declared licenses and package locations.

The packaged OBS app contains further components, including FFmpeg and x264.
A complete notices inventory, corresponding-source distribution process and
self-contained bundle must be completed before binary releases. No binary
release is published here. This note is an engineering inventory, not a legal
opinion or a claim that a distributable package has passed license review.

The README banner and the controlled pattern/window/overlay graphics are
original project assets. No proprietary Meld assets or source are included.
