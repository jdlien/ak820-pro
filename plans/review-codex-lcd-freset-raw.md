No P1 or P2 regression found against fix A. The reset is safe for the current callers; two nonblocking P3 issues remain.

Reviewed `a75671847b` against `6683c18134`, with ChibiOS-Contrib `5a1674e905`. Line numbers below refer to those commits. Nothing changed; no build or board test ran.

**P1**

| File:line | Finding | Scenario |
|---|---|---|
| — | None found. | — |

**P2**

| File:line | Finding | Scenario |
|---|---|---|
| — | None found in the current call graph. | — |

**P3**

| File:line | Finding | Scenario |
|---|---|---|
| [lcd_bus.c:369](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:369) | **FRESET readback is not a documented completion indication.** The vendor declares it write-only (`__OM`) in [SN32F290.h:2937](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/common/ext/SONiX/SN32F2xx/SN32F290.h:2937). | The loop can exit immediately or consume all 64 iterations without establishing reset completion. It cannot hang. Remove the misleading polling or use documented readable status; adding another FRESET read after the loop would not establish success. |
| [lcd_bus.c:364](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:364) | **The residue count races the idle FIFO ISR.** SPI0’s RX interrupt remains enabled during the drain. This repeats a diagnostic weakness already present in fix A. | The ISR can consume residue first, or between the `RX_EMPTY` test and `DATA` read. Consequently, `strays` can miss entries or count an empty read. No valid transaction is lost here, but the counter is not an exact measurement. |

1. **All four callers are safe under their existing ownership rules.** The polled fill, stream begin and RAM blit call `bus_quiesce()` before the window (`lcd_bus.c:402`, `441`, `576`). Their operations run synchronously on the main thread. The flash blit also quiesces first (`1206`); at its window (`1226`), Prepare has disabled DMA, and neither the flash READ command nor Fire has happened.

   Under the [documented FRESET semantics](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:864), this resets the SPI FSM and FIFOs, not the peripheral configuration registers. It preserves `DMACTRL`, `DMACNT`, `DMAHTCNT`, `DL`, `IE` and the RX threshold. The bitfield assignment preserves the other CTRL0 fields. It does not modify ChibiOS’s software state or the GPIO chip selects. Prepare’s borrowed SPI1 state remains intact for Fire.

2. **The guard is sufficient at these callers, but is not a complete ownership check by itself.** It omits `SPID0.state`, `TX_EMPTY` and `DMAEN`; an independently active FIFO transaction could therefore pass it between frames. I found no current path that permits that overlap: only the main thread starts transfers, synchronous FIFO calls finish before another painter runs, and `blit_done` becomes true after DMA teardown and CS release.

   Normal DMA completion waits for TX empty/nonbusy before publishing completion, so the reset runs at the DMA-to-polled boundary implicated by the evidence. A transient BUSY at entry would skip it—even if `spi0_poll_send()` subsequently waits successfully—but that requires an abnormal state beyond the normal completion sequence. Persistent BUSY follows the existing bounded give-up path.

3. **The wait already has a bound.** Both additions are bounded: 16 drain attempts and 64 reset reads. There is no post-limit failure check, but the more fundamental problem is the write-only readback described above. “Self-clearing” does not establish readable completion semantics. The subsequent sender still checks driver readiness, TX emptiness and BUSY.

4. **No other introduced regression found.** The change adds bounded work without masking interrupts, altering completion callbacks, or widening an interrupt-clear write. It does **not** repair the pre-existing DL change while CS is asserted, or Fire’s separate 8→16 transition without FRESET. Those remain limitations of the proposed cure, not regressions over fix A.

This is source-review readiness for the trial flash; whether it cures the garble remains unverified.

READY