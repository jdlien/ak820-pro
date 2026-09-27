# The battery: what the board can know, and how the level is estimated

Code: `battery.c` (VDD measurement, estimator, protection, log), `power.c`
(idle ladder), `indicators.c` (charger pins, pack presence), and the battery
row in `graphics/display.c`. Host tool: `hostagent/ak820battery.py`. Task 8 in
`.taskmaster/tasks/tasks.json` tracks the work.

> **State (2026-09-25):** flashed on JD's unit is `b35d8672b3`: it measures
> VDD, logs once a minute, cuts the RGB at low VDD, and shows the voltage on
> the battery row. Committed but **not flashed**: the level estimator
> (`36be68f16a`) and the idle ladder (`3b85686ff7`), waiting on the discharge
> described below to calibrate them.

## What is achievable, and what is not (2026-09-26)

⚠️ **Read this before working on the estimator.** The obvious goal — a
trustworthy percentage — is **not reachable on this hardware**, and the reasons
are structural rather than a matter of effort:

- **No ADC path to the pack.** Every `AIN` pin is a matrix column, an RGB row or
  the Win Lock LED, and VDD is a **buck-boost output pinned at 3.90 V** (above).
  The pack fell 4.18 → 3.84 V while VDD moved 1 mV.
- **The only signal is the module's `5C`,** which is itself voltage-derived.
- **NMC's curve is flat through the middle.** Roughly 3.9 → 3.6 V holds about
  half the capacity in 0.3 V. At `5C`'s measured ~47 points per volt that is
  ~14 points spanning half the pack, with ±3 of noise on top. **No filtering
  recovers a percentage worth printing mid-range.** This is why phones
  coulomb-count instead, and it is not a defect in our approach.

**The realistic objective, and what this work should aim at:**

- a **5-bar or 10%-granularity** indicator that **never goes backwards** while
  discharging;
- roughly ±10% mid-range, **better near the ends** where the curve is steep and
  where it actually matters;
- a **low-battery warning that fires**, which ⚠️ today's VDD thresholds may not
  (above).

That is a good keyboard battery indicator. It is not a good laptop one, and no
amount of work on this hardware will make it one. ⚠️ **Note also that the stock
firmware's gauge was this same `5C` value showing a hardcoded 100** — anything
that moves already beats what the board shipped with.

### The route that does not depend on voltage

The log already records `led_pm` (mean LED drive per mille) and `rgb_val`, and
the RGB is the dominant load. So the firmware can **estimate current from what
it knows it is driving** and integrate it — a coulomb count in software, with no
extra hardware:

    level = charge_at_last_full − ∫ f(rgb_val, led_pm, …) dt

anchored by `5C` at the ends where it is informative, and reset on charge. That
is monotonic and smooth, and it does not collapse in the plateau because it is
not reading voltage there at all.

⚠️ **This is what the INA228 tap is really for** (see the connector section): not
just ground truth for a curve, but measuring actual milliamps against LED drive,
effect, brightness and BT state so `f()` can be fitted. Honest about the cost:
the model drifts with pack ageing and temperature, so it needs the `5C` anchor
to stay honest, and it is a few evenings rather than an afternoon.

## Why this was hard

Every obvious source turned out to be wrong or absent:

