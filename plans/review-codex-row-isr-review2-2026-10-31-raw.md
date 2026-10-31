**NOT READY for stages 0–3 as written.** No files were modified and no builds were run.

The first review’s must-fixes **1, 4 and 5** are substantively addressed: terminal-window admission, the interim scanner and its budget, and mandatory waveform capture plus the settling sweep. **2, 3 and 6 remain partly open**, despite their dispositions.

The changes required before building are:

1. **Must-fix — D3/D10: epoch reconstruction still needs coherent snapshots and an exit-time calculation.**  
   [D3 step 1](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:374) reads CT16B5 and scheduler phase without specifying protection against preemption between those reads. Such preemption introduces its entire duration into the reconstruction error—not merely the stated 5.33 µs quantization error. This can misidentify the epoch and suppress a valid service.

   [D10](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:606) also obtains crossed boundaries from step 6, but preemption can occur **after** that check and before the exit timestamp. Multiple slots crossed there disappear from a modulo subtraction, understating handler occupancy. The counters’ actual behavior is documented in [the timer reference](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:710).

   **Fix:** specify a bounded, coherent time/phase snapshot at entry and exit, a fresh snapshot for arm validation, and exactly when the serviced epoch advances. Inject delays between snapshot reads and after arming. Define the supported gap bound and handling beyond CT16B5’s wrap; the [12-second watchdog](/Users/jdlien/code/ak820-pro/docs/hardware.md:351) does not establish the asserted 349 ms limit.

2. **Must-fix — stage 2/D8: brightness compensation is permitted in words but constrained out of the design.**  
   [Stage 2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:675) still hardcodes the historical **258 µs**, rather than selecting the measured stage-0 cadence. It fixes the PWM clock at 4.8 MHz and terminal at 256, requiring every width below 256. Consequently, channel 255 has **no upward compensation headroom** if the baseline contains additional light during sequential column release—as the [existing disable sequence](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:472) permits. Meanwhile, [D8](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:545) still requires the identity table until stage 5.

   **Fix:** make stage 2’s cadence, permissible widths and terminal derive from the measured baseline; authorize a wider terminal or different PWM clock when needed, while retaining the full-window admission rule. Remove D8’s identity-until-stage-5 requirement. Add explicit stage-0 optical references at values **1–16** and ordinary-operation waveform captures: [stage 0](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:637) currently collects the named power holds only at 64/128/255, although later gates require low-code comparisons against it.

3. **Must-fix — stage 1: its linker gate contradicts its implementation.**  
   [Stage 1](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:659) retains ChibiOS PWM and its callback, then requires **“no PWM object or vector retained.”** Those objects are required by the retained [initialization and callback machinery](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:875).

   **Fix:** move that gate, and D2’s reference to it, to stage 2. Stage 1 should verify that only the intended PWM owners remain. Replace “timing identical by construction” with measured equivalence: changing scanner locking and initialization does not establish identical execution time.

4. **Must-fix — rig section/stage 3: the rejected manual substitute remains authorized.**  
   The [last sentence of the delivery gate](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:834) still allows manual testing plus another day on black without the rig. This directly contradicts [first-review must-fix 6](/Users/jdlien/code/ak820-pro/plans/review-codex-row-isr-review1-2026-10-31-raw.md:36).

   **Fix:** remove that waiver for stage-3 acceptance. Require the repaired rig’s baseline and candidate short-tap comparison, using recorded release dwells. The copied-snapshot consume counting is now correctly specified; the waiver is what remains open.

**Stage 4 is sufficiently specified once stages 0–3 pass.** Its first-review blocker is addressed: bracket width and success/failure must be exposed before the comparison. The retained HAL locking contract, arbitration, timeout distinctions and sleep/recovery gates match the [RTC implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:270).

**Stage 5 is not yet sufficiently specified.** Two further must-fixes remain:

- **Must-fix before stage 5 — contradictory terminal windows.** [D2](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:327) specifies 2,047/1,023 ticks; [stage 5](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:738) specifies 4,096/1,535. These produce materially different admission deadlines. Choose one set of **literal terminal register values**, distinguish those from window lengths, and reconcile G5, the headroom calculations and acceptance tests.

- **Must-fix before stage 5 — emitted-tick normalization remains incomplete.** [D8](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:549) now specifies accumulator widths, atomic take/reset and `lit_ms`, but “by the per-cadence scale” does not define conversion to the [existing value-times-milliseconds contract](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.h:87). For a linear mapping `width = k × byte`, the conversion is `rgb_ms = emitted_ticks × field_period_ms / k`; dividing by `k` alone misses the field-period factor. Specify the formula, fractional remainder handling and treatment of any nonlinear calibration table. Validate a known constant frame before refitting coefficients, which could otherwise conceal a unit error.

Other wrong or unsupported claims do not independently block stages 0–3:

| Severity | Where and evidence | Correction |
|---|---|---|
| **Should-fix** | “What is known,” erase explanation: the [flash routines execute from SRAM](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:30), contrary to “code executes from the array being erased.” The claim that today’s erase necessarily leaves LEDs dark also remains conditional on Q4. | Attribute the interrupt delay to flash vector/instruction fetches; keep the old output state conditional. |
| **Should-fix** | D2’s categorical combined STOP/RST result exceeds the [header’s documentation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/sn32_ct.h:352), which specifies the actions individually. | Label the simultaneous-action result an inference. Keeping STOP-only and testing its waveform is sound. |
| **Should-fix** | The MODE-race explanation overstates what the current code proves. Both [row helpers](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/matrix.c:136) assert output mode; with those row bits already set, their MODE updates are idempotent. | Describe the hold-off’s ownership rationale, rather than claiming demonstrated lost updates merely because two RMW writers exist. Removing ISR mode writes remains a sound simplification. |
| **Should-fix** | Rig item 4’s “two more probe leads” does not establish the proposed Pico capture’s electrical compatibility, isolation bandwidth or timing accuracy. The [relevant GPIO domain is VDD](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:635), not uniformly 3.3 V. | Require a qualified probe/front end and capture implementation, or the appropriately rated scope/analyzer alternative. |
| **Should-fix** | Rig clock synchronization specifies one serial round-trip offset, without an uncertainty or drift bound, while discussing improvements around 1 ms. | Bound synchronization uncertainty and drift before attributing millisecond latency differences. Counts and short-tap acceptance do not require that claim. |
| **Note** | “Instruments” assigns per-row counts, row gap and raw edges to page 4. They are in [page 3](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:306). The cited historical maximum row gap was [6 ms](/Users/jdlien/code/ak820-pro/docs/hardware.md:798), not the 4.6 ms mean interval. | Correct the page and distinguish mean interval from maximum gap. |
| **Note** | D8’s ~29-second wrap calculation charges all 8,000 slots/s to each colour accumulator. With 81 populated LEDs, the stated maximum gives about **96.6 seconds per colour**. | Correct the estimate; retaining 64-bit accumulators is reasonable. A 64-bit accumulation also requires carry handling, not merely a 16-bit add. |
| **Should-fix** | “Risks” still asserts that the unbuilt driver and tables “come in under” the removed flash footprint. | State this as a budget target, verified by the linked image. |

The write keys, control and GPIO masks, IOEN returning a pin to its configured GPIO state, STOP clearing CEN, I2C direction switching, conditional cadence/luminance arithmetic, and quoted existing object/heap figures check out. I independently inspected the saved objects and both named ELFs. I found no additional running interrupt-side GPIO MODE/CFG writer that defeats the proposed stage-4 ownership change.