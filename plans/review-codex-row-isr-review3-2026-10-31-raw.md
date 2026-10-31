**NOT READY for stages 0–3 as written.** Three changes are required first. No files were modified, no builds ran, and all inspection stayed inside the repository.

The second review’s brightness-calibration and rig-waiver must-fixes are met. Stage 1’s implementation and linker gate are corrected, although stale references remain. Coherent entry/exit snapshots and fresh arm validation are now specified; **long-gap handling remains incomplete**.

1. **Must-fix before building — D3/D10: the wrap check cannot establish timestamp validity.**

   [D3 step 1](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:396) rejects a *raw* difference exceeding 174 ms. That cannot detect a full counter wrap. CT16B5 is [16-bit at 187,500 Hz](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:766): a real 350 ms gap appears as approximately **475 µs**, passes the check, and at 125 µs cadence reconstructs about **4 boundaries instead of 2,800**. Omission counts and handler-duration measurements can therefore report a long interruption as healthy.

   **Fix:** establish validity independently—through a suitable extended/coarse clock or a proven inter-snapshot bound with explicit invalidation of longer interruptions. Specify recovery without replay. Add injections around half-wrap, full-wrap and multiple wraps, including after arming.

   Also correct [D10’s latency-validity condition](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:645): normal consecutive services cross **one** boundary; “less than one slot elapsed” does not identify ordinary fresh service.

2. **Must-fix before building — waveform witness: the proposed divider can disturb the circuit being measured.**

   [Rig item 4](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:863) permits a 1 kΩ/2.2 kΩ divider on a shared column. That adds **3.2 kΩ to ground** when IOEN releases the pin for scanning, against [internal pull-ups of roughly 50–100 kΩ](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:1173). It can change the input level and transistor bias, introducing phantom input or altering the LED waveform. It is not established as a nonintrusive probe.

   The stated approximately 3.9 V rail also applies to battery operation; the source records [4.47–4.79 V on USB](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:68).

   **Fix:** require a voltage-rated, high-impedance, sufficiently low-capacitance probe/front end. Qualify loading during PWM ownership **and GPIO input operation**, and verify unchanged scanning with the probe attached.

3. **Must-fix before building — waveform witness: the permitted 24 MHz analyzer cannot certify the required minimum pulse.**

   [Rig item 4](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:869) explicitly permits 24 MHz capture, while [stage 0b](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:698) requires width-1 tests with D2’s 48 MHz pulse timers. Sampling every **41.7 ns** can entirely miss a **20.8 ns** pulse. Reporting the sample rate does not make that gate measurable. This leaves the first review’s waveform requirement incompletely satisfied.

   **Fix:** specify minimum detectable pulse width, sampling interval, bandwidth and width uncertainty sufficient for the width-1 and restart-glitch tests. Remove the 24 MHz option as an acceptance instrument for those tests.

The remaining corrections are nonblocking for stages 0–3:

| Severity | Where and contradictory evidence | Fix |
|---|---|---|
| **Should-fix** | [D2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:371) still calls PWM removal a stage-1 gate; [resource accounting](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:208) points to stage 1 for linked savings; [Risks](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:946) still says brightness-neutral “by construction.” Stage 1 explicitly retains PWM and requires measured equivalence. | Move removal/savings references to stage 2 and make the neutrality statement measurement-based throughout. |
| **Should-fix** | [Stage 1](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:716) requires `row_gap_max ≤ 5 ms`, although the cited [baseline maximum is 6 ms](/Users/jdlien/code/ak820-pro/docs/hardware.md:798). Stage 3’s 7 ms ceiling can also permit regression against a better measured baseline, contrary to G6. | Specify matched-load baseline-relative acceptance alongside absolute ceilings; distinguish windows containing the retained PCF hold-off. |
| **Should-fix** | [G5/D2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:344) presents 1.66× headroom without carrying forward stage 2’s calibration uncertainty. If stage 2 needs `k = 16`, preserving it at 125 µs uses approximately 1,977 ticks, leaving only about **1.04×** headroom below 2,047. | Label the quoted widths/headroom conditional and derive them from the measured calibration. |
| **Should-fix** | [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:736) conflates timer width 255 with full channel value 255. Under its calibrated LUT, full value nominally becomes approximately **2,550–4,080 ticks**. | Distinguish input bytes from literal match values and explicitly test `scale_lut[255]`. |
| **Should-fix before stage 6** | [D8’s nonlinear case](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:587) switches to raw emitted ticks but describes tick-millisecond coefficients under the same interface. That does not preserve the [existing value-times-milliseconds contract](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.h:87). | Retain a fixed reference normalization for nonlinear widths, or define the replacement units and consumer conversion consistently. |

**Stage 4 is sufficiently specified. Stage 5 is sufficiently specified for the linear-table path once the shared timing and waveform issues above are fixed.** Its literal terminals agree, and the field-period factor, remainder handling, constant-frame validation and repeated coexistence gates are present. The 62.5 µs cadence remains explicitly experimental.

The other checked claims hold: write keys and masks, IOEN returning pins to GPIO, documented STOP clearing CEN, GPIO atomics, I2C direction switching, conditional cadence/light arithmetic, and the saved object/ELF resource figures. I found no additional running interrupt-side GPIO MODE/CFG writer. The previously accepted flush/publication, scan fairness, boot priming, sleep/bootloader quiescence, priority and SPI-regression safeguards remain present. The consolidation’s potential input loss and ≥25 ms pass remain explicitly acknowledged exceptions.