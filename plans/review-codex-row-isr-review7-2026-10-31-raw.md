**NOT READY for stages 0–3 as written.** Removing the RTC resolves the sixth review’s slew and pending-wrap defects. Its replacement still needs three corrections.

1. **Must-fix before building — D3/D10 and stage 2: the validity rules contradict the acceptance tests.**

   [D3 invalidates an observer gap ≥8 ms](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:452), while [stage 2 requires a 100 ms globally masked gap to reconstruct exactly](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:832). Both observers stop during that mask; the first returning observation must therefore invalidate it. The sixth review’s threshold-consistency finding remains unresolved.

   “An observer whose **own** gap” also conflicts with exact reconstruction of long row-only holds: the row observer’s gap exceeds 8 ms even while the tick maintains a valid extension.

   **Fix:** specify one consistent validity state machine. Distinguish the shared extension’s last observation from each consumer’s previous timestamp; reconcile the 8 ms guard, the “under 174 ms” claim, and every injection’s expected result. Apply the same rule at entry, arm and exit.

2. **Must-fix before building — D3’s claimed 2 ms observation bound is unsupported.**

   [The inventory](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:443) says nothing else masks or stalls, but omits higher-priority service and existing critical sections. The [gap monitor explicitly includes UART2, USB and system-timer interference](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/overrun_diag.c:198). The [UART handler drains RX/TX in loops](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/UART/hal_serial_lld.c:296); [UART-LATENCY-PLAN explicitly rejects per-byte timing as a handler bound](/Users/jdlien/code/ak820-pro/plans/UART-LATENCY-PLAN.md:214).

   There is also a concrete counterexample to 2 ms: [dev transaction-lock mode retains the global lock](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:284), with a [10 ms transaction deadline](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:42).

   **Fix:** enumerate the supported operating modes and establish a conservative bound covering critical sections, higher-priority handlers and accumulated interference. Explicitly invalidate excluded diagnostic modes. Restore stage-2 tests with the tick independently stopped and restarted—the fourth review required these, but the current operative gate specifies scan-only and deep sleep without that independent case.

3. **Must-fix before building — D3’s USB witness lacks a continuity contract.**

   [The USB proof](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:458) treats `FRMNO` as continuously advancing whenever USB is active. It is a received SOF frame number; [suspend/reset/resume change bus operation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:233), and the existing [USB-active mirror is updated from the main loop](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2298).

   If SOFs stop during a 350 ms mask, a frozen frame number and CT16B5’s approximately 475 µs remainder satisfy the proposed 3 ms agreement tolerance. Neither endpoint state alone establishes uninterrupted SOFs.

   The 49.152 ms separation and 131.072 s coincidence are correct **nominal** arithmetic. They are not an unconditional proof: [HCLK comes from the IHRC](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:145), and [degraded mode leaves the watchdog disabled](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog.c:76).

   **Fix:** define USB continuity generations, pending bus-event handling, modular comparison, oscillator tolerance, and behavior without an armed watchdog. Invalidate/re-prime across bus discontinuities. Add suspend/reset/disconnect-during-hold tests; unavailable evidence must not become a healthy interval.

**Note — the battery limitation is a withdrawn guarantee.** Revision 8 explicitly permits long globally masked battery intervals to alias. That is transparent, but it does not satisfy the earlier universal long-gap rejection requirement.

The other checked hardware claims, masks, GPIO/I2C behavior, conditional light arithmetic, and saved object/RAM figures agree with the sources. Earlier publication, scan fairness, brightness calibration, bootloader, sleep, priority and SPI safeguards remain present. Stop/restart behavior and old pulse energy appropriately remain waveform prerequisites. The retained consolidation exception can still swallow a short press and exceed 25 ms.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under the same condition; 62.5 µs remains experimental.**

Inspection stayed inside the repository. No files were modified and no builds ran.