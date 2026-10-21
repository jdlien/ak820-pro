**The firmware fix is sound. I found no firmware safety blocker, one required landing condition, and a few documentation corrections.** References below use the reviewed commits’ line numbers.

1. **Must-fix at landing — include the firmware pin in the host merge.**  
   [deps.lock:20](/Users/jdlien/code/ak820-pro/deps.lock:20) still pins `9e52400ec9`. This is the dependency you already identified.

   Safest sequence: merge and publish `36330d5ec8` first; then land the host changes **and its pin in one host commit**, so main never exposes the incompatible combination. Verify the final pair with the default simulator. [run.sh:8](/Users/jdlien/code/ak820-pro/scripts/battery_sim/run.sh:8) reads the firmware checkout, not `deps.lock` directly, so updating the pin alone does not update its inputs.

2. **Should-fix — the host branch misses the old coefficients in the battery documentation.**  
   [docs/battery.md:951](/Users/jdlien/code/ak820-pro/docs/battery.md:951) still states **3,636 / 2,533 / 2,294**. Update these to **3,681 / 2,565 / 2,322**, specifying sums over 81 LEDs.

   Related cleanup:
   - [docs/battery.md:848](/Users/jdlien/code/ak820-pro/docs/battery.md:848) retains the earlier single-slope model. Label it explicitly as superseded or point to the current formula.
   - [rgb_fit.py:20](/Users/jdlien/code/ak820-pro/scripts/rgb_fit.py:20) and its printed “today” labels describe the historical **2.857 µW** model. Rename that comparison; the recorded model column should remain historical.
   - [BACKLOG.md:28](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:28) should record the fix when landed. Preserve actual flash history in `CLAUDE.md` and `current-status.md` until the flash happens.

3. **Should-fix — qualify “N is the fit’s only error” and “exact.”**  
   [rgb_fit.py:46](/Users/jdlien/code/ak820-pro/scripts/rgb_fit.py:46), [BACKLOG.md:44](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:44).

   Changing N uniformly scales all three fitted input columns, **even though the recorded per mille is an integer**. Thus the *same approximate fit* transforms exactly: slopes ×82/81, unchanged intercept and residuals. I reproduced:

   | Coefficient | Refit, nW/unit | Firmware |
   |---|---:|---:|
   | Red | 3681.2502 | 3681 |
   | Green | 2564.5260 | 2565 |
   | Blue | 2322.0115 | 2322 |

   But the per-mille conversion is lossy. For example, red at value 16 has drive 2: its actual channel sum is **162**, whereas logged `led 2` reconstructs **123.93**. Consequently, this is not an exact recovery of physical drive or “true” slopes.

   Reconstructing the recorded solid settings using QMK’s CIE table gives approximately **3681.16 / 2565.98 / 2323.79**, with intercept **7.600 mW** rather than **7.713 mW** against measured RGB-off. That is a separate, small calibration refinement; it need not block this count correction.

   Also, the rescale applies to the **unrounded fit**, not exactly to the old integer constants. In particular, blindly scaling rounded green would round to 2564; **2565 is correctly obtained from the refit**.

4. **Note — the diagnosis and executable LED count are confirmed.**  
   [keyboard.json:53](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keyboard.json:53) contains **81 RGB entries**, versus 82 key positions. [config.h:32](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:32) explains the unlit knob. QMK derives the count from layout length.

   [sn32f2xx.h:33](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.h:33) maps the driver count to that generated count; [sn32f2xx.c:974](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:974) sums those committed LEDs. [battery.c:754](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:754) reports the time-weighted sum divided by **81 × 3 × 255 = 61,965**.

   I found no remaining executable 82-LED/246-channel assumption in the requested firmware and host paths. The driver’s “82–128 LED copy” at `sn32f2xx.c:966` is only a stale timing-comment example. `LAYOUT_82_ansi` correctly names the key layout.