- **The CH582F's percentage (`5C`) is not a level** — ⚠️ **but see the
  2026-09-26 observation below, which contradicts the strongest form of this.**
  It read 100 through a full-brightness discharge, and 100 while recharging a
  pack we then believed flat. It does sense the pack: a board with no pack
  fitted reads 0 (`indicators.c`). The **stock firmware's gauge was this
  number**: none of the nine stock SN32F290 images in `fpb/ajazz-ak820-pro`
  (AK820 Pro v1.13, v1.14, and seven sibling boards) references the ADC,
  comparator or op-amp base addresses.

  > ⭐ **2026-09-26: `5C` moved. It is not pinned at 100.** Near the end of the
  > 09-25 discharge the owner read **~85%** on the `Fn`+`D` debug page, row 8,
  > which renders `ch582_get_battery()` directly (`display.c:878`). The pack was
  > at ~3.99–4.00 V. It **snapped to 100 the instant USB was connected**, and a
  > post-reset `HC_CONN` read on USB gave 100 with a minimum of 99 since boot.
  >
  > So the sentence "across the whole range we have observed it only ever says
  > 100" is **withdrawn**. What the evidence now supports is narrower and more
  > useful: `5C` tracks *something*, coarsely and slowly, and it is **useless
  > while charging** — it reports charger state, not charge.
  >
  > ⚠️ **Do not yet treat this as a gauge.** It is one reading, recalled
  > approximately, with no trajectory behind it: the `module_pct` column of the
  > once-a-minute RAM log would have shown the whole curve against the pack, and
  > that log was lost when the slider went to `cable` at 13:22. 85% at 3.99 V is
  > also optimistic for NMC — nearer 65–75% on the standard curve — so if it is
  > a level it is a badly calibrated one. **The next discharge must capture
  > `module_pct` over the whole run**, which the log already records; it only
  > needs to survive to be dumped.
  >
  > If `5C` does track the pack, it is a gauge reachable with no ADC work at
  > all, which is the thing this document spent its length establishing was
  > absent. That is worth an hour of deliberate testing before more estimator
  > calibration.
  >
  > ⭐ **2026-09-26, later: it does track, and it is now the ONLY signal** (see
  > the buck-boost note above). Settled pairs, excluding the post-charge
  > artifact: **3.99 V → 85** and **3.84 V → 78**, about **47 points per volt**,
  > consistent and correctly signed. Over the same excursion VDD moved 1 mV.
  > The post-charge memory is real but transient: 97 at 14:03 after ~20 min on
  > the charger had decayed to 78 by evening. So the gauge is a filtered,
  > ratcheted, remapped `5C` — discarded for some hours after any charge.
- **No analogue pin can see the pack.** AIN0..AIN15 are P2.0..P2.15, all
  matrix columns, RGB rows or the Win Lock LED. The op-amp and comparator
  inputs are RGB rows (B4, B5, A11), the flash's WP (B2), the encoder (A10)
  and the BOOT pin (B3). There is nowhere to wire a divider, even by hand.
- **The SN32's own supply is regulated on battery** (below), so the one
  voltage it can measure is flat for the top fifth or so of the charge.
- **The charger's DONE pin never reads low**, even when charging clearly
  finished (see "The charger"), so "full" has to be inferred.

## Hardware facts

