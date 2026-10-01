# The battery: what the board can know, and how the level is estimated

Code: `battery.c` (the supply decision, `5C`, the level, protection, the log),
`power.c` (the power caps: the lights cut, and the idle ladder when enabled),
`indicators.c` (charger pins, pack presence), and the battery row and debug
page in `graphics/display.c`. Host tool: `hostagent/ak820battery.py`. The
plan, two codex reviews and every disposition:
[`plans/BATTERY-GAUGE-PLAN.md`](../plans/BATTERY-GAUGE-PLAN.md).

> **State (2026-09-30):** on JD's unit is `deef6053dd`, the Phase 1 gauge.
> A drain test at full white has run from FULL since 2026-09-28 ~19:55
> ([`history/battery-2026-09-28-drain/`](../history/battery-2026-09-28-drain/));
> it supplies the curve that replaces the provisional one. Its last night
> passed Phase 1 gates 2 (protection) and 4 (eight meter points). Resume from
> [`plans/current-status.md`](../plans/current-status.md).

## The short version

- **The MCU cannot see the pack.** The SN32 can measure only its own supply,
  VDD, and on battery that is a buck-boost's output: ~3.90 V whatever the pack
  is doing. No analogue pin reaches the pack either.
- **The Bluetooth module can.** The CH582F sits on the unregulated rail and
  reports a byte, `5C`, that everyone took for a (fake) percentage. It is a
  **linear voltmeter on the pack**: `5C = 114.22 × V − 361.04`.
- **Averaged, it agrees with a meter to within about the meter's resolution:**
  eight checks on the 09-28 run, 4.01 V down to 3.22 V, all within 11 mV
  (below).
- **The level is a fraction of runtime**, read off a curve of pack voltage.
  The voltage is good; the curve in the firmware is a **placeholder** until the
  drain test is fitted.
- **It is blind at both ends:** above ~4.036 V (the top ~8-10% of runtime) and
  below ~3.161 V. While charging, the charge current inflates the reading.

## Where the pack voltage comes from: `5C`

### What `5C` is

The CH582F sends the MCU a `5C <byte>` frame: the stock firmware's battery
percentage, and the only battery signal the stock firmware had (none of the
nine stock SN32F290 images in `fpb/ajazz-ak820-pro` — AK820 Pro v1.13, v1.14
and seven sibling boards — references the ADC, comparator or op-amp base
addresses). It is not a cell model. It is a straight line on the pack voltage,
fitted against a meter at five settled points on the 09-25 discharge
(`history/battery-2026-09-25/readings.csv`: 3.84 → 78, 3.81 → 74, 3.74 → 66,
3.68 → 59, 3.30 → 16):

    5C = 114.22 × V_pack − 361.04      r² = 0.99987, residuals < 0.5 count
    inverted:  V_pack = (5C + 361.04) / 114.22

- **One count is 8.75 mV.**
- **It clamps:** 100 above ~4.036 V and 0 below ~3.161 V. Both ends are the
  line extrapolated, not measured. A full pack rests at 4.18 V, above the
  ceiling, so `5C` reads 100 for the first ~5 hours of a discharge at full
  white — which is why every test before 09-26 concluded "it only ever says
  100": they all ran inside the clamp.