5. **Note — the gauge changes safely, but not as a uniform percentage shift in displayed level.**  
   [battery.c:676](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:676) increases modelled energy by at most **2.168775 mW**, at full white. With backlight level 5, reported draw becomes **296.584 mW**, previously **294.415 mW**: **+0.737%**.

   - **Level count:** consumes energy slightly faster while counting, including post-unplug relaxation. Capacity and the 10‰ floor are unchanged.
   - **Ratchet and hold:** [battery.c:1133](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:1133) retains the same voltage bounds. Below-band holds still discard pending count energy; total energy still accumulates. These corrections can mask the small slope change.
   - **Low cap:** [power.c:215](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:215) still enters at **≤150‰**, potentially earlier. With uninterrupted full-white counting and no band corrections, entry is about **20 minutes earlier**. It sheds load sooner.
   - **Time left:** [battery.c:729](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:729) uses the corrected awake average and counted level. Sleep energy remains unchanged.
   - **HC_POWER:** [hid_protocol.c:888](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:888) exposes the corrected draw, average and energy without a protocol change. `ak820battery.py` and `current_map.py` decode those values rather than duplicating the model.

   RGB-off, sleep and externally powered counting paths retain their behavior. Voltage warning/cut thresholds are independent of these coefficients. Arithmetic remains comfortably within its existing integer widths.

6. **Note — the simulator expectations remain valid; no newly misleading mutant pass found.**  
   [count.c:8](/Users/jdlien/code/ak820-pro/scripts/battery_sim/count.c:8)’s **300.65 mW** expectation should stay: corrected arithmetic gives **300.657 mW** at its level-10 backlight. The smaller simulated buffer offsets the larger slopes. Your reported failures with old firmware and corrected stubs are therefore meaningful.

   `sleeps.c` shares that expectation; ladder boundary tests still inspect 151/150‰ directly. [colour.c:44](/Users/jdlien/code/ak820-pro/scripts/battery_sim/colour.c:44) already overrides the count to **81**, so its DRIFT hash needs no adjustment. `ladder_check.py` checks normalized drive and caps, not these slopes.

   [mutants.py:117](/Users/jdlien/code/ak820-pro/scripts/battery_sim/mutants.py:117) explicitly exempts the existing **“re-seat before RELAX_S”** survivor. That weakness predates this fix; a successful run does not mean every mutant was caught. The white-only energy stub also does not independently validate each colour’s coefficient.

7. **Note — retain A, base, capacity and the charging tail for this fix.**  
   [battery.c:573](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:573): changing N leaves the fitted intercept unchanged. Its adjustment from measured RGB-off to model RGB-off therefore remains valid. `P_BASE_UW` and measured capacity have no LED-count dependency. An eventual exact-drive refit should reconsider A alongside the slopes; this correction does not require it.

   [count.c:417](/Users/jdlien/code/ak820-pro/scripts/battery_sim/count.c:417): correcting replay conversion and coefficients together nearly cancels. Across every integer `led_pm`, old-simulator versus corrected-simulator RGB power differs by less than **0.014 mW**, from coefficient and integer rounding. R3 should remain essentially unchanged; individual count transition times can move. This is expected even though the real board’s model increases by about 0.7%.

   `tail_fw.c`, `tail_grid.py` and `tail_fw_grid.py` exercise the independent charging-tail model. No tail refit is warranted.

8. **Should-fix — qualify the retained accuracy claim.**  
   [docs/power.md:238](/Users/jdlien/code/ak820-pro/docs/power.md:238) and [docs/battery.md:953](/Users/jdlien/code/ak820-pro/docs/battery.md:953): “within 0.6% at every step” should identify **paired state means**. Using corrected executable arithmetic against the rounded summary, I get **0.552% maximum error for paired means**, but **0.924% for individual holds**. Purple is about **+0.161%**. This supports the correction without overstating its validation.

I reran the fit and pure numerical checks, inspected both commits, and checked their diffs. Simulator and compiler results are your supplied evidence; I did not rerun builds or access hardware.

**Verdict: firmware `36330d5ec8` is cleared to merge and include in the next dev flash after the current test session. Host `df8553b` is cleared as part of the atomic host-plus-pin landing, not alone as currently committed. The should-fix documentation items are not flash-safety blockers.**