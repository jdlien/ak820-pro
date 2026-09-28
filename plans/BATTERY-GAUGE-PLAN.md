# The battery gauge, and the power ladder — plan

**Status: drafted 2026-09-28, nothing built.** Phase 1 replaces a battery
readout that currently shows a constant. Phase 2 turns the existing idle ladder
into a user-visible power mode on `Fn`+`B`.

**Read first:** [`../docs/battery.md`](../docs/battery.md) — the measurements,
the hardware facts, and every finding this plan depends on. This file is the
work; that file is the evidence. ⚠️ Four claims in it have been **overturned by
measurement** and are marked as withdrawn; do not resurrect them.

Evidence: [`../history/battery-2026-09-25/`](../history/battery-2026-09-25/)
(readings + the 09-28 charge log, 452 entries at one-minute resolution).

---

## What is established, and what it cost to learn

| fact | consequence |
|---|---|
| **VDD is a buck-boost output**, pinned at ~3.90 V. Pack fell 4.18 → 3.74 V while VDD moved +3 mV | ⚠️ **No ADC path to the pack.** Anything derived from VDD is derived from a constant |
| **`5C` = 114.2 × V_pack − 361.0**, r² 0.99987, validated 3.16 → 4.17 V on charge *and* discharge | ⭐ The module is a **linear voltmeter**. `V = (5C + 361.0) / 114.2`, ±3 mV |
| The map **clamps**: 100 above **4.036 V**, 0 below **3.161 V** | Display read 100% for the last **3.5 h of charging** and the first ~20% of discharge |
| Logged jitter is **±1 count**, not the ±3 the debug page suggests | A short median filter is enough |
| RGB full vs off moves the pack **10 mV** | One curve covers every load state — unusual, and it makes voltage gauging viable here |

⚠️ **The stock gauge was this same `5C` showing a hardcoded 100.** Everything
below beats that trivially; the bar is the *honest* version, not the working one.

### What we still do not have

**This cell's own voltage→SoC curve.** The 09-25 discharge was interrupted by a
20-minute charge, the death time is known only to ±5.7 h, and the readings carry
an unexplained 4× swing in `dV/dt` across two supposedly identical intervals.
⚠️ **Do not fit a curve to it** — it would bake an unexplained inconsistency
into the firmware.

**This does not block Phase 1.** A generic NMC curve on accurate voltage lands
inside the objective, and the curve is a **table swap** later.

⭐ **And Phase 1 collects its own replacement.** Once the firmware converts `5C`
to millivolts and logs it, one ordinary flat run yields voltage-vs-time at
one-minute resolution — the data this plan could not reconstruct by hand.

---

## Phase 1 — the gauge

### 1.1 `5C` → millivolts

`V_mv = (5C × 1000 + 361000) / 114.2`, integer-only. Source is
`ch582_get_battery()` (`graphics/display.c:878` already reads it).

⚠️ **Honour the clamps.** `5C == 100` means "**≥ 4.036 V**, unknown"; `5C == 0`
means "**≤ 3.161 V**, unknown". Never convert those to a number and never feed
them to the curve.

### 1.2 Filter and ratchet

- **Median** over ~30 samples. Jitter is ±1 count logged, so this is cheap and
  takes ±25 mV to ±5 mV.
- **Ratchet**: the displayed level never rises while on battery. Charge only
  decreases while discharging, so clamping discards noise, not information.
  Reset on charge.
- ⚠️ **Hold off after charging.** `5C` snaps to 100 the instant USB appears and
  decays over *hours*; a post-charge reading is meaningless. Ignore it until
  some time after the charger is gone.

### 1.3 ⚠️ Fix `battery_on_battery()` — this gates everything else

`battery.c:84,136` is a bare threshold at `ON_USB_MIN_MV 4300` with **no
hysteresis**, and it is wrong twice:

- **It flickers.** Observed live 09-28: VDD creeping through 4300 mV as the
  charge tapered made the battery row alternate between "USB" and the voltage.
- ⚠️ **It cannot tell "unplugged" from "charging hard."** The charge log shows
  **VDD at 4193 mV for four hours** while on USB — below the threshold, so
  `BATT_F_ON_BATTERY` and `charging` were set *simultaneously*.

**Fix — prefer the direct observation:**

    CHRG low                                    -> on USB (charging)
    CHRG high AND VDD >= 4300 (with hysteresis)  -> on USB (idle/full)
    otherwise                                    -> on battery

VDD then only arbitrates the case CHRG cannot, which is the case where VDD is
trustworthy (no charge current, no diode drop).

⚠️ The ratchet and the whole of Phase 2 gate on this predicate. A version that
is wrong for hours breaks both.

### 1.4 The display

