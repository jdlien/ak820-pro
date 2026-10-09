# Battery gauge, Phase 1b: the curve, charging, the blinks, the stalls — plan

**Status (2026-10-09, ~03:45): executing, gate 8.** Flash 2 (`28f260225f`,
token `0xdf1e8b99`) has been on the board since 12:54 10-08. **B3 is met:** three
trials give a mean `K_CC` of 133.0, the value flash 2 carries, and `RELAX_S`
1800 s is confirmed three times. Gate 8's full charge runs unattended on the
USB relay from 03:43. Gates 1-4 are met:
- gate 3 passed on flash 1b, after flash 1's 2.5% failure and a trim;
- the soaks named C1's writer (the RTC period's PCF path) and D2's stall
  (`battery_5c_report`'s sort; flash 1c's profile).

Flash 1c is on the board. Flash 2 (branch `phase1b-flash2`) carries B's model
with a placeholder tail, the D fix, C2 and the new camera page. It is built
and host-verified, and waits for B3's `K_CC` and `RELAX_S`. B3 trial 1's
charge ran 20:21:37-21:01:35 10-07; its relaxation was filmed overnight.
Resume from `current-status.md`, "2026-10-07". See "As
built", just before the review dispositions. Revision 7 came after codex's sixth review
([every round verbatim](review-codex-battery-refine-plan-2026-10-04.md);
dispositions at the end). Phase 1 (the gauge) is built, flashed, and checked on
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

1. **A preservation dump** (✅ taken 2026-10-04 21:44, `log-20261004-2144.csv`,
   commit `602f8fd`; take another if in doubt), whatever the charge's progress:
   `set -o pipefail; venv/bin/python3 hostagent/ak820battery.py log history/battery-2026-10-04-charge/log-$(date +%Y%m%d-%H%M).csv`
   (call `venv/bin/python3` directly until E3 is fixed). Before it, prove the
   board is RUNNING with a raw-HID read — `venv/bin/python3 hostagent/ak820battery.py`
   must answer. The USB vendor id alone does not: the bootloader is `0C45:7140`
   and the board `0C45:8009`.
2. **The final dump** at least **one full log period (10 min) after charging
   stops**, so a completed entry records the termination. Charging stops when
   CHRG is released: the battery row's bolt goes, and `ak820battery.py` stops
   showing `charging`. The charge LED is firmware-driven and off by default
   (`CHARGING_LED_BRIGHTNESS` 0). The 09-28 and 10-01 charges from flat took
   ~9.5 h and ~9.4 h, so expect it ~05:30 10-05. Record the time JD saw the
   bolt go separately from the log.

   ⚠️ **2026-10-04 22:37: the board was found in the bootloader** (`0C45:7140`).
   JD entered it before bed, for an overnight flash that is not coming, so the
   RAM log after 21:44 is lost (`readings.csv`). It was suggested that JD cold
   power-cycle it back to running (slider to cable, unplug ~10 s, slider to BT,
   replug). Then a fresh log covers the sensor ceiling and the termination, and
   this dump still applies. Check which happened before relying on it:
   - **If the board is running:** take the dump. Its log starts mid-charge at the
     reboot. Note that in `readings.csv`; B1 uses its timings from the reboot on.
   - **If it stayed in the bootloader all night:** there is no log of this
     charge's end. Nothing shows charging in the bootloader, because the LED and
     the bolt are both firmware-driven. The 10-04 charge then gives B1 only its
     start and its first 1.7 h. `T_TAIL` is the median of two, stated as such.
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
| charges from flat | 09-28: CHRG low ~03:02, `5C` at the clamp 06:57, VDD rising ~07:00, termination ~12:32 (~9.5 h). 10-01: boot ~08:46, `5C` at the clamp from the 12:56 entry, VDD rising from the 13:06 entry, termination ~18:12 (~9.4 h). These are timings against the sensor clamp and VDD, **not** measured CC/CV phases (B) | the charge folders, history/battery-2026-09-25/readings.csv |
| VDD vs the board's own load | during the charge's flat-VDD stretch before the sensor clamp, LED drive 1000 → 499 ‰ raised VDD **+59 mV** (4200 → 4259) with nothing else changing | 10-01 charge `readings.csv` |
| the charging display on the fitted curve | `curve(V − 150 mV)` would read **~45% at 12:36 on 10-01** (3.83 h into a charge from flat), then race at 0.4%/min to 90.5 when `5C` clamps; and the creep sits at the 97 cap ~1.1 h before termination, then steps 3 | 10-01 charge `readings.csv` |
| internal-flash writes | **816 write sessions in ~47 h** on `759e265796` (counted once per backing-store unlock), ~15 h of it on USB and ~32 h on battery; JD sees the blink "every few minutes, at least" | run 2 `readings.csv` (19:29 10-03) |
| what a write does to the LEDs | the row ISR de-selects every row while the driver is in its program state (`docs/leds.md` item 3); interrupts are masked only per program line (`hal_efl_lld.c:37-59`; the datasheet gives 10 µs typical, 20 µs maximum per 64-bit program); page erase (1-2 ms per 1 KB page) is unmasked. **7 ms (`flash_gap_max_ms`) is the longest flash-marked main-loop interval**, which includes the DMA drain before the write — not a measured blink or program duration | the driver, `health.c`, the datasheet |
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
2. **Host-only, no board traffic:**
   - A, the refit;
   - B1, the charge analysis;
   - E3, the venv bootstrap;
   - E7, `flash.sh`;
   - B2's replay adapter, with today's charging logic replayed as a baseline;
   - D1's transport counters with their host harness.
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
4. **Measure on flash 1**: first D1's A/B qualification (gate 3), then the
   verification protocol's soaks — C1's writer, D2's stall attribution, the
   transport counters — and B3's partial charges.
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
   the keyboard. **Do not press `Fn`+`Esc` yet.**
4. `./flash.sh <the exact artifact path build.sh printed>`. It dumps the keymap
   and the lighting from the running board, then prints "press Fn+Esc to enter
   the bootloader" and waits. **While it waits**, check both backups are fresh:
   `ls -l ~/Documents/ak820pro-keymap.json ~/Documents/ak820pro-lighting.json`
   (modified within the last minute). Only then JD presses `Fn`+`Esc`. If either
   is stale, Ctrl-C. (On 10-01 `Fn`+`Esc` was pressed before the script ran, so it
   found the bootloader and restored the 09-29 backups. Until E7 lands, a failed
   lighting backup only warns.)
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
  timestamp jitter do not split), and the source boundary (19:29 → 23:30)
  treated as a gap.
- **Censoring:** in the new fit, exclude every interval with **any** clamped
  report (`c5_max` = 100, or `c5_min` = 0) — the host withholds `pack_mv` for
  exactly those (`ak820battery.py` ~152), and a mean like 15:59's 99.36 with a
  max of 100 is not a measurement. The legacy run-1 path keeps its own rule, for
  the byte-identical reproduction.
- **The 4-hour gap** 19:29 → 23:30 10-03 has no data. Flag every knot whose
  voltage falls inside it, and report how those knots and the scores move under
  the two monotone extremes (the gap's endpoint voltages held to each side) as
  well as linear interpolation in time.

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
3.8 h into a charge from flat** (10-01), and the 10-04 charge confirms the
direction (18.4% at 1.7 h, 21:44): the discharge curve's 4.00-4.02 V plateau has
no counterpart on charge, where the terminal voltage climbs steadily, so **no
constant offset maps the charging voltage onto the discharge curve.** The creep
also reaches its cap ~1.1 h before termination, then steps 3 points.

Two queued Phase 1 fixes belong here: "Charge", not the 95 guess, while charging
at the clamp with nothing known; and the re-seat after unplugging (on 09-29 it was
spent on a still-relaxing clamp reading; the ratchet then walked 95 → 86).

### What the model is, and is not

An **empirical display estimate for a stated operating condition** — charging from
the board's usual USB source (JD's Mac, BT position) through the ASC4056 — not a
physical measurement. Its quantity is the gauge's own, the fraction of full-white
runtime, which behind a buck-boost is closer to stored energy than to charge.

What the logs show is **timing relative to the `5C` sensor clamp and to VDD**, not
the charger's constant-current/constant-voltage phases: the ASC4056 regulates to
~4.2 V, above the sensor's 4.036 V ceiling, so `5C` reaching the clamp is not the
CC→CV transition, and VDD's rise through a charge is load-confounded (+59 mV for a
50% LED change). From flat, `5C` reached the clamp ~4.0-4.2 h in and termination
came ~9.4-9.5 h in, on both logged charges. The physical CC/CV reading of those
spans is an interpretation.

Known departures, each a reason the model is bounded and correctable: the
ASC4056's precharge below ~2.9 V and thermal regulation (its datasheet, in the
`ajazz-ak820-pro` clone's `docs/ASC4056.pdf`); a source that cannot supply the
programmed current; the board's own load on the same USB input; and CHRG low does
not prove constant current.

