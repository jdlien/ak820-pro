**NOT READY for stages 0–3 as written.** One must-fix remains. Revision 6 adds the fourth review’s requested tests, but its timestamp-validity algorithm still cannot pass them.

**Must-fix before building — D3 step 1, D10, and stage 2: the observation bound is still circular.**

[D3’s two observers](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:421) extend the same 16-bit counter. When both are prevented from running, neither can distinguish elapsed time from its remainder after wrapping:

- A **350 ms** interruption appears as approximately **475 µs**.
- A **700 ms** interruption appears as approximately **949 µs**.

Both pass the proposed **8 ms** check. At 125 µs cadence, the stated reconstruction can consequently report about four boundaries instead of 2,800. D10 can likewise admit an invalid duration into apparently healthy statistics.

This directly contradicts the observation requirement documented in [the existing time extension](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/platforms/chibios/timer.c:19) and follows from [CT16B5’s counter properties](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:766). Adding another observer improves ordinary coverage; it does not establish validity when both stop. The [12-second watchdog](/Users/jdlien/code/ak820-pro/docs/hardware.md:351) cannot detect a 350 ms interruption that returns.

**Fix:** specify an independent elapsed-time/validity mechanism, or prove an observation bound covering masking and higher-priority handlers, with explicit invalidation whenever that bound cannot hold. Testing the same modulo difference against 8 ms is insufficient. Apply validity consistently across entry, arm and exit, including recovery across an invalidated epoch. Keep the [operative stage-2 injections](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:790), time them independently of the extension under test, and require invalid intervals to remain visibly invalid in acceptance results.

Startup priming, independent tick stopping, and placement of the long-gap tests are now addressed. **The fourth review’s central must-fix is not.**

I found no regression in the earlier accepted publication, scan-fairness, boot-priming, sleep/bootloader, brightness-calibration, priority or SPI safeguards. The requested register/key/mask claims, IOEN-to-GPIO behavior, I2C direction switching, conditional cadence/light arithmetic and saved object/ELF resource figures check out. I found no additional running interrupt-side GPIO MODE/CFG writer. Old pulse energy and stop/restart waveform behavior appropriately remain measurement prerequisites.

The explicitly retained [consolidation exception](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:147) can still swallow a short press and exceed 25 ms; this rewrite does not promise to eliminate it.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under the same condition; 62.5 µs remains experimental.**

Inspection stayed inside the repository. No files were modified and no builds ran.