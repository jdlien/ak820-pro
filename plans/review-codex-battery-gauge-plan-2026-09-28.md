# Codex review of the battery gauge plan

`codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh -s read-only`, 2026-09-28 ~13:20, against [BATTERY-GAUGE-PLAN.md](BATTERY-GAUGE-PLAN.md) at `5eebd43`. Verbatim; dispositions are in the plan.

Do not implement the plan as written. The `5C` voltage approach is promising, but its claimed calibration range is unsupported, the charging hold-off rests on an overturned interpretation, and Phase 1 leaves essential protection and logging work unspecified. The first flash should establish reliable measurements, supply classification, and low-battery behavior before attempting a calibrated percentage or enabling the idle ladder.

Firmware citations below refer to `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`, except where stated otherwise.

1. **P0 — Phase 1 leaves low-battery protection attached to the wrong voltage.**

   **Evidence:** [battery.c:322](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:322) compares VDD against the 3550/3400 mV thresholds. The pack/VDD measurements and explicit warning in [readings.csv:30](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:30) show why those thresholds cannot provide the intended protection. The plan nevertheless schedules a discharge run without replacing them ([plan:279](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:279)). Its rule to ignore both clamps also leaves no protection behavior for `5C == 0`.

   **Recommendation:** Make protection part of Phase 1, independently of the display ratchet and post-charge hold-off. Provisionally retain **3.55 V warning and 3.40 V RGB cut**, applied to fresh, validated pack-voltage estimates; validate the lower-range conversion before relying on these settings. Use elapsed-time qualification around 30 seconds, warning rearm above 3.65 V, and a cut latched until confirmed external power has returned for five seconds.

   On confirmed battery power, a fresh zero report means **critical low**, not missing data: display `Low` immediately and require only a short confirmation, such as three fresh reports, before applying the lighting cut. Do not wait for a 30-sample median or charging hold-off. Unknown/stale readings must never clear an existing low-battery latch.

   Implement the cut as an independent output cap. The present one-shot `rgb_matrix_disable_noeeprom()` can be undone by a subsequent user toggle while `lights_cut` remains true ([battery.c:347](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:347)). Turning off RGB also does **not** electrically disconnect the cell; it is load shedding, not deep-discharge protection.

2. **P1 — The proposed supply predicate needs a state machine and a separate pack-presence decision.**

   **Evidence:** The proposed CHRG/4300 mV expression ([plan:80](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:80)) handles steady charging but leaves transition timing, faults, and missing-pack pulses unspecified. `charge_is_charging()` actually requires **CHRG low and B17 high**, whereas `battery_flags()` uses CHRG alone ([indicators.c:255](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:255), [battery.c:367](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:367)). Those are different signals, especially for the documented no-pack state.

   The current presence heuristic also assumes a wireless slider position proves battery power and can classify a zero-reading, noncharging faulted pack as absent after 15 seconds ([indicators.c:206](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:206)). USB can power the board in BT position, so that assumption is false.

   **Recommendation:** Specify independent states for **supply**, **charger activity**, **pack presence**, and **measurement validity**. For this measured unit, start bench validation with external-power entry at **4100 mV for 500 ms**, battery entry below **4000 mV for one second**, and retain the prior state between them. Qualify raw CHRG low over two 100 ms observations as positive external-power evidence; retain that evidence across approximately one second of high gaps to cover 2 Hz no-pack pulses. Do not use those pulses to confirm a charging session.

   | State or transition | Required behavior |
   |---|---|
   | Unplugged, VDD ≈3900 | Battery after qualification; this proves a pack is powering the board. |
   | USB charging, VDD ≈4193 | External via CHRG, also supported by the lower rail threshold. |
   | CV taper through 4300 | Remain external throughout; no transition at 4300. |
   | Termination | Remain external when CHRG releases; classify charging cessation separately. |
   | USB idle/full, BT ≈4470 or cable ≈4790 | External, including boot without previous charging history. |
   | No pack, CHRG pulsing | External; classify absence only from corroborating evidence, in either slider position. |
   | NTC fault, CHRG/DONE high | External if the rail supports it; “not charging,” never automatically “full.” |
   | VIN below VBAT/insufficient input | Cable presence and battery discharge may coexist. Classify the actual supply, or expose uncertainty. |
   | Boot before valid observations | Unknown; do not reset the ratchet, declare full, or enter an idle stage. |

   These thresholds are starting values, not portable hardware constants: [battery.c:28](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:28) documents approximately ±2% ADC-reference gain error. Test different cables, ports, load settings, boot states, and charger faults.

   Explicitly budget transition latency. For 4193→3900 mV, the step is only 293 mV, so the existing `>300 mV` snap never fires. Replaying its integer EMA reaches 3998 mV after **17 samples, approximately 1.7 seconds**, before additional debounce. Larger 4470→3900 and 4790→3900 transitions snap after three samples ([battery.c:476](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:476)). A dedicated short rail filter would give more consistent detection.

   `ch582_is_usb()` is **only slider-mode software state**, not cable detection ([ch582f_ajazz.c:154](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:154)). Recent advancing USB frame numbers are useful corroboration—the RTC already observes them ([rtc/rtc.c:523](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:523))—but their absence cannot distinguish unplugging from host suspend or a charger-only cable. Enumeration state alone may also outlive bus activity. The parsed module reports provide no independent VBUS indication.

