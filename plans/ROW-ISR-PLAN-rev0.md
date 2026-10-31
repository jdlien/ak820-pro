# The row ISR rewrite: the RGB driver on direct registers, and the flickers it ends

Status: **revision 0 (10-31), Claude's draft, written before reading codex's
independent design** ([`review-codex-row-isr-design-2026-10-31.md`](review-codex-row-isr-design-2026-10-31.md),
from the brief [`design-prompt-row-isr.txt`](design-prompt-row-isr.txt)). The two
are compared in "Comparison with codex's design" below once it lands, then
the merged plan goes to a codex reviewer until it is called ready. Nothing
built. Grows out of two backlog entries: "Row-ISR body: the one lever that
lifts scan rate, main loop and field rate together" (09-03) and "The LED
blink at an internal-flash write" (10-27), [`BACKLOG.md`](BACKLOG.md).
Owner: the Mac session.

JD's reason for doing it (10-31): the flicker and dimming fixes. The CPU and
the field rate are the bonus.

## What is known (measured 09-03 and since; derived where marked)

The driver is `qmk_firmware-ak820pro/drivers/led/sn32f2xx.c`, a QMK core
file with local commits, on `keyboards/a_jazz/ak820pro/config.h`'s settings.
The 81 LEDs are a matrix of 15 columns (hardware PWM on CT16B0, B1 and B2,
the column pins shared with the key matrix) and 18 rows (6 key rows times R,
B, G; plain GPIO, the mux select). One row is lit at a time. The period
match on CT16B1 is the row ISR, `rgb_callback()`, at priority 3.

| Part of one slot | µs | Source |
|---|---|---|
| PWM period, the row lit | 53.3 | 256 ticks at 4.8 MHz (`SN32F2XX_RGB_PWM_FREQ`) |
| ISR body, LED work | 160 | measured: 30 `pwmDisableChannel`/`pwmEnableChannel` calls at ~5 µs |
| key scan, every third slot | ~84 | measured: 261 µs body with the scan against 160 without |
| entry, exit, hooks, latency | ~17 | derived: 258 less the rest |
| **slot** | **258** | measured: 3,876 ISR/s, health page 4 |

- **3,876 slots a second, a field rate of 215 Hz, 72.8% of the CPU**
  (health page 4, `ak820health.py --isr`; [docs/leds.md](../docs/leds.md),
  "CPU budget").
- **Derived: the LED is lit about 21% of each slot.** The ISR disables every
  column and deselects every row near its start
  (`shared_matrix_rgb_disable_output()`), writes the next row's 15 duties,
  selects the row at its end, and only then re-arms the three counters to
  `0xFFFF` so a clean period starts. One 53 µs period per 258 µs slot. The
  rest is the ISR with the outputs off. Not yet seen on a scope; the stage 1
  gate measures it as current (below).
- **What the timer does when the ISR cannot run is not settled.** By the
  code, the period match only resets the counter (`MRnRST`,
  `hal_pwm_lld.c:318`; `MRnSTOP` sits behind `SN32_PWM_USE_ONESHOT`, which
  nothing in the tree defines), so the counter free-runs through a stall
  with the last row still selected, and the 09-01 artifact showed what that
  looks like: one row at ~18× brightness for the stall. The 240 fps clips of
  the clock chip's hold-off show the opposite, every row dimming alike and
  none hot ([`history/pcf-flicker-20261027/`](../history/pcf-flicker-20261027/README.md)),
  which that README explains as the timer stopping at each period's end.
  The code and the clips disagree (Q4). The design below does not depend on
  which is right: it makes the stall state dark by configuration.
- **The scan** (`quantum/matrix.c`, `matrix_read_cols_on_row()`, called from
  the ISR): `select_row()` re-asserts output mode and writes low;
  `unselect_row()` re-asserts output mode and writes high
  (`MATRIX_UNSELECT_DRIVE_HIGH`, `config.h:149`, for the shared columns);
  each mode assert is a read-modify-write of the port's `MODE` and `CFG`
  (`_pal_lld_setpadmode()`); then 15 single-pin reads, then a 30 µs spin
  (`MATRIX_IO_DELAY`, `sn32f2xx.c:matrix_output_unselect_delay`). Two of the
  key rows, A18 and A19, are on port A.
