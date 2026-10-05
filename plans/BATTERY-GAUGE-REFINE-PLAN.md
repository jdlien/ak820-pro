# Battery gauge, Phase 1b: the curve, charging, the blinks, the stalls — plan

**Status (2026-10-04): written, under codex review. Not started.** Phase 1 (the
gauge) is built, flashed and validated on two full discharges. This plan
refines it on what those runs measured. **Phase 2, the power ladder, comes
after it** ([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md), "Phase 2"); nothing
here builds any of Phase 2.

**Read first, in this order:**
1. This file — it is meant to be executable cold.
2. [`../docs/battery.md`](../docs/battery.md) — the evidence and every
   withdrawn claim. Do not resurrect a withdrawn claim.
3. [`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md) — Phase 1's design, its two
   codex reviews and dispositions, and the "Queued" list this plan absorbs.
4. The run records: [`../history/battery-2026-09-28-drain/`](../history/battery-2026-09-28-drain/)
   (run 1), [`../history/battery-2026-10-01-drain/`](../history/battery-2026-10-01-drain/)
   (run 2), and the charges [`../history/battery-2026-10-01-charge/`](../history/battery-2026-10-01-charge/),
   [`../history/battery-2026-10-04-charge/`](../history/battery-2026-10-04-charge/).
   Each folder's `readings.csv` holds every observation in time order,
   corrections included.

Call JD by name in docs. American spelling is fine in this repo.

---

## ⚠️ Step 0 — before anything else: dump the 10-04 charge log

The board is charging from flat on USB in the BT position since ~20:02 on
2026-10-04 (after run 2's pack died). That charge's RAM log is evidence for
workstream B and **any flash, slider flip, or loss of power erases it.**

- The 09-28 and 10-01 charges from flat terminated after ~9.5 h and ~9.4 h, so
  this one should finish ~05:30 on 10-05. Dump after the charge LED goes out
  (the log then holds the whole charge and the termination).
- `set -o pipefail; venv/bin/python3 hostagent/ak820battery.py log history/battery-2026-10-04-charge/log-<stamp>.csv`
  — call `venv/bin/python3` directly; `hostagent/ak820battery.py`'s venv
  bootstrap currently refuses (task E3).
- Prove the board is RUNNING with a raw-HID read (`ak820battery.py` answers),
  not by the USB vendor id: the bootloader is `0C45:7140` and the board
  `0C45:8009`, and only the product id differs.
- Record the dump and what it shows in that folder's `readings.csv`, then
  commit.

---

## What is established (the inputs to this plan)

| fact | value | source |
|---|---|---|
| `5C` → pack mV | `5C = 114.22 V − 361.04`; **8 meter points, 4.01-3.22 V, all within −9/+11 mV** (meter resolution 10 mV) | docs/battery.md, "Checked against a meter" |
| run 1 (09-28) | FULL ~19:52 09-28 → RGB cut 02:13 10-01: 54.4 h wall, **51.55 h equivalent full white** after crediting USB plug-ins and a dim start; clamp exit **89.6%** | `history/battery-2026-09-28-drain/fit-output.txt` |
| run 2 (10-01) | unplug 11:00:00 10-02 → cut **13:33:25** 10-04 (±5 s, from video): **50.56 h** wall, one plug-in inside it (19:29 10-03, tens of seconds); clamp exit **90.3%** (4.90 h in) | run 2 `readings.csv`, `video-trace.csv` |
| curve validation | the curve fitted on run 1, scored on run 2 (216 points): **below 3.95 V 0.1-0.6 points rms (worst +2.1); 3.95-4.036 V plateau 3.2 rms, worst −8.5 (curve reads low)** | run 2 `readings.csv` |
| the lights-off reserve | run 2: cut 13:33:25 → dead **18:34:54** = **5 h 01 min**; `5C` reached 0 (≤3.161 V) ~17:45; a **flat spot at 3222 mV** for ~30 min, seen in run 1 too | run 2 `readings.csv` |
| lights-off draw | ~1/3 of full white (rough, an upper bound: the fall rate after the cut over the full-white rate extrapolated) | `scripts/battery_fit.py` `BASE` |
| charge from flat | constant current ~3.9 h (09-28) / 4.25 h (10-01); `5C` reaches 100 ~4.0 h in; **termination 9.5 h / 9.4 h** | the two charge folders |
| VDD vs the board's own load | in constant current, LED drive 1000 → 499 ‰ raised VDD **+59 mV** (~1.2 mV per % of drive) | 10-01 charge `readings.csv` |
| the charging display on the fitted curve | `curve(V − 150 mV)` reads **~45% four hours into a charge from flat** (where ~70-80% is plausible by time), then races at 0.4%/min to 90.5 when `5C` clamps | 10-01 charge `readings.csv` |
| internal-flash writes | **816 in ~47 h** on `759e265796` (one per ~3.5 min), against ~6 a cycle designed; JD sees the ~7 ms blink "every few minutes, at least" | run 2 `readings.csv` (19:29 10-03) |
| main-loop stalls | **≥10 ms: ~37/h on USB, ~400/h on battery**; ≥25 ms: 3-4 in ~2 days; worst 36 ms (`blit`); `i2c_gap_max` 17 ms; `flash_gap_max` 7 ms | the same |
| BT ACK timeouts | 24% of frames mostly on USB, 42-48% on battery; **the CH582F TX path does not block** (`ch582f_ajazz.c:505` returns while waiting) | debug-page frames, code |

### The firmware and branch state

- **On the board: `759e265796`** (`via-daily-759e265796-20261001-201702.bin`):
  the fitted curve (`2597f88756`) and whole percent on the battery row.
- **`ak820pro-jdlien` HEAD is `241ef8fdad`**, two commits past the board: the
  `Fn`+`D` camera page (big seven-segment volts and percent) and its clock row.
  **Built, never run on hardware.** It ships with the next flash unless reverted
  (decision D5).
- `deps.lock` still pins `44e7314e65`; moving it is a release step, not part of
  this plan.
- Host checks: `scripts/battery_sim/run.sh` (27 scenarios) compiles the real
  `battery.c` and `power.c`; `scripts/battery_fit.py` fits run 1.

---

## Scope

**In:** A, refit the curve on both runs. B, the charging display. C, the
internal-flash write rate (the blink), and the LCD backlight flash during a
write. D, the stalls on battery. E, small items: the warning's threshold and
re-arm, the venv bootstrap bug, the countdown rate, the camera page's
hardware check, docs.

**Out (and where it lives):** Phase 2's power modes, the emergency reserve mode
and standby ([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md)); the camera page's
extras (later, JD); a pack tap or current logger (JD's DigiKey cart, not
ordered); a third full drain test (not needed: A validates by leave-one-out).

---

## Order of work, and the flashes

Two flashes, because the stall fix cannot be designed before it is measured:

1. **Step 0** (above).
2. **Host-only work, no board traffic:** A (refit), B's calibration analysis,
   E3 (venv bootstrap).
3. **Firmware, flash 1:** C (write-rate fix + per-field write counters), D's
   instrumentation (per-cause stall counters), B (the charging model), A (the
   refitted curve), E1/E2 (warning), E4 (countdown rate), the camera page as
   committed. Simulator, build, a codex implementation review, then flash.
4. **Hardware verification of flash 1** (gates below): write rate and stall
   counts over ≥12 h on battery and ≥12 h on USB; a partial-charge experiment;
   the camera page.
5. **Flash 2:** the stall fix D designs from flash 1's counters, if one is
   needed. Codex review, flash, a ≥12 h soak.
6. Docs, status, CLAUDE.md. Then Phase 2.

**⚠️ Every flash:** dump the RAM log first (slider on BT); prove the board is
running by raw HID; let `flash.sh` back up the keymap and lighting with the
board RUNNING (never enter the bootloader first — on 10-01 it was already in
the bootloader and the 09-29 backups were restored); JD at the keyboard. A flash
erases the emulated EEPROM (saved level, BT slot, LCD brightness, RTC period,
clock format) — expected, not a fault.

---

## A — Refit the curve on both runs

**Why:** below 3.95 V the run-1 curve already tracks run 2 within ~0.5 point;
the 3.95-4.036 V plateau is the weak spot (−8.5 worst). ~20% of the runtime
passes in ~20 mV there, so a few mV of run-to-run difference is several
points. Two runs average that out better than one.

### A1. Put run 2 on the same footing as run 1

Extend `scripts/battery_fit.py` (keep run 1's path byte-for-byte reproducible:
its current output is committed as `history/battery-2026-09-28-drain/fit-output.txt`):

- **Run 2's sources:** `history/battery-2026-10-01-drain/log-20261003-1929.csv`
  (10-minute entries, PLAIN mean of `5C`, 11:00 10-02 → 19:29 10-03) and
  `video-trace.csv` (the gauge's TRIMMED mean read off the debug page, every
  15 min 23:30 10-03 → 13:31 10-04, times ±1 min). ⚠️ Two estimators: compare
  them where they overlap in character (both are unbiased means of the same
  reports, the trimmed one drops the outer eighths); do not mix them inside one
  smoothing window without checking for an offset.
- **Run 2's time axis:** start 11:00:00 10-02 (the 11:09 entry straddles the
  unplug: credit its USB fraction from its mean VDD exactly as run 1's code
  does); the 19:29 10-03 plug-in (credit it the same way: its entry's VDD
  gives the seconds, `r` the charge put back); T ends at the cut, 13:33:25.
  No dim stretch in run 2 (`led_pm` 1000 throughout — check the log).
- **The 4-hour gap** 19:29 → 23:30 on 10-03 has no data. The smoothing must
  not bridge it with an average (A1 already splits segments at gaps).

### A2. Fit, and validate by leave-one-out

- Fit each run alone (knots at even level steps, as now), then score each fit
  on the OTHER run's points — the honest out-of-sample number. Report rms and
  worst by band: 3.40-3.60, 3.60-3.80, 3.80-3.95, 3.95-4.036 V.
- **The pooled curve:** for each knot level, the mean of the two runs' voltages
  at that level (voltage-averaging at fixed level suits level-spaced knots).
  Score it on both runs.
- **Targets:** below 3.95 V, leave-one-out rms ≤ 1.0 point and worst ≤ 3; on
  the plateau, rms ≤ 3 and worst ≤ 6. If the plateau misses, do not tune
  further on two runs — record it and take decision D4.
- The top knot stays **4036 mV = 90%** (`LEVEL_CLAMP_EXIT`): the clamp exit fell
  at 89.6% and 90.3%. 0% stays **3400 mV**, the RGB cut.
- Commit the fit's output and per-entry points to each run's folder, as for
  run 1.

### A3. Into the firmware

- Swap `curve_mv`/`curve_pm` in `battery.c`; keep the comment block's
  provenance current (both runs, the leave-one-out numbers, the plateau
  caveat).
- Re-run `scripts/battery_sim/run.sh`. Scenario expectations that are a curve
  value (as `unplug_mid_charge`'s 187 pm and `reseat_survives_replug`'s were)
  move with it — **update each with its arithmetic in a comment**, never by
  copying the new output blind.
- Update docs/battery.md's curve section and table.

---

## B — The charging display

### The problem

While charging, the level is `curve(terminal mV − CHARGE_IR_MV)`, only rising,
capped at 97% (shown as 97), then a 0.4%/min catch-up to 90.5% once `5C` reaches
the clamp, a 0.1%/3 min creep to 97, and 100 at termination. On the placeholder
curve that happened to look plausible; **on the fitted curve it reads ~45% four
hours into a charge from flat**, because the discharge curve's 4.00-4.02 V
plateau (~20% of the runtime) has no counterpart on charge — the terminal
voltage climbs steadily through those millivolts. **No constant I×R maps the
charging voltage onto the discharge curve.** And the creep reaches the 97 cap
~1.1 h before termination, then snaps 3 points (10-01 log).

Two queued fixes from Phase 1 belong here: show "Charge", not the 95 guess,
while charging at the clamp with nothing saved; and keep the re-seat owed past a
clamp reading just after unplugging (on 09-29 the re-seat was spent on a
still-relaxing clamp reading and the ratchet walked 95 → 86 at 1%/15 s).

### The design (to be confirmed by B1's analysis)

The charger is a TP4056-class constant-current, constant-voltage charger, so:

- **Constant current is linear in time.** In a real charging session (CHRG low
  ≥60 s, as now), the level rises at a fixed rate `K_CC` (%/h) from where it was
  when the session began. No voltage in the loop.
- **At the CV handover** (`5C` reaches the clamp, which happened 0-0.25 h
  before the VDD rise that marks true CV on the two logged charges): the level continues from wherever CC
  left it on a **decelerating approach** toward ~99%:
  `L(t) = L_end − (L_end − L_cv) · exp(−t_cv / τ)`, with `τ` fitted so that the
  approach reaches ~99% about when the charger usually terminates (~5.2-5.5 h
  into CV from flat). In CV the charge current decays roughly exponentially,
  so a decelerating display is the physically right shape, not a fake.
- **Termination** (CHRG released 10 s, `5C` at 100): 100%, as now.
- **The start level:** the gauge's level when the session began. Unknown (a
  boot on USB): below the clamp, `curve(V − CHARGE_IR_MV)` as a one-time seed
  (crude but bounded); at the clamp with nothing saved, **"Charge"** until
  termination or unplug (the queued fix).
- **Unplug mid-charge:** the re-seat from the post-unplug voltage, kept owed
  until the first below-clamp estimate or ~2 min on battery (the queued fix).
  The re-seat is the truth-check on `K_CC`: a charging estimate that is wrong
  costs one correction at unplug.
- **Brief plug-ins** (no real session): the level does not move (as now).

### B1. Calibrate `K_CC`, the CV handover and `τ` (host analysis first)

- **Inputs:** the three charges from flat — 09-28
  (`history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv`, 452
  one-minute entries), 10-01 (`history/battery-2026-10-01-charge/log-20261001-1947.csv`,
  66 ten-minute entries) and 10-04 (Step 0's dump). Per charge: the start, the
  `5C`-reaches-100 time, the VDD-rise (CV) time, termination; VDD through the
  taper with `led_pm`.
- **`K_CC` from timing alone needs one assumption**, the share of a full
  charge delivered in constant current (`F_CC`, typical 0.75-0.85): from flat,
  CC lasting `t_cc` hours delivers `F_CC` of the charge. In runtime terms
  `K_CC ≈ 100 · F_CC / t_cc` %/h, after first refilling the lights-off reserve
  below 0% (~5 h at ~1/3 power ≈ 1.6 h of full white ≈ 3% of a full charge, so
  the level reaches 0% only after ~3% has gone in). **That is an estimate with
  one free parameter** — B3 measures it.
- **`τ`**: from the CV span (`5C`-clamp → termination) of the three charges,
  so the approach is at ~99% at the median termination.

### B2. Simulator scenarios (gate 8 grows)

Replay each charge-from-flat log through the simulator and assert: the level
rises smoothly (no step > 1 point at the CV handover); ≥ 97% before
termination; one step ≤ 2 points at termination; 100 at FULL. Plus: a partial
charge from 50% (ends plausibly); a boot on USB at the clamp with nothing saved
shows "Charge" (`battery_level_pct()` unknown, state CHARGING); unplug
mid-CC re-seats from the voltage and never rises afterwards; the re-seat stays
owed across a clamp reading in the first ~2 min (the 09-29 case: reproduce it
from `readings.csv`'s description); brief plug-ins change nothing. Add a mutant
for each (a `K_CC` of 0, a CV jump, a re-seat spent on the clamp).

### B3. Calibrate on hardware: a partial-charge experiment (after flash 1)

From a known level on battery (≥1 h unplugged, below the plateau, ideally
40-70%): plug in for **exactly 60 min**, unplug, leave ≥60 min unplugged to
relax, read the level the voltage gives. `K_CC` measured = the rise / 1 h.
Repeat once at a different starting level if JD has the time. Compare with B1's
estimate; adjust `K_CC` if they differ by > 15%. Record in a new
`history/battery-<date>-partial-charge/`.

---

## C — The internal-flash writes (the blink), and the backlight

### C1. Confirm the writer (no fix before this)

**Prime suspect:** the persisted RTC period. `rtc.c` saves it from **two paths**
— the USB SOF window (~line 665) and the PCF trim (~line 1001) — whenever it
is ≥ 64 ticks (~0.19%) from the stored value. `docs/clock.md` measures the ILRC
wandering 7-12 ms/s (0.7-1.2%) with ~±0.1% window noise; a comment in `rtc.c`
claims the threshold "keeps temperature wander from causing steady rewrites",
which those numbers contradict. Each `kb_eeconfig_set_*` compares and settles 5 s,
so ~17 writes/h means a field really changes that often.

Confirm before fixing: **per-field change counters** in `kb_eeconfig.c` (one
`uint16_t` per field, incremented on each real change in `kb_mark_dirty`'s
callers, and a count of actual `eeconfig_update_kb_datablock` calls), exposed
on a health page (`hid_protocol.c` has the pages; pick spare bytes or add a
subcommand — document it in `ak820health.py`). Also count writes NOT from
`kb_eeconfig` (QMK's RGB/VIA eeconfig, wear-leveling consolidation): the
existing `flash_writes` minus `kb_eeconfig`'s flushes. These counters stay in
the daily build — they are how a blink is matched to a writer from now on.

### C2. The fix (once C1 names the writer)

If it is the RTC period: **persist rarely.** The stored period only seeds the
next boot, and the loop re-converges in ~4 min with a host attached
(`docs/clock.md`). Suggested policy: persist at most once per 6 h of uptime,
and only when the value has moved ≥ 64 ticks from the stored one AND held
within ±64 of its new value for ≥ 3 consecutive windows; always persist once
after the first ≥ 10 min of a cold boot with nothing stored (as now). Apply it
to both paths. The goal: **≤ 10 internal-flash writes per day** on battery with
no user setting changes. Fix the misleading comment in `rtc.c`.

If C1 names something else, design for that writer; the goal stands.

### C3. Flash endurance (an estimate, then a decision)

With QMK's default wear-leveling (`WEAR_LEVELING_BACKING_SIZE` 2048, logical
1024, `platforms/chibios/drivers/wear_leveling/wear_leveling_efl_config.h`),
estimate how many backing-store erases ~400 writes/day caused, and look up the
SN32F290's rated program/erase endurance (the datasheet in `fpb/ajazz-ak820-pro`).
Record the estimate in docs/battery.md. Expected: a non-issue once C2 lands,
but it should be a number, not a hope.

### C4. The LCD backlight during a write (decision D3)

During a write every interrupt is masked (~7 ms; Cortex-M0, no VTOR), so the
backlight's software PWM (`display_backlight_tick`, a CT16B3 ISR) freezes the
pin where it was: caught ON at a low duty, a visible bright flash (JD saw it,
10-01 ~05:16); caught OFF, an unnoticeable dark blip. The existing
`backing_store_operation_begin/end` hooks (`ak820pro.c:711`) bracket each HAL
operation: **drive `PANEL_BKL` low in `begin` when the duty is partial**, and
let the ISR resume in `end`. At full duty (always on) leave it alone. Cheap and
safe; whether to do it at all is D3 (with ≤ 10 writes a day the flash may not
matter).

---

## D — The stalls on battery

### What is known

`count_ge_10ms` grows ~400/h on battery and ~37/h on USB (run 2: 550 after
15 h mostly on USB, 13336 after 47 h). `count_ge_25ms` is rare (3-4 in two
days, all non-flash) and the worst is 36 ms, marked `blit`. The marks only keep
**maxima** per cause (`blit_gap_max` 36, `i2c_gap_max` 17, `flash_gap_max` 7),
not counts, so the ~400/h cannot be attributed yet. The CH582F's ACK wait does
not block. The 6-a-cycle level saves and the RTC writes are ~7 ms (flash),
under 10.

Candidates (each needs a count, not a guess): the PCF8563 bit-banged I2C
(17 ms max seen; does the trim path read the PCF more often on battery?); LCD
blits (the battery row, the clock band, the glyph queue); unmarked work
(`none`), e.g. the `5C` path's 64-byte sort (cheap on paper; ~1000 compares
with ~27% of the CPU left to the main loop).

### D1. Instrument (in flash 1)

- **Count ≥ 10 ms gaps per mark** (`flash`, `blit`, `i2c`, `none`), next to the
  existing maxima in `health.c`; expose them on a health page and in
  `ak820health.py --stalls`.
- Consider a fourth mark for the CH582F/5C parse path and one for `battery_task`
  if `none` turns out to dominate.

### D2. Measure, then decide (between flash 1 and flash 2)

Reset the counters (hold `Fn`+`D`), then ≥ 12 h on battery and ≥ 12 h on USB,
the board idle and the same lighting. Read the per-mark counts over USB at the
end of each (a health read is one brief plug-in on battery — note it). Then
design the fix for whichever mark carries the battery-only excess; if it is the
RTC's I2C, the C2 change may already have cut it (fewer trim windows writing,
not fewer reads — check).

**Target:** on battery, ≥ 10 ms gaps ≤ 50/h and **no ≥ 25 ms gap in a 12 h
soak**, or a documented reason the remainder is irreducible. ⚠️ A ≥ 25 ms gap
can lose a keypress (docs/hardware.md); the ≥ 10 ms count is the leading
indicator.

---

## E — Small items

- **E1. "Battery low" threshold (decision D1).** On the fitted curve 3550 mV is
  ~4.5%, ~2.3 h before the cut at full white (run 2: the video trace crosses
  3550 mV ~11:20; the cut came at 13:33). 3676 mV is 10%, ~5 h. Default: **raise to the voltage at 10%** on the
  refitted curve. Thresholds stay RAM-settable over `HC_BATTCFG`.
- **E2. Re-arm only after a real charge (decision D2).** Every plug-in re-arms
  the warning today, so each dump re-fires it after unplugging (10-01 01:06,
  seen). Default: re-arm only after a real charging session (CHRG low ≥ 60 s)
  or the pack above warn + 100 mV, as now.
- **E3. The venv bootstrap.** `hostagent/venv_bootstrap.py`'s exec-loop guard
  uses `os.path.samefile`, which follows `venv/bin/python3`'s symlink to the
  pyenv interpreter the script's `#!/usr/bin/env python3` already runs — so it
  calls the venv "the interpreter we already are" and refuses. Guard on
  `sys.prefix` against the candidate's venv root instead. Test: run
  `hostagent/ak820battery.py` by its shebang from a shell without the venv on
  PATH.
- **E4. The countdown rate.** The clamp span at full white: run 1 10.4 points in
  5.36 h equivalent, run 2 9.7 points in 4.90 h — ~1.95-1.98 points/h,
  `COUNTDOWN_S_PER_PM` ≈ 182-186 (now 190). Set it from the two runs' mean;
  simulator scenario `countdown_ease` must still pass.
- **E5. The camera page (decision D5).** Committed (`188092ac71`, `241ef8fdad`),
  never run. If it ships in flash 1: check on hardware that `Fn`+`D` cycles
  dashboard → debug → camera → dashboard, the digits are right against the
  debug page's `Batt` row, the clock row matches the dashboard clock, and the
  stall counters do not move while the page is up (it paints one segment per
  pass by design). Extras (JD: "later") are out of scope.
- **E6. Docs.** docs/battery.md (curve, charging, the reserve, the writes),
  docs/display.md (anything the charging display changes), docs/clock.md (the
  RTC persist policy), `plans/current-status.md`, CLAUDE.md's current state.

---

## Gates

1. **A:** leave-one-out results committed; the pooled curve meets A2's targets
   or D4 is decided; `run.sh` passes with each curve-tied expectation's
   arithmetic in a comment.
2. **B (host):** the three charges replay through the simulator with B2's
   assertions; the new mutants are caught.
3. **C1:** a named writer, by counter, before C2 is written.
4. **Build:** `./build.sh daily` clean (no `-dirty`), and a codex
   implementation review with every finding dispositioned (the pattern of
   `review-codex-battery-gauge-impl-2026-09-28.md`).
5. **Flash 1 on hardware:** ≥ 12 h on battery with **≤ 10 internal-flash
   writes per day** (C2), the per-field counters agreeing; the per-mark stall
   counts recorded (D2).
6. **B3:** a 60-minute partial charge's measured `K_CC` within 15% of the
   firmware's, or the firmware's corrected.
7. **Flash 2 (if needed):** ≥ 12 h on battery meeting D2's target.
8. **E5:** the camera page works or is reverted.
9. Docs updated (E6); status written to resume cold.

---

## Decisions for JD (defaults apply unless JD says otherwise)

| | question | default |
|---|---|---|
| D1 | "Battery low" threshold | the voltage at **10%** on the refitted curve (~3.68 V), ~5 h before the cut at full white |
| D2 | re-arm the warning | only after a **real charging session** |
| D3 | the backlight during a flash write | decide after C2: if writes are ≤ 10/day, leave it; else force the pin low (a dark blip instead of a bright one) |
| D4 | the plateau, if A2 misses its target | **voltage only** (accept ~±5 points there); the alternative — a time-based countdown through the plateau, like the clamp's — reads low at lighter loads and needs its own design |
| D5 | the camera page in flash 1 | **ship it** with E5's check (it is committed and cheap); revert if it misbehaves |
| D6 | the charging display's shape | B's design: linear in constant current, decelerating in constant voltage, 100 at termination |

---

## Handoff to Phase 2 (the power ladder) — what these runs give it

- **The LEDs are ~2/3 of full-white power** (lights-off ~1/3, rough). That is
  Phase 2's lever, and "take the drain out of idle, not the fun out of use" (JD)
  is about where to pull it.
- **The reserve below the cut is ~5 h with the lights off**, and the board ran
  ~50 min below `5C`'s floor. That sizes the emergency Power Reserve idea.
- **Fix C and D first**: a mode that dims the lights should not still blink every
  few minutes or stall on battery.
- Phase 2's own "measure before building" (2.6) still applies; the current
  logger (INA228) is not ordered.

---

## What this plan deliberately does not do

- Change `5C`'s line or the 0% point (3400 mV, JD's choice).
- Claim state of charge: the level stays "fraction of full-white runtime left".
- Run another multi-day drain: leave-one-out on the two runs validates A.
- Build any power mode.

## Review dispositions

(Filled in from the codex review of this plan.)
