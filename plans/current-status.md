# Current status

Updated 2026-10-08 (the newest block is first below; the crash hunt's notes follow it). The crash hunt's section was last updated 2026-09-24, 12:45; its plan is
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md). The live work is Phase 1b,
below.

## Why

One spontaneous, unexplained watchdog reset on 2026-09-22 at ~13:13
([incident](../history/incident-2026-09-22-wdt/README.md)). The retained
operation breadcrumbs added that afternoon
([WATCHDOG-BREADCRUMBS.md](WATCHDOG-BREADCRUMBS.md)) will name where the main
loop stopped next time. The crash hunt adds what they cannot say (a CPU fault
versus a hang, the PC, stack depth, why blits time out) and tries to provoke
the next reset instead of waiting for it.

## 2026-10-08 — RESUME HERE

**Phase 1b is mid-B3, and flash 2 is built but for B3's numbers.** The plan is
[`BATTERY-GAUGE-REFINE-PLAN.md`](BATTERY-GAUGE-REFINE-PLAN.md); its "As
built" section (just before the review dispositions) has every step with
hashes. Nothing is pushed (JD: push only when told). Phase 2 is still
note-taking only, but its order is agreed
([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md), "Phase 2: the agreed
order").

**On the board: flash 1c**, `647c12f26d` (token `0x0c93c530`), since 14:05
10-06.
- Flash 1 (`4293607b4b`, 10-05 12:28) failed gate 3: the accounting cost
  2.5%. Flash 1b (`97a24c6e20`) trimmed it and passed.
- Flash 1c adds a diagnostic profile of slow CH582F calls.
- The soaks named both culprits:
  - **C1:** the RTC period's PCF path, 6-8 flash writes a day on battery,
    each blinking the LEDs.
  - **D2:** the battery-only stalls are `battery_5c_report`'s 64-byte
    insertion sort, run for each of the three reports that arrive together
    every 5 s.
- The records: [`../history/battery-2026-10-05-flash1/readings.csv`](../history/battery-2026-10-05-flash1/readings.csv).

**Flash 2: firmware branch `phase1b-flash2`**, local only, on top of flash
1c. As of 10-07 it was at `54c437028b`; **its head is now `28f260225f`, with
trial 1's tail** (see "2026-10-08 so far" below). It holds:
- B's charging model, with the tail from B3 trial 1 (was a placeholder: K 190,
  L_KNEE 775, T_TAIL 313 min);
- log v5;
- the camera page in the clock's font (JD approved it from
  `scripts/camera_page_preview.py`'s render);
- **the D fix** (the trimmed mean by histogram, identical to the sort on
  99,972 estimates);
- **C2** (`rtc/rtc_persist.c`: the first save at 10 min, then at most one per
  6 h).

Every host check passes (`scripts/battery_sim/run.sh`, `tail_fw_grid.py`,
`mutants.py`, `scripts/diag_sim`, `scripts/ch582_sim`), and it builds clean
(heap 3496 B).

⚠️ **Its worktree is in a session's job directory**
(`/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2`, moved there 10-08). If it is
gone: `git -C qmk_firmware-ak820pro worktree prune`, then `... worktree add
<dir> phase1b-flash2`. The simulators take its keyboard directory through
`BATTERY_SIM_SRC=`, `DIAG_SIM_SRC=` or `--src`. To build it, check out its
commit detached in `qmk_firmware-ak820pro`, run `./build.sh daily`, then
`git checkout ak820pro-jdlien` again.

**Left for flash 2**, after B3:
1. `scripts/battery_charge.py --tail K_CC L_KNEE T_TAIL_H --header
   <worktree>/keyboards/a_jazz/ak820pro/battery_tail.h`, with T_TAIL 5.22 h
   from B1. Widen `tail_grid.py`'s grid first if K_CC falls outside 160-230.
2. Rerun every check.
3. The RAM.
4. A codex gate-7 review (`codex exec -m gpt-6-astra -c
   model_reasoning_effort=xhigh -s read-only ... < /dev/null`, in the
   background, saved verbatim beside the plan, every finding dispositioned).
5. The flash procedure.
6. Gate 8: the soaks and the per-event checks.