**The pack** (JD's unit, printed on the cell): `JKJ606090 4000mAh 72.9g,
3.7V 14.8Wh`, date code `202512.30`, Shenzhen Jiekejie. Chemistry
Li/Ni/Co/Mn with a graphite anode: **NMC**, so the standard NMC
voltage-to-level curve applies. The other unit (the white one) had no pack
fitted as of 2026-09-09.

**The slider is labelled POWER on the PCB.** It selects the power source as
well as the mode (docs/hardware.md): BT → cable reboots the MCU.

**VDD by power state** (the SN32 measuring itself, `battery.c`):

| state | VDD | meaning |
|---|---|---|
| cable position, USB in | 4.79 V | USB, through a low-drop path |
| BT position, USB in | 4.47 V (4.31 V while charging hard) | USB through a diode; the pack is not on VDD |
| BT position, unplugged | **3.90 V, flat** | a regulator's output, fed from the pack |

The regulator: with a meter at the pack connector, the pack read 4.18 V at
rest (4.17 V with the RGB at full) while VDD read 3.90 V, and over the
following nine hours the pack fell 4.17 → 4.01 V while VDD **never left 3.90
V** (full table below).

> ⚠️ **2026-09-26: it is a BUCK-BOOST, and there is no dropout to wait for.**
> An earlier version of this paragraph predicted "VDD will follow the pack, a
> dropout below it, once the pack gets down to around 3.95-4.0 V". **Falsified.**
> With the pack at **3.84 V** the debug page read **VDD 3.901 V** — VDD *above*
> its own input, which no linear regulator can do. Across the whole excursion so
> far the pack fell **4.18 → 3.84 V (−340 mV)** while VDD moved **+1 mV**.
>
> **VDD is therefore useless as a pack gauge over the entire practical range**,
> and the two-region gauge this document was working toward — the module's `5C`
> up top, the ADC below the dropout — has no lower region to hand over to.
> **`5C` is the only signal available.**
>
> ⚠️ **Safety consequence, unconfirmed but likely:** the warn (3.55 V) and RGB
> cut (3.40 V) thresholds below are set **on VDD**, which is pinned at 3.90 V.
> They cannot fire until the buck-boost collapses entirely, which may be below
> the pack protection circuit's trip point — so the firmware's low-battery net
> may be inert, with the pack's own protection doing the real work. **Confirm
> this before relying on those thresholds in any deep discharge.**

**The load barely sags the pack**: RGB at full versus off moved the pack by
10 mV, and VDD not at all.

## The pack connector, and tapping it (2026-09-26)

**3-pin, 1.25 mm pitch, almost certainly Molex PicoBlade** (or a clone; the
Chinese "JST 1.25mm" listings are the same family). The housing measured
**5.45 mm** across on calipers, which is what settles it:

| family | pitch | 3-pin housing |
|---|---|---|
| JST SH | 1.0 mm | ~4.6 mm |
| **PicoBlade / JST GH** | **1.25 mm** | **~5.5 mm** |

⚠️ PicoBlade and JST GH differ only in the latch; GH leads mate with PicoBlade
headers, so a mistake there costs retention, not function. The decisive check is
pin 1 to pin 3 centres: **2.5 mm = 1.25 mm pitch**. Part numbers to match a
listing against: header `53261-0371`, pack plug `51021-0300`, in-line mate
`51047-0300`. Search "1.25mm 3 pin male to female extension cable"; they come in
cheap 10-packs, and crimping this pitch by hand needs a fine crimper (Engineer
PA-09 or similar) for no good reason.

**The pinout, from JD's unit:** red **+**, black **−**, white **NTC**. The
silkscreen beside the header says `NTC`. ⚠️ The black wire is nearly invisible
against the black PCB in photographs — count conductors at the pack, not on
screen.

⚠️ **The NTC is present and the firmware cannot read it.** It appears nowhere in
`battery.c`; it goes to the charger's temperature-fault input (the ASC4056 fault
row below). And there is no route to change that: the ADC survey above found
every AIN pin already spoken for. **So pack temperature is reachable only by an
external tap** — worth having, because the NMC curve we are fitting shifts with
temperature and a multi-day run on a desk sees several degrees.

### The tap

A **3-pin male-to-female extension** in line with the pack, with the conductors
brought out to a logger. Nothing is soldered to the pack, and no pack terminal is
ever exposed — which is the safety argument as much as the convenience one: the
09-25 run had **three accidental probe shorts**, one of which rebooted the board.
A permanent tap removes the poking that caused them.

- **Voltage only, in parallel.** ADS1115 (16-bit, ±4.096 V, ~0.1 mV) with a 2:1
  divider, or a logging DMM and no code at all.
- A 100k/100k divider draws 21 µA: ~2.5 mAh over five days out of 4000. Ignorable.
- Sample every 10-60 s. The pack moves ~0.008 V/h; anything faster is oversampling.
- Take the NTC out to the same logger for temperature.

⚠️ **Do not put a current shunt in the pack path while the regulator dropout is
being characterized.** The regulator's own drop is under 0.12 V at this load
(above); an INA219/INA226 with the usual 0.1 Ω shunt eats ~30 mV of that at
300 mA, so VDD would appear to follow the pack **earlier than it really does**
and the calibration would encode the test rig. If coulomb counting is wanted
later, use 0.01 Ω (~3 mV) and re-verify the dropout.

**Before connecting anything**, two checks at the header with the pack in:
`+` to `−` reads pack voltage (~4.0 V), and NTC to `−` reads ~10 kΩ at room
temperature for a 10k thermistor. That identifies the pins properly instead of
trusting wire colour.

⚠️ **Correction to an earlier claim here:** meter readings are *not* sensitive to
the RGB load. "The load barely sags the pack" above is the measured fact — full
versus off moved it 10 mV. A meter reading that wanders is probe contact, not
lighting.

## A real fuel gauge, retrofitted (a plan, not done)

⚠️ **Optional and personal.** This modifies one unit and helps nobody else
running this firmware. It is recorded because it is the **only route to a
percentage worth printing** — everything else in this document is making the
best of a signal that cannot deliver one.

**The part:** a **MAX17048** (or BQ27441). ModelGauge, so **no sense resistor**
— it sits across the pack and reports over I²C, ~$5 on a breakout. It models the
cell's dynamics to compensate for load and relaxation, which is exactly the
problem that makes raw voltage useless through the NMC plateau. Typical ±1-2%.
⚠️ Still voltage-derived, so it is not coulomb counting; it is just very good at
the thing `5C` is bad at.

### The pin mapping, verified

QMK's pin names map to the MCU's ports as **`A`→P0, `B`→P1, `C`→P2, `D`→P3**.
Proof: `keyboard.json`'s rows `B14, B15, B19, D19, A19, A18` become P1.14, P1.15,
P1.19, P3.19, P0.19, P0.18 → physical pins **38-43**, exactly the "row pins
38-43" in `fpb/ajazz-ak820-pro`. Columns land on 15-27, 29, 30 against its
"column pins 15-30", with pin 28 (P2.15) being `LED_WINLOCK_PIN`.

The MCU is an **HFD80CP100** — an SN32F299F clone, **80-pin LQFP, 0.5 mm pitch**,
20 legs a side, marked `U3`. Its pin-1 dimple is at the **bottom-left of the
package** with the part marking readable.

### What every pin does

| pins | use |
|---|---|
| 1-6, 8-14, 73, 75-78 | RGB matrix rows (`SN32F2XX_RGB_MATRIX_ROW_PINS`) |
| 15-27, 29, 30 | key matrix columns (shared with the RGB columns) |
| 38-43 | key matrix rows |
| 28, 65, 68 | WinLock LED (`C15`), indicator (`D15`), charging LED (`B18`) |
| 36, 37 | dip switch (`B12`, `B13`) |
| 44, 45, 64 | panel `RST` (`A17`), `BKL` (`A16`), `DC` (`D14`) |
| 50, 52, 59 | SPI `SCK` (`D0`), `MOSI` (`D2`), `SS` (`B8`) |
| 46, 47 | RTC |
| 72, 74 | encoder (`A10`), `BOOT` (`B3`) |
| 48, 49, 66, 67, 69, 70, 71 | flash/BT/misc (`A13`, `A12`, `B16`, `B17`, `B0`, `B1`, `B2`) |
| 7, 35, 53-58, 79, 80 | RESET, VREG33, USB, SWD, VDDIO1, VSS, VDD |

⚠️ **The RGB rows include `D10`-`D13`, which are `LXIN`/`LXOUT`/`XIN`/`XOUT`.**
Both crystal pairs are repurposed as LED drive, so **the board has no crystal at
all** and runs on the internal RC — which is why `config.h` warns the oscillator
is per-unit and temperature-dependent. Unrelated to the battery, and worth
knowing.

### Free pins — nine of them

Zero references anywhere in the firmware:

| QMK | port | **physical pin** | alt function |
|---|---|---|---|
| **A0** | P0.0 | **31** | AD0 |
| **A1** | P0.1 | **32** | AD1/SEG10 |
| **A2** | P0.2 | **33** | AD2/SEG11 |
| **A3** | P0.3 | **34** | AD3 |
| B9 | P1.9 | 56 | A5 |
| B7 | P1.7 | 60 | COM4/SEG28 |
| B6 | P1.6 | 61 | COM5/SEG29 |
| B10 | P1.10 | 62 | COM6/SEG30 |
| B11 | P1.11 | 63 | COM7/SEG31 |

Two are needed for a bit-banged I²C; 31-34 are contiguous.

⚠️ **`D1` (pin 51) looks free and is not.** `SPI_MISO_PIN` is `NO_PIN`, so it has
no firmware references — but it is SPI0's hardware MISO, sitting between `SCK`
(50) and `MOSI` (52), and the flash almost certainly uses it for reads.

⚠️ **"Unused by firmware" is not "unconnected."** Before committing, probe each
candidate with the board powered: a genuinely free pin floats or sits where its
internal pull puts it. One held firmly high or low is wired to something the
stock hardware used.

### Identifying the legs physically

Do **not** trust the dimple alone. Anchor it electrically:

1. **Find VSS (pin 79)** — buzz each leg to ground; exactly one is a dead short.
2. **Pin 80 (VDD) is adjacent to it**, and **pin 1 is immediately around the
   corner from pin 80**. That gives both the position and the direction of
   numbering.
3. **Cross-check with pin 35 (`VREG33`)**, which has a decoupling capacitor to
   ground nearby.

### ⚠️ The practical obstacle, and how to avoid it

0.5 mm pitch is at the edge of what is reasonable freehand, and bridging
adjacent legs is the normal outcome. **Do not start at the legs.**

**Probe for a bigger target first.** The board carries **two large round gold
test pads**, **two columns of five rectangular gold pads**, and **`RU9`/`RU10`
unpopulated resistor footprints** near U2. Ring each of them out against the nine
candidate legs. **One hit turns this into soldering to a resistor pad.**
Unpopulated strapping footprints are very often wired to a spare GPIO — that is
what they are for.

If it does come to the legs:

- **Kapton tape as a solder mask** — cover the row, expose only the target leg.
  Bridging becomes physically impossible. The single biggest improvement.
- **0.1 mm enamelled magnet wire**, not 30 AWG. Surface tension keeps the joint
  on one leg.
- **A USB microscope (~$30)** does more for this than any other purchase in this
  document.
- Strain-relieve with UV resin or epoxy before anything moves, and
  continuity-check before powering.

### ⚠️ What this does not change

The **filtered-`5C` path needs no soldering, no purchase, and meets the objective
above**. The retrofit buys a percentage worth printing, on one unit, at the cost
of a fiddly modification to a board in daily use. It is a want, not a need, and
stopping after the probing step is a perfectly good outcome.

## The charger (ASC4056)

A TP4056-class linear charger, ESOP8 (`fpb/ajazz-ak820-pro/docs/ASC4056.pdf`,
in Chinese). **Pin 5 is BAT** (the pack's +), a much easier probe point than
the pack connector. CHRG (pin 7) and DONE (pin 6) are open-drain, read on B16
and B17 with pull-ups:

| state | CHRG | DONE |
|---|---|---|
| charging | low | high |
| full | high | low |
| no battery | pulsing ~2 Hz | low |
| fault (temperature, VIN < 3.8 V, VIN < VBAT) | high | high |

**DONE has never been seen low.** Charging finished at 20:16 on 2026-09-24
(CHRG went high with USB in) and B17 stayed high, which the table calls a
fault. B17 is probably not DONE, or DONE is not connected. The usable "full"
signal is **CHRG going high while USB is in, after it had been low**.

The stock firmware lit the charging LED in the cable position, so the pack
does charge there too (owner, 2026-09-25). Our firmware leaves that LED off
because it is far too bright; the bolt on the battery row reads the same pin.

## Measurements, 2026-09-24/25

**Recharge after an hour's drain:** an hour unplugged at full pastel RGB was
put back in **23 minutes** of charging (19:53 → 20:16). This charger gives at
most 1 A, so that hour cost under ~380 mAh.

**The discharge run** (meter at the pack connector, VDD from the battery row):

| time | pack | VDD | lighting |
|---|---|---|---|
| 10:54 | 4.18 / 4.17 | 3.90 | rest / RGB full, pastel |
| 11:28 | 4.14 | 3.90 | |
| 12:06 | 4.12 | | |
| 13:57 | 4.08 | | |
| 15:34 | 4.05 | 3.90 | |
| 15:36 | | | **switched to solid white, 100%** |
| 16:25 | 4.03 | 3.90 | |
| 17:07 | 4.02 | 3.90 | |
| 19:39 | 4.01 | 3.90 | |

(Raw readings with every note: `history/battery-2026-09-25/readings.csv` once
the run's log is read.)

**The draw is small:** 4.17 → 4.01 V in 8¾ hours is about 18% of an NMC
charge, **roughly 2% an hour, 80-130 mA for the whole board at full RGB**.
The LEDs are multiplexed 1/18, so even full white draws modestly. A full pack
should last on the order of 30-40 hours at full brightness, and several days
with the lights off.

## The shutdown of 2026-09-24

After a few hours unplugged at full brightness the board went completely dark
and came back **only when the cable was plugged in**. By the numbers above
the pack was **nowhere near flat**. It had charged for only ~45 minutes before
the charger stopped, and read full the same evening. Our firmware has **no
sleep, timeout or power-down path at all**. So something cut the battery-side
power, and USB (which reaches VDD by its own path) bypassed it. Suspects:

1. an idle or disconnect power-off in the CH582F or the power circuit (the
   stock firmware has a "deep sleep" state, `g_connection_mode` 0x0D, that
   ours never takes part in);
2. the pack's protection circuit tripping (a charger connection resets it).

Not reproduced yet. If it happens again: note the time and how long the board
had been idle, then try a key press, then the slider flip with the cable still
out, then the cable.

## The level estimate (`36be68f16a`, not yet flashed)

Three sources, each used only where it is true:

1. **The charger terminating with USB in is a true 100%.**
2. **Below the regulator**, the level comes from VDD + dropout on the NMC curve.
3. **In the regulated band**, a countdown from the load: a base draw plus the
   LED drive, read from `sn32f2xx_led_load()` (the sum of every channel's PWM
   value), converted to level through the pack's 4000 mAh (1 mA = 0.025 %/h).
   It is floored at the level where the regulator lets go, which the voltage
   then takes over.

On USB the level holds, creeps up while charging, and jumps to 100 at
termination. The regulator's output is learned per unit (the highest settled
VDD on battery). Constants marked `CAL` in `battery.c` await the discharge
log: `DROPOUT_MV`, `DRAW_BASE_MA`, `DRAW_LED_FULL_MA`, `CHARGE_MA`, and the
curve itself.

## Protection and the log (`b35d8672b3`, flashed)

- **Warn** ("Battery low") after 30 s under 3.55 V VDD; **cut** the RGB
  (noeeprom, so the saved setting is untouched) after 30 s under 3.40 V, until
  USB returns. Both are RAM-only and settable: `ak820battery.py cfg WARN CUT`.
- **The log**: once a minute, 12 hours, in RAM. Read it with
  `ak820battery.py log out.csv`, and **plug in with the slider on BT**: a
  BT → cable flip resets the board and loses it.

## The idle ladder (`3b85686ff7`, not yet flashed)

On battery only: RGB to a quarter after 1 minute idle, RGB off and the screen
capped at level 4 of 23 after 5, the screen backlight off after 15. Any key
or knob turn restores everything within a tenth of a second, and the key
types as normal. Each stage is a cap below the user's settings, never a
change to them. Deep sleep (stopping the row ISR, sleeping the MCU) is next;
key scanning lives in that ISR, so it needs its own wake path (task 8.4, and
task 9 for making that ISR cheaper).