- **Bars, plus a percentage in 5% steps.** The granularity is what tells the
  user it is an estimate; 1% resolution is a claim we cannot back.
- ⚠️ **"Full" and "Low" at the clamps, never a number.** Above 4.036 V we know
  only "≥"; a frozen `100%` is the lie the stock firmware told.
- ⚠️ **Remove the raw voltage from the battery row.** It currently shows VDD,
  which is a constant — no more informative than the hardcoded 100 it replaced.
  It earned its place as an *instrument* (it is what exposed the buck-boost) and
  must not survive as a *feature*.
- Volts stay on the `Fn`+`D` debug page, where an engineer wants them.

### 1.5 Logging

**`LOG_PERIOD_MS` 60000 → 300000.** `LOG_LEN` is 720, so one-minute entries wrap
at **12 h**; five-minute entries give **60 h**. ⚠️ Two multi-day runs have
already lost their logs to this.

⚠️ **The log dies with the board**, so a discharge-to-death run can never
preserve its own final hours. A calibration run stops at ~3.3 V and dumps **with
the slider on BT** — moving it to `cable` resets the board.

### 1.6 Free win: charge-complete from VDD

`DONE` never asserts (confirmed across 7.5 h). `CHRG` does work but took **9½ h**
to clear, with the display reading full for the last 5½. VDD is the live signal:

| VDD | meaning |
|---|---|
| ~4193 mV, flat | constant-current, full charge current |
| rising | CV phase, current tapering |
| ~4470 mV | no charge current — **done** |

A diode's drop is logarithmic in current, ~50 mV per e-fold, so the +75 mV
measured on 09-28 is a 4-5× fall in current.

### Phase 1 gates

1. ⚠️ **`battery_on_battery()` correct in all four states**: unplugged; USB
   charging hard; USB idle/full; no pack. Verify against the charger pin and a
   meter, not against itself.
2. The reading **never rises on battery** across a multi-hour run.
3. "Full" shows above 4.036 V, "Low" below 3.161 V, a number only between.
4. `5C` → mV agrees with a meter within **±20 mV** at three widely spaced points.
5. The board is **not left on a stale VDD readout** — the battery row shows the
   pack.
6. 60 h of log survives a reboot-free run.

---

## Phase 2 — the power ladder, on `Fn`+`B`

### What exists

`3b85686ff7` (committed, **not flashed**): **on battery only**, RGB to a quarter
after 1 min idle, RGB off and the screen capped at level 4 of 23 after 5 min,
backlight off after 15 min. Any key or knob restores within 0.1 s and the key
types normally. **Each stage is a cap below the user's settings, never a change
to them** — keep that property.

### The proposal

⚠️ **The three stages are not equally cheap to reverse, and that — not the
clock — should set the timings:**

| stage | cost of being wrong | so it can be |
|---|---|---|
| **RGB off** | none. Instant, no lost input | **aggressive** |
| **Screen off** | you lose the clock at a glance | **moderate** |
| **Radio down** | reconnect latency, possibly a lost keystroke | **very conservative** |
| **Deep sleep** | needs a wake path that does not exist yet | **blocked** |

RGB is also the *dominant* load, so the aggressive stage is the one that pays.
Dimming before extinguishing matters: a step to 25% is barely noticeable in
peripheral vision, and it removes ~75% of the load a minute in.

`Fn`+`B` cycles three modes, shown on the LCD:

| | **Full Power** | **Normal** (default) | **Power Saver** |
|---|---|---|---|
| RGB → 25% | never | **1 min** | 30 s |
| RGB off | never | **5 min** | 2 min |
| screen dim/capped | never | **5 min** | 2 min |
| screen backlight off | never | **15 min** | 5 min |
| deep sleep | never | 30 min ⚠️ | 10 min ⚠️ |
| radio down | never | **never** | 30 min ⚠️ |

⭐ **Normal is the ladder that already exists** (`3b85686ff7`: 1 min / 5 min /
15 min), plus deep sleep when its wake path lands. That is deliberate — those
values were chosen with care and match what the stage costs. Power Saver is the
same shape, roughly 3× tighter.

