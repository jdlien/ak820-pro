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

## Why this was hard

Every obvious source turned out to be wrong or absent:

- **The CH582F's percentage (`5C`) is not a level.** It read 100 through a
  full-brightness discharge, and 100 while recharging a pack we then believed
  flat. It does sense the pack: a board with no pack fitted reads 0
  (`indicators.c`). Across the whole range we have observed it only ever says
  100. The **stock firmware's gauge was this number**: none of the nine stock
  SN32F290 images in `fpb/ajazz-ak820-pro` (AK820 Pro v1.13, v1.14, and seven
  sibling boards) references the ADC, comparator or op-amp base addresses.
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
V** (full table below). The regulator's own drop is therefore under 0.12 V at
this load. VDD will follow the pack, a dropout below it, once the pack gets
down to around 3.95-4.0 V: not yet observed.

**The load barely sags the pack**: RGB at full versus off moved the pack by
10 mV, and VDD not at all.

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
