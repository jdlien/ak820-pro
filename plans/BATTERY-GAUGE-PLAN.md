# The battery gauge, and the power ladder — plan

**Status: revised 2026-09-28 after a codex review. Phase 1 is built and passes
the simulator (gate 8); not yet flashed.**
Phase 1 replaces a battery readout that currently shows a constant. Phase 2
turns the existing idle ladder into a user-visible power mode on `Fn`+`B`.

**Read first:** [`../docs/battery.md`](../docs/battery.md) — the measurements,
the hardware facts, and every finding this plan depends on. This file is the
work; that file is the evidence. ⚠️ Several claims in it have been **overturned
by measurement** and are marked as withdrawn; do not resurrect them.

Evidence: [`../history/battery-2026-09-25/`](../history/battery-2026-09-25/)
(meter readings in `readings.csv`, and the 09-28 charge log, 452 entries at
one-minute resolution). Review:
[`review-codex-battery-gauge-plan-2026-09-28.md`](review-codex-battery-gauge-plan-2026-09-28.md),
verbatim; every finding is dispositioned [at the end](#review-dispositions).

⭐ **Everything here is provisional by design.** The `5C` fit is two constants
and the level curve is a table. Better measurements — the pack tap, the
calibration run — replace them without touching the logic around them.

---

## What is established, and what it cost to learn

| fact | consequence |
|---|---|
| **VDD is a buck-boost output**, pinned at ~3.90 V. Pack fell 4.18 → 3.74 V while VDD moved +3 mV; it first sagged (~3.87 V) with the pack at 3.30 V | ⚠️ **No ADC path to the pack.** Anything derived from VDD is derived from a constant |
| **`5C` = 114.22 × V_pack − 361.04**, r² 0.99987, five settled meter points **3.30 → 3.84 V, discharge only**, every residual under half a count | ⭐ The module is a **linear voltmeter**. `V = (5C + 361.04) / 114.22` |
| The fit **extrapolates** to 100 at **4.036 V** and 0 at **3.161 V**, where the module clamps | The clamp voltages are extrapolations, not measurements |
| ⚠️ **The top clamp covers ~8-10% of runtime, not ~20%.** `5C` left 100 about 5.3 h into a ~52-63 h run at full white | The generic curve's "~20% above 4.036 V" is the curve's error, not the cell's |
| Behind a buck-boost the board draws **constant power**, not constant current. Current rises ~27% from 4.18 to 3.30 V | A timed run measures **fraction of runtime left at that load**, which is what the gauge shows |
| RGB full vs off moved the pack **10 mV**, once, near full, with pastel lighting | Suggests load barely shifts the curve; not established across the range |

⚠️ **The stock gauge was this same `5C` showing a hardcoded 100.** Everything
below beats that trivially; the bar is the *honest* version, not the working one.

### ⚠️ One claim withdrawn from the first draft of this plan

The first draft said the fit was "validated 3.16 → 4.17 V on charge *and*
discharge". **It was not.** No one measured 3.16 V: the session that fitted it
wrote "the meter says the pack is at 3.16 V" at 03:03 on 09-28, and the owner
never said so — **3.161 V is the fit's own zero point, repeated back as a
reading.** The 4.17 V point is a `5C` of 100, which is the clamp and constrains
nothing. The five real points were read out in conversation and recovered from
the session transcript into `readings.csv` on 09-28.

### What we still do not have

**This cell's own voltage→level curve.** The 09-25 discharge was interrupted by
a 20-minute charge that added an unknown few hours, the death time is known only
to a 5.7 h window, and the readings carry an unexplained 4× swing in `dV/dt`.
⚠️ **Do not fit a curve to it.** Phase 1 ships a named placeholder
([1.4](#14-the-level)) and collects its own replacement.

**Any current measurement at all.** Every figure in mA in these documents is
inferred from a guessed curve. See [Phase 2's measurement](#26-measure-before-building).

---

## Phase 1 — the gauge

⚠️ **The order below is the build order**, and it differs from the first draft:
the supply predicate first, then protection, because both are wrong today and
neither needs better calibration.

### 1.0 What goes into the first flash — and what does not

- ⚠️ **The idle ladder (`3b85686ff7`) is compiled out by default**
  (`POWER_LADDER_ENABLE`, off). A plan saying "do not flash it" does not remove
  it from HEAD. Verify on the artifact, not the source.
- **The VDD estimator (`36be68f16a`) is deleted**, not bypassed: the learned
  clamp, the load countdown, the `CAL` constants, the VDD curve. Keep VDD
  measurement, `sn32f2xx_led_load()` and `sn32f2xx_set_power_scale()` — the
  last now carries the low-battery cut.
- **Record the load conditions at the flash**: artifact name, RGB effect and
  brightness, LCD brightness (⚠️ **a flash resets it** — `flash.sh` restores
  keymap and RGB only), radio mode.

### 1.1 ⚠️ The supply predicate — everything gates on it

`battery_on_battery()` is a bare 4300 mV threshold with **no hysteresis**, and
it is wrong twice:

- **It flickers.** Observed 09-28 11:24: VDD creeping through 4300 mV as the
  charge tapered made the battery row alternate between "USB" and "4.30V".
- ⚠️ **It cannot tell "unplugged" from "charging hard."** The charge log shows
  **VDD at ~4193 mV for four hours** on USB, below the threshold, so
  `BATT_F_ON_BATTERY` and `charging` were set *simultaneously*.

**The fix is a state machine with separate questions**, not a better threshold:

| question | answered by |
|---|---|
| **supply** — what powers the rail: `UNKNOWN`, `BATTERY`, `EXTERNAL` | CHRG as positive evidence, VDD with dwell and hysteresis |
| **charging** — is the charger running | CHRG low, qualified |
| **full** | external, CHRG released and settled, **and** a fresh `5C` of 100 |
| **presence** — is there a pack | latched once the board has run from it, or charged it steadily |

Supply rules, evaluated at 10 Hz on **raw** VDD samples (the EMA's 1.6 s lag is
for display):

    CHRG low on 2 consecutive ticks       -> EXTERNAL evidence, held 1 s after
                                             the last low (covers the ~2 Hz
                                             no-pack pulse)
    VDD >= 4100 mV for 5 ticks (0.5 s)    -> EXTERNAL
    VDD <  4000 mV for 10 ticks (1 s)
        AND no EXTERNAL evidence          -> BATTERY
    otherwise                             -> keep the previous state
    boot                                  -> UNKNOWN until one of the above

⭐ **Why these numbers:** on battery VDD is the buck-boost at ~3.90 V; on USB
no raw sample went below **4119 mV** in the whole 7.5 h charge log (the lowest
one-minute minimum, at 06:59), and it is 4.47 V (BT slider) or
4.79 V (cable) when not charging. So VDD alone nearly separates the states with
a 4000/4100 band; CHRG covers the charging-hard case outright. ⚠️ The ADC's
2.0 V reference is ±2% per part, so on another unit re-check both margins.

| state | expected |
|---|---|
| unplugged, VDD ~3.90 | `BATTERY` within ~1 s |
| USB charging, VDD ~4.13-4.30 | `EXTERNAL` (CHRG) |
| CV taper through 4300 | `EXTERNAL` throughout — **no transition at 4300** |
| termination (CHRG releases) | stays `EXTERNAL` (VDD ≥ 4100) |
| USB idle/full, BT or cable slider | `EXTERNAL`, including a boot with no charging history |
| no pack, USB, CHRG pulsing | `EXTERNAL`, either slider position; presence from its own rule |
| charger fault (NTC, VIN < VBAT) | whatever VDD says actually powers the rail; never "full" by itself |
| boot before the dwell | `UNKNOWN`: no ratchet reset, no "full", no idle stage |

⚠️ `ch582_is_usb()` is the **slider's mode as software state**, not cable
detection; it is not an input. USB frame activity is corroboration at best — a
charger-only cable and a suspended host both look like "no frames".

⚠️ **Presence has a bug of its own.** `battery_is_absent()` treats "not in the
cable position" as proof of a pack, but USB powers the board in the BT position
too — so a pack-less board on USB in BT never says "No Batt". Replace that rule
with "has run from the pack this boot" (supply was `BATTERY`), latched.

### 1.2 Protection — ⚠️ the one that could matter

The warn (3.55 V) and RGB cut (3.40 V) compare against **VDD, which is pinned
at 3.90 V**, so they **never fired** on the 09-25 run, which went to the pack's
protection trip. Moved onto the pack voltage from `5C`, in the same flash:

- **Warn** "Battery low" after 30 s under **3550 mV**, once; re-arm above 3650.
- **Cut** the RGB after 30 s under **3400 mV**. Both thresholds are inside the
  fitted range (3.30-3.84 V), so they rest on measurement, not extrapolation.
- ⚠️ **A fresh `5C` of 0 on battery is "critically low", not "unknown"**: three
  fresh reports in a row cut at once, without waiting for the 30 s or a median.
- ⚠️ **The cut is a power cap** (`sn32f2xx_set_power_scale(0)`), not
  `rgb_matrix_disable_noeeprom()`, which the user's own RGB toggle undid while
  `lights_cut` stayed set. Latched until external power for 5 s. ⚠️ **Stale or
  unknown readings never clear it.**
- Thresholds stay RAM-only and settable over `HC_BATTCFG`, now in pack mV.

This is load shedding, not deep-discharge protection: it does not disconnect
the cell. The pack's own protector does that, and on 09-28 it did (0 V at the
connector by 02:59).

### 1.3 `5C`: freshness, filtering, millivolts

- ⚠️ **Fix the age wrap.** `battery_last_recv` is a `uint16_t` read with
  `timer_elapsed()`, so the age wraps every **65.5 s** — the comment says it
  saturates. A silent module looks fresh forever. → 32-bit timestamp, a
  received-report counter, **stale after 20 s** (four missed polls).
- **`5C` arrives every 5 s**, only in reply to the `A6 53` poll. A median of 30
  is 2½ minutes, not half a minute. → **median of the last 7 fresh reports**
  (~35 s), fed only on reception, never by re-reading the cached value.
  **Emptied at every supply change**: reports taken under charge current do not
  describe the pack off it, and vice versa.
- **Millivolts**, integer: `mV = (5C × 1000000 + 361040000 + 57110) / 114220`,
  for **1..99 only**. ⚠️ `5C == 100` means **≥ 4036 mV**, `5C == 0` means
  **≤ 3161 mV**: bounds, never numbers, never fed to the curve.

### 1.4 The level

⭐ **What the number means:** the fraction of runtime left at the kind of load
the board had when the curve was measured. Behind a buck-boost that is the only
thing a timed run can calibrate, and it is what a user wants to know.

**The placeholder curve** is the generic Li-ion table already in `battery.c`,
**scaled so the top clamp reads 90%** — the one anchor the 09-25 run gives
robustly (8-10% of runtime above 4.036 V, whatever the death time). ⚠️ The
textbook NMC rest-voltage table was the other candidate and the run rejects it:
it reads **~47% at 3.74 V**, where the run had **at most ~25%** of its runtime
left. Name the table in the source, call it provisional there, and replace it
after the calibration run.

**Bands:**

| where | on battery | while charging |
|---|---|---|
| `5C` fresh, 1..99 | the curve, through the ratchet | the curve on the voltage **less ~150 mV of I×R**, **only rising**, capped at **97** (shows 95) |
| `5C` = 100 (≥ 4.036 V) | **the countdown**, below | creeps toward 99 over the CV phase |
| `5C` = 0 (≤ 3.161 V) | **"Low"**, red; protection's critical path | the curve's 0, rising |
| charger released, `5C` 100 | — | **100** |
| no fresh `5C` yet | blank, bar down | "Chrg" |

⭐ **The countdown** — the owner's "convincing fudge" for the top clamp, where
the voltage says only "≥ 4.036 V": after a full charge, start at **100** and
count down with time while `5C` sits at 100, **floored at 92.5** — the lowest
value the panel still shows as 95 — so it never claims the clamp's exit (90)
early. When `5C` leaves the clamp the curve takes over
from 90; if the countdown ran slow, **ease down** onto the curve rather than
jumping. Unplugged mid-charge at the clamp, it starts from the charging value.
Booted on battery at the clamp with no history, it starts at **95** — within
five points of the truth anywhere in that band. Default rate: the 09-25 clamp
span, ~2 points an hour; it matters little, because the clamp is only ~10 points
wide.

**Smoothing, so it neither lies nor jumps:**

- the 7-report median (1.3);
- **the ratchet**: on battery the level never rises. It moves down only after
  the curve has sat below it for **six fresh medians in a row** (~30 s), and
  then only to the *highest* of those six — so one low outlier cannot drag it
  down for good. It resets once per **qualified charging session** (CHRG held
  low for a minute), never on a CHRG pulse or on `UNKNOWN`;
- **5% steps** on the panel, 1% internally. After a charge the pack relaxes
  *downward*, which the ratchet follows without a visible bounce, so there is
  **no hold-off**: the first fresh median after unplugging is shown.
- ⚠️ A reboot loses the ratchet. It reacquires from fresh reports; no
  persistence in Phase 1.

⚠️ **Charging needs its own correction** (found replaying the 09-28 log in the
simulator, below). `5C` reads the *terminal* voltage, which the charge current
lifts by I×R: uncorrected, 5C 90 two hours into that charge read as **~77%**,
where the charge time says **~40%**, and unplugging there would have dropped
the level ~35 points. So while charging the curve is read at the voltage
**less `CHARGE_IR_MV` (150 mV, provisional)**: ~0.8-0.9 A (4 h of constant
current from flat) through ~180 mΩ. And after a real charging session the level
**re-seats once**, from the first median of post-unplug reports, before the
ratchet takes over — so a wrong I×R costs one correction at unplug, not hours of
a level locked too low.

### 1.5 The display

- **Bars plus a percentage in 5% steps.** The granularity is what tells the
  user it is an estimate; 1% resolution is a claim we cannot back.
- ⚠️ **Remove the raw voltage from the battery row.** It is VDD, a constant.
  It earned its place as an *instrument* (it exposed the buck-boost) and must
  not survive as a *feature*.
- **The `Fn`+`D` debug page** carries the engineering view: raw `5C` and its
  age, the pack millivolts (or the bound), and VDD — separately, not run
  together as they are now.

### 1.6 Logging

⚠️ The first draft's change, `LOG_PERIOD_MS` → 300000 on its own, would have
broken three ways: 720 × 5 min is **60 h, shorter than the run it is for**;
`ak820battery.py` hardcodes **60 s per entry**, so the dump would read five
times too fast and multiply every `dV/dt` by five; and each entry keeps only the
**last** `5C` of its period, discarding the ~59 others.

**Log v3**, firmware and host tool in **one change**:

- **10-minute entries, 720 of them: 120 h.** RAM: 16-byte entries are 11,520 B,
  +2,880 over today, against ~9 KB of free heap.
- Per entry: VDD mean and min; **every fresh `5C` in the period** as sum,
  count, min and max; flags at the end **and** OR-ed over the period (so a
  transition cannot hide between samples); the mean effective LED drive
  (`sn32f2xx_led_load()`, which sees the power cap); the effective LCD
  backlight level; the displayed level.
- The reply carries the **format version and the period**, and the low 16 bits
  of the total entries ever written, so a dump that straddles a new entry is
  detected and retried. The host reads the period from the reply, never assumes
  it.
- ⚠️ **The log dies with the board**, so a calibration run stops at a
  meter-verified ~3.3 V and dumps **with the slider on BT** — moving it to
  `cable` resets the board. A persistent checkpoint is [deferred](#review-dispositions).

### 1.7 Withdrawn: charge-complete from VDD

The first draft inferred "done" from VDD reaching ~4470 mV. ⚠️ **Our own log
contradicts it:** in the cable position VDD reads **4530 mV while charging**
(`log.csv`, 09-26 13:24). VDD's rise through the taper is a real, qualitative
signal and stays in the log; "full" comes from 1.1's rule instead (CHRG
released and settled, with a fresh `5C` of 100), which a charger fault
mid-charge cannot satisfy.

### Phase 1 gates

1. ⚠️ **Supply correct in every row of 1.1's table**, checked against the
   charge LED, the debug page and the cable — not against itself. No flicker
   through a CV taper; plug and unplug classified within 2 s.
2. **Protection fires**: set the thresholds just above the present pack
   voltage with `ak820battery.py cfg`, see the warning and the cut; the cut
   survives a user RGB toggle and lifts after 5 s on USB. ⚠️ The pack must be
   under the top clamp (`5C` < 100): at the clamp it is only known to be
   ≥ 4036 mV, which is under no threshold.
3. The level **never rises on battery** across a multi-hour run, and never
   visibly bounces.
4. `5C` → mV agrees with a meter within **±20 mV** at three points spread
   across 3.3-3.9 V.
5. The battery row shows the level, never VDD.
6. A v3 dump reconstructs timestamps at 10-minute spacing, and a ≥ 24 h run
   dumps intact.
7. **The ladder is absent from the artifact.**
8. ⭐ **`scripts/battery_sim/run.sh` passes.** It compiles the firmware's own
   `battery.c` and `power.c` on the host against a simulated board and runs 23
   scenarios: the 09-28 charge log, a 57.7 h discharge with jitter, every supply
   transition, a pack-less board, the protection, the re-seat, and one per
   defect the implementation review found. **Fifteen deliberately broken
   variants are each caught** — the old 4300 mV predicate, a ratchet that
   rises, protection on VDD, charging reaching 100, and one reverting each
   review fix. ⚠️ It does not compile `indicators.c` or `display.c`: presence
   and the panel are checked by reading, and on hardware.

---

## The calibration run — after Phase 1, once the pack tap is wired

Not a Phase 1 gate: the firmware stands on the provisional constants. When the
pack tap (ADS1115 or MAX17048 on the 1.25 mm extension, `docs/battery.md`) can
log the pack continuously:

- **One supervised run at fixed settings**, from a terminated charge to a
  **meter-verified 3.30 V**. ⚠️ **Never run it into the pack's protector** on
  purpose: that endpoint is not "empty", and the 09-24 shutdown shows the board
  can lose power for reasons we have not explained.
- ⚠️ **The RGB cut fires at 3.40 V**, which changes the load before 3.30 V.
  Either lower it for the run with `ak820battery.py cfg` (RAM-only, gone at the
  next reboot) or run with RGB off throughout. Decide before starting.
- The tap refits `5C` → mV across the whole range, charging included, and the
  log gives time; together they give this cell's runtime curve.
- **Validate the fitted table on a second run**, not on the run it came from.
- Characterize post-charge relaxation there too: tap readings at 0/5/15/30/60/
  120 min after unplugging from a few starting levels settle how optimistic the
  first minutes after a charge are.
- **Measure `CHARGE_IR_MV`**: the step in the pack voltage at the instant of
  unplugging mid-charge, at a few points of the constant-current phase.

---

## Phase 2 — the power ladder, on `Fn`+`B`

### What exists

`3b85686ff7` (committed, **compiled out** as of Phase 1): **on battery only**,
RGB to a quarter after 1 min idle, RGB off and the screen capped at level 4 of
23 after 5 min, backlight off after 15 min. Any key or knob restores within
0.1 s and the key types normally. **Each stage is a cap below the user's
settings, never a change to them** — keep that property.

### The proposal

⚠️ **The stages are not equally cheap to reverse, and that — not the clock —
should set the timings:**

| stage | cost of being wrong | so it can be |
|---|---|---|
| **RGB off** | none. Instant, no lost input | **aggressive** |
| **Screen off** | you lose the clock at a glance | **moderate** |
| **Radio down** | reconnect latency, possibly a lost keystroke | **very conservative** |
| **Deep sleep** | needs a wake path that does not exist yet | **blocked** |

⚠️ **Which stage *pays* is unknown** ([2.6](#26-measure-before-building)); the
table above is about cost only.

`Fn`+`B` cycles three modes, shown on the LCD:

| | **Full Power** | **Normal** (default) | **Power Saver** |
|---|---|---|---|
| RGB → 25% | never | **1 min** | 30 s |
| RGB off | never | **5 min** | 2 min |
| screen dim/capped | never | **5 min** | 2 min |
| screen backlight off | never | **15 min** | 5 min |
| deep sleep | never | 30 min ⚠️ | 10 min ⚠️ |
| radio down | never | **never** | 30 min ⚠️ |

⭐ **Normal is the ladder that already exists**, plus deep sleep when its wake
path lands. Power Saver is the same shape, roughly 3× tighter.

⚠️ **Normal never touches the radio.** It appears only in Power Saver, because
choosing Power Saver is the consent to reconnect latency.

⚠️ **On USB every mode behaves as Full Power.**

**Low battery:** below ~15% the firmware **caps the lighting** — RGB and screen
as Power Saver would — regardless of the selected mode, and says so on the
display. ⚠️ **Lighting only.** The first draft forced the whole of Power Saver,
radio included, and then justified long reconnects with "the mode is the
consent"; an automatic switch is not consent. Radio and deep sleep stay behind
the user's explicit choice.

### ⚠️ Design questions that need answering before building

1. **The radio.** Powering down the CH582F drops the BT link, and reconnect is
   not instant. ⚠️ **The CH582F transmit queue is not a wake buffer**: when
   nearly full it deliberately merges keyboard states (`ch582f_ajazz.c:538`),
   which is right for a stalled link and loses edges a wake buffer must keep.
   A radio stage needs its own contract: every press, release, modifier and
   knob event buffered through the reconnect, a bounded buffer with a defined
   overflow, and a defined failure when the host never returns. Tested with
   taps, bursts, held modifiers, an absent host and repeated sleep/wake.
2. **Deep sleep needs its own wake path.** Key scanning lives in the row ISR,
   so stopping it stops scanning (`docs/battery.md`, task 8.4; task 9 for making
   that ISR cheaper). Do not schedule deep sleep before that path exists.
3. **Persistence.** The mode belongs in the emulated EEPROM beside BT slot and
   LCD brightness. ⚠️ **A flash erases it** — `flash.sh` restores keymap and
   RGB, not this. Default must be sane (**Normal**).
4. **The keycode.** ⚠️ `ak820pro_keycodes` is **index-matched to via.json's
   `customKeycodes[]` and is APPEND ONLY** (`scripts/check_via_sync.py`).
5. **The mode display.** A transient overlay, as `Fn`+`C` does for clock format.
   ⚠️ A full-screen `lcd_clear_rect()` blocks ~43 ms and drawing is one LCD op
   per glyph — use the glyph queue and bands (`docs/display.md`).
6. **Reconnect latency sets whether the radio stage exists at all**:

   | reconnect | Power Saver (chosen) |
   |---|---|
   | < 5 s | fine |
   | > 5 s | **fine — the mode is the consent** |

   ⚠️ **But a delay is not the same as a loss.** At any depth the keystroke that
   wakes the board **must still be typed** (question 1).

   Reference: a NuPhy Air beside this desk takes ~15 s and is called "very
   annoying" — but it reaches that depth *by default*, with no mode chosen.

### 2.6 Measure before building

⚠️ **We do not know what draws the power, and the ladder assumes we do.** RGB
full versus off moved the pack **10 mV** once; through a pack resistance
anywhere from 60 to 330 mΩ (a comparable 606090 pack is specified at 60 mΩ
cell, 180 mΩ with its protection board) that is **30 to 170 mA** — the
measurement cannot choose. And the LEDs dark do not stop the row ISR's 72.8% of
the CPU, so "RGB off" saves the LED current only.

⚠️ **"A few hours of RGB off from Phase 1's log" cannot settle it.** A 3-hour
block falls 3-5 `5C` counts; a 20% saving changes that by **less than one
count**. It would take **10-16 hours per condition**, alternated (ABBA) over
days.

⭐ **Measure the current directly instead.** The 1.25 mm extension already
bought for the pack tap puts a meter **in series with the pack's + lead** in
minutes: RGB full / off, screen full / dim / off, BT linked / idle, each read in
turn at a fixed pack voltage. That answers in an afternoon what the log would
take a week to hint at. ⚠️ The MAX17048 measures voltage, not current; it does
not answer this.

A reference point: a NuPhy Air gets **weeks** with LEDs on. It has no screen,
and a single-chip nRF52840 rather than our SN32 + CH582F. Some of our gap is
architectural; some may be the screen, which is fixable.

### Phase 2 gates

1. Each mode's stages fire at the stated times, **on battery only**.
2. ⚠️ **No keystroke is ever lost** on wake, from any stage, including radio
   idle-down.
3. Stages remain **caps**, never writes to the user's settings.
4. The mode survives a reboot; a flash resets it to Normal and says so.
5. ⭐ **A measured runtime improvement** against a **matched baseline run** at
   the same settings — not the 09-25 run, which was interrupted and mixed two
   lighting setups. If Normal is not measurably better, it is complexity for
   nothing.

---

## Order of work

1. ✅ **1.0-1.3**: ladder compiled out, estimator deleted, the supply state
   machine, protection on the pack voltage, `5C` freshness
2. ✅ **1.4-1.6**: the level, the display, log v3 with the host tool, and the
   simulator (gate 8)
3. Flash, then bench-check every row of 1.1's table and the protection with
   the owner (gates 1-7)
4. **2.6's measurement** — a meter in series, when the extension cables arrive
5. The **calibration run**, once the pack tap logs; swap the constants and the
   table
6. Phase 2's lighting modes; radio and deep sleep each behind its own gate

⚠️ **Do not flash the idle ladder during a calibration run** — it changes the
load profile mid-measurement.

---

## What this plan deliberately does not do

- **No MAX17048 retrofit in the firmware yet.** It is a refinement (±1-2% vs
  ±5%), not an enabler. As a **bench instrument** on the pack tap it is exactly
  what the calibration run needs.
- **No software coulomb counting.** Superseded by the voltage route.
- **No claim of ±5%.** The error budget in `docs/battery.md` is a target until
  a second run checks the table against data it was not fitted to.

---

## Review dispositions

Codex (gpt-6-astra, xhigh), 2026-09-28, against the first draft at `5eebd43`.

| # | finding | disposition |
|---|---|---|
| 1 | **P0** Protection stays on VDD | **Accepted.** 1.2: pack voltage, `5C == 0` as critical, a power cap that a user toggle cannot undo, stale never clears it |
| 2 | Supply predicate needs a state machine and separate presence | **Accepted.** 1.1, codex's 4100/4000 band and dwells, backed by the log's 4119 mV worst raw sample on USB; the presence bug fixed |
| 3 | `5C` age wraps; median of 30 is 2.5 min | **Accepted, verified in the code.** 1.3 |
| 4 | The 114.2 fit has no committed provenance | **Accepted, and resolved differently than expected**: the five points were recovered from the session transcript into `readings.csv`; the refit reproduces 114.22 / −361.04 exactly. The "3.16 V on charge" validation was **never measured** and is withdrawn |
| 5 | Post-charge "memory" unproven; hold-off needs redesign | **Accepted in diagnosis, modified in remedy.** The owner confirms `5C` snaps to 100 only from a mostly-charged pack — the CV voltage above the clamp — and climbs from a flat one: terminal voltage both times. No "--" hold-off: relaxation runs downward, and the ratchet follows it (1.4). Relaxation is characterized in the calibration run |
| 6 | Charge-complete from VDD mislabels cable-mode charging | **Accepted.** 1.7; "full" needs CHRG released **and** `5C` at 100 |
| 7 | "Full" at the clamp misleads; the ratchet can lock in an error | **Modified.** The owner rejected "High": the clamp gets the countdown (1.4). The ratchet steps down only on sustained evidence. No ±5% claim |
| 8 | A log period change silently corrupts the host's timestamps | **Accepted, verified** (`* 60` in `ak820battery.py`). 1.6: version and period in the reply, host and firmware in one change, wrap detection |
| 9 | 60 h is shorter than the run; last-value logging discards the signal | **Accepted.** 120 h at 10 min, `5C` as sum/count/min/max, effective load logged |
| 10 | The first flash is not specified; the cut changes the calibration load | **Accepted.** 1.0 compiles the ladder out and deletes the estimator; the calibration run decides the cut before it starts |
| 11 | A timed run measures runtime, not charge; the protector is not "empty" | **Accepted.** The level is defined as runtime fraction; the run stops at a meter-verified 3.30 V |
| 12 | Phase 2's load inference is underdetermined; "a few hours" cannot resolve it | **Accepted, with a cheaper remedy**: a meter in series through the extension cable, rather than 10-16 h ABBA blocks |
| 13 | Automatic Power Saver contradicts the radio consent; the TX queue is not lossless | **Accepted.** Low battery caps lighting only; the radio stage gets a wake-buffer contract |
| 14 | A persistent checkpoint is possible but not free | **Deferred.** Worth it for the next unexplained shutdown, not for Phase 1 |

## Implementation review dispositions

Codex (gpt-6-astra, xhigh), 2026-09-28, against `b8b64162af` + `8627554513`:
[verbatim](review-codex-battery-gauge-impl-2026-09-28.md). Verdict: flash after
findings 1-8. It could not run the simulator (its sandbox refused `mktemp`), so
its findings are code traces; each was re-checked against the code, and each
fix has a simulator scenario and a mutant that reverts it.

| # | finding | disposition |
|---|---|---|
| 1 | Failed ADC reads leave `ext_run` qualified, so a remembered EXTERNAL lifts the cut after unplugging | **Accepted.** VDD evidence expires after 1 s of failed conversions; the cut lifts only on 5 s of *fresh* evidence (CHRG, or VDD this second). `restore_needs_evidence` |
| 2 | The median survives a charger-only change: a fault mid-CV was judged FULL on charging reports, and a CHRG gap reinterpreted a charging median without the I×R | **Accepted.** The median restarts at every charger start/stop too; FULL needs post-release reports. `charger_fault`, `chrg_gap` |
| 3 | Charging neither caps an existing level nor bounds its upward steps | **Split.** Upward moves are now at most 1% per report (`boot_charging_rise`; `charge_log` asserts single steps). **Declined:** pulling a remembered FULL down to the cap during a top-up. A level ≥ 97.5% exists only within ~80 min of a FULL; the pack *is* full, and 100 → 95 → 100 across a top-up would read as a glitch. `full_then_replug` pins the choice |
| 4 | A brief replug cancels the owed re-seat | **Accepted.** Owed until consumed. `reseat_survives_replug` |
| 5 | Three zeroes cut the RGB but the level walks down for ~45 min; "Low" is not red | **Accepted.** Critical sets the level to 0 at once; "Low" keeps a red 2 px sliver in the bar (the glyphs cannot be recoloured). `critical` |
| 6 | Two reports between ticks count as one | **Accepted.** The CH582F parser now calls `battery_5c_report()` per frame; the polled counter is gone from the gauge. `burst` |
| 7 | A period stretched over an ADC outage misdates the log; the first entry came instantly at boot (`\| 1`) | **Accepted, both.** Every period closes on a fixed cadence (VDD 0 when there was no conversion); a started flag replaces the `\| 1`. `log_cadence` |
| 8 | One stray 0 says "No Batt", and the bar is not repainted when presence returns | **Accepted.** Absence is judged on the fresh median; presence returning repaints the bar. ⚠️ Not simulated: check on the white unit |
| 9 | The countdown floor (910) shows 90, the exit's value | **Accepted.** 925: the clamp reads 100, then 95 |
| 10 | A threshold above 4036 compares against the clamp's bound | **Accepted.** No threshold comparison at the top clamp. `threshold_at_clamp` |
| 11 | The debug row has no age | **Accepted.** `59@4 3677 3901`: 5C, seconds since it arrived, pack mV, VDD mV |

**Not added from its scenario list:** an EOC timeout distinct from a zero
conversion, report phases varied around transitions, log-ring wrap, and host
packet fixtures for v1/v2/v3 (codex decoded synthetic packets through the
reader and found every offset right).
