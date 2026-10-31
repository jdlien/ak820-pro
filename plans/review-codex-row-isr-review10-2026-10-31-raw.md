**NOT READY for stages 0–3 as written.** One acceptance-method correction remains. This does not reopen the withdrawn battery long-gap guarantee.

1. **Must-fix before building — stage 2: the LED pulse gap does not independently measure every specified interrupt silence.**

   [Stage 2’s timing method](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:900) measures from the last LED pulse to the first returning pulse and asserts one-slot uncertainty. But its [ordering injection](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:941) places a **20 ms global mask inside a row-only hold lasting another 100 ms**. The pulse gap measures the outer hold; it cannot establish the inner 20 ms silence. Moreover, [D3’s arm admission](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:585) can omit returning pulses, so the claimed one-slot uncertainty is not established.

   **Fix:** capture explicit start/end markers bracketing the global mask and the row-only hold separately, using the independent witness. Bound marker overhead, capture-clock error and CT16B5 rate uncertainty. Predict outcomes over that entire uncertainty interval; adjust durations when it straddles a wrap or the 8 ms threshold. Remove the contradictory command-round-trip timing instruction at lines 900–902.

   The ninth review’s rate-dependent seven-second correction and delayed, retained-result **no-USB setup are met in the operative text**. Its independent-duration requirement remains only partly met.

Two factual corrections are nonblocking:

- **Should-fix — D3’s watchdog bound.** [Lines 535–540](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:535) turn the ILRC graph’s endpoints into a guarantee that every watchdog-permitted return lies inside 13 seconds. The source supplies a [temperature graph](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:146), not guaranteed oscillator limits; [12.3 seconds is an observation](/Users/jdlien/code/ak820-pro/docs/hardware.md:351). Keep the 13-second USB scope explicit and describe 8.7–12.4 seconds as graph-derived estimates, without the universal inference.
- **Should-fix — D3’s tolerance justification.** [“Three times their sum”](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:527) is incorrect: three times 0.04% + 0.05% is **0.27%**, not 0.15%. Correct the justification and state the clock-rate envelope supporting the chosen tolerance.

The other checked register/key/mask claims, STOP clearing CEN, IOEN returning pins to GPIO, GPIO atomics, I2C direction switching, conditional light arithmetic and resource figures agree with the sources. I independently checked the saved objects and ELFs. No additional running interrupt-side MODE/CFG writer surfaced.

I found no regression in the earlier matrix-publication, scan-fairness, brightness-calibration, waveform, priority, SPI, sleep or bootloader safeguards. The existing consolidation can still swallow a short press and exceed 25 ms; that remains an [explicit exception](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:162). Hardware-dependent stop/restart behavior, baseline pulse energy and settling appropriately remain prerequisite measurements.

**Stage 4 is sufficiently specified once corrected stages 0–3 pass. Stage 5 is sufficiently specified for the linear-table path under that condition; 62.5 µs remains experimental.**

All inspection stayed inside the repository. No files were modified and no builds ran.