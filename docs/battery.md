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

## What is achievable (revised 2026-09-27 — the earlier verdict was wrong)

⚠️ **This section previously said a trustworthy percentage was "not reachable
on this hardware." That is withdrawn.** It was written believing `5C` was a
coarse, noisy gauge. It is not: it is a **precise voltmeter on the pack**, and
that changes the answer.

### What `5C` actually is

Fitted against a meter across one discharge, four settled points:

    5C = 117.8 × V_pack − 374.5      r² = 0.99947
    inverted:  V_pack = (5C + 374.5) / 117.8      ±3 mV

So the module is doing the crudest possible thing — a **straight line from
~3.18 V = 0% to ~4.03 V = 100%**, no cell model, no curve, no compensation.
⚠️ That single fact explains everything this document previously found
mysterious: a full pack at 4.18 V is **above the 4.03 V ceiling**, so it clamps
to 100 and stays there through the first ~20% of the discharge. Every earlier
test that concluded "it only ever says 100" was run entirely inside the clamp.

**The important consequence: `5C` gives us the pack voltage the SN32 cannot
see.** The MCU is behind the buck-boost; the CH582F is on the unregulated rail.
That is the whole reason this one number matters.

### A ±5% percentage is reachable with no new hardware

**Time is the coulomb counter.** The load here is essentially constant, so in a
constant-load discharge *elapsed time is proportional to charge consumed*. A
single full run therefore **measures this cell's own voltage→SoC curve**
directly: at total runtime `T`, the SoC at any voltage is `remaining/T`. No
generic NMC table, no assumed capacity.

⚠️ **And this board has a property that makes voltage gauging work better here
than it usually does:** RGB full versus off moves the pack **10 mV** (Hardware
facts, below). Load-induced sag is the usual reason voltage gauges fail, and at
10 mV **one curve covers every load state the keyboard has.**

Error budget:

| source | contribution |
|---|---|
| `5C` quantisation (8.5 mV per count) | ±1.2% |
| jitter, ±3 counts raw | ±3.5% |
| ↳ **median-filtered over ~30 samples** | **±0.6%** |
| curve fitted from our own run | ±3-5% ← dominant |
| temperature, 10 °C swing | ±1.5-3% |
| cell ageing after a year | ±5%, drifting |

**≈±5% fresh.** The jitter is *not* the limit — it averages down as √n, so half
a minute of sampling takes ±25 mV to ±5 mV.

### The objective

- **bars plus a percentage in 5% steps** — the granularity is what tells the
  user it is an estimate; 1% resolution is a claim we cannot back;
- **ratcheted**: never rising while on battery, reset on charge;
- ⚠️ **a low-battery warning that fires**, which today's VDD thresholds may not;
- volts on the `Fn`+`D` debug page only, never on the battery row.

### What the MAX17048 still buys — less than this document used to claim

A **refinement and a convenience, not an enabler**: ±1-2% instead of ±5%, no
curve fitting or periodic recalibration, and ageing compensation our fitted
curve will not have. Its load and relaxation modelling is largely wasted here,
given the 10 mV sag. Worth doing if the accuracy or the maintenance matters;
⚠️ **not required for a percentage worth printing.**

### ❌ The software coulomb-count route is superseded

An earlier version proposed estimating current from `led_pm`/`rgb_val` and
integrating it, with the INA228 measuring milliamps to fit the model. **Dropped.**
The voltage route above is simpler, needs no extra hardware, and does not drift
with an unmeasured load model. The INA228 was removed from the parts list.

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

**The part:** a **MAX17048**. ModelGauge, so **no sense resistor** — it sits
across the pack and reports over I²C, ~$5 on a breakout. It models the cell's
dynamics to compensate for load and relaxation, which is exactly the problem
that makes raw voltage useless through the NMC plateau. Typical ±1-2%. ⚠️ Still
voltage-derived, so it is not coulomb counting; it is just very good at the
thing `5C` is bad at.

### ⭐ The board already has an I²C bus

**This is what makes the mod reasonable rather than fiddly.** `halconf.h:15-21`:

> External PCF8563 RTC on **P0.14/P0.15** via the ChibiOS software (bit-banged)
> I2C fallback LLD … The SN32 HW I2C peripheral cannot reach those pins.

So SDA and SCL are already routed, already working, and already driven by a
proven driver. Consequences:

- **No free GPIO needed.** The pin audit below is still useful reference, but
  the retrofit does not consume any of it.
- **No new driver needed.** `SW_I2C_USE_I2C1` gives `I2CD1`; add a second
  device to the same bus.
- **No address conflict.** MAX17048 is `0x36`, PCF8563 is `0x51`.
- **No 0.5 mm soldering.** The targets are the PCF8563's own pins (SO8/TSSOP8,
  1.27 or 0.65 mm pitch) or its surrounding passives — an entirely different
  difficulty class from a QFP leg.

### Wiring

| MAX17048 | goes to | note |
|---|---|---|
| `VDD` | **pack +** | it measures its own supply; this is the whole point |
| `GND` | **pack −** | common with board ground |
| `SDA` | P0.14 or P0.15 | whichever `rtc.c` assigns; take it at the PCF8563 |
| `SCL` | the other | |
| `CTG`/`ALRT` | leave | not needed for polling |

### ⚠️ Three electrical checks before committing

1. **Logic levels across two supplies.** The MAX17048's `VDD` is the **pack**
   (up to 4.2 V) while the SN32 runs at 3.3 V. Its I²C thresholds are specified
   against its own `VDD`, so confirm `VIH` is met by a 3.3 V bus at a 4.2 V
   `VDD` (0.7 × 4.2 = 2.94 V, so it should pass, but **check the datasheet
   rather than this arithmetic**). Nothing exceeds 3.3 V on the SN32 side, so
   that direction is safe.
2. **Pull-ups may not exist as components.** ⚠️ `SW_I2C_USE_OPENDRAIN FALSE`
   means the driver emulates open-drain by **switching the pin to input to
   release the line** — so something else pulls it high, possibly the SN32's
   internal pull-ups rather than external resistors. **Look for them on the
   board before planning to solder to them.**
3. **Bus capacitance.** Adding a second device and a length of wire slows the
   rise time, and internal pull-ups are weak (tens of kΩ). If the bus is
   relying on them, **fit a proper 4.7 kΩ external pull-up** on each line as
   part of the mod. You are soldering anyway.

### ⚠️ The bus is rationed, and for a reason

`ak820pro.c:585`: *"RTC I2C (port A) glitches the flash SPI1 pins (A12/A13)
mid-DMA."* I²C transactions are deliberately limited to **one per main-loop
pass, and only with the LCD DMA idle** (`docs/clock.md`). A MAX17048 read every
30 s is negligible traffic, but it must go **through that gate, not around it**
— schedule it the way `rtc_task()` is scheduled, and do not add a transaction
anywhere that can run mid-blit.

### Solder targets, easiest first

1. **External I²C pull-up resistors**, if they exist — 0402/0603 pads, trivial.
2. **The PCF8563's SDA/SCL pins** — SO8 or TSSOP8, very manageable.
3. **A via on either net** — scrape the mask, tin, done.
4. The MCU legs, pins 46/47 — last resort, and unnecessary given the above.

Pack `+`/`−` come from the connector tap (see the connector section), so no
soldering to the pack itself.

### The pin audit (reference, no longer load-bearing)

Kept because it is useful for any firmware work on this board, not because the
gauge needs it. QMK's names map as **`A`→P0, `B`→P1, `C`→P2, `D`→P3**, verified
because `keyboard.json`'s rows land on physical pins **38-43**, exactly matching
`fpb/ajazz-ak820-pro`'s "row pins 38-43", and the columns on 15-30. The MCU is
an **HFD80CP100** — an SN32F299F clone, **80-pin LQFP, 0.5 mm pitch**, marked
`U3`, pin-1 dimple at the bottom-left of the package with the marking readable.
Datasheet: `docs/SN32F299_V1.8_EN.pdf` in that repo.

