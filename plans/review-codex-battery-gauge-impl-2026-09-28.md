# Codex review of the battery gauge implementation

`codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh -s read-only`, 2026-09-28 ~14:30, against firmware `b8b64162af` + `8627554513` and the parent repo at `2c9d037`. Verbatim; dispositions are in [BATTERY-GAUGE-PLAN.md](BATTERY-GAUGE-PLAN.md#implementation-review-dispositions).

**Flash after specific fixes.** I would require findings 1–8 below to be resolved before flashing this implementation.

I read the revised plan, implementation summary, resulting files, and baseline changes. The C simulator could not run: `mktemp` was denied by the read-only sandbox. Findings below are code traces, supplemented by executed in-memory arithmetic/state checks and synthetic packet tests of the actual Python reader. No files were changed.

1. **P1 — Failed ADC conversions can release the RGB cut after USB has been unplugged.**

   [battery.c:186](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:186) preserves `ext_run` on failed conversions. Meanwhile, `ext_ticks` keeps advancing solely because the remembered supply is EXTERNAL, and [protection_tick:545](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:545) treats that as proof permitting restoration.

   **Trigger:** Start on battery with the cut latched. Supply valid USB readings and CHRG low for one second. Unplug, release CHRG, and return failed ADC conversions thereafter. `ext_run` remains qualified, supply stays EXTERNAL indefinitely, and the cut releases about four seconds after unplugging. Confirmed with a source-equivalent state trace.

   **Fix:** Qualify restoration using fresh positive external-power evidence. Expire VDD evidence and reset the restoration dwell when neither valid external VDD nor qualified CHRG supports it. A remembered classification must not complete the five-second release condition.

2. **P1 — Charger-only transitions reuse charging medians, producing false FULL and large percentage bounces.**

   The ring is cleared only on a **supply** change ([battery.c:199](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:199)). Charging can stop while supply remains EXTERNAL. [full_tick:405](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:405) then trusts the old median, while [level_report:453](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:453) immediately removes the 150 mV correction.

   **Triggers:**

   - Start with seven charging reports of 100. CHRG releases because of a fault, VDD remains external, and subsequent reports are 90 every five seconds. At ten seconds, the median is still 100: firmware declares FULL and sets 100%, despite two fresh reports of 90. At twenty seconds, the median becomes 90 and the display falls to 75%.
   - While charging at `5C=80`, the corrected level is 168‰, displayed as 15%. Release CHRG long enough to exhaust its one-second hold, with a report arriving before charging resumes. The unchanged median is now interpreted without correction: 639‰, displayed as 65%. Resuming charging preserves that inflated level.

   **Fix:** Track charger-current transitions separately from supply transitions. Require post-release evidence for FULL and for switching to the uncorrected curve; do not reinterpret the old charging ring. Debounce brief CHRG interruptions and apply a controlled transition to the new estimate.

3. **P1 — Charging enforces neither the advertised cap nor the visible step limit on an existing level.**

   [level_report:459](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:459) limits the target but never reduces an already excessive level. Its assignment also permits arbitrarily large upward steps. [level_tick_1hz:480](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:480) only increments values below the cap.

   **Triggers:**

   - Reach FULL, unplug briefly, then reconnect while CHRG remains low and `5C=100`. The remembered 1000‰ survives unchanged throughout charging. The panel can show 100% for hours before this charge terminates.
   - Boot charging at `5C=80`, acquiring 15%. Raise reports to 90 before the sixty-second session qualification. At qualification, the direct assignment jumps to 45%. The charge-log test checks monotonicity but does not assert its `w_big` counter.

   **Fix:** Centralize charging output policy: make entry into a new charging session explicitly cap the level at 970‰, then enforce bounded upward movement. Reserve 100% for qualified FULL or its subsequent discharge history.

4. **P1 — A brief replug discards an outstanding post-charge re-seat.**

   [battery.c:204](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:204) sets `reseat` after a qualified charge, but the following line clears it on every transition back to EXTERNAL.

   **Trigger:** Charge for more than a minute. Unplug for three seconds—insufficient to acquire three post-unplug reports. Replug for ten seconds, then unplug again. The first unplug clears `session`; the replug clears `reseat`; ten seconds cannot qualify another session. The final discharge therefore retains the charging estimate. If it is too low because of the provisional IR correction, the ratchet prevents recovery for hours. Confirmed with a source-equivalent state trace.

   **Fix:** Preserve an owed re-seat across brief reconnects. Clear it when a valid correction is consumed, rather than merely when external power returns.

5. **P1 — Critical zero reports can leave a high green percentage on the panel for roughly forty-five minutes.**

   [protection_tick:554](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:554) cuts after three zeroes, but the level still descends through the ordinary 1%-per-six-medians ratchet. [draw_battery:1436](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1436) shows “Low” only when the **smoothed percentage** rounds to zero.

   **Trigger:** Acquire approximately 90%, then receive sustained zero reports. Protection cuts promptly, but the percentage takes roughly forty-four minutes to reach “Low”. The temporary alert expires much earlier. Moreover, at zero the bar disappears and the text/outline remain white: the specified red “Low” presentation is absent.

   **Fix:** Expose qualified critical-low status independently of the smoothed level. Make it override the ordinary percentage presentation immediately, with a persistent red indication. Keep protection and the display ratchet separate.

6. **P1 — The report counter detects reception but cannot preserve every received report.**

   [c5_intake:273](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:273) consumes exactly one cached value whenever the counter differs. The parser can accept several frames before the next battery tick ([ch582f_ajazz.c:1065](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1065)); command retries make closely spaced replies a relevant case.

   **Trigger:** Receive valid reports 59 and 60 between two 100 ms battery ticks. The counter advances twice, but only 60 enters the median and log. Three zero frames in that interval likewise count as one zero. Thus the promised per-report aggregates and critical-report count are not implemented for bursts.

   **Fix:** Deliver reports through a bounded queue or a per-report intake hook. Preserve each value and reception time; do not multiply the final cached value by the counter delta. Define whether retry responses count as independent protection evidence.

   Ordinary counter wrap, `65535 → 0`, is handled correctly by the inequality comparison.

7. **P1 — ADC outages break the fixed-period log contract and silently misdate history.**

   [log_task:641](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:641) refuses to finish an interval when `acc_n == 0`. The host nevertheless reconstructs every interval as exactly 600 seconds ([ak820battery.py:149](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:149)).

   **Trigger:** Finish an entry, then have no valid ADC samples for twenty minutes while `5C` and the main loop continue. The next valid conversion produces one entry covering that extended interval. The host places the preceding entry only ten minutes earlier. Longer outages also saturate the `5C` count; sufficiently long ones wrap `acc_led_n`.

   There is another inherited timing defect here: at an even-millisecond first call, `acc_start = now | 1` places the start one millisecond in the future. Unsigned elapsed time becomes `UINT32_MAX`, emitting an immediate partial entry.

   **Fix:** Close every scheduled interval regardless of ADC validity, representing missing VDD explicitly and resetting all aggregates. Use a separate initialization flag instead of modifying timestamps with `| 1`.

8. **P1 — A transient zero can falsely show “No Batt”, then leave the restored percentage beside an empty bar.**

   [battery_is_absent:207](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:207) uses the latest raw zero without freshness or persistence qualification. The display clears the bar for absence, but restores it only when `level_changed` is true ([display.c:1518](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1518)).

   **Trigger:** Boot on USB with a full pack whose initial charging pulse lasts less than three seconds. Neither presence latch is set. After fifteen seconds, one report of zero makes presence false even while the median and level remain 100. The next report of 100 restores the percentage, but `level_changed` is false and the cleared bar remains empty indefinitely.

   **Fix:** Qualify absence using sustained fresh evidence. Also repaint the fill whenever presence changes back to present, independently of percentage changes. The current simulator does not compile `indicators.c`, so its “no_pack” case cannot catch this.

9. **P2 — The countdown’s floor does not accomplish its stated panel behavior.**

   The 910‰ floor rounds to **90%** in [battery_level_pct:494](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:494). Starting at 1000‰, the display reaches 90% after approximately four hours while `5C` can still remain 100. The simulator explicitly expects this ([sim.c:172](/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:172)), despite the plan’s “never claims the clamp’s exit early” rationale.

   **Fix:** Either keep the visible clamp value at least 95%—925‰ is the rounding boundary—or explicitly revise that rationale and accept 90% as the coarse clamp presentation.

10. **P2 — Configurable protection thresholds can incorrectly treat a clamp bound as a measurement.**

    [battery.c:557](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:557) says the bounds compare correctly, but that holds only for suitable thresholds.

    **Trigger:** A pack at 4.18 V reports 100. Configure cut at 4100 mV. Firmware compares the lower bound, 4036, against 4100 and cuts, although the actual pack is above the threshold.

    **Fix:** Reject unsupported threshold ranges or implement bound-aware comparisons. The default 3550/3400 mV thresholds are safely inside the observable range.

11. **P2 — The required debug age is missing.**

    [display.c:887](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:887) reads age only to substitute `--` after twenty seconds; it never renders the age required by plan §1.5. A nineteen-second-old reading looks like a just-received one.

    **Fix:** Show a compact numeric age. The current value strings fit their column budget; adding age requires shortening the label/voltage formatting deliberately.

Other checks passed by inspection or the stated read-only tests:

- Synthetic packets decoded correctly through the actual Python v1/v2/v3 reader. V3’s header occupies bytes 3–15 and its entry bytes 16–31: the 29-byte write from `&data[3]` fits exactly. HC_CONN byte 31 and its battery offsets agree.
- Raw-HID handling, CH582 parsing and battery housekeeping execute serially in the main loop; I found no concurrent log-copy race. The written-count detects entry movement during an ordinary v3 dump.
- Conversion/interpolation arithmetic and normal ten-minute sums fit their integer types. The seven-element sort, LED-buffer sum and flag reads introduce no obvious large computation. `display_set_alert()` only updates state; it does not synchronously draw.
- Power-cap composition preserves the cut across user toggles and ladder changes. The saved daily ELF’s SHA-256 matches its manifest; `power_task()` is a bare `bx lr`, and the linker reserves 6,144 bytes for the heap. This verifies the ladder gate, not hardware stall timing.

**Required before flashing:**

- Fix protection restoration, charger-transition evidence, charging limits and pending re-seat lifetime: findings 1–4.
- Fix critical presentation and presence/bar recovery: findings 5 and 8.
- Preserve report intake and the log’s fixed-period contract: findings 6–7.
- Run the real C simulator with regressions, then repeat artifact checks on the rebuilt firmware. Meter agreement, actual LCD timing and the remaining hardware gates still need bench verification.

**Simulator scenarios to add:**

- Every listed counterexample, with reports arriving at varied phases around supply and CHRG transitions.
- EOC timeout separately from a completed conversion returning zero; ADC failure during cut restoration and across complete log periods.
- Multiple reports per tick, counter wrap, invalid `0xFF` frames, stale recovery, and report gaps during ratchet qualification.
- Charging step-size assertions, remembered FULL followed by charging, charger faults below the clamp, and reconnects before re-seat acquisition.
- Real presence logic and recorded drawing operations; both ladder builds with `power_task()` actually called, variable idle time, RGB toggles and backlight caps.
- Empty/partial/full/wrapped log rings, odd/even boot timestamps, written-count wrap, entry movement during dumps, and v1/v2/v3 packet fixtures.