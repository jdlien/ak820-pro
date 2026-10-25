# Codex on P2b's design (the Screen in 1% steps), 10-25 night

Prompt: `plans/review-prompt-p2b-design.txt`. Line references are to `8b4aec16`.

## Dispositions

1. **`battery_sim` isn't pinned, and breaks (must fix):** taken. It builds the
   working tree's battery.c and power.c, so it follows the scale now:
   `run.sh` writes `sim_bkl.h` (`SIM_BKL_100`) and copies `indicator_levels.h`
   when `display.c` has no 24-entry `bkl_duty[]`; `sim.c`'s adapter then takes
   the 0-100 level and its rounded ticks, as display.c does (the pinned builds
   keep the 24 levels); the dim cap's check is `SIM_DIM_CAP` (37 or 4); and a
   replayed row's backlight goes through its ticks (`bkl_ticks`,
   `sim_bkl_from_ticks()`), from "bkl" (0-23) or "bkl100" (v8), so an old log
   replays on the new build and a new log on an old one. Run here without its
   sanitizer pass (this Windows toolchain has no asan): 177 scenarios ok, none
   failed; `mutants.py` stops on Windows' cp1252 reading a source file, as it
   would without this change.
2. **The log's `bkl` scale (must decide):** taken: `BATTERY_LOG_VERSION` 8, and
   `ak820battery.py` accepts 8 and writes the byte as a new column, `bkl100`;
   `bkl` always means 0-23. A tool that reads only `bkl` (`gauge_replay.py`, for
   the fixed historical drains) fails on a v8 log instead of misreading it.
   Without the decoder's change, `flash.sh`'s log dump would have refused v8.