**B3 trial 1 is done and analyzed**
([`../history/battery-2026-10-07-partial-charge/`](../history/battery-2026-10-07-partial-charge/);
the plan's "B3 trial 1" in "As built"):
- **`K_CC` ≈ 133 pm/h, measured two ways.** On the curve at the 60-min
  point it is 132.3 (122-142). By runtime from the unplug to the RGB cut it is
  133.5. That is below B1's 165-213 bound, beyond the uncertainty, and the
  charge current matched 10-01's and 10-04's. The tail stays feasible at
  `K_CC` 120-145, with `L_KNEE` ~515. The plan's rule: trial 2, then decide.
- **`RELAX_S`, provisionally 1800 s.** A re-seat reads ~1 point high at
  6-10 min and ~0.3 at 30. The first 6 min were not filmed.
- **The board died at 07:56 on 10-08**, by its clock in the video. The RGB cut
  was at ~02:25, and the reserve lasted 5 h 31 min. The RAM log is gone, and
  the pack is flat: recharge it soon.
- **The video:** `~/Downloads/PXL_20261008_030743525.mp4` (3.9 GB) and the
  `-trimmed.mp4` (3.26 GB), not in git. Pulled with adb as below; read with
  ffmpeg crops (the camera was on a tripod, so fixed crops work: LCD
  `crop=500:450:740:150`, keys `crop=460:460:200:620`; `signalstats` YAVG
  finds the cut and the death).
  ```sh
  ADB=~/Library/Android/sdk/platform-tools/adb
  $ADB devices -l                                    # the phone, authorized
  $ADB shell 'ls -lt /sdcard/DCIM/Camera | head -8'  # the newest PXL_*.mp4
  $ADB pull /sdcard/DCIM/Camera/PXL_<name>.mp4 ~/Downloads/
  ```

**2026-10-08 so far (newest last):**
- **Flash 2 is rebuilt on trial 1's numbers and cleared by codex.**
  - Firmware `28f260225f` on `phase1b-flash2`, host `91804d9`:
    `K_CC` 133, `L_KNEE` 533, and `RELAX_S`/`PAUSE_S` 1800 s.
  - Gate 7 found 3 bugs; two verification passes followed. The second
    said **"flash"**.
  - JD chose to show the model's number while charging (F3, option A).
  - The artifact: `ak820pro-builds/out/via-daily-28f260225f-20261008-112003.bin`,
    token **`0xdf1e8b99`**.
  - The worktree is now `/Users/jdlien/.claude/jobs/dbe817d8/tmp/qmk-flash2`.
  - Every disposition is in the plan, "Gate 7"; the review is in
    `review-codex-battery-refine-impl2-2026-10-08.md`, with both
    verification passes.
- **Trial 2 is under way** in `../history/battery-2026-10-08-partial-charge/`.
  - The recharge from flat ran 10:45:06-11:50:23, stopped at a charging 5C
    of 75 (≈ trial 1's end).
  - JD has filmed its relaxation from 11:51:30, which gives the 0-6 min
    trial 1 missed.

**Since 12:54, flash 2 is on the board** (token `0xdf1e8b99`, verified).
- **Trial 2** charged 14:32:15-15:15:18 (43 min 00 s). Its `K_CC` is 148.5
  pm/h, preliminary (138-159); with trial 1's 133 the mean is ~141.
- **The bench** (`docs/test-bench.md`, `scripts/bench_power.py`): the HomeKit
  outlet "Christmas Tree" powers the Acasis hub.
  - A port switched OFF still carries data, so **the board can be read on
    battery without charging**.
  - With its port switched ON, the outlet switches charging.
- **Now:** the board sits on a switched-off port (data only), discharging at
  full white. A watcher reads it every 5 min into
  `../history/battery-2026-10-08-partial-charge/watch-rgb-cut.log`, and at the
  RGB cut it dumps the log (`log-*-rgbcut.csv`).

**The night of 10-08/09 runs unattended** (JD authorized it): `scripts/bench_trial.py`
in the background since 18:38, logging every read to
`../history/battery-2026-10-08-partial-charge/night-run.csv`. In order:
- wait for the RGB cut (reads every 5 min, then every minute from 21:00), and
  dump the log;
- **trial 3:** relay on for exactly 40:00, from L = 0 (the cut is the curve's
  zero), then relay off;
- 2 h of relaxation, a read a minute, and a dump;
- relay on to FULL (gate 8's charge), and a dump.

The relay is left ON at the end. If the run failed, the relay is off and
the CSV says why.

**Next, in order:**
1. **At the RGB cut** (expected ~22:30, ±45 min): the runtime cross-check for
   trial 2. That is `K = (D × t_on_battery − L(start)) / t_charge`, with the
   on-battery time from 14:32:15 less the charge. Tell JD the lights are out.
2. **Charging is now mine, by the relay** (no button needed): since ~18:31 the
   board is on the relay cable (`scripts/usb_relay.py status | on 2 | off 2`;
   `docs/test-bench.md`, "The USB relay"). Confirm each switch with one
   `ak820battery.py` read (`supply`). `bench_power.py` no longer reaches it.
   - **Gate 8's charge from below 50%:** a full charge on the outlet, then a
     dump; check that the chg LOST/OVERRUN/self-check bits never set.
   - **Then a battery soak** for gate 8's flash-write budget and stalls.
3. **Decide `K_CC`** (~141?). If it moves, regenerate the tail, rerun the
   checks, get a codex review, and reflash.
4. **Pull JD's videos** (13:03-~14:35, 14:40-?) when convenient.

**Also:**
- **The hardware:** JD is ordering the DigiKey cart
   (`parts/digikey-order-2026-09-29.csv`: INA228, QT Py RP2040, MAX17048s)
   and needs a `uhubctl`-capable hub (`BATTERY-GAUGE-PLAN.md`, "If the
   hardware arrives"). The INA228's current shows where charging really
   slows: the knee F3 left open.

## 2026-10-04, night (superseded by the block above)

**Next: execute [`BATTERY-GAUGE-REFINE-PLAN.md`](BATTERY-GAUGE-REFINE-PLAN.md)
top to bottom, starting at its Step 0.** That is Phase 1b: refit the curve on
both runs, the charging display, the internal-flash writes behind the LED
blink, and the battery-only stalls. It is at revision 7, after six codex
rounds (gpt-6-astra, xhigh); round 6's verdict was "ready to execute". Every
round is verbatim in
[`review-codex-battery-refine-plan-2026-10-04.md`](review-codex-battery-refine-plan-2026-10-04.md),
and the dispositions are at the end of the plan. **Phase 2, the power
ladder, comes after it.** It is note-taking only until JD asks.

- **Run 2, the validation drain, is done.** Unplugged 10-02 11:00:00, the RGB
  cut came at 13:33:25 10-04 (50.56 h), and the board died at 18:34:54 (from
  JD's time-lapse). See [`../history/battery-2026-10-01-drain/`](../history/battery-2026-10-01-drain/)
  and [`../docs/battery.md`](../docs/battery.md).
- **The 10-04 charge from flat** started ~20:02, with a preservation dump at
  21:44. ⚠️ **At 22:37 the board was in the bootloader**: JD entered it before
  bed for an overnight flash, but no firmware was ready, so the log after 21:44
  is lost. **Check the board's state first:** in `ioreg`, product 28992
  (`0x7140`) is the bootloader and 32777 (`0x8009`) is running. Then follow the
  plan's Step 0, which covers both cases.
- **On the board: `759e265796`** (the fitted curve, whole percent), unless
  something else has been flashed since. Rollback artifact and build token:
  the plan's "Firmware, branch, and artifacts".
- ⚠️ **The keymap and lighting backups date from 09-29 13:57.** `flash.sh`
  must take fresh ones from the RUNNING board; see the plan's flash
  procedure.

## 2026-10-01, morning (superseded by the block above)

**The 09-28 drain test is over, and the curve is fitted, committed and NOT yet
flashed.** Plan and dispositions: [`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md).
Evidence: [`../docs/battery.md`](../docs/battery.md). Run records:
[`../history/battery-2026-09-28-drain/`](../history/battery-2026-09-28-drain/)
-- `readings.csv` (every observation, JD's words, corrections), the
`log-*.csv` dumps, and the fit's `fit-output.txt` / `fit-points.csv`.

**On the board since ~20:20 10-01: `759e265796`** (the fitted curve, whole
percent). The charge from flat before it is dumped and analysed in
`history/battery-2026-10-01-charge/`. **A validation run started at the
unplug, 10-02 11:00:00** (not 10-01 20:19: the board stayed on USB
overnight): `history/battery-2026-10-01-drain/`, white at full drive as on
09-28. The cut is due ~51.6 h later, ~14:36 Sunday 10-04. ⚠️ **Dump the
charge log before any flash or slider flip** -- a charge from flat on this
firmware is wanted for the charging side (CHARGE_IR_MV, the CV creep). The
09-28 charge took ~9.5 h; dump when the charge LED goes out (CHRG released).

**How the run ended:** FULL ~19:52 09-28 (log VDD); "Battery low" ~00:00 10-01
(3544 mV); the RGB cut ~02:13 (from the log's led_pm), **54.4 h wall, 51.6 h
equivalent full white**; lights off after that; "Low" from ~04:24 (<3.30 V);
last seen 05:19 at 3222 mV; **found dead 08:45** (the log after the 05:03 dump
died with it). On replug, 5C read a fresh 0 under charge: the cell went well
below 3.16 V before the protector cut it. A probe short at ~20:44 09-30 lost
~45 min of log and needed a slider flip (cable out) to revive -- see the 09-24
shutdown section of docs/battery.md.

**Phase 1 gates: all met.** 2 (protection) on the last night -- warn, cut, the
cut survives the user, 5 s of USB lifts it, it re-cuts on battery. 4 (meter vs
gauge) -- eight points 4.01-3.22 V, −9 to +11 mV, including 3.22 V below the
fitted range.

**The fit** (`scripts/battery_fit.py`): 0% at the cut (3400 mV, JD's choice),
knots at even steps of level, the clamp exit at 89.6% (the 90% anchor stands).
Each USB plug-in is credited with the charge it put back (r = 10.5; durations
from each entry's mean VDD) and the dim start at its lower power; ±20% on
those moves the level at 3.70/3.55/3.50 V by ≤ 0.1 point. Simulator 27/27
after updating three expectations that were the old curve's numbers (343 ->
187 pm at 5C 70; "starts high" ≥ 50). Firmware commit on `ak820pro-jdlien`.

**Next:**
1. ✅ Charged, dumped, flashed (`759e265796`). The validation run: panel
   readings with times are the data (no plug-in needed); dump rarely, and
   again from the 'Battery low' warning on; the security camera from there.
   Then compare the panel against the runtime it actually had left.
2. **The queued fixes** (plan, "Queued"): "Charge" not the 95 guess while
   charging at the clamp with nothing saved; keep the re-seat owed past a
   clamp reading just after unplug; the stalls (`25:6 10:2449`, worst 35 ms
   blit -- measure first); the backlight flashing bright during a flash write;
   the warning's threshold and re-arm (JD to decide); later, drop tenths.
3. Validate the curve on a second run, ideally filmed (plan, ideas).
4. Phase 2 is **not built**; JD is in note-taking mode.

**Traps from this run:**
- `flash.sh` backs up keymap and lighting **only if the board is running** --
  do not enter the bootloader first, or it restores the 09-24 pastel.
- A flash wipes the RAM log and the EEPROM: **dump first**.
- Dump with the slider on **BT**, then unplug within a minute (longer is a
  charging session, which re-seats the level and charges the pack).
- A loose cable charges without enumerating: check `ioreg` for `0C45`.
- ⚠️ **`0C45` alone does not mean running**: the bootloader is `0C45:7140`,
  the board `0C45:8009`. Before a flash, prove it is running with a raw-HID
  read (`ak820battery.py` answers), not the vendor id -- on 10-01 the board
  was already in the bootloader and flash.sh restored the 09-29 backups.
- Use `set -o pipefail` in dump one-liners, or a failed dump prints "saved".
- 09-30 19:57: `hostagent/ak820battery.py` refused ("no repo venv provides
  'hid'") although `venv/bin/python3` imports `hid` fine. Run
  `venv/bin/python3 hostagent/ak820battery.py log ...` directly. Cause:
  `venv/bin/python3` symlinks to pyenv's 3.13.9, which is also what
  `#!/usr/bin/env python3` runs, and `venv_bootstrap._same()` uses
  `os.path.samefile` (follows symlinks), so its exec-loop guard calls the
  venv "the interpreter we already are". Fix (not applied): guard on
  `sys.prefix` against the candidate's venv root instead.
- **Docs pass, 09-30 evening:** `docs/battery.md` restructured (current
  facts first, withdrawn claims in a dated table at the end), the display
  doc's battery row and debug row, firmware comments (comment-only), and
  as-built notes in the plan. `5C` cadence: 2-3 reports per 5 s poll cycle,
  bunched -- the mechanism is unconfirmed.

## 2026-09-28, 14:55 (superseded)

**The battery gauge (Phase 1) is built, not flashed.** Everything is in
[`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md): the plan, codex's review of it
([verbatim](review-codex-battery-gauge-plan-2026-09-28.md)) and a disposition
per finding.

- **Artifact:** `via-daily-f2bcc26f14-20260928-145123.bin` (token
  `0x97fc73c0`), firmware `f2bcc26f14` on `ak820pro-jdlien`. The idle ladder
  is compiled out; the VDD estimator is deleted.
- **Reviewed twice by codex** (plan, then implementation: flash after eight
  fixes, all applied). `scripts/battery_sim/run.sh`: 23 scenarios, 15 mutants
  caught.
- ✅ **Running since 2026-09-29 ~13:58: `deef6053dd`**
  (`via-daily-deef6053dd-20260929-135459.bin`) -- the level from a trimmed mean
  of 64 `5C` reports, the panel in tenths (`BATTERY_SHOW_TENTHS`, for the
  calibration), ~6 saved-level flash writes a cycle (every write blinks the
  LEDs ~7 ms), log v4. Flashed mid-way through the 09-28 drain test after a
  dump; the run continues. Queued fixes: plans/BATTERY-GAUGE-PLAN.md, "Queued".
- (Previously `487cb8e9f0`, from ~15:41 on 09-28: (`via-daily-487cb8e9f0-20260928-153833.bin`)
  -- `27bf8a4f06` plus "Charge" for "Chrg". ✅ **The charger does terminate
  with the board running in BT on USB:** a top-up of a full pack held CHRG
  low ~11 min (VDD 4484-4489 mV), then released at 15:43 with VDD 4530 mV;
  the gauge went to full and 100%, and saved it. (The worry was the 09-28 note
  that the LED went out "with the board off".)
- (Re-flash ~15:36: `27bf8a4f06`)
  (`via-daily-27bf8a4f06-20260928-153336.bin`), which adds the saved level: a
  reboot at the top clamp (every slider flip) restores it instead of guessing
  95. First read after the flash: BT position on USB, charger topping up,
  level 95 -- the guess, because the flash erased the saved level. It goes to
  100 when CHRG releases, and is saved from then on.
- (First flash, ~14:58, `f2bcc26f14`, from the bootloader, so the keymap and
  lighting came from the 09-24 backups (lighting: effect 2, val 137 -- not the
  solid white of the 09-25 run). First read on USB, cable position: supply
  external, state full, level 100%, `5C` 100, VDD 4831 mV, log period 600 s,
  thresholds 3550/3400 pack mV.)
- **Next: the bench checks** (Phase 1 gates 1-7). ⚠️ The meter comparison and
  the protection test need the pack **under the top clamp** (`5C` < 100),
  i.e. some hours of use on battery first.
- `deps.lock` still pins `44e7314e65`; move it when this is released.
- The 09-27/28 meter readings were recovered from a session transcript into
  `history/battery-2026-09-25/readings.csv`. ⚠️ Write readings there as they
  are taken, not only in conversation.

Everything below is the 09-27 state, kept for its findings; where it says the
battery row must stop showing VDD, or to calibrate the estimator, the gauge
has superseded it.

## Installed right now (2026-09-27, 13:00)

**The work is on the battery: read [docs/battery.md](../docs/battery.md)
first.** Task 8 in `.taskmaster/tasks/tasks.json` tracks it.

- **Firmware: `via-daily-b35d8672b3-20260924-205842.bin`**, token
  `0x583b65cf`. Production fixes (`6b60458dd0`) plus the start of the battery
  work: VDD from the SN32 ADC; a once-a-minute RAM log; low-battery warn and
  RGB cut at 3.55 V and 3.40 V on VDD; the voltage on the battery row.

### ⚠️ Three findings that change the plan

1. **VDD is a BUCK-BOOST output. It is useless as a gauge.** With the pack at
   3.81 V the debug page read **VDD 3.903 V** — above its own input, which no
   linear regulator can do. Across the run the pack fell **4.18 → 3.74 V
   (−440 mV)** while VDD moved **+3 mV**. ⚠️ **This kills the prediction that
   VDD would start following the pack below ~3.95 V.** There is no dropout
   coming.
2. ⚠️ **The estimator (`36be68f16a`) is dead on arrival.** It derives a level
   from VDD via a lithium curve, and VDD is a constant. **Do NOT calibrate the
   `CAL` constants in `battery.c`** — the earlier "Next" step in this file said
   to, and that instruction is withdrawn. The input carries no signal.
3. ⚠️ **The low-battery protection may be inert.** Warn (3.55 V) and RGB cut
   (3.40 V) are thresholds **on VDD**, which is pinned at 3.90. They cannot
   fire until the buck-boost collapses, possibly below the pack protection
   circuit's trip point. **Unverified — confirm before relying on it.** Cheap
   test: `ak820battery.py cfg 3950 3900` (RAM-only, resets on reboot) and see
   whether warn and cut fire at a VDD the rail actually reaches.

### ⭐ The module's `5C` value DOES track the pack

The premise that `5C` is pinned at 100 is **withdrawn**. It moves, and the
`Fn`+`D` debug page row 8 shows it (`ch582_get_battery()`, `display.c:878`).
Settled readings against a standard NMC curve:

| pack | 5C | curve | offset |
|---|---|---|---|
| 3.99 | 85 | 75.9% | +9.1 |
| 3.84 | 78 | 59.8% | **+18.2** |
| 3.81 | 74 | 56.2% | **+17.8** |
| 3.74 | 66 | 46.6% | **+19.4** |

**The last three agree within ±1 point.** `5C` moves 120 points/volt where the
curve moves 132 %/V — it tracks the curve's *shape*, which is why the offset
holds. ⚠️ **If it holds below 3.70 V the remap is a subtraction** (`level =
5C − 18`). The 3.99 outlier is unexplained: charge memory, a wrong generic
curve at the top, or real depth-dependence. **Readings below 3.70 V separate
them, and that is the single most valuable thing to collect.**

⚠️ `5C` is **noisy (±3) and useless while charging** — it snaps to 100 the
instant USB appears and decays over hours. Any gauge built on it needs a median
filter, a ratchet that never rises on battery, and a hold-off after charging.

### ⚠️ TODO before any release: the battery row must stop showing VDD

`b35d8672b3` shows **VDD on the battery row**, which replaced the CH582F's
hardcoded 100%. ⚠️ **It is a constant.** VDD is the buck-boost output and it has
moved 3 mV while the pack fell 440 mV, so the row conveys exactly as much as the
fake 100% it replaced — less, arguably, since "3.90 V" is not even in units a
user can misread.

It **earned its place as an instrument**: watching it sit still while the meter
fell is what exposed the buck-boost, and a percentage derived from VDD would
have hidden that behind a plausible-looking number. But it is a diagnostic, not
a feature, and diagnostics survive by inertia unless someone writes them down.

**Replace it with**, once the mapping is calibrated:

1. `V_pack = (5C + 374.5) / 117.8` — exact to ~±3 mV, ~8.5 mV per count
2. that voltage through **this cell's** curve, fitted from
   `history/battery-2026-09-25/readings.csv`, not a generic NMC table
3. displayed as **bars plus a percentage in 5% steps** — the granularity is what
   tells the user it is an estimate; 1% resolution is a claim we cannot back
4. **ratcheted**: never rising while on battery, reset on charge
5. ⚠️ volts stay on the `Fn`+`D` debug page, where an engineer wants them

### The discharge run

- **Started 2026-09-25 10:54.** ⚠️ Interrupted 09-26 13:22 when the slider went
  to `cable` to wake the Mac, which **reset the board and lost the RAM log**;
  ~20 min on the charger, unplugged again 14:03. Running since.
- **Readings: `history/battery-2026-09-25/readings.csv`** — meter, screen, and
  the analysis inline.
- **At 12:54 on 09-27:** pack **3.74 V**, `5C` **66%**, 49.3 h elapsed, ~51%
  consumed at 1.03 %/h. **Projected ~94 h total (3.9 days), ~45 h left.**
  Lighting full pastel to 15:36 on 09-25, **solid white 100%** since.
- **What to do:** a meter + debug-page reading whenever you pass it. That pair
  is the calibration data. Nothing else is needed from the run.

⚠️ **Two traps for the next run.** The RAM log is **720 entries at one a
minute = 12 hours**, then it wraps — a multi-day run keeps only the last 12 h
unless `LOG_PERIOD_MS` goes to 300000 (5 min → 60 h). And **the Mac needs USB
to wake**, which is what ended this run; use `caffeinate -d` or a second
keyboard.

### Hardware decided on, not yet ordered

- ✅ **MAX17048 fuel gauge** — DigiKey `1528-5580-ND` (Adafruit 5580). The
  retrofit. ModelGauge, no sense resistor, ±1-2%.
- ✅ **1.25 mm 3-pin male+female pigtails**, Amazon ~$15/20 sets, for the pack
  tap. ⚠️ Digi-Key's ready-made PicoBlade assemblies are **female-to-female**
  and cannot make a passthrough alone.
- ✅ Keep the **JST SH 4-pin Qwiic cables** already in the cart — they mate
  with the MAX17048's STEMMA QT, so no soldering to the module.
- 🤔 **QT PY RP2040** — optional, only as a bench rig to prove the gauge before
  touching the keyboard. Any spare MCU does.
- ❌ **INA228 dropped.** Its purpose was fitting a load model for a
  software coulomb count; the MAX17048 replaces that in hardware.
- ❌ **PPK2 not now.** Right instrument for the idle-ladder work later
  (task 9), wrong one for this. ~CA$150 at DigiKey, not the CA$255 Amazon ask.

### ⭐ The retrofit is much easier than it looked

**The board already has an I²C bus.** `halconf.h:15`: an external **PCF8563
RTC on P0.14/P0.15** over the ChibiOS software (bit-banged) I²C fallback LLD.
So SDA and SCL are routed, a driver exists and works, and **no free GPIO is
needed**. MAX17048 is `0x36`, PCF8563 is `0x51` — no conflict. Solder targets
become the PCF8563's SO8 pins or its passives, **not** a 0.5 mm QFP leg.

Full plan, wiring, the three electrical checks (logic levels across two
supplies, pull-ups that may not exist as components, bus capacitance) and the
pin audit: **[docs/battery.md](../docs/battery.md)**, "A real fuel gauge,
retrofitted".

⚠️ The bus is **rationed** — one transaction per main-loop pass with the LCD
DMA idle, because RTC I²C on port A glitches the flash SPI1 pins mid-DMA
(`ak820pro.c:585`). A gauge read every 30 s is negligible but must go through
that gate.

### What is achievable — read before building anything

A trustworthy percentage is **not reachable on the stock hardware**: no ADC
path to the pack, `5C` is the only signal and is voltage-derived, and NMC's
curve is flat through the middle. **The objective is a 5-bar / 10% indicator
that never goes backwards, ±10% mid-range and better at the ends, plus a low
warning that actually fires.** The MAX17048 is what buys a real percentage.

- **Committed locally, not flashed, not pushed** (firmware `ak820pro-jdlien`):
  `91d854f2ff` and `b35d8672b3` (the flashed build); `36be68f16a` (the
  estimator — ⚠️ **do not calibrate, see above**); `3b85686ff7` (the idle
  ladder — ⚠️ **do not flash during a calibration run**, it dims the lights and
  changes the load profile mid-measurement).
- **Pushed 2026-09-24 ~14:00:** ChibiOS `a4f8412134`, firmware `6b60458dd0`,
  main `882b322`.
- **Bluetooth test, 2026-09-24:** 57 minutes on BT with the cable in: 9,597
  frames, 0 drops, 0 malformed, 2.9% late. Then, unplugged, the board **went
  dark with charge left** and came back only on USB: unexplained
  (docs/battery.md).
- **Still not done:** the `HC_BLITFAULT` forced-failure tests; a hunt on
  `6b60458dd0` (`deps.lock` still pins `44e7314e65`).
- **Also open:** the unplug glitch (task 8.6), and the RGB colour breakup at a
  215 Hz field rate (task 9) — ⚠️ **not fixable in firmware**: the fringe
  scales linearly with field rate and needs ~4 kHz, past this M0. Colour choice
  is a free 2×, and a single saturated channel has none at all
  (`docs/leds.md`).

## ✅ The overnight hunt on 44e7314e65 passed (2026-09-24 04:57)

Ten hours: 1,964,044 blits, no timeout of any kind, no busy-wait, no
non-flash stall of 25 ms or more, no reset
([evidence](../history/crash-hunt-2026-09-24-final-daily/)).

## ✅ The DMA "never-start" is solved (2026-09-23)

Every "never started" blit timeout on record was a **completed** transfer
whose completion the SPI0 half-transfer handler erased. It read `RIS` and
then cleared every flag, so a DMATCIF raised between those two instructions
was lost.

Only 660-byte clock digits were exposed, and the reason is timing. The
equal-priority LED row ISR delays that handler until 188–258 µs after the
arm, and a 660-byte transfer completes at 220 µs. The fix (ChibiOS
`c57623d0d2`) clears only what was read and re-checks for the completion.
E5 ran **3 hours and 580,060 blits with no timeout**.

Found with `CURCNT` instrumentation. Along the way, `DMACNT` turned out never
to count down, so "never started" was a label, not a diagnosis. A Codex review
(`gpt-6-astra`, reasoning effort high) supplied the equal-priority
correction. It also found the other fixes of the day:
- the USB lock nesting;
- the CH582F pump order;
- the `IC` read-modify-write.

Full analysis and every disposition:
[`FIRMWARE-FINDINGS-2026-09-23.md`](FIRMWARE-FINDINGS-2026-09-23.md).
Evidence:
[`history/crash-hunt-2026-09-23-lost-completion/`](../history/crash-hunt-2026-09-23-lost-completion/).

## ✅ The fault recorder works, after a fix (2026-09-23)

All seven `HC_FAULT` modes were verified on hardware. The first runs of
modes 1 and 3 came back invalid: on this chip **the last SRAM write before a
loop that never writes again is lost at the watchdog reset**, and every
handler commits its record and then spins. So the final `FAULT_MAGIC` store
was lost, every time. `DSB` doesn't help; one sacrificial write after it
does (`commit_terminal()`, firmware `02db293696`). The watchdog also **recovers a
locked-up core** (mode 4), with the record intact. Details:
[`CRASH-HUNT-PLAN.md`](CRASH-HUNT-PLAN.md), "Third result", and
[`docs/hardware.md`](../docs/hardware.md). ⚠️ The v7 daily build lacks the
fix: a fault on it would record as invalid, so a real crash would read
"unavailable".

## ✅ The fix held: ten hours, no reset (second hunt, 23:00 → 09:00)

Same stress that hung v6 in 13 minutes: no reset in 10 h and 1,960,093
blits. The guard caught 7 overlaps, **all 7 alongside a DMA that never
started** -- the predicted mechanism. All 53 blit timeouts were never-starts,
all recovered by one retry. All 8 non-flash stalls ≥ 25 ms (25–26 ms) came
with a never-start recovery. Deepest stack use: interrupt 464/1024, main
680/2048. Settings verified at exit; the agent restored itself at 09:00:15
and is writing v7 rows to `ak820-health.csv`. Evidence:
[`history/crash-hunt-2026-09-23-v7/`](../history/crash-hunt-2026-09-23-v7/).

The first hunt (v6, 21:05) was stopped at 22:03. It ignored `pkill -INT` (a
background job inherits SIGINT as ignored), so it was stopped with SIGTERM
and its settings restored from its backup by hand, verified; the script now
handles both signals. Its evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).

**If the keyboard freezes in ordinary use:** leave it connected. The
watchdog brings it back in ~15 s; read `ak820 health --crash` (on v7 a fault
carries its PC: `scripts/symbolize.sh <pc> <token>`). A cold power-off
destroys the record.

## ⚠️ The hunt reproduced the hang at 21:18:52 — and the cause is found

13 minutes in: `lcd_transfer within text`. A synchronous LCD draw re-armed the
flash->LCD DMA while the glyph pump's last transfer was still in flight, which
left SPI0 unable to complete an ordinary `spiSend()`; no timeout, so the
watchdog. Full mechanism and fix in `CRASH-HUNT-PLAN.md` ("First result").
A second codex pass found the same hole in the CPU draws (Caps padlock,
battery fill, icons) and in every external-flash transaction, so the fix is
now `bus_quiesce()` at the start of every CPU transaction on either bus. That
also gives JD's 13:13 crash (typing, light load) a plausible path. A
narrow third codex pass verified the guard covers every runtime transaction
([review](review-codex-crash-hunt-impl3-2026-09-22.md)). Committed as
firmware `1b7f781887`; flashed 22:59 (see above).

## Health v7 (Part B) — daily flashed 2026-09-22 22:59; validated 2026-09-23

Daily: `ak820pro-builds/out/via-daily-1b7f781887-20260922-225845.*` (flashed
until the 2026-09-23 fault tests; lacks the lost-write fix above). A
HardFault or an unhandled vector now
writes a terminal record with the PC and the interrupted context, and a ChibiOS
halt records its caller. The record's consecutive-reset count clears after 10
healthy minutes, so three spread-out crashes can no longer switch the watchdog
off for good. Page 6 adds stack watermarks, the blit-timeout breakdown and a
build token that `scripts/symbolize.sh` resolves to the archived ELF.
Host simulation passes under ASan/UBSan; the Rust side decodes all of it (364
unit tests). Codex reviewed the implementation twice: no High and twelve
Medium/Low issues the first time
([review-codex-crash-hunt-impl-2026-09-22.md](review-codex-crash-hunt-impl-2026-09-22.md)),
two High (the unguarded bus paths above) and four smaller the second
([review-codex-crash-hunt-impl2-2026-09-22.md](review-codex-crash-hunt-impl2-2026-09-22.md)).
All fixed; the third pass left two small hunt-script fixes, also done. The archived
ELFs now carry line info: `scripts/symbolize.sh <pc> <token>` answers with
file:line.

## Next

1. ✅ The overnight hunt passed; `deps.lock` moved to `44e7314e65`.
2. **Built overnight, committed locally, NOT pushed or flashed:** firmware
   `6b60458dd0` on top of `44e7314e65`. It carries:
   - `lcd_blit_wait()` tracking CURCNT and DMAEN (start, progress, stall in
     a few ms, and the class);
   - the dashboard repainting after a blit given up for good;
   - the debug-page pump's recovery;
   - the internal-flash driver refusing to erase a sector behind a caller's
     back (ChibiOS `f247ebc639`);
   - the UART reporting hardware overrun (ChibiOS `a4f8412134`), counted on
     the instrumented console;
   - stale comments corrected.

   Clean builds: `via-instrumented-6b60458dd0-20260924-001130.bin` (token
   `0x2d80c2ff`) and `via-daily-6b60458dd0-20260924-001152.bin` (token
   `0x70bfdc04`).

   **The board's daily has no remote bootloader jump, so it needs
   JD's Fn+Esc once.** Then, on the instrumented build:
   - `HC_BLITFAULT 1`: expect an IRQ-lost timeout and a successful repaint;
   - `HC_BLITFAULT 2`: expect `[display] a blit was given up`, then a
     dashboard repaint;
   - the wireless test, with the console captured: ACK histogram, orphans,
     and UART overrun, framing and parity counts in Bluetooth mode;
   - an hour of hunting;
   - then the daily, and push.
3. **JD's wireless test** can use either build: the CH582F path is
   identical in both. It is the first real test of the serial fix and the
   pump order.
4. **Still open:**
   - FRESET SPI0 at hand-back (hygiene, deferred);
   - UART overrun counting;
   - the LED ISR's thread-class PWM calls;
   - the raw-HID flash-provisioning policy (anyone on the host can rewrite
     the external flash's assets);
   - the ACK deadline in Bluetooth mode;
   - Mac sleep/wake and the reboot test;
   - a tagged release.
5. **Parked idea** (taskmaster task 6): a QR code to the agent installer via
   a jqr.ca redirect.

## Repository notes

All pushed, 2026-09-23 ~19:00. Firmware `ak820pro-jdlien` is at `44e7314e65`;
ChibiOS `ak820pro-patches` is at `c212e20dd2`. That branch carries three
fixes from today: the serial fix `a3fdffe26d`, the SPI0 lost completion
`c57623d0d2` and the USB fix `c212e20dd2`. It also carries the reverted
dispatch attempt `2a17a73b48` and its revert `bf9310ca84`.

**`deps.lock` still pins `02db293696`** (v7 plus the lost-write fix). It moves
to `44e7314e65` once the overnight hunt passes. The recovery bundle in
`ak820pro-builds/` holds the new ChibiOS tip. `.taskmaster/` stays untracked, as
before; it now holds task 6, the QR idea. The hunt's raw output stays in
`~/Library/Logs/ak820pro/crash-hunt/`; a snapshot of the 21:18 evidence is in
[`history/crash-hunt-2026-09-22/`](../history/crash-hunt-2026-09-22/).
