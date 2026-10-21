**The plan is not ready to build as written.** The static-page approach is sound, but the headline calculation, LED count, validation gate, and daily-use model need corrections.

I reviewed firmware through `git show` on `ak820pro-jdlien`, which resolved to `9e52400ec9fa5828867ab2b17c247d559f98f879`, matching [deps.lock:20](/Users/jdlien/code/ak820-pro/deps.lock:20). Firmware references below refer to that revision, not the working tree. I ran only offline fitting and arithmetic; no hardware-facing code.

1. **Must-fix — the continuous-use formula is an approximation, and its reference checks describe a different calculation.** [Plan:70](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:70)

   The firmware’s rules are:

   | Condition | RGB while typing | Screen while typing |
   |---|---|---|
   | Always on / Balanced, above 150‰ | Requested value | Requested level |
   | Power saver | Value capped at 128 | Requested level |
   | Any mode except Lights out, **at or below** 150‰ | Value capped at 128 | Requested level |
   | Lights out | Off | Normally off; message/debug exceptions |
   | RGB cut latched | Off | Still governed by the mode |

   The comparison is `level <= LOW_CAP_PM`, not strictly “below 15%”. Low battery takes the darker of the selected mode’s stage and Saver’s stage; it does not brighten Lights out. Neither ACTIVE nor DIM caps the screen. Sources: `power.c:119`, `power.c:203`.

   Lights out illuminates the screen at the user’s level for four seconds after a message, and continuously while the debug pages are open. The low-cap notice waits for an already lit screen and is suppressed in Lights out; it does not itself force the screen on. The voltage-cut alert can trigger Lights out’s normal message illumination. Sources: `power.c:70`, `power.c:225`, `power.c:245`; `battery.c:1266`.

   **The ~52-hour check cannot validate the proposed headline.** With the actual pinned model and LED count, full white at LCD level 5 gives:

   - Fixed brightness: **52.9 h**.
   - Assuming exactly 15% of energy remains when dimming starts: **45.0 h at full brightness + 15.3 h capped = 60.3 h**.

   Keep fixed-state runtime as a separate regression calculation. Compare the headline against a calculation that includes the future cap.

   **Must-fix — Always on never deep-sleeps, including below 15%.** Its low-battery lighting follows Saver, but a long pause ends at the **awake-dark draw**, not sleep power. `power_sleep_wanted()` explicitly rejects Full mode (`power.c:294`). This matters for [plan:105](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:105).

2. **Must-fix — 150‰ is not guaranteed to mean 15% of measured energy remains.** [Plan:73](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:73)

   In an uninterrupted, uncorrected count starting at FULL, it does: each permille represents **15.579 mWh**. But the implemented gauge also:

   - Ratchets downward against the voltage band.
   - Holds its level and discards pending count energy below the band.
   - Re-seats after charging and initializes differently after reboot.
   - Stops counting level downward at 10‰; the voltage protection subsequently establishes zero.

   Sources: `battery.c:583`, `battery.c:684`, `battery.c:1095`; [docs/battery.md:856](/Users/jdlien/code/ak820-pro/docs/battery.md:856).

   Therefore retain the 85/15 formula only as an explicitly stated scenario assumption. There is no single different tail fraction derivable from these constants. In particular, the 1% count floor does **not** justify replacing 15% with 14%.

   A useful sensitivity: for full white/LCD 5, moving the assumed dimming point by one percentage point changes the estimate by about **0.49 h**. That is a sensitivity calculation, not a confidence interval. A future drain should record the logger’s remaining energy when the actual cap activates.