3. **P1 — `5C` freshness currently wraps, and the proposed filter counts samples at the wrong implied rate.**

   **Evidence:** `battery_last_recv` is `uint16_t`; `ch582_battery_age_ms()` calls `timer_elapsed()` ([ch582f_ajazz.c:209](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:209), [ch582f_ajazz.c:725](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:725)). Contrary to its saturation comment, [platforms/timer.c:10](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/platforms/timer.c:10) wraps elapsed time every **65.536 seconds**. A dead module repeatedly appears fresh, and the log’s age cannot reach its intended 255-second stale sentinel after an initial report.

   Normal polling is every **five seconds**, with 250 ms retries only before the first response ([ch582f_ajazz.c:40](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:40)). Thirty independent reports therefore take approximately **2½ minutes**, not half a minute. Sampling the cached getter faster merely duplicates observations.

   **Recommendation:** Require a 32-bit receive timestamp, a received-report sequence number, and an explicit stale threshold—initially 20 seconds. Feed filters only on actual report reception, including repeated values. Define startup behavior and reject `0xFF` before arithmetic.

   Choose the filter in seconds: an odd median of five or seven fresh reports gives approximately 25–35 seconds of acquisition. Keep longer averaging for logging. The once-minute charge log cannot establish raw ±1 jitter, independence, or a guaranteed √n reduction; collect per-report statistics before making the plan’s ±5 mV filtering claim.

4. **P1 — The replacement fit has no committed provenance, although its numerical difference is relatively small.**

   **Evidence:** The four pairs in [readings.csv:30](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:30), :34, :38 and :42 are:

   `(3.84,78), (3.81,74), (3.74,66), (3.68,59)`.

   Recomputed ordinary least squares gives:

   `5C = 117.7705977 × V − 374.4507270`, `r² = 0.999473408`.

   This reproduces [docs/battery.md:23](/Users/jdlien/code/ak820-pro/docs/battery.md:23). The tracked occurrences of `114.2`, `361.0`, and `0.99987` lead only to the plan. The charge CSVs contain **VDD, not meter-measured pack voltage**, so they cannot supply the missing calibration.

   For the same `5C`, the plan’s inverse minus the documented rounded inverse differs as follows:

   | Voltage under the plan’s mapping | Difference |
   |---:|---:|
   | 3.16 V | −18.0 mV |
   | 3.40 V | −10.7 mV |
   | 3.68 V | −2.1 mV |
   | 3.84 V | +2.7 mV |
   | 4.04 V | +8.9 mV |

   Across integer reports 1–99, the existing firmware curve produces at most approximately **1.44 percentage points** difference between these fits. Nevertheless, nearest-5% rounding changes bins: `5C=88` becomes approximately 67.0% versus 67.7%, hence **65% versus 70%**. Small coefficient differences do not justify accepting undocumented calibration.

   **Recommendation:** Require the timestamped meter/report pairs, conditions, exclusions, and reproducible fit calculation to be committed **before changing the constants**. Describe 117.8/−374.5 as provisional and validated only over **3.68–3.84 V**. Tiny residuals from four meter readings recorded to 10 mV do not establish ±3 mV absolute accuracy or charge/discharge equivalence.

   Specify actual integer arithmetic. If the new fit is subsequently justified, rounded millivolts are:

   `((uint32_t)p * 10000u + 3610000u + 571u) / 1142u`

   for valid interior reports only. The plan’s `/114.2` expression is not integer-only.

