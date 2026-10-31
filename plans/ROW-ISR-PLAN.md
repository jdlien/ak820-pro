# The row ISR rewrite: the RGB driver on direct registers, and the flickers it ends

Status: **revision 14, READY for stages 0-3 (10-31, the fourteenth
readiness review, [`review-codex-row-isr-review14-2026-10-31-raw.md`](review-codex-row-isr-review14-2026-10-31-raw.md));
stages 4 and 5 sufficiently specified once 0-3 pass; the 62.5 µs cadence
an experiment.** Nothing built. Next: stage 0 (the baseline) once the rig
and the witness exist; JD's optocouplers, resistors and wire arrive 11-01.
Every stage lands on white first, where the bench is, and on black after
its gates pass (corrected after the review; revision 0 had black first,
carried from the diagnostics' pattern unexamined).
How it got here: Claude's
revision 0 was written blind ([`ROW-ISR-PLAN-rev0.md`](ROW-ISR-PLAN-rev0.md));
codex (gpt-6-astra, xhigh, read-only) designed independently from the brief
[`design-prompt-row-isr.txt`](design-prompt-row-isr.txt), verbatim in
[`review-codex-row-isr-design-2026-10-31-raw.md`](review-codex-row-isr-design-2026-10-31-raw.md);
revision 1 merged the two ("Comparison with codex's design", the decision
log); a second codex session (gpt-6.1-sol, xhigh) audited the merge from
[`design-collab-prompt-row-isr.txt`](design-collab-prompt-row-isr.txt),
verbatim in [`review-codex-row-isr-collab-2026-10-31-raw.md`](review-codex-row-isr-collab-2026-10-31-raw.md),
and every finding is dispositioned in "Revision 2" at the end; a fresh
gpt-6-astra session then reviewed revision 2 for readiness
([`review-codex-row-isr-review1-2026-10-31-raw.md`](review-codex-row-isr-review1-2026-10-31-raw.md):
NOT READY, six must-fixes for stages 0-3, three for stages 4-5), and
"Revision 3" at the end dispositions each; the second review
([`review-codex-row-isr-review2-2026-10-31-raw.md`](review-codex-row-isr-review2-2026-10-31-raw.md):
NOT READY, four must-fixes for stages 0-3, two for stage 5; stage 4 called
sufficient) is dispositioned in "Revision 4"; the third review
([`review-codex-row-isr-review3-2026-10-31-raw.md`](review-codex-row-isr-review3-2026-10-31-raw.md):
NOT READY, three must-fixes, all on the measurement side; stages 4 and 5
called sufficient) in "Revision 5"; the fourth
([`review-codex-row-isr-review4-2026-10-31-raw.md`](review-codex-row-isr-review4-2026-10-31-raw.md):
NOT READY on one remaining area, the timestamp's validity) in "Revision
6"; the fifth ([`review-codex-row-isr-review5-2026-10-31-raw.md`](review-codex-row-isr-review5-2026-10-31-raw.md):
NOT READY, the same area, the bound still circular) in "Revision 7";
the sixth ([`review-codex-row-isr-review6-2026-10-31-raw.md`](review-codex-row-isr-review6-2026-10-31-raw.md):
NOT READY, the RTC's slewed period defeats any agreement test) in
"Revision 8", which scopes the claim to what this chip can prove; the
seventh ([`review-codex-row-isr-review7-2026-10-31-raw.md`](review-codex-row-isr-review7-2026-10-31-raw.md):
NOT READY, three consistency points on that scoping and a note that the
universal guarantee is withdrawn) in "Revision 9", which fixes the three
and records the withdrawal as the owner's decision; the eighth
([`review-codex-row-isr-review8-2026-10-31-raw.md`](review-codex-row-isr-review8-2026-10-31-raw.md):
accepts the withdrawal; NOT READY on two precise points, excluded-mode
recovery and the injections' predicted outcomes) in "Revision 10"; the
ninth ([`review-codex-row-isr-review9-2026-10-31-raw.md`](review-codex-row-isr-review9-2026-10-31-raw.md):
the recovery fix met; NOT READY on two points in stage 2's acceptance
specification, the rate-dependence of a residue and the no-USB test's
setup) in "Revision 11"; the tenth
([`review-codex-row-isr-review10-2026-10-31-raw.md`](review-codex-row-isr-review10-2026-10-31-raw.md):
NOT READY on one point, how the injected silences are timed) in
"Revision 12"; the eleventh
([`review-codex-row-isr-review11-2026-10-31-raw.md`](review-codex-row-isr-review11-2026-10-31-raw.md):
NOT READY on the same point's endpoint contract) in "Revision 13"; the
twelfth ([`review-codex-row-isr-review12-2026-10-31-raw.md`](review-codex-row-isr-review12-2026-10-31-raw.md):
NOT READY on one sentence of it, a silence-length promise the guard
cannot make) in "Revision 14"; the thirteenth re-read revision 13 by a
slip and repeated it; the fourteenth read revision 14 and found no
must-fix.
Grows out of two backlog entries: "Row-ISR body: the one lever that lifts
scan rate, main loop and field rate together" (09-03) and "The LED blink
at an internal-flash write" (10-27), [`BACKLOG.md`](BACKLOG.md). Owner:
the Mac session.

JD's reason for doing it (10-31): the flicker and dimming fixes. The CPU and
the field rate are the bonus.

## What is known (measured 09-03 and since; derived where marked)

The driver is `qmk_firmware-ak820pro/drivers/led/sn32f2xx.c`, a QMK core
file with local commits, on `keyboards/a_jazz/ak820pro/config.h`'s settings.
The 81 LEDs are a matrix of 15 columns (hardware PWM on CT16B0, B1 and B2,
the column pins shared with the key matrix) and 18 mux rows (6 key rows times
three colours; plain GPIO, the mux select). One mux row is lit at a time. The
period match on CT16B1 is the row ISR, `rgb_callback()`, at priority 3.

| Part of one slot | µs | Source |
|---|---|---|
| PWM period, the row lit | 53.3 | 256 ticks at 4.8 MHz (`SN32F2XX_RGB_PWM_FREQ`) |
| callback body, LED work | 160 | measured: the minimum; 30 `pwmDisableChannel`/`pwmEnableChannel` calls at ~5 µs |
| key scan, every third slot | ~84 | derived: (187.9 − 160) × 3 from the mean; the 261 µs maximum is not a clean scan figure |
| outside the callback | ~70 | derived: 258 less 188; the PWM period, the IRQ machinery, the re-arm |
| **slot** | **258** | measured: 3,876 ISR/s, health page 4 |

- **3,876 slots a second, a field of 215.3 Hz, 72.8% callback occupancy**
  (health page 4, `ak820health.py --isr`; [docs/leds.md](../docs/leds.md),
  "CPU budget"; [docs/hardware.md](../docs/hardware.md)). ⚠️ The 72.8% is
  elapsed time inside the callback at 5.33 µs resolution: it includes
  preemption by higher-priority handlers and excludes the handler's own
  entry, exit and re-arm. The complete handler has never been measured;
  D10 does, with its own caveats stated there.
- **Derived: the LED is lit about 21% of each slot.** The callback disables
  every column and deselects every row near its start, writes the next row's
  15 duties, selects the row at its end, and only then re-arms the three
  counters to `0xFFFF` so a clean period starts (`sn32f2xx.c:782-800`). One
  53 µs period per 258 µs slot. In continuous-equivalent duty, channel code
  255 lights its LED (53.1 µs / 4.644 ms) = **1.14%** of the time, against
  the 5.56% a 1-in-18 mux could give. Not yet seen on a scope; conditional
  on one bounded pulse per slot, which Q4 settles.
- **What the timer does when the ISR cannot run is not settled.** By the
  code, the period match only resets the counter (`MRnRST`,
  `hal_pwm_lld.c:318`; `MRnSTOP` sits behind `SN32_PWM_USE_ONESHOT`, which
  nothing in the tree defines), so the counter free-runs through a stall
  with the last row still selected, and the 09-01 artifact showed what that
  looks like: one row at ~18× brightness. The 240 fps clips of the clock
  chip's hold-off show the opposite, every row dimming alike and none hot
  ([`history/pcf-flicker-20261027/`](../history/pcf-flicker-20261027/README.md)),
  which that README explains as the timer stopping. The code and the clips
  disagree (Q4). The design does not depend on which is right: it makes the
  stall state dark by configuration.
- **The colour order within a field is not what the comment says.** By the
  code (`update_pwm_channels()`, `sn32f2xx.c:491-559`: the key row advances
  at `current_row % 3 == 2`, the colour case is 0 → B, 1 → G, 2 → R), mux
  pin 3k lights key row k's blue, 3k+1 its green, and 3k+2 key row k+1's
  red; for key row k the software submits R at slot 3k−1, B at 3k, G at
  3k+1, modulo 18. So one key's three colours come in consecutive slots,
  and the physical pin order must be B, G, R-of-the-next-row for colours to
  render, not the "R, B, G per group" of `config.h:6`. The rainbow fringe
  today is one to two slots, 258-516 µs, **3.1-6.2 arc-minutes** at 200°/s,
  not the 18.6 the LED doc computes from a third of a field. Which physical
  LED each mux pin drives is still unverified (Q6).
- **Derived, unmeasured: today's light is not uniform across columns.** The
  callback releases the 15 columns one `pwmDisableChannel()` at a time,
  ~5 µs each, *before* it deselects the mux row (`sn32f2xx.c:472-490`), and
  the period match has reset the counter, so the row keeps cycling while
  the columns go off in order: column 0 is released ~6 µs after the match,
  column 14 ~80 µs after, more than a whole extra 53 µs period. If that
  reading is right, the right-hand columns (`MATRIX_COL_PINS` order) are
  lit up to about twice as long per slot as the left, and "today's pulse
  energy" is a per-column quantity. Stage 0 looks for it on camera
  (per-column means at Solid white; Q12). The rewrite makes every column
  equal, which would change the look; brightness preservation is then
  defined on the board mean, with the gradient's removal recorded as a
  deliberate change.
- **A bounds defect in the current driver.** The hardware-PWM path reads
  `led_state[led_index]` without the `NO_LED` check that only the
  software-PWM path compiles (`sn32f2xx.c:515-534`). Nine of the 90 matrix
  positions have no LED ((0,14) the knob, (3,12), (4,1), (4,14), (5,3),
  (5,4), (5,5), (5,7), (5,8)), and each position is visited once per colour,
  so **27 lookups a field read past the 81-entry array**. Nothing lights,
  since no LED is there, but it is an out-of-bounds read on the input path.
  The new driver produces explicit zeros.
- **The scan** (`quantum/matrix.c:136-194`, `matrix_read_cols_on_row()`,
  called from the ISR): `select_row()` re-asserts output mode and writes
  low; `unselect_row()` re-asserts output mode and writes high
  (`MATRIX_UNSELECT_DRIVE_HIGH`, `config.h:149`, for the shared columns);
  each push-pull assert is a read-modify-write of the port's `MODE`
  (`_pal_lld_setpadmode()`, `hal_pal_lld.c:202-245`: output mode touches
  `MODE` only; an input-with-pull-up mode touches `MODE` and `CFG`). Then 15
  single-pin reads. The row helpers wrap these in `ATOMIC_BLOCK_FORCEON`,
  which is thread-class `chSysLock()`/`chSysUnlock()` run from the ISR
  (`atomic_util.h:21`), the same kind of wrong-context call as the PWM
  API's. The "30 µs" unselect delay is `TIME_US2I(30)` iterations of a
  compiler barrier, about six: short and uncalibrated, not 30 µs
  (`sn32f2xx.c:158`). Where the ~84 µs goes is unattributed between the two
  mode writes, the 15 reads and the hooks; stage 0 measures it. Two of the
  key rows, A18 and A19, are on port A.
- **The clock chip's write flickers because of that mode write.** The
  PCF8563 hangs off a software I2C on A14 (SCL) and A15 (SDA)
  (`rtc/rtc.c:25-29`). The fallback driver drives transmitted bits push-pull
  with `palWriteLine()` and switches SDA to an input with pull-up for every
  read bit and ACK (`SW_I2C_USE_OPENDRAIN FALSE`, `halconf.h:21`;
  `hal_i2c_lld.c:212-240`): each switch is a read-modify-write of port A's
  `MODE` (and `CFG`), and `MODE` is the register the scan's row select also
  read-modify-writes. The row helpers assert output mode on pins that are
  already outputs, so their read-modify-writes are idempotent and no lost
  update has been demonstrated; the hold-off exists for ownership, to keep
  the I2C's mode changes atomic by design
  ([`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md)), and that is reason
  enough for it: `ak820_i2c_xfer_begin()` (`rtc/rtc.c:284`) disables
  CT16B1's interrupt in the NVIC for the whole transaction, up to 3.4 ms
  (`i2c_max_cycles`, HC_RTC page 2), and the board is dark for it: 1 to 6
  dark frames at 240 fps. [`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md),
  "Why the PCF holds the lock at all": only for that atomicity. It is the
  only place in the board that holds the row interrupt off (grep
  `CT16B1_IRQn`). The transaction's deadline is 10 ms by the macro
  (`rtc/rtc.c:36`; a stale comment says 20) and 5 ms for deep sleep's
  pre-sleep read and wake recovery. On USB the write is deferred to when
  nobody is looking (`gremlin/pcf-unseen`); off USB it follows every sync
  and still shows.
- **The cleanup blink is the erase, and no driver can touch it.** A
  wear-levelling consolidation erases two 1 KB pages, 1-2 ms each, and
  programs 1 KB back, ~58 ms in one pass today. The program windows are
  invisible since the scan runs through them (`sn32f2xx_pgm_scan`, 10-27).
  An erase holds off every interrupt: the flash routines themselves run
  from SRAM (`hal_efl_lld.c:30`), but every vector and handler lives in the
  array being erased and the vectors cannot move to SRAM
  ([docs/sn32f299.md](../docs/sn32f299.md), sections 2 and 10), so nothing
  can be serviced for 1-2 ms a page. What the board shows meanwhile is
  conditional on Q4 (dark by the clips, a lit row by the code); under D2 it
  is dark. The pass also blocks the main loop, so a press and release both
  inside it are overwritten in the rolling matrix before the consumer sees
  them; faster scanning does not change that, though a cheaper handler
  should shorten the pass (it is ~73% ISR today) and stage 7 remeasures it.
  Both out of this plan's scope ("Noted, not planned", below).
- **LCD fills** once cost 18% of row refreshes during menu repaints, 1.3%
  since the polled send (`30f1e0cfde`, 10-25). Every late start of the
  callback lengthens the field today, because the next period starts when
  the callback ends; D2's fixed slot ends that mechanism.
- **The dim end is already compressed before the driver.** `rgb_matrix`
  builds with `USE_CIE1931_CURVE` (`common_features.mk:480,638`; the via
  build's `cflags.txt`), so `hsv_to_rgb()` (`quantum/color.c:22`) maps
  value 64 to channel 12 and 128 to 48 before the driver sees a byte, and
  the mixing after it quantizes to bytes too. The driver's duty is linear
  in that byte. The dim-end coarseness is the 8-bit plateau of the CIE
  output, so finer dimming must be carried from the conversion in more than
  8 bits; a wider table inside the driver cannot restore it (D9).
- **The instruments.** Health page 4: `isr_entries`, the body's sum, min and
  max in 5.33 µs ticks. Page 3 (`health.c:306`): `row_samples[]`,
  `row_gap_max` (the worst gap between samples of one row, 6 ms in the
  record, [docs/hardware.md](../docs/hardware.md); the mean interval is
  ~4.6 ms), `raw_edges` against `key_presses`; ⚠️ `raw_edges` is a consume-side
  count of the bits that differ between the old and fresh matrices
  (`health.c:122-133`; `cooked_changes` counts the differing rows), not an
  ISR transition count: a press and release
  both inside one consume interval are invisible to it, and the bench has
  recorded one-short raw counts with every press delivered
  ([docs/test-bench.md](../docs/test-bench.md), "Measured"); the cause is
  known: `input_note_consume()` runs before the locked compare-and-copy, so
  an ISR update that lands between them reaches debounce without entering
  the count (`BACKLOG.md`, "`raw_edges` undercounts by design; it could be
  exact", 10-19; `sn32f2xx.c:1067`). `raw_edges` counts changed bits,
  `cooked_changes` differing rows. Page 4 has four
  reserved bytes left (`health.c:360`). The stall counters (`stall>25`
  must be 0; `ge25`). HC_FLASHW page 4 (fills, cleanups). HC_RTC page 2
  (`i2c_max_cycles`). HC_PEEK reads SRAM only (`hid_protocol.c:991`), so a
  timer register capture needs a dev op; the 20 kHz tick's gap monitor
  records gaps ≥ 128 µs only (`overrun_diag.c:198`). The INA228 logger on
  white's pack and R1's per-load method; the power map's LED figures: full
  white adds ~189 mW, value 128 ~43 mW, value 64 ~18 mW
  ([docs/power.md](../docs/power.md)). JD's 240 fps camera with
  `vid_rows.py` and `vid_events.py`. ⚠️ **The wake rig is gone** (10-23):
  relay 1 presses nothing; JD is rebuilding it ("The key-press rig", below).
- **The power model depends on the drive.** `battery.c` charges the LEDs at
  a base, an 8.64 mW lit overhead while any LED is on, and `P_RGB_R_NW`
  3,681 nW per unit of the red channels' time-weighted sum with its green
  and blue siblings (`battery.c:556-583`, fitted by `scripts/rgb_fit.py`
  from `sn32f2xx_led_drive_take()`). Any change in how long a unit of value
  lights the LED moves the colour coefficients; a cadence change can move
  the lit overhead even when pulse energy is preserved.
- **RAM is at the floor:** heap gap 224 B on white's dev build and 152 B on
  black's (`fcb7ae00b4`), 128 B the floor (C5): 96 and 24 B to spare. Flash
  240,944 B of 256 KiB on white's dev load. Today's driver object is 2,324 B
  of code, 252 B of rodata, 482 B of initialized writable data (the three
  configurations at 160 B each) and 548 B of bss; ChibiOS's PWM layer is
  3,188 B of code plus 304 B in `hal_pwm.o`, and its three driver objects
  (24 B each) and configurations total ~552 B of RAM. Object totals are not
  linked savings; the linker map after stage 2 is.

## Goals and non-goals

- **G1. No flicker at the clock chip's write**, on USB and off: zero dark
  frames on camera at a forced write.
- **G2. The complete row handler at or under 20% of the CPU** (from a 72.8%
  callback occupancy that undercounts it).
- **G3. A field of 444 Hz at the first cadence** (from 215), the colour
  fringe 1.5-3 arc-minutes at 200°/s; **889 Hz as an experiment** with its
  trade declared (D4), 0.75-1.5 arc-minutes.
- **G4. Every stored value lights the board as it does today:** the
  incremental LED power after subtracting the build's own dark baseline,
  per colour and at low drive, within 3% at the stages that keep the
  cadence and 5% at the one that changes it, forward and backward holds;
  plus fixed-exposure optical checks, including the lowest non-zero codes
  (values 1-16), which value 64's channel 12 does not exercise. Brightness
  is defined on the board mean (Q12). No conversion of the EEPROM's or the
  profiles' values; the battery model's interface survives and its
  coefficients are refitted per cadence.
- **G5. Pulse timers at 48 MHz, 20.8 ns a tick, with a per-cadence window**
  (D2's literal terminals), of which brightness preservation uses ~1,236 of
  2,048 codes (10.3 bits) at the first cadence: 1.66× of headroom for a
  later dimming curve and white balance if stage 2's calibration lands at
  k = 10, 1.04× at k = 16 (D2). More headroom means a wider
  window and an earlier arm deadline, a trade stage 6 may make.
- **G6. No key lost:** `row_gap_max` at or under today's, `stall>25` zero,
  every key and the knob seen in VIA's key tester, a night's soak clean;
  with the rig rebuilt, every machine press registered at every link of
  the chain under ordinary settings writes, and short-tap acceptance no
  worse than the baseline the repaired rig collects in stage 0. A forced
  consolidation is characterized separately (Q8), not held to this.
- **G7. The wireless link unchanged or better:** ACK timeouts a frame and
  UART overruns at their baselines over a typing burst and a night; the
  20 kHz tick's rate and worst gap unchanged.
- **G8. A late handler fails dark, never hot:** no stall of any cause can
  leave a row lit, and a slot the handler misses is counted, not replayed.
- **Non-goals:** the consolidation's erase blink and its main-loop block;
  the effects' algorithms; the LCD path; the backlight tick; the priority
  table; black's open deep-sleep reset (kept observable, not touched).

## The design (revision 2)

### D1. A board-local driver and matrix; ChibiOS's PWM service off

`keyboards/a_jazz/ak820pro/rgb/rowisr.c` (the name is open), selected by
`"driver": "custom"` in `keyboard.json` with the board's
`rgb_matrix_driver_t`, and `CUSTOM_MATRIX = lite` with the board's
`matrix_init_custom()` and `matrix_scan_custom()` (`common_features.mk:580,665`;
`matrix_common.c:145-174` calls debounce after the consume). `mcuconf.h`
turns `SN32_PWM_USE_CT16B0/1/2` off **and `halconf.h` turns `HAL_USE_PWM`
off**: with all three off and the service on, the PWM header fails the
build with "no CT peripheral assigned" (`hal_pwm_lld.h:93`). The driver
programs the timers itself through **explicit register offsets from the
timer bases** (`docs/sn32f299.md`, section 7's table), not the LLD's
structs: their small-timer `MR[]` is declared with five entries on this
target and the LLD indexes `MR[9]` through it (`sn32_ct.h:96,196,216`), an
out-of-array access that happens to land. The column map loses its `&PWMDn` pointers for timer
indices. The core file `drivers/led/sn32f2xx.c` stops being compiled for
this board; its local commits stay in the branch for the other SN32 boards
and for `UPSTREAM-CONTRIBUTIONS.md`.

`CUSTOM_MATRIX = lite` excludes `quantum/matrix.c` from the build
(`common_features.mk:673`), so every scan the board runs, interim or final,
is board-local code: stage 2's **interim scanner** is a faithful copy of
`matrix_read_cols_on_row()` and its row helpers with I-class locking
(`chSysLockFromISR`), the mode writes it still makes being harmless while
the I2C hold-off stays; stage 3 replaces it with D3 step 3.

**The scan starts in `matrix_init_custom()`, before `rgb_matrix` exists,**
and that function **primes all six rows synchronously** (one bounded pass
of D3's scan step per row, or a wait on the readiness mask) before it
returns, because Bootmagic's first `matrix_scan()` must already hold
samples that can start debounce (`quantum/keyboard.c:459`,
`bootmagic.c:63`); a timer merely started leaves that first scan empty.
Later RGB initialization must not clear acquired matrix state. Builds with
RGB disabled keep scanning.

The exported API every caller in the board uses is kept with the same names
and contracts: `sn32f2xx_init/flush/set_color/set_color_all`,
`sn32f2xx_led_load`, `sn32f2xx_led_drive_take`, `sn32f2xx_led_committed_dark`,
`sn32f2xx_led_commits`, `sn32f2xx_pgm_scan`, `sn32f2xx_set_power_scale`,
`sn32f2xx_blank`, `sn32f2xx_set_scan_only/scan_only_active` (dev),
`sn32f2xx_sleep_enterI/exitI`, and the health hooks
`sn32f2xx_isr_enter_hook/exit_hook`, `input_note_row_scan`,
`input_note_consume`, `matrix_scan_custom`, `matrix_can_read`. Renaming is
a later cleanup, not part of this. The board defines its own LED count and
configuration interfaces rather than inheriting `RGB_MATRIX_SN32F2XX`'s side
effects.

### D2. The slot schedule on CT16B4; the PWM timers one-shot

**The row interrupt moves to CT16B4**, which is free
([docs/sn32f299.md](../docs/sn32f299.md), section 7), clocked at HCLK,
`PRE 0`, its MR9 the slot length with `MR9IE` and `MR9RST` set and no stop:
the keyed `MCTRL = 0x5A600000` (bits 21 and 22), `MR9 = 5,999` at the first
cadence and `2,999` at the second, the actual period verified on hardware
rather than trusted to the −1 arithmetic. The slot is fixed: **125 µs
first**, a 444 Hz field; **62.5 µs as the experiment** of D4, 889 Hz. The
handler's cost no longer sets the field, and a late start moves a pulse
inside its slot instead of lengthening the field.

**CT16B0, B1 and B2 become one-shot pulse generators with no interrupt:**
48 MHz, `PRE 0`; the terminal match (B0's and B2's MR9, B1's MR12) with
**`STOP` set and `RST` clear** (B0/B2: keyed `MCTRL = 0x5A800000`, bit 23;
B1: `MCTRL2` bit 8), every duty match with interrupt, reset and stop clear.
**A stop match clears `CEN`** (`sn32_ct.h:357`), so each slot's restart
writes `TC = 0` and then `TMRCTRL` with `CEN`, in that order. `TMRCTRL` is
not a keyed register (`docs/sn32f299.md`, "The write key": `MCTRL`, `MRn`,
`EM`, `PWMCTRL`, `PWMmNIOCTRL`, `PWMmNDB`); `MR`, `MCTRL` and `PWMCTRL`
writes on B0, B2 and B4 carry `0x5A` in bits 31:24; B1 has no key.

In PWM mode 1 a channel is low (the LED on; the columns are active-low)
until its match and high after it, so a counter parked at its terminal
match holds every column off: **a stall of any length is dark by
hardware.** Two rules keep that true. **Never set `STOP` and `RST`
together:** by the two actions' individual descriptions (`sn32_ct.h:352-360`;
the combination is not documented, so this is an inference) that parks the
counter at 0, where every non-zero channel is active, and a stall would
light the whole selected row; stop-only, witnessed on the waveform, is the
configuration this plan trusts. **Every channel
match stays below the terminal match:** the manual treats a match equal
to the cycle length as a one-tick pulse and says nothing for a match
above it, which would never go inactive and would hold its column lit
through a stall; the conservative rule is strictly less, and D4's widths
are far below.

**The terminal window is a per-cadence constant, and the arm is admitted
against the whole window, not against the slot's largest width.** A
counter runs to its terminal whatever the duties are, so a dim late slot
admitted on its short pulse would still be running when the next handler
wrote a brighter duty and selected its row: with `TC` below the new match
the output is active, and the row would light at the old phase before the
restart. The rule: arm only if the time left in the slot covers the
terminal window plus the three arms' skew, the handler's tail and the
guard; otherwise the slot is omitted. So the window sets the latest
admissible arm, and a shorter window buys tolerance of late starts. At
125 µs the window is **2,047 ticks (42.7 µs)**, an arm deadline ~80 µs into
the slot (a USB handler at enumeration, ~85 µs, still forces an omission);
at 62.5 µs it is **1,023 ticks (21.3 µs)**, a deadline ~40 µs in. The
preserved widths of D4 (1,235 and 618 ticks) are 60% of each window, which
leaves 1.66× of headroom for D9 **if stage 2's calibration lands at k = 10**;
at k = 16 the preserved full value is ~1,977 ticks and the headroom 1.04×.
The widths and the headroom are conditional on that measured k, not the
3.3× a 4,096 window would give; stage 6 may widen the window and pay in
deadline if it wants more. At stage 2's
cadence, the measured stage-0 slot (~258 µs), the pulse timers already run
at 48 MHz with **the literal terminal 4,095** (an 85.3 µs window, an arm
deadline ~165 µs into the slot), and the scale table absorbs the clock
change and the measured baseline (D4): today's one clean 53.3 µs pulse is
2,560 ticks, so k ≈ 10, and a baseline brightened by the sequential
column release fits up to k = 16 (255 × 16 < 4,095) with upward headroom
for every channel; today's terminal 255 is never reused, since channel 255
could not stay strictly below it. The three literal terminals are 4,095,
2,047 and 1,023; the window lengths are one more each. The parked state, every output
inactive, is the state the handler always finds the timers in; stage 0b
proves it with the waveform witness ("The key-press rig", item 4).

The pin routing stays: `SN_PFPA` B0 `0x3332`, B1 `0x0F00`, B2 `0x0000`;
the column map resolved into a **`const` table in flash** of match-register
addresses and a key word per column (an init-built table would spend ~120 B
of the RAM D1 recovers). The control words are precomputed whole: B1's
`PWMENB`/`PWMIOENB` mask `0xFF0`; B0's `PWMCTRL` `0x5AF0000F` active
(mode 1 encodes as zero; enables `0xF`, IO bits at 20+n) and `0x5A00000F`
with the columns released; B2's `0x5AE0000E` and `0x5A00000E`. Stores, not
read-modify-writes.

Every reference to the row interrupt follows the move: `CT16B1_IRQn` in
`rtc/rtc.c`, the sleep hooks, the health hooks, the dev diagnostics.
Nothing may keep masking an obsolete vector, and no PWM object or vector
may survive by accident (a stage 2 gate).

### D3. The per-slot sequence

The GPIO masks are fixed by the pin lists (`keyboard.json:142-145`,
`config.h:9`), checked by the collaborator:

| | GPIO0 (A) | GPIO1 (B) | GPIO2 (C) | GPIO3 (D) |
|---|---|---|---|---|
| mux rows | `0x00B00` (A8, A9, A11) | `0x00030` (B4, B5) | `0x03C00` (C10-13) | `0x73F00` (D8-13, D16-18) |
| key rows | `0xC0000` (A18, A19) | `0x8C000` (B14, B15, B19) | | `0x80000` (D19) |
| shared columns | `0x000F0` (A4-7) | | `0x043FF` (C0-9, C14) | |

Columns are inputs with pull-ups and key rows push-pull outputs high from
init, and **the running ISR never writes `MODE`, `CFG`, `CFG1` or a whole
`DATA` register**: only `BSET` and `BCLR` (`hal_pal_lld.h:330-411`). That
is the whole of the clock-chip fix. The handler keeps ChibiOS's
`OSAL_IRQ_PROLOGUE/EPILOGUE`: a bare handler at the lowest priority can be
preempted by an OS-aware one whose epilogue does not do the outermost
return's work (`chcore.c:124`), so the port's contract is kept (Q7 closed).
Each slot, in order:

1. Read the scheduler's `RIS`, write `IC` with exactly those bits. **Count
   elapsed slots by phase-aware reconstruction**, not from the flag: `RIS`
   has one bit per source, and twenty missed matches read as one. The
   handler keeps the pair (CT16B5 system time, scheduler `TC`) from its
   last service; now it reads both **in one short critical section, two
   loads, so no preemption can land between them and enter the
   reconstruction as its own duration**, and takes the boundaries crossed as
   round((Δt − Δphase) / slot), where Δt is the system time difference at
   5.33 µs resolution and Δphase the `TC` difference in µs: subtracting the
   phase makes the quotient an exact multiple of the slot to within the
   resolution, so rounding is unambiguous at both cadences and latency
   changes do not shift it. CT16B5 is 16 bits at 187.5 kHz and wraps every
   349.525 ms, and no difference of its own readings can see a wrap: a
   350 ms gap reads as ~475 µs, a 700 ms one as ~949 µs. **No clock on this
   chip can measure, from the inside, a silence of every interrupt longer
   than that:** every counter is 16 bits or wraps within a second, the
   RTC's sub-second counter is reset and re-periodized by the clock
   discipline (`rtc/rtc.c:570,1384`) so no agreement test against it can
   be proven, and the existing `platforms/chibios/timer.c` extension and
   the stall counters share the blind spot and have always lived with it.
   **The plan therefore withdraws any universal long-gap guarantee: the
   owner's decision, revision 9.** What follows is what the chip can prove,
   with the one case outside it named, bounded by construction, and caught
   on the bench by a witness.

   **The time source and its state machine.** One shared 32-bit extension
   of CT16B5, with its own last-observation stamp, kept by observation as
   `timer.c` keeps the main loop's, by two observers from interrupt
   context: the 20 kHz backlight tick (priority 2, `indicators.c`) every
   50 µs and the row handler every slot. An observation is a critical
   section of a few instructions: read `TC`, compare it with the stamp,
   fold a wrap into the high word if it went backwards, store the stamp.
   The extension is VALID or INVALID:

   - An observation whose raw gap **since the extension's last
     observation** (not since the observing consumer's own previous
     service) reads 8 ms or more moves it to INVALID: by the inventory
     below nothing silences every interrupt that long, so such a reading
     is abnormal and may be a wrap's remainder.
   - Deep sleep entry, degraded mode (the watchdog disarmed after
     repeated resets, `watchdog.c:76`, compiled into every build and ended
     only by the next boot) and the dev diagnostic lock mode
     `OD_LOCK_TRANSACTION` (the system lock through a whole clock-chip
     transaction, up to its 10 ms deadline; `od_i2c_lock_mode` 0,
     `overrun_diag.h:34`, ended by the transaction's end) move it to
     INVALID on entry **and hold it there until the mode ends**: each is
     an exclusion flag, and no re-prime happens while any exclusion is
     active.
   - The extension carries a **loss generation**, a counter incremented at
     every transition to INVALID and never otherwise. Every consumer
     snapshot records it. An interval whose end generation differs from
     its start generation touched INVALID, whether or not an observer has
     re-primed in between, and is excluded from every statistic and
     counted as exactly one epoch loss, however many checks rejected it.
   - INVALID becomes VALID only by a re-prime, and only while no exclusion
     is active: the next observation sets the stamp and the high word
     afresh; the row handler, at its next service, sees the generation
     changed, counts the one epoch loss, re-primes its own previous
     snapshot, becomes the first service of a fresh epoch, reconstructs
     nothing across the gap, and resumes. Nothing is ever replayed.
   - The handler's reconstruction (the boundaries crossed, the latency,
     the duration) uses the extension only while VALID and the generation
     unchanged, at entry, at the arm and at exit, each from a coherent
     snapshot of the extension, its generation and the scheduler's `TC`.
     The handler's own gap may be anything up to **one hour**, the
     supported consumer interval (the extension is 32 bits of 5.33 µs and
     wraps after 6 h 22 min; a row-only interval longer than an hour is
     INVALID, with its generation bumped): a row-only hold-off leaves the
     tick observing.

   **What that proves, by case.** (1) Any interruption of the row handler
   alone, up to the one-hour consumer bound (the clock chip's hold-off,
   any future one, a run of omissions): exact, **provided another observer
   kept the extension VALID through it**, which the tick does whenever it
   runs; in scan-only, with the tick stopped, the handler is the only
   observer, and a hold of the handler is then a silence of every observer
   and falls under cases 2 to 4. (2) An **observation gap** under 8 ms: exact. The guard
   measures the gap from the extension's last observation to the next,
   never the silence itself. The gap exceeds the silence by an offset at
   each end that depends on the mode in force: with the tick running, up
   to its 50 µs period plus its service latency, which higher-priority
   handlers lengthen and which no nominal figure bounds
   (`overrun_diag.c:198`; [`UART-LATENCY-PLAN.md`](UART-LATENCY-PLAN.md));
   with the tick stopped and the handler in scan-only, up to its 625 µs
   slot plus its own latency. Those offsets are **recorded from the
   observers' synchronized stamps, not assumed**. The plan therefore
   promises nothing about a silence's length, only about the gap: a gap
   under 8 ms is exact, a gap of 8 ms or more is INVALID, and a given
   silence can fall on either side depending on its phase and the mode,
   which is what the near-threshold injections exercise.
   (3) An observation gap from 8 ms to 349.5 ms: INVALID, declared, by the
   guard. (4) A silence of every interrupt of 349.5 ms or
   longer that returns: the guard reads only the remainder, so it may
   alias; **not detected on battery**. So the bound the proof needs is
   349.5 ms, not 2 ms: no code path may silence every interrupt that long.
   The inventory, for release builds and dev builds in their default lock
   mode: the per-line flash program window, 10-20 µs masked
   (`hal_efl_lld.c:332`); a page erase, 1-2 ms with the core stalled
   ([docs/sn32f299.md](../docs/sn32f299.md), section 10); the flush copy,
   10-16 µs; the matrix helpers' atomic blocks and the handler's own
   section, microseconds; the UART2 handler's drain loops and the USB
   handler at priorities 0 and 1, tens of microseconds an event
   (`overrun_diag.c:198` lists them as the tick's interferers), whose
   accumulated effect the guard measures directly rather than bounding a
   priori; deep sleep, invalidated explicitly. The excluded modes,
   invalidated on entry: `OD_LOCK_TRANSACTION` (10 ms at most, far under
   the bound, excluded so the inventory stays exact) and degraded mode. A
   new path that reached the bound would be a defect, and one the UART
   overrun counters would show whenever the module was sending at the
   time, since 350 ms of silence loses its frames; they are not an
   independent silence detector.

   (5) **On USB, case 4 is caught after the fact** by a clock the core
   cannot stop: the USB frame counter `SN_USB->FRMNO`, 11 bits advanced by
   the host's 1 kHz SOF (`rtc/rtc.c:639`; modulus 2.048 s, exact to the
   host's ±500 ppm), under a continuity contract. The snapshot takes
   `FRMNO`, the USB status `INSTS` and a bus-event generation the USB
   handler increments on every `BUS_RESET`, `BUS_SUSPEND`, `BUS_RESUME` and
   `BUS_WAKEUP` it services ([docs/sn32f299.md](../docs/sn32f299.md),
   "USB"). `FRMNO` is trusted for an interval only if at its end no
   bus-event flag is pending and the generation is unchanged; a suspend,
   reset or disconnect during the silence is latched by the peripheral
   and makes the interval INVALID, never healthy. The comparison is
   modular, CT16B5's residue against `FRMNO`'s, with a tolerance of 3 ms
   plus 0.2% of the span. The clock-rate envelope behind it: HCLK is the
   IHRC, measured 0.01-0.04% off the host's clock on this board
   ([docs/sn32f299.md](../docs/sn32f299.md), "IHRC"), and the host's SOF
   is within ±0.05%, so the two rates differ by at most 0.09%; 0.2% is
   more than twice that envelope. **The USB proof's scope is 13 s**, its own figure: the
   two moduli, 349.525 ms and 2.048 s, first coincide at 131.072 s, come
   no closer than 49 ms inside 13 s (at 2.1 s) against a tolerance of at
   most 29 ms there, and next come within 6 ms at 14.33 s, which is
   outside the scope. The watchdog is a separate bound with its own
   uncertainty, stated as an estimate, not a guarantee: its timeout is
   189 × 128 × 16 cycles of the ILRC
   ([docs/sn32f299.md](../docs/sn32f299.md), "Watchdog"), 11.5 s at this
   unit's ~33.6 kHz, about 8.7-12.4 s over the temperature graph the
   manual gives for the ILRC (a graph, not a specified limit), and 12.3 s
   as once recorded ([docs/hardware.md](../docs/hardware.md)). Intervals
   beyond 13 s are outside the USB proof's scope, whatever the watchdog
   did; degraded mode is INVALID throughout on its own rule. The guard and the frame
   counter are two checks on one interval: whichever rejects first, the
   interval is INVALID and the loss is one. So with USB active and
   the bus healthy, which is the bench's state, a returning silence of any
   length up to 12 s reads INVALID.

   Deep sleep re-primes by the first tick after wake, and the handler
   treats everything before it as INVALID, so the order of the wake hooks
   (`sleep.c:604`) does not matter. `matrix_init_custom()` primes before
   the first scan, the row handler the only observer until the tick starts
   in post-init (`ak820pro.c:65`). Light sleep's tick stop (`sleep.c:109`)
   leaves the handler observing every scan-only slot, 625 µs apart, so the
   extension stays VALID and the tick re-joins without a re-prime. The
   same snapshot and the same rules serve entry, the arm and exit. Sleep, scan-only
   and a cadence change re-prime the pair. Boundaries crossed minus one is
   the count of slots not serviced. **At most one service per epoch, and
   the serviced epoch advances only at the arm, inside step 6's section:**
   an invocation that finds it is still inside the epoch the previous
   invocation armed for does nothing but count.
2. Deselect every mux row: four `BCLR` stores, one per port. The PWM
   outputs are parked inactive (D2), so this is belt and braces, and it is
   what makes a late slot dark.
3. **Scan slots only (every third serviced slot):** release the columns by
   writing the three released control words; select the key row with one
   `BCLR`; settle (2 µs first, Q1 measures); read GPIO0 and GPIO2 `DATA`
   once each and assemble the 15 column bits in `MATRIX_COL_PINS` order;
   `input_note_row_scan()`; write `shared_matrix[]` and the dirty flag as
   today (the rolling matrix, the six-row priming mask and the locked
   consume-copy-clear stay; no sticky edge bits,
   [`MATRIX-PUBLISH-PLAN.md`](MATRIX-PUBLISH-PLAN.md), the shipped contract);
   deselect with one `BSET`; restore the three active control words. The
   columns were left high by the terminal match, so the unpressed ones have
   nothing to rise through; the pressed ones are pulled low through the
   diode by the row's push-pull drive. No spin after the deselect: the PWM
   drives the columns next. The key-row rotation advances on every
   serviced scan slot and stays fair on its own.
4. Write the 15 match registers for the next mux row from the front frame
   (D8) through the scale table: a load, a lookup and a store each, keyed on
   B0 and B2, zeros for the nine holes.
5. Select the mux row for the next `(key row, colour)` from a table that
   encodes the order Q6 confirms (initially the code's B, G, R-of-next). The
   LED rotation advances on serviced slots, so a stall resumes where it
   stopped and every row gets its turn. Stage 0b verifies that selecting
   the row before the restart lights nothing (the outputs are parked).
6. **Inside one critical section, under 2 µs with a 5 µs ceiling:**
   take a fresh coherent snapshot (system time, `TC`, `RIS`) and re-derive
   the epoch against the pair of step 1. If a boundary was crossed since
   step 1 (the flag set again, or the reconstruction says so), the handler
   was preempted across a slot while it worked: do not arm, count an omission, and leave the
   flag for the pending interrupt, which re-enters immediately after exit
   and services the new epoch (that re-entry is the one service of that
   epoch). Otherwise, if the time left covers the terminal window plus the
   arms' skew, the tail and the guard (D2), restart the three pulse timers
   together (`TC = 0`, then `CEN`); if not, leave the row dark and count
   the omission against that row and colour. The check and the arm share
   the section so UART or USB cannot preempt between "fits" and `CEN`.
   Never replay missed slots.

The counters the handler keeps, cheaply: slots elapsed, handlers serviced,
pulses emitted, pulses omitted (and per row and colour), the longest run
of omissions, the emitted width sums per colour (D8). About 30 stores and
20 loads in a LED-only slot; 10 more and two port reads in a scan slot.
Target: a complete handler of **≤ 20 µs mean at 125 µs slots (16%) and
≤ 12 µs at 62.5 µs (19.2%)**, measured by D10, with separate gates on the
latency tail; at stage 2, the LED part under 10 µs plus the interim scan's
cost as stage 0b attributes it (~28 µs a handler averaged if the old
figure holds).

### D4. The pulse window and brightness preservation

Continuous-equivalent duty is the pulse length over the field. Today,
code 255 → 53.1 µs / 4.644 ms = 1.14% (conditional on Q4). At a 125 µs slot
(a 2.25 ms field) and 48 MHz ticks, the same light needs

    w(c) = round(c × (48 / 4.8) × (215.33 / 444.44)) = round(4.845 c)

so code 255 → **1,235 ticks, 25.7 µs**, not 4,095: about 1,236 usable
levels, 10.3 bits. At the 62.5 µs slot, w(c) = round(2.4225 c), code 255 →
618 ticks (12.9 µs), 619 levels, 9.3 bits. The factor is **calibrated, not
assumed**: stage 5's gate measures a fixed Solid colour's incremental LED
power before and after and sets the scale to the measured ratio before
anything is stored. Exposing the whole 4,096 window at once would raise
the maximum average drive about 3.3×; that headroom belongs to D9, by a
decision, not by accident.

**The second cadence is an experiment with a declared trade**, not the
destination: under plain rounding the lowest codes drift (channel 1 → 2
ticks against an ideal 2.42, about 17% low), which G4's 5% does not cover,
and the usable levels fall to 9.3 bits. It is attempted only after the
first cadence passes every gate, and only if low-code preservation and the
precision path's needs are judged worth 0.75 arc-minutes of fringe. The
arm deadlines are D2's: ~80 µs into a 125 µs slot, ~40 into a 62.5 µs one.
A USB handler at enumeration (~85 µs) can still force an omission, which
G8 makes dark and counted. A late slot that goes from dim to bright is the
transition stage 2 tests, since that is where an unparked counter would
show. A 20.8 ns tick is not optical resolution: the column transistors'
switching bounds how fine the lowest codes get (Q2).

### D5. Around internal-flash writes and erases

Unchanged in behaviour. The handler runs between the masked program
windows as it does since 10-27 (`sn32f2xx_pgm_scan` default true; the 09-01
row-deselect guard kept behind the flag for the dev write test's
comparison). An erase stalls the core; the parked pulse timers hold every
column off and the board is dark for it. The flash-to-LCD DMA drain before
a write (`backing_store_pre_write_hook()`, `ak820pro.c:722`) and the
per-line program masks (`hal_efl_lld.c:332-339`) stay. Stage 7 remeasures
the consolidation pass's length under the cheap handler.

### D6. The clock chip's transaction

With D3 in, nothing in interrupt context writes a port's `MODE`, `CFG` or
`CFG1` (confirmed by grep at build time: the 20 kHz tick writes pins through
`BSET`/`BCLR` only, `indicators.c:111`; sleep entry runs with interrupts
locked; the reviewer found no other interrupt-side mode writer). `ak820_i2c_xfer_begin()`
and `_end()` stop disabling the row interrupt; the dev-build `od_*`
accounting stays; HAL's unlock and relock contract, the bus admission and
the recovery arbitration stay. The scan runs through the transaction and
the board stays lit. The transaction grows by the handler's share: at
16-20% occupancy, 2.6 / (1 − 0.16..0.20) = **3.1-3.25 ms** (Q3 asks the
bracket's tolerance; the 10 ms deadline is far, the 5 ms one around deep
sleep is the one to check). Under today's handler it would be 2.6 / 0.27 ≈
9.6 ms, which is why this is stage 4, after the hot path. In the interim
stages the hold-off follows the interrupt to its new vector.

`pcf-unseen`'s deferral on USB stays until the camera shows nothing at a
forced write; then a follow-up retires it so the clock chip is written at
once again, on USB and off (its own small change, JD's call).

### D7. Sleep, scan-only and the bootloader

- `sn32f2xx_sleep_enterI()`: the scheduler's interrupt off, the released
  control words written, every mux row deselected, the pulse timers and the
  scheduler stopped, the scheduler's pending flag and NVIC bit cleared; the
  columns left as pull-up inputs for the wake. `sn32f2xx_sleep_exitI()`:
  the key rows restored high, the counters restarted, the scheduler's flag
  cleared and its interrupt on, the epoch clock of D3 step 1 re-primed; the
  dark frame kept until the wake's normal rendering lights it (the 10-24
  wake dark-frame fix). The admission and wake sequence in
  `sleep.c:263,444-495,582-612` is unchanged, the deep sleep's SRAM routine
  and its delay (`sleep.c:313-326,535`) untouched; the contract is I-class,
  no lock calls; any `CRST` wait is bounded. Black's unexplained deep-sleep
  reset (`BACKLOG.md:152`) stays open and observable: its phase diagnostics
  are preserved, and the gates include long, fully unplugged BT sleeps and
  charging and knob wakes on both boards, not only short rig cycles.
- Scan-only (dev, light sleep's sizing): no LED work, one key row per slot
  at a longer slot (`SN32F2XX_SCAN_ONLY_TICKS`'s 625 µs, now the
  scheduler's MR9), its own row counter, kept.
- The bootloader: **one idempotent quiesce on every jump route**, including
  Bootmagic's direct jump and the raw-HID jump (`watchdog.c:121-131`
  overrides `bootloader_jump()`): stop the scheduler, write the released
  control words, deselect, then every LED pin high-impedance, with no
  pending interrupt able to undo it, and safe to call before full RGB
  initialization; the watchdog stop, the RAM magic and the reset unchanged.

### D8. The flush, the frames and the power accounting

`led_state[]` (the ISR's front frame) and `led_state_buf[]` (rgb_matrix's)
exist today, 243 B each. **The flush keeps the masked `memcpy` for the first
implementation**: 10-16 µs with interrupts off once per rendered frame
(`sn32f2xx.c:971`), so a slot starts up to 16 µs late, which the guard of
D3 step 6 must be tested against with the other delays. It keeps the
meaning of "committed": the front frame the ISR lights from the next slot
on. The cheaper alternative, kept open, is a pointer swap of the two
existing buffers under a short lock followed by an unmasked copy of the new
front into the back (so effects that update only some LEDs keep their
state): the same next-slot visibility, no masked copy. Codex's prepared
18×15 frames adopted at a field boundary are rejected separately: 1,080 B
of RAM and a gap between a frame submitted and a frame displayed.

**"Committed dark" means the front frame is dark**, which is what
`sn32f2xx_led_committed_dark()`'s callers in sleep and `flash_tidy.c` ask;
it does not prove a programmed pulse has ended, and sleep's explicit
blanking in D7 stays authoritative.

The handler writes `MR = scale_lut[byte]`, a 256-entry table of 16-bit
words in flash (512 B), calibrated at stage 2 against the stage-0 baseline
and rescaled at each cadence (D4). Fifteen lookups a slot.

**Power accounting follows the physical output, with the contract spelled
out.** The handler accumulates the emitted width sum per colour in three
64-bit accumulators (a 16-bit add with its carry into the upper word; at
1,235 ticks × 81 LEDs × 444 fields a second, ~44 M ticks a second per
colour, a 32-bit sum would wrap in ~97 s), adding nothing for an omitted
pulse; the main loop's `sn32f2xx_led_drive_take()` reads and zeroes them
under a short lock and converts ticks into the model's existing unit,
value times milliseconds: for the linear table, width = k × byte,
**`rgb_ms = Σticks × T_field_ms / k`** (a LED at byte b emits k·b ticks once
per field, so over T ms it emits b·k·T/T_field), the division's remainder
carried into the next take; a non-linear table (stage 6) keeps the same
conversion with the cadence's fixed reference k, so the unit stays an
equivalent linear value times milliseconds and the consumer is unchanged,
and the model's coefficients are refitted because the light per
equivalent unit then follows the curve. **A known constant frame is validated against
the accumulators before any refit**, so a unit error cannot hide inside
new coefficients. So
`battery.c:680`'s energy calculation and its interface survive while their
inputs become what was driven. **`lit_ms` keeps its present meaning**,
elapsed time with any committed channel non-zero (`sn32f2xx.h:81`),
computed from the committed frame as today; it is not replaced by a
lit-slot fraction, which would change saturated-colour and sparse-frame
accounting. A global omission percentage would not do either: a dropped
bright red slot and a dropped empty slot cost differently. Validated on
sparse frames, forced omissions and dark transitions as well as
full-board holds; the coefficients are refitted per cadence on the logger
(stage 5, stage 7), the dark and base terms included.

### D9. The precision path (stage 6)

Because the CIE curve compresses value to an 8-bit channel before the
driver, finer dimming needs a wider conversion, not a wider driver:

- a board-local `hsv_to_rgb16()` (the board already wraps
  `rgb_matrix_hsv_to_rgb()` in `power.c:162` for the power caps) producing
  12-bit channels through a 16-bit CIE table (512 B flash), and a
  `set_color16()` into a 16-bit render buffer and a 16-bit committed frame:
  **972 B together, +486 B over today's two byte buffers**, before any
  metadata, funded by the ~552 B D1 recovers; a single wide front buffer
  cannot hold uncommitted rendering. The masked copy's length is
  remeasured at 16 bits;
- used first by a precision Solid effect and then the board-local effects
  (RAINFALL, DRIFT); QMK's stock effects keep the 8-bit path through the
  scale table. A precision effect appends **both** a stable profile effect
  id (`rgb_effects.c:15`; `menu/profiles.c:355` applies them) and a QMK
  custom effect entry, which are different namespaces, and updates the
  effect-name table and the VIA definition; existing profiles render as
  they do;
- white balance as three fixed-point gains applied in the conversion (243
  multiplies per changed frame, in the main loop), compiled defaults first
  with RAM-only dev controls; a persisted setting needs a versioned
  migration, because the 218 B profile block is fully occupied
  (`menu/profiles.h:20-50`) and the macro buffer is at 19 B;
- `power_val_cap()`, the lights-out scale and DRIFT's own value scaling
  preserved; no second gamma on top of CIE bytes;
- options with their costs, for later: a colour-slot order that makes a
  chosen pair adjacent (a table, free); per-key trims (243 B, deferred
  until variation is measured); temporal dithering (a four-field pattern
  repeats at 111 Hz at the first cadence, so not at the dim end).

Stage 6 is where the look of stored values under a curve is decided; every
earlier stage is neutral. Its RAM is proven by a complete allocation
ledger before it is built and by the linker map and stack watermarks on
each build flavour and each board after.

### D10. Measuring the handler

Health page 4's hooks read CT16B5 at 187.5 kHz, 5.33 µs a tick, useless for
a 10 µs handler. The new hooks read **the scheduler's own `TC`** (CT16B4 at
48 MHz, 0..5,999) at entry and at exit, wrap-aware: the entry value is the
latency from the slot boundary, valid only when D3 step 1's epoch check
says exactly one boundary was crossed since the last service, which is
what an ordinary fresh service looks like (`TC` is modulo a slot: a 5 ms
delay would read as a small latency without the check; with more than one
boundary the latency is undefined and the extra slots are counted as
missed); exit minus entry, each a coherent (extended time, `TC`) snapshot taken as
D3 step 1 does and each checked against the extension's validity, is the
handler's elapsed time including preemption, with the boundaries crossed
between the two snapshots reconstructed from the pairs, not taken from
step 6, which a preemption after the arm and before the exit would miss,
labelled as such; an interval D3 step 1 calls invalid is excluded from every statistic and
counted as such, and the latency, the duration and the missed-slot
figures of a service are all judged by that one rule; the port's prologue,
epilogue and exception return lie outside the hooks and are bounded from
the port's assembly (`chcore.c:124`, with its two return paths) or by an
independent handler timing on the waveform witness; the slots-elapsed
count against wall time is a cadence check, not a handler measurement.
The record gains the latency
maximum, the complete elapsed sum, min and max, the elapsed and serviced
slot counts, the emitted and omitted pulse counts with the longest run,
and the 20 kHz tick's rate and worst gap, which needs the tick monitor's
threshold lowered from 128 µs on dev builds. Page 4 keeps its fields for
the before/after comparison; the new fields take **a new health page**,
and **both decoders** change: `ak820health.py` and the daemon's
`ak820-agent/src/health.rs:476`, with the health version byte bumped.
`isr_entries` a second remains the field rate's witness.

## Stages and gates

Each stage is one flash, reversible, and lands on white first, where the
bench is: the INA228 on its pack, the relay cable, the data cut, the rig
and the witness, all on Buzz, and every gate below is read there. Black
(gremlin's board) gets each stage after white's gates pass, as the second
unit and the Windows host's transport check, and only when Warren's
deep-sleep diagnostics on it can spare it; it has no bench, so a day on it
before white would measure nothing. `flash.sh` dumps white's RAM battery
log before each flash; what a reset on an experimental build can lose is
the log since that dump. Every stage repeats a hue sweep, a Solid
near-white hold, the dev write test page (one, ten, cleanup) and JD's eyes:
"any flickering is a non-option" (09-03) is the standing bar. Comparisons
are same-session A/B on the same board and power source; scan-rate
differences under ~6% between sessions prove nothing.

### Stage 0: establish truth (the untouched baseline)

On the running firmware: record the token and settings; three health
windows of ≥ 20 s each at idle, under an LCD repaint load, under forced PCF
writes and across a forced cleanup; a fixed-exposure 240 fps clip of each;
INA228 holds at Solid white, red, green and blue at values 64, 128 and 255,
forward and back, with the dark baseline; fixed-exposure optical
references at values 1 to 16, which the later low-code gates compare
against; the measured slot rate, which stage 2 reproduces. Rebuild the
rig, including the witness, and capture today's ordinary pulse train on
one column and one mux row, which is the first look at Q4 and Q12 and the
reference every later waveform gate compares against. Output: the
baseline every later gate compares against.

### Stage 0b: a bounded diagnostic build

HC_PEEK cannot read timer registers and the mask probe holds the global
lock, so a dev build adds two ops: a register capture of the three timers'
`MCTRL`, `MCTRL2`, `TMRCTRL` and `PWMCTRL`, and a row-only interrupt
hold-off of a chosen length. With it: Q4 (a 5 ms hold at Solid white: hot
row or dark, by eye, camera and INA228), Q6 (single-key, single-colour
patterns per key row with a slow tagged slot sequence, since untagged
full-board video cannot order sub-frame slots), the scan's cost
attributed. Also, on the three timers configured as D2 wants: match values 0,
1 (the glitch test, a single 20.8 ns tick), the smallest entry the scale
table will emit (k, ~208 ns), terminal−1 and an invalid terminal, with
service deliberately delayed, the counter's `TC` and `CEN` recorded, the
output on the witness, and the gross optical output (Q5).

### Stage 1: isolate ownership

D1's ownership only, with **the ChibiOS PWM service and the existing
callback mechanism kept**, so the pulse machinery is unchanged: the
driver's code moves board-local unchanged (the same `pwmEnableChannel()`
calls, the same end-of-callback re-arm), the custom matrix with the
interim scanner, the scan started and primed in matrix init, the hold-off
on the same vector. Equivalence is **measured, not assumed**: the scanner's
locking and the init order do change execution time. The PWM service
comes out in stage 2 with the scheduler. Gates: Bootmagic with valid
settings and after a settings reset; RGB disabled; every build flavour;
only the intended PWM owners in the linker map (the three PWM drivers
remain at this stage); the callback's rate and elapsed metric within 3% of
stage 0; the early quiesce safe before RGB init; no new phantom or missing key; `row_samples[]` fair;
`row_gap_max` no worse than stage 0's under the same load (the record's
worst is 6 ms, [docs/hardware.md](../docs/hardware.md)), windows that
contain the retained PCF hold-off judged apart; stalls, UART errors and ACK timeouts at baseline;
incremental LED power within 3% in the holds; every bootloader route works
and the bootloader stays dark at `0x7140`; deep sleep 5 of 5 on BT.

### Stage 2: the hot path at the old cadence

D2 and D3 whole, the PWM service off, the scheduler at **the measured
stage-0 slot** (~258 µs by the record, set from the measurement, not the
history) and the pulse timers at the final 48 MHz with the literal
terminal 4,095 and `STOP` only, so the field is unchanged and each slot
carries one clean pulse; **the interim scanner stays** (D1), and the
hold-off moves to the new vector. Brightness is **calibrated against stage
0, not assumed**: the old per-slot energy is conditional on Q4 and
per-column (Q12), so the scale table is set here to match the board mean
(k ≈ 10 for one clean pulse, up to 16 if the baseline carried the release's
extra light, D2), and the change is recorded. Gates: no PWM object or
vector retained (the linker map); the LED part of the handler ≤ 10 µs and
the complete handler within stage 0b's attribution; the callback metric
drops accordingly; **the waveform witness** shows, at this clock, one pulse per
slot of the programmed width, no pulse during a held-off slot, a clean
restart, and the right behaviour at input bytes 0 and 255 (match values 0 and `scale_lut[255]`,
2,550 to 4,080 ticks by k) and a literal match value 1 on the pulse timers,
and a late dim-to-bright transition;
holding the scheduler's interrupt off for 5 ms shows every row dark and no
pulse repeating; deliberate service delays at several phases and across
several slots produce the expected elapsed-slot deficit, no repeated,
overlong or wrong-row pulse, omissions attributed to the right row and
colour, and a bounded critical section; delays injected between the
snapshot's reads and after the arm are counted, never mis-serviced;
**the long-gap injections**, each by a dev op, each timed only by the
independent witness's marker edges below (the host's command round-trip
is not a timing method and is not used; the frame counter is the
board's own witness on USB, not the test's clock), each judged by the
record afterwards, each with exactly the outcome D3 step 1's case claims
for the measured gap, and each showing its VALID or INVALID state in the
record:
**each expected outcome is predicted, before the run, from the
measured silence and the measured clock rate, never asserted by length
class.** Every injected silence and every row-only hold is bracketed by
**marker edges on the witness**, which are the authoritative timing. The
marker is the Caps Lock indicator's pin, D15, a plain GPIO the op drives
directly with the tick's software PWM for it paused for the test, probed
at the LED; a nested case gets two markers (the row-only hold on D15, the
inner mask on the Win Lock indicator's pin, C15). **The endpoint
contract:** for a silence of every interrupt, the op masks first and
raises the marker inside the mask, and lowers the marker inside the
mask before it unmasks, so the marked interval lies within the silence
and is shorter than it by two stores, under 0.1 µs each; for a row-only
hold, each marker edge and its NVIC write with the barriers
(`core_cm0.h:659`) sit together inside one short critical section, so
nothing can preempt between the pair and their separation is the few
cycles of the write, bounded and recorded. The LED pulse train is not
the measurement: it shows the outer hold only, and omitted pulses blur
its edges. The measured length carries its uncertainty explicitly: the
endpoint offsets above; the
observation offsets of D3 case 2 at both ends, taken for the mode in
force (the tick running, or stopped with the handler in scan-only) from
the observers' own synchronized stamps in the record, never from a
nominal period; and the capture clock's accuracy, **qualified, not
assumed**, by timing a known one-second mark from the host over a minute
before the run and recording the figure. CT16B5's rate is measured
against the same qualified capture clock over the preceding minute. The
prediction is made over that whole interval, in terms of the observation
gap, and a duration whose interval straddles a wrap boundary or the 8 ms
threshold is changed until it does not. The residues quoted here are nominal
examples at 187,500 Hz: a residue modulo 349.525 ms under 8 ms can alias
on battery (350 ms leaves 0.475 ms, 700 ms leaves 0.949), and a residue's
rate dependence grows with the length (7 s leaves 9.5 ms nominally but
6.7 ms at 400 ppm slow, so its outcome is whatever the measured rate
predicts). **The mandatory guard-rejection case is therefore a 1 s
silence**, whose residue, 301 ms nominal, stays above 8 ms at any rate
the IHRC can have. On USB the frame counter rejects whatever the guard
does not, and an interval both reject counts one loss. **The no-USB
case needs the data cut, not the power cut:** on this bench a switched-off
port cuts VBUS only, and the board enumerates over data alone, so a
relay-2 "battery" state still has SOFs and the USB witness
([docs/test-bench.md](../docs/test-bench.md), "A port switched off still
carries data"); the no-USB injections are armed over raw HID before a
`uhubctl` data cut, fire after a delay long past the bus discontinuity
(whose own interval is INVALID by the continuity contract), keep their
result in the record through reconnection, and are read back afterwards.
The set: row-only hold-offs of 100 ms, 200 ms, 700 ms and 7 s, exact
(~800, ~1,600, ~5,600 and ~56,000 missed slots at 125 µs; the stage-2
equivalents at 258 µs); a silence of every interrupt of 5 ms, exact; of
20 ms, 100 ms, 200 ms and 1 s, INVALID by the guard with one epoch loss on
either power source; of 350 ms and 700 ms on USB, INVALID by the frame
counter with one epoch loss, never a small healthy count, and of 7 s on
USB, INVALID with one loss by whichever check fires first; of 700 ms on
USB with the host suspending the bus during the hold, and again with a
bus reset, and again with a disconnect, each INVALID by the continuity
contract, each followed by recovery (re-enumeration where it applies)
and a VALID next interval; 350 ms, 700 ms and 7 s with the data cut,
where aliasing is possible, each outcome predicted from the measured
silence and rate and written into the result as the declared limit; each
kind also started after an arm; **the near-threshold cases**: silences of
every interrupt of 7.5, 7.9, 8.1 and 8.5 ms, each at several phases
relative to the last observation, first with the tick running and again
with it independently stopped and the handler in scan-only, each outcome
predicted from the recorded gap, exact under 8 ms and INVALID at or over,
the two modes giving different gaps for the same silence; **the ordering
case**: a 20 ms silence of every interrupt
inside a row-only hold-off that lasts 100 ms longer, so the tick
invalidates and re-primes before the row handler returns, whose interval
must still be excluded by its generation and counted once; the tick
stopped and restarted independently of sleep, by light sleep's control,
while the handler runs scan-only, VALID throughout; a deep-sleep cycle,
INVALID on entry and re-primed by the first tick after wake;
`OD_LOCK_TRANSACTION` entered and left on a dev build, INVALID across it
with no re-prime inside it; and an hour of ordinary running on each
power source with no false epoch loss; widths
bytes 0 (off) and 255 (full) also right by eye; no wrong-colour row in a
hue sweep; the 660-byte
clock-digit blits and their neighbouring sizes clean for a night on a dev
build, with VIA key assignment running during LCD DMA (the repository's
reliable flash/DMA reproduction, [docs/hardware.md](../docs/hardware.md))
and `invariant_fail` 0, no blit timeout or poll give-up; the 20 kHz tick's
rate and worst gap unchanged; deep sleep 10 of 10 on 2.4G and 5 of 5 on BT
with the waking key kept, and one long unplugged BT sleep per board;
scan-only on dev; incremental LED power within 3% of the mean the scale
was set to, per colour.

### Stage 3: the scan without mode writes

D3 step 3: atomic row select, the two-port reads, fixed pin modes, the
settle from Q1's sweep, the ISR-side transition counters for the rig's
keys, and **the consume count made exact**: the transitions are derived
from the very snapshot copied into `raw_matrix` inside the lock (the XOR
taken there, the popcount outside), so nothing reaches debounce
uncounted. Cadence unchanged by construction now that the scheduler is
fixed. Gates: **Q1's delay sweep passed with margin** (held cross-row
chords, each colour active, both boards), not a fixed 2 µs plus typing;
every key and the knob in VIA's key tester; six row counts within one of
each other over an uninterrupted window; `row_gap_max` no worse than stage 0's under the same load and under 7 ms
in any window, those with the PCF hold-off judged apart; no column leak with held keys and chords; the rig's
delivery gate against the stage 0 short-tap baseline; a night's soak. The
I2C hold-off stays.

### Stage 4: the clock chip's transaction unmasked

D6, and first **the writer's bracket width and its success or failure
exposed** on the RTC status page: today the writer computes its edge
without keeping the width (`rtc/rtc.c:1668`) and the page carries the
release and boundary errors and the acquisition uncertainty but not the
width (`rtc/rtc.c:2285`), so the gate below has nothing to read without
it. Gates: a forced PCF write filmed shows no dark frame, on USB and off;
`i2c_max_cycles` ≤ ~3.5 ms and the 5 ms path around deep sleep inside its
budget; the bracket's width and the release error at baseline (Q3);
stuck-bus injection and the restart pass with no pass ≥ 25 ms; a night of
syncs settled every time; UART overruns and refused bytes at baseline;
sleep and wake cycles under load. Then the follow-up: retire `pcf-unseen`'s
deferral.

### Stage 5: the cadence

The slot to 125 µs with the literal terminal 2,047 (D2) and the scale
rescaled (D4); D8's accounting validated on a constant frame first. Gates: ~8,000 serviced slots a second
and 444 samples a second a row; the handler's elapsed share ≤ 20% and its
latency tail bounded; `row_gap_max` ≤ 4 ms; omissions zero in quiet runs
and under 0.1% under mixed LCD, UART and flash load, with the longest run
examined; **incremental LED power per colour, white and at value 64,
within 5% of stage 0's holds after the scale is set to the measured
ratio**, forward and backward; the camera's brightness within the same
tolerance at fixed exposure; `rgb_fit.py` refitted and the model's
residuals checked, the dark and base terms included; **the lowest codes
on camera and the witness, values 1-16, monotonic and within tolerance of
stage 0**; the SPI DMA size sweep repeated; the 20 kHz tick unchanged;
**stage 4's clock gates, the wireless gates and the sleep and wake gates
repeated at this cadence** (passing them at 258 µs establishes nothing at
125). **This is the release candidate.** The 62.5 µs experiment, if
attempted, repeats every gate with the handler ≤ 12 µs and the literal terminal
1,023, and reports the low-code drift against G4 for a decision.

### Stage 6: the precision path

D9, one feature at a time, each with its own flash and preview. Gates: the
allocation ledger and the heap gap on each board's feature set; monotonic
low-end steps by camera at values 1 to 16; no glitch at 0 or full; every
effect through the power caps, darkness, profile restore, preview and
cancel, both Win/Mac remembered states, host backup and restore, the
transitions between byte and wide effects, and sleep; render preparation
≤ 0.5 ms a changed frame; the SPI DMA sweep once more; `rgb_fit.py` refit
if the per-unit drive moves.

### Stage 7: the release check

A combined soak with the power-model refit: a night each on black and
white under typing, LCD, clock and flash activity; zero unexplained resets
or timeouts, zero non-flash passes ≥ 25 ms, no regression in transport or
delivery; the consolidation pass remeasured; `build.sh`'s structural and
RAM gates; the docs updated (LED, hardware, sn32f299's "How this board uses
them", the health pages, the power doc's LED figures).

## The key-press rig: rebuilt, it is the scan's gate

JD offered (10-31) to rebuild the wake rig, broken 10-23, with some
soldering, and to make it better than before. It should be rebuilt in
stage 0: the scan change is the one part of this plan that can lose
keystrokes, and a rebuilt rig turns that gate from JD's typing and VIA's
key tester into a count. The old rig's record
([docs/test-bench.md](../docs/test-bench.md), "The wake rig"): the relay
closed on a 5 ms command, 15 ms presses registered 10 of 10, 200 of 200
reached the Mac at typing speed, and `relay_press_test.py`,
`keydrop_test.py` and `deep_cycles.py` still exist, counting at the board
(`raw_edges`, `key_presses`) and at the Mac (the F19 listener, the session
unlocked).

What "better than before" should mean, most valuable first:

1. **Strain relief, and the right wire.** A lead tearing off its switch
   is what retired it, and the lead was PC power-supply wire, about ten
   times the copper a matrix line needs, so every move of the keyboard
   levered the joint. Use 28-30 AWG silicone-insulated stranded hook-up
   wire (the handwiring kind), a two-pin connector a few centimetres from
   the plug so the keyboard unplugs from the rig instead of pulling on the
   joint, and a tape loop or glue anchoring the lead to the case before
   the socket.
2. **Two keys on different key rows**, the old (0,13) and one low on the
   board, so a scan fault on one row cannot hide behind another; the same
   column for both covers the shared-column leak case.
3. **An optocoupler across each switch's contacts**, not a bare MOSFET
   (which is not galvanically isolated), driven by JD's QT Py RP2040 from
   the Mac over USB serial. The part is the Sharp PC817C (JD's order,
   10-31; the TLP222A photorelay would do too but takes a month to ship):
   its LED from the GPIO through 330 Ω (~6 mA), its phototransistor across
   the contacts with the collector, pin 4, on the key's column side and the
   emitter, pin 3, on the diode-and-row side; a wrong orientation registers
   nothing and harms nothing, since the keyboard's own diode blocks the
   reverse path, so the rule is try, then swap. Its microsecond switching
   is faster than a photorelay's millisecond turn-on, which suits the
   short-tap tests. The wiring reference is the artifact "AK820 key-press
   rig: QT Py RP2040 + TLP222A" (a PC817C panel beside the TLP222A one). The PC817C's switching times
   and its behaviour when reversed, and the LVC buffer's ratings in item
   4, come from the manufacturers' datasheets, not from this repository's
   sources, and stay labelled unverified until the exact parts' datasheets
   and the qualification's results are recorded with the rig. It gives: silent, bounce-free presses
   timed to the millisecond, down to 1 ms, with the turn-off time and the
   polarity qualified, and **the actual contact closure timestamped at the
   rig**, not only the host's command. Presses of 8-12 ms sit on the
   debounce boundary (5 ms stable, `sym_defer_pk`) and are where a slower or
   unfair scan shows first. Keep the isolation the dry contacts gave: the
   keyboard and the rig share nothing but the opto's light. The relay board
   stays for the power cut.
4. **A waveform witness.** Nothing on the bench today can see a pulse: the
   camera integrates 4 ms, the INA228 ~200 ms, and a register snapshot
   shows a parked counter, not what the output did in between. The gates
   that rest on one clean pulse per slot, no pulse during a hold-off, a
   clean restart and the low codes (stage 0b, stage 2, stage 5) need a
   capture at tens of nanoseconds on one column pin and one mux-row pin:
   a borrowed scope, or an RP2040 board (JD's QT Py RP2040 is one) with a
   PIO capture. **The instrument's figures are part of the gate:** the
   smallest width it must resolve is the smallest the table emits for byte
   1 at nominal calibration: ~208 ns at stage 2's cadence (k ≈ 10), ~104 ns
   at the 125 µs cadence (4.845) and ~42 ns at the 62.5 µs experiment
   (2.42), always derived from the actual table; and the restart-glitch
   test looks for a single 20.8 ns tick, which sets the instrument; so the
   acceptance instrument samples at **100 MS/s or faster** with a stated
   bandwidth and a width uncertainty of one sample (the RP2040's PIO at
   125 MHz, or a scope of ≥ 100 MHz). A 24 MHz analyzer, sampling every
   41.7 ns, can miss a one-tick pulse entirely and is a supplementary
   instrument for one-pulse-per-slot and parked-between-slots checks only,
   never for width-1, the glitch test or the width gates.
   **The probe must not load the line.** The columns are inputs with
   50-100 kΩ pull-ups whenever IOEN releases them for a scan
   ([docs/sn32f299.md](../docs/sn32f299.md), "Electrical"), so a resistive
   divider of a few kΩ to ground would pull a released column low and
   fake a key, and would bias the column transistor during PWM; it is
   ruled out. The front end is high-impedance and rated for the rail,
   which is ~3.9 V on battery and **4.47-4.79 V on USB** (the same doc,
   "At a glance"): a single-gate LVC Schmitt buffer per channel (TI's SN74LVC1G17 or
   Nexperia's 74LVC1G17), powered from the QT Py's 3.3 V, whose input is
   rated for 5.5 V with the part unpowered or at 3.3 V; its worst-case
   input leakage, input capacitance and minimum pulse width are taken
   from the chosen manufacturer's datasheet and written into the
   qualification, not assumed from the part name (TI rates the leakage at
   ±5 µA maximum, which against a 50 kΩ pull-up is up to 0.25 V of droop
   at the worst corner, which is exactly why the released-column check
   below is the admission, not the figure); fed through 1 kΩ for safety
   and driving the capture pin at 3.3 V; or a 10 MΩ, ≤ 15 pF scope probe. Qualification before any
   gate is read: with the probe attached, the released column still reads
   high on the witness itself, VIA's key tester shows no phantom on that
   column, and the PWM waveform on the line is unchanged against an
   unprobed neighbour, with the board on USB (relay 2 on, the data through
   the hub), where the grounds are already common.

The rig's own closure timestamps are what the chain starts from. Counts
and short-tap acceptance need no clock sync. A latency claim does: the
offset between the rig's clock and the Mac's is measured by serial
round-trip at the start and the end of every batch, its uncertainty (half
the round-trip, typically under 1 ms) and the drift between the two
measurements are reported with the result, and differences inside that
bound are not claimed.

The delivery gate counts the chain: commanded closures → ISR-side
transitions on the rig's keys (temporary counters, since `raw_edges`
cannot see a press and release inside one consume) → `raw_edges` →
`key_presses` → the host's down and up events, with the wireless retries,
give-ups, replacements and queue drops beside them. At least 1,000 presses
per transport at 15 ms and 25 ms press dwell with a defined release dwell,
every one registered at every link, under each stressor in turn: idle, a
hue sweep, a Solid frame, an LCD repaint, a burst of settings writes, a
2.4G request stream; then 8, 10 and 12 ms to map the debounce boundary,
which must not worsen; then latency distributions, not totals, which
should lose about 1.2 ms of mean sampling delay at the first cadence and
1.8 at the second (a bounded component, not 4.6 ms from every press). The
historical marginal limit (25 ms held, 10 ms open) is characterized
separately, not required. Stage 0 collects the short-tap baseline with
the repaired rig on today's firmware, so "no worse" has a number. The rig is a prerequisite for stage 3's
acceptance: its stage-0 baseline and the candidate's short-tap comparison,
with the release dwells recorded, are the gate, and manual testing does
not substitute for them.

## Risks the history says to respect

- **SPI0 shares priority 3.** A 188 µs callback delayed the DMA
  half-transfer handler by 188-258 µs; a 10 µs one delays it less, but
  higher-priority handlers and simultaneous pending sources add to any
  figure, so there is no established maximum. The race that window
  exposed is fixed (`c57623d0d2`), but the exposed transfer sizes move: the
  clock-digit sweep with VIA assignment during DMA runs at stage 2, at each
  cadence, and after the precision work. Flag clearing stays narrow.
- **`IC` is write-1-to-clear:** write what `RIS` returned, nothing wider.
  The lost-completion bug on SPI0 was exactly this. (The ChibiOS LLD's
  `pwm_lld_disable_channel()` ORs into `IC`, `hal_pwm_lld.c:408`; the new
  driver does not inherit it.)
- **The write key** on CT16B0, B2 and B4 for `MR`, `MCTRL` and `PWMCTRL`;
  not on `TMRCTRL`; B1 has none. **`CEN` last**, and written every restart
  because a stop match clears it.
- **Stop without reset, never both; channel matches strictly below the
  terminal; the terminal window shorter than the slot by the service time
  and the guard** (D2).
- **The ends of the duty range:** value 0 must be truly off and the top
  value truly full; the +1 period lesson of 08-31; equality with the
  terminal is a special case, not the rule.
- **UART2's ~87 µs byte deadline:** no masked span near it; `PRIMASK`
  defeats priority; the critical section in D3 step 6 is under 2 µs with a
  5 µs ceiling; the masked flush copy is 10-16 µs.
- **Matrix sampling never depends on the consumer's phase** (the 09-03
  fix); the rolling matrix, the six-row priming mask and the locked
  consume-copy-clear stay; no sticky edge bits.
- **No ChibiOS call from the handler** that is not I-class, and the port's
  prologue and epilogue kept. The old callback's `pwmEnableChannel()` from
  interrupt context unlocked interrupts mid-handler.
- **The priority table stands:** UART2 and the system timer 0, USB 1, the
  20 kHz tick 2, the row interrupt and SPI0 3.
- **The torn frame** (D8), **the flash-program path** (D5), **the stored
  values' brightness** (D4), **the drive accounting** (D8), **Bootmagic's
  first scan** (D1), **the out-of-array `MR[9]`** (D1).
- **Do not report stalls by drawing to the LCD being measured;** keep
  power-source changes, host pollers and firmware changes apart in A/B.
- **Flash and RAM:** the old driver (2.3 KB code, 0.25 KB rodata) and the
  PWM layer (3.5 KB) leave; the new driver and its tables (the scale table
  512 B, the column map, the masks) are budgeted to come in under that,
  verified on the linked image at stage 2; the ~552 B of
  PWM objects is gross: the handler's counters, accumulators and tables in
  RAM come off it before anything is claimed, and black has 24 B to spare
  today. The heap gap is checked by `build.sh` (floor 128 B) on both
  boards' feature sets.
- **The drain on white:** stage 1 keeps the pulse machinery and is measured within 3%,
  stages 2 and 5 by calibration against stage 0 (the mean; Q12), and the
  model's dark and base terms are verified alongside the LED terms before
  it is called valid again; flashes keep their settings as every flash
  since P5a does.
- **Black's open deep-sleep reset** is not this plan's to fix, and this
  plan must not make it harder to see.

## Open questions, and what settles each

| | Question | Settled by |
|---|---|---|
| Q1 | The column settle after release, select and restore, with pressed keys across rows and the transistors' stored charge. | A dev delay sweep against ISR samples and raw errors with held cross-row chords and each colour active, on both boards; keep margin above the shortest clean setting. Expect single microseconds. |
| Q2 | How many of the 4,096 codes are optically distinct at the bottom. | A photodiode or scope on isolated low-width pulses if one is borrowed; the camera and the logger reject obvious plateaus and non-monotonic steps only. Values 1-16 by camera is the stage 6 gate. |
| Q3 | The PCF bracket's and the 5 ms deep-sleep path's tolerance of a 20% longer transaction. | `rtc.c`'s bracket math and `docs/clock.md`'s seed budget; per-kind transaction times, the bracket width and release error, the daemon's residuals, over a night of syncs with the handler preempting; the pre-sleep read and wake recovery under load. |
| Q4 | What a stall shows today: does the counter free-run (a hot row) or stop (dark)? | Stage 0b's register capture and row-only hold at Solid white, by eye, camera and INA228. Gates the old light-energy figure D4's scale starts from; pulse shape needs a scope. |
| Q5 | Restarting a stopped counter: `TC` writable while stopped; `CRST` self-clear cycles; the terminal-equality case; selecting the mux before the restart lights nothing. | Stage 0b on all three timers with the widths 0, 1, terminal−1 and an invalid terminal, service delayed; `TC` and `CEN` recorded; gross optical output. (`CEN` cleared by a stop match is documented, `sn32_ct.h:357`.) |
| Q6 | Which physical LED each mux pin drives, so the colour-slot table is right. | Stage 0b's single-key, single-colour patterns per key row with a slow tagged slot sequence. Decides D3 step 5's table and the valid rainbow comparison. |
| Q7 | Closed: the handler keeps the port's prologue and epilogue (D3). | |
| Q8 | Does the consolidation lose short presses today, and how long does its pass block after the rewrite? | Rig presses of 25-40 ms phase-swept across a forced cleanup, ISR transitions against consumed against debounced against host; the stall counters. Out of scope to fix; in scope to know. |
| Q9 | Does a cheaper handler save power? | Matched dark and lit power-map holds; the awake loop spins rather than sleeping (`config.h:248`), so expect little until light sleep is wider. |
| Q10 | Is the precision path's RAM viable on both boards? | The allocation ledger before stage 6; the linker map and stack watermarks per flavour after. |
| Q11 | Is black's deep-sleep reset independent of this rewrite? | Its retained phase diagnostics, long unplugged BT sleeps with the logger's wake edges, on black; white's clean short sleeps cannot settle it. |
| Q12 | Is today's light brighter on the right-hand columns, as the release order predicts? | Per-column means from a fixed-exposure camera frame at Solid white (stage 0); the witness on a left and a right column. Decides what "brightness preserved" means: the board mean, with the gradient's removal recorded. |
| Q13 | Can the bench see a pulse? | The witness of the rig section, item 4: a Pico PIO capture or a borrowed scope on one column and one mux row, before stage 0b's lifecycle tests are run. |

## Noted, not planned: the consolidation

The erase blink needs an EEPROM whose erases do not stall the core: the
external SPI flash (QMK has a SPI-flash wear-levelling backend; the
board's SPI1 is shared with the LCD blit DMA and has its own driver in
`graphics/lcd_bus.c`, so it is a project), or a compensation the eye might
accept (the stall is software-initiated, so the driver could boost the
fields either side; unproven; needs the headroom D4 leaves). Running the
handler from SRAM is not a fix, since the vectors cannot move; a wholly
SRAM-resident polling erase routine is conceivable but unproven and
substantial, and does not belong in this rewrite. The main-loop block that
can swallow a press is a separate work package if zero loss through
cleanup is ever required. All belong in `BACKLOG.md`, not here.

## Comparison with codex's design (the decision log, revision 1)

Taken from codex, which revision 0 lacked:

- **The scheduler on CT16B4 with one-shot pulse timers** (D2). Revision 0
  kept the PWM period match as the interrupt, so every late start still
  lengthened the field, and its "luminance-neutral by construction" rested
  on an assumed on-fraction. The fixed slot makes the field deterministic,
  turns a late start into a moved pulse, and makes brightness a calibrated
  scale (D4) instead of an argument.
- **Fail dark, count, never replay** (D3 step 6, G8).
- **The `NO_LED` bounds read** in the current driver; explicit zeros.
- **The colour-slot order** and the doc's rainbow figure being three times
  too high; the 30 µs delay that is six barrier iterations. Revision 0
  repeated both from the docs.
- **The CIE curve upstream**, which voids revision 0's D9 (a wide table in
  the handler cannot restore a plateau the conversion already made); the
  precision path now starts at the conversion.
- **The scan started in matrix init** for Bootmagic and RGB-off builds.
- **The 72.8% caveat** (callback occupancy, not the handler) and measuring
  the complete handler from the scheduler's counter (D10).
- **Finer staging**: truth first, then ownership, then the hot path at the
  old cadence, then the I2C, then the cadence; revision 0 changed the hot
  path and the cadence in one flash. Same-session A/B; the 3% hold
  tolerance where the cadence does not change.
- The bootloader's common quiesce; the dark frame kept through a wake;
  the power-savings caveat; the consolidation's main-loop block.

Kept from revision 0:

- **The channel-match ceiling as a stall-safety rule**, not only a range
  rule. (The stop-plus-reset trap was in both designs; revision 1 wrongly
  credited it to revision 0 alone, corrected by the collaborator.)
- **The scan's dark-time argument**: the columns are left high by the
  terminal match, so only the pressed columns move at the select
  (conditional on the window having parked before the slot, D2).
- **The rig section** with the three upgrades and the per-stressor counts;
  codex asked for the repair and the chain-of-custody count, merged into
  the gate.
- **The I2C staging reason in numbers**: ~9.6 ms if unmasked before the
  hot path, ~3.1-3.25 ms after.
- **The measured object sizes** for the flash budget, reclassified by the
  collaborator.

Rejected from codex, with the reason:

- **Prepared 18×15 frames adopted at a field boundary** (1,080 B of RAM on
  a build with a 224 B gap, and a submitted-versus-displayed gap for
  `committed_dark`'s callers). Pointer swapping of the existing buffers is
  not rejected with it (D8).
- **A 25 µs handler target as the release ceiling**: 20% at 125 µs slots,
  40% at 62.5; the ceiling is per cadence (D3).

Revised by the collaborator: **444 Hz is the release candidate and 889 Hz
the experiment** (revision 1 had them the other way round; D4 says why).

## Revision 2: the collaborator's findings, dispositions

Every finding of [`review-codex-row-isr-collab-2026-10-31-raw.md`](review-codex-row-isr-collab-2026-10-31-raw.md),
with what changed.

| Finding | Disposition |
|---|---|
| Fail-dark cannot be implemented with one latched flag; the deadline check must be atomic with the arm. | **Accepted.** D3 step 1 counts elapsed slots from CT16B5 and re-reads `RIS` at exit; step 6 puts the check and the arm in one critical section. |
| 27 invalid lookups a field, not 9. | **Accepted**, corrected. |
| The colour-order derivation is right; physical wiring unverified. | **Accepted**; Q6 reworded, stage 0b's tagged patterns. |
| "Nothing" for the six-iteration delay: call it short and uncalibrated. | **Accepted.** |
| Starting the timer does not make Bootmagic correct; prime all six rows synchronously. | **Accepted**, D1. |
| D10's `TC` alone misreports: latency modulo a slot, exit = latency + elapsed, the port's overhead outside the hooks. | **Accepted**, D10 rewritten with the epoch cross-check and honest labels. |
| Stage 2 could not keep the cadence while the old callback re-armed at its end. | **Accepted**; stages 2 and 3 swapped: the fixed scheduler first, at 258 µs with the old scan kept, then the scan change. |
| Bootmagic's direct jump needs the common quiesce; sleep admission unchanged. | **Accepted**, D7. |
| Consolidation's duration must be remeasured, not assumed 58 ms. | **Accepted**, stage 7. |
| Codex did identify the STOP/RST trap; the decision log was wrong. | **Accepted**, corrected. |
| "Columns already high" is conditional on the window having parked. | **Accepted**, D2's per-cadence window makes it hold. |
| The rig: isolation, closure timestamps, release dwell, `raw_edges`' blind spot, "must not worsen", the latency arithmetic. | **Accepted**, all in the rig section and stage 3. |
| The I2C estimate divides by the remaining fraction. | **Accepted**, D6 (3.1-3.25 ms; 9.6 under the old handler). |
| Object sizes reclassified; black's 152 B gap; the `.bin` cannot measure flash. | **Accepted**, "What is known" and the risks. |
| Pointer swapping is not what was rejected; reject the frame handoff only. | **Accepted**, D8. |
| 889 Hz only conditionally: 9.3 bits, channel 1 −17% under rounding. | **Accepted**: 444 Hz the release candidate, 889 the experiment with the trade declared (D4, G3, stage 5). |
| D4's second-cadence headroom used the first cadence's width. | **Accepted**, corrected (~37 µs). |
| G3's "under 2′" fails at 444 Hz for the widest pair; G5's 10.3 bits is first-cadence only. | **Accepted**, both reworded. |
| `TMRCTRL` is not keyed. | **Accepted**, D2 and the risks. |
| Equality with the terminal is a special case; keep strictly below. | **Accepted**, D2. |
| `STOP` clears `CEN` is documented; make the restart contract explicit. | **Accepted**, D2 (`sn32_ct.h:357`), Q5 narrowed. |
| The 85.3 µs window does not fit a 62.5 µs slot; define the lifecycle before allowing it. | **Accepted**: the per-cadence terminal window (1,535 ticks at 62.5 µs) and stage 0b's lifecycle tests. |
| `RIS` cannot count; track epochs; define rotation. | **Accepted**, D3 steps 1 and 5. |
| Page 4 has four reserved bytes; update the Rust decoder too. | **Accepted**: a new health page, both decoders, D10. |
| Stage 0 cannot be "no firmware change" for the register capture and the row-only hold. | **Accepted**: stage 0b added. |
| `HAL_USE_PWM` must go off; drop `&PWMDn`; board-owned LED interfaces; explicit register offsets (`MR[9]` out of array). | **Accepted**, D1. |
| The masked copy is 10-16 µs; test the guard against it; "committed dark" is the front frame, sleep's blanking authoritative. | **Accepted**, D8. |
| Per-colour emitted width sums, not a global omission percentage; the model's base and lit overhead; fit against incremental LED power after dark subtraction; forward/backward holds. | **Accepted**, D8, G4, stages 1, 2 and 5. |
| The precision path needs both wide buffers (972 B); the register map `const` in flash; the effect id namespaces, VIA, the tests. | **Accepted**, D9 and D2. |
| Q3 gains the 5 ms deep-sleep deadline; the macro is 10 ms. | **Accepted.** |
| The SPI DMA sweep at both cadences and after precision, with VIA assignment during DMA; no established maximum delay. | **Accepted**, the risks and stages 2, 5, 6. |
| The 20 kHz tick's rate and worst gap as gates; the monitor's 128 µs threshold. | **Accepted**, D10, G7. |
| Keep the port's prologue and epilogue. | **Accepted**, Q7 closed. |
| Black's deep-sleep reset: preserve its diagnostics, bound `CRST` waits, long unplugged sleeps on both boards, the SRAM WFI untouched. | **Accepted**, D7, Q11. |
| Soften "only fix" for the erase. | **Accepted**, "Noted, not planned". |

Nothing was rejected. Two of its remarks are recorded rather than
actioned: that electrical power is a proxy for luminance (hence the
fixed-exposure optical checks stay beside the holds), and that the
historical scan-rate figures between sessions are not comparable (hence
same-session A/B throughout).

## Revision 3: the first readiness review, dispositions

[`review-codex-row-isr-review1-2026-10-31-raw.md`](review-codex-row-isr-review1-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY. Every finding, with what changed.

| Finding | Severity | Disposition |
|---|---|---|
| Admission against the largest width does not guarantee parked timers; a late dim slot's counter runs into the next slot and a brighter duty plus the row select makes an unintended pulse. | must-fix | **Accepted.** D2: admission against the whole terminal window plus skew, tail and guard; the window shortened per cadence (2,047 and 1,023 ticks) so the arm deadline is ~80 and ~40 µs; the parked state defined before the row select; stage 2 tests a late dim-to-bright transition. |
| Missed-slot detection incomplete: `TC` wraps during preemption inside the handler, `RIS` at exit is after the arm, elapsed system time is not an epoch, CT16B5 has fractional ticks and a 349 ms wrap. | must-fix | **Accepted.** D3 step 1: phase-aware reconstruction, round((Δt − Δphase)/slot), re-primed on sleep, scan-only and cadence changes; step 6: the epoch and the pending match re-validated inside the critical section, no arm after a crossed boundary, one service per epoch, the pending re-entry consumes the event; D10 adds crossed boundaries to the elapsed figure; gates inject delays inside the handler and near boundaries. |
| Stage 1 cannot preserve timing while removing the PWM service; stage 2 assumes the old pulse energy before Q4; the old driver's sequential column release; the terminal 255 cannot be reused under "strictly below". | must-fix | **Accepted.** Stage 1 keeps the PWM service and the callback, ownership only; stage 2 removes it with the scheduler and measures brightness against stage 0, setting the scale there if needed; the literal terminal 256 specified; the sequential release's consequence written up as the column gradient (Q12). |
| "Keep the old scan" needs a board-local scanner (`CUSTOM_MATRIX = lite` excludes `quantum/matrix.c`), with context-correct locking (`ATOMIC_BLOCK_FORCEON` is thread-class); its ~28 µs a handler breaks a 25 µs gate. | must-fix | **Accepted.** D1: the interim scanner, a faithful copy with I-class locks; stage 2's budget set from stage 0b's attribution, the LED part ≤ 10 µs. |
| Eyes, the camera and the INA228 cannot certify pulses, restarts or repetition; register snapshots show configuration, not the waveform. | must-fix | **Accepted.** The waveform witness (rig item 4, Q13) required for stage 0b's lifecycle tests and stage 2's and 5's pulse gates; Q1's sweep made a stage 3 gate. |
| The delivery chain is not exact: the consume-side race before the locked copy; `raw_edges` counts bits; rig-host clock sync undefined; the consolidation exception contradicts "every press". | must-fix | **Accepted.** Stage 3 derives the consume count from the copied snapshot; stage 0 collects the short-tap baseline with the repaired rig; the rig section defines the clock sync and starts the chain at the rig's closure timestamps; G6 excepts the forced consolidation explicitly. |
| Push-pull mode assertions touch `MODE` only, not `CFG`. | should-fix | **Accepted**, "What is known". |
| The I2C fallback drives bits push-pull and switches SDA to input for reads and ACKs. | should-fix | **Accepted**, described as such. |
| The 20 kHz tick writes `BSET`/`BCLR`, not `DATA`. | note | **Accepted**, D6. |
| The small-timer `MR[]` has five entries, not four. | note | **Accepted**, D1. |
| D10's slot-count cross-check cannot measure the prologue and epilogue; the port has two return paths. | should-fix | **Accepted**: an assembly-derived bound or the witness; the slot comparison called a cadence check. |
| RAM reduction, flash and model validity asserted too strongly. | should-fix | **Accepted**: 552 B gross with the new state subtracted; dark and base power verified before the model is called valid. |
| Stage 4: the writer's bracket width and success are not exposed. | must-fix (stage 4) | **Accepted**: the status page gains them first. |
| Stage 5: D8's normalization, accumulator widths, atomic take and `lit_ms` undefined. | must-fix (stage 5) | **Accepted**: D8 spells out 64-bit accumulators, the locked take-and-zero, the per-cadence scale, and keeps `lit_ms`'s meaning. |
| Stage 5: value 64 leaves the lowest codes untested; repeat stage 4's, the wireless and the sleep gates at the higher cadence. | must-fix (stage 5) | **Accepted**, stage 5 and G4. |

Nothing was rejected. The reviewer confirmed the write keys, the control
and GPIO masks, the IOEN-to-GPIO behaviour, the documented stop clearing
`CEN`, the cadence and brightness arithmetic, and the object and heap
figures, and found no other interrupt-side mode writer.

## Revision 4: the second readiness review, dispositions

[`review-codex-row-isr-review2-2026-10-31-raw.md`](review-codex-row-isr-review2-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY; the first review's must-fixes 1, 4
and 5 met, 2, 3 and 6 partly open; stage 4 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| Epoch reconstruction reads time and phase without protection; preemption between the reads enters the error; D10's exit calculation misses boundaries crossed after the arm; the 349 ms wrap bound is unsupported. | must-fix | **Accepted.** D3 step 1: the pair read in one critical section; step 6: a fresh coherent snapshot; the serviced epoch advances only at the arm; gaps over 174 ms are an epoch loss, re-primed, never reconstructed; D10 reconstructs crossed boundaries from the entry and exit snapshots; stage 2 injects delays between the reads and after the arm. |
| Stage 2 hardcodes 258 µs, 4.8 MHz and terminal 256, leaving channel 255 no upward headroom if the baseline carried extra light; D8 keeps the identity table until stage 5; stage 0 lacks low-code references and waveform captures. | must-fix | **Accepted.** Stage 2 runs at the measured slot with the 48 MHz pulse timers and terminal 4,095 and calibrates the scale table there (k ≈ 10 to 16); D8's table is calibrated from stage 2; stage 0 adds optical references at values 1-16, the measured slot rate and a capture of today's pulse train. |
| Stage 1 keeps the PWM service yet requires no PWM object retained; "identical by construction" overstates. | must-fix | **Accepted.** The linker gate moved to stage 2; stage 1 verifies only the intended owners and measures the callback's equivalence within 3%. |
| The rig waiver authorizes the manual substitute the first review rejected. | must-fix | **Accepted.** The waiver removed; the rig's baseline and short-tap comparison with recorded release dwells are stage 3's gate. |
| D2 and stage 5 disagree on the windows (2,047/1,023 against 4,096/1,535). | must-fix (stage 5) | **Accepted.** One set of literal terminals, 4,095 at the stage-2 cadence, 2,047 and 1,023 after; G5 reworded; stage 5 and the headroom reconciled. |
| D8's tick-to-value conversion lacks the field-period factor, remainder handling and the non-linear case; validate a constant frame before refitting. | must-fix (stage 5) | **Accepted.** `rgb_ms = Σticks × T_field_ms / k`, the remainder carried, ticks as the unit for a non-linear table, a constant-frame validation before any refit. |
| The flash routines run from SRAM; the erase's hold-off is the vector fetch; today's dark state is conditional. | should-fix | **Accepted**, "What is known". |
| The combined STOP/RST result is an inference. | should-fix | **Accepted**, labelled so in D2. |
| The MODE race overstates: the row helpers' writes are idempotent; the hold-off's rationale is ownership. | should-fix | **Accepted**, "What is known". |
| Rig item 4 ignores the VDD domain, the front end and the capture's accuracy. | should-fix | **Accepted**: the divider or a rated probe, the capture's figures reported. |
| The clock sync has no uncertainty or drift bound. | should-fix | **Accepted**: bounds reported; counts and short-tap acceptance exempt. |
| The per-row counters live on page 3; the record's worst gap was 6 ms. | note | **Accepted**, "What is known". |
| The accumulator wrap is ~97 s per colour, not 29; 64-bit needs the carry. | note | **Accepted**, D8. |
| "Come in under" is a budget, not a fact. | should-fix | **Accepted**, the risks. |

Nothing was rejected. The reviewer re-confirmed the write keys, the masks,
the IOEN behaviour, the stop clearing `CEN`, the I2C direction switching,
the conditional arithmetic and the object and heap figures, and again
found no other interrupt-side mode writer.

## Revision 5: the third readiness review, dispositions

[`review-codex-row-isr-review3-2026-10-31-raw.md`](review-codex-row-isr-review3-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY; the brightness calibration and
the rig waiver met; stages 4 and 5 sufficient; three must-fixes, all on the
measurement side.

| Finding | Severity | Disposition |
|---|---|---|
| A raw 174 ms check cannot see a full wrap of a 16-bit clock: a 350 ms gap reads as 475 µs and reconstructs 4 boundaries instead of 2,800; D10's "less than one slot" misdescribes a fresh service. | must-fix | **Accepted.** D3 step 1: a coarse 32-bit clock from the 20 kHz tick joins the pair; validity is the two clocks' agreement within a slot and under 174 ms; otherwise an epoch loss, re-primed, never replayed; the bound and its exceptions stated; D10: exactly one boundary crossed is the fresh service. Stage 2 injects half-wrap, full-wrap and multi-wrap holds, including after the arm. |
| The 1 kΩ/2.2 kΩ divider loads a released column (50-100 kΩ pull-ups) and can fake a key or bias the transistor; the rail is 4.47-4.79 V on USB. | must-fix | **Accepted.** Rig item 4: the divider ruled out; a high-impedance front end rated for the rail (a 74LVC1G17 per channel, or a 10 MΩ probe); loading qualified in both ownerships and the scan verified unchanged with the probe on. |
| A 24 MHz analyzer cannot certify a 20.8 ns pulse; the gate was not measurable with it. | must-fix | **Accepted.** The acceptance instrument is ≥ 100 MS/s with stated bandwidth and one-sample width uncertainty; the 24 MHz analyzer demoted to a supplementary instrument; stage 0b's widths restated as match values with the glitch test on the fast instrument. |
| Stale stage-1 references for the PWM removal, the linked savings and "by construction". | should-fix | **Accepted**, all three moved or reworded. |
| `row_gap_max` ceilings of 5 and 7 ms against a 6 ms baseline could permit regression. | should-fix | **Accepted**: baseline-relative under matched load, with the absolute ceiling, hold-off windows judged apart. |
| The 1.66× headroom ignores stage 2's calibration uncertainty (1.04× at k = 16). | should-fix | **Accepted**, conditional in D2 and G5. |
| Stage 2 conflates bytes with match values; test `scale_lut[255]`. | should-fix | **Accepted**, stage 2 and stage 0b. |
| D8's non-linear case abandons the value-times-milliseconds contract. | should-fix (stage 6) | **Accepted**: the fixed reference k keeps the unit; the coefficients absorb the curve. |

Nothing was rejected. The reviewer confirmed the earlier safeguards remain
present and found no other interrupt-side mode writer.

## Revision 6: the fourth readiness review, dispositions

[`review-codex-row-isr-review4-2026-10-31-raw.md`](review-codex-row-isr-review4-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY on one area; the third review's two
waveform must-fixes met; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The coarse clock counts serviced ticks, not elapsed time: priority-0/1 handlers collapse ticks, light sleep stops it, it starts after acquisition; agreement with the modulo counter cannot detect a wrap-plus-50 µs gap; the stall counters' own extension needs observation once a wrap. | must-fix | **Accepted.** D3 step 1 replaced: a 32-bit extension of CT16B5 kept by two interrupt-context observers (the tick and the row handler), with an enforced observation bound: any observer gap ≥ 8 ms marks the extension invalid; deep sleep invalidates; matrix init primes; invalid intervals are excluded from every statistic and recovered by one epoch loss and a re-prime; the same extended time at entry, arm and exit. The long-gap injections (170, 350, 700 ms; row-only and all-masked; after an arm; the tick stopped) are now in stage 2's operative gate. |
| The 74LVC1G17's leakage and capacitance were asserted, not sourced. | should-fix | **Accepted**: the manufacturer's worst-case figures go into the qualification; TI's ±5 µA maximum named, with the released-column check as the admission. |
| The minimum widths' cadence labels disagree with D4 (208 / 104 / 42 ns). | note | **Accepted**, corrected and tied to the actual table. |
| "Rows that differ" belongs to `cooked_changes`; `raw_edges` counts bits. | note | **Accepted**, corrected. |

Nothing was rejected.

## Revision 7: the fifth readiness review, dispositions

[`review-codex-row-isr-review5-2026-10-31-raw.md`](review-codex-row-isr-review5-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY on the one remaining area; no
regression elsewhere; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The observation bound is circular: two observers of one 16-bit counter cannot tell a 350 ms gap from the 475 µs it leaves; an 8 ms check on the same modulo difference passes it; the watchdog cannot see a stall that returns. | must-fix | **Accepted.** D3 step 1 rebuilt on an independent hardware clock: the RTC's sub-second counter with its pending flag and the seconds count, which `rtc.c` already stamps. Validity is the agreement of the two clocks' elapsed times within 3 ms + 1% and under 174 ms; the two moduli (349.5 ms and 1 s plus one flagged second) first coincide at 699 s and come no closer than 10 ms inside the watchdog's 12 s, so no returning interruption can read valid. Invalid intervals count one epoch loss, re-prime, and enter no statistic; entry, arm and exit use the one rule; the tick observer is dropped. Stage 2's injections are timed by the host and the RTC, include the 7 s closest approach and a deep-sleep cycle, and must show their invalid intervals in the result. |

Nothing was rejected.

## Revision 8: the sixth readiness review, dispositions

[`review-codex-row-isr-review6-2026-10-31-raw.md`](review-codex-row-isr-review6-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY on the one area; no regression
elsewhere; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The RTC is not a fixed clock: the discipline slews its reload and phase steps reset its counter, so a slewed period makes a 7 s all-masked gap read valid; the 699 s coincidence figure was wrong (the exact repeat is 16,384 s). | must-fix | **Accepted; the RTC is dropped from the mechanism.** D3 step 1 now claims only what is provable on this chip: exact under 174 ms; exact for row-only interruptions of any length through the tick-kept extension; the all-interrupt case bounded to 2 ms by an inventory of every masked or stalled stretch, with an 8 ms observer-gap guard inside that bound; and the one case outside, an all-interrupt stall over 174 ms, declared undetectable on battery (as it is for `timer.c` and the stall counters today) and detected on USB by the host-driven frame counter, whose exact 2.048 s modulus and CT16B5's 349.525 ms cannot agree within 3 ms under 131 s, 49 ms apart at the closest inside 12 s. |
| The pending-wrap arithmetic double-counts; rollover between `SECCNT` and the flag; the coherent reader rejects pending snapshots; re-prime must follow the wake accounting. | must-fix | **Moot with the RTC dropped**; the re-prime is now by the first tick after wake, independent of the wake hooks' order. |
| Stage 2's 170 ms contradicts D3's 174; the 7 s test held only the row interrupt. | must-fix | **Accepted.** The injections restated per case: 100 ms exact for both kinds; row-only 200 ms, 700 ms and 7 s exact; all-masked 200 ms invalid by the guard; all-masked 350 ms, 700 ms and 7 s invalid on USB by the frame counter and recorded as the declared blind spot on battery; a deep-sleep cycle; an hour with no false loss. |
| The PC817C's and the LVC buffer's figures are not in the repository's sources. | should-fix | **Accepted**, labelled unverified until the datasheets and the qualification are recorded. |

Nothing was rejected.

## Revision 9: the seventh readiness review, dispositions

[`review-codex-row-isr-review7-2026-10-31-raw.md`](review-codex-row-isr-review7-2026-10-31-raw.md)
(gpt-6-astra, fresh session): NOT READY; the sixth review's RTC defects
resolved; three consistency points on the scoped claim, and the note that
the universal guarantee is withdrawn.

| Finding | Severity | Disposition |
|---|---|---|
| The 8 ms guard contradicts stage 2's "100 ms all-masked, exact"; "own gap" conflicts with exact row-only holds; no single state machine. | must-fix | **Accepted.** D3 step 1 is now one state machine: the guard is on the gap since the extension's last observation, not the consumer's; an all-interrupt silence of 8 ms or more is INVALID, under 8 ms exact; row-only holds of any length exact; the injections' expected outcomes restated case by case, including the 100 ms all-masked silence as INVALID. |
| The 2 ms bound omits higher-priority service and existing critical sections; the dev global-lock mode reaches 10 ms. | must-fix | **Accepted.** The bound the proof needs is restated as 349.5 ms, not 2 ms; the inventory names the UART and USB handlers, whose accumulated interference the guard measures rather than bounds; `OD_LOCK_TRANSACTION` and degraded mode are excluded modes, INVALID on entry; the tick-stop-and-restart injection restored. |
| `FRMNO` has no continuity contract: SOFs stop on suspend; the oscillator tolerance and degraded mode were unaddressed. | must-fix | **Accepted.** The snapshot takes `INSTS` and a bus-event generation; a pending or serviced bus event makes the interval INVALID; the comparison is modular with a tolerance of 3 ms plus 0.3% of the span against a 49 ms closest approach inside 12 s; degraded mode INVALID throughout; a suspend-during-hold injection added. |
| The battery limitation is a withdrawn guarantee and does not satisfy the earlier universal requirement. | note | **Recorded as the owner's decision.** The universal long-gap rejection is unsatisfiable on this hardware; the existing timer extension and stall counters already carry the same blind spot. The plan states the scoped claim and the one case outside it; the reviewer is asked to judge that claim. |

## Revision 10: the eighth readiness review, dispositions

[`review-codex-row-isr-review8-2026-10-31-raw.md`](review-codex-row-isr-review8-2026-10-31-raw.md)
(gpt-6-astra, fresh session): the owner's withdrawal accepted; NOT READY
on two points; no regression elsewhere; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| Recovery conflicts with the excluded modes: the next observation could revalidate inside degraded mode or the lock mode; no retained history lets the handler see an invalidation the tick already recovered from; degraded mode is in release builds. | must-fix | **Accepted.** Exclusions are flags that forbid any re-prime until the mode ends; a loss generation, incremented at every transition to INVALID, is recorded in every snapshot, so an interval whose generation changed is excluded and counted once regardless of the tick's recovery; the release-build sentence corrected; the ordering case added to stage 2. |
| The injections' outcomes contradict D3: 7 s leaves a 9.5 ms residue and is INVALID by the guard, not aliased; USB need not reject through the frame counter first; reset and disconnect during the hold were missing. | must-fix | **Accepted.** Outcomes are now predicted from the measured duration and the clocks' rates; battery aliasing is possible, not mandatory; one loss per interval whichever check fires; reset and disconnect during the hold added with recovery. |
| The 32-bit extension wraps after 6 h 22 min. | should-fix | **Accepted**: the supported consumer interval is bounded at one hour, longer is INVALID with the generation bumped. |
| "Beyond 12 s" is nominal; the recorded watchdog recovery is 12.3 s. | should-fix | **Accepted**: the USB proof's scope stated as 12.3 s, the closest approach still 49 ms against a 40 ms tolerance. |
| UART overruns witness a silence only if the module was sending. | should-fix | **Accepted**, made conditional. |

Nothing was rejected.

## Revision 11: the ninth readiness review, dispositions

[`review-codex-row-isr-review9-2026-10-31-raw.md`](review-codex-row-isr-review9-2026-10-31-raw.md)
(gpt-6-astra, fresh session): the eighth review's fix met; NOT READY on
two points in stage 2's acceptance specification; no regression
elsewhere; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The 7 s "INVALID by the guard" is unconditional, but at 400 ppm slow its residue is 6.7 ms and aliases; outcomes must be conditional on the measured rate, with a mandatory guard-rejection duration whose residue is safely above 8 ms. | must-fix | **Accepted.** Residues labelled nominal; every outcome predicted from the measured silence and rate; the mandatory guard case is a 1 s silence (residue 301 ms at any rate); 7 s is predicted, not asserted. |
| The bench's "battery" state keeps USB data and SOFs, so it exercises the USB witness; the host round-trip is not the silence's length. | must-fix | **Accepted.** The no-USB injections use the `uhubctl` data cut, armed before it, fired after the discontinuity, retained through reconnection; the silence is measured on the waveform witness as the gap in the pulse train, to one slot. |
| "Of any length" contradicts the one-hour bound. | should-fix | **Accepted.** |
| The watchdog's 12.3 s is an observation and ILRC-dependent; state the USB proof's scope separately. | should-fix | **Accepted.** The proof's scope is 13 s on its own arithmetic (the next near-coincidence at 14.33 s outside it), the tolerance tightened to 3 ms + 0.15% with its justification, and the watchdog's timeout given by its formula, 8.7-12.4 s over the ILRC's range, as a separate bound inside the scope. |

Nothing was rejected.

## Revision 12: the tenth readiness review, dispositions

[`review-codex-row-isr-review10-2026-10-31-raw.md`](review-codex-row-isr-review10-2026-10-31-raw.md)
(gpt-6-astra, fresh session): the ninth review's rate correction and the
no-USB setup met; NOT READY on one point; no regression elsewhere; stages
4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The LED pulse gap cannot time a mask nested inside a row-only hold, and omitted pulses blur its edges; the round-trip instruction contradicted it. | must-fix | **Accepted.** Every silence and hold is bracketed by marker edges on the witness (D15, and C15 for a nested inner mask), with the marker overhead, the capture clock's error and CT16B5's rate bounded and the prediction made over the whole interval; the pulse-gap and round-trip text removed. |
| The watchdog range was inferred from a graph as a guarantee. | should-fix | **Accepted**: stated as a graph-derived estimate, the 13 s scope kept on its own arithmetic, no inference from one to the other. |
| "Three times their sum" was wrong (0.27%, not 0.15%). | should-fix | **Accepted**: the envelope stated (0.09%), the tolerance 3 ms + 0.2%, the 13 s margin recomputed (29 ms against 49). |

Nothing was rejected.

## Revision 13: the eleventh readiness review, dispositions

[`review-codex-row-isr-review11-2026-10-31-raw.md`](review-codex-row-isr-review11-2026-10-31-raw.md)
(gpt-6-astra, fresh session): the markers and the pulse-gap withdrawal
met; NOT READY on the timing contract's remaining gaps; no regression
elsewhere; stages 4 and 5 sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The round-trip timing instruction survived; the marker-to-mask separation was unbounded; the guard measures observation gaps, so "under 8 ms exact" was overstated; the capture clock's ±50 ppm was assumed. | must-fix | **Accepted.** The round-trip text removed and the markers made authoritative; the endpoint contract written (the marker inside the mask; the marker and the NVIC write in one critical section); D3 case 2 restated in terms of the observation gap with the tick's offsets; the capture clock qualified against the host before each run; predictions made over the whole interval. |
| The watchdog inference survived its disposition. | should-fix | **Accepted**: beyond 13 s is simply outside the USB proof's scope, whatever the watchdog did. |

Nothing was rejected.

## Revision 14: the twelfth readiness review, dispositions

[`review-codex-row-isr-review12-2026-10-31-raw.md`](review-codex-row-isr-review12-2026-10-31-raw.md)
(gpt-6-astra, fresh session): the eleventh review's contract met but for
one sentence; NOT READY on it; no regression elsewhere; stages 4 and 5
sufficient.

| Finding | Severity | Disposition |
|---|---|---|
| The "under 100 µs, so a silence under 7.9 ms is exact" promise is unsupported: with the tick stopped the observations are 625 µs apart, and with it running its service latency has no a-priori bound. | must-fix | **Accepted.** D3 case 2 now promises nothing about a silence's length, only about the observation gap, with the offsets recorded per mode from the observers' stamps; case 1's row-only exactness is qualified on another observer keeping the extension valid; stage 2's budget uses the recorded offsets and adds near-threshold, phase-varied injections with the tick running and stopped. |

Nothing was rejected.

## The fourteenth readiness review: READY

[`review-codex-row-isr-review14-2026-10-31-raw.md`](review-codex-row-isr-review14-2026-10-31-raw.md)
(gpt-6-astra, fresh session): READY for stages 0-3 as written, no must-fix
remaining; stage 4 sufficiently specified once 0-3 pass; stage 5
sufficiently specified for the linear-table 125 µs path; 62.5 µs an
experiment with its stated brightness decision. One note, already the
plan's own exception: the consolidation can still swallow a short press
and exceed 25 ms (`BACKLOG.md`), which this rewrite does not promise to
end.

## Process log

- 10-31 02:28: the brief to codex (gpt-6-astra); revision 0 written blind
  in parallel.
- 10-31 02:44: codex's design received (245 lines); revision 1 merged.
- 10-31 02:50: the collaborator pass (gpt-6.1-sol) launched on revision 1;
  03:18 received (186 lines); revision 2 written with every finding
  dispositioned.
- 10-31 03:19: the first readiness review (gpt-6-astra, fresh) launched on
  revision 2; 03:28 received (59 lines): NOT READY; revision 3 written
  with every finding dispositioned.
- 10-31 03:40: the second readiness review (gpt-6-astra, fresh) launched on
  revision 3; 03:55 received (49 lines): NOT READY, four must-fixes for
  stages 0-3; revision 4 written with every finding dispositioned.
- 10-31 04:00: the third readiness review (gpt-6-astra, fresh) launched on
  revision 4; 04:12 received (38 lines): NOT READY, three must-fixes;
  revision 5 written with every finding dispositioned.
- 10-31 04:20: the fourth readiness review (gpt-6-astra, fresh) launched
  on revision 5; 04:33 received (32 lines): NOT READY on one area;
  revision 6 written with every finding dispositioned.
- 10-31 04:22: the fifth readiness review (gpt-6-astra, fresh) launched on
  revision 6; 04:29 received (23 lines): NOT READY on the same area;
  revision 7 written with the RTC witness.
- 10-31 04:33: the sixth readiness review (gpt-6-astra, fresh) launched on
  revision 7; 04:44 received (32 lines): NOT READY on the same area, with a
  counterexample; revision 8 written, the claim scoped to what the chip
  can prove and the USB frame counter added for the bench.
- 10-31 04:46: the seventh readiness review (gpt-6-astra, fresh) launched
  on revision 8; 04:58 received (34 lines): NOT READY on three
  consistency points and the withdrawn guarantee; revision 9 written.
- 10-31 04:58: the eighth readiness review (gpt-6-astra, fresh) launched
  on revision 9; 05:10 received (38 lines): the withdrawal accepted, two
  precise must-fixes; revision 10 written.
- 10-31 05:08: the ninth readiness review (gpt-6-astra, fresh) launched
  on revision 10; 05:17 received (29 lines): two must-fixes in stage 2's
  acceptance specification; revision 11 written.
- 10-31 05:18: the tenth readiness review (gpt-6-astra, fresh) launched
  on revision 11; 05:27 received (21 lines): one must-fix, the silences'
  timing method; revision 12 written.
- 10-31 05:27: the eleventh readiness review (gpt-6-astra, fresh)
  launched on revision 12; 05:36 received (24 lines): the timing
  contract's endpoints; revision 13 written.
- 10-31 05:37: the twelfth readiness review (gpt-6-astra, fresh) launched
  on revision 13; 05:45 received (23 lines): one sentence. The revision 14
  edit then failed on a mismatched anchor and the file stayed at revision
  13, so the thirteenth review (05:46-05:54,
  [`review-codex-row-isr-review13-2026-10-31-raw.md`](review-codex-row-isr-review13-2026-10-31-raw.md))
  re-read revision 13 and repeated the finding; revision 14 written
  after that, on both reviews.
- 10-31 05:54: the fourteenth readiness review (gpt-6-astra, fresh) on
  revision 14; 06:03 received (15 lines): **READY.** Fourteen reviews in
  all after the two designs and the collaborator pass: six on the
  measurement's validity claim until it was scoped to what the chip can
  prove, the rest on the acceptance contract of the dev-only injections.
- Next: stage 0 when the parts land (the plug, the presser on the QT Py
  RP2040 with the PC817Cs, the witness); the presser's CircuitPython and
  the serial backend for `keydrop_test.py` and `relay_press_test.py` are
  the first code to write, before any firmware.
- 14:21 the order of boards corrected: white first, where the bench is, and
  black after each stage's gates pass. Revision 0 had black first, carried
  from the diagnostics' pattern (black carries Warren's deep-sleep
  diagnostics) without a reason, and review 2 had already noted that a day
  on black without the rig measures nothing. A logistics change outside the
  design, not re-reviewed. Committed and pushed.