- **The clock chip's write flickers because of that mode write.** The
  PCF8563 hangs off a software I2C on A14 (SCL) and A15 (SDA)
  (`rtc/rtc.c:25-29`), which emulates open drain by switching SDA between
  input and output (`SW_I2C_USE_OPENDRAIN FALSE`, `halconf.h:21`): a
  read-modify-write of port A's `MODE`, the register the scan's row select
  also read-modify-writes. Two writers of one register, one of them an
  interrupt, lose updates, so `ak820_i2c_xfer_begin()` (`rtc/rtc.c:284`)
  disables CT16B1's interrupt in the NVIC for the whole transaction, up to
  3.4 ms (`i2c_max_cycles`, HC_RTC page 2), and the board is dark for it:
  1 to 6 dark frames at 240 fps. [`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md),
  "Why the PCF holds the lock at all": only for that atomicity. On USB the
  write is deferred to when nobody is looking (`gremlin/pcf-unseen`); off USB
  it follows every sync and still shows.
- **The cleanup blink is the erase, and no driver can touch it.** A
  wear-levelling consolidation erases two 1 KB pages, 1-2 ms each, and
  programs 1 KB back, ~58 ms in one pass. The program windows are invisible
  since the scan runs through them (`sn32f2xx_pgm_scan`, 10-27). An erase
  stalls the core: code executes from the array being erased and the vectors
  cannot move to SRAM ([docs/sn32f299.md](../docs/sn32f299.md), section 2 and
  10), so no interrupt runs, the stopped timer leaves the outputs inactive,
  and the board is dark twice for 1-2 ms. Out of this plan's scope; the
  early cleanup (`flash_tidy.c`) already hides most of them, and the one
  real fix, the emulated EEPROM on the external SPI flash where an erase
  never stalls the core, is a project of its own (noted at the end).
- **LCD fills** once cost 18% of row refreshes during menu repaints, 1.3%
  since the polled send (`30f1e0cfde`, 10-25). Not a target.
- **The rainbow** is geometry: the fringe on a saccade scales linearly with
  the slot gap, 18.6 arc-minutes at 215 Hz against 3.8 at 1,046 Hz
  ([docs/leds.md](../docs/leds.md), "The rainbow is a GEOMETRY problem").
- **The instruments.** Health page 4: `isr_entries`, the body's sum, min and
  max in 5.33 µs ticks (CT16B5 at 187.5 kHz; too coarse for the body this
  plan aims at, see D10), `row_samples[]`, `row_gap_max` (ms, ~4.6 today),
  `raw_edges` against `key_presses` (two edges a press when nothing is
  eaten). The stall counters (`stall>25` must be 0; `ge25`). HC_FLASHW page
  4 (fills, cleanups). HC_RTC page 2 (`i2c_max_cycles`). The INA228 logger on
  white's pack, and R1's per-load method
  ([docs/test-bench.md](../docs/test-bench.md)). JD's 240 fps camera with
  `vid_rows.py` and `vid_events.py`. ⚠️ **The wake rig is gone** (10-23):
  relay 1 presses nothing, so there is no machine-pressed key. The scan's
  gates are the on-board counters and VIA's key tester under JD's hands.
- **The power model depends on the drive.** `battery.c` charges the LEDs at
  `P_RGB_R_NW` 3,681 nW per unit of the red channels' time-weighted sum,
  and its green and blue siblings (`battery.c:583`, fitted by
  `scripts/rgb_fit.py` from `sn32f2xx_led_drive_take()`). Any change in how
  long a unit of value lights the LED moves those coefficients.
- **RAM is at the floor:** heap gap 224 B on the dev build, 128 B the
  floor (C5). Flash 241 KB of 256.

## Goals and non-goals

- **G1. No flicker at the clock chip's write**, on USB and off, measured
  on camera as zero dark frames at a forced write.
- **G2. The ISR at or under 20% of the CPU** (from 72.8%).
- **G3. A field rate at or above 800 Hz** (from 215), the rainbow fringe
  under 5 arc-minutes.
- **G4. Every stored value lights the board as it does today, within 10%.**
  No conversion of the EEPROM's or the profiles' values; the battery
  model's coefficients survive, re-verified.
- **G5. Ten bits of duty available**, so a later dimming curve and white
  balance have room without coarsening the dim end.
- **G6. No key lost:** `row_gap_max` at or under today's, `raw_edges`
  twice `key_presses` under typing, `stall>25` zero, every key and the knob
  seen in VIA's key tester, a night's soak clean; with the rig rebuilt,
  every machine press registered ("The key-press rig", below).
- **G7. The wireless link unchanged or better:** ACK timeouts a frame and
  UART overruns at their baselines over a typing burst and a night.
- **Non-goals:** the consolidation's erase blink (above); the effects; the
  LCD path; the backlight tick; new RAM (none: the two colour buffers exist
  and the tables go in flash).

## The design

### D1. A board-local driver; ChibiOS's PWM driver off for the three timers

`keyboards/a_jazz/ak820pro/rgb/rowisr.c` (the name is open), selected by
`"driver": "custom"` in `keyboard.json` with the board's
`rgb_matrix_driver_t`. `mcuconf.h` turns `SN32_PWM_USE_CT16B0/1/2` off; the
driver sets the timers up itself and owns CT16B1's vector
(`SN32_CT16B1_HANDLER`). The core file `drivers/led/sn32f2xx.c` stops being
compiled for this board; its local commits stay in the branch for the other
SN32 boards and for `UPSTREAM-CONTRIBUTIONS.md`.

The exported API every caller in the board uses is kept with the same names
and contracts: `sn32f2xx_init/flush/set_color/set_color_all`,
`sn32f2xx_led_load`, `sn32f2xx_led_drive_take`, `sn32f2xx_led_committed_dark`,
`sn32f2xx_led_commits`, `sn32f2xx_pgm_scan`, `sn32f2xx_set_power_scale`,
`sn32f2xx_blank`, `sn32f2xx_set_scan_only/scan_only_active` (dev),
`sn32f2xx_sleep_enterI/exitI`, and the health hooks
`sn32f2xx_isr_enter_hook/exit_hook`, `input_note_row_scan`,
`input_note_consume`, `matrix_scan_custom`, `matrix_can_read`.

### D2. The per-period sequence, LED-only slots (two of every three)

**The period match stops the counter and does not reset it** (`MRnSTOP`
set, `MRnRST` clear, on CT16B1's MR12 and on B0's and B2's MR9). In PWM mode
1 every channel's output went inactive at its own match, so a stopped
counter holds every column off: a stall of any length is dark by hardware,
never a hot row. The ISR then does, in this order:

1. Deselect the old row: one `BCLR` on its port. (Atomic: the SN32 PAL's
   pin writes are `BSET`/`BCLR`, `hal_pal_lld.h:330-411`.)
2. Write the 15 match registers for the next row's channel (R, B or G):
   `MR[ch] = duty_lut[value]`, with the `0x5A` key in bits 31:24 on CT16B0
   and B2 (none on B1; [docs/sn32f299.md](../docs/sn32f299.md), "The write
   key"). The timer-and-channel map is `SN32F2XX_PWM_COL_MAP`, resolved at
   init into a table of register addresses and a key word per column.
3. Select the new row: one `BSET`.
4. Restart the three counters on one boundary: `TC = 0` (read-write,
   p. 125) and then `TMRCTRL` with `CEN` (the key on B0 and B2; `CEN` set
   last), or `CRST` then `CEN` if Q5 finds a stop clears `CEN` and `CRST`
   self-clears within a few cycles. The three stores sit ~50 ns apart, a
   tick or so at 24 MHz; the timers stay locked because their periods are
   equal and each is restarted every slot. Today's `TC = 0xFFFF` re-arm
   exists because the counter free-runs; it goes.
5. Clear the period flag by writing `IC` with exactly the bits read from
   `RIS`, never wider.

No channel disable, no enable: the outputs are already inactive after the
match, the row pin is what blanks and lights, and the match registers are
written while no row is selected. About 25 stores: a body of 2-4 µs. No
ChibiOS call; the ISR takes no lock, since nothing it touches is shared
with a thread but the front colour buffer (D8).

### D3. Scan slots (every third)

Before step 2 of D2, with the old row deselected:

1. Take the PWM off the columns: `PWMIOENB = 0` on B1, and the precomputed
   `PWMCTRL` words with the IOEN bits clear on B0 and B2 (plain stores of
   precomputed values, not read-modify-writes). The columns' GPIO mode is
   input with pull-up from init and is never written again; clearing IOEN
   hands the pin back to it.
2. Select the key row: `BCLR` on its port. The key rows are push-pull
   outputs from init, high when idle (the board's electrical scheme
   already, `MATRIX_UNSELECT_DRIVE_HIGH`), and their mode is never written
   again. **This is the whole of the clock-chip fix:** no mode or
   configuration write of any port from interrupt context.
3. Settle for the measured time (Q1), not 30 µs. The columns were left
   high by the period match, so the unpressed ones have nothing to rise
   through; the pressed ones are pulled low through the diode by the row's
   push-pull drive, which is fast.
4. Read port A and port C `DATA` once each, and pick the 15 column bits out
   with shifts and masks (A4-A7, C0-C9, C14, in `MATRIX_COL_PINS` order).
   `input_note_row_scan()`, `shared_matrix[]`, the dirty flag and
   `matrix_scan_custom()`'s locked compare-and-copy stay as they are.
5. Unselect the row: `BSET`. No spin: the PWM is about to drive the
   columns, so the pull-up rise never matters to the LEDs.
6. Put the PWM back on the columns: the three precomputed IOEN words.

Then D2's steps 2-5. A scan slot's extra cost: about 10 stores, two loads,
the settle. QMK's `matrix_read_cols_on_row()` is weak and no longer called.

### D4. The PWM clock, the period and the resolution

**24 MHz (PRE 1) and a period of 1,024 ticks: 42.7 µs, 10 bits of duty.**

Why those: luminance is the duty within the period times the fraction of
the slot the row is lit. Today that is (value / 256) × 0.21 = 8.2 × 10⁻⁴
per unit of value. With a 42.7 µs period lit for ~84% of a ~51 µs slot and
the raw 8-bit value as the duty over 1,024, it is (value / 1,024) × 0.84 =
8.2 × 10⁻⁴ per unit. **The same brightness for every stored value, by
construction** (G4), with the top three-quarters of the duty range left
for the curve of D9. Stage 1's gate measures the ratio as current and the
LUT's single scale factor corrects any residual before anything else is
built on it.

Expected, to be read back on health page 4 (D10): slots of ~51 µs LED-only
and ~60 scan, ~17,700 a second, a field rate near 1 kHz, the ISR at
15-20% of the CPU, the LED lit ~80% of the time. Each key sampled every
~1 ms (from 4.6).

The fallback if the bottom codes misbehave (Q2): **12 MHz and 1,024 ticks**,
an 85 µs period, 83 ns a tick, a field rate near 550 Hz, and the same
luminance per unit to within a few percent, because the lit fraction
rises with the longer period. Both are luminance-neutral; the choice is
the transistors'.

The one-tick pulse is 42 ns at 24 MHz against 208 ns today. The column
transistors (bipolar, per the driver's own diagram) may not pass the
lowest few codes faithfully. JD's dim use sits around value 64 with
`VAL_STEP 2`, far above that; the gate looks at values 1 to 8 by eye.

### D5. Around internal-flash writes and erases

Unchanged in behaviour. The ISR runs between the masked program windows,
as it does since 10-27 (`sn32f2xx_pgm_scan` default true; the 09-01
row-deselect guard kept behind the flag for the dev write test's
comparison). An erase stalls the core and the stopped timer leaves the
board dark; nothing here changes that.

### D6. The clock chip's transaction

With D3 in, nothing in interrupt context writes a port's `MODE` or `CFG`
(to be confirmed by grep at build time: the 20 kHz tick writes `DATA`
only, sleep entry runs with interrupts locked). `ak820_i2c_xfer_begin()`
and `_end()` stop disabling CT16B1's interrupt; the dev-build `od_*`
accounting stays. The scan runs through the transaction and the board
stays lit. The transaction grows by the ISR's share of the CPU: at 15-20%
that is 2.6 ms → ~3.1 ms (Q3 asks the bracket's tolerance); at today's 73%
it would be ~9 ms, which is why this is stage 2, after the cheap ISR, not
part of stage 0.

Once the camera shows nothing at a forced write, `pcf-unseen`'s deferral
on USB has no reason left, and a follow-up retires it so the clock chip is
written at once again, on USB and off (its own small change, JD's call).

### D7. Sleep, scan-only and the bootloader

- `sn32f2xx_sleep_enterI()`: the interrupt's enable off, the IOEN words
  clear, every row deselected, the counters stopped. `sn32f2xx_sleep_exitI()`:
  clear the stale flag in `IC` and the NVIC pending bit, restart the
  counters as D2 step 4 does, enable. The contract `sleep.c` relies on is
  unchanged (I-class, no lock calls).
- Scan-only (dev, light sleep's sizing): one key row per period at
  `SN32F2XX_SCAN_ONLY_TICKS`, no LED work, its own row counter, kept.
- `sn32f2xx_blank()`: every LED pin to high impedance before the jump to
  the ROM bootloader, kept verbatim.

### D8. The flush and the colour buffers

`led_state[]` (the ISR's) and `led_state_buf[]` (rgb_matrix's) exist today,
243 B each. Option A keeps the masked `memcpy` in `sn32f2xx_flush()`: ~10 µs
with interrupts off, so a row starts up to 10 µs late once per frame, a
fifth of a slot, invisible. Option B swaps pointers instead: the flush marks
the back buffer ready, the ISR swaps at a period boundary, and the next
flush first copies front to back unmasked before `set_color()`'s
change checks run against it. No mask at all and no torn frame by
construction, for no RAM. B is the design; A is the fallback if B's extra
copy shows in the main-loop budget.

The drive accounting (`drive_now[]`, `sn32f2xx_led_drive_take()`) and
`power_scale` are kept as they are: the power model's unit is a unit of
value times time, and D4 keeps that unit's meaning.

### D9. The resolution pipeline, for the dimming curve and white balance

The colour state stays 8-bit. The ISR writes `MR = duty_lut[value]`, a
256-entry table of 16-bit words in flash (512 B), one lookup per column per
slot (15 loads, under 1 µs). Stage 1 ships it as the identity (0..255 of
1,024). Stage 3 fills it: a perceptual curve, and white balance as a
per-channel multiply before the lookup (15 multiplies a slot) or three
tables (1.5 KB flash). No RAM, no main-loop cost, and the curve is a
setting the menu can preview the way Font does. **The curve changes the
look of stored values**, so stage 3 is where that conversation happens,
not before; stage 1 is neutral.

### D10. Measuring a 5 µs body

Health page 4's hooks read CT16B5 at 187.5 kHz: 5.33 µs a tick, useless
for a body this short. On dev builds the hooks read CT16B4 instead, which
is free ([docs/sn32f299.md](../docs/sn32f299.md), section 7), run as a
16-bit counter at 48 MHz (wraps every 1.37 ms, fine for a body under 20
µs). The health record's `isr_ticks_*` fields change units; the health
version byte bumps and `ak820health.py --isr` prints both. `isr_entries`
a second is the field rate's measure and needs nothing.

## Stages and gates

Each stage is its own flash, lands on black (gremlin's board) for a day
first, then on white. "Any flickering is a non-option" (JD, 09-03) is the
standing bar: every stage includes a hue sweep, a Solid near-white hold, the
dev write test page (one, ten, cleanup), and JD's eyes.

### Stage 0: the scan without mode writes

The board's own `matrix_read_cols_on_row()` inside the current ISR: D3's
steps 2-5 (row select and unselect by `DATA` only, the port-wide reads, the
measured settle). The I2C hold-off stays until stage 2.

Gates: every key and the knob in VIA's key tester, once each, and a run of
JD's typing; `row_gap_max` ≤ 5 ms; `raw_edges` = 2 × `key_presses` under a
typing burst; `stall>25` = 0; ACK timeouts a frame at the baseline over a
burst; a night's soak clean; health page 4's body down by the 30 µs spin
and the pin reads (expect ~230 µs with the scan, from 261).

### Stage 1: the driver on direct registers at 24 MHz and 1,024 ticks

D1, D2, D3's IOEN handling, D4, D7, D8, D9's identity table, D10.

Gates: `isr_entries` ≈ 17,000-18,000 a second and the body ≤ 8 µs on the
48 MHz hooks; the ISR's share ≤ 20%; the field rate ≥ 800 Hz;
**luminance: the INA228 at a fixed Solid colour before and after, within
10%** (R1's method, on white's pack, two minutes each side, noted in the
drain's README as every test during a drain is; if off, the LUT scale is
set to the measured ratio and the gate re-run); values 0, 1, 2, 4, 8 and 255 by eye and camera at Solid
white (0 is off, 1 is dimmer than 2, 255 is not dark); a hue sweep with no
wrong-colour row; the write test page; deep sleep 10 of 10 on 2.4G and 5 of
5 on BT with the waking key kept; scan-only on a dev build; the bootloader
jump leaves no row lit; the 660-byte clock-digit blits clean for a night on
a dev build (the SPI0 race's exposure window moves with the ISR's length,
[docs/leds.md](../docs/leds.md); `invariant_fail` stays 0); `stall>25` = 0;
ACK timeouts and overruns at or under baseline; `row_gap_max` ≈ 1 ms; the
battery model's drive accounting continuous across the flash (the drain on
white keeps its settings).

### Stage 2: the clock chip's transaction unmasked

D6. Gates: a forced PCF write (dev op) filmed at 240 fps shows no dark
frame, on USB and off; `i2c_max_cycles` ≤ ~3.5 ms; the bracket's seed
within its budget (Q3); a night of syncs with the PCF settled every time
(`history/mainline-soak-20261020/`'s check). Then the follow-up: retire
`pcf-unseen`'s deferral.

### Stage 3: the dimming curve and white balance

D9's tables, a menu setting with a preview, the conversation about what
stored values should look like under the curve, and the gauge's
coefficients refitted with `rgb_fit.py` if the curve changes the per-unit
drive. Planned after stages 0-2 are on white; not detailed here.

## Risks the history says to respect

- **SPI0 shares priority 3.** A 188 µs ISR delayed the DMA half-transfer
  handler by 188-258 µs; a 5 µs one delays it by 5-60 µs. The race that
  window exposed is fixed (`c57623d0d2`), but the exposed transfer sizes
  move, so the clock-digit soak is a stage 1 gate.
- **`IC` is write-1-to-clear:** write what `RIS` returned, nothing wider.
  The lost-completion bug on SPI0 was exactly this. (The ChibiOS LLD's
  `pwm_lld_disable_channel()` ORs into `IC`, `hal_pwm_lld.c:408`; the new
  driver does not inherit it.)
- **The write key** on CT16B0 and B2 for `MR`, `MCTRL`, `PWMCTRL`, `TMRCTRL`;
  **`CEN` last.**
- **The ends of the duty range:** a match equal to the cycle length is a
  one-tick pulse, a match of 0 a constant level (section 7). Value 0 must
  be truly off and the top value truly full; the +1 period lesson of 08-31.
  With the period match at 1,023 (the counter runs 0..1,023), a channel's
  match must never exceed 1,023: a channel above the period match never
  goes inactive, so at the stop point it is still driving, and a stall
  would light that column. The table's top entry is 1,023, a duty of
  1,023/1,024, and nothing can write a larger match.
- **No ChibiOS call from the ISR** that is not I-class. The old driver's
  `pwmEnableChannel()` from interrupt context unlocked interrupts mid-ISR;
  the new one calls nothing.
- **The priority table stands:** UART2 0, USB 1, the 20 kHz tick 2, the row
  ISR 3. A cheaper ISR changes no priority.
- **Stop without reset, never both.** A period match with `STOP` and
  `RST` together would park the counter at 0, where every channel with a
  non-zero match is active: a stall would light the whole selected row at
  full duty. `STOP` alone parks it at the period, where every channel is
  inactive.
- **The torn frame** (D8), **the flash-program path** (D5), **the
  three-timer phase** (D2 step 4), **the stored values' brightness** (D4).
- **Flash and RAM:** today's driver is 2,576 B of code and 482 B of
  constant data, and ChibiOS's PWM layer 3,188 B (`arm-none-eabi-size` on
  the via build's objects), both of which leave; the new driver and its
  512 B table should come in under that. No new static RAM (548 B of bss
  today, the two colour buffers and the bookkeeping, carried over). The
  heap gap is checked by `build.sh` (floor 128 B).
- **The drain on white:** stage 1 is luminance-neutral so the drain's
  power model stays valid; the flash keeps its settings as every flash
  since P5a does.

## The key-press rig: rebuilt, it is the scan's gate

JD offered (10-31) to rebuild the wake rig, broken 10-23, with some
soldering, and to make it better than before. It should be rebuilt before
stage 0 lands on white: the scan change is the one part of this plan that
can lose keystrokes, and a rebuilt rig turns that gate from JD's typing and
VIA's key tester into a count. The old rig's record
([docs/test-bench.md](../docs/test-bench.md), "The wake rig"): the relay
closed on a 5 ms command, 15 ms presses registered 10 of 10, 200 of 200
reached the Mac at typing speed, and `relay_press_test.py`,
`keydrop_test.py` and `deep_cycles.py` still exist, counting at the board
(`raw_edges`, `key_presses`) and at the Mac (the F19 listener, the session
unlocked).

What "better than before" should mean, most valuable first:

1. **Strain relief.** A lead tearing off its switch is what retired it.
2. **Two keys on different key rows**, the old (0,13) and one low on the
   board, so a scan fault on one row cannot hide behind another; the same
   column for both covers the shared-column leak case
   (`MATRIX_UNSELECT_DRIVE_HIGH`).
3. **An optocoupler, or a small MOSFET, across each switch's contacts**
   instead of relay contacts, driven by a Pico or similar the Mac commands
   over USB serial: silent, bounce-free presses timed to the millisecond,
   down to 1 ms, and a press-to-host latency the listener can pair to the
   command. Presses of 8-12 ms sit on the debounce boundary (5 ms stable,
   `sym_defer_pk`) and are where a slower or unfair scan shows first. Keep
   the isolation the dry contacts gave: the keyboard and the rig share
   nothing but the opto's light. The relay board stays for the power cut.

With it, the gates read:

- **Stage 0 and stage 1:** 1,000 presses at 15 ms dwell and 1,000 at 25 ms,
  every one registered at the board and at the Mac, under each stressor in
  turn: idle, a hue sweep (the flush), a Solid frame, an LCD repaint, a
  burst of settings writes, a 2.4G request stream (the UART-latency
  matrix's "200 relay presses during a request stream", now 1,000); and
  the same at 8, 10 and 12 ms to map the debounce boundary before and
  after, which must not move. Press-to-host latency: its distribution
  before and after stage 1, expected to lose the ~4.6 ms sampling term.
- **Stage 2:** presses through forced PCF writes, every one registered.
- **Sleep:** `deep_cycles.py` through the ladder again, 100 of 100, the
  waking key kept.

Without the rig, the manual gates in the stages stand, and each stage
spends a day longer on black before white.

## Open questions, and what settles each

- **Q1. The column settle after the row select.** A dev hook that selects a
  row, then reads port C repeatedly and counts reads until the value is
  stable, over a pressed and an unpressed key; or the scope, if one is
  found. Expect single microseconds.
- **Q2. The bottom codes at 42 ns pulses.** By eye and camera at values 1
  to 8 (stage 1's gate); the fallback is 12 MHz.
- **Q3. The PCF bracket's tolerance of a 15-20% longer read.** `rtc.c`'s
  bracket math and `docs/clock.md`'s seed budget; a night of syncs.
- **Q4. What a stall shows today, and what a stopped timer holds.** The
  code says the counter free-runs (a hot row); the clips say dark. Settle
  it on a dev build at Solid white: hold CT16B1's interrupt off for 5 ms by
  a dev op (the `od_mask_*` machinery is there) and look, by eye and on
  camera. Then, on the new configuration, the same test must show dark on
  all three timers (B0 and B2 have no callback and are restarted by B1's
  ISR): the PWM-mode description (section 7, "PWM behaviour") says a
  channel is inactive from its match to the period's end, which is where a
  stopped counter sits.
- **Q5. Restarting a stopped counter.** Whether a period match with `STOP`
  clears `CEN` (then `CEN` must be written again each slot), whether `TC`
  can be written while stopped, and how many cycles `CRST` takes to
  self-clear; the manual (p. 125-126) and a dev build with the 48 MHz hooks.
  Decides between `TC = 0; CEN` and `CRST; CEN` in D2 step 4.
- **Q6. Whether B0 and B2 should stop at their period at all** or free-run
  with reset and be re-synced each period. Simpler ISR against a
  one-tick phase offset; decided on a dev build with the camera.
- **Q7. The ChibiOS prologue and epilogue.** The handler can use
  `OSAL_IRQ_PROLOGUE/EPILOGUE` (a reschedule check it never needs) or be a
  bare vector; measure the difference on the 48 MHz hooks and keep the
  cheaper one that the kernel's debug checks accept.

## Noted, not planned: the consolidation's erase

The only fix for the erase blink is an EEPROM whose erases do not stall the
core: the external SPI flash (QMK has a SPI-flash wear-levelling backend;
the board's SPI1 is shared with the LCD blit DMA and has its own driver in
`graphics/lcd_bus.c`, so it is a project), or a compensation the eye might
accept (the stall is software-initiated, so the driver could boost the
fields either side; unproven). Both belong in `BACKLOG.md`, not here.

## Comparison with codex's design

To be written when [`review-codex-row-isr-design-2026-10-31.md`](review-codex-row-isr-design-2026-10-31.md) lands.
