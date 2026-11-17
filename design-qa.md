# Native studio visual QA

final result: pass for implemented UI evolution, with the capability limits below

## UI evolution — 2026-11-16–17

Compared the actual GPUI app with the unchanged Phase 1 references at matching
logical sizes, light and dark. No Claude files were modified. Reference captures
from the earlier proxima-browser review were reused because their source did not
change. Preview/active thumbnail contain libobs media, not reference images.

| State | Paired evidence under `var/evidence/ui-evolution/` | Result |
| --- | --- | --- |
| Light studio, 1440×980 | `comparison-ready-1440.png` | Pass; hierarchy/colors/rail/stage retained |
| Dark selected layer, 1440×980 | `comparison-dark-1440.png` | Pass; native numeric inspector and focus |
| Light editor, 1024×780 | `comparison-edit-1024.png` | Pass; two real mixer channels and controls fit |
| Controlled source loss, 1024×780 | `comparison-source-lost-1024.png` | Pass; clear warning, source marker, recording disabled |

New panels use Kit inputs/buttons/popovers/dialogs and the same semantic palette.
H10 expands the audio area for real stereo meters, gain/mute and master, reducing
the immediately visible scene list; both areas scroll independently. Capability
content differs from the illustrative prototype. The stage retains its existing
roughly 32 px height difference, correct aspect ratio and letterboxing. Inactive
thumbnails remain explicitly unavailable. macOS owns the sharing indicator and
window controls. No fake CPU/statistics, agent proposals or preview assets appear.

Five interaction/layout defects were corrected with retained before/after
artifacts: dialog footer, dialog/popover stacking, compact mixer density,
fader pointer focus, and recovery-banner click-through. The final banner fix
only changes hit testing; its appearance matches the paired captures. Real
native recovery and a subsequent 3,478-frame gesture recording passed on the
final binary. Real saturation and gain reduction were also observed in GPUI.

Accessibility checks cover native AX names/roles, Tab/focus, labelled fields,
button activation and slider arrows. Long fractional transforms can scroll
within their focused input; exact f32 precision is retained. Device names may
truncate in the compact rail. A full VoiceOver/large-text audit remains pending.
No unresolved P1/P2 defect remains in the exercised controls; this is not a
claim that the whole Motive UI or future Design System screens are complete.

30 unit tests, Clippy and fmt passed. All 17 H1–H9 suites passed on the first
final-bundle run; both H10 suites passed, with one retained failed pilot attempt
and an unchanged successful retest. See [verification](docs/ui-evolution-verification.md)
for hashes, measurements, repro steps, raw-artifact locations and actual limits.

## Historical UI-0–UI-3 review

The following describes the preceding 7280c5c checkpoint. Its H9-only audio and
CLI-only configuration limits are superseded by the evolution report above.

Source: approved `design/screens/phase-1/`, Phase 1 artboards and the unmodified
local prototype. Implementation: signed native GPUI app, actual libobs preview.
No prototype image is used in the application. Browser reference captures use
only proxima-browser; native interaction/captures use CUA.

The supplied wide screenshots are 1440×900; the artboards specify 1440×980.
The compact supplied screenshot embeds a 1024×700 app in a 1440×900 image.
Fresh reference captures at requested dimensions are used for final comparison;
source fixture media, fake prototype stats and future features are excluded from
pixel equality. Native traffic lights/sharing indicator are macOS-owned.

## Iteration findings

- P1: clicking an inline input moved focus back to its row. Fixed by respecting
  the focused Kit input; real numeric edit retested successfully.
- P1: the measuring canvas had an implicit offset after the program image.
  Fixed with `inset_0`; canvas selection/movement/resize now hit the real bounds.
- P2: the default Kit asset bundle omitted some chosen Lucide icons. Fixed with
  the official complete asset bundle.
- P2: changing the Kit rem base shrank buttons. Restored its 16 px base while
  keeping application text sizes explicit per direction.md.
