# Codex on P2b's code (`a9f750ff`), 10-25 night

Prompt: `plans/review-prompt-p2b-code.txt`. No mandatory change before the flash;
flashed at ~02:55.

## Dispositions

1. **`mutants.py` builds the old scale:** taken, after the flash: its builds get
   run.sh's scale selection (and its Windows read gets an encoding).
2. **`ind_timing.py --lcd` could measure a dark or capped screen:** taken before
   any timing run: it requires the level set, the panel on and the effective
   level equal to it, and records the effective level.
3. **`--lcd` alone could keep a cancelled preview:** taken: the open-edit guard
   runs for `--set` or `--lcd`.
4. **`menu_p1b_gates.py`'s ±5:** taken: the expected values follow the
   percentage rule (`pct_of`/`val_of_pct`), the back-one-detent check expects the
   start's percentage's own value, and the start is put back exactly over VIA.
5. **Legacy replay on the new build (levels 20 and 22 move a tick):** taken,
   after the flash: the replay keeps a row's ticks directly (the adapter gets a
   ticks override), so a historical log replays exactly on either build.

## The review, verbatim

**No mandatory change before the gremlin test flash.** I found no P2b firmware defect or compatibility blocker in `flash.sh`. The host validation is not yet clean, however.

These can wait until after flashing, but should be corrected before relying on the affected tests:

1. **P2 — Mutation builds still use the old scale.** [mutants.py:175](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/mutants.py:175) copies neither `sim_bkl.h` nor `indicator_levels.h`. Its clean `l_forced_ceiling` run therefore expects `SIM_DIM_CAP == 4`, while production `power.c` supplies 37. This is independent of the reported Windows encoding failure. Apply the scale selection to every mutation build, including its nested rebuilds.

2. **P2 — LCD timing can measure a dark or capped screen.** [ind_timing.py:59](C:/Users/jdlien/code/ak820-pro/scripts/ind_timing.py:59) checks requested `level`, ignoring the returned `on` and `effective`. Thus `--lcd 42` can pass while effective brightness is zero. Establish and verify the effective workload, and record it with the results.

3. **P2 — LCD-only timing can preserve a cancelled preview.** [ind_timing.py:49](C:/Users/jdlien/code/ak820-pro/scripts/ind_timing.py:49) checks for an open edit only with `--set`. With `--lcd` alone during a Screen preview, op 6 snapshots the preview; op 4 cancels the edit; cleanup then reinstates the preview value. Apply the edit guard whenever either setting option is used.

4. **P2 — The board gate retains obsolete RGB-step expectations.** [menu_p1b_gates.py:145](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1b_gates.py:145) expects ±5, whereas the current editor advances one displayed percentage. For example, 86 advances to 89, but line 152 expects 91. This predates P2b, but this board will encounter false failures. Compute expectations using the current percentage conversion.

5. **P3 — Legacy replay on the new build is not universally exact.** [sim.c:119](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:119), used by [count.c:418](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/count.c:418), converts ticks back through a representable level. Legacy level 20 changes **33→32 ticks**, and level 22 changes **42→43 ticks**: ±815 µW. Preserve ticks directly for exact historical replay, or document the approximation. The existing R3/2e logs use levels that retain their ticks.

The firmware checks look sound: the accumulator stays bounded and ISR-owned; shared settings remain byte-sized volatiles; caps cannot produce an out-of-range lookup; C7 still lifts the cap and supplies level 1; wake hold wins. Tick, rounded duty, and immediate power writes agree. All 101 generated duties matched the generator, including default **42→5 rounded ticks** and cap **37→4 rounded ticks**.

Pinned simulator builds retain the legacy branch and unchanged baseline inputs. `ak820battery.py` accepts v8 and exports `bkl100`; legacy exports retain `bkl`. Flash backup/restore handles RGB and keycodes without interpreting LCD levels, and `devhook.py` reports the firmware’s maximum.

The previously deferred consumers remain deferred: [power_model.py:114](C:/Users/jdlien/code/ak820-pro/scripts/power_model.py:114) until its pin advances, [current_map.py:133](C:/Users/jdlien/code/ak820-pro/scripts/current_map.py:133) before another sweep, and [gauge_replay.py:63](C:/Users/jdlien/code/ak820-pro/scripts/gauge_replay.py:63) before consuming new logs.

The local default flash binary matches the reviewed `a9f750ff` artifact; its verified ELF has **144 B** heap clearance against the **128 B** floor. I changed nothing. Process launches were denied, so C/Python suites and hardware timing were not run; verification was source tracing, arithmetic checks, and artifact inspection.