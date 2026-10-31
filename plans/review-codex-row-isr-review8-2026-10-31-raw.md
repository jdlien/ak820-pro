**NOT READY for stages 0–3 as written.** Two areas still need correction. I accept the owner’s withdrawal of universal long-gap detection on battery.

1. **Must-fix before building — D3 step 1/D10: recovery conflicts with excluded-mode validity.**

   [The state machine](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:454) invalidates on entering degraded mode or `OD_LOCK_TRANSACTION`, then allows **the next observation** to restore VALID. That permits recovery while the excluded mode remains active, contradicting “INVALID throughout” and stage 2’s “INVALID across it.”

   Recovery also needs retained invalidation history: the tick can invalidate and re-prime before the row handler returns. Checking only the current VALID state at entry, arm and exit cannot establish that an interval never touched INVALID.

   **Fix:** prohibit revalidation until the exclusion ends; retain a loss generation or equivalent sticky state across re-primes, and associate it with the row handler’s snapshots. Require the specified epoch-loss reporting and exclusion of crossing intervals even when the tick has already recovered. Exercise that ordering in stage 2.

   Also correct “only the first exists in a release build”: [degraded mode is compiled into release firmware](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog.c:76).

2. **Must-fix before building — stage 2: the injection outcomes still contradict D3, and two seventh-review tests are absent.**

   [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:875) requires all three long battery injections to produce aliased small counts. Using [CT16B5’s documented frequency and width](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:766), their nominal residues are:

   | Global interruption | Raw residue | D3’s battery outcome |
   |---|---:|---|
   | 350 ms | 0.475 ms | Can alias |
   | 700 ms | 0.949 ms | Can alias |
   | 7 s | **9.493 ms** | **INVALID by the 8 ms guard** |

   Thus the 7 s expectation is wrong. On USB, that injection also need not invalidate *first* through the frame-counter check.

   **Fix:** specify expected outcomes and rejection reasons from the actual independently measured duration and clock rate. Treat battery aliasing as **possible**, not mandatory for every long interruption. Preserve one epoch loss when multiple checks reject the same interval.

   The seventh review also explicitly required **reset and disconnect during the hold**. The operative gate adds only suspend. Add the other two cases, including recovery; the [USB handler has distinct reset/suspend/resume paths](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:233).

Other incorrect claims are nonblocking:

- **Should-fix — D3’s “row-only … any length.”** Its specified 32-bit, 187.5 kHz extension wraps after approximately **6 h 21 min 46 s**. Bound the supported consumer interval or retain additional elapsed-wrap accounting.
- **Should-fix — D3’s “beyond 12 s only degraded mode runs.”** Twelve seconds is nominal; [the recorded watchdog recovery is approximately 12.3 s](/Users/jdlien/code/ak820-pro/docs/hardware.md:351). State the USB proof’s 12 s scope separately from the watchdog’s actual bound.
- **Should-fix — D3’s guaranteed UART-overrun witness.** A silence produces overruns only when sufficient incoming traffic arrives. [The UART implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/UART/hal_serial_lld.c:296) does not provide an independent silence detector. Make that claim conditional.

The seventh review’s shared-observation stamp, corrected 100 ms outcome, higher-priority interference inventory and USB event generation are present in the operative text. I found no regression in the earlier publication, brightness-calibration, waveform, scan-fairness, bootloader, sleep, priority or SPI safeguards. Register/key/mask claims, IOEN behavior, GPIO/I2C behavior and conditional light arithmetic check out; inspection of the saved objects and ELFs confirms the resource figures. Stop/restart behavior and old pulse energy appropriately remain measurement prerequisites.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under the same condition; 62.5 µs remains experimental.** Consolidation still permits short-press loss and a ≥25 ms pass as the declared exception.

All inspection stayed inside the repository. No files were modified and no builds ran.