3. **Must-fix — use the firmware model, but extract its actual inputs as well as its coefficients.** [Plan:37](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:37)

   **There are 81 RGB LEDs in the pinned firmware, not 82.** `keyboard.json:53` contains 81 RGB-layout entries; `config.h:33` identifies that layout as the source of `RGB_MATRIX_LED_COUNT`. The driver sums those committed LEDs.

   The discrepancy already exists in [rgb_fit.py:15](/Users/jdlien/code/ak820-pro/scripts/rgb_fit.py:15) and [the simulator stub:50](/Users/jdlien/code/ak820-pro/scripts/battery_sim/stubs/quantum.h:50). The firmware comments repeat 82, but the executable model uses the generated count.

   Using 82 gives **296.573 mW** at full white/LCD 5; the actual firmware inputs give **294.415 mW**, untethered. The proposed `led 333` fixture cannot catch this: normalized drive cancels the LED count, and red, green, and blue can all report 333.

   Other semantics the extraction must preserve:

   - CIE is applied to **HSV value before colour mixing**, not independently to the resulting RGB channels (`quantum/color.c:22`).
   - The table lives in `quantum/led_tables.c:23`.
   - RGB energy uses time-weighted **committed**, capped frames; the intercept applies only during lit time (`drivers/led/sn32f2xx.c:928`; `battery.c:670`).
   - Screen power uses effective backlight duty, including its on/off state.
   - Firmware sleep accounting uses **13.35 mW**, regardless of radio (`battery.h:158`). The page’s 13.25/13.8 mW and awake 2.4G adjustment are measured/extrapolated extensions.

   **Should-fix — replace the “every fitted constant within 2%” shipping gate.** [Plan:52](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:52)

   Two percent of the RGB intercept is only **0.173 mW**, while the existing RGB-off passes differ by **2.0 mW**. Also, a sweep with USB always configured identifies `P_BASE + P_USB`, not those constants separately.

   Gate exact firmware/page arithmetic separately from measurement agreement. For measurements, report residuals, repeatability, and uncertainty for total power and isolated increments. A failed measurement gate should trigger investigation—not automatically require changing firmware constants. The 81/82 error itself is small enough to pass a 2% gate.

4. **Should-fix — the sweep is a good starting design, but needs stronger controls and a separate sleep procedure.** [Plan:124](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:124)

   The shared floor, separate RGB/screen families, combined-load checks, and forward/reverse passes are sensible. I would add:

   - RGB value **0 and 1**, plus several low values such as 16/32/48. The first nonzero CIE drive occurs at value **1**, not 3.
   - Repeated dark references between families. Compare passes before averaging; reversal does not remove state-dependent relaxation or changing background activity.
   - Held-out purple and partial-saturation states, including a hue-sector boundary.
   - Recorded requested and read-back HSV/effect, effective LCD state, mode, cap, firmware identity, measurement interval, and pack voltage.

   Existing quiet holds have sample SDs around 0.1–0.4 mA, with some dark holds near 0.7–0.8 mA. The lowest backlight increment is only **0.815 mW**. Use longer or repeated low-end holds when those increments are not resolved. The animated cycle’s SD is about 3.5 mA, so its whole-hold measurement must be compared with a whole-hold model average, not one last-second `HC_POWER` sample. Sources: the supplied summaries; [current_map.py:399](/Users/jdlien/code/ak820-pro/scripts/current_map.py:399).

   **Must-fix if sleep is remeasured:** live USB data blocks deep sleep (`sleep.c:240`). Op 14 sub 2 merely holds a lighting stage; forced sleep uses **sub 4**, with the sleep preconditions satisfied and USB data removed. The existing hour-long procedure does this explicitly. Do **not** subtract 7.1 mW from sleep measurements as the blanket wording at [plan:145](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:145) could imply.

   **Note:** RGB/LCD setters are nonpersistent, but selecting the sweep’s power mode persists through `power_set_mode()` (`power.c:329`). The whole sweep is not necessarily flash-write-free.

