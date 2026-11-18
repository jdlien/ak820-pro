# Astra's review of the bench supply's docs (2026-11-18)

Codex, `gpt-6-astra` at xhigh, read-only, on commit `16191b5` (docs/test-bench.md's "The bench supply", plans/BACKLOG.md's "The bench supply as the pack", the status page's bullet, CLAUDE.md's row). Its brief: check every claim against this repo's sources, the safety of the wiring and the procedure, whether each test measures what it claims, the links. The supply's own software (riden-bridge) was outside its reach and taken as given.

## Dispositions

Every finding was checked against the source and accepted; the fixes are in the commit after `16191b5`.

| # | Finding | Checked | Disposition |
|---|---|---|---|
| 1 | The thresholds are judged on a 64-report trimmed mean (~2-2.5 min), not on single readings; 30 s steps can't settle it | `battery.c` "`5C`: intake, freshness, the estimate", `C5_RING` 64 | Accepted. Test 1 holds ~3 min a step (two leases at 25 mV); test 2 times from the estimate's crossing; the hover check reworded for the mean; the zero rule noted as the one on raw reports (`c5_zero_run`) |
| 2 | The ladder's sleep can't show with the data line on, nor in Always on | `sleep.c` `DSB_USB`; `power.c` `power_sleep_wanted()` | Accepted. Run in Balanced at a level of 15% or less, the data line cut with `uhubctl`, relay 2 off |
| 3 | The watchdog record can't show a brownout reboot loop (POR/LVD clear it); the logger's 1 Hz can miss fast cycling | `watchdog_record.h` | Accepted. USB re-enumerations on the Mac (the data line on) and the current as the evidence; the analyser if the case is open |
| 4 | The sweep gives the reserve's lower end, not its size | `plans/BACKLOG.md`, "A day of typing after the LED cut" | Accepted. Reworded; the size still needs a logged discharge past the cut |
| 5 | Energy from USB against energy into the pack is the whole system's figure, not the charger's efficiency | `docs/power.md` "Charging": the board runs from USB while it charges | Accepted. Reworded; the draw after the charger stops is the part to take out |
| 6 | A dark keyboard on the supply can't settle the 09-24 shutdown, which happened on the pack | `docs/battery.md` "The shutdown of 2026-09-24" | Accepted. It rules out the protector for that event only, and points at the board's power path; test 5 (the real pack) excluded |
| 7 (P3) | An older backlog item still gave the warning as 3550 mV | `battery.c` `warn_mv` 3680 | Accepted. Updated to 3680 mV, the curve's 10%, ~5 h before the cut at full white |

The task list (`.taskmaster`, tasks 22-26) was updated to match.

## The review, verbatim

Found six test-plan issues, all **P2 / medium**:

1. **[plans/BACKLOG.md:38](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:38): the timing test conflates raw readings with filtered voltage.** “Any reading at or above” does not restart the timer: protection uses the **64-report trimmed mean**, spanning roughly 2–2.5 minutes ([battery.c:270](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:270), [battery.c:1289](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:1289)). **Fix:** time the 30 seconds from the filtered estimate’s crossing. For calibration at lines 15–23, explicitly capture raw `5C` samples within each step, or hold long enough to replace the filter window; 30 seconds cannot settle the firmware voltage readout.

2. **[plans/BACKLOG.md:45](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:45): the sleep test needs an exception to “data line … stay on.”** Active USB data blocks deep sleep ([docs/test-bench.md:197](/Users/jdlien/code/ak820-pro/docs/test-bench.md:197), [sleep.c:255](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:255)). Always on also never sleeps, even below 15% ([power.c:364](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:364)). **Fix:** specify Balanced, confirm the reported level is ≤15%, then cut USB data with `uhubctl` while keeping relay 2 off; observe sleep through the logger.

3. **[plans/BACKLOG.md:57](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:57): the watchdog record cannot establish brownout reboot loops.** POR/LVD invalidate that record ([watchdog_record.h:37](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.h:37)); the logger’s ~200 ms averaging and 1 Hz stream can also miss fast cycling ([docs/test-bench.md:386](/Users/jdlien/code/ak820-pro/docs/test-bench.md:386), [460](/Users/jdlien/code/ak820-pro/docs/test-bench.md:460)). **Fix:** capture boot/reset activity live with the analyser and inspect reset-cause flags after recovery; treat current pulsing as supporting evidence.

4. **[plans/BACKLOG.md:61](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:61): the voltage sweep cannot size the typing reserve.** It finds the board’s voltage endpoint, not remaining pack energy, and this pack’s protector threshold remains unidentified ([docs/battery.md:988](/Users/jdlien/code/ak820-pro/docs/battery.md:988)). The existing reserve proposal explicitly requires a logged discharge past the cut ([plans/BACKLOG.md:740](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:740)). **Fix:** retain that discharge measurement; describe the sweep as supplying one endpoint for it.

5. **[plans/BACKLOG.md:79](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:79): USB-to-pack energy ratio is not charger efficiency.** USB powers the keyboard while charging ([docs/power.md:349](/Users/jdlien/code/ak820-pro/docs/power.md:349)), so input energy includes its operating load and cable losses. **Fix:** call this the whole-system USB-to-pack energy fraction, or separately measure/subtract the operating load and upstream losses.

6. **[plans/BACKLOG.md:87](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:87): a shutdown on the supply cannot rule out the protector as the historical cause.** The September event happened with a pack far from flat ([docs/battery.md:1275](/Users/jdlien/code/ak820-pro/docs/battery.md:1275)); deliberately causing undervoltage reproduces only the symptom. Test 5 also retains the real pack. **Fix:** limit the conclusion to “the protector cannot cause this particular event while physically absent”; leave the September cause unresolved.

One **P3 / low, pre-existing contradiction**: [plans/BACKLOG.md:998](/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:998) still says the warning is 3550 mV. The new section correctly says 3680 mV, matching [battery.c:1267](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:1267). Update the older threshold and associated percentage/runtime.

The pack-replacement wiring section is sound against the repo: high-side shunt, shared ground, polarity check, open NTC with charging disabled, relay 2 off, and local voltage reference. No confirmed damaging wiring defect found. The numeric thresholds, holds, approximate clamp voltages, analyser test, CLAUDE row, and status pointer are sound. All seven added local Markdown links resolve. Nothing was modified.