**NOT READY for stages 0–3 as written.** The remaining blocker is the injection timing contract. This does not reopen the withdrawn battery long-gap guarantee.

1. **Must-fix before building — stage 2/D3: finish the tenth review’s timing correction.**

   The separate D15/C15 markers correctly address nested holds, and the pulse-gap method is withdrawn. However, [stage 2 still requires timing around the raw-HID command](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:908), contrary to both the [tenth review](/Users/jdlien/code/ak820-pro/plans/review-codex-row-isr-review10-2026-10-31-raw.md:3) and revision 12’s claim that this instruction was removed.

   The new uncertainty budget also needs a precise endpoint contract. [“One store each end, under 0.1 µs”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:925) does not bound the separation between a marker edge and interrupt suppression/restoration. The [NVIC disable implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/common/ext/ARM/CMSIS/Core/Include/core_cm0.h:659) includes a register write and barriers; row-only suppression leaves higher-priority handlers enabled.

   Moreover, D3’s guard measures **last observation to next observation**, not merely the marked mask duration. A 7.99 ms mask beginning 40 µs after the last observation can exceed the 8 ms guard, contradicting [“any silence … under 8 ms: exact”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:494). Stage 2’s uncertainty interval currently omits these endpoint offsets.

   **Fix:** remove command-round-trip timing as an acceptance method; make the independent markers authoritative. Specify bounded marker/mask ordering, preventing preemption between each paired transition. Include observation-to-marker offsets and return latency in predictions, or record synchronized observer endpoints. Qualify the actual capture-clock accuracy rather than assuming ±50 ppm. State the 8 ms cases in terms of the resulting observation gap.

2. **Should-fix — D3: the watchdog inference remains despite its disposition.**

   [Lines 545–548](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:545) still say a silence exceeding 13 seconds either reset or ran in degraded mode. The preceding disclaimer does not make that inference valid: the [ILRC source gives a graph, not guaranteed limits](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:146), and [12.3 seconds is an observation](/Users/jdlien/code/ak820-pro/docs/hardware.md:350).

   **Fix:** say intervals beyond 13 seconds are outside the USB proof’s scope, independently of watchdog mode. The revised tolerance arithmetic itself is correct.

The other checked register keys, control/GPIO masks, STOP clearing CEN, IOEN-to-GPIO behavior, interrupt-side MODE/CFG ownership, I2C switching, conditional light arithmetic and resource figures agree with the sources. I independently checked the saved objects and both named ELFs.

I found no further readiness blocker or regression in the earlier matrix-publication, scan-fairness, brightness-calibration, priority, SPI, sleep or bootloader safeguards. Stop/restart waveforms, physical colour mapping, baseline energy and settling remain appropriately gated measurements. The explicitly retained consolidation exception can still lose a short press and exceed 25 ms.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under that condition; 62.5 µs remains experimental.**

All inspection stayed inside the repository. No files were modified and no builds ran.