**NOT READY for stages 0–3 as written.** The fifth review’s must-fix is not met. The RTC is independent hardware, but the specified validity algorithm can still accept a long interruption as healthy.

1. **Must-fix before building — D3 step 1/D10: the RTC is not a fixed, uninterrupted one-second clock.**

   [D3’s proof](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:424) conflicts with the actual clock implementation: [slewing changes the reload](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:570), and [phase-setting resets the counter with a shortened first period](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1384). Writing `SECCNTV` resets `SECCNT`, as [the hardware reference states](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:833).

   A concrete counterexample, using an allowed slew period: at 33,600 Hz, let the RTC period be 33,555 counts and its initial count 33,500. Mask all interrupts for **7 seconds**. The final RTC count is 260, with one pending flag despite eight wraps. The proposed correction gives **E = 9.375 ms**; CT16B5 gives **F = 9.493 ms**. Both pass the validity rule. At 125 µs cadence, approximately **76 boundaries replace 56,000**.

   The claimed 699-second coincidence is also numerically wrong: the exact nominal CT16B5 period and one second repeat at 16,384 seconds. Neither calculation establishes safety across changing RTC periods.

   **Fix:** specify validity across actual reloads, phase steps, initialization and wake corrections, with explicit invalidation of counter discontinuities. Prove long-gap rejection over the supported clock states, or choose another mechanism. Apply it consistently at entry, arm and exit.

2. **Must-fix before building — D3’s RTC snapshot and pending-wrap arithmetic are incomplete.**

   [The stated formula](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:432) adds a period whenever `SECIF` is pending. If it is pending at both entry and arm, that adds a fictitious second to a microsecond interval. The RTC handler cannot clear it between those snapshots because it shares the row handler’s priority. Servicing that already-accounted wrap afterward can count it again.

   Masking interrupts also cannot prevent hardware rollover between the `SECCNT` and flag reads. The existing [coherent RTC reader explicitly rejects pending-wrap snapshots](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:779); `cyc_elapsed()` is expressly limited to spans well under one second.

   **Fix:** define a rollover-safe snapshot and account for pending state at **both endpoints**. Specify recovery across reload generations. Re-prime after wake accounting: today [the LED exit hook precedes `rtc_account_sleepI()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:604). Test ordinary second boundaries without false epoch losses.

3. **Must-fix before building — stage 2’s acceptance expectations contradict D3 and miss the counterexample.**

   [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:806) requires **170 ms** to invalidate, while D3 accepts agreeing intervals below **174 ms**. A correctly implemented stable-clock case cannot satisfy both. Its seven-second test holds off only the row IRQ, allowing RTC interrupts to count normally; it does not exercise collapsed RTC wraps.

   **Fix:** reconcile the threshold and expected results. Add independently timed, globally masked long gaps across RTC phases and permitted reloads, plus pending-wrap, phase-step and wake-accounting cases. Invalid results must remain visibly invalid.

**Should-fix — rig items 3–4:** the PC817C reverse-orientation/timing assertions and quoted LVC electrical ratings lack supporting evidence in the supplied repository sources. [The rig specification](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:928) should label them unverified until the exact-part datasheets and qualification results are recorded. The qualified scope alternative remains usable.

The other checked claims agree with the sources: write keys, masks, STOP clearing CEN, IOEN returning pins to GPIO, GPIO atomics, interrupt-side MODE ownership, I2C direction switching, conditional light/cadence arithmetic, and saved object/ELF resource figures. Earlier publication, scan-fairness, brightness-calibration, waveform, bootloader, priority and SPI safeguards remain present. The existing consolidation can still swallow a short press and exceed 25 ms; [the plan explicitly retains that exception](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:149).

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under the same condition; 62.5 µs remains experimental.**

All inspection stayed inside the repository. No files were modified and no builds ran.