| pins | use |
|---|---|
| 1-6, 8-14, 73, 75-78 | RGB matrix rows (`SN32F2XX_RGB_MATRIX_ROW_PINS`) |
| 15-27, 29, 30 | key matrix columns (shared with the RGB columns) |
| 38-43 | key matrix rows |
| 28, 65, 68 | WinLock LED (`C15`), indicator (`D15`), charging LED (`B18`) |
| 36, 37 | dip switch (`B12`, `B13`) |
| 44, 45, 64 | panel `RST` (`A17`), `BKL` (`A16`), `DC` (`D14`) |
| 46, 47 | **PCF8563 I²C (P0.14/P0.15)** |
| 50, 52, 59 | SPI `SCK` (`D0`), `MOSI` (`D2`), `SS` (`B8`) |
| 72, 74 | encoder (`A10`), `BOOT` (`B3`) |
| 48, 49, 66, 67, 69, 70, 71 | flash/BT/misc (`A13`, `A12`, `B16`, `B17`, `B0`, `B1`, `B2`) |
| 7, 35, 53-58, 79, 80 | RESET, VREG33, USB, SWD, VDDIO1, VSS, VDD |

**Free — no firmware reference anywhere:** `A0`/`A1`/`A2`/`A3` (pins **31-34**,
contiguous), `B9` (56), `B7` (60), `B6` (61), `B10` (62), `B11` (63).

⚠️ **`D1` (pin 51) looks free and is not.** `SPI_MISO_PIN` is `NO_PIN`, so it
has no firmware references — but it is SPI0's hardware MISO, sitting between
`SCK` (50) and `MOSI` (52), and the flash almost certainly reads through it.

⚠️ **"Unused by firmware" is not "unconnected."** Probe before trusting.

⚠️ **The RGB rows include `D10`-`D13`, which are `LXIN`/`LXOUT`/`XIN`/`XOUT`.**
Both crystal pairs are repurposed as LED drive, so **the board has no crystal at
all** and runs on the internal RC — which is why `config.h` warns the oscillator
is per-unit and temperature-dependent, and why the clock needs a host to
discipline it.

### ⚠️ What this does not change

The **filtered-`5C` path needs no soldering, no purchase, and meets the
objective above**. The retrofit buys a percentage worth printing, on one unit,
at the cost of a modification to a board in daily use. It is a want, not a need.

## ⚠️ `battery_on_battery()` is wrong, in two ways (2026-09-28)

```c
#define ON_USB_MIN_MV 4300u
bool battery_on_battery(void) { return mv != 0 && mv < ON_USB_MIN_MV; }
```

**1. No hysteresis.** Observed live on 09-28: with VDD creeping up through
4300 mV as the charge current tapered, the battery row **alternated between
"USB" and the voltage** on every few-millivolt wobble. A slow crossing parks it
on the boundary for a long time, so this is not a rare flicker.

**2. ⚠️ It cannot tell "unplugged" from "plugged in, charging hard."** The
09-28 charge log shows **VDD at 4193 mV for four straight hours** while on USB
and charging — below the threshold, so the firmware believed it was on battery
the whole time. `BATT_F_ON_BATTERY` and `charging` were set **simultaneously**.
The threshold was set against this document's "4.31 V while charging hard", but
a deeply discharged pack charges harder than that and pulls VDD lower.

**The fix is a better signal, not a better threshold.** The charger pin is a
direct observation:

    CHRG low                                   -> on USB (charging)
    CHRG high AND VDD >= 4300 (with hysteresis) -> on USB (idle/full)
    otherwise                                   -> on battery

VDD then only arbitrates the case CHRG cannot — which is exactly the case where
VDD is trustworthy, because no charge current means no diode drop.

⚠️ **This gates the new gauge.** The ratchet must not run while charging and
the idle ladder must not dim a plugged-in keyboard, so a predicate that is
wrong for hours would break both.

## ⭐ VDD as the charge-complete signal

This document records that the ASC4056's DONE pin never reads low, so "full has
to be inferred". ⚠️ The 09-28 log shows **`done` never asserted and `charging`
never cleared across 7.5 hours** — both pins are useless for termination.

**VDD infers it.** VDD is USB through a diode, so its drop scales with current:

| VDD | meaning |
|---|---|
| ~4193 mV, flat | constant-current phase, full charge current |
| rising | CV phase, current tapering |
| ~4470 mV | no charge current — **done** |

Measured 09-28: flat at 4193 from 03:00 to 07:00, then 4241 → 4268 → 4300 as
the taper set in. A diode's drop is logarithmic in current, roughly 50 mV per
e-fold, so **+75 mV from the plateau is about a 4-5x fall in charge current**.

So the rail that is useless as a battery gauge is a serviceable
**charge-current** proxy, and it answers a question this document previously
recorded as unanswerable.

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