5. **Should-fix — show the reserve unscaled by default.** [Plan:80](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:80)

   The observation is valid: **5 h 01 min 29 s**, once, after the cut on the older firmware. [docs/battery.md:302](/Users/jdlien/code/ak820-pro/docs/battery.md:302)

   Scaling that duration assumes the same usable reserve energy, converter behaviour, cutoff history, radio, and endpoint under another load. None was measured. The current mode also changes the effective screen load: Lights out should not pay continuously for its stored LCD level.

   Present: **“After 0%: about five additional hours observed once, with a dim screen.”** Keep it separate from the headline and typical-day calculation. An optional scaled estimate can be labelled an unvalidated extrapolation, not “measured once” beside a newly calculated duration.

6. **Must-fix — distinguish what the calculator predicts from what the board reports.** [Plan:85](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:85)

   The board’s time-left is remaining gauge energy divided by its historical **awake average**. That average includes awake dim/dark periods, excludes deep sleep, retains history, and eventually has a 12-hour time constant. It predicts neither a full charge nor future nonstop typing at the selected controls. It also excludes reserve and is unavailable on USB, at unknown level, or after the cut. Sources: `battery.c:619`, `battery.c:722`, `battery.c:782`.

   Thus “the same quantity, a little short” is misleading. Even under a steady full-white history, the fixed-state versus proposed cap-inclusive figures differ by about **14%**. Other usage histories can change the direction of disagreement.

   **Must-fix — state the supported firmware and lighting scope prominently.** This is a calculator for this custom firmware; stock-firmware consumption is unmeasured ([docs/power.md:459](/Users/jdlien/code/ak820-pro/docs/power.md:459)).

   Import must retain RGB enabled/effect state and LCD on/off state, not merely HSV and a saved level. Unsupported effects need an explicit result. This includes **Alphas/Mods**, a static two-colour effect whose second hue depends on speed (`quantum/rgb_matrix/animations/alpha_mods_anim.h:9`), as well as animations.

