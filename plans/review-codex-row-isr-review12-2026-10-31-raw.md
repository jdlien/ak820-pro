**NOT READY for stages 0–3 as written. One must-fix remains; it does not reopen the withdrawn battery long-gap guarantee.**

1. **Must-fix before building — D3 step 1 and stage 2: remove the unsupported silence-to-observation bound.**

   [D3’s case 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:497) correctly defines the guard using **observation gaps**, but then asserts that endpoint offsets total under 100 µs and therefore every silence under 7.9 ms is exact.

   That contradicts the plan’s supported operation:

   - With the tick stopped, D3 itself specifies observations **625 µs apart**. A 7.6 ms mask starting 500 µs after the last observation produces a gap exceeding 8.1 ms: correctly **INVALID**, despite the “under 7.9 ms” promise. Independent tick stopping is implemented in [sleep.c](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:109).
   - With the tick running, its nominal 50 µs period does not bound service latency. The [gap monitor](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/overrun_diag.c:198) explicitly includes higher-priority interference, and [UART-LATENCY-PLAN](/Users/jdlien/code/ak820-pro/plans/UART-LATENCY-PLAN.md:214) rejects a per-byte estimate as a whole-handler bound.

   [Stage 2’s endpoint budget](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:940) carries this same tick-based assumption into its predictions.

   **Fix:** state exactness solely in terms of the resulting observation gap. Remove the universal 100 µs allowance and 7.9 ms silence promise; use the recorded endpoint offsets and their uncertainty for each operating mode. Qualify row-only exactness on another observer continuing to maintain a valid extension. Add near-8-ms, phase-varied injections with the tick running and independently stopped.

The eleventh review is therefore **partly met in the operative text**: command-round-trip timing is removed, separate markers cover nested holds, marker/NVIC transitions exclude preemption, capture-clock qualification is required, and the watchdog inference is gone. The observation-endpoint correction remains incomplete.

The other checked register/key/control masks, STOP clearing CEN, IOEN returning pins to GPIO, GPIO atomics, interrupt-side MODE/CFG ownership, I2C direction switching, conditional light arithmetic and resource figures agree with the sources. I independently checked the saved objects and both named ELFs.

I found no further blocker or regression in the earlier matrix-publication, scan-fairness, brightness-calibration, priority, SPI, sleep or bootloader safeguards. Stop/restart waveforms, physical colour mapping, baseline energy and settling remain appropriately gated measurements. **The retained consolidation exception can still swallow a short press and exceed 25 ms.**

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under that condition; 62.5 µs remains experimental.**

All inspection stayed inside the repository. No files were modified and no builds ran.