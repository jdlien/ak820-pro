**NOT READY for stages 0–3 as written.** One blocking area remains: D3/D10’s timestamp validity. The third review’s two waveform must-fixes are substantively met; its long-gap must-fix is not.

No files were modified or builds run. Inspection stayed inside the repository.

1. **Must-fix before building — D3 step 1, D10 and stage 2: the new coarse clock does not establish validity.**

   [D3](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:403) counts **serviced interrupts**, not elapsed 50 µs periods. Its claim that this clock stops only when every interrupt stops is false:

   - Priority-0/1 handlers can delay it and collapse multiple ticks into one service, as the existing [gap monitor explicitly documents](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/overrun_diag.c:198).
   - The light-sleep controls can [stop the tick independently of matrix scanning](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:109).
   - It starts in [keyboard post-init](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:65), after D1 requires acquisition to start.

   Agreement between this count and the modulo hardware counter is therefore insufficient. For example, an interruption lasting one CT16B5 wrap plus approximately 50 µs can leave the fine difference around 50 µs and only one coarse tick serviced afterward. Both can agree while hiding approximately 349 ms. Calling such interruptions “outside the bound” does not detect them. Nor do the existing stall counters independently rescue this: their [software time extension also requires observation at least once per hardware wrap](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/platforms/chibios/timer.c:16).

   **Fix:** specify an elapsed-time source that survives the supported interruptions, or a proven observation bound with explicit invalidation whenever it cannot hold. Define validity during startup and independent tick stop/restart, and use it consistently at entry, arm and exit. Define recovery and exclude invalid intervals from apparently healthy timing statistics.

   Put the half-wrap, full-wrap and multiple-wrap injections—including after arming and with the coarse tick unavailable—into the **operative stage-2 gate**. [Revision 5’s disposition claims these tests](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1209), but [stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:768) still specifies only several-slot delays.

The remaining factual corrections are nonblocking:

| Severity | Where and evidence | Fix |
|---|---|---|
| **Should-fix** | [Rig item 4](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:916): the 74LVC1G17’s “few pA” leakage and approximately 5 pF input are unsupported by the supplied sources. | Require a specified manufacturer/variant’s worst-case leakage, capacitance and pulse-transfer specifications. Keep the loading qualification; do not treat the component name as proof. The qualified scope-probe alternative remains usable. |
| **Note** | [Rig item 4’s minimum widths](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:900) disagree with [D4’s scaling](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:491). At nominal calibration, byte 1 produces approximately **208 ns at stage 2, 104 ns at 125 µs slots, and 41.7 ns at 62.5 µs slots**. | Correct the cadence labels and derive widths from the actual LUT. The mandatory 20.8 ns test already imposes the stricter instrument requirement. |
| **Note** | [“The instruments”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:176) still initially calls `raw_edges` a count of differing rows, then corrects itself later. [The implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:127) counts changed bits. | Correct the first sentence; differing rows belong to `cooked_changes`. |

The waveform requirements now prohibit the loading divider, cover the USB rail, require input-mode qualification, and exclude 24 MHz capture from minimum-pulse acceptance. Those changes satisfy the third review’s other two must-fixes.

The other checked claims hold: write keys, masks, IOEN returning pins to GPIO, documented STOP clearing CEN, GPIO atomics, I2C direction switching, conditional light/cadence arithmetic, and the saved object/ELF resource figures. I found no additional running interrupt-side GPIO MODE/CFG writer. Combined STOP/RST behaviour and the old pulse energy appropriately remain hypotheses gated by measurement.

The earlier publication, scan fairness, boot priming, sleep/bootloader quiescence, brightness calibration, priority and SPI safeguards remain present. Consolidation still permits a swallowed short press and a ≥25 ms pass; those are explicit existing exceptions.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under the same condition.** Its normalization, literal terminals, low-code comparisons and repeated coexistence gates remain intact; 62.5 µs remains experimental.