7. **Number audit.** References in the first column are lines in [POWER-CHARTS-PLAN.md](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md).

   | Plan claim | Check and classification |
   |---|---|
   | **35–38:** 106.9, 39.1, 8.64, 7.1 mW; 3.636/2.533/2.294 µW | **Note — correct.** Exact conversions of `battery.c:575–582`. |
   | **37:** 82 LEDs | **Must-fix — wrong.** Actual count is **81**, as explained above. |
   | **40, 136, 174:** 24 screen levels, indices 0–23, full duty 48 | **Note — correct.** `graphics/display.c:203`. |
   | **47:** within 0.6% at every step | **Should-fix — overstated.** The old offline fit reproduces **0.6% for paired state means**. Individual lit holds reach about **0.94%**. This is not validation of the current executable model. |
   | **48:** purple within 0.2% | **Should-fix — qualify.** Correct for the old fit’s reconstructed drive. Exact QMK colour plus 81 LEDs and current constants predicts **211.20 mW**, about **0.33% below** the recorded 211.9 mW. Current-model discrepancies reach about **0.80%** across the RGB sweep’s state means. |
   | **50:** 27.33 mA off, 36.70 mA at duty 48 | **Note — correct.** Paired means in `current-map-20261015-2210/summary.txt:28–32`; these include bench USB data. |
   | **61:** 15,579 mWh | **Note — correct source value.** Also the firmware capacity constant. It includes an estimated bridge over a logger outage, so avoid implying five-digit experimental precision. `drain-2f/README.md:112`. |
   | **70:** 150‰, cap 128 | **Must-fix — values correct, boundary wording wrong.** It is **≤150‰**. The energy-fraction interpretation remains an assumption. |
   | **81:** 5 h 01 min reserve | **Note — correct rounded observation.** Exact recorded duration is 5:01:29. |
   | **92:** ~52 h full white/LCD 5 | **Must-fix as a headline check.** A held-state reference; current pinned arithmetic gives **52.9 h fixed**, **60.3 h with the assumed tail**. |
   | **92–93:** 50.39 h logged, USB ~2.3%, ~51.5 h untethered | **Note — supported approximations.** Using 7.1 mW gives **2.296%** and **51.57 h**. |
   | **93–94:** typing costs about 1% | **Should-fix — unsupported by the cited evidence.** `docs/power.md:444` says typing’s own cost has not been separated. A held-awake measurement is useful, but does not establish a universal 1% continuous-typing correction. |
   | **95:** everything max/2.4G ~46 h | **Must-fix as a headline check.** With the stated +5 mW extrapolation: **46.6 h fixed**, **51.7 h with the assumed tail**. |
   | **95:** white 128 ~4 days; lights off ~6 days | **Note — reasonable rounding.** LCD 5 gives **102.1 h** at white 128 and **140.4 h** with RGB off; every light off gives **145.7 h**. |
   | **100:** 13.25/13.8 mW, ~49 days | **Should-fix — distinguish radios and firmware.** BT gives **48.99 days**; 2.4G gives **47.04 days**. Firmware’s 13.35 mW gives **48.62 days**. The measured 3.2 mA BT figure is supported. |
   | **107:** Balanced ~67 mWh/pause; Saver ~6 | **Should-fix — conditional.** Current model/LCD 5 gives about **66.0/6.14 mWh above sleep**, only for pauses long enough to traverse the relevant ladder. |
   | **115:** awake 2.4G adds ~5 mW | **Note — supported as the stated extrapolation**, not a firmware constant or lights-on measurement. |
   | **118:** R3 measured at ~73 mA | **Should-fix — stale/misleading.** R3 averaged **79.6 mA**, rising from roughly 73 to 90 mA. The ~73 mA figure describes the high-voltage map/start. `a1-summary.txt:1`. |
   | **118:** 3.40 V cut | **Note — correct default.** It is qualified by the firmware’s voltage estimate and dwell, not an instantaneous precision threshold. `battery.c:1257`. |
   | **17, 140:** about 45 states, two hours, 2% | **Note — plausible planning estimate.** There are **44 awake entries plus sleep**. Two awake passes take **88–132 minutes** before overhead; predicted consumption is roughly **1.4–2.4%**. A new hour-long sleep measurement adds another hour. |
   | **142:** value 3 produces drive 1/255 | **Note — correct**, but values **1 and 2 also do**. |
   | **176:** LCD readout `level*100/23` | **Should-fix — specify rounding.** Actual display uses `(level*100 + 11)/23` with integer division. Level 5 displays **22%**. `param_overlay.c:63`. |
   | **223–225:** HC_POWER uses 27 of 29 bytes | **Note — correct.** Payload occupies `data[3..29]`; bytes 30–31 remain. `hid_protocol.c:867`. |

   The “already public” statement and current browser-support assertions cannot be independently verified from repository files alone; I did not access external services.

8. **Contributions for an owner-facing page.**

   **Must-fix — pause count alone cannot determine a typical day.** [Plan:105](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:105) Ten two-minute pauses and ten hour-long pauses have different stage costs. Add pause duration or clearly defined schedule presets. Account for all 24 hours once: either stage durations explicitly, or sleep as the baseline plus incremental awake costs. Include the final absence after typing.

   **Suggestion — present the headline as a short timeline.** [Plan:64](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:64) For full white/LCD 5:

   > **About 60 hours of continuous typing to 0%**  
   > About 45 hours at your brightness, then 15 hours automatically dimmed.  
   > Model estimate for the reference keyboard; assumes dimming begins with 15% of usable energy remaining.

   Keep the observed reserve below this, separately. This preserves the intended “longest active use at this setting” while making the automatic setting change visible.

   **Should-fix — separate fit accuracy from runtime uncertainty.** A 0.6% fit residual is not a 0.6% battery-life error bar. Show the measured 50–52-hour fixed-light drains as evidence, and disclose capacity, cutoff, load, unit, and ageing limitations beside the estimate. If offering capacity or dimming-point sensitivity controls, label their ranges as assumptions.

   **Suggestion — make savings concrete.** Show current total draw and the change from the selected setting. Under the pinned model, reducing white from 255 to 128 saves about **142 mW**; turning a maximum backlight off saves **39.1 mW**. Those comparisons are easier to act on than coefficients.

   **Should-fix — define the chart’s reference conditions.** [Plan:167](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:167) Label each curve “other lighting off” if that is its meaning. A combined setting has two knob positions, so one “your settings” dot has no unique x-coordinate. Use separate markers for the knobs and a total-power readout or component bar.

   **Suggestion — retain Plot/SVG, with discrete values and accessible alternatives.** Draw actual integer settings, preserve the first-lit step, avoid smoothing through nonexistent levels, and provide labelled values/table access. Explain that equal slider positions across colours do not mean equal perceived brightness. Include units, assumptions, and model revision in exported SVGs.