3. **The tests:** taken in part:
   - the tick is pure in `indicator_levels.h` (`bkl_tick_pin()`, and
     `ind_duty_ticks()` for `display_backlight_duty()`), and the host tests run
     it: full and zero hold the pin and the accumulator, a level change keeps
     the residual and the count, every level's ticks within half a tick and
     never decreasing, the default's 42 at 5 ticks, the cap's 37 never dimmer
     than the old 4;
   - the Screen editor's slow and fast steps, the bar and the value; the saved
     LCD byte's 0, 1, 2, 43, 101, 102, 0x80 and 255 (`kbee.c`);
   - `bkl_effective()` (the caps, C7, the wake hold) and the keys' repeat are
     unchanged code on a new scale: covered on the board (the menu pass, the dev
     ops, `Fn`+`PgUp` held) and by JD by eye, not a new host harness;
   - the timing with an LCD workload: the forced runs set the LCD level by op 4
     too (`ind_timing.py`), at 42 (the old default's duty) and at fractional
     levels beside P2a's worst indicator load.
- **The dim cap's 37:** as codex says, the nearest is 36 (3.93 ticks); 37 (4.09)
  is chosen so the dim is never dimmer than the old one. Documented.
- **`power_model.py`, `current_map.py`, `gauge_replay.py`:** at the merge (they
  read a pinned firmware or fixed history), noted in the design.

## The review, verbatim

**Yes—amend the simulator/log compatibility claims and the test requirements before coding. The backlight algorithm itself needs no redesign.**

Firmware references below are to **`8b4aec16`**; the working tree was changing during review. I changed nothing.

1. **Must fix in P2b: `battery_sim` is not pinned, and existing tests will break.**

   The claim at [CONFIG-MENU-P1-DESIGN.md:1089](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1089) is incorrect for this simulator. [run.sh:8](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/run.sh:8) selects the working firmware and copies its sources at line 15.

   Changing the cap to 37 immediately breaks:

   - [ladder.c:532](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/ladder.c:532), which expects cap **4**.
   - [count.c:166](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/count.c:166), which expects four ticks of backlight draw. The unchanged [sim.c:88](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:88) uses `sim_bkl = 10`; cap 37 leaves that at old-table duty 10, producing **115045 µW instead of 110158 µW**.

   New-log replay is worse: [count.c:418](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/count.c:418) assigns `bkl` directly, and [sim.c:93](C:/Users/jdlien/code/ak820-pro/scripts/battery_sim/sim.c:93) indexes a 24-entry table without checking it. Values above 23 read out of bounds; smaller percentages silently use the wrong duty.

   **Change:** include the simulator’s level/duty adapter and cap expectations in P2b. Preserve historical logs’ old scale explicitly. Keeping the production duty API at 0–48 does not preserve a stub that derives duty from level.

2. **Must decide before coding, implement before collecting new logs: identify the changed `bkl` scale.**

   [The draft’s log paragraph:1087](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1087) changes the byte’s meaning without identifying its scale. [battery.h:32](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.h:32) still declares log version 7. [ak820battery.py:272](C:/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:272) exports raw `bkl`; [line 370](C:/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:370) prints the version only to stderr, outside the CSV.

   A recorded `bkl=10` therefore cannot distinguish old level 10 from new 10%. Updating the replay table alone would misinterpret historical logs.

   **Change:** specify a log-version/scale discriminator and preserve it in exported data. For example, bump the log version and export `bkl_scale` or `log_version`, treating existing unmarked files as legacy. A version bump also requires updating [ak820battery.py:305](C:/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:305), which currently rejects versions above 7.

3. **Must expand the acceptance plan: test the LCD integration, not only the shared arithmetic.**

   [The P2b tests:1106](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1106) omit the interactions most likely to regress. P2a’s [test_ind_levels():2639](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:2639) tests the helper, not `display_backlight_tick()`.

   Add:

   - LCD tick transitions through zero, fractional and full duty with a retained accumulator; stop drives low, restart at full writes high immediately.
   - Requested power, caps `0/37/0xFF`, C7’s floor/cap bypass, and wake hold taking precedence—including `display_set_power()`’s immediate write.
   - All 101 rounded duty results, endpoints, and effective-state overrides.
   - Screen slow/fast steps, bar and readout, rollback before key/repeat/HID writes, and repeat cancellation.
   - Actual boot application of unset/invalid/default, saved Off and 100; version mismatch; deferred saves and preview cancellation.
   - Explicit LCD workloads for timing. [ind_timing.py:55](C:/Users/jdlien/code/ak820-pro/scripts/ind_timing.py:55) sets only indicators. Establish/read back LCD levels through ops 4–6; compare old 5 with new 42 and exercise fractional duty alongside P2a’s worst indicator workload.

**What can wait:**

- **`power_model.py` can wait until the firmware pin advances.** It really reads `deps.lock` through `git show` ([line 43](C:/Users/jdlien/code/ak820-pro/scripts/power_model.py:43)). Its [24-entry parser:114](C:/Users/jdlien/code/ak820-pro/scripts/power_model.py:114) must change with that pin; retain the correct interpretation of historical sweep levels. `power_oracle.c` itself can remain unchanged.
- **Other tooling omissions:** [current_map.py:133](C:/Users/jdlien/code/ak820-pro/scripts/current_map.py:133) still sweeps old levels through 23; update before another comparable sweep—new 23 is only about **4.92% electrical duty**, formerly full. [gauge_replay.py:63](C:/Users/jdlien/code/ak820-pro/scripts/gauge_replay.py:63) also uses the old table, but can remain legacy-only for its fixed historical drains.

The requested firmware paths otherwise fit the plan:

- **Tick and sleep:** use `uint16_t duty` and compare full duty against `IND_FULL`, not 48. Retaining the ISR-owned accumulator is safe. Every-tick GPIO writes avoid P2a’s restart-cache problem. Existing sleep checks use effective level `>0`, so need no rescaling.
- **Mappings:** default **5→42 = 4.96875 ticks** is correct. **4→37 = 4.0859375 ticks** is a deliberate upward exception: nearest rounding gives **36**, at 3.9296875 ticks. Document that distinction.
- **Battery model:** `(duty + 128) >> 8` preserves its contract; maximum error across the actual table is about **0.404 mW**.
- **Persistence/HID/menu:** version 6 and encoded values 1–101 fit. Version mismatch resets the whole keyboard block; poison remains invalid. Shared HID state also covers **op 6**; op 5 still changes power. Menu storage/signatures, C7, repeat, and the splash need no further design change beyond those listed.

Independent simulation passed all 101 duties with retained residuals. C/Python suites were not run because process launches were denied.