- **It reads terminal voltage.** Plugged in near full it snaps to 100 (the
  charger's CV voltage is above the clamp); plugged in flat it climbs slowly
  (4 → 100 over 3 h 55 min on 09-28). See "Charging", below.
- **A board with no pack fitted reports 0** (`indicators.c` uses that, with
  the charger pins, for "No Batt").
- **Fitted on one unit, on discharge, 3.30-3.84 V.** Checked since across a
  recharge and up to 4.01 V (below). Another unit's module may sit on a
  different line.

### How often it arrives

Three observations, which do not yet add up to a mechanism:

- the firmware sends `A6 53` every 5 s (`CH582_BATTERY_POLL_MS`), as the stock
  firmware does;
- the battery log counts **224-237 reports per 10-minute entry** on 09-28
  (log v3) and **262-334** on 09-29/30 (v4): one per ~1.8-2.7 s;
- the debug page's age (the `3` in `62@3`) **counts up to ~4 and resets**
  (JD, 2026-09-30 ~20:00): gaps of ~4-5 s.

So **2-3 reports per 5-second poll cycle, bunched together** rather than spread
evenly. ⚠️ With the lights cut (10-01, from ~02:13) the count fell to
**194-256 per entry**, some entries with every report identical — which fits
the module also sending a report when the reading changes. A hint, not a
finding. Whether that is several replies to one poll, or the reply plus an
unprompted stream, has not been checked (a capture of the serial frames would show
it). It matters for one thing: if a bunch repeats one measurement, the 64
reports the estimate averages are ~25 independent readings, not 64.

### From reports to millivolts

The CH582F driver hands every report to `battery_5c_report()` as it is parsed
— never the cached last value, which would count one report many times.

- **The estimate is a trimmed mean of the last 64 reports**, in hundredths of
  a count: sort, drop the highest and lowest eighth, average the rest. That
  spans ~2-2.5 min at the current report rate. At least 5 reports before there
  is an estimate at all.
- **Why a mean and not a median** (the median of 7 before `deef6053dd`): a
  median of whole counts is a whole count, and one count is 1.2-5% of level
  depending on where the pack is, so the level moved in lumps and then sat
  still for an hour. A single report jitters by ±2-3 counts (the log's
  per-period min/max), and it dithers between neighbouring counts, so the mean
  resolves about a tenth of a count (the log's means read like `62.98`). The
  trim keeps a median's indifference to a stray report.
- **Emptied** when no report has arrived for 20 s, at every supply change, and
  whenever the charger starts or stops: reports taken under charge current do
  not describe the pack without it, and vice versa.
- **The clamps:** an estimate ≥ 99.50 is the top clamp (the pack is only known
  to be ≥ 4036 mV) and < 0.50 is the bottom one (≤ 3161 mV). Those are bounds,
  never fed to the curve; the debug page prints them as `>4036` and `<3161`.
- **Millivolts:** `(estimate + 361.04) × 1000 / 114.22`, in integers
  (`c5_to_mv`).

### Checked against a meter

Meter at the pack connector, which reads to 10 mV; the gauge's pack mV from
the debug page (`history/battery-2026-09-28-drain/readings.csv`). These are
**not** the points the line was fitted to: a different run, after a recharge.

| time | meter | gauge | error | firmware |
|---|---|---|---|---|
| 09-29 09:29 | 4.01 V | 4001 mV | −9 | median of 7 (whole counts) |
| 09-30 12:32 | 3.81 V | 3816 mV | +6 | trimmed mean |
| 09-30 14:57 | 3.79 V | 3791 mV | +1 | trimmed mean |
| 09-30 19:56 | 3.70 V | 3700 mV | 0 | trimmed mean |
| 09-30 20:43 | 3.68 V | 3686 mV | +6 | trimmed mean |
| 09-30 23:00 | 3.58-3.59 V | 3589 mV | 0 to +9 | trimmed mean |
| 10-01 01:05 | 3.50 V | 3505 mV | +5 | trimmed mean |
| 10-01 ~05:07 | 3.22 V | 3231 mV | +11 | trimmed mean |

All eight are inside the ±20 mV of Phase 1 gate 4, and every error is within
about one digit of the meter (10 mV). **The line held beyond both ends of its
fitted range**: −9 mV at 4.01 V above it, +11 mV at 3.22 V below it. JD reads
the screen first and probes after, so on a falling pack each error carries a
small positive lag: ~1 mV at 17 mV/h, ~4 mV at 80 mV/h.

⚠️ **One reading has never fitted.** On 09-26, near the end of the first run,
JD read **85** at a pack of ~3.99-4.00 V, where the line predicts ~95. It was
recalled, not logged, and nothing since has reproduced it.

## What the level means

⭐ **The fraction of runtime left, at the load the curve was measured at.**
Behind a buck-boost the board draws **constant power**, so the pack current
rises as the voltage falls (about 27% between 4.18 and 3.30 V). A timed run at
fixed settings therefore calibrates *runtime*, not charge: at total runtime `T`
the level at any voltage is `remaining / T`. That is also what a user wants to
know. Calling it state of charge would need a current measurement.

**The curve is the whole accuracy question now.** The voltage is good to ~10 mV;
how much level 10 mV is worth depends on the curve's slope — on the provisional
curve, 1.4-1.8% on the 3.87-4.02 V plateau and 2.8-5.6% between 3.69 and
3.87 V.

- ⚠️ **The textbook NMC rest-voltage curve does not fit this pack.** It puts
  3.74 V at ~47%; on 09-25 the pack reached 3.74 V at 49.3 h and was dead by
  63.4 h, so it had **at most ~25%** of its runtime left.
- **The provisional curve** (`curve_mv`/`curve_pm` in `battery.c`) is a generic
  Li-ion table (0% at 3.27 V … 80% at 4.02 V) scaled so the top clamp reads
  90%: on 09-25 `5C` left 100 about 5.3 h into a run of ~52-63 h, so the clamp
  is the top ~8-10% of runtime. It is named provisional in the source. **Only
  those two arrays change** when the fitted curve replaces it.
- **Load moves the pack only a little:** RGB full versus off moved it **10 mV**
  near full (one meter reading, pastel lighting). Near 3.40 V the RGB cut lifted
  it **~20 mV** (10-01 ~02:13: the log's mean rose 3408 → 3412 mV where it had
  been falling ~19 mV an entry; a rough trend estimate). Sag is the usual
  reason voltage gauges fail; at 10-20 mV one curve should cover the lighting
  states, but the sag does grow toward empty.

### How good it can get

| source | size | status |
|---|---|---|
| `5C` → mV | within ~10 mV, 3.22-4.01 V | measured, eight points |
| one `5C` count | 8.75 mV | the raw step; the mean resolves ~0.1 count |
| the curve | ±3-5% of level, guessed | **the dominant term**; the drain test fits it |
| temperature, 10 °C swing | ±1.5-3%, from generic NMC figures | unmeasured here |
| cell ageing, a year | ±5%, drifting | unmeasured |
| another unit's module | unknown | one unit fitted |

**≈ ±5% fresh is the target, not a result**, until a fitted curve is checked
against a run it was not fitted to.

### What the panel should show

- **Whole percent** (`deef6053dd`). The plan said 5% steps, so the granularity
  would say "estimate"; JD found they hid how fast the level was falling — it
  sat at 85% all day. While the curve is being fitted the panel shows **tenths**
  (`BATTERY_SHOW_TENTHS` in `config.h`); that goes before release.
- Ratcheted: never rising on battery, reset by a real charge.
- Volts on the `Fn`+`D` debug page only, never on the battery row.
- A low-battery warning that fires (it now does — below).

## The gauge as built (`deef6053dd`)

### Supply: what powers the board

A state machine on the charger's CHRG pin and VDD, because a VDD threshold
cannot tell "unplugged" from "plugged in and charging hard" (the old 4300 mV
predicate called a pack charging at VDD 4193 mV "on battery" for four hours on
09-28, and flickered in the taper):

    CHRG low on 2 ticks              -> USB, held 1 s past the last low
                                        (covers the no-pack ~2 Hz pulse)
    raw VDD >= 4100 mV for 0.5 s     -> USB
    raw VDD <  4000 mV for 1 s,
      with no evidence of USB        -> battery
    otherwise                        -> unchanged

On battery VDD is ~3.90 V; on USB no raw sample went under 4119 mV across a
7.5 h charge into a dead pack. ⚠️ The ADC reference is ±2% per part: re-check
both margins on another unit.

### The level

Kept internally in tenths of a percent.

- **On battery, below the top clamp:** the curve at the pack voltage, through
  **the ratchet** — it never rises; it moves down only after **six fresh
  estimates in a row** sit below it, and then to the *highest* of the six, at
  most 1% per move. Observed: ~15 s per 1% step (the 09-29 post-flash walk).
- **On battery, at the top clamp:** the voltage says only "≥ 4.036 V", so the
  level **counts down by time** from wherever charging left it: 1% per ~32 min
  (the 09-25 clamp span), floored at **90.5%**, just above the clamp's exit at
  90%, so a whole-percent or tenths panel runs into the curve without a step.
- **Booted at the top clamp** (every cable ↔ BT slider flip reboots): the saved
  level if it is in the clamp's 90-100 band, else a guess of 95. Below the
  clamp nothing is restored; the voltage is the authority.
- **Charging** reads the curve **150 mV below** the terminal voltage
  (`CHARGE_IR_MV`, the charge current's I×R: ~0.8-0.9 A through ~180 mΩ, a
  guess, unmeasured), only rises, and only in a **real charging session** (CHRG
  low for 60 s, so a brief plug-in cannot bump it). It stops at **97.0%**
  (creeping there through the CV phase at the clamp), and says **100 only when
  the charger terminates**: CHRG released for 10 s, on USB, with `5C` at 100.
  Charging termination with the board running in BT on USB is verified
  (09-28: a top-up released at 15:43, the gauge went to 100).
- **The re-seat:** after a real charging session the level is taken straight
  from the first post-unplug estimate below the clamp, once, so a wrong I×R
  costs one correction at unplug rather than hours of a wrong level.
- **The saved level** (kb eeconfig, 0.5% steps) is written at FULL, then at
  97.5 / 95 / 92.5 / 90 on battery (rounded down, so a restore never
  overstates), and once below the band, so a stale 9x is not restored after a
  pack swap: **six writes a charge cycle**, none while charging. It was every
  whole-percent change (~100 a cycle) until `deef6053dd`.
  ⚠️ **Every internal-flash write blanks the whole LED matrix for ~7 ms**
  (interrupts are masked through the program, and the vector table and row ISR
  live in flash; the Cortex-M0 has no VTOR to move them). JD sees it as a
  brief whole-board blink; a brightness step reproduces it. Count them with
  `ak820health.py --stalls --json` (`flash_writes`).

Queued fixes (the plan, "Queued"): show "Charge", not the 95 guess, while
charging at the clamp with nothing saved; don't spend the re-seat on a clamp
reading just after unplug — on 09-29 that left the level at 95 and the ratchet
walked it to ~86 at 1% per ~15 s.

### Protection

On the **pack voltage** from `5C` (it compared VDD until `8627554513`, and VDD
never fell far enough to fire):

- **"Battery low"** once, after 30 s under **3550 mV**; re-armed above 3650 mV
  or on USB.
- **"Low: RGB off"** after 30 s under **3400 mV**. Three fresh reports of 0 in
  a row cut at once and set the level to 0 ("Low").
- The cut is a **power cap** (`power_set_lights_cut`), not an RGB toggle, so
  the user's own `Fn`+`X` cannot undo it. It lifts only after **5 s of fresh
  evidence of USB** (CHRG low or VDD read high that second, not a remembered
  state). A stale reading never clears it.
- No threshold is judged at the top clamp, where the pack is only known to be
  ≥ 4036 mV.
- Thresholds are RAM-only, in pack mV, 0 disables: `ak820battery.py cfg WARN
  CUT`. A reboot restores the defaults.
- This sheds load; it does not disconnect the cell. The pack's own protection
  circuit does that (the 09-25 run: 0 V at the connector by 09-28 02:59).
- ✅ **Gate 2 passed on hardware**, the 09-28 run's last night: "Battery low"
  at ~00:00 on 10-01 (3544 mV on the debug row); the cut at ~02:13 (from the
  log's LED drive); JD could not turn the LEDs back on; 5 s of USB lifted it;
  and ~1 min after unplugging, still under 3400 mV, it cut again. ⚠️ Every
  plug-in re-arms the warning, so each brief dump re-fires it after unplugging.

### The panel

- **Battery row:** the level (`85%`; `85.9%` with tenths), an outline, and a
  fill that is green above 50%, amber 21-50%, red at 20% and below (rounded up,
  so a few percent never reads as empty). **`Low`** with a red sliver under
  0.5% on battery (below ~3.30 V on the provisional curve). While the level is unknown: **`Charge`** charging, **`USB`** on USB,
  blank on battery. **`No Batt`** and a red cross with no pack. A yellow **bolt**
  while the charger is charging (CHRG low and STDBY high).
- **Alerts** ("Battery low", "Low: RGB off") take the text band for 60 s.
- **`Fn`+`D`, row 8:** `Batt 62@3 3700 3900` is the module's **last raw
  `5C`** (62), its **age in seconds** (3; `--` once 20 s stale), the **pack mV**
  from the estimate (`>4036` / `<3161` at the clamps), and **VDD** in mV. The
  page recomposes once a second, so the age skips a value now and then.

### The log (v4)

**720 ten-minute entries, 120 h, in RAM.** Each holds VDD mean and min; every
`5C` report of the period as sum, count (16-bit), min and max; flags at the end
**and** OR-ed over the period, so a transition cannot fall between entries; the
level in 0.5%; the mean effective LED drive (`led_pm`, after the power cap);
and the effective LCD backlight. The reply carries the format version and the
period; the host tool never assumes either.

```sh
set -o pipefail
venv/bin/python3 hostagent/ak820battery.py log out.csv   # dump
venv/bin/python3 hostagent/ak820battery.py               # state (HC_CONN)
```

⚠️ **The log dies with the board.** A flat pack, a flash, and a **BT → cable
slider flip** (a reset) each lose it. Dump with the **slider on BT**, and
unplug within a minute: longer is a charging session, which re-seats the level
and charges the pack. ⚠️ A loose cable charges without enumerating: check for
USB id `0C45`.

`HC_CONN` (raw-HID channel 0x13) carries the live fields: VDD, charger pins,
the rounded estimate, its age, flags, the level, pack mV, LED drive, state and
the format version (`hid_protocol.c` has the byte map).

### Checked on the host

`scripts/battery_sim/run.sh` compiles this `battery.c` and `power.c` against a
simulated board and runs **27 scenarios**: the 09-28 charge log, a 57.7 h
discharge with jitter, every supply transition, a pack-less board, protection,
the re-seat, reboots at and below the clamp, and one per defect the
implementation review found. At that review fifteen deliberately broken
variants (a ratchet that rises, protection on VDD, the old 4300 mV predicate,
charging reaching 100, each review fix reverted) were each caught. It does not
compile `indicators.c` or `display.c`: presence and the panel are checked by
reading, and on hardware.

## Hardware facts

**The pack** (JD's unit, printed on the cell): `JKJ606090 4000mAh 72.9g,
3.7V 14.8Wh`, date code `202512.30`, Shenzhen Jiekejie. Li/Ni/Co/Mn with a
graphite anode: **NMC**. The other unit (the white one) had no pack fitted as of
2026-09-09.

**The slider is labelled POWER on the PCB.** It selects the power source as
well as the mode ([hardware.md](hardware.md)): BT → cable reboots the MCU.

**No analogue pin can see the pack.** AIN0..AIN15 are P2.0..P2.15, all matrix
columns, RGB rows or the Win Lock LED. The op-amp and comparator inputs are RGB
rows (B4, B5, A11), the flash's WP (B2), the encoder (A10) and the BOOT pin
(B3). There is nowhere to wire a divider, even by hand.

**VDD by power state** (the SN32 measuring itself against its internal 2.0 V
reference, ±2% per part):

| state | VDD | meaning |
|---|---|---|
| cable position, USB in | 4.79 V (4.53 V charging) | USB, through a low-drop path |
| BT position, USB in | 4.47 V idle; 4.12-4.31 V charging (~4.19 V through constant current from flat, rising through the taper) | USB through a diode |
| BT position, unplugged | **3.90 V, flat** | the buck-boost's output, fed from the pack |

**It is a buck-boost.** With the pack at 3.84 V, VDD read 3.901 V — above its
own input, which no linear regulator can do. Over the 09-25 run the pack fell
4.18 → 3.74 V while VDD moved +3 mV; VDD first sagged visibly (~3.87 V) with the
pack at 3.30 V. So VDD says which supply is on, never how full the pack is.

**VDD tracks charge current, qualitatively.** On USB in the BT position the
diode's drop scales with current: flat at ~4193 mV through constant current on
09-28 (03:00-07:00), then 4241 → 4268 → 4300 as the taper set in. ⚠️ Do not
threshold it: in the cable position VDD reads 4530 mV *while charging*, and USB
voltage, cable and temperature all move it. "Full" comes from CHRG.

**The draw at full white.** The 09-25 run lasted ~52-63 h (pastel for its
first ~4.7 h; its end fell in a 5.7 h unobserved window, and a 20 min charge
mid-run added an unknown few hours). From the label's 14.8 Wh that is
~0.23-0.28 W at the pack, ~60-75 mA at 3.7 V — if the label is honest. Lights-off draw is unmeasured. The LEDs are
multiplexed 1/18, so even full white draws modestly. **An hour unplugged at
full pastel RGB was put back in 23 minutes** of charging (09-24, 19:53 → 20:16;
this charger gives at most 1 A).

## The charger (ASC4056)

A TP4056-class linear charger, ESOP8 (`fpb/ajazz-ak820-pro/docs/ASC4056.pdf`,
in Chinese). **Pin 5 is BAT** (the pack's +), a much easier probe point than
the pack connector. CHRG (pin 7) and STDBY/DONE (pin 6) are open-drain, read on
B16 and B17 with pull-ups. The datasheet's table:

| state | CHRG | DONE |
|---|---|---|
| charging | low | high |
| full | high | low |
| no battery | pulsing ~2 Hz | low |
| fault (temperature, VIN < 3.8 V, VIN < VBAT) | high | high |

What the board actually shows:

- **CHRG works, slowly.** It released ~9½ h into a charge from a deeply
  discharged pack (09-28, pack 4.18 V), with `5C` at 100 for the last ~5½ h;
  a top-up of a full pack released after ~11 min. It answers "has charging
  stopped", not "how full". **The gauge's "full" is CHRG released with `5C` at
  100.**
- **DONE has never been seen low on USB**, not even after termination (09-24:
  CHRG went high with USB in and B17 stayed high, which the table calls a
  fault). B17 is probably not DONE, or DONE is not connected.
- ⚠️ **On battery DONE reads low**, in every entry of the 09-28 drain log: with
  no VIN the pin evidently loses its pull-up. So on battery it says nothing.
- The charging LED: the stock firmware lit it in the cable position, so the
  pack charges there too (JD, 2026-09-25). Ours leaves it off (far too bright);
  the bolt on the battery row reads the same pin.

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

⚠️ **The NTC is present and the firmware cannot read it.** It goes to the
charger's temperature-fault input, and every AIN pin is already spoken for
(above). **Pack temperature is reachable only by an external tap** — worth
having, because the curve we are fitting shifts with temperature and a
multi-day run on a desk sees several degrees.

### The tap

A **3-pin male-to-female extension** in line with the pack, with the conductors
brought out to a logger. Nothing is soldered to the pack, and no pack terminal is
ever exposed — which is the safety argument as much as the convenience one: the
09-25 run had **three accidental probe shorts**, one of which rebooted the board.
A permanent tap removes the poking that caused them.

- **Voltage only, in parallel.** ADS1115 (16-bit, ±4.096 V, ~0.1 mV) with a 2:1
  divider, or a logging DMM and no code at all.
- A 100k/100k divider draws 21 µA: ~2.5 mAh over five days out of 4000. Ignorable.
- The pack moves ~3-27 mV/h through most of a run at full white (slowest on
  the ~4.0 V plateau), and ~65 mV/h at the end (09-25: 3.68 → 3.30 V in 5.8 h). A sample every 10-60 s is plenty.
- Take the NTC out to the same logger for temperature.
- ⚠️ **A current shunt in the pack path drops its I×R between the pack and
  everything downstream, the CH582F included**, so `5C` would read lower than
  the pack by that much (~6-8 mV at a 0.1 Ω shunt and ~70 mA: about a count).
  Measure voltage on the pack side of any shunt, or use a 0.01 Ω one.

**Before connecting anything**, two checks at the header with the pack in:
`+` to `−` reads pack voltage (~4.0 V), and NTC to `−` reads ~10 kΩ at room
temperature for a 10k thermistor. That identifies the pins properly instead of
trusting wire colour. A meter reading that wanders is probe contact, not
lighting: full versus off moves the pack only 10 mV.

## A real fuel gauge, retrofitted (a plan, not done)

⚠️ **Optional and personal.** This modifies one unit and helps nobody else
running this firmware. The filtered-`5C` gauge needs no soldering and no
purchase, and is on track for ±5%; the retrofit is **a refinement, not an
enabler**: ±1-2%, no curve to fit or refit, and ageing compensation our fitted
curve will not have. Its load and relaxation modelling is largely wasted here,
given the 10 mV sag. It is a want, not a need.

**The part:** a **MAX17048**. ModelGauge, so **no sense resistor** — it sits
across the pack and reports over I²C, ~$5 on a breakout. ⚠️ Still
voltage-derived, so it is not coulomb counting; what it does better than us is
the voltage-to-level model, not the voltage. (JD's 2026-09-29 DigiKey cart,
[`plans/parts/`](../plans/parts/digikey-order-2026-09-29.csv), not yet ordered,
has an INA228 as a **current logger** for the power-mode work; a MAX17055 or
MAX1726x would be the permanent coulomb-counting option.)

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

## The shutdown of 2026-09-24 (unexplained)

After a few hours unplugged at full brightness the board went completely dark
and came back **only when the cable was plugged in**. The pack was **nowhere
near flat**: it had charged for only ~45 minutes before the charger stopped, and
read full the same evening. Our firmware has **no sleep, timeout or power-down
path at all** (the idle ladder is compiled out). So something cut the
battery-side power, and USB (which reaches VDD by its own path) bypassed it.
Suspects:

1. an idle or disconnect power-off in the CH582F or the power circuit (the
   stock firmware has a "deep sleep" state, `g_connection_mode` 0x0D, that
   ours never takes part in);
2. the pack's protection circuit tripping (a charger connection resets it).

Not reproduced. If it happens again: note the time and how long the board had
been idle, then try a key press, then the slider flip with the cable still out,
then the cable.

⭐ **A known cause gives the same symptom (2026-09-30, ~20:44).** A probe slip
shorted the pack connector mid-run, cable out: the board went **dark and stayed
dead**. A slider flip to the cable position and back, **still with no cable**,
brought it back (a fresh boot; the RAM log was gone). So a dark board on battery
is recoverable without a charger. That fits the pack protector's short-circuit
trip, which in DW01-class protectors releases once the load is removed — the
cable position disconnects the pack — but **the protector in this pack is
unidentified, so that is a hypothesis**, and a flip would also reset any latch
in the board's own power path. It does make suspect 2 concrete: something that
trips the protector, then holds it tripped while the board stays connected.

## The idle ladder (`3b85686ff7`, compiled out)

On battery only: RGB to a quarter after 1 minute idle, RGB off and the screen
capped at level 4 of 23 after 5, the screen backlight off after 15. Any key
or knob turn restores everything within a tenth of a second, and the key
types as normal. Each stage is a cap below the user's settings, never a
change to them. ⚠️ **Built only with `POWER_LADDER_ENABLE`**, off by default
since the gauge: it would change the load during the calibration run, and
which of its stages pays is unmeasured (plan, 2.6). Deep sleep (stopping the
row ISR, sleeping the MCU) is next; key scanning lives in that ISR, so it
needs its own wake path (task 8.4, and task 9 for making that ISR cheaper).
Phase 2 of the plan (power modes on `Fn`+`B`, an emergency reserve mode,
standby) supersedes the ladder's design; JD is collecting ideas there, not
building yet.

## Open questions

- **How `5C` frames arrive**: replies, a stream, or both (above).
- **Whether the line holds on another unit**, and across temperature.
- **`CHARGE_IR_MV`**: measure it as the step in `5C` at the moment of
  unplugging mid-charge.
- **The 85-at-~4.00 V reading** of 09-26 (above).
- **~10-15 unexplained flash writes** in 22 h on the old build (blinks at
  09-28 15:50 and 09-29 12:33 matched no known write).
- **The 09-24 shutdown** (above).

## Claims this document made and withdrew

Kept so nobody re-derives them. Each was stated as fact here at the time;
`git log -p docs/battery.md` has the full text.

| claim | withdrawn | why |
|---|---|---|
| "A trustworthy percentage is not reachable on this hardware" | 09-27 | `5C` is a precise voltmeter on the pack |
| "`5C` is not a level; it only ever says 100" | 09-26 | every test until then ran inside the top clamp |
| "VDD will follow the pack below ~3.95-4.0 V" (a regulator dropout) | 09-26 | VDD is a buck-boost output: 3.901 V with the pack at 3.84 V |
| "`5C` has a post-charge memory, discard it for hours after a charge" | 09-28 | 97 at 4.00 V is what the line predicts (96.7); the fall to 78 was 157 mV of line against the meter's 160 mV — it tracked the pack throughout |
| "Elapsed time is proportional to charge consumed" | 09-28, codex | constant power behind a buck-boost: it is runtime, not charge |
| "The line is validated 3.16-4.17 V on charge"; "the meter says 3.16 V" | 09-28 | nobody measured 3.16 V; it is the line's own zero point, repeated back as a reading |
| "Both charger pins are useless" | 09-28 | CHRG works, slowly; only DONE is broken |
| "DONE never reads low" | 09-28 | true on USB; on battery it reads low always |
| "~20% of runtime sits above the 4.036 V clamp" | 09-28 | ~8-10%: `5C` left 100 at 5.3 h of a ~52-63 h run |
| "~2%/h, 80-130 mA; 30-40 h at full brightness" (from an NMC curve) | 09-30 | the 09-25 run lasted ~52-63 h |
| "Meter readings are sensitive to the RGB load" | 09-26 | full versus off moved the pack 10 mV |
| "`5C` arrives every 5 s, only in reply to the poll" | 09-28 | 224-334 reports per 10 min: 2-3 per poll cycle (09-28 onward) |
| "VDD ~4470 mV means charging is done" | 09-28, codex | the cable position reads 4530 mV while charging |
| "Calibrate the VDD level estimator's constants" (`36be68f16a`) | 09-27 | VDD is a constant on battery; the estimator is deleted |
| Protection on VDD (`b35d8672b3`) | 09-28 | VDD was ~3.87 V with the pack at 3.30 V; it could not fire. Now on the pack voltage |
| `battery_on_battery()`: VDD < 4300 mV is "on battery" | 09-28 | no hysteresis (flickered in the taper), and a pack charging hard pulls VDD to 4193 mV. Now a state machine |