9. **Architecture and tests.**

   **Should-fix — separate the reusable maths from the page.** [Plan:153](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:153) A small `model.js` ES module imported by both `index.html` and `node --test` is simpler than extracting embedded scripts into a Python harness. No framework or application bundler is necessary.

   **Should-fix — make generation deterministic and fail closed.** Extract all firmware-dependent values from the exact `deps.lock` SHA: coefficients, capacity, LED count, CIE table, LCD table, caps, ladders, and sleep constant. Reject missing/ambiguous definitions and unexpected table sizes. Never silently substitute branch HEAD or working-tree files.

   Give `power.json` a schema version and distinguish:

   - Firmware model.
   - Measured evidence and its conditions.
   - Scenario assumptions and extrapolations.

   Prefer structured measurements over rounded `summary.txt` text. Extend the sweep output to retain full-precision results and requested/read-back settings. Preserve both raw bench power and the explicitly corrected untethered value.

   **Must-fix — strengthen the numerical oracle.** [Plan:184](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:184) Compile the pinned C colour/model code against host stubs with the **real LED count**, then compare JS results. The existing simulator defaults to working-tree sources and an 82-LED stub; it is not presently an independent check of the proposed page.

   Required cases include exact RGB channels, CIE-before-HSV ordering, hue boundaries, zero/first-lit values, all LCD levels, one RGB intercept, 149/150/151‰, all modes, screen messages, RGB cut, and Always on’s refusal to sleep. Test fixed-state runtime separately from cap-inclusive runtime and the board’s historical-average ETA. Test daily schedules with short, long, zero, and maximum-duration activity.

   **Should-fix — make deployment validate the same artifact it publishes.** [Plan:192](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:192) Commit generated JSON for review, add a regeneration/check mode, and have CI reject drift. Because the firmware clone is gitignored, CI must explicitly obtain its pinned commit; it need not run the full firmware setup/build. Validate on PRs, deploy only from the chosen main-branch workflow, and publish only `site/`. Include generator, tests, evidence, and `deps.lock` in workflow triggers. Test relative URLs under the repository’s Pages subpath. Vendoring the chart dependency would remove CDN availability from the calculator’s operation.

   **Should-fix for later import/WebHID work.** [Plan:220](/Users/jdlien/code/ak820-pro/plans/POWER-CHARTS-PLAN.md:220) One additional LCD-level byte does not encode its separate on/off state. A version bump also requires updating consumers: [ak820battery.py:99](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:99) accepts only version 1. Define compatibility before changing the reply.

   Keep the first import path through the existing host transport. For WebHID, “read-only” must mean a fixed allowlist of semantically read-only requests—queries still send HID reports, and HC_POWER uses the SET-value envelope. Validate lengths, command/page/version, and field ranges; retain the explicit daemon-coexistence tests described in CLAUDE.md. Connecting USB also makes live battery ETA unavailable, so importing settings and comparing live battery runtime are separate operations.

**Verdict: revise before building.** Resolve the LED count and oracle, label the 15% tail as an assumption, separate fixed-state and continuous-use results, define pause durations, and correct the sleep measurement path. The plain-JS, generated-data, GitHub Pages architecture can remain.