5. **P1 — The hours-long post-charge “memory” is unproven; the hold-off and ratchet must be redesigned around that uncertainty.**

   **Evidence:** In [log-20260928-1034.csv:2](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv:2), `5C=4` at 03:02. It reaches 50 at 03:23, 90 at 05:02, and first reaches 100 at **06:57**, line 237: **3 h 55 min**, not an instantaneous USB response. All 452 entries say charging; 217 report 100.

   The earlier 4.00 V/96–97 pair agrees with the documented fit, which predicts 96.7. The later 3.84 V/78 pair also agrees. Their approximately 18.5-count fall represents **157 mV**, almost exactly the meter’s 160 mV fall. It does not demonstrate decay at constant pack voltage. The approximately recalled 3.99 V/85 point remains an unexplained outlier ([readings.csv:25](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:25), :27, :30, :45).

   **Recommendation:** Remove “snaps … and decays over hours” as an established property. The working hypothesis should be that `5C` measures terminal voltage: during charging, that includes charging-current voltage rise and polarization, so an accurate voltage reading can still be a poor discharge-SoC input. Voltage relaxation is a separate physical effect; [TI’s fuel-gauging description](https://www.ti.com/lit/an/slua364b/slua364b.pdf) explicitly accounts for current correction and relaxation before using voltage to infer charge.

   Add synchronized meter/`5C` observations before charging, during CC, and at 0/5/15/30/60/120 minutes after unplugging, at several starting levels. That establishes whether module lag exists and sets the hold-off.

   Use a minimum delay plus measured settling criteria, rather than an unconditional hours-long timer. A **30-minute minimum followed by two ten-minute observation windows** is a bench candidate to validate, not a supported production constant. Flat `100` cannot prove settling because it is censored; steady discharge also has nonzero slope. A timeout must leave the estimate uncertain, not automatically declare it valid.

   During charging show `Chrg`; between unplugging and validated estimation show `Wait`/`--` with an unknown bar. Fresh critical-low evidence overrides that presentation. Reset the ratchet once per **qualified charging session**, not on USB detection or each CHRG pulse; clear the old filter and initialize the new ratchet only after valid post-charge acquisition.

6. **P1 — Phase 1.6 would mislabel charger faults and ordinary cable-mode charging as “done.”**

   **Evidence:** The plan equates approximately 4470 mV with no charging current and completion ([plan:114](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:114)). Yet [history/battery-2026-09-25/log.csv:3](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/log.csv:3) records **4530–4538 mV while charging** in cable position. Charger faults also deassert CHRG ([docs/battery.md:451](/Users/jdlien/code/ak820-pro/docs/battery.md:451)). The existing estimator declares full after three seconds charging followed by three seconds not charging, with no fault discrimination ([battery.c:245](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:245)).

   The 09-28 log ends with CHRG still active. It contains neither termination nor a 4470 mV endpoint. Its 75 mV rise is consistent with changing supply-path drop, but does not independently measure charging current.

   **Recommendation:** Remove automatic charge-complete inference from Phase 1.6. Log VDD as a qualitative diagnostic. USB voltage, cable resistance, slider-dependent paths, board load, diode temperature, and charger faults must be controlled before treating its change as current. Even `exp(75/50)≈4.48` is a ratio under an assumed diode model, not a measured charger-current ratio. Until termination can be corroborated, say `USB` or `Chrg`, not `Full`.

7. **P1 — Five-percent steps and a monotonic ratchet do not establish ±5% accuracy; “Full” is still misleading at the upper clamp.**

   **Evidence:** The plan itself says the upper clamp hides approximately the top 20%, yet labels it `Full` ([plan:23](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:23), :96). Under its proposed coefficients the mathematical endpoints are **3.16112 and 4.03678 V**; the old fit gives **3.17912 and 4.02801 V**. Actual code-transition voltages additionally depend on the module’s quantization rule.

   The generic curve is not specified. Reusing [battery.c:155](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:155) gives **22.5% at 3.74 V**, while [readings.csv:38](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:38) uses **46.6%** from another “standard NMC” curve. Neither is measured truth; the disagreement demonstrates the unsupported accuracy claim.

   A strict minimum ratchet permanently retains a downward error. Rebooting loses that minimum; the first clamp, stale value, or transient can otherwise initialize it incorrectly.

   **Recommendation:** Use `High` for upper saturation and reserve `Full` for corroborated completion. Preserve lower saturation as a bound and critical-low condition. Test transitions around 99/100 and 0/1 with hysteresis.

   Name and commit the placeholder curve, describe its output as provisional, and do not claim ±5% until checked against independent discharge data. Qualify downward bin changes over sustained fresh observations instead of taking every new minimum. Keep raw voltage and unclamped estimation independent of the display ratchet.

   Define monotonicity as **within one qualified discharge session** unless persistence is explicitly added. On battery reboot, reacquire fresh samples; a high clamp gives `High`, a low clamp gives `Low`, and unknown data gives `--`. The debug page should distinguish **VDD**, **estimated pack voltage/bound**, raw `5C`, and age; the current combined battery row is ambiguous ([display.c:873](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:873)).

8. **P1 — Changing the log period without changing the protocol and host reader silently corrupts the calibration.**

   **Evidence:** Both host parsers reconstruct timestamps using literal `* 60` ([ak820battery.py:97](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:97), :113). A five-minute firmware log would appear five times faster, turning a 60-hour record into 12 hours and multiplying derived `dV/dt` by five.

   Format detection depends on `HC_CONN[26..27] != 0`, the dead estimator’s regulator-clamp field ([ak820battery.py:125](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:125)). Removing that estimator can therefore make the host parse a new log as v1. The reader only accepts version 2 on its newer path.

   **Recommendation:** Make the firmware and host protocol migration one Phase 1 deliverable. Advertise an explicit format/version and period, or preferably store monotonic entry timestamps. Preserve v1/v2 decoding without inferring format from estimator content; version changed flag semantics too.

   Add entry sequence/generation checks or a frozen dump view. Once the ring is full, its logical oldest index moves during reads ([battery.c:435](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:435)), allowing omissions or duplication across a wrap. Verify requested indexes in replies.

   The archived dumps are cumulative snapshots, not independent runs, and include embedded `# … entries` lines—for example [the final CSV:320](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv:320). Calibration ingestion must exclude those lines and avoid double-counting snapshots.

9. **P1 — Five-minute retention is too short for the intended run, and last-value logging discards the useful signal.**

   **Evidence:** `720 × 5 minutes = 60 hours`, shorter than the plan’s own 62–67-hour baseline. It cannot preserve both start time and the final observations. The plan also promises one-minute replacement data earlier ([plan:41](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:41)).

   [battery.c:423](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:423) records only the last `5C`; charging flags and RGB brightness are also end-of-period snapshots. At 8–13 mV/hour, five minutes spans only **0.67–1.08 mV**, versus approximately **8.5–8.8 mV per report count**.

   **Recommendation:** Retain at least **96–120 hours**, for example a ten-minute long-term ring plus a small recent/event log. Five-minute aggregation is also reasonable if storage covers the whole run. Preserve every fresh report in per-period aggregates: sum/count or fractional mean, min/max, saturation counts, missing/stale coverage, and actual duration. A median alone often remains a single integer count.

   Log supply/charging transitions, effective LED drive, effective backlight duty, power stage, and connection-state coverage. `rgb_on` and `rgb_val` remain unchanged when the ladder caps output; they cannot describe actual load. `sn32f2xx_led_load()` does measure the scaled buffer ([driver:924](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:924)), so retain that measurement independently of the estimator.

   Budget RAM explicitly: the current 12-byte ring consumes **8640 bytes**; 16-byte entries consume **11,520**, and 20-byte entries **14,400**, on a 32 KiB MCU. Require linker/stack headroom and a documented wire layout before choosing fields.

10. **P1 — The first flash is not specified reproducibly, and fixing protection introduces another calibration load change.**

   **Evidence:** HEAD unconditionally calls `power_task()` at 10 Hz ([ak820pro.c:574](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:574)). The one/five/fifteen-minute ladder is enabled without an opt-out ([power.c:30](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:30)). The obsolete estimator continues running from `battery_task()` ([battery.c:498](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:498)). A warning in the plan to “not flash” these changes does not exclude them from HEAD.

   **Recommendation:** Define a named Phase 1 build configuration with the idle ladder **compiled out or explicitly disabled by default**, verified on the produced artifact. Remove the obsolete estimator and its learned-clamp/countdown/full-state behavior, retaining only useful measurement code.

   Record firmware hash, daily/instrumented build, RGB effect/output, LCD brightness and animation state, radio mode/link behavior, and protection settings. Flashing resets LCD brightness to its default unless restored ([CLAUDE.md:193](/Users/jdlien/code/ak820-pro/CLAUDE.md:193)), which can change the load.

   Once protection is fixed, RGB cuts at 3.40 V, before the proposed 3.30 V endpoint. That run is no longer constant-load. Keep protection enabled, log the transition, and either model the segments or conduct the calibration with RGB already off throughout.

11. **P1 — The proposed discharge measures a runtime curve, not automatically a cell SoC curve; shutdown is not a valid empty reference.**

   **Evidence:** [docs/battery.md:41](/Users/jdlien/code/ak820-pro/docs/battery.md:41) assumes constant load means elapsed time is proportional to charge consumed. With a regulated output, fixed board settings more nearly imply constant power: battery current scales approximately as `P/(ηV)`. Between 4.18 and 3.30 V that implies about **27% higher current**, even before efficiency changes.

   Stopping at 3.30 V leaves an unmeasured reserve. The unexplained September 24 shutdown occurred with apparently substantial charge remaining and recovered only with USB ([docs/battery.md:496](/Users/jdlien/code/ak820-pro/docs/battery.md:496)). Therefore “board died” does not establish exhausted capacity or validate the pack protector.

   **Recommendation:** Choose the quantity being calibrated: remaining runtime under a defined load, remaining usable energy, or charge SoC. Time-to-endpoint can calibrate the first; claiming charge SoC requires current measurement or a validated current model.

   Replace “run flat” with a supervised run to a **meter-verified conservative endpoint**, initially around 3.30 V, with explicit reserve semantics. Do not force the pack protector to trip for calibration. Establish the actual pack protection hardware/limits before relying on it; the NTC is not readable by this firmware ([docs/battery.md:208](/Users/jdlien/code/ak820-pro/docs/battery.md:208)).

   Treat unexplained power loss as an invalid endpoint. Record last voltage, link/idle state, reset cause, and recovery behavior. Validate any fitted table on a second run rather than using the fitting run as its own accuracy gate.

12. **P1 — Phase 2’s load inference is underdetermined, and “a few hours” cannot resolve modest savings reliably.**

   **Evidence:** `4000 mAh / 62–67 h = 59.7–64.5 mA`, conditional on usable capacity and a valid discharge duration. The 38 mA and 80–130 mA estimates also depend on guessed voltage-to-SoC curves ([readings.csv:35](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:35), [docs/battery.md:490](/Users/jdlien/code/ak820-pro/docs/battery.md:490)). These are not independent current measurements.

   The recorded 10 mV step was near full charge with pastel lighting, and the meter pairs are recorded to 10 mV ([readings.csv:2](/Users/jdlien/code/ak820-pro/history/battery-2026-09-25/readings.csv:2)). It cannot establish one load-independent curve over all temperatures and discharge levels.

   Tens of milliohms for a cell and appreciably more for a protected pack are plausible: a comparable manufacturer’s 606090/4000 mAh specification lists **60 mΩ cell and 180 mΩ cell+PCM**, measured at 1 kHz. These are neither this JKJ pack’s measurements nor DC step resistance. [Honcell datasheet](https://www.honcell.com/Public/Uploads/uploadfile/files/20240628/DATASHEETHCP606090NW3.7V4000mAhPACK2024.pdf)

   Applying `ΔI=10 mV/R` gives **167 mA at 60 mΩ**, **56 mA at 180 mΩ**, or **30 mA at 333 mΩ**. The unknown effective resistance and coarse voltage step prevent choosing among these.

   A three-hour block falls only 24–39 mV, approximately 3–5 counts. A **20% saving** changes that by **4.8–7.8 mV**, less than one count. Averaging helps only where the signal actually dithers; repeated identical codes do not create independent precision.

   **Recommendation:** Prefer a short direct battery-current comparison at fixed voltage and settings. Otherwise use alternating **ABBA blocks**, hold LCD/radio conditions fixed, exclude measured switching transients, and compare local slopes while accounting for voltage and temperature. To accumulate even three counts of separation for a 20% effect requires roughly **10–16 hours per condition** at the stated slopes; repeated 4–6-hour blocks over multiple days are more defensible than one short comparison.

   Measure RGB and LCD independently. Little RGB benefit does not prove the screen dominates. The driver still scans rows and programs PWM channels with dark LEDs ([driver:490](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:490)); disabling light output does not eliminate the reported 72.8% ISR work. Replace the contaminated 62–67-hour history with a matched baseline for the runtime-improvement gate.

13. **P1 — Automatic Power Saver contradicts the radio-consent policy, and the existing queue cannot guarantee lossless wake.**

   **Evidence:** Below approximately 15%, the plan forces Power Saver regardless of choice ([plan:193](/Users/jdlien/code/ak820-pro/plans/BATTERY-GAUGE-PLAN.md:193)), then justifies arbitrarily long reconnection because “the mode is the consent” (:246). Automatic selection provides no such consent. Normal’s radio policy also conflicts between “never” and the latency table.

   The existing CH582 transmit queue deliberately coalesces keyboard/consumer states when nearly full, explicitly acknowledging lost intermediate edges ([ch582f_ajazz.c:538](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:538)). It is not a lossless multi-second wake buffer.

   **Recommendation:** Automatic low-battery action should apply lighting caps only. Keep radio shutdown/deep sleep behind explicit selection and separate implementation gates. Specify buffering of presses, releases, modifiers and encoder/consumer events, plus reconnect failure and overflow behavior. Test short taps, bursts, held modifiers, unavailable hosts, and repeated sleep/wake cycles. Keep radio shutdown absent until that contract is demonstrated.

14. **P2 — A preemptive persistent checkpoint is possible, but EEPROM is not a free full-log backup.**

   **Evidence:** The log is ordinary RAM, while the keyboard config block is only five bytes and writes are deliberately deferred ([kb_eeconfig.c:6](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:6)). External flash already has asynchronous page-program/sector-erase APIs, with documented LCD/animation constraints ([lcd_bus.h:67](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.h:67)).

   **Recommendation:** For the first supervised run, reliable retention plus an early dump is sufficient. A small persistent checkpoint—timestamp, last valid reports, source state, minimum, and warning/cut events—is worthwhile for diagnosing another shutdown.

   Preserving hours of samples requires explicitly reserved external-flash space, pre-erased while powered reliably, with sequence numbers, CRC, and commit markers. Write incrementally while voltage is healthy, not after regulator collapse. Do not put the whole ring in the shared emulated EEPROM or assume unallocated asset-flash space is safe to overwrite.

**Revised order of work**

1. Commit the calibration evidence and reproducible calculations; withdraw unsupported charging-memory, endpoint-precision, and ±5% claims.
2. Specify and test supply/charger/presence states, fresh-report handling, 32-bit ages, and boot/transition behavior.
3. Replace low-battery protection and remove the obsolete estimator. Define clamp, stale, hold-off, and ratchet behavior independently.
4. Implement the versioned logger and host reader together, with whole-run retention and actual load/transition data.
5. Produce a named Phase 1 artifact with the idle ladder disabled. Verify meter agreement, protection, missing-pack/fault behavior, and log reconstruction before a long run.
6. Characterize post-charge settling; collect a controlled discharge to a conservative endpoint, fit the chosen quantity, and validate it on a second run.
7. Measure RGB/LCD savings with direct current measurements or adequately long alternating blocks. Then implement lighting modes; leave radio shutdown and deep sleep behind their own wake-integrity gates.