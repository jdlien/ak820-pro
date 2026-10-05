# Battery gauge, Phase 1b: the curve, charging, the blinks, the stalls — plan

**Status (2026-10-04): revision 2, after codex's first review
([verbatim](review-codex-battery-refine-plan-2026-10-04.md); dispositions at
the end). Not started.** Phase 1 (the gauge) is built, flashed, and checked on
two full discharges. This plan refines it on what those runs measured.
**Phase 2, the power ladder, comes after it**
([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md), "Phase 2"); nothing here
builds any of Phase 2.

**Read first, in this order:**
1. This file — written to be executed cold, top to bottom.
2. [`../docs/battery.md`](../docs/battery.md) — the evidence and every
   withdrawn claim. Do not resurrect a withdrawn claim.
3. [`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md) — Phase 1's design, its two
   codex reviews and dispositions, and its "Queued" list (this plan absorbs it).
4. The run records: [`../history/battery-2026-09-28-drain/`](../history/battery-2026-09-28-drain/)
   (run 1), [`../history/battery-2026-10-01-drain/`](../history/battery-2026-10-01-drain/)
   (run 2), and the charges [`../history/battery-2026-10-01-charge/`](../history/battery-2026-10-01-charge/)
   and [`../history/battery-2026-10-04-charge/`](../history/battery-2026-10-04-charge/).
   Each folder's `readings.csv` holds every observation in time order,
   corrections included.

Conventions: call JD by name in docs; American spelling; never record a reading
or a time that was not observed, and mark approximations. Commits end with the
`Claude-Session:` trailer the harness gives.

---

## Step 0 — preserve the 10-04 charge log (before anything else)

The board has been charging from flat on USB, slider on BT, since ~20:02 on
2026-10-04 (run 2's pack had died). Its RAM log is workstream B's third charge,
and **any flash, slider flip, or loss of USB power erases it.** It is already
on USB, so a dump costs nothing.

1. **A preservation dump now**, whatever the charge's progress:
   `set -o pipefail; venv/bin/python3 hostagent/ak820battery.py log history/battery-2026-10-04-charge/log-$(date +%Y%m%d-%H%M).csv`
   (call `venv/bin/python3` directly until E3 is fixed). Before it, prove the
   board is RUNNING with a raw-HID read — `venv/bin/python3 hostagent/ak820battery.py`
   must answer. The USB vendor id alone does not: the bootloader is `0C45:7140`
   and the board `0C45:8009`.
2. **The final dump** at least **one full log period (10 min) after the charge
   LED goes out**, so a completed entry records the termination. The 09-28 and
   10-01 charges from flat took ~9.5 h and ~9.4 h, so expect it ~05:30 10-05.
   Record the LED-out time as observed (JD) separately from the log.
3. Also capture the health counters before anything resets them:
   `venv/bin/python3 hostagent/ak820health.py --stalls --json` and
   `ak820-agent/target/release/ak820 health --crash --json` (the Rust CLI is
   built on this Mac; `--crash` includes the vitals page with `build_token`).
4. Record all of it in that folder's `readings.csv`; commit.

---

## What is established (the inputs to this plan)

| fact | value | source |
|---|---|---|
| `5C` → pack mV | `5C = 114.22 V − 361.04`; **8 meter points 4.01-3.22 V, all within −9/+11 mV** (the meter reads to 10 mV) | docs/battery.md, "Checked against a meter" |
| run 1 (09-28) | FULL ~19:52 09-28 → RGB cut 02:13 10-01 (from the log's `led_pm`): 54.4 h wall, **51.55 h equivalent full white** after crediting USB plug-ins and a dim start (`scripts/battery_fit.py`); clamp exit **89.6%** | `history/battery-2026-09-28-drain/fit-output.txt` |
| run 2 (10-01) | unplug **11:00:00 10-02** (JD) → cut **13:33:25 10-04** (±5 s, from the video): **50.56 h** wall, one dump plug-in inside it (19:29 10-03, **duration not logged**: it came after the last completed log entry); clamp exit **90.3%** (4.90 h in) | run 2 `readings.csv`, `video-trace.csv` |
| the run-1 curve scored on run 2 | 216 points (inclusion rule in A2): **below 3.95 V, 0.1-0.6 points rms, worst +2.1; on 3.95-4.036 V, 3.2 rms, worst −8.5 (the curve reads low)** — two runs of one pack, so a consistency check, not a confidence bound | run 2 `readings.csv` |
| the lights-off reserve | run 2: cut 13:33:25 → dead **18:34:54** = **5 h 01 min**; `5C` reached 0 (≤ 3.161 V) ~17:45; a **flat spot at 3222 mV** for ~30 min, also seen in run 1 | run 2 `readings.csv` |
| lights-off draw | ~1/3 of full white: rough, an upper bound (the slope after the cut over the full-white slope extrapolated to that voltage) | `scripts/battery_fit.py` `BASE` |
| charges from flat | 09-28: CHRG low ~03:02, `5C` 100 at 06:57, termination ~12:32 (~9.5 h). 10-01: boot ~08:46, `5C` 100 first logged 12:56, VDD rising from the 13:06 entry, termination ~18:12 (~9.4 h) | the charge folders, history/battery-2026-09-25/readings.csv |
| VDD vs the board's own load | in a constant-current stretch, LED drive 1000 → 499 ‰ raised VDD **+59 mV** | 10-01 charge `readings.csv` |
| the charging display on the fitted curve | `curve(V − 150 mV)` would read **~45% at 12:36 on 10-01** (3.83 h into a charge from flat), then race at 0.4%/min to 90.5 when `5C` clamps; and the creep sits at the 97 cap ~1.1 h before termination, then steps 3 | 10-01 charge `readings.csv` |
| internal-flash writes | **816 write sessions in ~47 h** on `759e265796` (counted once per backing-store unlock), ~15 h of it on USB and ~32 h on battery; JD sees the blink "every few minutes, at least" | run 2 `readings.csv` (19:29 10-03) |
| what a write does to the LEDs | the row ISR de-selects every row for the driver's whole program state (~7 ms, `flash_gap_max_ms`); interrupts are masked only per program line (tens of µs, `hal_efl_lld.c:37-59`); page erase (1-2 ms per 1 KB page, datasheet) is unmasked | `docs/leds.md` item 3, the driver |
| flash endurance | **20,000 erase+program cycles minimum, 100,000 typical**; page 1024 bytes | `SN32F299_V1.8_EN.pdf` (the `fpb/ajazz-ak820-pro` clone at `../ajazz-ak820-pro/docs/`), FLASH table |
| main-loop stalls | **≥10 ms: ~37/h on USB, ~400/h on battery** (550 at 15 h mostly on USB → 13,336 at 47 h); ≥25 ms: 3-4 in two days; worst 36 ms (`blit`); `i2c_gap_max` 17 ms; `flash_gap_max` 7 ms | run 2 `readings.csv` |
| BT ACK timeouts | 24% of frames mostly on USB, 42-48% on battery. The ACK wait itself does not block (`ch582f_ajazz.c:505` returns), but `sdWrite` does block when the TX queue is full (`hal_serial.h`, `TIME_INFINITE`) | debug-page frames, code |
| the clock's persisted period | saved from two paths whenever the proposed period is ≥ 64 ticks from the stored value (`rtc.c` ~665, SOF; ~1001, PCF) | `rtc.c` |

### Firmware, branch, and artifacts

- **On the board: `759e265796`**, artifact
  `ak820pro-builds/out/via-daily-759e265796-20261001-201702.bin` (build token
  `0xbf01f5fc`): the fitted curve and whole percent. **This is the rollback
  artifact.**
- **`ak820pro-jdlien` HEAD is two commits further** (`188092ac71`, `241ef8fdad`:
  the `Fn`+`D` camera page and its clock row) plus a comment-only fix. The
  camera page is **built, never run on hardware**; it ships with the next flash
  unless reverted (decision D5).
- `deps.lock` still pins `44e7314e65`; moving it is a release step, outside this
  plan.
- Host checks: `scripts/battery_sim/run.sh` (27 scenarios) compiles the real
  `battery.c` and `power.c`; `scripts/battery_fit.py` reproduces run 1's fit.

---

## Scope

**In:** A, refit the curve on both runs. B, the charging display. C, the
internal-flash write rate (the blink) and the LCD's bright flash. D, the stalls
on battery. E, small items: the warning's threshold and re-arm, the venv
bootstrap, the countdown rate, the camera page's hardware check, the docs.

**Out:** Phase 2's power modes, the emergency reserve mode and standby
([`BATTERY-GAUGE-PLAN.md`](BATTERY-GAUGE-PLAN.md)); the camera page's extras
(JD: later); a pack tap or current logger (JD's DigiKey cart, not ordered); a
third multi-day drain (the two runs give a two-run consistency check; a third
is deferred, not dismissed).

---

## Order of work, and the flashes

The measurement gates decide what each flash may carry. **Flash 1 is the
diagnostic build; the fixes that depend on its measurements go in flash 2.**
Expect two flashes and allow a third: a failed gate means another iteration,
not a forced ship.

1. **Step 0.**
2. **Host-only, no board traffic:** A (the refit), B1 (charge analysis), E3
   (venv bootstrap), the simulator's replay adapter (B2's infrastructure).
3. **Flash 1 — diagnostics plus changes that need no new measurement:**
   - C1: per-field `kb_eeconfig` counters and write-boundary counters (program
     and erase, by writer context);
   - D1: per-task duration accounting;
   - A: the refitted curve (validated on the host);
   - E1/E2: the warning threshold and re-arm (decisions, not measurements);
   - E4: the countdown rate;
   - the camera page as committed (D5).

   **Not in flash 1:** the charging model (B) and the persistence fix (C2) —
   both wait for their measurements. ⚠️ So flash 1 knowingly keeps today's
   charging display, which on the fitted curve reads low through constant
   current and then races (tell JD before flashing).
4. **Measure on flash 1** (the verification protocol below): C1's writer, D2's
   per-task stall attribution, B3's partial charges.
5. **Flash 2:** C2 (and C4 if D3 says so), the D fix, B's charging model.
   Simulator, a codex implementation review, then flash; then the same
   verification protocol.
6. Docs, status, CLAUDE.md. Then Phase 2.

### The flash procedure (every flash)

1. **Dump the RAM log first** (slider on BT) and capture the health counters and
   vitals (Step 0's commands). A flash erases both.
2. **Record the settings the flash will erase** (the emulated EEPROM goes): LCD
   brightness level, clock format, BT slot, and the lighting (`ak820battery.py`
   state shows LED drive; `hostagent/ak820lighting.py show`). The test lighting
   for comparable runs is white at full drive (effect 2, sat 0, val 225).
3. **Prove the board is running** by raw HID (`ak820battery.py` answers), JD at
   the keyboard. Never put it in the bootloader first: `flash.sh` backs up the
   keymap and lighting only from a running board (on 10-01 it was already in the
   bootloader and the 09-29 backups were restored).
4. `./flash.sh <the exact artifact path build.sh printed>`. ⚠️ `flash.sh`
   refuses on a failed keymap backup but **only warns** on a failed lighting
   backup: confirm both backup files' timestamps are fresh in its output before
   the flash proceeds (`~/Documents/ak820pro-keymap.json`,
   `~/Documents/ak820pro-lighting.json`).
5. **After:** `ak820 health --crash --json` shows the new `build_token`
   (`build.sh` printed it); the keymap and lighting are back; re-apply the LCD
   brightness, clock format and BT slot recorded in 2; the clock syncs.
6. **Rollback:** flash the previous artifact the same way.

---

## A — Refit the curve on both runs

**Why:** below 3.95 V the run-1 curve already tracks run 2 within ~0.5 point.
The 3.95-4.036 V plateau is the weak spot (worst −8.5): ~20% of the runtime
passes in ~20 mV there, so a few millivolts of run-to-run difference is several
points.

### A1. Put run 2 on the same footing as run 1

Extend `scripts/battery_fit.py`. **Run 1's path must stay reproducible**: its
committed output `history/battery-2026-09-28-drain/fit-output.txt` must come out
byte-identical (diff it).

- **Run 2's sources and their differences.** `log-20261003-1929.csv`:
  10-minute entries, the PLAIN mean of every `5C` report in the period, stamped
  at the period's end, 11:00 10-02 → 19:29 10-03. `video-trace.csv`: the gauge's
  TRIMMED mean (64 reports, outer eighths dropped, ~2-2.5 min) read off the
  debug page, every ~15 min 23:30 10-03 → 13:31 10-04, wall times ±1 min. **The
  two are different estimators and were never sampled simultaneously**, so no
  offset between them can be measured from these data. Treat them as separate
  sources: smooth within each, and report how the fit moves if one source is
  shifted by ±2 mV (a sensitivity, not a correction).
- **Run 2's time axis:** start at the recorded 11:00:00. The 11:09 entry
  (10:59-11:09) is clipped at 11:00:00 — its USB minute is excluded by time,
  not inferred from its VDD (no double correction). T ends at the cut,
  13:33:25. **The 19:29 plug-in is not in the log** (the dump read entries
  completed before it): model it as an event at 19:29:40 of assumed duration
  **45 s (range 15-90 s)** with run 1's charge credit `r`, and report the
  sensitivity over that range. No dim stretch in run 2: check `led_pm` is
  ~1000 in every on-battery entry.
- **Smoothing in time, not in samples.** A common time bandwidth for both
  sources (e.g. a 50-min centered window, by timestamp), segments split only at
  real gaps (> 1.5× the source's nominal interval, so 15-min video samples with
  timestamp jitter do not split), clamp-censored entries (`5C` mean ≥ 99.5)
  excluded, and the source boundary (19:29 → 23:30) treated as a gap.
- **The 4-hour gap** 19:29 → 23:30 10-03 has no data. Any knot whose voltage
  falls inside it is interpolated, not measured — flag those knots in the
  output.

### A2. Fit, and validate by leave-one-out

- **Leave-one-out:** fit run 1 alone, score it on run 2; fit run 2 alone, score
  it on run 1. Report each direction separately, by band (3.40-3.60, 3.60-3.80,
  3.80-3.95, 3.95-4.036 V), as rms and worst, both per point and
  time-weighted, and split by source (log vs video). These are the out-of-sample
  numbers.
- **The inclusion rule** (so a cold session reproduces the 216): run 2's log
  entries ending after 11:15 10-02 with a `pack_mv` (the host leaves it empty at
  the 5C clamp) and no `external` in `flags_any`, at the entry's midpoint (end −
  5 min); plus every full-white video sample; level = (13:33:25 − t) / 50.56 h.
  State any change to this rule in the output.
- **The pooled curve** for the firmware: for each knot level, the mean of the
  two runs' voltages at that level. Its scores on the two runs are **training
  diagnostics**, labeled as such — not validation.
- **Acceptance (engineering thresholds, not confidence bounds):**
  leave-one-out in each direction, below 3.95 V: rms ≤ 1.0 point, worst ≤ 3;
  on the plateau: rms ≤ 3.5, worst ≤ 9. Run 1's curve already meets the
  below-3.95 V threshold on run 2; the plateau threshold is today's −8.5 with a
  little room — the aim is to not get worse, and to report honestly. If the
  plateau misses, take decision D4; do not tune further on two runs.
- The top knot stays **4036 mV = 90%** (`LEVEL_CLAMP_EXIT`; the clamp exit fell
  at 89.6% and 90.3%); 0% stays **3400 mV**, the RGB cut.
- Commit each fit's output and per-entry points to the run's folder, as for
  run 1.

### A3. Into the firmware (flash 1)

- Swap `curve_mv`/`curve_pm` in `battery.c`; update its comment block's
  provenance (both runs, the leave-one-out numbers, the plateau caveat).
- `scripts/battery_sim/run.sh`: scenario expectations that are curve values
  (as `unplug_mid_charge`'s and `reseat_survives_replug`'s 187 pm were) move
  with it — **update each with its arithmetic in a comment**, never by pasting
  the new output.
- docs/battery.md's curve section and table.

---

## B — The charging display

### The problem

While charging, the level is `curve(terminal mV − CHARGE_IR_MV)`, only rising,
capped at 97.0%; once `5C` reaches the clamp a 0.4%/min catch-up to 90.5% and a
0.1%/3 min creep to the cap; 100 when the charger releases. On the placeholder
curve that looked plausible by accident. **On the fitted curve it reads ~45%
3.8 h into a charge from flat**: the discharge curve's 4.00-4.02 V plateau has
no counterpart on charge, where the terminal voltage climbs steadily, so **no
constant offset maps the charging voltage onto the discharge curve.** The creep
also reaches its cap ~1.1 h before termination, then steps 3 points.

Two queued Phase 1 fixes belong here: "Charge", not the 95 guess, while
charging at the clamp with nothing known; and the re-seat after unplugging
(on 09-29 it was spent on a still-relaxing clamp reading; the ratchet then
walked 95 → 86 at 1%/15 s).

### What the model is, and is not

An **empirical display estimate for a stated operating condition** — charging
from the board's usual USB source (JD's Mac, BT position) through the ASC4056
— not a physical measurement. Its quantity is the gauge's own: **fraction of
full-white runtime**, which behind a buck-boost is closer to stored energy than
to charge. It rests on the observation that, from flat, the charger's
constant-current stretch was ~4 h on both logged charges and termination came
~9.4-9.5 h in.

Known ways the real charge departs from it, each a reason the model must stay
bounded and correctable: the ASC4056's precharge below ~2.9 V and thermal
regulation (datasheet, linked in codex's review); an input source that cannot
supply the programmed current (a weak port, a long cable); the board's own load
on the same USB input (the +59 mV VDD step shows the input is shared); CHRG low
does not prove constant current; and VDD's rise is not a clean constant-voltage
marker because the board's own load moves VDD too. **Outside its validated
conditions the display falls back to "Charge" (level unknown)** rather than
advancing a percentage on time alone — and every charge is corrected once by
the voltage at unplug (the re-seat).

### The design (parameters fitted in B1, checked in B3)

All level arithmetic in per mille, integer, at most once per second; no floats
in the 10 Hz path. States while on external power:

| state | entered when | level | display |
|---|---|---|---|
| **UNKNOWN-CHG** | charging with no trusted start level (boot on USB; a level never known; a reboot mid-charge) | unchanged (unknown) | "Charge" |
| **CC** | a real session begins (CHRG low ≥ 60 s, as now) with a known level `L0` and `5C` below the clamp | `L0 + K_CC × t_chg`, where `t_chg` counts only seconds with `charging_now()`; capped at `L_CC_CAP` | the level |
| **CV** | `5C` reaches the clamp (≥ 99.50) during a real session, from CC or with a known level | at entry latch `L_cv = level` and `g0 = 1000 − L_cv`; then the gap decays `g ← g − g/τ_s` each second (fixed point), level `= 1000 − g`, capped at **990** | the level (≤ 99) |
| **FULL** | as now: CHRG released ≥ 10 s on external power with `5C` at the clamp | 1000 | 100 |
| (hold) | CHRG high briefly, stale `5C`, `5C` leaving the clamp mid-session | unchanged; `t_chg` pauses | the level |

- `τ_s` is computed **once, at CV entry**, so the approach reaches 99.0% at the
  median clamp-to-termination time `T_CV` whatever `L_cv` is:
  `τ = T_CV / ln((1000 − L_cv) / 10)` (in seconds; for `L_cv` ≥ 980 no
  approach is needed — hold until FULL). Computed with a small lookup table or
  an integer log, not `logf`, and bounded (`τ` between 10 min and 6 h).
- **Already full** (the just-full top-up the code handles today): a level above
  the CV cap is never pulled down to it (keep `battery.c`'s existing rule at
  ~556: a 100 stays 100 through a top-up).
- **Brief plug-ins** (no real session): nothing moves, as now.
- **Session restart:** a replug starts a new session from the current level
  (known). A reboot mid-charge loses `t_chg` and the phase → UNKNOWN-CHG. The
  saved level is not a charging checkpoint and is not used to resume.
- **FULL is a heuristic** (codex P2-9): CHRG released with `5C` clamped is also
  what a charger fault looks like while the terminal voltage is still above
  4.036 V; DONE is unusable on this board. A false FULL shows 100, then the
  clamp countdown and the voltage correct it on battery within hours. Document
  it; add the simulator scenario; do not build more on it.

### The re-seat at unplug (the queued fix, defined)

After a real session ends with the board on the pack:

1. The correction is **owed** from the moment the supply becomes BATTERY.
2. It is resolved by the first estimate built **only from reports received at
   least `RELAX_S` after the unplug** (initial `RELAX_S` = 120 s; B3's relaxation
   trajectory sets it) — the estimate is emptied at the supply change, so this
   is a freshness rule on top:
   - **below the clamp:** `level = curve(estimate)`, **up or down, once** (the
     one permitted upward move on battery);
   - **at the clamp:** the relaxed pack is ≥ 4.036 V, i.e. ≥ 90%: `level =
     max(level, LEVEL_CLAMP_FLOOR)`, and the countdown takes over from there.
3. A replug before resolution keeps it owed; `RELAX_S` restarts at the next
   unplug. Missing or stale reports keep it owed.
4. Without a real session (a brief plug-in), nothing is owed, as now.

### B1. Calibrate (host analysis, before flash 2)

Inputs: the three charges from flat — 09-28
(`history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv`, one-minute
entries; ⚠️ it ends before termination, which `readings.csv` records at
~12:32), 10-01 (`history/battery-2026-10-01-charge/log-20261001-1947.csv`,
ten-minute), 10-04 (Step 0's dump). Per charge: start, `5C`-reaches-clamp time,
termination, and VDD/`led_pm` through it.

- **`T_CV`**: the median clamp-to-termination time (two values today: ~5.5 h
  09-28, ~5.3 h 10-01).
- **`L_CC_CAP`**: the level the model may reach before the clamp; set it from
  B3, not assumed. Until B3, a conservative 80%.
- **`K_CC`**: needs one quantity these logs cannot give — the share of a full
  charge delivered before the clamp. Do not assume it into firmware; **B3
  measures `K_CC` directly.** B1 only bounds it (with that share between 0.7 and
  0.9, `K_CC` ≈ 16-23%/h of runtime from the 4.0-4.25 h constant-current spans)
  so B3's result can be sanity-checked.
- The reserve below 0% (~5 h lights-off) is refilled before the level reaches 0:
  B3 starts above 0%, so `K_CC` does not depend on it.

### B2. Simulator (gate 8 grows)

- **A replay adapter first.** `sim.c`'s replay parses the old seven-field
  one-minute format and advances 60 s per row, and supplies a labeled
  synthetic tail and termination for the 09-28 log. Extend it: version-aware
  parsing (v3/v4 ten-minute entries), explicit interval durations, end-state vs
  OR-ed flags kept distinct, `5C` reports synthesized per interval to match the
  logged mean/min/max, and every synthetic tail labeled as synthetic.
- **Assertions, numeric:** across each charge-from-flat replay the level never
  rises by more than 10 pm in one second-step except at FULL; at CV entry no
  step > 10 pm; **the last value before FULL ≥ 980** (so the FULL step is ≤ 20);
  100 at FULL. A partial charge from 500 pm with 1 h of charging ends within
  `500 + K_CC ± 30` pm. A boot on USB at the clamp with nothing known reads
  unknown with state CHARGING ("Charge"). A brief plug-in moves nothing.
- **The re-seat:** an underestimate (charging level 700, relaxed voltage worth
  850 → one upward step to 850); an overestimate (850 vs 700 → down); a
  prolonged clamp (≥ 10 min at the clamp after unplug → `max(level, 905)`);
  missing reports (owed until fresh ones); repeated replugs; the 09-29 case
  (charging-time level 950 guess, first post-unplug reports still at the clamp
  — the correction must not be spent on them).
- **FULL heuristic:** a charger fault with `5C` clamped reads FULL (documented,
  asserted).
- **Mutants:** `K_CC` = 0; a CV jump; the re-seat spent before `RELAX_S`; the
  CV cap removed.

### B3. Measure `K_CC` and the relaxation on hardware (flash 1)

The experiment, once or (better) twice:

1. On battery at full white, run the pack down into a **well-resolved band**:
   start near **5-8%** (3.55-3.60 V on the current curve), where 1 point is
   ~10 mV and nowhere near the plateau or the 3.83-3.87 V shoulder.
2. Record the settled voltage estimate (the gauge's trimmed mean via
   `ak820battery.py` state, over USB — note the plug-in) after ≥ 30 min on
   battery at constant load.
3. Charge from the Mac's port for **exactly 60 min** (wall clock), BT position,
   same lighting. Expect roughly +16-23 points: the end stays below ~3.80 V.
4. Unplug. Log the relaxation: the estimate at 0, 5, 15, 30, 60 and 120 min
   (each a raw-HID read; keep the board on battery between them only if the
   reads can be taken on USB without charging — otherwise read the debug page
   by eye or camera at those times).
5. **`K_CC` = (L_after − L_before + D) / 1 h**, where `L` is the fitted curve at
   the settled estimates and `D` is the full-white runtime consumed during the
   settling time (≈ 1.95 points/h) — computed offline from the raw voltages, not
   read off the displayed level (which the ratchet and the re-seat shape).
6. Uncertainty: from the `5C` estimate's spread (±1-2 mV), the curve's
   leave-one-out error in that band, and timing. Change the firmware's `K_CC`
   only if the measurement disagrees beyond its uncertainty.

The relaxation trajectory also sets `RELAX_S`, and characterizes how optimistic
the first post-charge minutes are (BATTERY-GAUGE-PLAN.md, "The calibration
run"). Record in a new `history/battery-<date>-partial-charge/`.

---

## C — The internal-flash writes (the blink), and the LCD's bright flash

### C1. Find the writer (flash 1; no fix before this)

The hypothesis, stated as one: **the clock's persisted RTC period.** `rtc.c`
saves it from two paths — the USB SOF loop (~line 665, every 32 accepted
samples) and the PCF trim (~line 1001, windows of ≥ 300 s) — whenever the
proposed period is ≥ 64 ticks from the stored one. What `docs/clock.md` actually
measures does not by itself predict ~17 writes an hour: it reports the SOF
loop holding within ~±2 ticks once converged, ~7-12 ms/s of drift only just
after a flash, and ~0.9% of ILRC movement over a day. The 816 also mixes ~15 h
on USB (the SOF path) with ~32 h on battery (the PCF path). So: measure.

Counters, in the daily build from now on (they are how a blink is matched to a
writer):

- **At the write boundary** (`backing_store_unlock` → the board's
  `backing_store_pre_write_hook`, and `backing_store_operation_begin(erase)`):
  count **write sessions, programs and erases**, each attributed to the writer
  that started it — a "current writer" context set by the callers
  (`kb_eeconfig`'s flush, QMK's RGB/VIA eeconfig, and "other"). Wear-leveling's
  consolidation happens inside an existing session and shows as erases.
- **In `kb_eeconfig.c`**: per-field change counts (BT slot, RTC period, LCD
  brightness, clock mode, battery level) at each setter's real change, and the
  number of `eeconfig_update_kb_datablock` flushes. (A field that changes and
  changes back before the 5 s settle produces a flush but maybe no physical
  write — which is why the boundary counters are the authority.)
- **For the RTC:** the last proposed and last stored period, and which path
  proposed it; expose on the existing `HC_RTC` status pages
  (`hostagent/rtc_phase0.py` reads them) or a health page.

Expose everything on a health page; document the bytes in `hid_protocol.c` and
in `ak820health.py`. Then measure separately: **≥ 12 h on battery and ≥ 12 h on
USB (host attached)**.

### C2. The fix (flash 2, once C1 names the writer)

If it is the RTC period, **separate persisting from correcting**:

- The correction paths keep doing exactly what they do (live frequency
  tracking and phase correction unchanged); each accepted proposal just updates
  a shared **candidate** (the latest valid period, 28000-40000).
- A **persistence scheduler**, run from housekeeping once a minute, owns every
  write:
  - **first save:** if nothing is stored, save the candidate once uptime ≥
    10 min — whether or not the candidate is still changing (this is the
    starvation trap `rtc.c`'s comment at ~990 and the SOF path's unchanged-value
    case already document; it must not come back);
  - **later saves:** only if `|candidate − stored| ≥ 64` **and** ≥ 6 h since the
    last save — a write budget of ≤ 4 a day from this field;
  - one budget shared by both paths.
- Fix the comment in `rtc.c` that claims the 32/64-tick threshold "keeps
  temperature wander from causing steady rewrites".
- **Tests:** fresh EEPROM (first save happens once, ~10 min after boot); a
  reboot (the stored seed is used); host USB (SOF), charger-only USB and
  battery (PCF); a reference change (USB ↔ battery) mid-run; a candidate that
  stops changing (still saved). If the clock code has no host harness, these
  are hardware checks read through `HC_RTC`.

If C1 names another writer, design for that writer; the goal stands: **≤ 10
write sessions per 24 h** on battery with no user setting changes, excluding the
saved level's milestones (≤ 6 per charge cycle) and anything JD does.

### C3. Flash endurance

Compute it from the actual encoding, not a guess: QMK's wear-leveling here uses
`WEAR_LEVELING_BACKING_SIZE` 2048 and `WEAR_LEVELING_LOGICAL_SIZE` 1024
(`wear_leveling_efl_config.h`); 2048 − 1024 − 8 (checksum) = 1016 bytes of log,
127 eight-byte slots, consolidated (erased) when full; an `eeconfig` update logs
one or more slots depending on the bytes changed (`quantum/wear_leveling/wear_leveling.c`).
With C1's measured program/erase counts, compute erases per day before and after
C2 and the years to 20,000 (the datasheet minimum; 100,000 typical). Record it
in docs/battery.md.

### C4. The LCD's bright flash (a hypothesis to test, then decision D3)

JD saw the LCD flash brighter "for a few ms" on 10-01 ~05:16 with the LEDs off.
**Not explained by interrupt masking** — the backlight PWM runs in a 20 kHz GPT
ISR (`indicators.c` `pwm_tick_cb`), and masking lasts tens of µs. **Hypothesis:
a page erase** (1-2 ms per page, unmasked): if an interrupt cannot fetch its
handler from flash while the array erases, the PWM pin freezes in its last state
for the erase — caught ON at a low duty, a visible bright flash. Erases are rare
(wear-leveling consolidation), which fits one sighting. **Test:** C1's erase
counter against sightings (JD notes the time; the counter's increment brackets
it), or a camera on the LCD during a forced consolidation on the instrumented
build. If confirmed and D3 says fix it: an ISR-observed inhibit flag (set
together with forcing `PANEL_BKL` low in one brief critical section in
`backing_store_operation_begin(erase=true)`, honored by
`display_backlight_tick`, cleared in `_end` and on every error path), at partial
duty only (at full duty the pin is already high), respecting the brightness cap
and power state. **Never mask interrupts around the whole HAL operation** — the
driver's comment says why (UART2 carries the CH582F link). Keep the existing
watchdog scopes in those hooks.

---

## D — The stalls on battery

### What is known

`count_ge_10ms` grows ~400/h on battery and ~37/h on USB. `count_ge_25ms` is
rare (3-4 in two days, all non-flash); the worst is 36 ms. The loop marks are
**not attribution**: `health.c` times the whole interval between passes, and
the outermost mark wins (`ak820pro.h` ~87: a 48 ms pass ending in a 2 ms clear
reports as `blit`), so a pass marked `blit` can hold far more unmarked work.
Per-mark maxima today: `blit` 36, `i2c` 17, `flash` 7 ms.

Candidates, none ruled in or out: the CH582F UART (`sdWrite` blocks while the TX
queue is full; retransmissions; RX bursts; on battery the ACK-timeout rate
doubles); the battery path (`battery_task`, the 64-byte sort per `5C` report,
protection); the display (housekeeping, the blit pump, the glyph queue, the
battery row); the RTC's PCF I2C (17 ms seen; its standalone check runs about once
a minute — ~60/h, not the ~400/h excess, and C2 changes persistence, not that
read schedule); QMK's own work, including **USB-suspend handling while
unenumerated on battery** and the RGB effect computation (it runs even under the
power cap).

### D1. Per-task duration accounting (flash 1)

- Wrap each main-loop task the board owns with a start/stop timestamp
  (`timer_read32()`, ms; or a µs counter if a cheap one exists — check before
  adding one): CH582F task, `battery_task`, display housekeeping, the blit pump,
  `rtc_task`, indicators, health, and QMK's own `keyboard_task` as a remainder
  (the pass minus the wrapped tasks).
- **Per pass, attribute a ≥ 10 ms gap to the task that consumed the most of it**,
  and keep per-task counts of ≥ 10 ms and ≥ 25 ms attributions plus each task's
  maximum. Also keep the existing marks (as correlations).
- **The instrumentation's own cost is a gate**: ≤ 0.1 ms per pass, measured
  (the repository has dropped keystrokes before to a profiler costing ~2 ms per
  pass — `plans/LOOP-BUDGET-PLAN.md`).
- Expose on a health page and in `ak820health.py --stalls`.

### D2. Measure, then decide (between flash 1 and flash 2)

Under the verification protocol's soak conditions: ≥ 12 h on battery and ≥ 12 h
on USB, then the per-task attribution. Design the fix for whichever task carries
the battery-only excess. Also record the CH582F's TX-queue-full events if the
attribution points at it — those can cost keystrokes without a ≥ 25 ms gap.

**Target:** on battery, ≥ 10 ms gaps ≤ 50/h and **no ≥ 25 ms gap in a 12 h
soak**, or a documented reason the remainder cannot be removed. ⚠️ A ≥ 25 ms gap
can lose a keypress (docs/hardware.md).

---

## E — Small items

- **E1. "Battery low" threshold (D1).** On the fitted curve 3550 mV is ~4.5%,
  ~2.3 h before the cut at full white (run 2: the trace crosses 3550 mV ~11:20;
  the cut came at 13:33). Default: **the voltage at 10%** on the refitted curve
  (~3.68 V), ~5 h before the cut. RAM-settable over `HC_BATTCFG` as now.
- **E2. Re-arm rule (D2).** Today it re-arms on any external supply or the pack
  above warn + 100 mV, so each brief dump re-fires it after unplugging (seen
  10-01 01:06). **The one rule, by default: re-arm only after a real charging
  session** (CHRG low ≥ 60 s); the voltage hysteresis is dropped (a relaxing or
  briefly charged pack cannot re-arm it). Tests: a short dump plug-in (no
  re-fire), a real charge (re-fires on the next crossing), repeated
  low-voltage crossings on battery (fires once). The light-cut protection's own
  rules (lifted only by 5 s of fresh USB evidence) are unchanged.
- **E3. The venv bootstrap.** `hostagent/venv_bootstrap.py`'s exec-loop guard
  uses `os.path.samefile`, which follows `venv/bin/python3`'s symlink to the
  pyenv interpreter that `#!/usr/bin/env python3` already runs, so it calls the
  venv "the interpreter we already are" and refuses. Guard on `sys.prefix`
  against the candidate venv's root. Test by running
  `hostagent/ak820battery.py` by its shebang with the venv off PATH.
- **E4. The countdown rate.** Run 1: 10.4 points of clamp in 5.36 h equivalent;
  run 2: 9.7 in 4.90 h → ~1.94-1.98 points/h → `COUNTDOWN_S_PER_PM` ≈ 182-186
  (now 190). Set it to the two runs' mean; `countdown_ease` must still pass.
- **E5. The camera page (D5).** Check on hardware: `Fn`+`D` cycles dashboard →
  debug → camera → dashboard; the digits match the debug page's `Batt` row; the
  clock row matches the dashboard clock; and the per-task stall counts while the
  page is up, over a defined 30 min with typing, against 30 min on the
  dashboard. Revert it if it misbehaves.
- **E6. Docs.** docs/battery.md (curve, charging, the reserve, the writes,
  endurance), docs/display.md (the charging display), docs/clock.md (the
  persistence policy; and the stale "128-s windows" text, which predates the
  current 32-sample SOF loop), docs/leds.md (the corrected masking account),
  `plans/current-status.md`, CLAUDE.md's current state.

---

## The verification protocol (each flash)

Idle soaks alone do not exercise the paths this plan changes.

- **Fixed conditions for comparative soaks:** the dashboard showing (not a debug
  page) unless the test is about a page; BT position; white at full drive; LCD
  brightness as recorded; the host timekeeper in its usual state (note it); no
  VIA.
- **Record at each start and end:** uptime, `build_token`, the watchdog's reset
  count and degraded flag, and the crash record (`ak820 health --crash --json`).
  **A reset invalidates the soak** (it clears RAM evidence; three watchdog
  resets put the watchdog in degraded mode — docs/hardware.md).
- **Per-event checks with active typing** (the stall counters read before and
  after each, ~1 min of typing around it): plug in and unplug (BT position);
  "Battery low" firing (set the threshold just above the pack with
  `ak820battery.py cfg`); the RGB cut and its lift; FULL; a level going from
  unknown to known; `Fn`+`D` page transitions; a forced internal-flash write (a
  brightness step). **No ≥ 25 ms gap attributable to any of them.**
- **The write-rate gate** is measured over a stated interval (≥ 12 h on
  battery), excluding the saved level's milestones and JD's own setting
  changes, which C1's per-field counters separate.

---

## Gates

1. **A:** leave-one-out results committed with A2's report; acceptance met or D4
   decided; run 1's `fit-output.txt` reproduced byte-identical; `run.sh` passes
   with each curve-tied expectation's arithmetic in a comment.
2. **B (host):** the replay adapter and B2's assertions pass; the new mutants
   are caught.
3. **Flash 1 build:** `./build.sh daily` clean (no `-dirty`); a codex
   implementation review with every finding dispositioned; D1's cost ≤ 0.1 ms
   per pass.
4. **Flash 1 on hardware:** the verification protocol passes; C1 names the
   writer from its counters; D2's attribution recorded; E5 checked.
5. **B3:** `K_CC` and the relaxation measured with an uncertainty; `RELAX_S`
   and `L_CC_CAP` set from them.
6. **Flash 2 build:** clean, codex-reviewed, simulator passes with B's model.
7. **Flash 2 on hardware:** the protocol passes; **≤ 10 write sessions per
   24 h** on battery (C2's goal); D2's stall target met or its remainder
   explained; a charge from below 50% shows a smooth rise and a ≤ 2-point step
   at FULL.
8. Docs and status updated (E6), written to resume cold.

---

## Decisions for JD (defaults apply unless JD says otherwise)

| | question | default |
|---|---|---|
| D1 | "Battery low" threshold | the voltage at **10%** on the refitted curve (~3.68 V), ~5 h before the cut at full white |
| D2 | when the warning re-arms | **only after a real charging session**; no voltage hysteresis |
| D3 | the LCD's bright flash during a write | after C4's test and C2: if write sessions are ≤ 10/day, leave it; if not, add the inhibit-flag guard |
| D4 | the plateau, if A2 misses | **voltage only**, reporting the measured plateau error (worst −8.5 today) rather than a rounder number; the alternative — a time-based countdown across the plateau, like the clamp's — reads low at lighter loads and needs its own design |
| D5 | the camera page in flash 1 | **ship it** with E5's check; revert if it misbehaves |
| D6 | the charging display | B's model: linear in constant current, decelerating at the clamp, ≤ 99 until FULL, "Charge" when the start is unknown |

---

## Handoff to Phase 2 (the power ladder)

- **The LEDs are roughly 2/3 of full-white power** (lights-off ~1/3, rough):
  Phase 2's lever. JD's principle — take the drain out of idle, not the fun out
  of use — says where to pull it.
- **The reserve below the cut is ~5 h with the lights off**, and the board ran
  ~50 min below `5C`'s floor: the size of the emergency Power Reserve idea.
- **C and D land first**: a mode that dims the lights should not still blink
  every few minutes or stall on battery.
- Phase 2's own "measure before building" (2.6) still applies; the current
  logger (INA228) is not ordered. D1's per-task accounting will help Phase 2's
  load questions too.

---

## What this plan deliberately does not do

- Change `5C`'s line or the 0% point (3400 mV, JD's choice).
- Claim state of charge: the level stays "fraction of full-white runtime left".
- Run another multi-day drain (deferred: two runs give a consistency check).
- Build any power mode.

---

## Review dispositions

### Round 1 — codex, 2026-10-04 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md))

| # | finding (short) | disposition |
|---|---|---|
| 1 | P1: flash 1 contained C2, which a gate said must wait for C1's counters | **Accepted.** Flash 1 is the diagnostic build; C2, the D fix and B's model go in flash 2; a third flash is allowed. "Order of work". |
| 2 | P1: the 19:29 plug-in is not in the log; its duration cannot come from VDD | **Accepted, verified** (the last entry closed before the plug-in). Modeled as an assumed 45 s (15-90 s) event with a sensitivity; the start clipped at the recorded 11:00:00. A1. |
| 3 | P2: the two estimators are not shown interchangeable; the smoother splits 15-min data and bridges gaps | **Accepted.** Separate sources, time-based bandwidth, jitter-tolerant splits, the gap flagged, a ±2 mV source-offset sensitivity; no offset claimed. A1. |
| 4 | P2: two holdouts of one pack overstate "validation"; pooled scores are training; D4's ±5 is unsupported | **Accepted.** Directional leave-one-out reported separately (per point, time-weighted, by source); pooled scores labeled training; the 216-point inclusion rule stated; thresholds called engineering thresholds; D4 reports the measured −8.5; "validates" → "a two-run consistency check". A2, D4. |
| 5 | P1: B presented an unobserved regime as a physical model | **Accepted.** B is an empirical estimate for a stated condition, with its known departures listed and a fallback to "Charge"; `F_CC` and the reserve conversion no longer assumed into firmware. B. |
| 6 | P1: B's states and the CV parameters were unspecified; τ not identified; reboots and top-ups | **Accepted.** A state table, τ computed at CV entry from `L_cv` and `T_CV`, a 99.0 cap, integer arithmetic, the just-full rule preserved, reboot → "Charge". B. |
| 7 | P1: B3 did not measure `K_CC` (inside the plateau; omitted the hour of discharge; read the displayed level) | **Accepted.** B3 starts at 5-8% in a well-resolved band, computes offline from raw estimates, adds the settling discharge, logs the relaxation at 0/5/15/30/60/120 min, and has an uncertainty rule. |
| 8 | P1: the re-seat timeout had no outcome and could leave an underestimate stuck | **Accepted.** The re-seat is defined: owed until an estimate from reports ≥ `RELAX_S` after unplug; below the clamp one move up or down; at the clamp `max(level, floor)`; replug keeps it owed. Simulator cases for both directions. |
| 9 | P2: FULL is a heuristic; a high-voltage fault looks the same | **Accepted.** Documented as a heuristic with its failure mode and self-correction; a simulator scenario. |
| 10 | P2: the replay cannot read the new logs; assertions vague and contradictory | **Accepted.** A replay adapter (version-aware, durations, synthetic tails labeled) and numeric assertions; "last value before FULL ≥ 980" resolves the contradiction. B2. |
| 11 | P2: C1 misread `docs/clock.md` and overstated the RTC hypothesis | **Accepted, verified** (7-12 ms/s is post-flash; ~±2 ticks converged). The hypothesis is stated as one, with separate USB and battery measurement; the stale 128-s text goes on E6's list. |
| 12 | P1: "three stable windows" reintroduced the persistence-starvation trap | **Accepted.** Persisting is separated from correcting: a shared candidate, a once-a-minute scheduler, a guaranteed first save, a 6 h budget; tests per reference. C2. |
| 13 | P1: the backlight guard raced the ISR; masking is per line, not per write | **Accepted, verified** in `hal_efl_lld.c`; the docs that said otherwise were corrected (commit `404bed0`). C4 now tests an erase hypothesis first; if built, an ISR-observed inhibit flag; never mask the whole operation. |
| 14 | P2: subtraction cannot find other writers; endurance needs the real encoding | **Accepted.** Counters at the write boundary by writer context, programs and erases separated; endurance from 127 slots and the datasheet's 20,000 minimum (verified in the PDF). C1, C3. |
| 15 | P1: marks cannot attribute stalls; `none` may hide the culprit | **Accepted.** Per-task duration accounting with a ≥ 10 ms attribution per pass, all candidate tasks from the start, and a cost gate. D1. |
| 16 | P2: `sdWrite` blocks when the TX queue is full; the PCF check is ~60/h | **Accepted, verified.** The claim narrowed to the ACK wait; TX-queue waits on the candidate list; the PCF check's rate noted. D. |
| 17 | P1: idle soaks miss the new transition paths; resets must invalidate | **Accepted.** A verification protocol: fixed conditions, per-event checks with typing, start/end vitals, reset invalidates, the write gate over a stated interval. |
| 18 | P2: Step 0 and the flash steps need completion checks | **Accepted.** A preservation dump now plus a final dump one period after termination; a flash procedure with fresh-backup checks (`flash.sh` only warns on lighting), settings recorded and reapplied, the build token verified, a rollback artifact. |
| 19 | P2: E2 and D2 disagreed on the re-arm rule | **Accepted.** One rule: re-arm only after a real charging session; tests listed. E2, D2. |