**What bounds the model, and what does not.** Below the sensor clamp, the display
never rises above the voltage ceiling `U`. LOST gives up ("Charge") when the model
runs more than 50 pm ahead of `U` for 30 min. That is a **consistency check** that
catches large, sustained contradictions. It does not catch small ones, and it does
not qualify a supply. **At the clamp there is no voltage evidence:** the display
advances on elapsed charging time alone, and a partial charge can sit at the clamp
for most of its session. That is **accepted for the stated condition** (JD's Mac
port, BT position, the board's own load), with three bounds:

- the 990 cap;
- OVERRUN: termination more than 60 min after the model's own termination time
  gives "Charge";
- the re-seat at unplug. A relaxed pack below the clamp then takes its level from
  the voltage. One still at the clamp is ≥ 90%, so the error is confined to the
  clamp band (90-99%).

A different charger, a hot pack, or a hub that cannot supply the current is outside
what the model claims. B2's slow-charge case tests LOST; it does not qualify those
supplies.

### The design (parameters from B1 and B3)

**Phase by level, not by the sensor clamp.** A partial charge from ~50% puts the
terminal voltage over 4.036 V almost at once (the charge current's lift), so the
clamp marks nothing about the charge's phase there.

Quantities, all per mille, integer, updated at most once a second (no floats in
the 10 Hz path):

- `K_CC` — the rise per hour of charging before the knee (B3 measures it).
- `L_KNEE` — the level at which the rise starts to slow (B1 derives it; an
  extrapolation, stated as one).
- `T_TAIL` — from the knee to termination, from flat (B1).
- **The tail's shape, `τ` and `A`**, computed offline and compiled in. From the
  knee, `M` approaches an asymptote `A` exponentially:
  `M = A − (A − L_KNEE)·e^(−t/τ)`. Two conditions fix the pair:
  - **it starts at `K_CC`** (`A − L_KNEE = K_CC·τ`), so the tail is never faster
    than the linear phase and its rate only falls;
  - **it reaches 990 exactly `T_TAIL` after the knee**
    (`K_CC·τ·(1 − e^(−T_TAIL/τ)) = 990 − L_KNEE`, solved for τ by bisection).

  With positive `K_CC` and `T_TAIL`, a finite positive τ exists if and only if
  `0 < 990 − L_KNEE < K_CC·T_TAIL`. That holds at every point of B1's ranges,
  checked 2026-10-04 on a 900-point grid: `K_CC` 160-230, `t_knee` 3.9-4.25 h,
  `R` 0-60, `T_TAIL` 5.0-5.6 h. At round 3's parameter set (`K_CC` 160, `t_knee`
  4.1 h, `R` 30, `T_TAIL` 5.35 h) the result is `L_KNEE` 626, τ 2.61 h and `A`
  1044, ending at 20.6 pm/h; codex reproduced this. Round 2's formula started that
  same tail at 253 pm/h.

  **The tail is compiled in as a table, not iterated.** At one corner of the grid
  (`K_CC` 230, `t_knee` 4.25 h, `R` 0, `T_TAIL` 5 h) the solution is nearly
  degenerate: `L_KNEE` 977.5, τ ≈ 0.054 h, and `A − 990` ≈ 10⁻³⁹. A per-second
  fixed-point recurrence there rounds `A` to 990 and either never reaches it or
  reaches it ~10 min in. Either is within 1 pm of the curve, but wrong about
  *when* it arrives (codex, round 4). So:
  - B1's script writes **`TAIL_X16[i]` = M at `i × 60` s after the knee, in
    1/16 pm**, from `i = 0` (`L_KNEE`) to `i = N`. Each node is rounded to the
    nearest 1/16 pm, and 990 × 16 fits a `uint16_t`. τ and `A` are solved for
    `T_TAIL` rounded to the minute, so `N × 60 = T_TAIL` and the last node is
    **exactly 990 × 16**. It goes into a generated header with the parameters in a
    comment, never hand-edited. That is ≤ 337 `uint16_t`, under 700 bytes.
  - **The tail clock** `t_tail` counts charging seconds in the tail and keeps
    counting past `T_TAIL`, for OVERRUN. **The lookup index saturates on its
    own:** `i = min(t_tail / 60, N)`. Between nodes, `M` is interpolated linearly
    with integer floor division (1/16 pm). It is shown in whole pm, rounded to
    nearest.
  - **A start above the knee** enters the clock at the first second whose
    interpolated `M` is ≥ `L0`: a node search, then an integer ceiling within
    the segment. There is no logarithm, and the tail is memoryless, so this is
    the same curve.
  - **Arrival is a time:** `t_tail ≥ T_TAIL`, never "`M` = 990". OVERRUN keys on
    the clock.
  - **Measured, not assumed:** `scripts/battery_sim/tail_grid.py` checks all of
    this over B1's grid, **at every integer second of every tail**, not a sample
    (codex, round 6). Its 2026-10-04 run, the degenerate corner included:
    - all 900 points feasible, at most 337 nodes;
    - the interpolated 1/16 pm table is within **0.180 pm** of the curve, and
      **0.601 pm** shown in whole pm. The rounding is **half up, `(x16 + 8) / 16`,
      the same rule in the C and the checker**;
    - the firmware's 1 h rise never exceeds `K_CC` from any start second, on the
      integer path;
    - past `T_TAIL` the saturated index holds exactly 990;
    - entry above the knee is the **first crossing in X16 units**: `M_x16` at the
      entry second is ≥ `L0 × 16`, and the second before is < `L0 × 16`. The
      *displayed* predecessor can already round to `L0`, so this is not
      asserted on rounded output.

    The rate bound, never faster than `K_CC`, is a property of the analytical
    curve (it starts at `K_CC` and decelerates). The firmware tests use these
    measured quantization tolerances.

  ⚠️ **If the calibrated parameters are infeasible, or B3 contradicts B1 beyond
  their uncertainty:** revise the model (the knee, not the measurements), or ship
  flash 2 with "Charge" for every session plus the re-seat, and let the model
  wait. **Never adjust a measured value to pass B2.**
- **The voltage ceiling** `U = curve(estimate)`, from a **fresh estimate below the
  clamp** only, with no I×R subtraction. The charge current lifts the terminal
  voltage above the pack's own, and the curve maps the lower full-white discharge
  voltage, so `U` overstates the level — a ceiling, never a target. There is no
  ceiling at the clamp. With no fresh estimate there is no ceiling either, and that
  case is handled separately (rule 2 below).
- **Constants:**

  | constant | value |
  |---|---|
  | `LOST_PM` | 50 |
  | `LOST_S` | 30 min |
  | `STALE_LOST_S` | 10 min |
  | `RISE_PM_PER_S` | 1 |
  | `T_OVERRUN` | 60 min |
  | `PAUSE_S` | 10 min, and never less than `RELAX_S` |
  | `FLAT_X100` | 1000 (10.00 counts) |

  "Fresh" is `battery.c`'s existing rule: an estimate needs 5 reports since the
  ring last emptied, and goes stale 20 s after the last report. The ring empties at
  every supply or charger change.

**The model `M`**, from a start level `L0` and charging time `t` (seconds with
`charging_now()` only; it pauses otherwise):

- below `L_KNEE`: `M = L0 + K_CC × t`, until it reaches `L_KNEE`;
- from `L_KNEE`, or from `L0` if it starts above: the tail table, on the tail
  clock, as above. A start above the knee joins the curve at its own level,
  already slower than `K_CC`.
- the linear phase is integer too: `M = L0 + K_CC·t / 3600`, with `K_CC` in pm/h
  and `t` in seconds.
- `M` is capped at 990.

**The displayed level, each second.** Precedence, highest first:

1. **It never falls** while charging (until FULL, or "Charge").
2. **It never rises past the evidence:**
   - with a fresh estimate below the clamp, a rise may reach at most `U`;
   - with a fresh estimate at the clamp, there is no voltage bound: it advances on
     elapsed charging time alone (see "What bounds the model");
   - with no fresh estimate (stale, or the ring refilling after a change), it does
     not rise.
3. **It rises at most `RISE_PM_PER_S`.** A ceiling that lifts (clamp entry, the
   estimate climbing, reports returning) then shows as a quick count-up, not a
   jump. The model's own rates are ≤ 0.07 pm/s, so the limiter binds only on
   catch-up.
4. **It never exceeds 990** before FULL.

`cand = min(M, 990, bound)`, where `bound` is `U`, none, or `level`, as rule 2
says; then `level = max(level, min(cand, level + RISE_PM_PER_S))`.

So when a fresh `U` falls below the displayed level, the display **holds**: it
neither falls nor rises. **In a numeric session that started at or below 990**,
the display never exceeds `M`, because it starts at `M` (= `L0`), only rises
toward `min(M, …)`, and `M` only rises. The one exception is the already-full
rule below: a 1000 kept through a top-up sits above `M`'s cap, and LOST never
applies to it. A held display more than `LOST_PM` above `U` therefore implies
`M − U > LOST_PM`, which LOST catches **after its dwell**. Until then, a display up
to the whole of `M − U` above a fresh `U` is permitted by design, for up to
`LOST_S` of accumulated contradiction. **`LOST_PM` is the declared
noise tolerance.** A held display may sit up to 50 pm above a fresh `U` for as long
as that lasts. `U` itself overstates under charge, and near the top of the curve
2 mV of estimate is ~50 pm (4006 → 4008 mV is 700 → 750).

| state | entered when | level shown |
|---|---|---|
| **UNKNOWN-CHG** | charging with no trusted `L0`: a boot on USB whose first estimate is above `FLAT_X100`; a reboot mid-charge (the phase and `t` are lost; the saved level is not a charging checkpoint) | "Charge" |
| **FROM-FLAT** | a boot on USB whose **first estimate** (from its first 5 reports, latched) is ≤ `FLAT_X100`, then a real session. Note 1. | `L0 = 0`, then the model |
| **MODEL** | a real session (CHRG low ≥ 60 s, as now) from a known level (on battery before, or a continuing session) | the model |
| **LOST** | in MODEL or FROM-FLAT, any of conditions (a)-(c). Note 2. | "Charge" until FULL, unplug, or a `PAUSE_S` pause, and not regained in that session. **Re-seats as UNKNOWN** at unplug. |
| **FULL** | as now: CHRG released ≥ 10 s on external power with `5C` at the clamp | 100 |

**Note 1, FROM-FLAT's threshold.** A first estimate of ≤ 3248 mV is measured
**under charge**, so the pack's own voltage is lower still. That is ≥ 150 mV below
the 3400 mV cut, which itself is a loaded voltage. Any threshold up to 3400 mV
would be sound in principle; the margin covers the voltmeter's ±11 mV and its line
being unvalidated under charge.

**What the records show about each charge's start.** No log records the first five
reports, so every replay's opening is a **labeled reconstruction**, consistent with
what was observed:

| charge | observed at plug-in | logged first entry | reconstruction (labeled) |
|---|---|---|---|
| 09-28 | JD read 2 → 3 → 4 on the debug page within a minute (`readings.csv`, 03:02) | one-minute format: 4, age 5 s | the first minute's reports at 4, as logged; no zero invented |
| 10-01 | JD read `0@1 <3161` at plug-in: raw report 0, estimate below the bottom clamp (`readings.csv`, ~08:45) | ten-minute: mean 13.45, min 0, max 27 | the first interval's reports in ascending order from 0, which matches the observation and the rising charge |
| 10-04 | JD read `0@0` at boot (`readings.csv`, ~20:03) | ten-minute: mean 14.22, min 0, max 28 | the same |

The interval statistics alone do not fix the order: other orderings reproduce
them with the opposite classification. So the replays classify the
reconstruction, not the record, and say so in their output.

**Note 2, LOST's three conditions:**

- **(a) Running ahead.** A fresh below-clamp estimate with `M − U > LOST_PM`,
  accumulated over `LOST_S`. A fresh below-clamp second with `M − U ≤ LOST_PM`
  resets the timer. At the clamp, or with no fresh estimate, it **holds**: it
  neither runs nor resets.
- **(b) No evidence.** No fresh estimate for `STALE_LOST_S` continuously.
- **(c) OVERRUN.** `T_OVERRUN` of charging after the tail clock reaches `T_TAIL`,
  without FULL: termination later than modeled. This is the one check available
  above the clamp.

**Two flags, kept apart.**

- **`session`**, today's flag: CHRG has been low for ≥ 60 s since the board was
  last on the pack. It clears only on the pack, and keeps its one meaning, a
  re-seat owed at unplug.
- **`modeled`**, new: the model is running. It opens when CHRG has been low for
  60 s continuously (`chrg_run ≥ SESSION_TICKS`), at a boot or after a handover.
  It closes at FULL, at unplug, or at a pause handover. MODEL, FROM-FLAT,
  UNKNOWN-CHG and LOST exist only while it is open.

**A pause** is `charging_now()` going false while `modeled` is open, on external
power. That is CHRG released past its existing 1 s hold (`battery.c` ~182). The
pause is timed from that moment and ends when `charging_now()` returns.

- **While paused:** `M` and every timer stop, and the display holds. Today's "on
  USB, charger idle: follow the estimate" path (`level_report`, ~570) does **not**
  run while `modeled` is open; it would move the level on a voltage still relaxing
  from the charge.
- **A resumption before `PAUSE_S`** continues the model where it stopped, with no
  requalification.
- **At `PAUSE_S`, the handover:** the charger is idle or faulted, and with no
  charge current there is nothing to model, so `modeled` closes.
  - The idle path then adopts a level only from an estimate built **entirely from
    reports received ≥ `RELAX_S` after the stop**, by the re-seat's mechanism.
    Clearing the ring at the charger change guarantees post-stop reports, not
    relaxed ones.
  - Until such an estimate exists, the display holds; an unknown level shows
    today's unknown display, not "Charge".
  - A charge that resumes after the handover must requalify (60 s). It is then
    MODEL from the adopted level, or UNKNOWN-CHG if none was adopted.
- **Termination is always at the clamp** (the charger stops at ~4.2 V CV, and the
  09-28 pack read 4.18 V at rest after it), so a pause below the clamp is never
  FULL.

- **Already full:** a level above 990 is never pulled down (keep `battery.c`'s
  existing rule at ~556: a 100 stays 100 through a top-up).
- **Brief plug-ins** (no real session): nothing moves, as now. A boot on USB with
  CHRG low shows "Charge" until its session qualifies at 60 s, and then FROM-FLAT's
  0 or UNKNOWN-CHG's "Charge". A boot with the charger idle takes today's idle path.
- **`LEVEL_UNKNOWN` is `0xFFFF`:** every comparison, subtraction and `max` in this
  code checks validity first. A bare `level >= 980` would pass for UNKNOWN.
- **The log becomes v5** for gate 8. Two bytes are added to each entry, making
  18:
  - **`m`**, `M` at the entry's end, in 0.5 % like `level`;
  - **`chg`**, the charging byte:

    | bits | meaning |
    |---|---|
    | 0-2 | the state at the end: none/idle, UNKNOWN-CHG, FROM-FLAT, MODEL, LOST, FULL |
    | 3 | LOST entered during the period, by (a) or (b) |
    | 4 | OVERRUN entered during the period |
    | 5 | a handover during the period |
    | 6 | the firmware's self-check: a rise ended above the then-fresh `U` (should never set; it catches integration bugs the simulator cannot see) |
    | 7 | the period's report sum or count saturated, so `c5_mean` and `c5_n` cover only the reports before it |

    These are latched over the period, like `flags_any`, so a LOST followed by
    FULL inside one entry still shows. All eight `flags` bits are taken
    (`battery.c` 80-88), so the bits cannot go there.

    **v5 also keeps `c5_min`/`c5_max` for every accepted report.** Today
    (`battery.c` ~332) they update only while the 16-bit sum accepts the
    report, so after ~661 reports of 99 a later 100 reaches the estimator but
    not the log (codex, round 6). Only the sum and count saturate, and they set
    bit 7. The recorded runs peak at 344 reports a period, far from that. B2
    has a fixture: 661 reports of 99, then 100s, must log `c5_max` 100 with
    bit 7 set.

  **The wire must be repacked, because the reply is full.** `HC_BATTLOG` answers
  in place at `&data[3]` (`hid_protocol.c` ~598). Today that is 3 + 13 header +
  16 entry = **32 bytes = `RAW_EPSIZE`** (`tmk_core/protocol/usb_descriptor.h`
  289), so a bigger entry would write past the buffer. v5 drops the period from
  each reply, making the header 11 bytes: 3 + 11 + 18 = 32.
  - The host reads the period once per dump from `HC_BATTCFG`, which already
    reports it (`battery_cfg`, `out[6..7]`). That is the firmware's value, still
    never assumed.
  - Firmware and host change together.
  - A `_Static_assert` that 3 + header + entry ≤ `RAW_EPSIZE`.
  - Host decode tests on v3, v4 and v5 replies, each with its version byte.
  - The B2 harness reads `battery_log_read`'s output into a 29-byte buffer
    guarded on both sides.

  RAM: 720 × 2 = 1440 bytes more. The rollback ELF has ~6 KB of linker heap
  space (codex, round 5); re-check the final build's map. `ak820battery.py` and
  B2's replay adapter read v3, v4 and v5.
- **FULL is a heuristic:** CHRG released with `5C` clamped is also what a charger
  fault looks like while the terminal voltage is still above 4.036 V, and DONE is
  unusable on this board. A false FULL shows 100; on battery the clamp countdown
  and the voltage then correct it within hours. Documented, simulated, not built on.

### The re-seat at unplug (the queued fix, defined)

After a real session ends with the board on the pack:

1. The correction is **owed** from the moment the supply becomes BATTERY.
2. It is resolved by the first estimate built **only from reports received at
   least `RELAX_S` after the unplug** (initial 120 s; B3's relaxation trajectory
   sets it):
   - **below the clamp:** `level = curve(estimate)`, **up or down, once** (the one
     permitted upward move on battery);
   - **at the clamp:** the relaxed pack is ≥ 4.036 V, so ≥ 90%: a known level
     becomes `max(level, LEVEL_CLAMP_FLOOR)`; an UNKNOWN one becomes
     `LEVEL_CLAMP_GUESS` (950, as a boot at the clamp does today). The countdown
     takes over from there. **A LOST session counts as UNKNOWN here**: its last
     displayed number came from a model the voltage had already contradicted.
3. A replug before resolution keeps it owed; `RELAX_S` restarts at the next unplug.
   Missing or stale reports keep it owed.
4. Without a real session (a brief plug-in), nothing is owed, as now.

### B1. Calibrate from the charges (host analysis)

Inputs: the three charges from flat — 09-28
(`history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv`, one-minute
entries; ⚠️ it ends before termination, which `readings.csv` records at ~12:32),
10-01 (`history/battery-2026-10-01-charge/log-20261001-1947.csv`, ten-minute), 10-04
(Step 0's dumps). Per charge: start, `5C`-reaches-clamp, the VDD rise, termination,
with `led_pm` alongside VDD.

- **`T_TAIL`**: from the knee to termination. With the knee taken at the VDD
  rise, ~5.5 h (09-28) and ~5.2 h (10-01); the median of three once 10-04 is in.
- **`L_KNEE`**: `K_CC × t_knee − R`, where `t_knee` is the time from plug-in to
  the VDD rise (~3.9-4.25 h) and `R` the refill of the reserve below 0% (small,
  unmeasured: take 30 pm, range 0-60, and report the sensitivity). **An
  extrapolation**: what it can cost is limited by the ceiling `U` below the clamp
  and by the re-seat at unplug.
- **`K_CC`**: B1 only bounds it (if 70-90% of a full charge goes in before the
  knee, ~16-23%/h of runtime); **B3 measures it.**
- **The start classification, per charge**, from Note 1's labeled
  reconstruction: the first estimate it gives, and the FROM-FLAT verdict. No zero
  prelude is synthesized for 09-28.
- **Once B3 is in:** solve τ and `A`, report feasibility (`0 < 990 − L_KNEE <
  K_CC·T_TAIL`) over the calibrated values and their uncertainty, and write
  `TAIL_PM`. For each recorded charge, report the model's termination time (the
  tail clock reaching `T_TAIL`) against the observed termination. It must leave
  OVERRUN at least 30 min of margin, so the model's time can be no more than
  30 min before termination. Otherwise revise the model, not `T_OVERRUN`.

### B2. Simulator

**Before flash 1 (infrastructure and a baseline):** a replay adapter — `sim.c`'s
replay parses the old seven-field one-minute format and advances 60 s per row,
with a labeled synthetic tail for the 09-28 log. Extend it: version-aware parsing
(v3/v4 ten-minute entries), explicit interval durations, end-state vs OR-ed flags
kept apart, `5C` reports synthesized per interval to match the logged mean/min/max,
every synthetic segment labeled. Then **replay all three charges against TODAY's
charging logic** and assert what it does now (the baseline the new model is
compared with).

**After B3, before flash 2 (the new model):**
Cases marked *(synthetic)* are constructed inputs and are labeled so in the
test's output. The rest replay recorded data.

**Replays and starts:**

- **FROM-FLAT replays.** Each charge's opening is Note 1's labeled
  reconstruction, classified by the rule; 09-28's is its logged 4, with no zero
  invented. Assert:
  - level 0 at the start;
  - no step > `RISE_PM_PER_S` in one second, except at FULL;
  - no rise ends above a fresh `U`;
  - ≤ 990 until FULL, and **the last value before FULL ≥ 970** (so the FULL step
    is ≤ 30 pm);
  - 1000 at FULL;
  - LOST and OVERRUN never fire.
- **FROM-FLAT boundary** *(synthetic)*, through real reports: the first estimate
  averages 5 whole counts untrimmed, so its resolution is 0.20 counts. Reports
  10, 10, 10, 10, 10 (10.00) give FROM-FLAT; 10, 10, 10, 10, 11 (10.20) give
  UNKNOWN-CHG. The 10.00/10.01 edge is tested directly on the classifying
  helper.
- **UNKNOWN start** (a boot on USB at the clamp, nothing known): "Charge"
  throughout; 1000 at FULL; validity asserted before any numeric comparison.

**The model's shape:**

- **Partial charge below the knee:** `L0 = L_KNEE − K_CC − 50`; after 60 min,
  `L0 + K_CC ± 10` pm (the synthesized `5C` keeps `U` above `M`, so the ceiling
  does not bind).
- **The tail's shape over B1's whole grid**, not only the calibrated set
  *(synthetic)*:
  - the generator: every feasible point's analytical curve starts at `K_CC` and
    decelerates; `tail_grid.py`'s figures reproduce;
  - the firmware path (the generated table through `battery.c`'s lookup): from
    any `L0`, the 1 h rise ≤ `K_CC` + 1 pm;
  - the table ends at exactly 990 × 16, at `T_TAIL` rounded to the minute;
  - the displayed whole-pm `M`, rounded half up, is within 0.7 pm of the curve
    (measured worst 0.601);
  - entry above the knee, in X16 units: `M_x16` at the entry second is
    ≥ `L0 × 16`, and the second before is < `L0 × 16`;
  - **past `T_TAIL`** the clock keeps counting while `M` stays at exactly 990.
    The index saturates at `N`, with no read past the table;
  - **OVERRUN timing:** from the knee, and from starts above it, OVERRUN fires
    after `(T_TAIL − t_tail0) + T_OVERRUN` of charging, ± 1 s. This is checked at
    every grid point, the degenerate corner included, where `M` shows 990 hours
    before the clock arrives;
  - infeasible points are reported, never fitted.
- **Early clamp entry:** `L0` 600 with `5C` clamped from the first minute, at the
  calibrated set and at round 3's set (where round 2's formula gave 787.85). The
  1 h rise ≤ `K_CC + 10`.
- **Near-full top-up:** `L0` 950, FULL after 15 min → the FULL step ≤ 50 pm.

**The cap and the clamp:**

- **Delayed termination at the clamp** *(synthetic)*: `L0` 600, `5C` clamped
  throughout, CHRG held 2 h past the model's termination time, at the calibrated
  set and at round 3's set. Assert:
  - ≤ 990 throughout (never 991-999);
  - "Charge" `T_OVERRUN` after the tail clock reaches `T_TAIL`;
  - 1000 at FULL;
  - unplugged before FULL, it re-seats as UNKNOWN (clamped → 950).
- **Just full:** 1000 stays 1000 through a top-up (the already-full exception to
  ≤ 990).

**The ceiling** *(synthetic)*:

- `U` falls to 30 pm below the display while `M` equals the display, so
  `M − U` = 30: it holds, and LOST does not fire.
- `U` is 60 pm below `M` for 29 min, then recovers: no LOST.
- `U` is 60 pm below `M` for 30 min: LOST.
- 20 min of `M − U` = 60, then 5 min clamped, then 10 min of `M − U` = 60: LOST.
  The timer held through the clamp.
- Clamp entry while the ceiling binds: a count-up at ≤ 1 pm/s to `M`.
- Clamp exit with `U` below the display: it holds, and the timer runs per
  condition (a).
- Reports lost for 9 min: no rise, then a catch-up at ≤ 1 pm/s.
- Reports lost for 10 min: LOST.

**Pauses** *(synthetic)*, parameterized on the final `PAUSE_S` and `RELAX_S`:

- Today's `chrg_gap` (2 s) still passes.
- A pause of `PAUSE_S` − 1 min below the clamp, then a resumption: the display
  holds; `M` and the timers continue with no jump and no requalification.
- A resumption 1 s before `PAUSE_S` continues the model. One 1 s after
  `PAUSE_S` requalifies at 60 s, from the adopted level.
- At the handover, reports still falling (relaxing) before `RELAX_S` are not
  adopted; the level comes from reports after it.
- Reports missing at `PAUSE_S`: the display holds until a qualifying estimate,
  then adopts it.
- The handover from LOST and from UNKNOWN-CHG: a number once adopted, never
  "Charge".
- A handover and then an unplug: `session` is still set, so the re-seat is
  owed.

**LOST, the re-seat, FULL:**

- **A slow charge:** `5C` rising at half the modeled rate → LOST ("Charge") after
  30 min of `M − U > 50`. This is a test of LOST, not a qualification of other
  supplies.
- **The re-seat:**
  - an underestimate: charging level 700, relaxed voltage worth 850 → one step up
    to 850;
  - an overestimate: 850 against 700 → one step down;
  - a prolonged clamp after unplug → `max(level, 905)`; UNKNOWN → 950; LOST → as
    UNKNOWN;
  - missing reports keep it owed until fresh ones arrive;
  - repeated replugs;
  - the 09-29 case: the first post-unplug reports still at the clamp must not
    spend it.
- **FULL heuristic:** a charger fault with `5C` clamped reads FULL (documented,
  asserted).

**Mutants, each caught.** The round-4 "990 cap removed" mutant is retired: a
table that ends at 990 with a saturated index makes a separate cap redundant, so
removing it changes no output. ≤ 990 until FULL is still asserted.

| mutant | caught by |
|---|---|
| `K_CC` = 0 | the partial charge below the knee |
| the tail started at clamp entry (round 1's formula) | early clamp entry |
| the generator using round 2's τ formula | the shape grid's 1 h rise and early clamp entry at round 3's set |
| the ceiling `U` ignored | the ceiling cases |
| the rise limiter removed | the clamp-entry count-up |
| the LOST timer resetting at the clamp instead of holding | the 20 + 5 + 10 min case |
| the re-seat before `RELAX_S` | the 09-29 case |
| the lookup index not saturated (reads past the table) | past `T_TAIL` in the shape grid; the new-model scenarios also run under `-fsanitize=address,undefined` |
| OVERRUN keyed on `M` reaching 990 instead of the clock | OVERRUN timing at the degenerate corner |
| OVERRUN timed from session start instead of the tail clock | OVERRUN timing from starts above the knee |
| entry above the knee by node only (no in-segment solve) | the exact-entry assertion |
| UNKNOWN treated as a number | the UNKNOWN start |

### B3. Measure `K_CC` and the relaxation on hardware (after flash 1)

At least two trials, each:

1. On battery at full white, run the pack down to **5-8%** — 3566-3640 mV on the
  current curve (re-derive on the refitted one): a band where one point is ~10 mV,
  well below the 3.83-3.87 V shoulder and the plateau.
2. **The starting estimate, read on the board with no USB:** the debug page's
  `Batt` row (pack mV, the trimmed mean) by eye or camera, with the time, after ≥
  30 min at constant load; two readings 5 min apart. (A USB read is not used: the
  estimator is emptied at every supply change and charging lifts it.)
3. Charge from the Mac's port for **exactly 40 min** (wall clock), BT position, the
  same lighting. Expect roughly +11-15 points.
4. Unplug. The relaxation, by eye or camera on the debug page: 0, 5, 15, 30, 60
  and 120 min.
5. **Endpoint rule:** the 60-min estimate must be ≤ 3810 mV (below the shoulder);
  if higher, reject the trial and shorten the next.
6. **`K_CC` = (L(60 min) − L(start) + D) / (40/60 h)**, offline from the refitted
  curve at the raw estimates, where `D` is the full-white runtime spent in the
  60 min settle (≈ 1.95 points). Not from the displayed level, which the ratchet
  and re-seat shape.
7. Uncertainty: the estimate's spread (±2 mV ≈ ±0.2 point here), the curve's
  leave-one-out error in this band (~0.5 point), timing (±1 min). Use the trials'
  mean; change the model only if B1's bound and B3 disagree beyond it.

B3 measures `K_CC` and `RELAX_S`; it does not measure `L_KNEE` (B1's extrapolation)
— the ceiling and the re-seat bound what that can cost. Each trial plus the
discharge back to ~5% is ~8 h at full white; two trials are a day. Record in a new
`history/battery-<date>-partial-charge/`.

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
- **In `kb_eeconfig.c`**: keep a copy of the last flushed block; at each flush
  compute the **mask of fields that differ from it** and carry that mask into the
  write context, so a physical write session is attributed to the fields it
  actually changed. Count sessions per field and **mixed-field sessions**
  separately. (Setter counts are not subtracted from physical counts: a field
  that changes and changes back before the 5 s settle costs nothing; one that
  rides along on another field's flush is in the mask.)
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

- **Mutually exclusive scopes** around each board task in the main loop: the
  CH582F task, `battery_task`, display housekeeping, the blit pump, `rtc_task`,
  the indicators, `health`, and `kb_eeconfig_task` (the deferred EEPROM flush);
  the rest of the pass is **"unaccounted"** (QMK's `keyboard_task`, the protocol
  and raw-HID work in `quantum/main.c`'s loop, anything unwrapped). Split
  "unaccounted" further if it turns out material.
- Per scope and per pass: elapsed time from a timestamp at entry and exit — ms
  from `timer_read32()`, or a µs counter if a cheap one exists (check SysTick's
  `VAL` before adding anything).
- **On a slow pass (≥ 10 ms):** add each scope's time to that scope's **"time in
  slow passes"** total; count the scope that took the most; and push the pass
  into a **16-entry ring** (pass length plus each scope's time, a byte each) — so
  a stall made of 8 ms of display plus 3 ms of battery shows as both.
- **A runtime enable flag** (RAM, set over raw HID), default on in the diagnostic
  build, for the A/B check in the gates.
- **Transport counters, independent of the stall accounting**, plain counters in
  every build (no `#ifdef` around any of them). Each of these can lose input
  without any ≥ 25 ms gap.

  | counter | where (`ch582f_ajazz.c`) | today |
  |---|---|---|
  | **queue-full rejections** | the enqueue at :585 | `tx_stat_drop`, today's *only* "drop" |
  | **retry exhaustion**, a new counter | the give-up branch at :507 | pops the frame and counts nothing, so abandoned frames read as zero drops |
  | **state frames replaced** in the queue | the 0xA1/0xA3 coalesce, :563-581 | no counter |
  | **UART overrun, framing and parity errors** | the listener at :480 and :908-920 | under `CONSOLE_ENABLE`; move them out so the daily diagnostic build collects them |
  | **RX malformed** | — | existing |

  **Verify the split on the host, before flash 1** (gate 1). Build a harness in
  `scripts/battery_sim`'s style: the driver compiled verbatim against stub
  `hal.h`/`quantum.h`, so no test hook enters either firmware build and no extra
  flash is needed. Its cases:
  - **One frame, every ACK withheld:** retry exhaustion +1; timeouts +9
    (`CH582_TX_MAX_RETRIES` is 8 retransmits, then give up); queue-full +0;
    replacements +0.
  - **The queue filled with non-state frames:** queue-full +1, exhaustion +0.
  - **The queue nearly full (≥ 20 of 24) with an `0xA1` already queued behind
    the in-flight frame, then another `0xA1`:** replacements +1, queue-full +0. A
    nearly full queue with no earlier `0xA1` behind the head does not replace.

  ⚠️ The daily build carries none of the instrumented build's diagnostics; a
  symbol diff verified this in the 09-23 work. An ACK-swallowing hook does not go
  into it.
- Expose all of it on a health page and in `ak820health.py --stalls`.

### D2. Measure, then decide (between flash 1 and flash 2)

Under the verification protocol's soak conditions: ≥ 12 h on battery and ≥ 12 h
on USB, then the attribution (the slow-pass totals and the ring, not only the
largest scope). Design the fix for whichever scopes carry the battery-only
excess. The transport counters are read in every soak regardless.

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
- **E7. `flash.sh`.** Make a failed lighting backup **fatal** (as the keymap's
  is), unless `--no-backup` or a new `--no-lighting` says otherwise; after each
  dump print the file's mtime and size, so the fresh-backup check in the flash
  procedure reads off the output. Fix its stale comment that raw HID needs the
  dip switch on 'cable' (any slider position works since `4b86d95014`).

---

## The verification protocol (each flash)

Idle soaks alone do not exercise the paths this plan changes.

- **Fixed conditions for comparative soaks:** the dashboard showing (not a debug
  page) unless the test is about a page; BT position; white at full drive; LCD
  brightness as recorded; the host timekeeper in its usual state (note it); no
  VIA.
- **The watchdog, at the start and the end of every soak:** not degraded,
  consecutive resets 0, the reset count unchanged across the soak, uptime
  continuous (`ak820 health --crash --json`: `wdt_degraded`,
  `wdt_consecutive_resets`, `vitals.uptime_ms`, `build_token`). **A reset, or a
  degraded watchdog at either end, invalidates the soak** (a reset clears RAM
  evidence; three resets leave the watchdog disabled — docs/hardware.md).
- **Delivered input, not just loop gaps.** Each per-event check below is done
  while JD types a fixed reference text (the pangram five times, ~220
  characters) into a plain-text file on the Mac; a host script diffs it against
  the reference and reports missing, duplicated and stuck keys. Alongside: D1's
  transport counters, read before and after.
- **Per-event checks** (stall and transport counters read before and after each):
  plug in and unplug (BT position); "Battery low" firing (threshold set just
  above the pack with `ak820battery.py cfg`); the RGB cut and its lift; FULL; a
  level going from unknown to known; `Fn`+`D` page transitions; a forced
  internal-flash write (a brightness step). **Pass: no input diff, no transport
  loss, and no ≥ 25 ms gap attributable to the event.** "Transport loss" means any
  increase in queue-full rejections, retry exhaustion, or state-frame
  replacements. A replacement can collapse a double-tap. UART errors are reported
  alongside.
- **The write-rate gate** is measured over a stated interval (≥ 12 h on
  battery) and counts physical write sessions by C1's field mask, excluding the
  saved level's milestones and JD's own setting changes; mixed-field sessions are
  reported, and count against the gate if any field in them is not excluded.

---

## Gates

Staged, so each can actually be run when it comes due.

1. **Before flash 1 (host):**
   - A complete: leave-one-out committed with A2's report; acceptance met or D4
     decided; run 1's `fit-output.txt` reproduced byte-identical.
   - `run.sh` passing, with each curve-tied expectation's arithmetic in a comment.
   - B2's replay adapter in, with the three charges replayed against today's
     charging logic as a baseline.
   - D1's transport-counter harness passing its three cases.
   - E3 and E7 done.
2. **Flash 1 build:** `./build.sh daily` clean (no `-dirty`); a codex
   implementation review with every finding dispositioned.
3. **Immediately after flash 1 — D1's cost:** 30 min with the accounting on and
   30 min off (the runtime flag), same conditions: main-loop passes per second
   within 1% and the ≥ 10 ms count no higher with it on, beyond noise. If not,
   turn it off and trim it before any soak (rollback criterion: a measured cost
   above 0.1 ms per pass).
4. **Flash 1 soaks:** the verification protocol passes; C1 names the writer by
   its field mask; D2's attribution recorded; E5 checked.
5. **B3:** `K_CC` from ≥ 2 trials with its uncertainty; `RELAX_S` from the
   relaxation trajectory.
6. **Before flash 2 (host):** B's model in, with B2's new-model assertions and
   mutants passing; any C2/D-fix simulation.
7. **Flash 2 build:** clean, codex-reviewed.
8. **Flash 2 on hardware:** the protocol passes; **≤ 10 physical write sessions
   per 24 h** on battery outside the exclusions (C2); D2's stall target met or
   its remainder explained. A real charge from below 50% on the Mac, checked
   against the v5 log (`m` and `chg`, B):
   - **`chg`'s LOST (3) and OVERRUN (4) bits never set** in any entry. They are
     latched over the period, so nothing falls between entries. This is the
     stated operating condition; LOST or OVERRUN here means the model is
     miscalibrated. Fail, and revisit B1/B3.
   - **the firmware's self-check bit (6) never set.**
   - **no rise past the evidence**, as an independent check from the log, applied
     **only where it is a necessary condition**. That means entry *i* where:
     - the logged level rose (`level_i > level_{i−1}`);
     - **neither entry *i* nor *i − 1* has a report at 100** (`c5_max` < 100;
       complete in v5 even when the sum saturates), so every estimate in the
       window is below the clamp (all reports ≤ 99 give an estimate ≤ 99.00 <
       99.50) and `U` applied to every rise;
     - **entry *i − 1* holds ≥ 64 reports**, so at every moment of entry *i* the
       64-report ring holds only reports from *i* and *i − 1*;
     - no FULL, no handover and no supply change inside entry *i* (`chg` bits
       and `flags_any`).

     There, `level_i ≤ curve(mv(max(c5_max_i, c5_max_{i−1})))` + 1 pm, using
     the firmware's own integer count-to-mV conversion. This holds because a rise
     ends at ≤ a fresh `U`, a trimmed mean is ≤ its largest report, the curve is
     monotone, and the log floors the level to 0.5 %. A logged rise means a true
     rise inside entry *i*: the true level is non-decreasing there and floors
     to the logged value. Codex's two
     counterexamples, a clamp exit and sparse reports spanning ~20 min, are
     excluded by the second and third conditions. The sustained case, a held
     display above `U`, is LOST's job and is tested exactly in B2.
   - ≤ 99 until FULL, with a FULL step ≤ 3 points;
   - where JD watches the LCD, the percent never skips a value except at FULL
     (the rise limit is 0.1 points a second).
9. Docs and status updated (E6), written to resume cold.

---

## Decisions for JD (defaults apply unless JD says otherwise)

| | question | default |
|---|---|---|
| D1 | "Battery low" threshold | the voltage at **10%** on the refitted curve (~3.68 V), ~5 h before the cut at full white |
| D2 | when the warning re-arms | **only after a real charging session**; no voltage hysteresis |
| D3 | the LCD's bright flash during a write | after C4's test and C2: if write sessions are ≤ 10/day, leave it; if not, add the inhibit-flag guard |
| D4 | the plateau, if A2 misses | **voltage only**, reporting the measured plateau error (worst −8.5 today) rather than a rounder number; the alternative — a time-based countdown across the plateau, like the clamp's — reads low at lighter loads and needs its own design |
| D5 | the camera page in flash 1 | **ship it** with E5's check; revert if it misbehaves |
| D6 | the charging display | B's model: linear until a knee level, then decelerating (never faster than the linear phase). It never rises past the voltage ceiling, and holds when the ceiling falls. It is capped at 99 until FULL. It shows "Charge" when the start is unknown, when the model runs ahead of the voltage, when reports stop, or when termination comes an hour after the model reached 99. At the clamp it runs on elapsed time alone, an accepted limit for charging from the Mac. |

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
- **The agreed order for Phase 2 (JD, 2026-10-06)** is in
  `BATTERY-GAUGE-PLAN.md`, "Phase 2: the agreed order": this plan first, then
  the meter, the lighting modes, light sleep, the emergency Power Reserve, a
  matched runtime run, and radio and deep sleep last.

---

## What this plan deliberately does not do

- Change `5C`'s line or the 0% point (3400 mV, JD's choice).
- Claim state of charge: the level stays "fraction of full-white runtime left".
- Run another multi-day drain (deferred: two runs give a consistency check).
- Build any power mode.

---

## As built

### Step 0 (2026-10-05)

The board stayed in the bootloader overnight until JD power-cycled it, on request,
at 00:29:43 10-05. A replug alone left it in the bootloader; the cable → BT slider
flip booted the firmware. It had charged in the bootloader: the terminal voltage
under charge went from `5C` 85.6 (21:42) to the clamp by 00:31. Its rate there is
unknown, so the 10-04 charge's total time from flat is not comparable. The
post-reboot log gives its termination and, if VDD has not yet risen, its knee. A
background watcher (one `HC_CONN` read every 3 min) takes the final dump and the
health and vitals 12 min after CHRG releases. Records:
`history/battery-2026-10-04-charge/readings.csv`.

**Done at 05:43:13.** CHRG released between 05:28:12 and 05:31:12 (the polls on
either side; the log agrees). The final dump is `log-20261005-0543.csv` (31
entries since the 00:29 boot), with `health-` and `vitals-20261005-0543.json`:
the boot was continuous, with no new ≥ 25 ms stall. **The knee was not
observable:** VDD at the first post-boot entry was already 15 mV over the last
pre-clamp reading. So this charge bounds `T_TAIL` below only (≥ 4.82 h). Its
VDD, timed back from termination, tracks 10-01's at the LED load's offset (−46
to −61 mV): consistent, not a third measurement. **B1 stands: `T_TAIL` is the
median of 09-28 and 10-01, 5.22 h.**

### Gate 1 (host) — met

- **A, the refit** (`scripts/battery_fit.py --refit --write`, commit `43c808b`;
  `history/battery-2026-10-01-drain/refit-output.txt`; each run's
  `refit-points.csv`). Run 1's legacy output is byte-identical. Leave-one-out
  meets the thresholds both ways:

  | direction | below 3.95 V (rms / worst) | plateau (rms / worst) |
  |---|---|---|
  | run 1 → run 2 | 0.54 / +2.05 | 3.13 / −8.66 |
  | run 2 → run 1 | 0.59 / −1.52 | 3.21 / +8.86 |

  So no D4. The plateau passes with little room. Shifting the log source by
  −2 mV takes its worst to −10.09 (run 1 → run 2) and +10.73 (run 2 → run 1), a
  sensitivity, not a correction. The 30% and 35% knots fall in run 2's 4 h gap.
  Linear in time, run 2 gives 3831.1/3846.5 mV against run 1's 3831.7/3846.5; the
  monotone extremes move the pooled knots by up to 11 mV (35%, held low). The plug-in's 15-90 s moves no pooled knot more than 1 mV. The
  firmware gets the pooled curve: no knot moved more than 5 mV.

  ⚠️ **The stated run-1-on-run-2 figures** (plateau rms 3.156, worst −8.490)
  reproduce only when scored as they were: wall-clock levels with T = 50.56, and
  the log's **whole-mV `pack_mv`**. The refit uses the unrounded mV from
  `c5_mean` and t_eff levels. On the plateau, 1 mV of rounding moves a point's
  error by up to ~1 point. Both are printed.
- **E3** (`d91cef1`): the venv guard compares `sys.prefix` with the candidate's
  venv root. The old module refuses by shebang with the venv off PATH; the new
  one works.
- **E7** (`ed2e942`): a failed lighting backup is fatal (`--no-lighting` to
  override), and each backup prints its mtime and size. Both paths were tested
  against the running board with scratch files, stopped at the `Fn`+`Esc` prompt.
- **B2's replay adapter and baseline** (`c87472e`). Each interval's reports are
  reconstructed as a monotone ramp from the logged min to max, summing to the
  logged mean; reports all at the mean lagged by up to 10 pm. **Self-check:**
  replayed against `759e265796`'s own `battery.c` (from git), the 10-04 log's
  levels come back within +5 pm (one log step). **Baseline on today's logic,
  refitted curve:**
  - 09-28 reads 47.3% when `5C` first clamps (3.93 h);
  - 10-01 reads 45.1% at 12:36, 3.8 h in, exactly `curve(4019 − 150)`; it sits
    at the 97 cap for 0.5 h, then steps 3 to FULL;
  - 10-04 reads 18.1% at 1.67 h.
- **D1's transport counters and harness** (`b94b030bdf`, `29e89d1`). New
  `giveups` and `replaced` counters; the UART error counters move into every
  build. `scripts/ch582_sim` compiles the driver verbatim with the daily flags.
  The plan's three cases pass, plus three more, and three mutants are each
  caught.
- `scripts/battery_sim/run.sh`: 35 pass. The curve-tied expectations moved with
  their arithmetic (187 → 185 pm). E2 has four scenarios and three mutants.

### Flash 1, as built (firmware `ak820pro-jdlien`, `dd5c94fdd9`..`f4ad230326`)

- **A3**: the pooled curve; `battery.c`'s comment carries both runs and the
  leave-one-out numbers.
- **E1**: "Battery low" at 3680 mV, the curve's 10%. **E2**: it re-arms only when
  `session` is set on USB, or on a new threshold over `HC_BATTCFG` (so it can be
  tested on demand). **E4**: `COUNTDOWN_S_PER_PM` 184, the mean of 185.5 (run 1)
  and 181.5 (run 2).
- **C1, as built differently from the plan's wording.** The writer is decided at
  the EEPROM boundary, by logical address. A new weak core hook,
  `eeprom_wear_leveling_write_hook()` in `drivers/eeprom/eeprom_wear_leveling.c`
  (`cc04408e01`), maps the address to the kb datablock, the RGB matrix config,
  VIA's region, or other. For the kb datablock, it ORs into a field mask each
  byte that differs from the cache. The plan had the callers set a context, and
  kb_eeconfig keep a last-flushed copy. That breaks on RGB:
  `rgb_matrix_eeprom_flush_allowed()` returns true on every settled pass, not
  only when a flush writes, so a caller-set context would bleed onto other
  writers. The address is exact. `wear_leveling_write()`'s own skip of unchanged
  data makes the mask the fields actually written. The pending writer is cleared
  every pass.

  Sessions are counted at unlock, programs and erases at
  `backing_store_operation_begin`, each by the session's writer, with the
  uptime of the last erase (for C4). Both RTC persistence paths count their
  proposals and stores, with the last value and path. Persistence behaviour is
  unchanged; that is C2.
- **D1's accounting** (`loop_acct.c`). Twelve mutually exclusive scopes:
  - the CH582F task (in `bluetooth_task`), battery+power;
  - display housekeeping, the blit pump, `rtc_task`, `rtc_fast_task`;
  - the LEDs, health, the kb-eeconfig flush, the second edge, the animation;
  - the rest of housekeeping.

  They are timed with the 16-bit system tick (5.33 µs, one register read), and
  the remainder is "unaccounted". A pass is `health_loop_tick`'s own, so a slow
  pass is exactly one of `count_ge_10ms`. Per slow pass, every scope's time is
  added, the largest is counted, and a 16-entry ring stores the pass length and
  each scope's ms, with uptime. All-pass totals are kept too. The runtime flag
  defaults on.
- **Health protocol 8**: `HC_FLASHW` (C1), `HC_ACCT` (D1; page `0xF0` on/off,
  `0xF1` reset) and `HC_LINK` (the transport counters). `health_reset()` clears
  C1 and D1 too. `ak820health.py --stalls` shows all three. `scripts/diag_sim`
  compiles both modules verbatim and decodes their pages with the Python's own
  decoders (`d19adc2`).
- RAM: `.bss` +720 B over the rollback ELF; heap 6080 → 5360 B (flash 2's v5 log
  needs 1440).
- **Tools for the measurements** (`3a1686e`): `scripts/typing_check.py` (the
  delivered-input check), `scripts/board_snapshot.sh` (one labelled
  before/after reading) and `scripts/acct_ab.py` (gate 3).

### Gate 3 — failed, and the trim (2026-10-05)

Flash 1 went on at ~12:28. Gate 3 ran 12:38-13:39 (`scripts/acct_ab.py
--minutes 30`; `history/battery-2026-10-05-flash1/gate3-acct-ab.json`), plugged
in, BT, FULL, the dashboard, white at full drive, with JD typing on another
keyboard:

| half | passes/s | ≥ 10 ms | ≥ 25 ms |
|---|---|---|---|
| ON, 12:38:49-13:08:49 | 273.43 | 16 | 0 |
| OFF, 13:08:49-13:38:49 | 280.52 | 11 | 0 |

**Passes/s −2.53% with it on: fails the 1% gate.** The ≥ 10 ms difference
(5) is inside the noise (2√27 ≈ 10.4). The cost, 0.092 ms a pass, is under the
0.1 ms rollback line, so flash 1 stays. As the plan says, the accounting went
OFF at 13:39:52, and is to be trimmed before any soak.

**Why it cost that much** (from the ELF): each scope made three calls (two
`stGetCounter`, one `loop_acct_add`). Every pass then summed all twelve scopes,
added them into 64-bit totals and cleared them. The row ISR takes ~73% of the
CPU, so each main-loop cycle costs ~3.7× in wall time.

**The trim** (firmware `7a0f28aa8f`; host test parent `5035b9c`):
- `ACCT` reads the tick inline (`st_lld_get_counter`) and adds into a running
  32-bit total at a fixed address;
- a pass end is one 48-byte copy, an add and a compare. A slow pass takes its
  own ticks as `run − pass_base`. The 64-bit all-pass totals fold in every
  4096 passes, and the pages read the pending part without folding;
- skipped, wrapped and on/off partial passes are dropped from every total;
- the per-pass param repeat and user hook are no longer timed (UNACCOUNTED).

`diag_sim` passes, including a new test across a fold. That test's
unaccounted figure also shows the old per-pass rounding: 9971 ms against
9984 for the same input. Estimated from the disassembly: ~135 cycles a pass
against ~600, about 0.6%. **Gate 3 runs again on the trimmed build.**

**Codex on the trim** ([verbatim](review-codex-battery-refine-impl1b-2026-10-05.md)),
verdict "fix 1 first":

| # | finding | disposition |
|---|---|---|
| 1 | Pages 3-4 read `run − fold_base`, so a mid-pass read counted the open pass's scope time but not its gap, or a pass about to be dropped | **Fixed, verified** (`97a24c6e20`): they read `pass_base − fold_base`. A new mid-pass test (`9a83613`) fails at `7a0f28aa8f` (ch582 5022, unaccounted 9974) and passes after. |
| 2 | Overflow and stack | Right, no change. |
| 3 | `slow_pass()`/`fold()` inlined: every pass end saved nine registers and set up a 112-byte frame, off included | **Fixed** (`97a24c6e20`): those and `ring_put()` are `noinline`. The fast path now pushes six registers and allocates no frame (from the ELF). |
| 4 | Untiming the param repeat and user hook | Acceptable for D2, no change. |
| 5 | Slow-pass u32 totals wrap after ~6.36 accumulated hours a scope | Noted, no change: at gate 3's ~12 ms a slow pass and ~30 an hour, that is years. |

No second round: the one fix is small and has a test that fails before it.
Flash 1b is `ak820pro-builds/out/via-daily-97a24c6e20-20261005-152818.bin`,
token `0x5425251f`, clean.

**Flash 1b went on at 16:28, and gate 3 passed** (16:39:40-17:39:40, same
conditions; `gate3b-acct-ab.json`):

| half | passes/s | ≥ 10 ms | ≥ 25 ms |
|---|---|---|---|
| ON | 291.88 | 18 | 0 |
| OFF | 290.90 | 21 | 0 |

That is +0.34% with it on: the cost is below what 30 minutes can resolve
(it was −2.53%). The accounting stays on. The battery soak and B3's drain
began at ~17:40, at the `battery-soak-start` snapshot.

### The first battery soak, and D2 round 2 — flash 1c (2026-10-06)

**Soak read 1** (17:40:14 10-05 → 12:48:36 10-06, 19.1 h, on the pack
throughout but the minutes at either end;
`history/battery-2026-10-05-flash1/readings.csv`):
- **D2: the battery-only stalls are in `ch582_task`.**
  - On battery: 5,494 passes ≥ 10 ms (~287/h). ch582 was the largest scope in
    4,720 of them, with 64.1% of their time (~8.2 ms each); unaccounted
    23.6%, `rtc_task` 5.5%.
  - On USB, in the 40 accounted minutes before: 23 slow passes, ch582 the
    largest in none.
  - Yet ch582's MEAN per pass was the same on both (0.47 vs 0.49 ms): the
    cost is in occasional long calls.
  - On battery the module sends `5C` ~2× as often (306 vs 167 a period), and
    its values vary, so `battery_5c_report`'s trimmed-mean sort has work to
    do. It is a candidate, but by estimate too small to be all of it.
- **C1: the writer is the RTC period, on its PCF path.** 6 stores of 27
  proposals, plus 5 level milestones and 1 LCD-brightness session; RGB, VIA
  and other 0. That is 12 sessions in 19.1 h, ~7.5 per 24 h outside the
  exclusions (if the brightness change was JD's). C2 is the plan's
  persistence scheduler.
- **One ≥ 25 ms gap**: 25 ms, probably at the plug-in for the read (the
  ring's 25 ms pass is ~12 s before it, `second_edge` 20 ms of it). That is
  a per-event finding, not the soak's.
- **Transport:** no loss. 13,968 sent, 7,624 ACK timeouts, 0 give-ups, 0
  replaced, 0 queue-full; UART overrun 3, framing 1.

**Flash 1c** (firmware `647c12f26d`, host `66d82c9`) is diagnostic only. It
splits each `ch582_task` call ≥ 4 ms into its parts:
- control, the RX drain and parse, the `5C` hook, the `5B`/`5C`
  acknowledgement writes, and the TX pump;
- with the bytes and `5C` reports the call handled, and every `5C` hook's
  cost.

It runs under D1's flag, with inline ticks, on `HC_LINK` pages 0x21-0x2A
(page 0 and the protocol version unchanged). `ch582_sim` drives a slow `5C`
through the real parser and decodes the pages with the real Python. The
artifact is `via-daily-647c12f26d-20261006-135833.bin`, token `0x0c93c530`,
clean, heap 5048 B.

**Codex on flash 1c** ([verbatim](review-codex-battery-refine-impl1c-2026-10-06.md)),
verdict "flash":

| # | finding | disposition |
|---|---|---|
| 1 | The split attributes correctly. Only watchdog bookkeeping and the final record fall outside it | No change. |
| 2 | Paging right. But `read_link` (page 0) checked the command, not the page, so a concurrent reader's profile reply could be decoded as link stats | **Fixed, host only**: it takes only a reply whose [3] is a version (< 0x21). A new `diag_sim` check fails on the old reader. |
| 3 | The cost is understated (four reads a pass, four more per `5C` with ACKs, `prof_end`'s call and frame). Plausibly small, not shown below gate 3b's resolution | **Accepted, no gate rerun**: a temporary diagnostic, its cost recorded here. Flash 2's build drops it or keeps it under the flag, and gate 3's comparison will be read again on flash 2. |
| 4 | The 16-bit tick aliases past 349.5 ms | Accepted. |
| 5 | It localizes elapsed time, not CPU: each section includes interrupts during it | **Noted for the reading**: a large `5C` section implicates that interval, not necessarily the sort. |

### Flash 2 so far (host, ahead of B3)

Branch `phase1b-flash2` of the firmware, local only, **rebased 10-05 ~17:50
onto flash 1b (`97a24c6e20`)**: `7e6b850d55` (B's model, the re-seat after
`RELAX_S`, log v5), `3665f33fd3` (M, the charging state and the curve exposed
for the simulator), `d4d46e24a1` (two fixes below), `99128c48ca`
(`hid_protocol.c`'s battery comments for v5). Before the rebase they were
`5706451217`, `0338829109`, `cc337781df` and `f9a794dad5`, the hashes the
records below cite. Every host check passed again after it: `run.sh` 73 ok
(with the sanitizer pass), mutants 12 of 12, the grid's 901 points,
`diag_sim`, `ch582_sim`. The
tail is a **placeholder** until B3: `K_CC` 190, `L_KNEE` 775, `T_TAIL` 313 min.

- **Two bugs the scenarios found, fixed in `cc337781df`:**
  - a brief replug between the unplug and the re-seat (no new session) left
    the re-seat owed with no `RELAX_S` running, so it never resolved
    (`m_reseat_replugs`). The unplug now restarts `RELAX_S` whenever a re-seat
    is owed;
  - FULL closing the model left the pause's `RELAX_S` pending. At its end the
    ring was emptied and FULL dropped until it refilled: 10-01's replay read
    1000 with the state NONE for 18 s. FULL now cancels it (`m_full_holds`
    fails without the fix, 12 s, and passes with it).
- **B2, all of it but B3's numbers** (parent `39d92fd`, `bab08fe`, `11f6965`):
  - `run.sh` against a v5 `battery.h` runs the 38 model scenarios, the three
    replays, and flash 1's 31 scenarios (four of them now check v5's intended
    behaviour: the 990 cap, "Charge" with no trusted start, the re-seat after
    `RELAX_S`, v5's header). 72 ok; then the model's scenarios again under ASan
    and UBSan, ok. Against flash 1 it is unchanged: 35 ok, the baselines equal.
  - **The firmware path over B1's whole grid**: `tail_fw.c` #includes
    `battery.c` verbatim; `tail_fw_grid.py` generates the header with the real
    generator at each of the 900 points (and the shipped one) and requires
    `tail_x16`, `tail_entry_s` and the model's trajectories to equal
    `tail_grid.py`'s construction exactly. On top: the X16 entry, exactly 990
    past `T_TAIL`, a 1 h rise ≤ `K_CC` + 1 from every start second, ≤ 0.7 pm
    from the curve. It times OVERRUN through the whole charging path from
    starts below, at and above the knee, ±1 s. **901 points ok, none
    infeasible.** Starts above ~900 cannot be made on the pack, so there the
    entry and the clock are checked by the lookup alone.
  - **The mutants table** (`mutants.py`): every catching test passes unmutated,
    then **12 of 12 mutants are caught** by the test the plan names.
  - The generator now rounds `L_KNEE` to whole pm before building the table,
    so its first node is the firmware's knee exactly (a fractional knee such as
    682.5 left a half-pm seam). The placeholder's table is unchanged.
- **One display edge, left as is:** in a short pause with the level unknown
  (UNKNOWN-CHG or LOST), the text reads "USB", not "Charge": it follows the
  charger pin, as today. It is accurate (the charger is not charging); the
  state table's "Charge until a `PAUSE_S` pause" describes the level, which
  stays unknown.
- **The camera page, redrawn in the clock's font (JD, 2026-10-06).** JD
  found the seven-segment digits ugly and cryptic ("like a kid went into MS
  Paint in 1993"). The clock atlas, cropped for the clock, still holds all 95
  ASCII glyphs. So the page is now four centred lines: the volts and the
  percent in the clock face (15×22), the board's clock in the same face, and
  the raw `5C` in the status face. Each is a fixed grid repainted one changed
  glyph a pass, like the debug page. Previews were rendered from the shipped
  atlases before any code (`scripts/camera_page_preview.py`, which mirrors
  `cam_lines[]`), and JD approved them ("night and day"). Firmware
  `6eadbd0e3a` on the branch.
- **The branch is rebased onto flash 1c (`647c12f26d`)**, so flash 2 keeps
  the ch582 profile under D1's flag. Its first full build
  (`via-daily-6eadbd0e3a-20261006-143050.bin`, WIP: the placeholder tail, not
  for flashing) is clean with no warnings. Heap 3496 B, against 5048 on flash
  1c: the v5 log takes its 1440.
- **D, the battery stalls: fixed** (`2e7155b2db`, 10-07). Flash 1c's profile,
  read at 13:44 10-07 after 23.6 h, settled it:
  - 73.5% of the slow ch582 calls' time was `battery_5c_report`, mean 1.75
    ms a report, worst 3.6. It insertion-sorted the 64-report ring on every
    report.
  - The module answers each 5 s poll with three reports in one burst, so
    ~6 ms of one pass.
  - On USB at the clamp every report is 100 and the sort moved nothing,
    hence battery-only.

  The trimmed mean is now taken from a histogram of the ring's values, kept
  on insert, eviction and forget: skip the lowest eighth, sum the next three
  quarters. It is identical to the old sort, verbatim, on 99,972 estimates
  (`battery_sim` `c5_equivalence`, `190e634`), and a top-only-trim mutant
  differs in 74,565.
- **C2, the flash writes: built** (`54c437028b`). C1 named the RTC period's
  PCF path: 6-8 saves a day on battery.
  - Both correction paths now only propose; `rtc/rtc_persist.c` owns every
    save. The first comes at 10 min if nothing is stored, later ones only
    ≥ 64 ticks off and ≥ 6 h after this boot's last.
  - `diag_sim` `persist` (`e947ee6`): first save at 10 min; 3 saves in a
    day of the worst both-paths wander; 1 in two settled days. Mutants
    without the budget (1440 a day) or the 10-min wait are caught.
  - The `rtc.c` comment that claimed the 64-tick threshold prevented steady
    rewrites is corrected.
- Flash 2's branch with both builds clean (`via-daily-54c437028b-20261007-135059.bin`,
  WIP, placeholder tail).
- **Left for flash 2:** B3's `K_CC` and `RELAX_S`, then
  `battery_charge.py --tail K_CC L_KNEE T_TAIL --header .../battery_tail.h` and
  `run.sh`, `tail_fw_grid.py`, `mutants.py` again (if `K_CC` falls outside
  160-230, widen the grid first); the final map's RAM; codex's gate-7 review.
  C2 and the D fix are in (above).

### B3 trial 1 (2026-10-07/08)

Record: `history/battery-2026-10-07-partial-charge/` (`readings.csv`, and
`relaxation-video.csv` read off JD's overnight time-lapse of the camera page).

- **The charge:** 20:21:37-21:01:35 on the Mac (39 min 58 s by ioreg), from
  3482 mV (1.8% on the curve), at full white. That is **below the 5-8% band**:
  JD restarted from 2% after the first try was lost. The 60-min estimate
  (22:01:21, 3652 mV) is ≤ 3810: the trial counts.
- **`K_CC` = (86.00 − 17.65 + 19.78) / 0.6661 h = 132.3 pm/h** (122-142 with
  ±2 mV and ±5 pm of curve error), on the curve on the board (`dd5c94fdd9`'s).
  **Cross-check by runtime:** the RGB cut came 5 h 23 min after the unplug
  (02:24:42-02:25:03 by the board's clock). At 50.56 h per 1000 pm that is
  106.6 pm at the unplug and **133.5 pm/h**. This check uses the curve only at
  the start.
- **It contradicts B1's bound** (165-213, from assuming 70-90% of a charge goes
  in before the knee) beyond the uncertainty. It is not a different charge
  current: the charging `5C` climbed 59→71 in 20 min here, as on 10-01 and
  10-04 (all at `led_pm` 1000). One trial; **the rule stands: trial 2, then
  decide.** The model can absorb it. At `K_CC` 120-145 every point of B1's
  other ranges is feasible (360 of 360, `tail_grid.solve`). `L_KNEE` would be
  ~515 (`K_CC` 133, `t_knee` 4.1 h, `R` 30) instead of ~626, so the tail would
  carry half the charge. That is the knee's meaning to revisit, not the
  measurement.
- **The relaxation:** take each reading's curve level, plus the full-white
  drain since the unplug. That gives the implied level at the unplug: ~115 pm
  at 6-10 min, ~112 at 15, ~109 at 30, ~106 at 60 and ~103 at 120, against
  106.6 by runtime. A re-seat would therefore read ~1 point high at 6-10 min,
  ~0.6 at 15 and ~0.3 at 30. The first 6 min were not filmed, so the initial
  `RELAX_S` (120 s) is only known to be ≥ 1 point high. Provisional: **`RELAX_S`
  1800 s**, to be confirmed by trial 2 filmed from before the unplug.
- **The reserve:** 5 h 31 min from the RGB cut to death (07:56:00-07:56:08,
  LEDs off, camera page lit, BT), against run 2's 5 h 01 min. The estimate went
  below the clamp (LO) at ~07:05. The board's RAM log died with it.
- **Flash 2 with trial 1's numbers** (firmware `872f1f8a67`, host `b793644`,
  2026-10-08), built so JD can flash before trial 2. The display model plays
  no part in B3's raw-estimate measurement.
  - **The tail:** `battery_charge.py --tail 133 533.255 5.22`. That gives
    `L_KNEE` 533, τ 5.78 h and `A` 1301.8, and the tail ends at 54 pm/h.
  - **Constants:** `RELAX_S` and `PAUSE_S` are 1800 s.
  - **The tail ends steep.** If the charger stays at constant current past
    the VDD rise, the model reads low mid-charge (by up to ~5 points), and
    the re-seat corrects it upward once at the unplug. The placeholder it
    replaces (`K_CC` 190, knee 775) would run ahead of a 133 pm/h pack by
    ~14 points at 2 h and ~26 at 4 h, held back only by the ceiling below
    the clamp.
  - **The checks:** `tail_grid`'s `K_CC` range is now 120-230 (1380
    feasible), and `tail_fw_grid` passes 1381 of 1381.
  - **Two scenarios assumed the old numbers.** `m_delayed_termination` now
    times OVERRUN from the tail entry when `L0` is above the knee, with an
    independent scan of the table. `m_reseat_missing` now stays stale past
    `RELAX_S`.
  - **The clamp-entry mutant survived the new header.** With the knee at 533,
    `m_early_clamp`'s `L0` of 600 lies above it. The new
    `m_early_clamp_below` (`L_KNEE − 100`) and round 3's grid point, the set
    this plan names, catch it: 12 of 12.
  - **The build:** `run.sh` 75 ok; `diag_sim` and `ch582_sim` pass;
    `via-daily-872f1f8a67-20261008-105323.bin` (token `0x314c6d7a`), with
    `.bss` unchanged at 30112 B.
  - Gate 7's codex review:
    [`review-codex-battery-refine-impl2-2026-10-08.md`](review-codex-battery-refine-impl2-2026-10-08.md).
- **`RELAX_S` confirmed (2026-10-08).** Trial 2's recharge from flat, 65 min
  to ~9%, was filmed from 1.2 min after its unplug. Measured against the
  60-min value, a re-seat would read ~1.7 points high at 1-2 min (the old 120
  s), ~0.9 at 6-13 min, ~0.6 at 15-21 and ~0.35 at 25-37. That is trial 1's
  shape where they overlap. **`RELAX_S` 1800 s stands**
  (`history/battery-2026-10-08-partial-charge/relaxation-video-recharge.csv`).
- **Trial 2 (2026-10-08), on flash 2**, recorded in
  `history/battery-2026-10-08-partial-charge/`:
  - **The run:** a recharge from flat, then the flash at 12:54. On USB
    14:32:15-15:15:18, 43 min 00 s with a 3 s cable swap, from 5.0%
    (~50 pm).
  - **`K_CC` 148.5 pm/h, preliminary** (138-159). L(60) came from a read over
    a **data-only port** at 16:18 (62 min). The runtime cross-check waits for
    the RGB cut.
  - **With trial 1:** the two overlap at ~138-142, and the mean is ~141. Both
    are below B1's 165-213. Flash 2 carries 133. A move to ~141 would mean
    regenerating the tail and reflashing once the cut is in.
  - **The bench** (`docs/test-bench.md`): a switched-off Acasis port cuts VBUS
    but not data, so **the board can be read on battery without charging**.
    The HomeKit outlet switches charging when the port is on
    (`scripts/bench_power.py`).
- **Trial 3 (the night of 10-08/09), unattended on the USB relay**
  (`scripts/bench_trial.py`, `night-run.csv`):
  - **The run:** charged exactly 2400.0 s from the RGB cut (L = 0, the curve's
    zero), then read every minute through the relaxation and on to the next
    cut.
  - **`K_CC`:** 120.4 on the curve, 127.0 by runtime. Trial 2's runtime had
    read 5.6% low against its curve; trial 3's reads 5.3% high. Both runs were
    on data-only USB on flash 2, so these are the curve's local errors, **not
    a USB load overhead**.
- **B3 MET (gate 5).** The trials, each the mean of its two methods:

  | Trial | Start | `K_CC` (pm/h) |
  |---|---|---|
  | T3 | 0% | 123.7 |
  | T1 | 1.8% | 132.9 |
  | T2 | 5.0% | 142.4 |
  | **Mean** | | **133.0** |

  The mean is the value flash 2 already carries, so there is no reflash for
  `K_CC`. `K_CC` rises with the starting level (~+18 pm/h over the bottom 5
  points), which a constant cannot follow. A charge from empty reads a little
  high early. The bench's charge-then-drain runs can map that, and the knee
  with it.
- **`RELAX_S` 1800 s holds across three relaxations** (trial 1, the 10-08
  recharge, trial 3). At 30 min the voltage-implied level sits 0.1-0.35 point
  above its 60-min value.
- **Trial 2, from the lessons:** film the whole trial, start readings included.
  Start ≥ 2 h after any earlier charge, because the relaxation inflates the
  start for an hour or more. Start in the band, and keep filming to the RGB cut
  for the runtime cross-check.

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

### Round 2 — codex, 2026-10-04, on revision 2 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md#round-2-2026-10-04-on-revision-2----verbatim))

Codex counted 9 of round 1's findings resolved and 10 partly resolved, and
reproduced the 216 points and the plateau figures exactly. Its new findings:

| # | finding (short) | disposition |
|---|---|---|
| R2-1 | P1: the "Charge" fallback had no implementable rule; clamp timing is not CC/CV | **Accepted.** A voltage ceiling `U` (no I×R subtraction) bounds the model; LOST ("Charge") when the model runs > 50 pm above it for 30 min; the logs described as timing against the sensor clamp and VDD, not phases. B. |
| R2-2 | P1: UNKNOWN on boot-on-USB contradicted the from-flat replays; `LEVEL_UNKNOWN` = `0xFFFF` passes numeric checks | **Accepted.** A FROM-FLAT state: a boot on USB with `5C` at 0 under charge is a trusted `L0` = 0 (all three charges start so); validity checks before every comparison; an UNKNOWN unplugged at the clamp becomes 950. B, B2. *(09-28 does not start at 0; corrected in R3-1.)* |
| R2-3 | P1: B3 read the start over USB, had wrong voltages, and claimed to measure `L_CC_CAP` | **Accepted, verified** (5-8% = 3566-3640 mV). The start is read on the board without USB; 40 min with an endpoint rule (≤ 3810 mV at 60 min); ≥ 2 trials; `L_CC_CAP` dropped for the ceiling, `L_KNEE` stated as B1's extrapolation. |
| R2-4 | P2: the CV formula accelerated partial charges | **Accepted.** Phases by level (linear to `L_KNEE`, then a decay with one compiled-in τ), not by clamp entry; tests for early clamp entry and near-full top-ups. B, B2. |
| R2-5 | P1: largest-task attribution hides cumulative causes | **Accepted.** Per-scope time-in-slow-passes totals and a 16-entry slow-pass ring; mutually exclusive scopes with an "unaccounted" remainder; `kb_eeconfig_task` and the RTC/display paths covered. D1. |
| R2-6 | P1: the typing gate could pass with lost input or a disabled watchdog | **Accepted.** A delivered-input check (a reference text typed and diffed on the host), transport counters independent of stall attribution (queue replacements included), and a non-degraded watchdog required at both ends. The protocol, D1. |
| R2-7 | P2: censored means treated as measurements; no gap sensitivity | **Accepted, verified** (the 15:59 entry). Every interval with a clamped report excluded in the new fit; gap knots reported under both monotone extremes and linear interpolation. A1. |
| R2-8 | P2: setter counts cannot attribute physical writes | **Accepted.** The flush carries a mask of fields changed since the last flushed block; per-field and mixed-field sessions counted; the gate counts physical sessions by mask. C1, the protocol. |
| R2-9 | P2: gates could not run when due | **Accepted.** Gates staged: baseline replays before flash 1, D1's A/B qualification right after it with a rollback criterion, new-model assertions after B3. |
| R2-10 | P2: `flash.sh` prints no timestamps on the normal path; a lighting failure continues | **Accepted, verified** in `flash.sh`. The procedure checks the backups' mtimes while the script waits for `Fn`+`Esc`; E7 makes the lighting failure fatal and prints mtimes. |
| R2-11 | P2: 7 ms is a loop interval, not the program state | **Accepted, verified** (`health.c`; the datasheet's 10/20 µs per 64-bit program). Relabelled here and in docs/battery.md and CLAUDE.md (commit `80e96b5`). |

### Round 3 — codex, 2026-10-04, on revision 3 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md#round-3-2026-10-04-on-revision-3----verbatim))

Codex counted 7 of round 2's findings resolved and 4 partly resolved. Of round
1's ten partly resolved findings, 5 are now resolved; the rest are covered by
R3-1 to R3-6. It again reproduced the 216 points, the plateau RMS of 3.156 and
the worst error of −8.490 byte-for-byte. Verdict: not ready, on R3-1 to R3-3.

| # | finding (short) | disposition |
|---|---|---|
| R3-1 | P1: 09-28 starts at `5C` 4, not 0, so it cannot enter FROM-FLAT as written | **Accepted, verified** (the log's first entry is 4 at age 5 s; `readings.csv` saw 2 → 3 → 4). FROM-FLAT now keys on the first estimate ≤ 10.00 counts (≤ 3248 mV under charge, ≥ 150 mV below the cut). All three charges qualify on their own data, with no zero invented; there is a synthetic 10.00/10.01 boundary test. B (Note 1), B1, B2. |
| R3-2 | P1: `max(level, min(M, U, 990))` cannot keep the display under a falling `U`; no rise limiter; no stale-estimate rule | **Accepted, verified** with codex's 4008 → 4006 mV example on the current curve. The display rule is now a stated precedence: never falls; never rises past the evidence (`U` below the clamp, none at the clamp, no rise when the estimate is not fresh); at most 1 pm/s; ≤ 990. A falling `U` makes it hold, and `LOST_PM` is the declared tolerance. Report loss for 10 min gives LOST. B2 tests falling estimates, clamp entry and exit, and report loss. |
| R3-3 | P1: the "existing drops" do not count retry exhaustion; UART errors are console-only | **Accepted, verified** (`ch582f_ajazz.c:507` pops without counting; `tx_stat_drop` is only queue-full at :585; the UART listener is under `CONSOLE_ENABLE`). There is a new retry-exhaustion counter, a replacement counter, and UART errors in every build. The split is verified by a host harness that compiles the driver verbatim against stubs, so no fault hook enters a firmware build and no extra flash is needed. "Transport loss" is defined. D1, gate 1, the protocol. |
| R3-4 | P2: a fixed τ can start the tail faster than `K_CC` | **Accepted, verified** (codex's set gives 253.2 pm/h and 787.85 at 1 h). The tail now approaches an asymptote `A` with its starting rate equal to `K_CC`, and reaches 990 at `T_TAIL`. It is feasible if and only if `K_CC·T_TAIL > 990 − L_KNEE`, which holds across B1's whole grid. If it is infeasible, revise the model or ship "Charge"; never adjust measurements. B2 checks the shape over the grid, and round 2's formula is now a mutant. |
| R3-5 | P2: LOST is a below-clamp consistency check, not supply qualification | **Accepted.** This is now stated plainly: at the clamp the display runs on elapsed time without voltage validation, accepted for the stated condition. It is bounded by the 990 cap, a new OVERRUN rule ("Charge" 60 min after the model reaches 990 without FULL) and the re-seat. A LOST session re-seats as UNKNOWN. There is a delayed-termination test at the clamp. |
| R3-6 | P2: nothing rejects the removed-990-cap mutant | **Accepted.** ≤ 990 until FULL is asserted for sessions starting at or below 990. The delayed-termination case holds CHRG 2 h past the model's arrival at 990, at a parameter set with `A` 1044, so the mutant shows. |

**Found while revising, not raised by codex:** the state machine had no rule
for a CHRG pause inside a session. `session` survives CHRG gaps, and today's
idle path would have moved the level on a voltage still relaxing from the
charge. A pause now holds the display; after `PAUSE_S`, it hands over to the
idle path. There are tests for both. B, B2.

### Round 4 — codex, 2026-10-04, on revision 4 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md#round-4-2026-10-04-on-revision-4----verbatim))

Codex counted R3-3, R3-5 and R3-6 resolved, R3-4 resolved mathematically, and
R3-1 and R3-2 partly resolved. It confirmed the driver line numbers, the nine
timeouts before abandonment, and the tail example (τ 2.61175 h, `A` 1043.880,
ending at 20.62985 pm/h). It judged the host harness realistic, with more stubs
than two headers. It found the pause handover coherent in policy. Verdict: not
ready, on R4-1 alone.

| # | finding (short) | disposition |
|---|---|---|
| R4-1 | P1: gate 8 forbade the held display above `U` that LOST's 30 min dwell permits | **Accepted.** Gate 8 now checks rises against a necessary condition the log can show: a rise's ending level ≤ `curve(max c5_max)` over the entry and the one before. It checks for no LOST or OVERRUN on a Mac charge, and leaves the sustained case to B2's exact tests. B adds `M` and the charging state to the log (v5). The B2 fixture now fixes `M − U` = 30. `level ≤ M` is scoped to sessions starting at or below 990. |
| R4-2 | P2: 1 pm accuracy does not fix *when* the tail arrives at 990; in the degenerate corner a Q16 recurrence stalls or arrives ~10 min in | **Accepted, verified** (that corner gives `L_KNEE` 977.5, τ ≈ 0.054 h). The recurrence is replaced by a generated table at 60 s steps ending at exactly 990, read on a tail clock. Arrival is the clock reaching `T_TAIL`, and OVERRUN keys on it. A start above the knee enters by integer search. Checked on the whole grid: ≤ 0.13 pm from interpolation, ≤ 0.5 pm with integer entries, ≤ 337 entries. B2 tests OVERRUN timing over the grid, including starts above the knee. |
| R4-3 | P2: interval minima are not first estimates; 10.01 is unreachable through 5 integer reports | **Accepted, verified** (`c5_trimmed_mean_x100` trims nothing below 8 reports). Each charge's opening is now a labeled reconstruction, tied to what JD observed at plug-in: 2 → 3 → 4 on 09-28, `0@1 <3161` on 10-01, `0@0` on 10-04. The boundary test is 10.00 against 10.20 through real reports, plus 10.00 against 10.01 on the helper directly. |
| R4-4 | P2: the pause rules needed their timing, evidence and flags pinned down | **Accepted.** A new `modeled` flag is kept apart from today's `session` (which stays "re-seat owed"). A pause is timed on `charging_now()`. The handover adopts only an estimate built from reports ≥ `RELAX_S` after the stop, and holds until one exists. A resumption after the handover requalifies at 60 s. The tests are parameterized on the final `PAUSE_S` and `RELAX_S`, at both edges, with missing reports and an unplug after the handover. |

Also fixed from round 4's prose: the D1 harness's replacement case now queues an
`0xA1` behind the in-flight frame first, since a nearly full queue alone does not
replace.

### Round 5 — codex, 2026-10-04, on revision 5 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md#round-5-2026-10-04-on-revision-5----verbatim))

Codex counted R4-3 and R4-4 resolved, and R4-1 and R4-2 partly resolved. It
confirmed the cited plug-in observations, the reachable 1000 against 1020
boundary, and the 337-node / 674-byte table. Verdict: not ready, on R5-1 and
R5-2.

| # | finding (short) | disposition |
|---|---|---|
| R5-1 | P1: a bigger v5 entry overflows the `HC_BATTLOG` reply, which is exactly 32 bytes today; all flag bits are taken | **Accepted, verified** (`hid_protocol.c` ~598 answers at `&data[3]`; 3 + 13 + 16 = 32 = `RAW_EPSIZE`; `BATT_F_*` uses all eight bits). v5 drops the per-reply period (the host reads it from `HC_BATTCFG`, which already reports it), so 3 + 11 + 18 = 32. There is a `_Static_assert` on the sum, host decode tests for v3/v4/v5, and a guarded buffer in the harness. The entry gains `m` and a latched `chg` byte. B. |
| R5-2 | P1: gate 8's rise check is not a necessary condition at a clamp exit, or when sparse fresh reports span more than two entries; LOST could fall between entries | **Accepted.** The check now applies only where it is sound: no report at 100 in either entry, ≥ 64 reports in the previous one, and no FULL, handover or supply change. Both of codex's counterexamples are excluded. `chg` latches LOST, OVERRUN, handover, and a firmware self-check over each period. Gate 8. |
| R5-3 | P2: integer-table accuracy and the rate bound were overstated; the start-index search quantized | **Accepted, verified.** Nodes are now in 1/16 pm, with the index saturating apart from the clock and an exact in-segment entry. The figures come from a committed checker, `scripts/battery_sim/tail_grid.py`: 0.173 pm interpolated, 0.607 pm rounded to whole pm, 1 h rise never above `K_CC`, entry exact. The rate bound is stated on the analytical curve; the firmware tests use the measured tolerances. B, B2. |
| R5-4 | P2: with a table ending at 990, the removed-cap mutant is equivalent | **Accepted.** That mutant is retired. New mutants: an unsaturated index (also caught under ASan/UBSan), OVERRUN keyed on `M` or on session time, and node-only entry. B2. |

### Round 6 — codex, 2026-10-04, on revision 6 ([verbatim](review-codex-battery-refine-plan-2026-10-04.md#round-6-2026-10-04-on-revision-6----verbatim))

**Codex's verdict: ready to execute, no P1 blockers.** It counted R5-1 and R5-4
resolved, and R5-2 and R5-3 resolved but for a P2 each. It reproduced every
`tail_grid.py` figure, and confirmed the v5 offsets: written count at packet
bytes 12-13, the entry from 14, and `HC_BATTCFG`'s period at packet bytes
10-11. Both P2s are fixed in revision 7 rather than left to execution:

| # | finding (short) | disposition |
|---|---|---|
| R6-1 | P2: the checker sampled (every 7 s and 300 s), so its maxima were low; rounding and entry needed units | **Accepted, verified.** `tail_grid.py` now checks every integer second, with C's half-up rounding `(x16 + 8) / 16`, and asserts saturation past `T_TAIL`. It gives 0.180 pm interpolated (codex: 0.180470) and 0.601 pm displayed. Codex's 0.657 used Python's ties-to-even; the C rounds half up. Entry is asserted as the first crossing in X16 units, not on rounded output. B, B2. |
| R6-2 | P2: the log's extrema stop updating when the 16-bit sum saturates, so `c5_max` < 100 does not prove no 100 | **Accepted, verified** (`battery.c` ~332). v5 keeps the extrema for every accepted report, and bit 7 of `chg` marks a saturated sum or count. B2 has a fixture. The recorded runs peak at 344 reports a period. |

**The plan is ready for a new session to execute.** Step 0 now records the
2026-10-04 22:37 bootloader event and what the charge's end can still give B1.

### Gate 2 — codex on flash 1, 2026-10-05 ([verbatim](review-codex-battery-refine-impl-2026-10-05.md))

Codex (gpt-6-astra, xhigh), against firmware `759e265796..f4ad230326` and the
parent `ae17255..d19adc2`. **Verdict: "flash after findings 1..5".** It confirmed:
- D1's scopes are mutually exclusive, with the pass boundary right;
- C1's address map (RGB 23-30, kb 37-42, VIA from 43) and its equivalence to the
  planned last-flushed copy;
- E1/E2, the transport counters, and the protocol-8 offsets in the Python. Rust
  accepts version 8 but does not read the new pages;
- the refit as A1/A2 describe it. It reproduced both fit outputs and all three
  points files byte for byte, and judged whole-mV `pack_mv` with T = 50.56 the
  right reading of the stated figures.

It found no ≥ 25 ms path in the camera page, and E5's hardware check stands.

| # | finding (short) | disposition |
|---|---|---|
| 1 | P1: the candidate was a `-dirty` build of `b94b030bdf` | **Accepted.** After the fixes: `via-daily-4293607b4b-20261005-012019.bin`, token `0xa7adc2d1`, `dirty: false`. |
| 2 | P2: boot's settle and partial passes corrupt the first counted pass | **Accepted, verified.** `health_loop_tick` discards scope time during the settle. The pass in progress at a reset, an enable or a disable is not counted. diag_sim covers both (`4293607b4b`). |
| 3 | P2: the Python accepts another command's or page's reply | **Accepted, verified** (an `HC_LINK` reply was accepted as `HC_GET`). Every read now takes only a report answering its own command and page, discarding others until a deadline, and `HC_ACCT`'s dimensions are checked. diag_sim feeds it foreign replies first (`ba696c7`). |
| 4 | P2: a scope ≥ 349.5 ms wraps the 16-bit tick and lands in "unaccounted" | **Accepted.** A pass ≥ 340 ms is counted slow and ringed with 0xFF scopes, but kept out of the totals and winners, and counted on page 0 (`long_passes`). A scope can only wrap inside a pass that long. |
| 5 | P2: an "erase" is one whole-store erase of both 1 KB sectors | **Accepted, verified** in `wear_leveling_efl.c`. Documented, and the store size is on `HC_FLASHW` page 2. For C3's endurance, each page takes one cycle per count. |
| 6 | P2: the 10-04 baseline could pass with no numeric level; the baseline must not move with flash 2 | **Accepted.** A numeric level from 20:32 on, and 18.1% ±10 pm at 21:42. The baselines run against flash 1's `battery.c` pinned from git (`dd5c94fdd9`), and their output must equal `scripts/battery_sim/baseline-dd5c94fdd9.txt`. |
| 7 | P3: the reconstruction missed its sum by up to 3 counts | **Accepted, verified** (its 11:36 and 11:46 figures). The nudging sweeps to an exact sum, and every interval asserts count, sum, extrema and monotonicity. |
| 8 | P3: `%.0s` fed doubles | **Accepted.** Removed. |

**Verification pass** (same file, appended verbatim). Codex counted findings 2-6
and 8 resolved, and 7 partly resolved: the reconstruction still capped an
interval at 2,000 reports, and a one-report or constant interval skipped the
assertions. **Verdict: "flash".** That last P3 is fixed anyway: a cap of 4,096
that fails loudly when exceeded, and the constant case asserts its sum (`404888b`).

### Gate 7 — codex on flash 2, 2026-10-08 ([verbatim](review-codex-battery-refine-impl2-2026-10-08.md))

On `872f1f8a67` (B3 trial 1's numbers). Verdict: **"fix 3 first"**. Fixed in
firmware `c4d7b3702b` and host `c95d0a2`. Each fix has a scenario that fails
before it and passes after, and a mutant (15 of 15 caught); `run.sh` 78 ok.
The build is `via-daily-c4d7b3702b-20261008-111212.bin` (token
`0x267a2e50`), `.bss` unchanged at 30112 B.

| # | finding (short) | disposition |
|---|---|---|
| F1 | FROM-FLAT latched the estimate at the next task, which can hold a sixth report from the same burst | **Accepted, verified** (10,10,10 then 10,10,11 read UNKNOWN; 10,10,10 then 10,11,9 read FROM-FLAT). Now latched in `battery_5c_report` at exactly five. `m_flat_burst`, `m_flat_burst_above`. |
| F2 | a charge resuming after an unadopted handover started MODEL from the held display | **Accepted, verified** (MODEL at 324). Now UNKNOWN-CHG, as the plan says. `m_pause_after_unadopted`; `m_pause_after` waits for a real adoption, 150 pm off the display. |
| F3 | `K_CC` 133 with B1's VDD knee: the plan's contradiction rule is not met; codex recommends "Charge" for every session until the knee is measured. The model may read ~6-9 points low late in a long charge (not "~5"), and a slow top-up from 950 reaches OVERRUN after 1.70 h (was 4.35) | **JD chose (A), 2026-10-08 ~11:55:** ship the model at trial 1's numbers, provisional until trial 2, erring low; not "Charge" for every session. This knowingly departs from the plan's contradiction rule (B3 against B1's *assumed* 70-90%), as a measured experiment on JD's own board; the bench logger's current sensor is to locate the real knee. The "~5 points" claim is withdrawn: codex's figures stand (~6-9 points low late in a long charge if constant current continues past the VDD rise; a slow top-up from 950 reaches OVERRUN, "Charge", after 1.70 h). Gate 8 watches the OVERRUN bit. |
| 3 | 30 min of blank after unplugging an UNKNOWN or LOST session; the clamp countdown runs while the re-seat is owed | **Accepted as a known cost** for now. Re-seating an unknown level sooner is a policy change, to decide when trial 2 settles `RELAX_S`. **No change for the countdown:** the pack is discharging during `RELAX_S`, the countdown tracks it at its usual rate, and the plan does not say the display holds while owed. |
| 4 | the histogram is exact; no overflow | Agreed. |
| 5 | C2: a fresh EEPROM with an already-matching seed can propose nothing, so no first save; the integration cases are untested | **Deferred, watched in gate 8.** After a flash the period re-converges with the host attached, and a moving period proposes. Gate 8 checks for an RTC write in `HC_FLASHW` on the first day; if none comes, this is the reason. An integration case in `diag_sim` follows. |
| 6 | the camera page draws one glyph a pass; no ≥ 25 ms path | Agreed. |
| 7 | `b793644`'s changes are legitimate; `m_pause_after` called any held number adopted; `m_full_holds` no longer crossed `RELAX_S` | **Accepted, fixed** (above, with F2). `m_full_holds` now runs `RELAX_S` + 5 min and fails without FULL's relax cancel (mutant added). |
| 8 | the log's sum and count kept accepting after the first rejection, so not the promised prefix | **Accepted, verified** (65444 / 666 against 65439 / 661). Nothing accumulates after the first rejection. `m_log_saturated`. |

**Verification pass 1** (on `c4d7b3702b`, appended verbatim): F1, F2 and 7
**partly**, 8 resolved, and "fix 3 first". The three gaps, all fixed in
firmware `28f260225f` and host `91804d9`:
- **F1:** an estimate taken while the supply was unknown was never counted,
  so a later one could become the "first". The first estimate is now
  consumed whatever the supply (`m_flat_unknown_first`).
- **F2:** handover, then unplug, then a qualifying replug before the re-seat
  still started MODEL from the held number. `level_held` carries it until
  `adopt_relaxed` or FULL replaces it (`m_handover_unplug_replug`).
- **7:** `m_pause_after_unadopted`'s reports did not really stop. It now
  uses `tgt_stoppable`. A log-prefix mutant was added.

Both new scenarios fail on `c4d7b3702b`; 18 of 18 mutants are caught. The
build is `via-daily-28f260225f-20261008-112003.bin` (token `0xdf1e8b99`),
`.bss` 30112 B.

**Verification pass 2** (on `28f260225f`, appended verbatim): F1, F2, 7 and
8 all **resolved**. FROM-FLAT is not refused on a genuine USB boot (the supply
qualifies in ~0.2-0.5 s, long before five reports). **Verdict: "flash (with
F3 resolved either way)".**
