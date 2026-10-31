**NOT READY for stages 0–3 as written.** One correction remains in D3’s observation-gap contract. This does not reopen the withdrawn battery long-gap guarantee.

1. **Must-fix before building — D3 step 1, case 2; stage 2’s timing predictions.**

   [D3 asserts](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:497) that observation offsets total less than 100 µs, making every interrupt silence below 7.9 ms exact. That bound is unsupported and admits a counterexample.

   Suppose the mask starts **49 µs after the last observation**, lasts **7.890 ms**, and a pending USB handler runs for **85 µs** before the tick observes again. The observation gap is **8.024 ms**, so the guard correctly declares INVALID—contrary to the stated guarantee. The [85 µs USB duration is documented](/Users/jdlien/code/ak820-pro/plans/UART-LATENCY-PLAN.md:25); the [tick monitor explicitly includes higher-priority interference](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/overrun_diag.c:198). UART drain loops can add further delay.

   **Fix:** remove the universal 100 µs bound and “under 7.9 ms exact” inference. State acceptance solely in terms of the actual observation gap. In [stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:940), make measured endpoint offsets authoritative: specify synchronized stamps at the marker transitions and adjacent observer samples, including their uncertainty. Alternatively, establish a defensible bound covering accumulated interference. Predictions must use those offsets without clipping them to 100 µs.

The eleventh review is otherwise addressed in the operative text: command-round-trip timing is explicitly excluded; nested holds have separate markers; marker/NVIC pairs exclude preemption; capture-clock qualification is required; and the watchdog inference is removed. The observation-offset bound above prevents calling its must-fix fully closed.

The other checked claims agree with the sources: register keys and masks, STOP clearing CEN, IOEN returning pins to GPIO, GPIO atomics, I2C direction switching, conditional light/cadence arithmetic, and resource figures. I independently inspected the saved objects and both named ELFs. No additional running interrupt-side GPIO MODE/CFG writer surfaced.

I found no regression in the accepted publication, scan-fairness, brightness-calibration, priority, SPI, sleep or bootloader safeguards. Waveform behavior, physical colour mapping, baseline energy and settling remain appropriately gated measurements. **The retained consolidation exception can still swallow a short press and exceed 25 ms.**

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under that condition; 62.5 µs remains experimental.**

All inspection stayed inside the repository. No files were modified and no builds ran.