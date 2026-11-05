Reviewed **13d7d8bd71**, both firmware diffs, and the host changes. No builds or file changes. The exhaustive checker passes at K=300/64/640; the generator matches `curve12.h` and rejects gamma 0 and −1.

The ordinary encoding/value paths are fixed. These issues remain:

1. **P2 — returning before a flush still defeats initialization.** [rgb_matrix.c:357](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:357), [rgb_matrix.c:627](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:627).

   Jellybean committed → DRIFT paints one chunk → Jellybean before either flush leaves `rgb_last_effect == Jellybean`. Initialization is suppressed, and DRIFT’s approximately 17 LEDs become chroma at the Jellybean flush. They appear markedly dimmer or dark and retain DRIFT’s colours until randomly repainted. At minimum speed, a particular LED waits approximately **162 seconds on average** for a drop.

   The timing window is narrow—several main-loop passes—so ordinary browsing is unlikely to trigger it, but timed host writes or cancellation just after preview activation can. This is persistent buffer contamination, not the accepted single-field tearing.

   **Comparing current mode with last-flushed mode cannot catch it:** both are Jellybean. A cheap guard is in `rgb_task_start()`: before replacing `rgb_current_effect`, invalidate `rgb_last_effect` when the newly selected effective renderer differs. This uses existing state and also covers `NONE`.

   That matters for another inherited QMK case: disable → `NONE` clears the buffer → enable before the off flush. The unchanged last-effect/enable trackers suppress Jellybean’s initialization, leaving the clear to recover through drops. Completed off/on cycles work correctly. The narrowed remainder of code P1.4 merits P2.

2. **P2 — pattern activation can change encoding before changing bytes.** [rowisr_diag.c:419](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:419), [rgb_matrix.c:459](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:459).

   Finish a dim Solid render and its indicator hook; then receive the pattern command before the next pass’s flush. `wide_blocked` becomes true immediately, but the buffer still contains Solid chroma. Solid red at v=64 consequently jumps from **53 to 1,195 ticks** until the next pattern-painted flush—even when the requested pattern is black.

   Both raw-HID handling and menu housekeeping can run in this interval. Activate the block when the indicator hook actually installs the raw bytes, or restart rendering on pattern entry so the pending chroma frame cannot flush as bytes.

3. **P2 — pattern release does not clear LEDs excluded by flags.** [rowisr_diag.c:420](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:420), [jellybean_raindrops_anim.h:6](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/animations/jellybean_raindrops_anim.h:6).

   Reinitialization fixes release with the normal all-LED flags. With unchanged flags excluding LEDs—for example `LED_FLAG_NONE`, reachable through QMK’s flag-step keycodes—the effect skips those LEDs even during initialization. Raw pattern bytes therefore survive indefinitely and become chroma again. Clear the complete render buffer on release before requesting initialization.

4. **P2 — the tap fallback hides transport/protocol failures too.** [overrun_diag.py:114](/Users/jdlien/code/ak820-pro/scripts/overrun_diag.py:114).

   `SystemExit` also means timeout in `current_map.xfer()` and short/wrong-op reply in `op()`. Those now become `{available: False, bytes: 0}`. I verified this with isolated mocked calls. The missing-tap case works, but only an explicitly unsupported op 15 should take this fallback; other failures must remain failures.

5. **P2 — the expanded validation finding is only partly closed.** [ROW-ISR-PLAN.md:1098](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1098), [check_curve12.py:22](/Users/jdlien/code/ak820-pro/scripts/check_curve12.py:22).

   Exhaustive arithmetic is covered. Deterministic interruptions at every chunk boundary, the pending-flush pattern-entry case, and four-field emitted-tick accounting with forced omissions remain uncovered. The accepted camera gate and conversion/handler timing measurements also remain validation obligations; this read-only round does not close them.

6. **P3 — superseded descriptions remain alongside their corrections.** [ROW-ISR-PLAN.md:1011](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1011), [rowisr.c:237](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:237).

   The plan still describes CIE after RGB multiplication, wrapper-owned value/dirtiness, per-render cancellation, guaranteed invisible tearing, and hue preservation/even steps to the bottom. The disposition paragraph corrects these, but the earlier statements remain contradictory. Driver comments still reference removed `sn32f2xx_wide_frame()` and the handler’s former LUT reads.

Disposition of **every prior P1/P2**, numbered in their original order:

| Prior finding | Disposition |
|---|---|
| Design P1.1 / code P1.1: wrapper-owned encoding, aborted render | **Closed.** One Solid chunk followed by completed DRIFT takes the byte path from DRIFT’s mode. No retained wrapper flag exists. |
| Design P1.2 / code P1.3: no-drop Jellybean brightness | **Closed.** Flush reads capped value independently of wrapper activity; unchanged chroma is reconverted when value changes, including zero. |
| Design P1.3 / code P1.2: unchanged-byte encoding transitions | **Conversion trigger closed.** `last_wide` catches identical-byte transitions. Pattern-entry sequencing remains issue 2. |
| Design P1.3 / code P1.4: raw ownership and retained buffers | **Partly closed.** Normal pattern release repaints Jellybean; round trips and excluded LEDs remain issues 1 and 3. |
| Design P2.1: chunk lifecycle/value policy | **Partly closed.** Flush-time value is sound; aborted-return initialization remains issue 1. |
| Design P2.2 / code P2.1: unmasked conversion | **Accepted design change; camera gate outstanding.** The flush now accurately names the relaxed coherence. |
| Design P2.3: conversion explanation and old/new differences | **Differences explicitly accepted.** Remaining contradictory documentation is P3 above. |
| Design P2.4: arithmetic and low-end contract | **Closed by implementation/checks and accepted quantization limits.** |
| Design P2.5 / code P2.2: fixed mux-power term | **Accepted, unfixed model debt.** Dither-only frames still accrue continuous `lit_ms`; emitted-tick accounting does not remove that bias. |
| Design P2.6: tap-enabled RAM budget | **Closed by declaring that configuration unsupported.** No new build-size claim made here. |
| Design P2.7: expanded gates | **Partly closed; issue 5.** |
| Code P2.3: diagnostics fail without tap | **Missing-tap scenario closed.** The broader exception suppression is issue 4. |

The other requested lifecycle checks hold:

- **Value between chunks:** harmless for wide effects because every chunk stores full-value chroma; one capped value scales the complete buffer at flush. This does not promise simultaneous hue/saturation updates across chunks.
- **Ladder caps:** `apply()` updates the cap/scale and requests initialization, aborting pending rendering. The eventual flush uses the new cap.
- **Disable/suspend/wake:** zero bytes remain zero under either encoding. After a completed off flush or suspend flush, initialization repaints on return. Deep sleep still requires a committed dark frame; wake’s cap change restarts rendering. The rapid off/on exception is issue 1.
- **Profiles and lighting previews:** they use the same QMK mode/HSV setters. Brightness changes inherit the fix; rapid mode round trips inherit the remaining tracker hole.
- **Pattern re-init interactions:** it changes neither preview snapshots nor saved settings. Repeated ladder/release initialization requests safely coalesce. It intentionally resets animation state—Jellybean colours, Heatmap history, RAINFALL state and DRIFT position—and does not itself replace the retained wake-dark frame.

NOT READY