⚠️ **Normal does not touch the radio at all.** Dropping BT to save power and
then eating the first keystroke of the sentence someone came back to type is a
bad trade at any battery level. It appears only in Power Saver, and only if
[design question 1](#-design-questions-that-need-answering-before-building)
comes back favourably.

⚠️ **On USB every mode behaves as Full Power.** The existing ladder is already
battery-only; keep it.

**One behaviour worth adding, and it is standard practice:** below ~15% the
firmware **forces Power Saver regardless of the selected mode**, and says so on
the display. A device that quietly burns its last 15% on RGB because someone
picked Full Power a month ago is not being respectful of the choice — it is
being literal about it. ⚠️ Needs Phase 1's gauge to be trustworthy first, which
is another reason this is Phase 2.

### ⚠️ Design questions that need answering before building

1. **The radio is the hard one.** Powering down the CH582F drops the BT link,
   and reconnect is not instant. **The first keystroke after wake must not be
   lost** — either buffer it or do not idle the radio at all in Normal. Measure
   reconnect latency before choosing. The CH582F pending-action machinery
   (`docs/wireless.md`) is where this lives.
2. **Deep sleep needs its own wake path.** Key scanning lives in the row ISR, so
   stopping it stops scanning (`docs/battery.md`, task 8.4; task 9 for making
   that ISR cheaper). Do not schedule deep sleep before that path exists.
3. **Persistence.** The mode belongs in the emulated EEPROM beside BT slot and
   LCD brightness. ⚠️ **A flash erases it** — `flash.sh` restores keymap and
   RGB, not this. Default must be sane (**Normal**).
4. **The keycode.** ⚠️ `ak820pro_keycodes` is **index-matched to via.json's
   `customKeycodes[]` and is APPEND ONLY** — inserting shifts every later
   keycode and corrupts existing VIA keymaps (`scripts/check_via_sync.py`
   guards this).
5. **The mode display.** A transient overlay, as `Fn`+`C` does for clock format.
   ⚠️ A full-screen `lcd_clear_rect()` blocks ~43 ms and drawing is one LCD op
   per glyph — use the glyph queue and bands (`docs/display.md`).
6. ⚠️ **We do not know what draws the power, and the ladder assumes we do.**
   The design above rests on RGB dominating. `docs/battery.md` records that
   **RGB full versus off moves the pack 10 mV** — through a plausible internal
   resistance that is roughly 30-100 mA, against an average of ~62 mA for the
   whole 62-67 h run. **Those do not reconcile.** The LCD backlight and an MCU
   at 72.8% duty are both unaccounted for.

   ⭐ **The test is free and comes first.** Run on battery with **RGB off** for
   a few hours and compare `dV/dt` against the RGB-on rate at a similar
   voltage; Phase 1's log records both with no meter and no discipline. If the
   rate barely changes, the aggressive stage is the wrong one and **the screen
   should be aggressive instead.**

   A reference point: a NuPhy Air gets **weeks** with LEDs on. It has no
   screen, and a single-chip nRF52840 rather than our SN32 + CH582F with an LED
   ISR burning 72.8% of the CPU. Some of our gap is architectural and
   unfixable; some may be the screen, which is fixable.

7. **Reconnect latency sets whether the radio stage exists at all.** Measure it
   before designing around it:

   | reconnect | verdict |
   |---|---|
   | < 500 ms | imperceptible — fine anywhere |
   | 0.5-2 s | acceptable only after long idle |
   | 2-5 s | Power Saver only, after >= 30 min |
   | **> 5 s** | **never**, at any timeout |

   ⚠️ **The cost is the surprise, not the duration.** A NuPhy Air beside this
   desk takes ~15 s and is reported as "very annoying" despite only reaching
   that depth after hours — because it is hit precisely when someone has sat
   down to start typing.

### Phase 2 gates

1. Each mode's stages fire at the stated times, **on battery only**.
2. ⚠️ **No keystroke is ever lost** on wake, from any stage, including radio
   idle-down.
3. Stages remain **caps**, never writes to the user's settings.
4. The mode survives a reboot; a flash resets it to Normal and says so.
5. ⭐ **A measured runtime improvement**, from the Phase 1 log: a full run in
   Normal against the 62-67 h baseline at full white. If it is not measurably
   better, the feature is complexity for nothing.

---

## Order of work

1. **Phase 1.3** (`battery_on_battery()`) — everything gates on it
2. **Phase 1.1/1.2/1.4** — the gauge and display
3. **Phase 1.5** (`LOG_PERIOD_MS`) — in the same flash
4. Run the keyboard flat once, dump the log, **fit this cell's curve**, swap the
   table
5. **Phase 2.6 measurement** before any of Phase 2's build
6. Phase 2

⚠️ **Do not flash the idle ladder during a calibration run** — it changes the
load profile mid-measurement.

---

## What this plan deliberately does not do

- **No MAX17048 retrofit.** It is a refinement (±1-2% vs ±5%), not an enabler,
  and `docs/battery.md` has the full plan if it is ever wanted. The board's
  existing I²C bus makes it tractable; it is still a modification to a keyboard
  in daily use.
- **No software coulomb counting.** Superseded by the voltage route, which needs
  no extra hardware and does not drift with an unmeasured load model.
- **No attempt at 1% accuracy.** The clamps make the top and bottom of the range
  structurally unknowable from this signal. ±5% with honest edges is the target.