- P2: long fractional numeric values were clipped. Fields widened for final QA.
- P2: native layer accessibility role hid its child controls. Changed the row
  to a focusable group; input/button children appear in the native AX tree.
- P1: idle capture loss left the header “Listo”. Header now uses the same source
  issue state as the banner and recording is disabled. Retested with a real
  closed capture window.
- P2: recovery inherited dark text on the dark stage in light mode. The button
  now has an explicit white surface and dark text; clicked successfully to
  recover a refused local connection.

- P2: rounding displayed transform values could quantize an unchanged Enter.
  The final formatter preserves round-trippable f32 text. A property regression
  and real native input check preserved X=64.125 without a revision change.

## Fidelity surfaces

Typography uses the native system font with 22 px scene title, 13 px body,
12 px secondary and 11 px notes. Layout uses a 52 px native title bar, 296/232 px
rail, thin separators, a single elevated dark stage, 46 px layer rows and an
inline inspector. Colors come from direction.md in both themes. The approved
M mark path is reused; controls use the bundled native icon library. Image
content is live libobs, so the prototype's illustrative media is intentionally
different. Copy reports current capabilities and real output state.

## Final comparisons

Reference and native captures were presented together in each comparison at the
same logical window size, theme and functional state. The source has illustrative
camera/window imagery and four demo scenes; native captures use controlled
libobs sources and the actual project inventory.

| State | Paired evidence under `var/evidence/ui/` | Result |
| --- | --- | --- |
| Light, ready, 1440×980 | `comparison-ready-1440.png` | Pass with capability differences below |
| Dark, selected layer, 1440×980 | `comparison-dark-1440.png` | Pass |
| Light, inline edit, 1024×780 | `comparison-edit-1024.png` | Pass; no clipped fields |
| Light, source lost, 1024×780 | `comparison-source-lost-1024.png` | Pass after warning/contrast fixes |
| Dark header detail | `comparison-header-dark.png` | Pass: hierarchy, native controls, theme |
| Light inspector detail | `comparison-inspector-light.png` | Pass: row height, text, fields, focus |

Native-only interaction evidence: `final-input-focus-1440.png`,
`final-keyboard-focus-1440.png`, `final-ready-dark-1024.png`,
`final-add-source-popover-1024.png`, `final-precise-field-1024.png`,
`final-connecting-1024.png`,
`final-cancel-pending-1024.png`, `final-output-error-fixed-1024.png`.
`ui1-dark-recording-1440.png` is the earlier real active-recording check;
`editor-recording-resize.png` records resizing during the later decoded recording
(the owner had resized the window for that screenshot). The recording is not a
prototype animation. Earlier failed iterations are retained for traceability.

## Accepted capability differences

- The program uses its actual aspect ratio and letterboxing. Its stage is about
  32 px shorter than the prototype in these comparisons, leaving more space for
  real layer controls; the canvas is not stretched to imitate fixture imagery.
- Inactive scene thumbnails and per-layer image thumbnails need an engine
  capability. They are not substituted with copied prototype assets.
- The meter reflects H9's single real peak. A second stereo bar and fader would
  misrepresent the current audio contract; H10 is a separate task.
- The core retains a lost source's last frame. UI marks the source and shows a
  warning rather than drawing a fake loss slate into the actual program.
- Agent proposals, future multi-output states, fake CPU readings, and additional
  Claude Phase 2–5 screens are intentionally excluded.
- Native traffic lights/sharing indicators, Kit focus/hover behavior and icons
  are platform components; the full-screen screenshot is not a pixel clone.

No unresolved P1/P2 UI defect remains in the exercised flows. This review covers
UI-0–UI-3's implemented scope, not completion of the entire Design System.


Final validation: 24 unit tests, production Clippy, fmt, 17 existing media suites
(with retained failures and clean retests), final-bundle control checks and a
92-frame decoded recording. See `docs/ui-native-verification.md` for bundle
hashes, measurements and the narrow formatter change after the full media run.
